"""The forecast evaluation harness, with a fake Analyst and Judge (no Foundry)."""

from __future__ import annotations

import asyncio
import json

from matchmind.agents.evaluate_forecasts import call_with_retries, replay, run_match, summarize
from matchmind.agents.schemas import AnalystInsight
from matchmind.generate_match import generate
from tests.test_agents import FORECAST, INSIGHT


class FakeAnalyst:
    def __init__(self, fail_first: int = 0):
        self.calls, self.fail_first, self.contexts = 0, fail_first, []

    async def explain(self, context, language="en"):
        self.calls += 1
        self.contexts.append(context)
        if self.calls <= self.fail_first:
            raise RuntimeError("429 too many requests")
        home = context["home_id"]
        return AnalystInsight.model_validate({**INSIGHT, "forecast": {**FORECAST, "dominant_team_id": home, "watch_player_id": None}})


class FakeJudge:
    def __init__(self):
        self.calls = 0

    async def run(self, context):
        self.calls += 1
        return {"event_id": context["event_id"], "issued_clock": context["issued_clock"], "forecast": context["forecast"],
                "facts": context["facts"], "verdict": {"verdict": "partly", "summary": "s", "lesson": f"lesson {self.calls}"}}


def test_replay_collects_key_moments_and_a_ledger_with_marks():
    events, meta = generate("THU", "NBF", seed=42)
    ledger, moments, final = replay(events, meta, min_importance=3)
    assert moments and all(m.kind != "full_time" and m.importance >= 3 for m, _ in moments)
    assert ledger.marks and 45 in ledger.marks and final["minute"] >= 90
    assert ledger.history and all("event_id" in e for e in ledger.history)


def test_run_match_grades_in_order_and_feeds_the_record_back():
    events, meta = generate("THU", "NBF", seed=42)
    ledger, moments, final = replay(events, meta, min_importance=3)
    analyst, judge = FakeAnalyst(), FakeJudge()
    rows = asyncio.run(run_match(analyst, judge, meta, ledger, moments, final, sem=asyncio.Semaphore(2), loop=True))
    assert len(rows) == len(moments) == analyst.calls and judge.calls == len(rows)
    assert rows[0]["had_track_record"] is False  # nothing graded before the first call
    assert any(r["had_track_record"] for r in rows[1:])  # later calls saw their record
    seen = [c["analyst_track_record"] for c in analyst.contexts if c.get("analyst_track_record")]
    assert seen and seen[-1]["forecasts_graded"] >= 1 and seen[-1]["recent_verdicts"][-1]["lesson"].startswith("lesson")
    assert all("last_10_minutes" in c and "game_state" in c for c in analyst.contexts)
    for r in rows:
        assert r["picked_home"] is True and r["scores"]["watch"] is None
        assert 0 <= r["scores"]["goal"] <= 1 and r["facts"]["minutes"] <= 12
        assert r["facts"]["window"].startswith(r["clock"])
    report = summarize(rows, 1, "test", 0.0)
    assert report["forecasts"] == len(rows) and report["analyst"]["watch"]["n"] == 0
    assert report["with_track_record"]["n"] + report["without_track_record"]["n"] == len(rows)
    assert report["habits"]["picked_home"] == 1.0
    json.dumps(report)


def test_run_match_without_the_loop_never_shows_a_record():
    events, meta = generate("THU", "NBF", seed=42)
    ledger, moments, final = replay(events, meta, min_importance=3)
    analyst = FakeAnalyst()
    rows = asyncio.run(run_match(analyst, None, meta, ledger, moments, final, sem=asyncio.Semaphore(2), loop=False))
    assert rows and all(c.get("analyst_track_record") is None for c in analyst.contexts)
    assert all(not r["had_track_record"] for r in rows)


def test_retries_then_gives_up_quietly():
    import matchmind.agents.evaluate_forecasts as mod
    real_sleep = mod.asyncio.sleep
    mod.asyncio.sleep = lambda *_: real_sleep(0)  # no waiting in tests
    try:
        flaky = FakeAnalyst(fail_first=1)
        ctx = {"home_id": "THU", "away_id": "NBF", "teams": {}, "moment": {"event_id": 1}}
        ok = asyncio.run(call_with_retries(lambda: flaky.explain(ctx), asyncio.Semaphore(1)))
        assert ok and ok.forecast.dominant_team_id == "THU" and flaky.calls == 2
        dead = FakeAnalyst(fail_first=99)
        assert asyncio.run(call_with_retries(lambda: dead.explain(ctx), asyncio.Semaphore(1), attempts=2)) is None
    finally:
        mod.asyncio.sleep = real_sleep
