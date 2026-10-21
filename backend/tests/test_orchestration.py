"""Agent Framework orchestration: concurrent fan-out, director fan-in, and per-moment traces."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from matchmind.agents.analyst import AnalystAgent
from matchmind.agents.director import DirectorAgent
from matchmind.agents.narrator import NarratorAgent
from matchmind.agents.orchestration import FrameworkMomentPipeline, compose_fan_out_prompt, parse_participant
from matchmind.agents.schemas import AnalystInsight, Narration, ViewerProfile
from matchmind.agents.tracing import MomentTrace, current_trace, trace_agents, trace_tools
from tests.test_agents import CONTEXT, DECISION, INSIGHT, NARRATION, FakeAgent


# ---------------------------------------------------------------- tracing

def test_trace_records_agent_runs_with_latency_and_tool_calls():
    trace = MomentTrace("moment")
    token = current_trace.set(trace)
    try:
        agent_ctx = SimpleNamespace(agent=SimpleNamespace(name="Analyst"), result=SimpleNamespace(usage_details=SimpleNamespace(input_token_count=120, output_token_count=40)))
        fn_ctx = SimpleNamespace(function=SimpleNamespace(name="get_player_workload"), arguments={"match_id": "THU-NBF-42", "player_id": "THU-13"}, result={"acwr_live": 1.3})

        async def inner_tool():
            await asyncio.sleep(0.01)

        async def inner_agent():
            await trace_tools(fn_ctx, inner_tool)

        asyncio.run(trace_agents(agent_ctx, inner_agent))
    finally:
        current_trace.reset(token)
    kinds = [e["kind"] for e in trace.to_list()]
    assert kinds == ["agent_start", "tool_call", "tool_result", "agent_end"]
    start, call, result, end = trace.to_list()
    assert start["agent"] == "Analyst" and end["agent"] == "Analyst"
    assert call["tool"] == "get_player_workload" and call["args"]["player_id"] == "THU-13"
    assert call["agent"] == "Analyst" and result["agent"] == "Analyst"  # attributed to the running agent
    assert result["latency_ms"] >= 5 and end["latency_ms"] >= result["latency_ms"]
    assert end["tokens"] == {"input": 120, "output": 40}
    json.dumps(trace.to_list())


def test_middleware_is_a_no_op_without_an_active_trace():
    called = []

    async def inner():
        called.append(1)

    asyncio.run(trace_agents(SimpleNamespace(agent=SimpleNamespace(name="X")), inner))
    assert called == [1] and current_trace.get() is None


# ---------------------------------------------------------------- prompt + parsing

def test_fan_out_prompt_carries_context_and_viewer_profile():
    prompt = compose_fan_out_prompt(CONTEXT, ViewerProfile(mode="commentator", language="es"))
    assert "Kai Okafor" in prompt and "rioplatense" in prompt and "Key moment context" in prompt


def test_parse_participant_reads_json_even_with_prose_around_it():
    outputs = [("Analyst", "Sure: " + json.dumps(INSIGHT) + "\nDone."), ("Narrator", json.dumps(NARRATION))]
    insight = parse_participant(outputs, "Analyst", AnalystInsight)
    narration = parse_participant(outputs, "Narrator", Narration)
    assert isinstance(insight, AnalystInsight) and insight.headline == INSIGHT["headline"]
    assert isinstance(narration, Narration) and narration.text == NARRATION["text"]
    with pytest.raises(ValueError, match="Director"):
        parse_participant(outputs, "Director", Narration)


# ---------------------------------------------------------------- pipeline

def _pipeline(run_workflow, director=None):
    return FrameworkMomentPipeline(
        AnalystAgent(FakeAgent(INSIGHT)), NarratorAgent(FakeAgent(NARRATION)),
        DirectorAgent(director or FakeAgent(DECISION)), run_workflow=run_workflow,
    )


def test_pipeline_fans_out_once_then_runs_the_director_and_returns_a_trace():
    seen = []

    async def fake_workflow(prompt):
        seen.append(prompt)
        await asyncio.sleep(0.01)
        return [("Analyst", json.dumps(INSIGHT)), ("Narrator", json.dumps(NARRATION))]

    pipeline = _pipeline(fake_workflow)
    result = asyncio.run(pipeline.run(CONTEXT, [ViewerProfile(mode="commentator", language="es")]))
    assert len(seen) == 1 and "rioplatense" in seen[0]
    assert result["analyst"]["headline"] == INSIGHT["headline"]
    view = result["viewers"]["commentator:es:-"]
    assert view["narration"]["text"] == NARRATION["text"] and view["decision"]["show"] == DECISION["show"]
    assert result["errors"] == [] and result["orchestration"].startswith("agent-framework")
    stages = [e["stage"] for e in result["trace"] if e["kind"] == "stage"]
    assert stages == ["fan-out", "director"]
    assert any(e["kind"] == "stage_end" and e["stage"] == "fan-out" and e["latency_ms"] >= 5 for e in result["trace"])
    json.dumps(result)


def test_pipeline_falls_back_to_direct_calls_when_the_workflow_fails():
    async def broken(prompt):
        raise RuntimeError("workflow down")

    result = asyncio.run(_pipeline(broken).run(CONTEXT, [ViewerProfile()]))
    assert result["analyst"]["headline"] == INSIGHT["headline"]
    assert result["viewers"]["analyst:en:-"]["narration"]["text"] == NARRATION["text"]
    assert any("workflow down" in e for e in result["errors"])
    assert any(e["kind"] == "fallback" for e in result["trace"])


def test_pipeline_with_several_profiles_uses_the_direct_path():
    calls = []

    async def fake_workflow(prompt):
        calls.append(1)
        return []

    result = asyncio.run(_pipeline(fake_workflow).run(CONTEXT, [ViewerProfile(), ViewerProfile(mode="casual")]))
    assert calls == [] and set(result["viewers"]) == {"analyst:en:-", "casual:en:-"}
