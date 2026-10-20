"""simulate_intervention: the counterfactual tool (MCP + in-process) and branch storage."""

from __future__ import annotations

import json

import pytest

from matchmind.interpreter.state import MatchState
from matchmind.tools.registry import LiveStateRegistry, MatchTools


@pytest.fixture(scope="module")
def registry(match):
    events, meta = match
    state = MatchState(meta)
    for e in events:
        state.apply(e)
    reg = LiveStateRegistry()
    reg.update(meta["match_id"], meta, state.snapshot())
    return reg


@pytest.fixture(scope="module")
def tools(registry):
    return MatchTools(registry)


def _starting_gk(meta, team_id):
    return next(p["player_id"] for p in meta["teams"][team_id]["players"] if p["position"] == "GK" and p["starter"])


def test_simulate_substitution_returns_a_branch_summary_and_stores_the_branch(tools, registry, meta):
    gk = _starting_gk(meta, "THU")
    out = tools.simulate_intervention(meta["match_id"], minute=60, action="substitution", team_id="THU", player_off_id=gk)
    assert out["status"] == "applied" and out["divergence_minute"] == 60
    assert out["branch_id"].startswith(meta["match_id"] + "~")
    assert out["intervention"]["type"] == "substitution" and out["intervention"]["player_off_id"] == gk
    for side in ("actual", "branch"):
        assert {"score", "xg", "shots", "injury_concerns", "goals"} <= set(out[side])
    assert out["actual"]["score"] == meta["score"]
    assert set(out["diff"]) >= {"goals_home", "goals_away", "xg_home", "xg_away", "injury_concerns"}
    assert out["player_off"]["player_id"] == gk and "concerns_after_actual" in out["player_off"]
    stored = registry.branch(meta["match_id"], out["branch_id"])
    assert stored["meta"]["interventions"][0]["status"] == "applied"
    assert stored["events"][0]["match_id"] == out["branch_id"]
    json.dumps(out)


def test_branches_are_deterministic_and_cached(tools, registry, meta):
    gk = _starting_gk(meta, "THU")
    a = tools.simulate_intervention(meta["match_id"], 60, "substitution", "THU", player_off_id=gk)
    b = tools.simulate_intervention(meta["match_id"], 60, "substitution", "THU", player_off_id=gk)
    assert a == b
    assert len(registry.branches(meta["match_id"])) >= 1


def test_simulate_tactic_change(tools, meta):
    out = tools.simulate_intervention(meta["match_id"], 70, "tactic", "NBF", press_intensity=1.0, style="direct")
    assert out["status"] == "applied" and out["intervention"]["style"] == "direct"
    assert out["branch"]["score"] is not None


def test_simulate_rejects_bad_input(tools, meta):
    with pytest.raises(ValueError):
        tools.simulate_intervention(meta["match_id"], 60, "teleport", "THU")
    with pytest.raises(ValueError):
        tools.simulate_intervention(meta["match_id"], 60, "substitution", "THU")  # no player_off_id
    with pytest.raises(KeyError):
        tools.simulate_intervention("NOPE", 60, "substitution", "THU", player_off_id="THU-01")


def test_get_risk_windows_reads_the_live_risk_summary(tools, registry, meta):
    registry.update_risk(meta["match_id"], {"minute": 70, "active_windows": [{"player_id": "THU-03", "level": "high"}],
                                            "scorecard": {"model": {}, "baseline": {}}, "hazards": {"THU-03": 0.8}})
    out = tools.get_risk_windows(meta["match_id"])
    assert out["active_windows"][0]["player_id"] == "THU-03" and out["minute"] == 70
    assert "scorecard" in out


def test_get_risk_windows_without_a_monitor_is_empty_not_an_error(tools, registry, meta):
    reg = LiveStateRegistry()
    reg.update(meta["match_id"], meta, registry.get(meta["match_id"])["snapshot"])
    out = MatchTools(reg).get_risk_windows(meta["match_id"])
    assert out["active_windows"] == [] and out["scorecard"] is None
