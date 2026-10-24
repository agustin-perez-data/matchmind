"""Synthetic positional data: consistent with the events, deterministic, physically bounded, and never
touching the engine's events."""

from __future__ import annotations

import json
import math

import pytest

from matchmind.generate_match import generate
from matchmind.interpreter.state import MatchState
from matchmind.sim.tracking import ANCHORS, PITCH_LENGTH_M, PITCH_WIDTH_M, build_tracking


@pytest.fixture(scope="module")
def frames(events, meta):
    return build_tracking(events, meta)


def _t(e):
    return int(e["minute"]) * 60 + int(e["second"])


def _c(v):
    return min(100.0, max(0.0, float(v)))  # the engine lets a backward pass end just off the pitch; the ball is clamped


def _speed(a, b):
    return math.hypot((b[0] - a[0]) / 100 * PITCH_LENGTH_M, (b[1] - a[1]) / 100 * PITCH_WIDTH_M)


def test_building_tracking_never_changes_the_events(events, meta):
    before = json.dumps(events, sort_keys=True)
    build_tracking(events, meta)
    assert json.dumps(events, sort_keys=True) == before
    again, _ = generate("THU", "NBF", seed=42)
    assert json.dumps(again, sort_keys=True) == before  # the engine does not know tracking exists


def test_frames_are_deterministic(events, meta, frames):
    assert build_tracking(events, meta) == frames
    other = build_tracking(events, {**meta, "seed": 99})
    assert [f["ball"] for f in other] == [f["ball"] for f in frames]  # the ball comes from the events
    assert other != frames  # the players' noise comes from the tracking seed


def test_one_frame_per_second_per_period_and_the_second_half_restarts_at_45(frames, events):
    per_period = {}
    for f in frames:
        per_period.setdefault(f["period"], []).append(f["minute"] * 60 + f["second"])
    assert set(per_period) == {1, 2}
    for period, ts in per_period.items():
        assert ts == list(range(ts[0], ts[-1] + 1))  # strictly increasing, no gaps
    half_time = next(e for e in events if e["type"] == "half_time")
    full_time = next(e for e in events if e["type"] == "full_time")
    assert per_period[1][0] == 0 and per_period[1][-1] == _t(half_time)
    assert per_period[2][0] == 45 * 60 and per_period[2][-1] == _t(full_time)


def test_every_frame_has_the_eleven_who_are_on_the_pitch(frames, events, meta):
    state = MatchState(meta)
    by_t = {(f["period"], f["minute"] * 60 + f["second"]): f for f in frames}
    checked = 0
    for e in events:
        state.apply(e)
        if e["type"] in ("substitution", "half_time", "kickoff", "second_half_kickoff"):
            f = by_t.get((e["period"], _t(e) + (1 if e["type"] == "substitution" else 0)))  # a sub shows the second after
            if f is None:
                continue
            on = {pid for pid, p in state.snapshot()["players"].items() if p["on_pitch"]}
            assert set(f["players"]) == on
            checked += 1
    assert checked >= 4
    for f in frames:
        assert len(f["players"]) == 22
        for x, y in f["players"].values():
            assert 0 <= x <= 100 and 0 <= y <= 100


def test_the_ball_and_the_carrier_match_the_last_placed_event_of_each_second(frames, events):
    by_t = {(f["period"], f["minute"] * 60 + f["second"]): f for f in frames}
    last_at = {}
    for e in events:
        if e["type"] in ("pass", "shot", "tackle", "interception", "foul"):
            last_at[(e["period"], _t(e))] = e
    checked = 0
    for key, e in last_at.items():
        f = by_t[key]
        assert abs(f["ball"][0] - _c(e["x"])) <= 0.11 and abs(f["ball"][1] - _c(e["y"])) <= 0.11, (key, e["type"])
        assert f["carrier"] == e["player_id"]
        checked += 1
    assert checked > 500


def test_a_completed_pass_lands_on_its_receiver(frames, events):
    by_t = {(f["period"], f["minute"] * 60 + f["second"]): f for f in frames}
    placed = [e for e in events if e["type"] in ("pass", "shot", "tackle", "interception", "foul")]
    hits = 0
    for i, e in enumerate(placed[:-1]):
        nxt = placed[i + 1]
        if e["type"] != "pass" or e["outcome"] != "complete" or nxt["period"] != e["period"]:
            continue
        gap = _t(nxt) - _t(e)
        flight = max(1, min(3, round(e["distance_m"] / 15)))
        if gap <= flight:
            continue  # the next event comes before the ball would have landed: the frame shows that event
        f = by_t[(e["period"], _t(e) + flight)]
        assert f["carrier"] == e["receiver_id"]
        assert abs(f["ball"][0] - _c(e["end_x"])) <= 0.11 and abs(f["ball"][1] - _c(e["end_y"])) <= 0.11
        hits += 1
    assert hits > 100


def test_the_carrier_is_on_the_ball_and_nobody_is_faster_than_a_sprint(frames):
    prev = None
    sprint_violations = 0
    for f in frames:
        if f["carrier"]:
            cx, cy = f["players"][f["carrier"]]
            assert abs(cx - f["ball"][0]) <= 0.11 and abs(cy - f["ball"][1]) <= 0.11
        if prev and prev["period"] == f["period"]:
            for pid, pos in f["players"].items():
                if pid in prev["players"] and pid not in (f["carrier"], prev["carrier"]):
                    if _speed(prev["players"][pid], pos) > 12.2:  # 12 m/s plus coordinate rounding
                        sprint_violations += 1
        prev = f
    assert sprint_violations == 0


def test_a_substitute_takes_over_the_slot(frames, events, meta):
    sub = next(e for e in events if e["type"] == "substitution")
    t = _t(sub)
    before = next(f for f in frames if f["period"] == sub["period"] and f["minute"] * 60 + f["second"] == t)
    after = next(f for f in frames if f["period"] == sub["period"] and f["minute"] * 60 + f["second"] == t + 1)
    assert sub["player_off_id"] in before["players"] and sub["player_off_id"] not in after["players"]
    assert sub["player_on_id"] in after["players"] and sub["player_on_id"] not in before["players"]
    ox, oy = before["players"][sub["player_off_id"]]
    nx, ny = after["players"][sub["player_on_id"]]
    assert _speed((ox, oy), (nx, ny)) <= 12.2  # he starts where the other left


def test_kickoff_frames_start_from_the_formation(frames, meta):
    first = frames[0]  # the first chain may start in the very first second, so only the shape is asserted
    home, away = meta["home_id"], meta["away_id"]
    hx = [x for pid, (x, _) in first["players"].items() if pid.startswith(home)]
    ax = [x for pid, (x, _) in first["players"].items() if pid.startswith(away)]
    assert min(hx) < 10 and max(ax) > 90  # keepers in their goals: home attacks right, away left
    assert sum(hx) / len(hx) < sum(ax) / len(ax)  # the two sides on their own halves on average
    assert ANCHORS["GK"][0][0] < ANCHORS["DF"][0][0] < ANCHORS["MF"][0][0] < ANCHORS["FW"][0][0]


def test_frames_are_compact_and_json_safe(frames):
    assert len(json.dumps(frames[100])) < 900
    assert all(len(str(v)) <= 5 for v in frames[100]["ball"])  # one decimal
