"""Coach agent: proposes an intervention on a risk alert; the system simulates the branch."""

from __future__ import annotations

import asyncio
import json

import pytest

from matchmind.agents.coach import CoachAgent, CoachPipeline, build_coach_context
from matchmind.agents.schemas import CoachProposal
from matchmind.interpreter.state import MatchState
from matchmind.tools.registry import LiveStateRegistry, MatchTools
from tests.test_agents import FakeAgent


@pytest.fixture(scope="module")
def live(match):
    """Registry + tools + snapshot at minute ~60 of the demo match."""
    events, meta = match
    state = MatchState(meta)
    for e in events:
        state.apply(e)
        if e["type"] == "physical_sample" and e["minute"] >= 59:
            break
    reg = LiveStateRegistry()
    reg.update(meta["match_id"], meta, state.snapshot())
    return reg, MatchTools(reg), state.snapshot()


def _alert(snapshot, meta):
    pid = next(p["player_id"] for p in snapshot["players"].values() if p["on_pitch"] and p["position"] == "MF" and p["team_id"] == meta["home_id"])
    p = snapshot["players"][pid]
    return {"player_id": pid, "name": p["name"], "team_id": p["team_id"], "position": "MF", "open_minute": 59,
            "expires_minute": 74, "hazard": 0.81, "level": "high", "clock": "59:40", "minutes_played": 59, "acwr_live": p["acwr_live"]}


def test_coach_context_has_player_workload_bench_options_and_match_state(live, meta):
    reg, tools, snap = live
    alert = _alert(snap, meta)
    ctx = build_coach_context(alert, snap, meta, trigger="risk_alert")
    assert ctx["trigger"] == "risk_alert" and ctx["player"]["player_id"] == alert["player_id"]
    assert ctx["minute"] == 59 and ctx["score"] == snap["score"]
    assert ctx["bench_options"], "no bench options"
    assert all(b["position"] == "MF" and b["minutes_played"] == 0 for b in ctx["bench_options"])
    assert ctx["team"]["name"] == meta["teams"][meta["home_id"]]["name"]
    assert "fatigue" not in json.dumps(ctx) and len(json.dumps(ctx)) < 5000


def test_coach_returns_structured_proposal_grounded_in_context(live, meta):
    reg, tools, snap = live
    alert = _alert(snap, meta)
    ctx = build_coach_context(alert, snap, meta, trigger="risk_alert")
    bench = ctx["bench_options"][0]["player_id"]
    fake = FakeAgent({"action": "substitution", "team_id": alert["team_id"], "player_off_id": alert["player_id"],
                      "player_on_id": bench, "press_intensity": None, "style": None, "minute": 60,
                      "rationale": "hazard 0.81, ACWR elevated", "urgency": 4, "expected_effect": "fewer knocks"})
    proposal = asyncio.run(CoachAgent(fake).propose(ctx))
    assert isinstance(proposal, CoachProposal) and proposal.action == "substitution"
    prompt, options = fake.calls[0]
    assert options["response_format"] is CoachProposal
    assert alert["name"] in prompt and bench in prompt and "59" in prompt


def test_pipeline_simulates_the_proposed_substitution(live, meta):
    reg, tools, snap = live
    alert = _alert(snap, meta)
    ctx = build_coach_context(alert, snap, meta, trigger="risk_alert")
    fake = FakeAgent({"action": "substitution", "team_id": alert["team_id"], "player_off_id": alert["player_id"],
                      "player_on_id": None, "press_intensity": None, "style": None, "minute": 60,
                      "rationale": "r", "urgency": 4, "expected_effect": "e"})
    result = asyncio.run(CoachPipeline(CoachAgent(fake), tools).run(ctx))
    assert result["proposal"]["action"] == "substitution"
    assert result["branch"]["status"] == "applied" and result["branch"]["divergence_minute"] == 60
    assert result["branch"]["player_off"]["player_id"] == alert["player_id"]
    assert result["errors"] == [] and result["latency_ms"] >= 0
    json.dumps(result)


def test_pipeline_hold_means_no_branch(live, meta):
    reg, tools, snap = live
    ctx = build_coach_context(_alert(snap, meta), snap, meta, trigger="risk_alert")
    fake = FakeAgent({"action": "hold", "team_id": meta["home_id"], "player_off_id": None, "player_on_id": None,
                      "press_intensity": None, "style": None, "minute": 60, "rationale": "fine", "urgency": 1,
                      "expected_effect": "none"})
    result = asyncio.run(CoachPipeline(CoachAgent(fake), tools).run(ctx))
    assert result["proposal"]["action"] == "hold" and result["branch"] is None


def test_pipeline_survives_agent_failure_and_bad_proposals(live, meta):
    reg, tools, snap = live
    ctx = build_coach_context(_alert(snap, meta), snap, meta, trigger="risk_alert")
    result = asyncio.run(CoachPipeline(CoachAgent(FakeAgent(fail=True)), tools).run(ctx))
    assert result["proposal"] is None and "boom" in result["errors"][0]
    bad = FakeAgent({"action": "substitution", "team_id": meta["home_id"], "player_off_id": "ZZZ-99", "player_on_id": None,
                     "press_intensity": None, "style": None, "minute": 60, "rationale": "r", "urgency": 3, "expected_effect": "e"})
    result = asyncio.run(CoachPipeline(CoachAgent(bad), tools).run(ctx))
    assert result["proposal"]["player_off_id"] == "ZZZ-99"
    assert result["branch"]["status"] == "skipped"  # the engine refuses to sub a player who is not on the pitch
