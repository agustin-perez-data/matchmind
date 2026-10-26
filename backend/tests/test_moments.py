"""Key-moment detection and the compact context handed to the LLM agents."""

from __future__ import annotations

import json

import pytest

from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.interpreter.state import MatchState


@pytest.fixture(scope="module")
def moments(match):
    """Every (event, snapshot, moment) triple the demo match produces."""
    events, meta = match
    state = MatchState(meta)
    out = []
    for e in events:
        state.apply(e)
        snap = state.snapshot()
        m = detect_key_moment(e, snap)
        if m is not None:
            out.append((e, snap, m))
    return out


def test_every_goal_is_a_top_importance_moment(moments, events):
    goal_ids = {e["event_id"] for e in events if e["type"] == "goal"}
    found = {e["event_id"]: m for e, _, m in moments if e["type"] == "goal"}
    assert set(found) == goal_ids
    assert all(m.kind == "goal" and m.importance == 5 for m in found.values())


def test_routine_passes_and_pressures_are_never_moments(moments):
    assert not any(e["type"] in ("pass", "pressure", "possession_change", "physical_sample") for e, _, _ in moments)


def test_low_xg_shots_are_filtered_but_big_chances_kept(events, meta):
    state = MatchState(meta)
    tiny = dict(events[1], type="shot", xg=0.03, outcome="off_target", x=60.0, y=50.0, distance_m=30.0,
                shot_speed_kmh=80.0, assist_player_id=None, assist_player_name=None)
    big = dict(tiny, xg=0.45, outcome="saved")
    state.apply(tiny)
    assert detect_key_moment(tiny, state.snapshot()) is None
    state.apply(big)
    m = detect_key_moment(big, state.snapshot())
    assert m is not None and m.kind == "big_chance" and m.importance >= 3


def test_half_and_full_time_are_moments(moments):
    kinds = {m.kind for _, _, m in moments}
    assert {"half_time", "full_time"} <= kinds


def test_moment_summary_is_a_short_english_line(moments):
    for e, _, m in moments:
        assert 10 <= len(m.summary) <= 160, m.summary
        assert e["clock"] in m.summary


def test_context_is_compact_json_without_latent_state(moments, meta):
    e, snap, m = next(t for t in moments if t[2].kind == "goal")
    ctx = build_moment_context(m, snap, meta)
    blob = json.dumps(ctx)
    assert "fatigue" not in blob and "susceptib" not in blob
    assert len(blob) < 6000, len(blob)
    assert ctx["moment"]["kind"] == "goal"
    assert ctx["score"] == snap["score"]
    assert ctx["clock"] == e["clock"]
    assert set(ctx["teams"]) == set(meta["teams"])
    for tid, team in ctx["teams"].items():
        assert team["name"] == meta["teams"][tid]["name"]
        assert "xg" in team and "possession_pct" in team
    assert len(ctx["xg_race_tail"]) <= 6
    assert "momentum" in ctx


def test_context_lists_the_players_involved_with_workload(moments, meta):
    e, snap, m = next(t for t in moments if t[2].kind == "goal")
    ctx = build_moment_context(m, snap, meta)
    ids = {p["player_id"] for p in ctx["players_involved"]}
    assert e["player_id"] in ids
    if e.get("assist_player_id"):
        assert e["assist_player_id"] in ids
    for p in ctx["players_involved"]:
        assert {"name", "team_id", "position", "minutes_played", "distance_m", "acwr_live", "risk_band"} <= set(p)


def test_context_can_include_watched_players_for_player_focus_viewers(moments, meta):
    e, snap, m = next(t for t in moments if t[2].kind == "goal")
    watched = [p["player_id"] for p in meta["teams"][meta["home_id"]]["players"][:2]]
    ctx = build_moment_context(m, snap, meta, watched_players=[*watched, "ZZZ-99"])
    assert [p["player_id"] for p in ctx["watched_players"]] == watched
    assert all("name" in p and "acwr_live" in p for p in ctx["watched_players"])
    assert "watched_players" not in build_moment_context(m, snap, meta) or build_moment_context(m, snap, meta)["watched_players"] == []


def test_context_carries_top_risk_alerts_only(moments, meta):
    e, snap, m = moments[-1]
    ctx = build_moment_context(m, snap, meta)
    assert len(ctx["risk_alerts"]) <= 3
    assert ctx["risk_alerts"] == snap["risk_alerts"][:3]
