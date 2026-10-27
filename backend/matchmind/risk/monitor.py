"""Load & Risk Monitor: injury-risk windows from observables, scored against ground truth.

The simulator's latent fatigue x susceptibility produces `injury_concern`
events. This monitor never sees the latent state; it only reads what a real
performance analyst could read (minutes, live ACWR, sprint density, previous
knocks, and the drop in metres-per-minute against the position norm) and
predicts "this player is at risk in the next N minutes".

Because the concerns are observable events, every prediction can be scored:
- an **alert** (window opening) is *true* if a concern for that player happens
  while the window is active; a **concern** is *covered* if a window was active
  when it happened; **lead time** = minutes from window opening to concern;
- **ranking**: when a concern happens, where did the model rank that player
  among everybody recently observed on the pitch? Top-3 hit rate vs the random
  reference (3 / players ranked) is the honest metric for a rare event.

A naive baseline (risk = minutes played) runs alongside with the same
machinery, so the scorecard shows whether the model adds anything.
Decision support, not medical advice.
"""

from __future__ import annotations

import math

HORIZON_MINUTES = 15
THRESHOLD = 0.5
HIGH_THRESHOLD = 0.7
RANKING_WINDOW_MINUTES = 6  # observations older than this are not "on the pitch" for ranking
TOP_K = 3
TOP_N_WINDOWS = 5  # a window only opens for a player ranked within the top N hazards on the pitch


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class RiskModel:
    """Logistic hazard over observable workload features (weights tuned offline, see evaluate.py)."""

    def __init__(self, bias=-2.6, acwr=2.5, minutes=2.4, sprint_density=1.5, concerns=1.2, effort=6.0):
        self.w = {"bias": bias, "acwr": acwr, "minutes": minutes, "sprint_density": sprint_density,
                  "concerns": concerns, "effort": effort}

    def hazard(self, p: dict) -> float:
        w = self.w
        effort_drop = max(0.0, 1.0 - float(p.get("effort_ratio_recent", 1.0)))  # 0 = on the norm
        x = (
            w["bias"]
            + w["acwr"] * (float(p.get("acwr_live", 1.0)) - 1.0)
            + w["minutes"] * (float(p.get("minutes_played", 0)) / 90.0)
            + w["sprint_density"] * float(p.get("sprints_per_min", 0.0))
            + w["concerns"] * float(p.get("injury_concerns", 0))
            + w["effort"] * effort_drop
        )
        return round(_sigmoid(x), 4)


class NaiveMinutesBaseline:
    """What a tired-eyes heuristic would do: risk grows with minutes, flag everyone after N."""

    def __init__(self, after_minute: int = 60):
        self.after_minute = after_minute
        self.threshold = after_minute / 90.0

    def hazard(self, p: dict) -> float:
        return round(min(1.0, float(p.get("minutes_played", 0)) / 90.0), 4)


class Track:
    """Risk windows + scoring for one predictor."""

    def __init__(self, model, horizon_min: int = HORIZON_MINUTES, threshold: float = THRESHOLD,
                 ranking_window_min: int = RANKING_WINDOW_MINUTES, top_n: int | None = None):
        self.model, self.horizon, self.threshold = model, horizon_min, threshold
        self.ranking_window = ranking_window_min
        self.top_n = top_n  # None = any player above the threshold
        self._windows: dict[str, dict] = {}  # player_id -> active window
        self._last: dict[str, tuple[int, float]] = {}  # player_id -> (minute, hazard) of the latest observation
        self._alerts: list[dict] = []
        self._concerns: list[dict] = []

    def _expire(self, minute: int) -> None:
        for pid in [pid for pid, w in self._windows.items() if minute > w["expires_minute"]]:
            del self._windows[pid]

    def update(self, player_id: str, minute: int, player: dict, **extra) -> dict | None:
        """Feed a fresh observation. Returns a new alert when a window opens, else None."""
        self._expire(minute)
        h = self.model.hazard(player)
        self._last[player_id] = (minute, h)
        if h < self.threshold:
            return None
        if player_id in self._windows:
            self._windows[player_id]["expires_minute"] = minute + self.horizon
            self._windows[player_id]["hazard"] = h
            return None
        if self.top_n is not None:
            rank, _ = self._rank(player_id, minute)
            if rank is None or rank > self.top_n:
                return None
        window = {
            "player_id": player_id, "open_minute": minute, "expires_minute": minute + self.horizon,
            "hazard": h, "level": "high" if h >= HIGH_THRESHOLD else "elevated", "hit": False, **extra,
        }
        self._windows[player_id] = window
        self._alerts.append(window)
        return {k: v for k, v in window.items() if k != "hit"}

    def last_hazard(self, player_id: str) -> float | None:
        last = self._last.get(player_id)
        return last[1] if last else None

    def _rank(self, player_id: str, minute: int) -> tuple[int | None, int]:
        recent = {pid: h for pid, (m, h) in self._last.items() if minute - m <= self.ranking_window}
        if player_id not in recent:
            return None, len(recent)
        ordered = sorted(recent.items(), key=lambda kv: (-kv[1], kv[0]))
        return [pid for pid, _ in ordered].index(player_id) + 1, len(recent)

    def concern(self, player_id: str, minute: int) -> dict:
        self._expire(minute)
        w = self._windows.get(player_id)
        covered = w is not None
        if covered:
            w["hit"] = True
        rank, n = self._rank(player_id, minute)
        rec = {"player_id": player_id, "minute": minute, "covered": covered,
               "lead_minutes": (minute - w["open_minute"]) if covered else None,
               "rank": rank, "ranked_players": n}
        self._concerns.append(rec)
        return rec

    def active(self, minute: int) -> list[dict]:
        self._expire(minute)
        return [{k: v for k, v in w.items() if k != "hit"} for w in self._windows.values()]

    def windows(self) -> list[dict]:
        """Every window opened so far, with its hazard at opening and whether a knock followed (calibration data)."""
        return [{"player_id": w["player_id"], "open_minute": w["open_minute"], "hazard": w["hazard"], "level": w["level"], "hit": w["hit"]}
                for w in self._alerts]

    def hazards(self, minute: int) -> dict[str, float]:
        return {pid: h for pid, (m, h) in self._last.items() if minute - m <= self.ranking_window}

    def scorecard(self) -> dict:
        alerts, true_alerts = len(self._alerts), sum(1 for w in self._alerts if w["hit"])
        concerns, covered = len(self._concerns), sum(1 for c in self._concerns if c["covered"])
        leads = [c["lead_minutes"] for c in self._concerns if c["covered"]]
        ranked = [c for c in self._concerns if c["rank"] is not None and c["ranked_players"] > 1]
        top3 = sum(1 for c in ranked if c["rank"] <= TOP_K)
        rank_pcts = [100.0 * (c["rank"] - 1) / (c["ranked_players"] - 1) for c in ranked]
        random_rates = [min(1.0, TOP_K / c["ranked_players"]) for c in ranked]
        return {
            "alerts": alerts,
            "true_alerts": true_alerts,
            "precision": round(true_alerts / alerts, 3) if alerts else 0.0,
            "concerns": concerns,
            "covered": covered,
            "recall": round(covered / concerns, 3) if concerns else 0.0,
            "mean_lead_minutes": round(sum(leads) / len(leads), 1) if leads else None,
            "ranked_concerns": len(ranked),
            "top3_hits": top3,
            "top3_rate": round(top3 / len(ranked), 3) if ranked else 0.0,
            "top3_random_rate": round(sum(random_rates) / len(random_rates), 3) if ranked else 0.0,
            "mean_rank_pct": round(sum(rank_pcts) / len(rank_pcts), 1) if ranked else 0.0,
        }


class RiskMonitor:
    """Consumes the event stream + Interpreter snapshots; keeps model and baseline tracks."""

    def __init__(self, meta: dict, model=None, baseline=None, horizon_min: int = HORIZON_MINUTES,
                 threshold: float = THRESHOLD, top_n: int | None = TOP_N_WINDOWS):
        self.meta = meta
        self.horizon = horizon_min
        baseline = baseline or NaiveMinutesBaseline()
        # Same top-N policy for both tracks, so the comparison stays fair.
        self.model_track = Track(model or RiskModel(), horizon_min, threshold, top_n=top_n)
        self.baseline_track = Track(baseline, horizon_min, getattr(baseline, "threshold", 0.5), top_n=top_n)
        self.recent_alerts: list[dict] = []
        self.concerns: list[dict] = []
        self.minute = 0
        # hazard per player over the match, one point per workload sample: what the bench draws as a curve
        self.series: dict[str, list[list[float]]] = {}

    @staticmethod
    def _minute(event: dict) -> int:
        # first-half stoppage runs 45-47 and the second half restarts at 45: clamp so time never runs backwards
        m = int(event["minute"])
        return m if event.get("period", 1) == 1 else max(m, 45)

    def observe(self, event: dict, snapshot: dict) -> list[dict]:
        """Returns the alerts (newly opened model windows) this event produced."""
        t = self._minute(event)
        self.minute = max(self.minute, t)
        pid = event.get("player_id")
        if event["type"] == "physical_sample" and isinstance(pid, str) and pid in snapshot.get("players", {}):
            p = snapshot["players"][pid]
            self.baseline_track.update(pid, t, p)
            alert = self.model_track.update(pid, t, p, name=p["name"], team_id=p["team_id"],
                                            position=p["position"], clock=event.get("clock"),
                                            minutes_played=p["minutes_played"], acwr_live=p["acwr_live"],
                                            effort_ratio_recent=p.get("effort_ratio_recent"))
            pts = self.series.setdefault(pid, [])
            point = [t, self.model_track.last_hazard(pid)]
            if pts and pts[-1][0] == t:
                pts[-1] = point  # the batch after full time can land on the same minute as the last regular one
            else:
                pts.append(point)
            if alert:
                self.recent_alerts.append(alert)
                return [alert]
        elif event["type"] == "injury_concern" and pid:
            rec = self.model_track.concern(pid, t)
            base = self.baseline_track.concern(pid, t)
            rec = {**rec, "name": event.get("player_name"), "clock": event.get("clock"),
                   "detail": event.get("detail"), "baseline_covered": base["covered"], "baseline_rank": base["rank"]}
            self.concerns.append(rec)
        return []

    def active_windows(self) -> list[dict]:
        return self.model_track.active(self.minute)

    def hazard_series(self) -> dict[str, list[list[float]]]:
        """[minute, hazard] pairs per player in sample order. Not part of summary(): the agents' tool output stays small."""
        return {pid: [list(pt) for pt in pts] for pid, pts in self.series.items()}

    def hazards(self) -> dict[str, float]:
        """Latest model hazard per player recently observed on the pitch."""
        return self.model_track.hazards(self.minute)

    def scorecard(self) -> dict:
        base = self.baseline_track.model
        return {
            "model": self.model_track.scorecard(),
            "baseline": self.baseline_track.scorecard(),
            "horizon_minutes": self.horizon,
            "baseline_rule": f"risk = minutes played; flag everyone after {base.after_minute} minutes"
            if isinstance(base, NaiveMinutesBaseline) else "custom",
        }

    def summary(self) -> dict:
        return {
            "minute": self.minute,
            "active_windows": self.active_windows(),
            "recent_alerts": self.recent_alerts[-5:],
            "concerns": self.concerns,
            "hazards": self.hazards(),
            "scorecard": self.scorecard(),
            "note": "Risk windows are inferred from observable workload only (ACWR, minutes, sprint density, "
                    "metres-per-minute drop, previous knocks). Decision support, not medical advice.",
        }
