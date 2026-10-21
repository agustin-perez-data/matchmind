"""Demo robustness: agent outputs are cached per moment and profile; each live stream has its own state view."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from matchmind.agents.cache import AgentCache, coach_key, insight_key, verdict_key
from matchmind.api.app import create_app
from matchmind.tools.registry import LiveStateRegistry, MatchTools, current_session
from tests.test_api import FakeCoach, FakeJudge, FakePipeline, _drain, data_dir  # noqa: F401 (fixture)


# ---------------------------------------------------------------- cache

def test_cache_round_trips_through_memory_and_disk(tmp_path):
    cache = AgentCache(tmp_path / "cache")
    assert cache.get("M1", "insight", insight_key(10, "analyst:en:-")) is None
    cache.put("M1", "insight", insight_key(10, "analyst:en:-"), {"analyst": {"headline": "h"}, "errors": [], "latency_ms": 900})
    hit = cache.get("M1", "insight", insight_key(10, "analyst:en:-"))
    assert hit["cached"] is True and hit["analyst"]["headline"] == "h" and hit["latency_ms"] == 900
    assert cache.stats() == {"hits": 1, "misses": 1, "entries": 1, "dir": str(tmp_path / "cache")}
    on_disk = json.loads((tmp_path / "cache" / "M1.json").read_text(encoding="utf-8"))
    assert list(on_disk) == ["insight:10:analyst:en:-"] and "cached" not in on_disk["insight:10:analyst:en:-"]
    again = AgentCache(tmp_path / "cache")  # a restart keeps what was learned
    assert again.get("M1", "insight", insight_key(10, "analyst:en:-"))["analyst"]["headline"] == "h"


def test_cache_never_keeps_degraded_results_and_keys_are_profile_specific():
    cache = AgentCache(None)
    cache.put("M1", "insight", insight_key(10, "analyst:en:-"), {"analyst": None, "errors": ["analyst: boom"]})
    assert cache.get("M1", "insight", insight_key(10, "analyst:en:-")) is None
    cache.put("M1", "insight", insight_key(10, "commentator:es:-"), {"analyst": {"headline": "es"}, "errors": []})
    assert cache.get("M1", "insight", insight_key(10, "analyst:en:-")) is None
    assert cache.get("M1", "insight", insight_key(10, "commentator:es:-"))["analyst"]["headline"] == "es"
    assert coach_key("risk_alert", "THU-15", 61) == "risk_alert:THU-15:61" and verdict_key(10, "es") == "10:es"


def test_cache_survives_an_unreadable_file(tmp_path, caplog):
    (tmp_path / "M1.json").write_text("{not json", encoding="utf-8")
    cache = AgentCache(tmp_path)
    assert cache.get("M1", "coach", "x") is None
    cache.put("M1", "coach", "x", {"proposal": None, "errors": []})
    assert json.loads((tmp_path / "M1.json").read_text(encoding="utf-8"))["coach:x"]["proposal"] is None


# ---------------------------------------------------------------- the stream uses the cache

@pytest.fixture()
def cached_client(data_dir, tmp_path):
    fakes = {"pipeline": FakePipeline(), "coach": FakeCoach(), "judge": FakeJudge()}
    app = create_app(data_dir=data_dir, pipeline=fakes["pipeline"], coach=fakes["coach"], judge=fakes["judge"],
                     cache=AgentCache(tmp_path / "cache"))
    with TestClient(app) as c:
        yield c, fakes


def test_second_viewer_of_the_same_profile_is_served_from_the_cache(cached_client, meta):
    client, fakes = cached_client
    url = f"/ws/matches/{meta['match_id']}?speed=0"
    with client.websocket_connect(url) as ws:
        ws.receive_json()
        first = _drain(ws)
    insights1 = [m for m in first if m["kind"] == "insight"]
    coach1 = [m for m in first if m["kind"] == "coach"]
    verdicts1 = [m for m in first if m["kind"] == "verdict"]
    assert insights1 and coach1 and verdicts1 and not any(m.get("cached") for m in insights1 + coach1 + verdicts1)
    calls = (len(fakes["pipeline"].calls), len(fakes["coach"].calls), len(fakes["judge"].calls))

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        second = _drain(ws)
    insights2 = [m for m in second if m["kind"] == "insight"]
    assert insights2 and all(m["cached"] for m in insights2)
    assert all(m["cached"] for m in second if m["kind"] in ("coach", "verdict"))
    assert len(fakes["pipeline"].calls) == calls[0], "no second Analyst call for the same moments"
    assert len(fakes["coach"].calls) == calls[1] and len(fakes["judge"].calls) == calls[2]
    # the verdicts' scores are this viewer's own grading, not the first viewer's copy
    v2 = [m for m in second if m["kind"] == "verdict"]
    assert v2 and all(set(m["scores"]) == {"dominance", "goal", "watch", "overall"} for m in v2)
    assert second[-1]["credibility"]["judged"] == len(v2)
    health = client.get("/health").json()
    assert health["cache"]["hits"] >= len(insights2) and health["judge"] is True and health["live_sessions"] == 0

    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&mode=commentator&lang=es") as ws:
        ws.receive_json()
        third = _drain(ws)
    assert not any(m.get("cached") for m in third if m["kind"] == "insight"), "another profile is another explanation"
    assert len(fakes["pipeline"].calls) > calls[0]


def test_cache_can_be_switched_off(data_dir, meta):
    pipeline = FakePipeline()
    with TestClient(create_app(data_dir=data_dir, pipeline=pipeline, coach=FakeCoach(), judge=FakeJudge(), cache=False)) as c:
        for _ in range(2):
            with c.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&coach=0") as ws:
                ws.receive_json()
                msgs = _drain(ws)
            assert not any(m.get("cached") for m in msgs)
        assert c.get("/health").json()["cache"] is None
    n = len(pipeline.calls)
    assert n >= 2  # both viewers were explained from scratch


# ---------------------------------------------------------------- per-session registry views

def test_each_session_reads_its_own_view_and_outsiders_get_the_latest():
    registry = LiveStateRegistry()
    tools = MatchTools(registry)
    meta = {"match_id": "M1", "home_id": "THU", "away_id": "NBF", "teams": {"THU": {"name": "Thames United", "players": []}, "NBF": {"name": "Northbridge FC", "players": []}}}

    def snap(minute):
        return {"match_id": "M1", "home_id": "THU", "away_id": "NBF", "period": 1 if minute < 45 else 2, "minute": minute,
                "clock": f"{minute}:00", "score": {"THU": 0, "NBF": 0}, "teams": {"THU": {"xg": 0.1 * minute, "shots": 1, "possession_pct": 50.0, "passes": 10, "pass_accuracy": 0.8, "pressures": 1, "shots_on_target": 0, "goals": 0}, "NBF": {"xg": 0.0, "shots": 0, "possession_pct": 50.0, "passes": 10, "pass_accuracy": 0.8, "pressures": 1, "shots_on_target": 0, "goals": 0}},
                "momentum": 0.0, "momentum_series": [], "xg_race": [], "players": {}, "risk_alerts": []}

    async def viewer(sid: str, minute: int):
        current_session.set(sid)
        registry.update("M1", meta, snap(minute))
        await asyncio.sleep(0.01)
        return int(tools.get_match_state("M1")["clock"].split(":")[0]), registry.get("M1")["snapshot"]["minute"]

    async def both():
        return await asyncio.gather(viewer("a", 30), viewer("b", 80))

    (a_tool, a_get), (b_tool, b_get) = asyncio.run(both())
    assert (a_tool, a_get) == (30, 30) and (b_tool, b_get) == (80, 80)
    assert current_session.get() is None and registry.get("M1")["snapshot"]["minute"] == 80  # outsiders see the latest write
    assert registry.sessions() == 2
    registry.drop_session("a")
    registry.drop_session("b")
    assert registry.sessions() == 0 and registry.get("M1")["snapshot"]["minute"] == 80


def test_session_risk_and_credibility_stay_with_the_session():
    registry = LiveStateRegistry()
    meta = {"match_id": "M1", "teams": {}}
    snapshot = {"match_id": "M1", "minute": 10, "score": {}, "teams": {}, "players": {}, "risk_alerts": []}

    async def viewer(sid):
        current_session.set(sid)
        registry.update("M1", meta, snapshot)
        registry.update_risk("M1", {"minute": 10, "active_windows": [], "hazards": {}, "scorecard": None, "note": sid})
        registry.update_credibility("M1", {"judged": 1}, latest={"who": sid})
        await asyncio.sleep(0.01)
        return registry.get("M1")["risk"]["note"], registry.get("M1")["credibility"]["latest"]["who"]

    async def both():
        return await asyncio.gather(viewer("a"), viewer("b"))

    assert asyncio.run(both()) == [("a", "a"), ("b", "b")]
