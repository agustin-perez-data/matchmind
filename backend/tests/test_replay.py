"""Replay scheduling: turn a JSONL event list into a timed live feed."""

from __future__ import annotations

import json

import pytest

from matchmind.stream.replay import delays, event_seconds, load_events


def _ev(period, minute, second, eid=1):
    return {"event_id": eid, "period": period, "minute": minute, "second": second, "type": "pass"}


def test_event_seconds_is_absolute_match_time():
    assert event_seconds(_ev(1, 0, 0)) == 0
    assert event_seconds(_ev(1, 12, 30)) == 12 * 60 + 30
    assert event_seconds(_ev(2, 46, 5)) == 46 * 60 + 5


def test_delays_follow_clock_gaps_divided_by_speed():
    evs = [_ev(1, 0, 0), _ev(1, 0, 4), _ev(1, 0, 10), _ev(1, 1, 0)]
    assert delays(evs, speed=1.0) == [0.0, 4.0, 6.0, 50.0]
    assert delays(evs, speed=10.0) == [0.0, 0.4, 0.6, 5.0]


def test_delays_never_negative_and_zero_speed_means_instant():
    evs = [_ev(1, 0, 10), _ev(1, 0, 5)]  # clock goes backwards within a minute
    assert delays(evs, speed=1.0) == [0.0, 0.0]
    assert delays(evs, speed=0) == [0.0, 0.0]


def test_half_time_break_is_not_replayed_in_real_time():
    """45:40 -> 45:00 (2nd half restarts at minute 45) must not stall or go negative."""
    evs = [_ev(1, 45, 40), _ev(2, 45, 0), _ev(2, 45, 8)]
    d = delays(evs, speed=1.0)
    assert d[0] == 0.0
    assert d[1] == 0.0
    assert d[2] == 8.0


def test_load_events_reads_jsonl_in_order(tmp_path):
    p = tmp_path / "m_events.jsonl"
    rows = [_ev(1, 0, 0, 1), _ev(1, 0, 3, 2)]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert load_events(p) == rows


def test_load_events_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_events(tmp_path / "nope.jsonl")
