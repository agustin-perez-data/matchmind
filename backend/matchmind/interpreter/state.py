"""Interpreter agent: pure-Python live match state.

Consumes raw simulator events one at a time and maintains:

- team stats (passes, accuracy, possession, shots, xG, goals, pressing...)
- an **xG race** (cumulative xG per team at every shot)
- a **momentum** index in [-1, 1] (+ favours the home side), an
  exponentially-decaying "threat" accumulator fed by attacking events
- per-player workload from physical samples, with a live **ACWR**
  (acute:chronic workload ratio) computed ONLY from observables:
  the 28-day load history plus distance covered so far today.

No LLM here: this is the deterministic layer every other agent reads from.
The simulator's latent `fatigue` / `injury_susceptibility` never reach it.
"""

from __future__ import annotations

import copy
import math

# ---------------------------------------------------------------- ACWR

ACUTE_DAYS = 7
CHRONIC_DAYS = 28

# Threat weights feeding the momentum accumulator (event type -> weight)
THREAT_PASS_FINAL_THIRD = 0.4
THREAT_PRESSURE = 0.25
THREAT_TURNOVER = 0.3
THREAT_SHOT_BASE = 2.0
THREAT_SHOT_PER_XG = 8.0
THREAT_GOAL = 5.0
MOMENTUM_DECAY_SECONDS = 120.0  # time constant of the exponential decay
MOMENTUM_SCALE = 10.0  # raw accumulator value that maps to tanh(1)

FINAL_THIRD_X = 66.0  # team-frame x (0 = own goal, 100 = opponent goal)

# League norm: metres covered per minute by position (top-flight averages).
# A player running well below it is showing observable fatigue.
POSITION_NORM_MPM = {"GK": 45.0, "DF": 102.0, "MF": 118.0, "FW": 108.0}


def acwr(load_history: list[dict], today_distance_m: float) -> float:
    """Acute (7-day) over chronic (28-day) mean daily distance, today included.

    Returns 1.0 (neutral) when there is no history to compare against.
    """
    if not load_history:
        return 1.0
    by_day = {int(d["day"]): float(d["distance_m"]) for d in load_history}
    acute = sum(by_day.get(d, 0.0) for d in range(-(ACUTE_DAYS - 1), 0)) + today_distance_m
    chronic = sum(by_day.get(d, 0.0) for d in range(-(CHRONIC_DAYS - 1), 0)) + today_distance_m
    if chronic <= 0:
        return 1.0
    return round((acute / ACUTE_DAYS) / (chronic / CHRONIC_DAYS), 3)


def risk_band(ratio: float) -> str:
    """Sports-science ACWR bands (Gabbett): <0.8 under, 0.8-1.3 sweet spot,
    1.3-1.5 elevated, >1.5 high. Decision support, not medical advice."""
    if ratio < 0.8:
        return "undertrained"
    if ratio < 1.3:
        return "optimal"
    if ratio < 1.5:
        return "elevated"
    return "high"


# ---------------------------------------------------------------- state

def _empty_team_stats() -> dict:
    return {
        "passes": 0, "passes_completed": 0, "shots": 0, "shots_on_target": 0,
        "xg": 0.0, "goals": 0, "pressures": 0, "tackles": 0, "interceptions": 0,
        "fouls": 0, "yellow_cards": 0, "red_cards": 0,
    }


class MatchState:
    """Incremental match state. Call `apply(event)` per event, `snapshot()` to read."""

    SNAPSHOT_TYPES = frozenset(
        {"goal", "shot", "half_time", "full_time", "substitution", "injury_concern", "card"}
    )

    def __init__(self, meta: dict):
        self.match_id = meta["match_id"]
        team_ids = list(meta["teams"].keys())
        self.home_id = meta.get("home_id", team_ids[0])
        self.away_id = meta.get("away_id", team_ids[1])
        self.teams = {tid: _empty_team_stats() for tid in (self.home_id, self.away_id)}
        self.score = {self.home_id: 0, self.away_id: 0}
        self.period = 1
        self.minute = 0
        self.clock = "00:00"
        self.last_event_id = 0
        self.home_attacking_right = True

        self._players: dict[str, dict] = {}
        self._history: dict[str, list[dict]] = {}
        for tid, team in meta["teams"].items():
            for p in team["players"]:
                self._history[p["player_id"]] = p.get("load_history", [])
                self._players[p["player_id"]] = {
                    "player_id": p["player_id"], "name": p["name"], "team_id": tid,
                    "position": p["position"], "shirt_number": p["shirt_number"],
                    "on_pitch": bool(p.get("starter", False)),
                    "minutes_played": 0, "distance_m": 0.0, "sprints": 0,
                    "top_speed_kmh": 0.0, "injury_concerns": 0,
                    "mpm_recent": None,  # metres per minute over the last sampling window
                }

        self.xg_race: list[dict] = []
        self._momentum_raw = 0.0
        self._last_seconds: int | None = None
        self._last_period: int | None = None
        self.momentum_series: list[dict] = []
        self._player_shots: dict[str, int] = {}
        # positional frames (synthetic, from the positional model): shape, heat and pressure
        self._shape: dict[str, dict | None] = {self.home_id: None, self.away_id: None}
        self._heat: dict[str, list[int]] = {}
        self._pressure: dict | None = None
        self._press_acc: dict[str, list[float]] = {self.home_id: [0.0, 0], self.away_id: [0.0, 0]}
        self._block_by_minute: dict[str, dict[int, list[float]]] = {self.home_id: {}, self.away_id: {}}
        self._frames_seen = 0
        self._fan: dict[str, dict] = {}  # per player: what a fan counts (touches, shots, goals, assists, duels won)
        self._minute_marks: dict[int, dict] = {}  # team totals + per-player shots at the start of each minute

    RECENT_KEYS = ("xg", "shots", "shots_on_target", "pressures", "passes")
    HEAT_COLS, HEAT_ROWS = 12, 8
    PRESSURE_RADIUS_M = 8.0

    def apply_frame(self, frame: dict) -> None:
        """One positional frame: team shape, per-player heat and pressure on the carrier.

        Does not touch the clock, momentum or `last_event_id`: frames are a side channel.
        """
        players = frame.get("players") or {}
        if not players:
            return
        self._frames_seen += 1
        minute = int(frame.get("minute", self.minute))
        carrier = frame.get("carrier")
        poss_team = self._players[carrier]["team_id"] if carrier in self._players else None
        by_team: dict[str, list[tuple[str, float, float]]] = {self.home_id: [], self.away_id: []}
        for pid, (x, y) in players.items():
            info = self._players.get(pid)
            if info is None or info["team_id"] not in by_team:
                continue
            by_team[info["team_id"]].append((pid, float(x), float(y)))
        for tid, rows in by_team.items():
            if not rows:
                continue
            outfield = [(pid, x, y) for pid, x, y in rows if self._players[pid]["position"] != "GK"]
            xs_team = [self._team_frame_x(tid, x) for _, x, _ in outfield]
            ys = [y for _, _, y in outfield]
            if not xs_team:
                continue
            cx, cy = sum(xs_team) / len(xs_team), sum(ys) / len(ys)
            compact = sum(math.hypot((x - cx) / 100 * 105.0, (y - cy) / 100 * 68.0) for x, y in zip(xs_team, ys)) / len(xs_team)
            lines = {}
            for pos in ("DF", "MF", "FW"):
                xs_pos = [self._team_frame_x(tid, x) for pid, x, _ in outfield if self._players[pid]["position"] == pos]
                if xs_pos:
                    lines[pos] = round(sum(xs_pos) / len(xs_pos) / 100 * 105.0, 1)
            self._shape[tid] = {
                "block_height_m": round(cx / 100 * 105.0, 1),
                "width_m": round((max(ys) - min(ys)) / 100 * 68.0, 1),
                "compactness_m": round(compact, 1),
                "lines": lines,
                "phase": "attacking" if poss_team == tid else "defending" if poss_team else "transition",
            }
            self._block_by_minute[tid].setdefault(minute, [0.0, 0])
            self._block_by_minute[tid][minute][0] += cx / 100 * 105.0
            self._block_by_minute[tid][minute][1] += 1
            for pid, x, y in rows:  # heat in team frame, so both halves add up into one picture
                xt = self._team_frame_x(tid, x)
                col = min(self.HEAT_COLS - 1, max(0, int(xt / 100 * self.HEAT_COLS)))
                row = min(self.HEAT_ROWS - 1, max(0, int(y / 100 * self.HEAT_ROWS)))
                self._heat.setdefault(pid, [0] * (self.HEAT_COLS * self.HEAT_ROWS))[row * self.HEAT_COLS + col] += 1
        if carrier in self._players and poss_team in by_team:
            ball = players.get(carrier)
            other = self.away_id if poss_team == self.home_id else self.home_id
            near = sum(
                1 for _, x, y in by_team[other]
                if math.hypot((x - ball[0]) / 100 * 105.0, (y - ball[1]) / 100 * 68.0) <= self.PRESSURE_RADIUS_M
            )
            self._pressure = {"carrier": carrier, "team_in_possession": poss_team, "opponents_within_8m": near,
                              "under_pressure": near >= 2}
            self._press_acc[other][0] += near
            self._press_acc[other][1] += 1
        else:
            self._pressure = None

    def press_index(self) -> dict[str, float | None]:
        """Mean opponents within 8 m of the carrier while each team defends (higher = presses harder)."""
        return {tid: (round(acc[0] / acc[1], 2) if acc[1] else None) for tid, acc in self._press_acc.items()}

    def shape_recent(self, minutes: int = 10) -> dict[str, dict] | None:
        """Block height over the last `minutes` against the whole match so far, per team."""
        if not self._frames_seen:
            return None
        out = {}
        for tid, marks in self._block_by_minute.items():
            if not marks:
                continue
            all_sum = sum(v[0] for v in marks.values())
            all_n = sum(v[1] for v in marks.values())
            recent = [v for m, v in marks.items() if m >= self.minute - minutes]
            r_sum = sum(v[0] for v in recent)
            r_n = sum(v[1] for v in recent)
            if all_n and r_n:
                out[tid] = {"block_height_m": round(r_sum / r_n, 1), "delta_vs_match_m": round(r_sum / r_n - all_sum / all_n, 1)}
        return out or None

    def _mark_minute(self) -> None:
        if self.minute not in self._minute_marks:
            self._minute_marks[self.minute] = {
                "teams": {tid: {k: t[k] for k in self.RECENT_KEYS} for tid, t in self.teams.items()},
                "shots": dict(self._player_shots),
            }

    def recent(self, minutes: int = 10) -> dict:
        """What happened in the last `minutes` of play: team totals gained and who took the shots.
        The window starts at the latest minute mark at or before now − minutes (zero before kick-off)."""
        start = self.minute - minutes
        marks = [m for m in self._minute_marks if m <= start]
        base = self._minute_marks[max(marks)] if marks else {"teams": {tid: {k: 0 for k in self.RECENT_KEYS} for tid in self.teams}, "shots": {}}
        teams = {}
        for tid, t in self.teams.items():
            gained = {k: t[k] - base["teams"][tid][k] for k in self.RECENT_KEYS}
            gained["xg"] = round(gained["xg"], 3)
            teams[tid] = gained
        shooters = sorted(
            ({"player_id": pid, "name": self._players.get(pid, {}).get("name", pid), "team_id": self._players.get(pid, {}).get("team_id"),
              "shots": n - base["shots"].get(pid, 0)} for pid, n in self._player_shots.items() if n - base["shots"].get(pid, 0) > 0),
            key=lambda s: (-s["shots"], s["player_id"]),
        )[:4]
        return {"minutes": minutes, "from_minute": max(0, max(marks) if marks else 0), "teams": teams, "shooters": shooters}

    def top_shooters(self, limit: int = 4) -> list[dict]:
        return sorted(
            ({"player_id": pid, "name": self._players.get(pid, {}).get("name", pid), "team_id": self._players.get(pid, {}).get("team_id"), "shots": n}
             for pid, n in self._player_shots.items()),
            key=lambda s: (-s["shots"], s["player_id"]),
        )[:limit]

    # ------------------------------------------------------------ helpers

    def _attacks_right(self, team_id: str) -> bool:
        return self.home_attacking_right if team_id == self.home_id else not self.home_attacking_right

    def _team_frame_x(self, team_id: str, x_abs: float) -> float:
        return x_abs if self._attacks_right(team_id) else 100.0 - x_abs

    def _sign(self, team_id: str) -> float:
        return 1.0 if team_id == self.home_id else -1.0

    def _advance_clock(self, event: dict) -> None:
        seconds = int(event["minute"]) * 60 + int(event["second"])
        if self._last_seconds is not None and self._last_period == event["period"]:
            dt = max(0, seconds - self._last_seconds)
            self._momentum_raw *= math.exp(-dt / MOMENTUM_DECAY_SECONDS)
        self._last_seconds = seconds
        self._last_period = event["period"]
        self.period = int(event["period"])
        self.minute = int(event["minute"])
        self.clock = event.get("clock", f"{self.minute:02d}:{int(event['second']):02d}")
        self.last_event_id = int(event["event_id"])
        self._mark_minute()

    def _push_threat(self, team_id: str, weight: float) -> None:
        self._momentum_raw += self._sign(team_id) * weight

    @property
    def momentum(self) -> float:
        return round(math.tanh(self._momentum_raw / MOMENTUM_SCALE), 3)

    def _record_momentum(self) -> None:
        point = {"period": self.period, "minute": self.minute, "value": self.momentum}
        last = self.momentum_series[-1] if self.momentum_series else None
        if last is not None and (last["period"], last["minute"]) == (self.period, self.minute):
            self.momentum_series[-1] = point
        else:
            self.momentum_series.append(point)

    # ------------------------------------------------------------ apply

    def apply(self, event: dict) -> None:
        self._advance_clock(event)
        handler = getattr(self, f"_on_{event['type']}", None)
        if handler is not None:
            handler(event)
        self._record_momentum()

    def _on_kickoff(self, e: dict) -> None:
        self.home_attacking_right = bool(e.get("home_attacking_right", True))

    def _on_second_half_kickoff(self, e: dict) -> None:
        self.home_attacking_right = bool(e.get("home_attacking_right", False))

    def _fan_count(self, pid: str | None, key: str) -> None:
        if pid:
            f = self._fan.setdefault(pid, {"touches": 0, "shots": 0, "goals": 0, "assists": 0, "duels_won": 0})
            f[key] += 1

    def _on_pass(self, e: dict) -> None:
        t = self.teams[e["team_id"]]
        t["passes"] += 1
        self._fan_count(e.get("player_id"), "touches")
        if e.get("outcome") == "complete":
            t["passes_completed"] += 1
            if self._team_frame_x(e["team_id"], float(e.get("end_x", 0.0))) > FINAL_THIRD_X:
                self._push_threat(e["team_id"], THREAT_PASS_FINAL_THIRD)

    def _on_shot(self, e: dict) -> None:
        t = self.teams[e["team_id"]]
        xg = float(e.get("xg", 0.0))
        t["shots"] += 1
        t["xg"] += xg
        if e.get("player_id"):
            self._player_shots[e["player_id"]] = self._player_shots.get(e["player_id"], 0) + 1
        self._fan_count(e.get("player_id"), "touches")
        self._fan_count(e.get("player_id"), "shots")
        if e.get("outcome") in ("goal", "saved"):
            t["shots_on_target"] += 1
        self._push_threat(e["team_id"], THREAT_SHOT_BASE + THREAT_SHOT_PER_XG * xg)
        self.xg_race.append({
            "period": self.period, "minute": self.minute, "clock": self.clock, "team_id": e["team_id"],
            self.home_id: round(self.teams[self.home_id]["xg"], 3),
            self.away_id: round(self.teams[self.away_id]["xg"], 3),
        })

    def _on_goal(self, e: dict) -> None:
        self.teams[e["team_id"]]["goals"] += 1
        self._fan_count(e.get("player_id"), "goals")
        self._fan_count(e.get("assist_player_id"), "assists")
        if "score" in e:
            self.score = dict(e["score"])
        else:
            self.score[e["team_id"]] += 1
        self._push_threat(e["team_id"], THREAT_GOAL)

    def _on_pressure(self, e: dict) -> None:
        self.teams[e["team_id"]]["pressures"] += 1
        self._push_threat(e["team_id"], THREAT_PRESSURE)

    def _on_tackle(self, e: dict) -> None:
        self.teams[e["team_id"]]["tackles"] += 1
        self._fan_count(e.get("player_id"), "touches")
        self._fan_count(e.get("player_id"), "duels_won")
        self._push_threat(e["team_id"], THREAT_TURNOVER)

    def _on_interception(self, e: dict) -> None:
        self.teams[e["team_id"]]["interceptions"] += 1
        self._fan_count(e.get("player_id"), "touches")
        self._fan_count(e.get("player_id"), "duels_won")
        self._push_threat(e["team_id"], THREAT_TURNOVER)

    def _on_foul(self, e: dict) -> None:
        self.teams[e["team_id"]]["fouls"] += 1

    def _on_card(self, e: dict) -> None:
        key = "red_cards" if e.get("card") == "red" else "yellow_cards"
        self.teams[e["team_id"]][key] += 1

    def _on_physical_sample(self, e: dict) -> None:
        p = self._players.get(e["player_id"])
        if p is None:
            return
        prev_min, prev_dist = p["minutes_played"], p["distance_m"]
        p["minutes_played"] = int(e.get("minutes_played", p["minutes_played"]))
        p["distance_m"] = float(e.get("distance_m", p["distance_m"]))
        if p["minutes_played"] > prev_min:
            p["mpm_recent"] = (p["distance_m"] - prev_dist) / (p["minutes_played"] - prev_min)
        p["sprints"] = int(e.get("sprints", p["sprints"]))
        p["top_speed_kmh"] = float(e.get("top_speed_kmh", p["top_speed_kmh"]))
        p["on_pitch"] = True

    def _on_injury_concern(self, e: dict) -> None:
        p = self._players.get(e["player_id"])
        if p is not None:
            p["injury_concerns"] += 1

    def _on_substitution(self, e: dict) -> None:
        off, on = self._players.get(e.get("player_off_id")), self._players.get(e.get("player_on_id"))
        if off is not None:
            off["on_pitch"] = False
        if on is not None:
            on["on_pitch"] = True

    def _on_half_time(self, e: dict) -> None:
        if "score" in e:
            self.score = dict(e["score"])

    def _on_full_time(self, e: dict) -> None:
        if "score" in e:
            self.score = dict(e["score"])

    # ------------------------------------------------------------ read

    def _player_view(self, p: dict) -> dict:
        history = self._history.get(p["player_id"], [])
        live = acwr(history, p["distance_m"])
        norm = POSITION_NORM_MPM.get(p["position"], 100.0)
        view = {k: v for k, v in p.items() if k != "mpm_recent"}
        minutes = p["minutes_played"]
        view.update(self._fan.get(p["player_id"], {"touches": 0, "shots": 0, "goals": 0, "assists": 0, "duels_won": 0}))
        if self._frames_seen:
            view["heat"] = self._heat.get(p["player_id"])
        view.update({
            "acwr_pre_match": acwr(history, 0.0),
            "acwr_live": live,
            "risk_band": risk_band(live),
            "sprints_per_min": round(p["sprints"] / minutes, 3) if minutes else 0.0,
            # observable fatigue proxies: metres per minute vs the position norm (1.0 = on the norm)
            "effort_ratio": round((p["distance_m"] / minutes) / norm, 3) if minutes else 1.0,
            "effort_ratio_recent": round(p["mpm_recent"] / norm, 3) if p["mpm_recent"] is not None else 1.0,
        })
        return view

    def snapshot(self) -> dict:
        total_passes = sum(t["passes"] for t in self.teams.values()) or 1
        teams = {}
        for tid, t in self.teams.items():
            view = dict(t)
            view["xg"] = round(t["xg"], 2)
            view["pass_accuracy"] = round(t["passes_completed"] / t["passes"], 3) if t["passes"] else 0.0
            view["possession_pct"] = round(100.0 * t["passes"] / total_passes, 1)
            teams[tid] = view

        players = {pid: self._player_view(p) for pid, p in self._players.items()}
        alerts = [
            {k: p[k] for k in ("player_id", "name", "team_id", "position", "minutes_played",
                               "acwr_live", "risk_band", "injury_concerns")}
            for p in players.values()
            if p["minutes_played"] > 0 and p["risk_band"] in ("elevated", "high")
        ]
        alerts.sort(key=lambda a: (-a["acwr_live"], a["player_id"]))

        return {
            "match_id": self.match_id,
            "home_id": self.home_id,
            "away_id": self.away_id,
            "period": self.period,
            "minute": self.minute,
            "clock": self.clock,
            "last_event_id": self.last_event_id,
            "score": dict(self.score),
            "teams": teams,
            "momentum": self.momentum,
            "momentum_series": copy.deepcopy(self.momentum_series),
            "xg_race": copy.deepcopy(self.xg_race),
            "players": players,
            "risk_alerts": alerts,
            "recent": self.recent(10),
            "top_shooters": self.top_shooters(),
            "shape": dict(self._shape) if self._frames_seen else None,
            "shape_last_10": self.shape_recent(10),
            "press_index": self.press_index() if self._frames_seen else None,
            "pressure": self._pressure,
        }
