"""Key-moment detection (deterministic) and the compact context for LLM agents.

The Interpreter sees every event; the LLM agents only wake up for moments
worth explaining. Keeping this gate in plain Python keeps cost and latency
predictable and makes the trigger policy testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BIG_CHANCE_XG = 0.30
CHANCE_XG = 0.15
TEAM_STAT_KEYS = (
    "passes", "pass_accuracy", "possession_pct", "shots", "shots_on_target", "xg", "goals",
    "pressures", "tackles", "interceptions", "fouls", "yellow_cards", "red_cards",
)
PLAYER_KEYS = (
    "player_id", "name", "team_id", "position", "minutes_played", "distance_m", "sprints",
    "top_speed_kmh", "acwr_live", "risk_band", "injury_concerns",
)
EVENT_KEYS = (
    "type", "clock", "team_id", "player_id", "player_name", "assist_player_id", "assist_player_name",
    "outcome", "xg", "distance_m", "shot_speed_kmh", "detail", "card", "player_off_id", "player_off_name",
    "player_on_id", "player_on_name", "won_by",
)


@dataclass(frozen=True)
class KeyMoment:
    kind: str
    importance: int  # 1 (ticker) .. 5 (interrupt the broadcast)
    summary: str  # deterministic one-liner, English
    event_id: int
    event: dict = field(default_factory=dict, compare=False, repr=False)  # trimmed source event

    def to_dict(self) -> dict:
        return {"kind": self.kind, "importance": self.importance, "summary": self.summary, "event_id": self.event_id}


def _trim(event: dict) -> dict:
    return {k: event[k] for k in ("event_id", *EVENT_KEYS) if k in event}


def _moment(kind: str, importance: int, summary: str, event: dict) -> KeyMoment:
    return KeyMoment(kind, importance, summary, event["event_id"], _trim(event))


def _score_line(snapshot: dict) -> str:
    h, a = snapshot["home_id"], snapshot["away_id"]
    return f"{h} {snapshot['score'][h]}-{snapshot['score'][a]} {a}"


def detect_key_moment(event: dict, snapshot: dict) -> KeyMoment | None:
    """Return a KeyMoment if this event deserves the agents' attention, else None."""
    t = event["type"]
    clock = event.get("clock", "")
    who = event.get("player_name", "")
    team = event.get("team_id", "")

    if t == "goal":
        assist = f" (assist {event['assist_player_name']})" if event.get("assist_player_name") else ""
        return _moment("goal", 5, f"{clock} GOAL {team} - {who}{assist}. {_score_line(snapshot)}", event)

    if t == "shot":
        xg = float(event.get("xg", 0.0))
        outcome = event.get("outcome", "")
        if outcome == "goal":
            return None  # the following goal event carries the moment
        if xg >= BIG_CHANCE_XG or (outcome == "saved" and xg >= 0.2):
            importance = 4 if xg >= BIG_CHANCE_XG else 3
            return _moment("big_chance", importance, f"{clock} Big chance {team} - {who} ({outcome}, xG {xg:.2f}). {_score_line(snapshot)}", event)
        if xg >= CHANCE_XG:
            return _moment("chance", 2, f"{clock} Chance {team} - {who} ({outcome}, xG {xg:.2f})", event)
        return None

    if t == "card":
        colour = event.get("card", "yellow")
        return _moment("card", 4 if colour == "red" else 2, f"{clock} {colour.capitalize()} card {team} - {who}", event)

    if t == "injury_concern":
        return _moment("injury_concern", 3, f"{clock} Injury concern - {who} {event.get('detail', '')}".strip(), event)

    if t == "substitution":
        return _moment("substitution", 2, f"{clock} Substitution {team}: {event.get('player_on_name')} on for {event.get('player_off_name')}", event)

    if t == "half_time":
        return _moment("half_time", 3, f"{clock} Half-time. {_score_line(snapshot)}", event)

    if t == "full_time":
        return _moment("full_time", 5, f"{clock} Full-time. {_score_line(snapshot)}", event)

    return None


def _player_view(players: dict, pid: str | None) -> dict | None:
    if pid and pid in players:
        return {k: players[pid][k] for k in PLAYER_KEYS if k in players[pid]}
    return None


def build_moment_context(
    moment: KeyMoment, snapshot: dict, meta: dict, watched_players: list[str] | None = None
) -> dict:
    """Compact, JSON-safe view of the match at this moment for the LLM agents.

    `watched_players` are the viewers' favourite players: their workload view is
    attached so player-focus narration can talk about them by name even when
    they were not involved in the moment.
    """
    event = moment.event or {"event_id": moment.event_id}
    teams = {}
    for tid, stats in snapshot["teams"].items():
        info = meta["teams"].get(tid, {})
        teams[tid] = {"name": info.get("name", tid), "short_name": info.get("short_name", tid)}
        teams[tid].update({k: stats[k] for k in TEAM_STAT_KEYS if k in stats})

    involved_ids = [event.get(k) for k in ("player_id", "assist_player_id", "receiver_id", "player_off_id", "player_on_id")]
    players = snapshot.get("players", {})
    involved = []
    for pid in involved_ids:
        view = _player_view(players, pid)
        if view and all(p["player_id"] != pid for p in involved):
            involved.append(view)
    watched = [v for v in (_player_view(players, pid) for pid in (watched_players or [])) if v]

    return {
        "match_id": snapshot["match_id"],
        "competition": meta.get("competition", "MatchMind Synthetic League"),
        "home_id": snapshot["home_id"],
        "away_id": snapshot["away_id"],
        "period": snapshot["period"],
        "minute": snapshot["minute"],
        "clock": event.get("clock", snapshot["clock"]),
        "score": dict(snapshot["score"]),
        "moment": moment.to_dict(),
        "event": {k: event[k] for k in EVENT_KEYS if k in event},
        "teams": teams,
        "momentum": snapshot["momentum"],
        "momentum_trend": [p["value"] for p in snapshot.get("momentum_series", [])[-5:]],
        "xg_race_tail": snapshot.get("xg_race", [])[-6:],
        "players_involved": involved,
        "watched_players": watched,
        "risk_alerts": snapshot.get("risk_alerts", [])[:3],
    }
