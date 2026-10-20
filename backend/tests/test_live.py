"""Live smoke test against Azure AI Foundry. Opt-in: MATCHMIND_LIVE=1 pytest tests/test_live.py."""

from __future__ import annotations

import asyncio
import os

import pytest

from matchmind.agents.clients import build_pipeline, foundry_configured
from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.agents.schemas import ViewerProfile
from matchmind.interpreter.state import MatchState

pytestmark = pytest.mark.skipif(
    os.environ.get("MATCHMIND_LIVE") != "1" or not foundry_configured(),
    reason="live Foundry test; set MATCHMIND_LIVE=1 and configure backend/.env",
)


def test_pipeline_explains_the_first_goal_with_real_agents(match):
    events, meta = match
    state = MatchState(meta)
    for e in events:
        state.apply(e)
        if e["type"] == "goal":
            break
    moment = detect_key_moment(e, state.snapshot())
    ctx = build_moment_context(moment, state.snapshot(), meta)
    profiles = [ViewerProfile(mode="analyst"), ViewerProfile(mode="commentator", language="es")]
    result = asyncio.run(build_pipeline().run(ctx, profiles))
    assert result["errors"] == []
    assert result["analyst"]["headline"]
    assert 0.0 <= result["analyst"]["confidence"] <= 1.0
    es = result["viewers"]["commentator:es:-"]
    assert es["narration"]["language"] == "es" and es["narration"]["text"]
    assert es["decision"]["priority"] == 5
