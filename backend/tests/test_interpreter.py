"""Interpreter agent: pure-Python live stats from the event stream."""

from __future__ import annotations

import itertools
import json

import pytest

from matchmind.interpreter.state import MatchState, acwr, risk_band


@pytest.fixture(scope="module")
def final_state(match):
    events, meta = match
    state = MatchState(meta)
    for e in events:
        state.apply(e)
    return state


# ---------------------------------------------------------------- team stats

def test_team_totals_match_generator_summary(final_state, meta):
    snap = final_state.snapshot()
    for tid, ref in meta["summary"].items():
        team = snap["teams"][tid]
        assert team["passes"] == ref["passes"]
        assert team["shots"] == ref["shots"]
        assert team["xg"] == pytest.approx(ref["xg"], abs=0.01)
        assert team["goals"] == ref["goals"]
        assert team["pressures"] == ref["pressures"]
        assert team["tackles"] == ref["tackles"]
        assert team["pass_accuracy"] == pytest.approx(ref["pass_accuracy"], abs=0.001)
        assert team["possession_pct"] == pytest.approx(ref["possession_pct"], abs=0.1)


def test_score_and_clock_track_the_stream(final_state, meta):
    snap = final_state.snapshot()
    assert snap["score"] == meta["score"]
    assert snap["period"] == 2
    assert snap["minute"] >= 90
    assert snap["last_event_id"] == meta["n_events"]


def test_shots_on_target_counts_goals_and_saves(final_state, events):
    snap = final_state.snapshot()
    for tid in snap["teams"]:
        expected = sum(
            1 for e in events
            if e["type"] == "shot" and e["team_id"] == tid and e["outcome"] in ("goal", "saved")
        )
        assert snap["teams"][tid]["shots_on_target"] == expected


# ---------------------------------------------------------------- xG race

def test_xg_race_marks_the_goals(final_state):
    snap = final_state.snapshot()
    assert sum(1 for p in snap["xg_race"] if p["goal"]) == sum(snap["score"].values())
    assert all(isinstance(p["goal"], bool) for p in snap["xg_race"])


def test_xg_race_is_cumulative_and_ends_at_totals(final_state, meta):
    race = final_state.snapshot()["xg_race"]
    home, away = meta["teams"].keys()
    assert race[0]["minute"] >= 0
    for a, b in itertools.pairwise(race):
        assert b[home] >= a[home] and b[away] >= a[away]
        # minutes restart at 45 for the second half, so order by (period, minute)
        assert (b["period"], b["minute"]) >= (a["period"], a["minute"])
    assert race[-1][home] == pytest.approx(meta["summary"][home]["xg"], abs=0.01)
    assert race[-1][away] == pytest.approx(meta["summary"][away]["xg"], abs=0.01)


# ---------------------------------------------------------------- momentum

def _shot(eid, minute, second, team, xg=0.3, outcome="saved"):
    return {
        "event_id": eid, "period": 1, "minute": minute, "second": second,
        "clock": f"{minute:02d}:{second:02d}", "type": "shot", "team_id": team,
        "player_id": f"{team}-19", "player_name": "X", "x": 90.0, "y": 50.0,
        "distance_m": 10.0, "xg": xg, "shot_speed_kmh": 90.0, "outcome": outcome,
        "assist_player_id": None, "assist_player_name": None,
    }


def test_momentum_is_bounded_and_swings_toward_the_attacking_team(meta):
    state = MatchState(meta)
    home, away = meta["teams"].keys()
    for i in range(1, 8):
        state.apply(_shot(i, 10, i * 5, home))
    m = state.snapshot()["momentum"]
    assert -1.0 <= m <= 1.0 and m > 0.3
    state.apply({
        "event_id": 99, "period": 1, "minute": 12, "second": 0, "clock": "12:00",
        "type": "goal", "team_id": away, "player_id": f"{away}-19", "player_name": "Y",
        "assist_player_id": None, "assist_player_name": None, "score": {home: 0, away: 1},
    })
    assert state.snapshot()["momentum"] < m


def test_momentum_series_has_one_point_per_minute_seen(final_state):
    series = final_state.snapshot()["momentum_series"]
    keys = [(p["period"], p["minute"]) for p in series]
    assert keys == sorted(set(keys))
    assert keys[0] == (1, 0) and keys[-1] >= (2, 90)
    assert all(-1.0 <= p["value"] <= 1.0 for p in series)


# ---------------------------------------------------------------- ACWR / players

def test_acwr_is_acute_over_chronic_daily_mean():
    history = [{"day": d, "distance_m": 5000.0, "hsr_m": 400.0} for d in range(-28, 0)]
    # acute = (6 days + today) / 7 ; chronic = (27 days + today) / 28
    assert acwr(history, today_distance_m=0.0) == pytest.approx((6 * 5000 / 7) / (27 * 5000 / 28), abs=0.001)
    assert acwr(history, today_distance_m=5000.0) == pytest.approx(1.0, abs=0.001)
    # a heavy day today: acute (30000+12000)/7 over chronic (135000+12000)/28
    assert acwr(history, today_distance_m=12000.0) == pytest.approx(6000 / 5250, abs=0.001)


def test_acwr_handles_empty_history():
    assert acwr([], today_distance_m=5000.0) == 1.0
    assert acwr([{"day": -1, "distance_m": 0.0, "hsr_m": 0.0}], today_distance_m=0.0) == 1.0


def test_risk_bands():
    assert risk_band(0.5) == "undertrained"
    assert risk_band(1.0) == "optimal"
    assert risk_band(1.35) == "elevated"
    assert risk_band(1.7) == "high"


def test_player_workload_follows_physical_samples(final_state, events):
    players = final_state.snapshot()["players"]
    last = {}
    for e in events:
        if e["type"] == "physical_sample":
            last[e["player_id"]] = e
    assert last, "fixture match has no physical samples"
    for pid, e in last.items():
        p = players[pid]
        assert p["distance_m"] == e["distance_m"]
        assert p["sprints"] == e["sprints"]
        assert p["minutes_played"] == e["minutes_played"]
        assert p["top_speed_kmh"] == e["top_speed_kmh"]
        assert 0.0 < p["acwr_live"] < 5.0
        assert p["risk_band"] in {"undertrained", "optimal", "elevated", "high"}


def test_effort_ratio_tracks_metres_per_minute_against_the_position_norm(final_state, events):
    players = final_state.snapshot()["players"]
    samples = [e for e in events if e["type"] == "physical_sample" and e["player_id"] == "THU-01"]
    last = samples[-1]
    p = players["THU-01"]
    assert p["effort_ratio"] == pytest.approx((last["distance_m"] / last["minutes_played"]) / 45.0, abs=0.01)
    prev = samples[-2]
    recent = (last["distance_m"] - prev["distance_m"]) / (last["minutes_played"] - prev["minutes_played"])
    assert p["effort_ratio_recent"] == pytest.approx(recent / 45.0, abs=0.01)
    assert all(0.3 < q["effort_ratio"] < 1.5 for q in players.values() if q["minutes_played"] > 0)


def test_injury_concerns_are_counted_per_player(final_state, events):
    players = final_state.snapshot()["players"]
    concerns = {}
    for e in events:
        if e["type"] == "injury_concern":
            concerns[e["player_id"]] = concerns.get(e["player_id"], 0) + 1
    assert concerns, "fixture match has no injury_concern events"
    for pid, n in concerns.items():
        assert players[pid]["injury_concerns"] == n


def test_snapshot_never_exposes_latent_state(final_state):
    blob = json.dumps(final_state.snapshot())
    assert "fatigue" not in blob
    assert "susceptib" not in blob


def test_risk_alerts_list_on_pitch_players_in_elevated_or_high_band(final_state):
    snap = final_state.snapshot()
    for alert in snap["risk_alerts"]:
        assert alert["risk_band"] in {"elevated", "high"}
        assert snap["players"][alert["player_id"]]["acwr_live"] == alert["acwr_live"]
    expected = {
        p["player_id"] for p in snap["players"].values()
        if p["risk_band"] in {"elevated", "high"} and p["minutes_played"] > 0
    }
    assert {a["player_id"] for a in snap["risk_alerts"]} == expected


def test_fan_counters_per_player_match_the_event_stream(final_state, events):
    from collections import Counter
    snap = final_state.snapshot()
    players = snap["players"]
    touches, shots, goals, assists, duels = Counter(), Counter(), Counter(), Counter(), Counter()
    for e in events:
        pid = e.get("player_id")
        if e["type"] in ("pass", "shot", "tackle", "interception"):
            touches[pid] += 1
        if e["type"] == "shot":
            shots[pid] += 1
        if e["type"] == "goal":
            goals[pid] += 1
            if e.get("assist_player_id"):
                assists[e["assist_player_id"]] += 1
        if e["type"] in ("tackle", "interception"):
            duels[pid] += 1
    for pid, p in players.items():
        assert (p["touches"], p["shots"], p["goals"], p["assists"], p["duels_won"]) == (touches[pid], shots[pid], goals[pid], assists[pid], duels[pid])
    assert sum(p["goals"] for p in players.values()) == sum(snap["score"].values())
    assert any(p["touches"] > 20 for p in players.values())
