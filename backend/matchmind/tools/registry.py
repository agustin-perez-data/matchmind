"""Match-state tools: one implementation, two surfaces.

`MatchTools` methods are plain, typed, documented Python callables so they can
be handed straight to Agent Framework agents as function tools AND registered
on the MCP server (see mcp_server.py) for external agents such as Copilot.

Everything here is derived from observables only: the simulator's latent
fatigue / susceptibility never reach this layer.
"""

from __future__ import annotations

import time


class LiveStateRegistry:
    """Latest Interpreter snapshot per match, updated by the streamer."""

    def __init__(self):
        self._matches: dict[str, dict] = {}

    def update(self, match_id: str, meta: dict, snapshot: dict) -> None:
        self._matches[match_id] = {"meta": meta, "snapshot": snapshot, "updated_at": time.time()}

    def get(self, match_id: str) -> dict | None:
        return self._matches.get(match_id)

    def ids(self) -> list[str]:
        return sorted(self._matches)


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

    def as_functions(self) -> list:
        """The tool callables, for Agent Framework function calling."""
        return [self.list_matches, self.get_match_state, self.get_player_workload, self.get_risk_alerts, self.get_xg_race]
