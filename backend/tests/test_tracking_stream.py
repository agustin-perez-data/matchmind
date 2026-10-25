"""Positional frames through the Interpreter, the replay timeline, the WebSocket and the MCP tools."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from matchmind.api.app import create_app
from matchmind.interpreter.state import MatchState
from matchmind.sim.tracking import build_tracking
from matchmind.stream.replay import frame_stride, merge_timeline
from matchmind.tools.registry import LiveStateRegistry, MatchTools
from tests.test_api import _drain, data_dir  # noqa: F401 (fixture)


# ---------------------------------------------------------------- replay helpers

def test_frame_stride_follows_the_speed():
    assert frame_stride(0) == 0 and frame_stride(-1) == 0
    assert frame_stride(1) == 1 and frame_stride(60) == 1
    assert frame_stride(61) == 2 and frame_stride(150) == 2
    assert frame_stride(151) == 5 and frame_stride(400) == 5
    assert frame_stride(401) == 0 and frame_stride(1000) == 0


def test_merge_timeline_keeps_clock_order_with_events_before_frames():
    events = [{"period": 1, "minute": 0, "second": 5, "type": "pass"}, {"period": 1, "minute": 0, "second": 7, "type": "shot"},
              {"period": 2, "minute": 45, "second": 2, "type": "pass"}]
    frames = [{"kind": "frame", "period": 1, "minute": 0, "second": s} for s in (4, 5, 6, 7)] + [{"kind": "frame", "period": 2, "minute": 45, "second": 2}]
    tl = merge_timeline(events, frames)
    keys = [(i["period"], i["minute"] * 60 + i["second"], i.get("kind", "event")) for i in tl]
    assert keys == [(1, 4, "frame"), (1, 5, "event"), (1, 5, "frame"), (1, 6, "frame"), (1, 7, "event"), (1, 7, "frame"), (2, 2702, "event"), (2, 2702, "frame")]
    assert merge_timeline(events, []) == events


# ---------------------------------------------------------------- interpreter

def _meta():
    return {"match_id": "M", "home_id": "THU", "away_id": "NBF", "teams": {
        "THU": {"name": "Thames", "players": [{"player_id": f"THU-{i:02d}", "name": f"H{i}", "position": pos, "shirt_number": i, "starter": True}
                                               for i, pos in enumerate(["GK", "DF", "DF", "MF", "FW"], start=1)]},
        "NBF": {"name": "Northbridge", "players": [{"player_id": f"NBF-{i:02d}", "name": f"A{i}", "position": pos, "shirt_number": i, "starter": True}
                                                    for i, pos in enumerate(["GK", "DF", "DF", "MF", "FW"], start=1)]},
    }}


def test_apply_frame_measures_shape_heat_and_pressure_in_team_frame():
    state = MatchState(_meta())
    state.apply({"event_id": 1, "period": 1, "minute": 0, "second": 0, "type": "kickoff", "team_id": "THU", "home_attacking_right": True})
    # home attacks right: outfield at x 20/20/40/60 -> mean 35 -> 36.75 m; away attacks left: at x 90/90/70/63 -> team frame 10/10/30/37 -> 21.75 -> 22.8 m
    frame = {"kind": "frame", "period": 1, "minute": 3, "second": 0, "carrier": "THU-05",
             "players": {"THU-01": [5, 50], "THU-02": [20, 20], "THU-03": [20, 80], "THU-04": [40, 50], "THU-05": [60, 50],
                         "NBF-01": [95, 50], "NBF-02": [90, 30], "NBF-03": [90, 70], "NBF-04": [70, 50], "NBF-05": [63, 50]}}
    state.apply_frame(frame)
    snap = state.snapshot()
    thu, nbf = snap["shape"]["THU"], snap["shape"]["NBF"]
    assert thu["block_height_m"] == 36.8 and thu["width_m"] == round(60 / 100 * 68, 1) and thu["phase"] == "attacking"
    assert thu["lines"] == {"DF": 21.0, "MF": 42.0, "FW": 63.0}
    assert nbf["block_height_m"] == 22.8 and nbf["phase"] == "defending" and nbf["lines"]["FW"] == 38.9
    # pressure: NBF-05 at x 63 is 3.15 m from the carrier at x 60 (same y); NBF-04 at x 70 is 10.5 m away
    assert snap["pressure"] == {"carrier": "THU-05", "team_in_possession": "THU", "opponents_within_8m": 1, "under_pressure": False}
    assert snap["press_index"] == {"THU": None, "NBF": 1.0}
    heat = snap["players"]["NBF-02"]["heat"]
    assert len(heat) == 96 and sum(heat) == 1
    # NBF-02 at absolute (90, 30) is team-frame x 10 -> column 1, y 30 -> row 2 (both halves add up in team frame)
    assert heat[2 * 12 + 1] == 1
    assert snap["shape_last_10"]["THU"]["block_height_m"] == 36.8 and snap["shape_last_10"]["THU"]["delta_vs_match_m"] == 0.0
    assert snap["block_series"] == [{"period": 1, "minute": 3, "THU": 36.8, "NBF": 22.8}]


def test_phase_follows_the_last_side_in_possession_when_the_ball_is_loose():
    state = MatchState(_meta())
    state.apply({"event_id": 1, "period": 1, "minute": 0, "second": 0, "type": "kickoff", "team_id": "THU", "home_attacking_right": True})
    players = {"THU-01": [5, 50], "THU-02": [20, 20], "THU-03": [20, 80], "THU-04": [40, 50], "THU-05": [60, 50],
               "NBF-01": [95, 50], "NBF-02": [90, 30], "NBF-03": [90, 70], "NBF-04": [70, 50], "NBF-05": [63, 50]}
    state.apply_frame({"kind": "frame", "period": 1, "minute": 3, "second": 0, "carrier": "THU-05", "players": players})
    state.apply_frame({"kind": "frame", "period": 1, "minute": 3, "second": 1, "carrier": None, "players": players})
    snap = state.snapshot()
    assert snap["shape"]["THU"]["phase"] == "attacking" and snap["shape"]["NBF"]["phase"] == "defending"
    assert snap["pressure"] is None  # no carrier, nobody to press
    fresh = MatchState(_meta())
    fresh.apply_frame({"kind": "frame", "period": 1, "minute": 0, "second": 0, "carrier": None, "players": players})
    assert {s["phase"] for s in fresh.snapshot()["shape"].values()} == {"transition"}  # only before the first carrier


def test_snapshot_without_frames_has_no_shape_or_heat(meta, events):
    state = MatchState(meta)
    for e in events[:50]:
        state.apply(e)
    snap = state.snapshot()
    assert snap["shape"] is None and snap["pressure"] is None and snap["press_index"] is None
    assert snap["block_series"] == []
    assert "heat" not in next(iter(snap["players"].values()))


def test_frames_through_the_interpreter_give_a_deeper_block_when_defending(events, meta):
    state = MatchState(meta)
    att, dfn = [], []
    both_transition, seen_carrier = 0, False
    for item in merge_timeline(events, build_tracking(events, meta)):
        if item.get("kind") == "frame":
            state.apply_frame(item)
            seen_carrier = seen_carrier or item.get("carrier") is not None
            sh = state.snapshot()["shape"]
            if seen_carrier and all(s["phase"] == "transition" for s in sh.values()):
                both_transition += 1
            for tid, s in sh.items():
                (att if s["phase"] == "attacking" else dfn if s["phase"] == "defending" else []).append(s["block_height_m"])
        else:
            state.apply(item)
    assert both_transition == 0  # the ball in flight keeps the last side's phase
    margin = sum(att) / len(att) - sum(dfn) / len(dfn)
    assert margin > 1, margin  # the block sits higher with the ball than without it
    snap = state.snapshot()
    assert sum(snap["players"]["THU-01"]["heat"]) > 5000  # the keeper plays the whole match
    # block height per minute, period-aware: first-half stoppage (1, 45+) and the second-half restart (2, 45) both exist
    series = snap["block_series"]
    keys = [(p["period"], p["minute"]) for p in series]
    assert keys == sorted(keys) and len(keys) == len(set(keys)) and len(series) > 85
    assert (1, 45) in keys and (2, 45) in keys
    assert all(10 <= p["THU"] <= 80 and 10 <= p["NBF"] <= 80 for p in series)


# ---------------------------------------------------------------- websocket

@pytest.fixture()
def plain_client(data_dir):
    with TestClient(create_app(data_dir=data_dir, enable_agents=False, cache=False)) as c:
        yield c


def test_frames_interleave_in_clock_order_without_touching_events_or_risk_messages(plain_client, meta, events):
    base = f"/ws/matches/{meta['match_id']}?speed=0"
    with plain_client.websocket_connect(base) as ws:
        ws.receive_json()
        without = _drain(ws)
    with plain_client.websocket_connect(base + "&frames=all") as ws:
        ws.receive_json()
        with_frames = _drain(ws)
    frames = [m for m in with_frames if m["kind"] == "frame"]
    assert len(frames) > 5000 and all(len(f["players"]) == 22 for f in frames[:50])
    evs = [m["event"]["event_id"] for m in with_frames if m["kind"] == "event"]
    assert evs == [e["event_id"] for e in events]
    assert sum(1 for m in without if m["kind"] == "risk") == sum(1 for m in with_frames if m["kind"] == "risk")
    # clock order: a frame never precedes an event of the same second
    last = None
    for m in with_frames:
        if m["kind"] not in ("event", "frame"):
            continue
        item = m["event"] if m["kind"] == "event" else m
        key = (item["period"], item["minute"] * 60 + item["second"], 1 if m["kind"] == "frame" else 0)
        assert last is None or key >= last
        last = key
    assert not any(m["kind"] == "frame" for m in without)  # speed 0 sends none by default
    end = with_frames[-1]
    assert end["state"]["shape"] and end["state"]["press_index"]


def test_frames_can_be_switched_off(plain_client, meta):
    with plain_client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&frames=0") as ws:
        ws.receive_json()
        msgs = _drain(ws)
    assert not any(m["kind"] == "frame" for m in msgs)


# ---------------------------------------------------------------- mcp tools

def test_tracking_tools_read_shape_and_heat_from_the_registry(events, meta):
    registry = LiveStateRegistry()
    tools = MatchTools(registry)
    state = MatchState(meta)
    for item in merge_timeline(events, build_tracking(events, meta)):
        state.apply_frame(item) if item.get("kind") == "frame" else state.apply(item)
    registry.update(meta["match_id"], meta, state.snapshot())
    shape = tools.get_team_shape(meta["match_id"])
    assert set(shape["shape"]) == {"THU", "NBF"} and shape["shape"]["THU"]["team"] == "Thames United"
    assert shape["press_index"]["THU"] is not None and "positional model" in shape["note"]
    heat = tools.get_player_heatmap(meta["match_id"], "THU-17")
    assert heat["frames"] > 1000 and len(heat["grid"]) == 96 and abs(sum(heat["time_by_third"].values()) - 1) < 0.02
    assert "channel of the" in heat["reading"]
    with pytest.raises(KeyError):
        tools.get_player_heatmap(meta["match_id"], "THU-99")
    assert any(fn.__name__ == "get_team_shape" for fn in tools.as_functions())
