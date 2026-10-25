"""Forecast ledger, deterministic grading and the Judge pipeline (no LLM calls)."""

from __future__ import annotations

import asyncio
import json

from matchmind.agents.judge import (
    BASE_GOAL_RATE_10MIN, ForecastLedger, JudgeAgent, JudgePipeline, PendingForecast, build_judge_context, grade_forecast,
    judge_prompt, naive_forecast, verdict_from_score,
)
from matchmind.agents.schemas import JudgeVerdict
from tests.test_agents import CONTEXT, FORECAST, FakeAgent

META = {"match_id": "THU-NBF-42", "teams": {
    "THU": {"name": "Thames United", "players": [{"player_id": "THU-15", "name": "Declan Silveira"}]},
    "NBF": {"name": "Northbridge FC", "players": [{"player_id": "NBF-19", "name": "Kai Okafor"}]},
}}


def _insight(forecast=FORECAST):
    return {"event_id": 120, "analyst": {"headline": "h", "forecast": forecast}}


def _snapshot(minute, xg_thu, xg_nbf, score=(0, 1), clock=None):
    return {"minute": minute, "clock": clock or f"{minute}:00", "score": {"THU": score[0], "NBF": score[1]},
            "teams": {"THU": {"xg": xg_thu}, "NBF": {"xg": xg_nbf}}}


# ---------------------------------------------------------------- ledger

def test_ledger_holds_a_forecast_until_its_window_closes():
    ledger = ForecastLedger()
    item = ledger.add(_insight(), CONTEXT)
    assert item is not None and item.issued_minute == 34 and item.due_minute == 44
    assert item.xg_at_issue == {"THU": 0.46, "NBF": 0.62} and item.naive["dominant_team_id"] == "NBF"
    assert ledger.due(_snapshot(43, 0.5, 0.7)) == [] and ledger.pending == [item]
    assert ledger.due(_snapshot(44, 0.5, 0.7)) == [item] and ledger.pending == []


def test_ledger_ignores_insights_without_a_forecast_and_flushes_at_full_time():
    ledger = ForecastLedger()
    assert ledger.add({"event_id": 1, "analyst": {"headline": "no forecast"}}, CONTEXT) is None
    assert ledger.add({"event_id": 2, "analyst": None}, CONTEXT) is None
    whistle = {**CONTEXT, "moment": {**CONTEXT["moment"], "kind": "full_time"}}
    assert ledger.add(_insight(), whistle) is None  # nothing left to forecast
    ledger.add(_insight(), CONTEXT)
    assert ledger.due(_snapshot(36, 0.5, 0.7), flush=True) and ledger.pending == []


def test_ledger_slices_the_window_by_event_id_so_late_insights_still_get_exact_windows():
    ledger = ForecastLedger()
    ledger.observe({"event_id": 100, "type": "shot", "clock": "30:00", "team_id": "THU", "player_id": "THU-15", "xg": 0.1})
    pending = ledger.add(_insight(), CONTEXT)  # issued at event 120
    ledger.observe({"event_id": 121, "type": "pass", "clock": "35:00", "player_id": "THU-1"})
    ledger.observe({"event_id": 130, "type": "shot", "clock": "36:00", "team_id": "NBF", "player_id": "NBF-19", "xg": 0.2})
    ledger.observe({"event_id": 150, "type": "goal", "clock": "40:00", "team_id": "THU", "player_id": "THU-15", "assist_player_id": "THU-7"})
    ledger.observe({"event_id": 200, "type": "goal", "clock": "60:00", "team_id": "THU", "player_id": "THU-15"})
    assert [e["type"] for e in ledger.window_events(pending, until_event_id=150)] == ["shot", "goal"]
    assert [e["event_id"] for e in ledger.window_events(pending)] == [130, 150, 200]  # up to the last event seen


# ---------------------------------------------------------------- grading

def test_a_late_insight_is_still_graded_on_exactly_its_window():
    """At replay speed the agents answer seconds late; the window must still close on the due minute."""
    ledger = ForecastLedger()
    for minute, xg in [(40, (0.5, 0.7)), (44, (0.9, 0.7)), (47, (1.4, 0.8))]:
        ledger.observe({"event_id": minute * 10, "type": "pass"}, _snapshot(minute, *xg))
    ledger.observe({"event_id": 445, "type": "shot", "clock": "44:30", "team_id": "THU", "player_id": "THU-15", "xg": 0.5},
                   _snapshot(44, 0.9, 0.7))
    pending = ledger.add(_insight(), CONTEXT)  # issued for 34:41 but added at 47'
    close = ledger.window_close(pending, live=_snapshot(47, 1.4, 0.8))
    assert close["minute"] == 44 and close["event_id"] == 440  # the first state seen at the due minute
    assert ledger.window_events(pending, close["event_id"]) == []  # the shot at 44:30 came after the mark
    facts, scores, _ = grade_forecast(pending, close, ledger.window_events(pending, close["event_id"]))
    assert facts["xg_gained"] == {"THU": 0.44, "NBF": 0.08} and not facts["truncated"] and facts["minutes"] == 10
    assert scores["dominance"] == 0.0  # NBF was called, Thames created more
    # with no mark at or just after the due minute, the live state closes the window
    assert ledger.window_close(PendingForecast(**{**pending.__dict__, "due_minute": 60}), live={"minute": 95})["minute"] == 95



def test_grading_settles_dominance_by_xg_gained_goal_by_brier_and_watch_by_involvement():
    ledger = ForecastLedger()
    pending = ledger.add(_insight(), CONTEXT)
    window = [{"type": "shot", "clock": "36:00", "team_id": "NBF", "player_id": "NBF-19", "xg": 0.2},
              {"type": "goal", "clock": "40:00", "team_id": "NBF", "player_id": "NBF-19"}]
    facts, scores, naive = grade_forecast(pending, _snapshot(44, 0.50, 1.10, score=(0, 2)), window)
    assert facts["xg_gained"] == {"THU": 0.04, "NBF": 0.48} and facts["shots"] == 2 and not facts["truncated"]
    assert facts["goals"][0]["team_id"] == "NBF" and facts["players_involved"] == ["NBF-19"]
    assert scores["dominance"] == 1.0 and scores["watch"] == 1.0
    assert scores["goal"] == round(1 - (0.4 - 1) ** 2, 3)
    assert scores["overall"] == round((1 + scores["goal"] + 1) / 3, 3)
    # the naive baseline (xG leader keeps dominating, base-rate goal odds, nobody to watch yet) on the same window
    assert naive["dominance"] == 1.0 and naive["watch"] is None
    assert naive["goal"] == round(1 - (BASE_GOAL_RATE_10MIN - 1) ** 2, 3)
    assert naive["overall"] == round((1 + naive["goal"]) / 2, 3)


def test_grading_leaves_unsettleable_claims_out_of_the_score():
    ledger = ForecastLedger()
    pending = ledger.add(_insight({**FORECAST, "watch_player_id": None}), CONTEXT)
    facts, scores, _ = grade_forecast(pending, _snapshot(44, 0.46, 0.62), [])  # nothing happened in the window
    assert facts["xg_gained"] == {"THU": 0.0, "NBF": 0.0} and facts["goals"] == []
    assert scores["dominance"] is None and scores["watch"] is None
    assert scores["goal"] == round(1 - 0.4 ** 2, 3) and scores["overall"] == scores["goal"]


def test_grading_marks_a_window_cut_short_by_full_time():
    ledger = ForecastLedger()
    pending = ledger.add(_insight(), CONTEXT)
    facts, _, _ = grade_forecast(pending, _snapshot(38, 0.5, 0.7, clock="38:12"), [])
    assert facts["truncated"] and facts["minutes"] == 4 and facts["window"] == "34:41 to 38:12"


def test_wrong_calls_score_zero():
    ledger = ForecastLedger()
    pending = ledger.add(_insight(), CONTEXT)  # calls NBF to dominate, 0.4 goal odds, watch Okafor
    window = [{"type": "goal", "clock": "39:00", "team_id": "THU", "player_id": "THU-15"}]
    _, scores, _ = grade_forecast(pending, _snapshot(44, 1.2, 0.65, score=(1, 1)), window)
    assert scores["dominance"] == 0.0 and scores["watch"] == 0.0 and scores["goal"] == round(1 - 0.6 ** 2, 3)


def test_credibility_is_a_running_mean_next_to_the_baseline():
    ledger = ForecastLedger()
    ledger.record({"event_id": 1, "scores": {"overall": 1.0, "dominance": 1.0, "goal": 1.0, "watch": None},
                   "naive_scores": {"overall": 0.5, "dominance": 0.0, "goal": 1.0, "watch": None}})
    ledger.record({"event_id": 2, "scores": {"overall": 0.5, "dominance": 0.0, "goal": 1.0, "watch": 1.0},
                   "naive_scores": {"overall": 0.5, "dominance": 0.0, "goal": 1.0, "watch": None}})
    s = ledger.summary()
    assert s["judged"] == 2 and s["pending"] == 0 and s["horizon_min"] == 10
    assert s["analyst"] == {"overall": 0.75, "dominance": 0.5, "goal": 1.0, "watch": 1.0}
    assert s["naive"] == {"overall": 0.5, "dominance": 0.0, "goal": 1.0, "watch": None}
    assert s["counts"] == {"analyst": {"overall": 2, "dominance": 2, "goal": 2, "watch": 1},
                           "naive": {"overall": 2, "dominance": 2, "goal": 2, "watch": 0}}
    assert s["counts"]["analyst"]["overall"] == s["judged"]
    assert ForecastLedger().summary()["analyst"]["overall"] is None


def test_naive_forecast_backs_the_xg_leader_with_base_rate_odds_and_the_top_shooter():
    n = naive_forecast(CONTEXT)
    assert n["dominant_team_id"] == "NBF" and n["goal_probability"] == BASE_GOAL_RATE_10MIN and n["watch_player_id"] is None
    history = [{"event_id": 10, "type": "shot", "player_id": "THU-15"}, {"event_id": 20, "type": "goal", "player_id": "NBF-19"},
               {"event_id": 30, "type": "shot", "player_id": "THU-15"}, {"event_id": 40, "type": "injury_concern", "player_id": "NBF-07"}]
    assert naive_forecast(CONTEXT, history)["watch_player_id"] == "THU-15"  # two shots beat one goal; knocks do not count
    # the ledger only lets the naive call see what happened before the forecast was issued
    ledger = ForecastLedger()
    for e in history:
        ledger.observe(e)
    ledger.observe({"event_id": 500, "type": "shot", "player_id": "NBF-19"})
    ledger.observe({"event_id": 501, "type": "shot", "player_id": "NBF-19"})
    assert ledger.add(_insight(), CONTEXT).naive["watch_player_id"] == "THU-15"  # issued at event 120, NBF-19's late shots unseen


def test_verdict_thresholds():
    assert verdict_from_score(0.9) == "called_it" and verdict_from_score(0.75) == "called_it"
    assert verdict_from_score(0.5) == "partly" and verdict_from_score(None) == "partly"
    assert verdict_from_score(0.35) == "missed" and verdict_from_score(0.0) == "missed"


# ---------------------------------------------------------------- judge agent + pipeline

def _graded_context(language="es"):
    ledger = ForecastLedger()
    pending = ledger.add(_insight(), CONTEXT)
    window = [{"type": "goal", "clock": "40:00", "team_id": "NBF", "player_id": "NBF-19"}]
    facts, scores, naive = grade_forecast(pending, _snapshot(44, 0.5, 1.1, score=(0, 2)), window)
    ledger.record({"event_id": pending.event_id, "scores": scores, "naive_scores": naive})
    ctx = build_judge_context(pending, facts, scores, naive, META, language)
    ctx["credibility"] = ledger.summary()
    return ctx


def test_judge_context_names_teams_and_players_and_the_prompt_asks_for_the_language():
    ctx = _graded_context("es")
    assert ctx["forecast"]["dominant_team"] == "Northbridge FC" and ctx["forecast"]["watch_player"] == "Kai Okafor"
    assert ctx["facts"]["xg_gained_named"] == {"Thames United": 0.04, "Northbridge FC": 0.48}
    assert ctx["facts"]["players_involved_named"] == ["Kai Okafor"]
    prompt = judge_prompt(ctx)
    assert "Graded forecast" in prompt and "rioplatense" in prompt
    json.dumps(ctx)


def test_judge_agent_returns_the_structured_verdict():
    payload = {"verdict": "called_it", "summary": "Lo clavó: Northbridge dominó y Okafor marcó.", "lesson": "nothing"}
    fake = FakeAgent(payload)
    verdict = asyncio.run(JudgeAgent(fake).judge(_graded_context()))
    assert isinstance(verdict, JudgeVerdict) and verdict.verdict == "called_it"
    assert fake.calls[0][1]["response_format"] is JudgeVerdict


def test_pipeline_keeps_the_scores_and_falls_back_to_a_code_verdict_when_the_judge_fails():
    ctx = _graded_context()
    ok = asyncio.run(JudgePipeline(JudgeAgent(FakeAgent({"verdict": "partly", "summary": "s", "lesson": "l"}))).run(ctx))
    assert ok["verdict"]["summary"] == "s" and ok["scores"] == ctx["scores"] and ok["errors"] == []
    assert [e["stage"] for e in ok["trace"] if e["kind"] == "stage"] == ["judge"]

    broken = asyncio.run(JudgePipeline(JudgeAgent(FakeAgent(fail=True))).run(ctx))
    assert broken["verdict"] == {"verdict": "called_it", "summary": None, "lesson": None}  # overall >= 0.75
    assert broken["errors"] and "boom" in broken["errors"][0]
    assert broken["credibility"]["judged"] == 1

    silent = asyncio.run(JudgePipeline(None).run(ctx))
    assert silent["verdict"]["verdict"] == "called_it" and silent["errors"] == []
    json.dumps(ok), json.dumps(broken)
