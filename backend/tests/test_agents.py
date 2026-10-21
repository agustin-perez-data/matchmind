"""LLM agents (Analyst, Narrator, Director) and the per-moment pipeline.

The Agent Framework agent is replaced by a fake with the same `run()` contract
so these tests never call Foundry. The live smoke test lives in test_live.py.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from matchmind.agents.analyst import AnalystAgent
from matchmind.agents.director import DirectorAgent
from matchmind.agents.narrator import NarratorAgent
from matchmind.agents.pipeline import MomentPipeline
from matchmind.agents.schemas import AnalystInsight, DirectorDecision, Narration, ViewerProfile


class FakeAgent:
    """Mimics agent_framework.Agent.run(prompt, options={"response_format": Model})."""

    def __init__(self, payload: dict | None = None, *, fail: bool = False, delay: float = 0.0, name="fake"):
        self.payload, self.fail, self.delay, self.name = payload or {}, fail, delay, name
        self.calls: list[tuple[str, dict]] = []

    async def run(self, prompt, *, options=None, **_):
        self.calls.append((prompt, options or {}))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        model = (options or {}).get("response_format")
        value = model.model_validate(self.payload) if model is not None else None
        return SimpleNamespace(value=value, text=json.dumps(self.payload))


CONTEXT = {
    "match_id": "THU-NBF-42", "clock": "34:41", "period": 1, "minute": 34,
    "score": {"THU": 0, "NBF": 1}, "home_id": "THU", "away_id": "NBF",
    "moment": {"kind": "goal", "importance": 5, "summary": "34:41 GOAL Northbridge FC - Kai Okafor (assist Luka Ojo). 0-1"},
    "event": {"type": "goal", "team_id": "NBF", "player_id": "NBF-19", "player_name": "Kai Okafor"},
    "teams": {"THU": {"name": "Thames United", "xg": 0.46, "possession_pct": 55.0},
              "NBF": {"name": "Northbridge FC", "xg": 0.62, "possession_pct": 45.0}},
    "momentum": -0.67, "xg_race_tail": [], "players_involved": [
        {"player_id": "NBF-19", "name": "Kai Okafor", "team_id": "NBF", "position": "FW",
         "minutes_played": 34, "distance_m": 3700.0, "acwr_live": 1.41, "risk_band": "elevated"}],
    "risk_alerts": [],
}

FORECAST = {"dominant_team_id": "NBF", "goal_probability": 0.4, "watch_player_id": "NBF-19",
            "claim": "Northbridge keep finding Okafor behind the line"}
INSIGHT = {"headline": "Northbridge punish a slow press", "why_it_matters": "Thames' high line was beaten.",
           "tactical_read": "Direct ball behind the full-back.", "key_stat": "xG 0.46 vs 0.62", "confidence": 0.8,
           "forecast": FORECAST}
NARRATION = {"text": "GOAL! Okafor finishes a slick move.", "language": "en", "mode": "analyst"}
DECISION = {"show": ["narration", "insight"], "priority": 5, "headline": "Okafor strikes first",
            "personalized_note": None}


# ---------------------------------------------------------------- analyst

def test_analyst_returns_structured_insight_and_grounds_prompt_in_context():
    fake = FakeAgent(INSIGHT)
    insight = asyncio.run(AnalystAgent(fake).explain(CONTEXT))
    assert isinstance(insight, AnalystInsight)
    assert insight.headline == INSIGHT["headline"]
    prompt, options = fake.calls[0]
    assert options["response_format"] is AnalystInsight
    assert "Kai Okafor" in prompt and '"THU": 0' in prompt and "34:41" in prompt


# ---------------------------------------------------------------- narrator

@pytest.mark.parametrize("mode,language,expect", [
    ("analyst", "en", "English"),
    ("casual", "en", "casual"),
    ("commentator", "es", "rioplatense"),
    ("player_focus", "en", "NBF-19"),
])
def test_narrator_prompt_adapts_to_viewer_profile(mode, language, expect):
    fake = FakeAgent(dict(NARRATION, mode=mode, language=language))
    profile = ViewerProfile(mode=mode, language=language, favorite_player_id="NBF-19")
    narration = asyncio.run(NarratorAgent(fake).narrate(CONTEXT, profile))
    assert isinstance(narration, Narration) and narration.mode == mode
    prompt, options = fake.calls[0]
    assert options["response_format"] is Narration
    assert expect in prompt


def test_narrator_names_a_watched_favorite_player_not_involved_in_the_moment():
    ctx = dict(CONTEXT, watched_players=[
        {"player_id": "THU-19", "name": "Enzo Craven", "team_id": "THU", "position": "FW",
         "minutes_played": 34, "distance_m": 3500.0, "acwr_live": 1.1, "risk_band": "optimal"}])
    fake = FakeAgent(dict(NARRATION, mode="player_focus"))
    asyncio.run(NarratorAgent(fake).narrate(ctx, ViewerProfile(mode="player_focus", favorite_player_id="THU-19")))
    prompt, _ = fake.calls[0]
    assert "Enzo Craven" in prompt and '"involved_in_this_moment": false' in prompt


# ---------------------------------------------------------------- director

def test_director_receives_insight_narration_and_profile():
    fake = FakeAgent(DECISION)
    profile = ViewerProfile(mode="casual", language="en")
    decision = asyncio.run(DirectorAgent(fake).direct(
        CONTEXT, AnalystInsight(**INSIGHT), Narration(**NARRATION), profile))
    assert isinstance(decision, DirectorDecision)
    assert decision.show == ["narration", "insight"] and decision.priority == 5
    prompt, _ = fake.calls[0]
    assert INSIGHT["headline"] in prompt and NARRATION["text"] in prompt and "casual" in prompt


def test_director_decision_rejects_unknown_cards():
    with pytest.raises(ValueError):
        DirectorDecision(show=["tiktok"], priority=3, headline="x")


# ---------------------------------------------------------------- profile

def test_viewer_profile_defaults_and_key():
    p = ViewerProfile()
    assert p.mode == "analyst" and p.language == "en" and p.favorite_player_id is None
    assert p.key == "analyst:en:-"
    assert ViewerProfile(mode="player_focus", language="es", favorite_player_id="THU-09").key == "player_focus:es:THU-09"


def test_viewer_profile_rejects_unknown_mode_or_language():
    with pytest.raises(ValueError):
        ViewerProfile(mode="vip")
    with pytest.raises(ValueError):
        ViewerProfile(language="fr")


# ---------------------------------------------------------------- pipeline

def test_pipeline_runs_analyst_and_narrators_concurrently_then_director():
    analyst, narrator, director = FakeAgent(INSIGHT, delay=0.2), FakeAgent(NARRATION, delay=0.2), FakeAgent(DECISION)
    profiles = [ViewerProfile(mode="analyst"), ViewerProfile(mode="casual")]
    pipeline = MomentPipeline(AnalystAgent(analyst), NarratorAgent(narrator), DirectorAgent(director), profiles)

    async def timed():
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        result = await pipeline.run(CONTEXT)
        return result, loop.time() - t0

    result, elapsed = asyncio.run(timed())
    assert elapsed < 0.35, elapsed  # 3 slow calls in parallel, not 0.6s sequential
    assert result["moment"] == CONTEXT["moment"]
    assert result["analyst"]["headline"] == INSIGHT["headline"]
    assert set(result["viewers"]) == {"analyst:en:-", "casual:en:-"}
    for view in result["viewers"].values():
        assert view["narration"]["text"] == NARRATION["text"]
        assert view["decision"]["show"] == DECISION["show"]
    assert len(narrator.calls) == 2 and len(director.calls) == 2 and len(analyst.calls) == 1


def test_pipeline_survives_a_failing_agent():
    pipeline = MomentPipeline(AnalystAgent(FakeAgent(fail=True)), NarratorAgent(FakeAgent(NARRATION)),
                              DirectorAgent(FakeAgent(DECISION)), [ViewerProfile()])
    result = asyncio.run(pipeline.run(CONTEXT))
    assert result["analyst"] is None
    assert "boom" in result["errors"][0]
    assert result["viewers"]["analyst:en:-"]["narration"]["text"] == NARRATION["text"]


def test_pipeline_result_is_json_serializable():
    pipeline = MomentPipeline(AnalystAgent(FakeAgent(INSIGHT)), NarratorAgent(FakeAgent(NARRATION)),
                              DirectorAgent(FakeAgent(DECISION)), [ViewerProfile()])
    result = asyncio.run(pipeline.run(CONTEXT))
    json.dumps(result)
