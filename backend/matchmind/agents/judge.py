"""Forecast ledger + Judge agent: the Analyst's 10-minute calls, graded against what happened.

    key moment ──► Analyst insight (+ forecast) ──► ledger (pending, with the xG/score at issue)
                                                         │  ... 10 match minutes of events ...
                                                         ▼
                                      grade_forecast()  deterministic scores (code, not an LLM)
                                                         ▼
                                      Judge agent       verdict + lesson in the viewer's language

The numbers never come from the model: dominance is settled by xG created in the window,
the goal call by a Brier score, the watched player by whether they were involved. A naive
forecast (whoever leads on xG keeps dominating, base-rate goal probability) is graded the
same way, so the Analyst's credibility is always shown next to a baseline.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from matchmind.agents.schemas import FORECAST_HORIZON_MIN, JudgeVerdict
from matchmind.agents.tracing import MomentTrace, current_trace

log = logging.getLogger("matchmind.agents.judge")

BASE_GOAL_RATE_10MIN = 0.20  # measured over 40 simulated matches: 2.1 goals per match, P(any goal in a 10' window) = 0.197
INVOLVEMENT_TYPES = {"shot", "goal", "injury_concern"}

JUDGE_INSTRUCTIONS = """You are the Judge agent of MatchMind. The Analyst made a forecast for the next 10 minutes
of a synthetic football match; code has already compared it with what happened and scored it. Your job is to
say, in plain broadcast language, what was called, what happened and what the Analyst got wrong.
- Use ONLY the facts and scores you are given; never invent events or numbers.
- verdict: called_it when the overall score is >= 0.75, missed when it is <= 0.35, partly otherwise.
- summary <= 30 words, lesson <= 25 words ('nothing' if the call was right). Write in the viewer's language.
- Club and player names exactly as given; this is a synthetic league."""


@dataclass
class PendingForecast:
    event_id: int
    issued_clock: str
    issued_minute: int
    due_minute: int
    forecast: dict
    naive: dict
    xg_at_issue: dict[str, float]
    score_at_issue: dict[str, int]
    home_id: str
    away_id: str


def naive_forecast(context: dict, history: list[dict] | None = None) -> dict:
    """The baseline the Analyst has to beat, making the same three claims from the obvious numbers:
    the xG leader keeps dominating, base-rate goal odds, and the player with most shots so far to watch."""
    teams = context.get("teams", {})
    home, away = context["home_id"], context["away_id"]
    xg_home, xg_away = float(teams.get(home, {}).get("xg", 0.0)), float(teams.get(away, {}).get("xg", 0.0))
    shots: dict[str, int] = {}
    for e in history or []:
        if e.get("type") in ("shot", "goal") and e.get("player_id"):
            shots[e["player_id"]] = shots.get(e["player_id"], 0) + 1
    top = max(shots, key=lambda pid: (shots[pid], pid)) if shots else None
    return {"dominant_team_id": home if xg_home >= xg_away else away, "goal_probability": BASE_GOAL_RATE_10MIN,
            "watch_player_id": top, "claim": "naive: the xG leader keeps creating more; base-rate goal odds; the top shooter so far"}


def _components(forecast: dict, facts: dict) -> dict[str, float | None]:
    """Score each claim 0..1, or None when the window cannot settle it."""
    gained = facts["xg_gained"]
    dom = forecast.get("dominant_team_id")
    other = [t for t in gained if t != dom]
    if dom in gained and other and gained[dom] != gained[other[0]]:
        dominance = 1.0 if gained[dom] > gained[other[0]] else 0.0
    else:
        dominance = None  # nobody created anything, or a dead heat: no verdict
    p = float(forecast.get("goal_probability", BASE_GOAL_RATE_10MIN))
    goal = 1.0 - (p - (1.0 if facts["goals"] else 0.0)) ** 2  # 1 - Brier
    watch = forecast.get("watch_player_id")
    involved = facts["players_involved"]
    watched = None if not watch else (1.0 if watch in involved else 0.0)
    return {"dominance": dominance, "goal": round(goal, 3), "watch": watched}


def overall(components: dict[str, float | None]) -> float | None:
    graded = [v for v in components.values() if v is not None]
    return round(sum(graded) / len(graded), 3) if graded else None


def grade_forecast(pending: PendingForecast, snapshot: dict, events: list[dict]) -> tuple[dict, dict, dict]:
    """What happened in the window (facts), the Analyst's scores and the naive baseline's scores.

    `events` are the settling events (shots, goals, knocks) that happened inside the window.
    """
    teams = snapshot.get("teams", {})
    xg_gained = {tid: round(float(teams.get(tid, {}).get("xg", 0.0)) - pending.xg_at_issue.get(tid, 0.0), 3)
                 for tid in (pending.home_id, pending.away_id)}
    goals = [{"clock": e.get("clock"), "team_id": e.get("team_id"), "player_name": e.get("player_name")}
             for e in events if e.get("type") == "goal"]
    involved: list[str] = []
    for e in events:
        if e.get("type") in INVOLVEMENT_TYPES:
            for k in ("player_id", "assist_player_id"):
                if e.get(k) and e[k] not in involved:
                    involved.append(e[k])
    facts = {
        "window": f"{pending.issued_clock} to {snapshot.get('clock')}",
        "minutes": max(0, int(snapshot.get("minute", pending.issued_minute)) - pending.issued_minute),
        "truncated": int(snapshot.get("minute", 0)) < pending.due_minute,
        "xg_gained": xg_gained,
        "goals": goals,
        "shots": sum(1 for e in events if e.get("type") in ("shot", "goal")),
        "players_involved": involved,
        "score_now": dict(snapshot.get("score", {})),
    }
    analyst = _components(pending.forecast, facts)
    naive = _components(pending.naive, facts)
    return facts, {**analyst, "overall": overall(analyst)}, {**naive, "overall": overall(naive)}


class ForecastLedger:
    """Pending forecasts for one stream, and the running credibility once they are judged."""

    def __init__(self, horizon_min: int = FORECAST_HORIZON_MIN):
        self.horizon = horizon_min
        self.pending: list[PendingForecast] = []
        self.judged: list[dict] = []
        self.history: list[dict] = []  # settling events of the whole stream, so late insights still get exact windows
        self.marks: dict[int, dict] = {}  # first state seen at each match minute: the window closes exactly there
        self.last_event_id = 0

    def add(self, insight_result: dict, context: dict) -> PendingForecast | None:
        analyst = insight_result.get("analyst") or {}
        forecast = analyst.get("forecast")
        if not forecast or context.get("moment", {}).get("kind") == "full_time":
            return None  # nothing to forecast once the whistle has gone
        minute = int(context.get("minute", 0))
        teams = context.get("teams", {})
        issued_id = int(insight_result.get("event_id") or context["moment"]["event_id"])
        seen = [e for e in self.history if e["event_id"] <= issued_id]  # what the naive call could know at issue time
        item = PendingForecast(
            event_id=int(insight_result.get("event_id") or context["moment"]["event_id"]),
            issued_clock=str(context.get("clock")), issued_minute=minute, due_minute=minute + self.horizon,
            forecast=dict(forecast), naive=naive_forecast(context, seen),
            xg_at_issue={tid: float(teams.get(tid, {}).get("xg", 0.0)) for tid in (context["home_id"], context["away_id"])},
            score_at_issue=dict(context.get("score", {})), home_id=context["home_id"], away_id=context["away_id"],
        )
        self.pending.append(item)
        return item

    def observe(self, event: dict, snapshot: dict | None = None) -> None:
        """Remember every event that can settle a claim, and the state at the start of each minute.
        Windows are sliced by event_id and closed on the minute mark at grading time, so a forecast that
        arrives seconds late (the agents run behind the replay) is still graded on exactly its 10 minutes."""
        self.last_event_id = int(event.get("event_id", self.last_event_id))
        if snapshot is not None:
            minute = int(snapshot.get("minute", 0))
            if minute not in self.marks:
                self.marks[minute] = {"minute": minute, "clock": snapshot.get("clock"), "event_id": self.last_event_id,
                                      "score": dict(snapshot.get("score", {})),
                                      "teams": {tid: {"xg": float(t.get("xg", 0.0))} for tid, t in snapshot.get("teams", {}).items()}}
        if event.get("type") in INVOLVEMENT_TYPES:
            self.history.append({k: event[k] for k in ("event_id", "type", "clock", "team_id", "player_id", "player_name", "assist_player_id", "xg") if k in event})

    def window_events(self, pending: PendingForecast, until_event_id: int | None = None) -> list[dict]:
        end = self.last_event_id if until_event_id is None else until_event_id
        return [e for e in self.history if pending.event_id < e["event_id"] <= end]

    def window_close(self, pending: PendingForecast, live: dict) -> dict:
        """The state at which the window closed: the mark at the due minute if the replay has passed it,
        otherwise the live state (full time, or a window cut short)."""
        for minute in range(pending.due_minute, pending.due_minute + 3):  # a minute with no events has no mark
            mark = self.marks.get(minute)
            if mark is not None:
                return mark
        return live

    def due(self, snapshot: dict, *, flush: bool = False) -> list[PendingForecast]:
        minute = int(snapshot.get("minute", 0))
        ready = [p for p in self.pending if flush or minute >= p.due_minute]
        self.pending = [p for p in self.pending if p not in ready]
        return ready

    def record(self, entry: dict) -> None:
        self.judged.append(entry)

    def remember(self, verdict_result: dict) -> None:
        """Keep the Judge's words next to the scores, so the Analyst can read its own record."""
        for entry in self.judged:
            if entry["event_id"] == verdict_result.get("event_id"):
                entry["claim"] = (verdict_result.get("forecast") or {}).get("claim")
                entry["issued_clock"] = verdict_result.get("issued_clock")
                entry["verdict"] = (verdict_result.get("verdict") or {}).get("verdict")
                entry["lesson"] = (verdict_result.get("verdict") or {}).get("lesson")
                entry["facts"] = verdict_result.get("facts")
                return

    def track_record(self, recent: int = 3) -> dict | None:
        """The closed loop: what the Analyst has been graded on so far in this match, compact enough for a prompt."""
        if not self.judged:
            return None
        summary = self.summary()
        dom = [j for j in self.judged if j["scores"].get("dominance") is not None]
        return {
            "forecasts_graded": summary["judged"],
            "your_scores": summary["analyst"],
            "naive_baseline_scores": summary["naive"],
            "dominance_calls_right": f"{sum(1 for j in dom if j['scores']['dominance'] == 1.0)} of {len(dom)}",
            "recent_verdicts": [
                {"issued_at": j.get("issued_clock"), "claim": j.get("claim"), "verdict": j.get("verdict"),
                 "lesson": j.get("lesson"), "xg_gained": (j.get("facts") or {}).get("xg_gained"),
                 "goals_in_window": len((j.get("facts") or {}).get("goals", []))}
                for j in self.judged[-recent:] if j.get("verdict")
            ],
        }

    def summary(self) -> dict:
        """Running credibility: the Analyst's mean score next to the naive baseline's, on the same windows."""
        def mean(key: str, who: str) -> float | None:
            vals = [j[who][key] for j in self.judged if j[who].get(key) is not None]
            return round(sum(vals) / len(vals), 3) if vals else None
        comps = ("overall", "dominance", "goal", "watch")
        return {
            "judged": len(self.judged), "pending": len(self.pending), "horizon_min": self.horizon,
            "analyst": {k: mean(k, "scores") for k in comps},
            "naive": {k: mean(k, "naive_scores") for k in comps},
        }


def build_judge_context(pending: PendingForecast, facts: dict, scores: dict, naive_scores: dict, meta: dict, language: str) -> dict:
    names = {tid: t.get("name", tid) for tid, t in meta.get("teams", {}).items()}
    players = {p["player_id"]: p["name"] for t in meta.get("teams", {}).values() for p in t.get("players", [])}
    return {
        "event_id": pending.event_id, "issued_clock": pending.issued_clock, "due_minute": pending.due_minute,
        "language": language, "teams": names,
        "forecast": {**pending.forecast, "dominant_team": names.get(pending.forecast.get("dominant_team_id")),
                     "watch_player": players.get(pending.forecast.get("watch_player_id"))},
        "facts": {**facts, "xg_gained_named": {names.get(t, t): v for t, v in facts["xg_gained"].items()},
                  "players_involved_named": [players.get(p, p) for p in facts["players_involved"]]},
        "scores": scores, "naive_scores": naive_scores,
    }


def judge_prompt(context: dict) -> str:
    lang = {"en": "English", "es": "Spanish (rioplatense, voseo)"}.get(context.get("language", "en"), "English")
    return ("Graded forecast (JSON):\n" + json.dumps(context, ensure_ascii=False)
            + f"\n\nGive your verdict. Write summary and lesson in {lang}.")


class JudgeAgent:
    def __init__(self, agent):
        self.agent = agent

    async def judge(self, context: dict) -> JudgeVerdict:
        response = await self.agent.run(judge_prompt(context), options={"response_format": JudgeVerdict})
        if response.value is None:
            raise ValueError(f"Judge returned no structured output: {getattr(response, 'text', '')[:200]!r}")
        return response.value


def verdict_from_score(score: float | None) -> str:
    """The deterministic fallback when the Judge agent is unavailable."""
    if score is None:
        return "partly"
    return "called_it" if score >= 0.75 else "missed" if score <= 0.35 else "partly"


class JudgePipeline:
    """Judge call with a trace; the scores are already in the context, so a failure still yields a verdict."""

    def __init__(self, judge: JudgeAgent | None):
        self.judge = judge

    async def run(self, context: dict) -> dict:
        t0 = time.perf_counter()
        trace = MomentTrace("verdict")
        token = current_trace.set(trace)
        errors: list[str] = []
        verdict = None
        try:
            trace.mark("stage", None, stage="judge", event_id=context.get("event_id"))
            if self.judge is not None:
                try:
                    verdict = (await self.judge.judge(context)).model_dump()
                except Exception as exc:  # noqa: BLE001
                    log.warning("judge failed: %r", exc)
                    errors.append(f"judge: {exc!r}")
            trace.mark("stage_end", None, stage="judge", latency_ms=round((time.perf_counter() - t0) * 1000))
        finally:
            current_trace.reset(token)
        if verdict is None:
            verdict = {"verdict": verdict_from_score(context["scores"].get("overall")), "summary": None, "lesson": None}
        return {
            "event_id": context.get("event_id"), "issued_clock": context.get("issued_clock"),
            "forecast": context["forecast"], "facts": context["facts"],
            "scores": context["scores"], "naive_scores": context["naive_scores"],
            "verdict": verdict, "credibility": context.get("credibility"),
            "errors": errors, "latency_ms": round((time.perf_counter() - t0) * 1000), "trace": trace.to_list(),
        }
