"""The forecast evaluation harness, with a fake Analyst (no Foundry)."""

from __future__ import annotations

import asyncio
import json

from matchmind.agents.evaluate_forecasts import forecast_with_retries, grade_match, replay, summarize
from matchmind.generate_match import generate
from tests.test_agents import FORECAST, INSIGHT, FakeAgent


class FakeAnalyst:
    def __init__(self, fail_first: int = 0):
        self.calls, self.fail_first = 0, fail_first

    async def explain(self, context, language="en"):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise RuntimeError("429 too many requests")
        from matchmind.agents.schemas import AnalystInsight
        home = context["home_id"]
        return AnalystInsight.model_validate({**INSIGHT, "forecast": {**FORECAST, "dominant_team_id": home, "watch_player_id": None}})


def test_replay_collects_key_moments_and_a_ledger_with_marks():
    events, meta = generate("THU", "NBF", seed=42)
    ledger, contexts, final = replay(events, meta, min_importance=3)
    assert contexts and all(c["moment"]["kind"] != "full_time" for c in contexts)
    assert all(c["moment"]["importance"] >= 3 for c in contexts)
    assert ledger.marks and 45 in ledger.marks and final["minute"] >= 90
    assert ledger.history and all("event_id" in e for e in ledger.history)


def test_grade_match_scores_every_forecast_on_its_own_window():
    events, meta = generate("THU", "NBF", seed=42)
    ledger, contexts, final = replay(events, meta, min_importance=3)
    analyst = FakeAnalyst()
    async def run_all():
        sem = asyncio.Semaphore(2)
        return await asyncio.gather(*(forecast_with_retries(analyst, c, sem) for c in contexts))

    insights = asyncio.run(run_all())
    rows = grade_match(ledger, contexts, list(insights), final)
    assert len(rows) == len(contexts) and analyst.calls == len(contexts)
    for r in rows:
        assert r["picked_home"] is True and r["scores"]["watch"] is None
        assert 0 <= r["scores"]["goal"] <= 1 and r["facts"]["minutes"] <= 12
        assert r["facts"]["window"].startswith(r["clock"])
    report = summarize(rows, 1, "test", 0.0)
    assert report["forecasts"] == len(rows) and report["analyst"]["watch"]["n"] == 0
    assert report["habits"]["picked_home"] == 1.0 and report["wins"]["analyst"] + report["wins"]["naive"] + report["wins"]["tie"] == len(rows)
    json.dumps(report)


def test_retries_then_gives_up_quietly():
    ctx = {"home_id": "THU", "away_id": "NBF", "teams": {}, "moment": {"event_id": 1}}
    flaky = FakeAnalyst(fail_first=1)
    import matchmind.agents.evaluate_forecasts as mod
    real_sleep = mod.asyncio.sleep
    mod.asyncio.sleep = lambda *_: real_sleep(0)  # no waiting in tests
    try:
        ok = asyncio.run(forecast_with_retries(flaky, ctx, asyncio.Semaphore(1)))
        assert ok and ok["forecast"]["dominant_team_id"] == "THU" and flaky.calls == 2
        dead = asyncio.run(forecast_with_retries(FakeAnalyst(fail_first=99), ctx, asyncio.Semaphore(1), attempts=2))
        assert dead is None
    finally:
        mod.asyncio.sleep = real_sleep
    assert FakeAgent  # keep the shared fixtures import honest
