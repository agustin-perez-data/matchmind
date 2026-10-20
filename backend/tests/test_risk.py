"""Load & Risk Monitor: risk windows from observables, scored against injury_concern events."""

from __future__ import annotations

import json

import pytest

from matchmind.interpreter.state import MatchState
from matchmind.risk.monitor import NaiveMinutesBaseline, RiskModel, RiskMonitor, Track


def _player(minutes=0, acwr=1.0, spm=0.2, concerns=0, effort=1.0):
    return {"minutes_played": minutes, "acwr_live": acwr, "sprints_per_min": spm,
            "injury_concerns": concerns, "effort_ratio_recent": effort}


# ---------------------------------------------------------------- model

def test_hazard_is_a_probability_increasing_with_minutes_acwr_and_effort_drop():
    m = RiskModel()
    fresh, late = m.hazard(_player(5, 1.0)), m.hazard(_player(85, 1.0))
    assert 0.0 <= fresh < late <= 1.0
    assert m.hazard(_player(60, 1.5)) > m.hazard(_player(60, 1.0)) > m.hazard(_player(60, 0.7))
    assert m.hazard(_player(60, 1.0, concerns=1)) > m.hazard(_player(60, 1.0, concerns=0))
    assert m.hazard(_player(60, 1.0, effort=0.8)) > m.hazard(_player(60, 1.0, effort=1.0))


def test_baseline_only_looks_at_minutes():
    b = NaiveMinutesBaseline(after_minute=60)
    assert b.hazard(_player(59, 1.9)) < b.threshold <= b.hazard(_player(60, 0.5))
    assert b.hazard(_player(30)) < b.hazard(_player(45)) < b.hazard(_player(90)) == 1.0


# ---------------------------------------------------------------- windows + scoring (synthetic)

class _Dial:
    """Test model: the hazard is whatever the observation says it is."""

    def hazard(self, p):
        return p["h"]


def test_window_opens_once_renews_while_hot_and_expires_after_horizon():
    t = Track(model=_Dial(), horizon_min=15, threshold=0.5)
    assert t.update("P1", 59, {"h": 0.2}) is None
    opened = t.update("P1", 60, {"h": 0.6})
    assert opened and opened["player_id"] == "P1" and opened["open_minute"] == 60 and opened["expires_minute"] == 75
    assert opened["level"] == "elevated"
    assert t.update("P1", 64, {"h": 0.8}) is None  # renewal, not a new alert
    assert t.active(64)[0]["expires_minute"] == 79
    t.update("P1", 70, {"h": 0.1})  # cooled down: no renewal
    assert t.active(79) and t.active(80) == []  # expires 15 minutes after the last hot observation


def test_scoring_true_alert_lead_time_and_missed_concern():
    t = Track(model=NaiveMinutesBaseline(after_minute=50), horizon_min=15, threshold=0.5)
    t.update("P1", 50, _player(50))  # alert at 50 -> window until 65
    rec = t.concern("P1", 58)
    assert {k: rec[k] for k in ("player_id", "minute", "covered", "lead_minutes")} == {
        "player_id": "P1", "minute": 58, "covered": True, "lead_minutes": 8}
    assert t.concern("P2", 58)["covered"] is False  # no window for P2 -> missed
    t.update("P3", 50, _player(50))  # alert never followed by a concern -> false alert
    sc = t.scorecard()
    assert sc["alerts"] == 2 and sc["true_alerts"] == 1 and sc["precision"] == 0.5
    assert sc["concerns"] == 2 and sc["covered"] == 1 and sc["recall"] == 0.5
    assert sc["mean_lead_minutes"] == 8.0


def test_concerns_are_ranked_against_the_other_players_on_the_pitch():
    t = Track(model=_Dial(), horizon_min=15, threshold=0.9)  # threshold high: no windows, pure ranking
    for pid, h in (("A", 0.1), ("B", 0.5), ("C", 0.3), ("D", 0.8)):
        t.update(pid, 60, {"h": h})
    rec = t.concern("C", 62)
    assert rec["rank"] == 3 and rec["ranked_players"] == 4  # D, B, C, A
    assert t.concern("D", 63)["rank"] == 1
    sc = t.scorecard()
    assert sc["top3_hits"] == 2 and sc["top3_rate"] == 1.0
    assert sc["mean_rank_pct"] == pytest.approx(((3 - 1) / 3 + 0.0) / 2 * 100, abs=0.1)
    assert sc["top3_random_rate"] == pytest.approx(3 / 4, abs=0.001)


def test_stale_observations_drop_out_of_the_ranking():
    t = Track(model=_Dial(), horizon_min=15, threshold=0.9, ranking_window_min=6)
    t.update("A", 40, {"h": 0.9})
    t.update("B", 60, {"h": 0.2})
    assert t.concern("B", 61)["ranked_players"] == 1  # A was last seen 21 minutes ago (subbed off)


def test_a_window_is_credited_at_most_once():
    t = Track(model=NaiveMinutesBaseline(after_minute=50), horizon_min=15, threshold=0.5)
    t.update("P1", 50, _player(50))
    t.concern("P1", 52)
    t.concern("P1", 53)
    sc = t.scorecard()
    assert sc["alerts"] == 1 and sc["true_alerts"] == 1 and sc["covered"] == 2


# ---------------------------------------------------------------- monitor on the demo match

@pytest.fixture(scope="module")
def monitored(match):
    events, meta = match
    state, monitor = MatchState(meta), RiskMonitor(meta)
    alerts = []
    for e in events:
        state.apply(e)
        alerts.extend(monitor.observe(e, state.snapshot()))
    return monitor, alerts


def test_monitor_raises_alerts_and_scores_model_and_baseline(monitored, events):
    monitor, alerts = monitored
    assert alerts, "no risk windows opened in the demo match"
    for a in alerts:
        assert {"player_id", "name", "team_id", "open_minute", "expires_minute", "hazard", "level", "clock"} <= set(a)
        assert a["level"] in ("elevated", "high")
    sc = monitor.scorecard()
    n_concerns = sum(1 for e in events if e["type"] == "injury_concern")
    for key in ("model", "baseline"):
        assert sc[key]["concerns"] == n_concerns
        assert 0.0 <= sc[key]["precision"] <= 1.0 and 0.0 <= sc[key]["recall"] <= 1.0
        assert 0.0 <= sc[key]["top3_rate"] <= 1.0 and 0.0 <= sc[key]["mean_rank_pct"] <= 100.0
    assert sc["horizon_minutes"] == 15


def test_monitor_summary_is_json_and_observable_only(monitored):
    monitor, _ = monitored
    blob = json.dumps(monitor.summary())
    assert "fatigue" not in blob and "susceptib" not in blob
    s = monitor.summary()
    assert {"active_windows", "scorecard", "recent_alerts", "concerns"} <= set(s)


def test_each_concern_is_recorded_with_coverage(monitored, events):
    monitor, _ = monitored
    recorded = monitor.summary()["concerns"]
    assert [c["player_id"] for c in recorded] == [e["player_id"] for e in events if e["type"] == "injury_concern"]
    assert all(set(c) >= {"player_id", "minute", "covered", "lead_minutes", "baseline_covered"} for c in recorded)
