"""Rolling last-10-minute stats, game state and the Analyst's track record in the moment context."""

from __future__ import annotations

from matchmind.agents.judge import ForecastLedger
from matchmind.agents.moments import build_moment_context, detect_key_moment, game_state
from matchmind.generate_match import generate
from matchmind.interpreter.state import MatchState


def _state_at(events, meta, minute):
    state = MatchState(meta)
    for e in events:
        if (int(e["minute"]) > minute and e["period"] == 2) or (e["period"] == 1 and int(e["minute"]) > minute):
            break
        state.apply(e)
    return state


def test_recent_window_counts_only_the_last_ten_minutes():
    events, meta = generate("THU", "NBF", seed=42)
    state = MatchState(meta)
    for e in events:
        state.apply(e)
        if state.minute >= 30:
            break
    recent = state.recent(10)
    assert recent["minutes"] == 10 and 19 <= recent["from_minute"] <= 20
    full = state.snapshot()["teams"]
    for tid in (meta["home_id"], meta["away_id"]):
        assert 0 <= recent["teams"][tid]["shots"] <= full[tid]["shots"]
        assert 0 <= recent["teams"][tid]["xg"] <= full[tid]["xg"] + 1e-6
        assert recent["teams"][tid]["passes"] < full[tid]["passes"]  # the first 20 minutes are excluded
    shots_in_window = [e for e in events if e["type"] == "shot" and e["period"] == 1 and 20 <= int(e["minute"]) <= 30
                       and e["event_id"] <= state.last_event_id]
    assert sum(t["shots"] for t in recent["teams"].values()) == len(shots_in_window)
    assert all(s["shots"] > 0 for s in recent["shooters"]) and len(recent["shooters"]) <= 4


def test_recent_window_before_ten_minutes_is_everything_so_far():
    events, meta = generate("THU", "NBF", seed=42)
    state = MatchState(meta)
    for e in events:
        state.apply(e)
        if state.minute >= 5:
            break
    recent = state.recent(10)
    assert recent["from_minute"] == 0
    assert recent["teams"][meta["home_id"]]["passes"] == state.snapshot()["teams"][meta["home_id"]]["passes"]


def test_top_shooters_are_sorted_and_named():
    events, meta = generate("THU", "NBF", seed=42)
    state = MatchState(meta)
    for e in events:
        state.apply(e)
    top = state.top_shooters()
    assert top and top[0]["shots"] >= top[-1]["shots"] and all({"player_id", "name", "team_id", "shots"} <= set(s) for s in top)
    shots = {}
    for e in events:
        if e["type"] == "shot":
            shots[e["player_id"]] = shots.get(e["player_id"], 0) + 1
    assert top[0]["shots"] == max(shots.values())


def test_game_state_reads_who_is_chasing_and_time_left():
    s = {"home_id": "THU", "away_id": "NBF", "score": {"THU": 0, "NBF": 1}, "minute": 70, "period": 2}
    g = game_state(s)
    assert g == {"leading": "NBF", "trailing": "THU", "margin": 1, "minutes_remaining": 23, "half_time_break_ahead": False}
    level = game_state({**s, "score": {"THU": 1, "NBF": 1}, "minute": 42, "period": 1})
    assert level["leading"] is None and level["trailing"] is None and level["half_time_break_ahead"] is True


def test_moment_context_carries_the_window_the_game_state_and_the_record():
    events, meta = generate("THU", "NBF", seed=42)
    state = MatchState(meta)
    moment = None
    for e in events:
        state.apply(e)
        if e["type"] in MatchState.SNAPSHOT_TYPES and state.minute > 15:
            moment = detect_key_moment(e, state.snapshot())
            if moment is not None:
                break
    assert moment is not None
    ledger = ForecastLedger()
    ledger.record({"event_id": 1, "scores": {"overall": 0.4, "dominance": 0.0, "goal": 0.8, "watch": None},
                   "naive_scores": {"overall": 0.6, "dominance": 1.0, "goal": 0.8, "watch": None}})
    ledger.remember({"event_id": 1, "issued_clock": "10:00", "forecast": {"claim": "Thames keep the ball and create"},
                     "facts": {"xg_gained": {"THU": 0.0, "NBF": 0.3}, "goals": []},
                     "verdict": {"verdict": "missed", "lesson": "possession is not chances"}})
    ctx = build_moment_context(moment, state.snapshot(), meta, track_record=ledger.track_record())
    assert ctx["last_10_minutes"]["minutes"] == 10 and set(ctx["last_10_minutes"]["teams"]) == {"THU", "NBF"}
    assert ctx["game_state"]["minutes_remaining"] > 0 and "top_shooters" in ctx
    rec = ctx["analyst_track_record"]
    assert rec["forecasts_graded"] == 1 and rec["dominance_calls_right"] == "0 of 1"
    assert rec["recent_verdicts"][0]["lesson"] == "possession is not chances" and rec["recent_verdicts"][0]["goals_in_window"] == 0
    assert build_moment_context(moment, state.snapshot(), meta)["analyst_track_record"] is None
    assert ForecastLedger().track_record() is None
