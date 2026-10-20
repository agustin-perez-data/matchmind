"""Counterfactual branching: same seed + an intervention plan = same match until minute M."""

from __future__ import annotations

import pytest

from matchmind.generate_match import generate


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "match_id"}


def _starting_gk(meta: dict, team_id: str) -> str:
    return next(p["player_id"] for p in meta["teams"][team_id]["players"] if p["position"] == "GK" and p["starter"])


def test_meta_records_seeds_so_a_branch_can_be_rebuilt(meta):
    assert meta["seed"] == 42 and meta["league_seed"] == 7
    assert meta["interventions"] == []


def test_forced_substitution_branch_is_identical_until_the_intervention_minute(match):
    base_events, base_meta = match
    gk = _starting_gk(base_meta, "THU")
    plan = [{"minute": 60, "type": "substitution", "team_id": "THU", "player_off_id": gk, "reason": "coach"}]
    br_events, br_meta = generate("THU", "NBF", 42, interventions=plan, match_id="THU-NBF-42~b1")

    assert br_meta["match_id"] == "THU-NBF-42~b1"
    assert br_meta["interventions"] == [dict(plan[0], status="applied")]
    before = lambda evs: [_strip(e) for e in evs if (e["period"], e["minute"]) < (2, 60)]
    assert before(base_events) == before(br_events)
    assert [_strip(e) for e in base_events] != [_strip(e) for e in br_events]

    sub = next(e for e in br_events if e["type"] == "substitution" and e.get("forced"))
    assert (sub["period"], sub["minute"]) == (2, 60)
    assert sub["player_off_id"] == gk and sub["reason"] == "coach"
    assert sub["player_on_id"] != gk
    # the goalkeeper who came on plays the rest of the match
    last_sample = [e for e in br_events if e["type"] == "physical_sample" and e["player_id"] == sub["player_on_id"]][-1]
    assert last_sample["minutes_played"] >= 25


def test_intervention_for_a_player_not_on_the_pitch_is_skipped_and_changes_nothing(match):
    base_events, base_meta = match
    bench_gk = next(p["player_id"] for p in base_meta["teams"]["NBF"]["players"] if p["position"] == "GK" and not p["starter"])
    plan = [{"minute": 30, "type": "substitution", "team_id": "NBF", "player_off_id": bench_gk}]
    br_events, br_meta = generate("THU", "NBF", 42, interventions=plan, match_id="x")
    assert br_meta["interventions"][0]["status"] == "skipped"
    assert [_strip(e) for e in br_events] == [_strip(e) for e in base_events]


def test_tactical_change_emits_an_event_and_diverges_afterwards(match):
    base_events, _ = match
    plan = [{"minute": 50, "type": "tactic", "team_id": "NBF", "press_intensity": 1.0, "style": "direct"}]
    br_events, br_meta = generate("THU", "NBF", 42, interventions=plan, match_id="x")
    assert br_meta["interventions"][0]["status"] == "applied"
    change = next(e for e in br_events if e["type"] == "tactical_change")
    assert (change["period"], change["minute"], change["team_id"]) == (2, 50, "NBF")
    assert change["press_intensity"] == 1.0 and change["style"] == "direct"
    before = lambda evs: [_strip(e) for e in evs if (e["period"], e["minute"]) < (2, 50)]
    assert before(base_events) == before(br_events)
    assert [_strip(e) for e in base_events] != [_strip(e) for e in br_events]


def test_unknown_intervention_type_is_rejected():
    with pytest.raises(ValueError, match="unknown intervention"):
        generate("THU", "NBF", 42, interventions=[{"minute": 10, "type": "teleport", "team_id": "THU"}])
