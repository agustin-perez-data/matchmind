"""Match-state tools: one implementation, two surfaces.

`MatchTools` methods are plain, typed, documented Python callables so they can
be handed straight to Agent Framework agents as function tools AND registered
on the MCP server (see mcp_server.py) for external agents such as Copilot.

Everything here is derived from observables only: the simulator's latent
fatigue / susceptibility never reach this layer.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import time

from matchmind.generate_match import generate

INTERVENTION_ACTIONS = ("substitution", "tactic")


current_session: contextvars.ContextVar[str | None] = contextvars.ContextVar("matchmind_session", default=None)


class LiveStateRegistry:
    """Interpreter snapshot (+ risk summary, credibility, counterfactual branches) per match.

    Every live stream is a session: it writes its own view of the match (its replay may be
    at minute 30 while another viewer's is at minute 80), and the agent tools called from
    inside that stream read that view, through the `current_session` context variable.
    Readers outside any session (MCP clients, REST) get the most recently updated view.
    """

    def __init__(self):
        self._matches: dict[str, dict] = {}          # match_id -> latest view (any session)
        self._sessions: dict[str, dict[str, dict]] = {}  # session_id -> match_id -> view
        self._branches: dict[str, dict[str, dict]] = {}

    def _view(self, match_id: str, create: bool) -> dict | None:
        sid = current_session.get()
        if sid is None:
            return self._matches.setdefault(match_id, {}) if create else self._matches.get(match_id)
        views = self._sessions.setdefault(sid, {})
        if create:
            return views.setdefault(match_id, {})
        return views.get(match_id) or self._matches.get(match_id)

    def update(self, match_id: str, meta: dict, snapshot: dict) -> None:
        view = self._view(match_id, create=True)
        view.update({"meta": meta, "snapshot": snapshot, "updated_at": time.time()})
        if current_session.get() is not None:  # the latest view is also what outsiders see
            self._matches[match_id] = view

    def update_risk(self, match_id: str, risk_summary: dict) -> None:
        view = self._view(match_id, create=False)
        if view is not None:
            view["risk"] = risk_summary

    def update_credibility(self, match_id: str, summary: dict, latest: dict | None = None) -> None:
        view = self._view(match_id, create=False)
        if view is not None:
            view["credibility"] = {**summary, "latest": latest}

    def get(self, match_id: str) -> dict | None:
        return self._view(match_id, create=False)

    def drop_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def sessions(self) -> int:
        return len(self._sessions)

    def ids(self) -> list[str]:
        return sorted(self._matches)

    # ---- counterfactual branches -------------------------------------------------

    def store_branch(self, match_id: str, branch_id: str, branch: dict) -> None:
        self._branches.setdefault(match_id, {})[branch_id] = branch

    def branch(self, match_id: str, branch_id: str) -> dict | None:
        return self._branches.get(match_id, {}).get(branch_id)

    def branches(self, match_id: str) -> list[dict]:
        return [b["summary"] for b in self._branches.get(match_id, {}).values()]

    def base_events(self, match_id: str) -> list[dict]:
        """The actual match's events, regenerated once from the seeds in meta."""
        entry = self._matches[match_id]
        if "events" not in entry:
            meta = entry["meta"]
            events, _ = generate(meta["home_id"], meta["away_id"], seed=meta["seed"], league_seed=meta["league_seed"])
            entry["events"] = events
        return entry["events"]


def _side_summary(events: list[dict], meta: dict) -> dict:
    """Observable outcome of one timeline (actual or branch)."""
    home, away = meta["home_id"], meta["away_id"]
    teams = {t: {"xg": 0.0, "shots": 0, "injury_concerns": 0} for t in (home, away)}
    score = {home: 0, away: 0}
    goals = []
    for e in events:
        if e["type"] == "shot":
            teams[e["team_id"]]["xg"] += e["xg"]
            teams[e["team_id"]]["shots"] += 1
        elif e["type"] == "goal":
            score = dict(e["score"])
            goals.append({"clock": e["clock"], "period": e["period"], "minute": e["minute"],
                          "team_id": e["team_id"], "player_name": e["player_name"]})
        elif e["type"] == "injury_concern":
            t = e.get("team_id_affected")
            if t in teams:
                teams[t]["injury_concerns"] += 1
    for t in teams.values():
        t["xg"] = round(t["xg"], 2)
    return {
        "score": score,
        "xg": {t: teams[t]["xg"] for t in teams},
        "shots": {t: teams[t]["shots"] for t in teams},
        "injury_concerns": {t: teams[t]["injury_concerns"] for t in teams},
        "injury_concerns_total": sum(t["injury_concerns"] for t in teams.values()),
        "goals": goals,
    }


def _player_after(events: list[dict], player_id: str, minute: int) -> dict:
    after = [e for e in events if e.get("player_id") == player_id and (e["period"], e["minute"]) >= (2 if minute >= 45 else 1, minute)]
    samples = [e for e in events if e["type"] == "physical_sample" and e["player_id"] == player_id]
    return {
        "concerns_after": sum(1 for e in after if e["type"] == "injury_concern"),
        "minutes_played": samples[-1]["minutes_played"] if samples else 0,
        "distance_m": samples[-1]["distance_m"] if samples else 0.0,
    }


class MatchTools:
    def __init__(self, registry: LiveStateRegistry):
        self._registry = registry

    # ------------------------------------------------------------ helpers

    def _entry(self, match_id: str) -> dict:
        entry = self._registry.get(match_id)
        if entry is None:
            raise KeyError(f"unknown match {match_id!r}; known: {self._registry.ids()}")
        return entry

    @staticmethod
    def _team_name(meta: dict, team_id: str) -> str:
        return meta["teams"].get(team_id, {}).get("name", team_id)

    # ------------------------------------------------------------ tools

    def list_matches(self) -> list[dict]:
        """List the matches currently known, with live score and clock."""
        rows = []
        for mid in self._registry.ids():
            e = self._registry.get(mid)
            meta, snap = e["meta"], e["snapshot"]
            rows.append({
                "match_id": mid,
                "home": self._team_name(meta, snap["home_id"]),
                "away": self._team_name(meta, snap["away_id"]),
                "score": snap["score"],
                "clock": snap["clock"],
                "period": snap["period"],
            })
        return rows

    def get_match_state(self, match_id: str) -> dict:
        """Current score, clock, team statistics (passes, xG, shots, pressing) and momentum of a match."""
        e = self._entry(match_id)
        meta, snap = e["meta"], e["snapshot"]
        teams = {}
        for tid, stats in snap["teams"].items():
            teams[tid] = {"name": self._team_name(meta, tid), **stats}
        return {
            "match_id": match_id,
            "clock": snap["clock"],
            "period": snap["period"],
            "score": snap["score"],
            "home_id": snap["home_id"],
            "away_id": snap["away_id"],
            "momentum": snap["momentum"],
            "momentum_note": "+1 = home side dominant, -1 = away side dominant",
            "teams": teams,
            "risk_alert_count": len(snap.get("risk_alerts", [])),
        }

    def get_player_workload(self, match_id: str, player_id: str) -> dict:
        """Live workload of one player: minutes, distance, sprints, top speed, ACWR (acute:chronic workload ratio), risk band and last 7 days of training load."""
        e = self._entry(match_id)
        meta, snap = e["meta"], e["snapshot"]
        p = snap["players"].get(player_id)
        if p is None:
            raise KeyError(f"unknown player {player_id!r} in match {match_id!r}")
        history = []
        for team in meta["teams"].values():
            for mp in team["players"]:
                if mp["player_id"] == player_id:
                    history = mp.get("load_history", [])
        return {
            "player_id": player_id,
            "name": p["name"],
            "team": self._team_name(meta, p["team_id"]),
            "position": p["position"],
            "on_pitch": p.get("on_pitch", False),
            "minutes_played": p["minutes_played"],
            "distance_m": p["distance_m"],
            "sprints": p["sprints"],
            "sprints_per_min": p.get("sprints_per_min", 0.0),
            "top_speed_kmh": p["top_speed_kmh"],
            "acwr_pre_match": p["acwr_pre_match"],
            "acwr_live": p["acwr_live"],
            "risk_band": p["risk_band"],
            "injury_concerns": p["injury_concerns"],
            "load_history_last_7_days": history[-7:],
            "note": "ACWR bands: <0.8 undertrained, 0.8-1.3 optimal, 1.3-1.5 elevated, >1.5 high. Decision support, not medical advice.",
        }

    def get_risk_alerts(self, match_id: str, limit: int = 5) -> list[dict]:
        """Players on the pitch whose live ACWR is in the elevated or high band, highest first."""
        e = self._entry(match_id)
        return e["snapshot"].get("risk_alerts", [])[: max(0, int(limit))]

    def get_xg_race(self, match_id: str) -> list[dict]:
        """Cumulative expected goals per team at every shot so far (minute, clock, per-team xG)."""
        e = self._entry(match_id)
        return e["snapshot"].get("xg_race", [])

    def get_risk_windows(self, match_id: str) -> dict:
        """Live injury-risk windows from the Load & Risk Monitor (players predicted at risk in the next 15 minutes), the latest hazard per player and the running scorecard of the monitor against ground truth."""
        e = self._entry(match_id)
        risk = e.get("risk")
        if risk is None:
            return {"match_id": match_id, "minute": e["snapshot"]["minute"], "active_windows": [], "hazards": {},
                    "scorecard": None, "note": "no live risk monitor for this match yet"}
        return {"match_id": match_id, **risk}

    def get_team_shape(self, match_id: str) -> dict:
        """Team shape from the positional model (synthetic positions driven by the ball and the formation, not measured tracking): block height, width, compactness and line heights in metres per team, the phase (attacking/defending), the block height over the last 10 minutes against the match mean, and each team's press index (mean opponents within 8 m of the ball carrier while defending)."""
        e = self._entry(match_id)
        snap = e["snapshot"]
        if not snap.get("shape"):
            return {"match_id": match_id, "shape": None, "note": "no positional frames applied for this match yet"}
        meta = e["meta"]
        return {
            "match_id": match_id, "minute": snap["minute"], "clock": snap["clock"],
            "shape": {tid: {"team": self._team_name(meta, tid), **(sh or {})} for tid, sh in snap["shape"].items()},
            "last_10_minutes": snap.get("shape_last_10"),
            "press_index": snap.get("press_index"),
            "pressure_now": snap.get("pressure"),
            "note": "Positions come from a positional model built on the event stream; shape follows the model, not a tracking feed.",
        }

    def get_player_heatmap(self, match_id: str, player_id: str) -> dict:
        """Where a player has spent the match: a 12x8 occupancy grid in team frame (columns run from own goal to the opponent's, rows from the left touchline to the right), plus the share of time in each third and a one-line reading. Positions come from the positional model, not measured tracking."""
        e = self._entry(match_id)
        snap, meta = e["snapshot"], e["meta"]
        p = snap["players"].get(player_id)
        if p is None:
            raise KeyError(f"unknown player {player_id!r} in {match_id}")
        grid = p.get("heat")
        if not grid or not sum(grid):
            return {"match_id": match_id, "player_id": player_id, "name": p["name"], "grid": None, "note": "no positional frames for this player yet"}
        cols, rows = 12, 8
        total = sum(grid)
        thirds = [sum(grid[r * cols + c] for r in range(rows) for c in range(lo, hi)) / total for lo, hi in ((0, 4), (4, 8), (8, 12))]
        lanes = [sum(grid[r * cols + c] for r in range(lo, hi) for c in range(cols)) / total for lo, hi in ((0, 3), (3, 5), (5, 8))]
        third = ("own third", "middle third", "final third")[max(range(3), key=lambda k: thirds[k])]
        lane = ("left", "central", "right")[max(range(3), key=lambda k: lanes[k])]
        return {
            "match_id": match_id, "player_id": player_id, "name": p["name"], "team": self._team_name(meta, p["team_id"]),
            "position": p["position"], "frames": total, "grid_cols": cols, "grid_rows": rows, "grid": grid,
            "time_by_third": {"own": round(thirds[0], 2), "middle": round(thirds[1], 2), "final": round(thirds[2], 2)},
            "time_by_lane": {"left": round(lanes[0], 2), "central": round(lanes[1], 2), "right": round(lanes[2], 2)},
            "reading": f"{p['name']} spent most of the match in the {lane} channel of the {third}.",
            "note": "Positional model, not measured tracking.",
        }

    def get_analyst_credibility(self, match_id: str) -> dict:
        """How the Analyst agent's 10-minute forecasts have scored so far in this match (dominance, goal odds, watched player), next to a naive baseline graded on the same windows, plus the latest verdict."""
        e = self._entry(match_id)
        cred = e.get("credibility")
        if cred is None:
            return {"match_id": match_id, "judged": 0, "pending": 0, "analyst": None, "naive": None, "latest": None,
                    "note": "no graded forecasts for this match yet"}
        return {"match_id": match_id, **cred}

    def simulate_intervention(
        self,
        match_id: str,
        minute: int,
        action: str,
        team_id: str,
        player_off_id: str | None = None,
        player_on_id: str | None = None,
        press_intensity: float | None = None,
        style: str | None = None,
    ) -> dict:
        """Re-simulate the match from `minute` with one coach intervention and compare it with what actually happened.

        action="substitution" needs player_off_id (player_on_id optional: same-position bench player by default);
        action="tactic" needs press_intensity (0-1) and/or style (possession|balanced|direct).
        The branch is deterministic: identical to the real match until `minute`, then it diverges.
        Returns score / xG / shots / injury concerns for both timelines, the diff, and a branch_id
        whose full event stream is available at GET /matches/{match_id}/branches/{branch_id}.
        """
        e = self._entry(match_id)
        meta = e["meta"]
        if action not in INTERVENTION_ACTIONS:
            raise ValueError(f"unknown intervention action {action!r}; expected one of {INTERVENTION_ACTIONS}")
        if team_id not in meta["teams"]:
            raise ValueError(f"unknown team {team_id!r}; expected one of {list(meta['teams'])}")
        iv: dict = {"minute": int(minute), "type": action, "team_id": team_id, "reason": "coach"}
        if action == "substitution":
            if not player_off_id:
                raise ValueError("substitution needs player_off_id")
            iv["player_off_id"] = player_off_id
            if player_on_id:
                iv["player_on_id"] = player_on_id
        else:
            if press_intensity is None and not style:
                raise ValueError("tactic needs press_intensity and/or style")
            if press_intensity is not None:
                iv["press_intensity"] = float(press_intensity)
            if style:
                iv["style"] = style

        branch_id = f"{match_id}~{hashlib.sha1(json.dumps(iv, sort_keys=True).encode()).hexdigest()[:8]}"
        cached = self._registry.branch(match_id, branch_id)
        if cached is not None:
            return cached["summary"]

        base_events = self._registry.base_events(match_id)
        br_events, br_meta = generate(meta["home_id"], meta["away_id"], seed=meta["seed"],
                                      league_seed=meta["league_seed"], interventions=[iv], match_id=branch_id)
        applied = br_meta["interventions"][0]
        actual, branch = _side_summary(base_events, meta), _side_summary(br_events, meta)
        home, away = meta["home_id"], meta["away_id"]
        summary = {
            "branch_id": branch_id,
            "match_id": match_id,
            "status": applied["status"],
            "intervention": {k: v for k, v in applied.items() if k != "status"},
            "divergence_minute": int(minute),
            "actual": actual,
            "branch": branch,
            "diff": {
                "goals_home": branch["score"][home] - actual["score"][home],
                "goals_away": branch["score"][away] - actual["score"][away],
                "xg_home": round(branch["xg"][home] - actual["xg"][home], 2),
                "xg_away": round(branch["xg"][away] - actual["xg"][away], 2),
                "injury_concerns": branch["injury_concerns_total"] - actual["injury_concerns_total"],
            },
            "branch_event_count": len(br_events),
        }
        if action == "substitution":
            name = next((p["name"] for t in meta["teams"].values() for p in t["players"] if p["player_id"] == player_off_id), player_off_id)
            a, b = _player_after(base_events, player_off_id, int(minute)), _player_after(br_events, player_off_id, int(minute))
            summary["player_off"] = {
                "player_id": player_off_id, "name": name,
                "concerns_after_actual": a["concerns_after"], "concerns_after_branch": b["concerns_after"],
                "minutes_actual": a["minutes_played"], "minutes_branch": b["minutes_played"],
            }
        self._registry.store_branch(match_id, branch_id, {"meta": br_meta, "events": br_events, "summary": summary})
        return summary

    def as_functions(self) -> list:
        """The tool callables, for Agent Framework function calling."""
        return [self.list_matches, self.get_match_state, self.get_player_workload, self.get_risk_alerts,
                self.get_xg_race, self.get_risk_windows, self.get_analyst_credibility, self.get_team_shape,
                self.get_player_heatmap, self.simulate_intervention]
