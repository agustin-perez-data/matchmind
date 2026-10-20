"""Match-state tool registry: one implementation, exposed in-process and over MCP."""

from __future__ import annotations

import asyncio
import json

import pytest

from matchmind.interpreter.state import MatchState
from matchmind.tools.registry import LiveStateRegistry, MatchTools


@pytest.fixture(scope="module")
def registry(match):
    events, meta = match
    state = MatchState(meta)
    for e in events[:1200]:  # mid second half
        state.apply(e)
    reg = LiveStateRegistry()
    reg.update(meta["match_id"], meta, state.snapshot())
    return reg


@pytest.fixture(scope="module")
def tools(registry):
    return MatchTools(registry)


def test_list_matches_reports_live_score_and_clock(tools, meta):
    rows = tools.list_matches()
    assert [r["match_id"] for r in rows] == [meta["match_id"]]
    assert rows[0]["home"] == meta["teams"][meta["home_id"]]["name"]
    assert "clock" in rows[0] and "score" in rows[0]


def test_get_match_state_is_compact_and_current(tools, registry, meta):
    snap = registry.get(meta["match_id"])["snapshot"]
    state = tools.get_match_state(meta["match_id"])
    assert state["score"] == snap["score"] and state["clock"] == snap["clock"]
    assert state["momentum"] == snap["momentum"]
    assert set(state["teams"]) == set(meta["teams"])
    assert "players" not in state  # per-player data has its own tool
    assert len(json.dumps(state)) < 3000


def test_get_player_workload_returns_observables_only(tools, meta):
    tid = meta["home_id"]
    pid = meta["teams"][tid]["players"][2]["player_id"]
    p = tools.get_player_workload(meta["match_id"], pid)
    assert p["player_id"] == pid and p["team"] == meta["teams"][tid]["name"]
    assert {"minutes_played", "distance_m", "sprints", "top_speed_kmh", "acwr_live", "acwr_pre_match", "risk_band"} <= set(p)
    assert "fatigue" not in json.dumps(p)
    assert len(p["load_history_last_7_days"]) == 7


def test_get_risk_alerts_is_sorted_and_limited(tools, meta):
    alerts = tools.get_risk_alerts(meta["match_id"], limit=2)
    assert len(alerts) <= 2
    ratios = [a["acwr_live"] for a in alerts]
    assert ratios == sorted(ratios, reverse=True)


def test_unknown_match_raises_a_clear_error(tools):
    with pytest.raises(KeyError, match="NOPE"):
        tools.get_match_state("NOPE")
    with pytest.raises(KeyError, match="NOPE"):
        tools.get_player_workload("NOPE", "THU-01")


def test_unknown_player_raises_a_clear_error(tools, meta):
    with pytest.raises(KeyError, match="ZZZ-99"):
        tools.get_player_workload(meta["match_id"], "ZZZ-99")


def test_mcp_server_exposes_the_registry_tools(registry, meta):
    from matchmind.tools.mcp_server import build_mcp_server

    server = build_mcp_server(registry)

    async def go():
        names = {t.name for t in await server.list_tools()}
        result = await server.call_tool("get_match_state", {"match_id": meta["match_id"]})
        return names, result

    names, result = asyncio.run(go())
    assert {"list_matches", "get_match_state", "get_player_workload", "get_risk_alerts", "get_xg_race"} <= names
    # FastMCP returns content blocks (TextContent) and/or a structured dict depending on version
    if isinstance(result, tuple):
        result = result[1] if len(result) > 1 else result[0]
    if isinstance(result, dict):
        text = json.dumps(result)
    else:
        text = "".join(getattr(block, "text", "") for block in result)
    assert meta["match_id"] in text and '"momentum"' in text
