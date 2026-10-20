"""Simulator invariants the downstream agents rely on."""

from __future__ import annotations

import json


def test_second_half_kickoff_restarts_the_clock_at_45_00(events):
    kick = next(e for e in events if e["type"] == "second_half_kickoff")
    assert (kick["period"], kick["minute"], kick["second"]) == (2, 45, 0)
    assert kick["clock"] == "45:00"


def test_clock_never_runs_backwards_within_a_period(events):
    for a, b in zip(events, events[1:]):
        if a["period"] != b["period"]:
            continue
        assert b["minute"] >= a["minute"], (a["event_id"], b["event_id"])


def test_events_never_leak_latent_player_state(events, meta):
    blob = json.dumps(events) + json.dumps(meta)
    assert "fatigue" not in blob
    assert "susceptib" not in blob
