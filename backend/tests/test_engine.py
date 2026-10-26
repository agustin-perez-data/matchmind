"""Simulator invariants the downstream agents rely on."""

from __future__ import annotations

import itertools
import json


def test_second_half_kickoff_restarts_the_clock_at_45_00(events):
    kick = next(e for e in events if e["type"] == "second_half_kickoff")
    assert (kick["period"], kick["minute"], kick["second"]) == (2, 45, 0)
    assert kick["clock"] == "45:00"


def test_clock_never_runs_backwards_within_a_period(events):
    for a, b in itertools.pairwise(events):
        if a["period"] != b["period"]:
            continue
        assert b["minute"] >= a["minute"], (a["event_id"], b["event_id"])


def test_starters_are_the_eleven_who_kicked_off_not_everyone_who_played(meta, events):
    for tid, team in meta["teams"].items():
        starters = [p["player_id"] for p in team["players"] if p["starter"]]
        assert len(starters) == 11
        came_on = {e["player_on_id"] for e in events if e["type"] == "substitution" and e["team_id"] == tid}
        assert not (set(starters) & came_on)


def test_injury_model_never_changes_the_rest_of_the_match():
    """Knocks are drawn from the latent state, but passes, shots and goals must not depend on it."""
    from matchmind.sim.engine import MatchSimulator
    from matchmind.sim.league import build_league

    def play(susceptibility: float) -> list[dict]:
        league = build_league(7)
        home, away = league["THU"], league["NBF"]
        for p in home.players + away.players:
            p.injury_susceptibility = susceptibility
        return MatchSimulator(home, away, seed=42).run()["events"]

    calm, fragile = play(0.0), play(1.0)
    assert not [e for e in calm if e["type"] == "injury_concern"]
    assert [e for e in fragile if e["type"] == "injury_concern"]
    strip = lambda evs: [{k: v for k, v in e.items() if k != "event_id"} for e in evs if e["type"] != "injury_concern"]
    assert strip(calm) == strip(fragile)


def test_the_ball_is_continuous_inside_a_possession_chain(events):
    """A completed pass ends where the next pass (or the shot) of the same move starts."""
    checked, prev = 0, None
    for e in events:
        if e["type"] == "pressure":
            continue  # pressing happens between two touches of the same move
        if e["type"] in ("pass", "shot") and prev is not None and prev["outcome"] == "complete":
            if e["type"] == "pass":
                assert (e["x"], e["y"]) == (prev["end_x"], prev["end_y"]), (prev["event_id"], e["event_id"])
            else:
                assert e["x"] == prev["end_x"], (prev["event_id"], e["event_id"])
                assert abs(e["y"] - min(75.0, max(25.0, prev["end_y"]))) < 0.11
            checked += 1
        prev = e if e["type"] == "pass" else None  # anything else ends the move
    assert checked > 300


def test_nobody_assists_their_own_shot(events):
    shots = [e for e in events if e["type"] in ("shot", "goal")]
    assert shots
    assert all(e["assist_player_id"] != e["player_id"] for e in shots)


def test_events_never_leak_latent_player_state(events, meta):
    blob = json.dumps(events) + json.dumps(meta)
    assert "fatigue" not in blob
    assert "susceptib" not in blob
