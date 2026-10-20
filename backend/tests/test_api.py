"""FastAPI service: REST discovery, WebSocket live replay, agent insights, MCP endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from matchmind.api.app import create_app
from matchmind.generate_match import write_match

SNAPSHOT_TYPES = ("goal", "shot", "half_time", "full_time", "substitution", "injury_concern", "card")
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class FakePipeline:
    """Stands in for MomentPipeline: no LLM, instant, records what it was asked."""

    def __init__(self):
        self.calls: list[tuple[dict, list]] = []

    async def run(self, context, profiles):
        self.calls.append((context, profiles))
        return {
            "event_id": context["moment"]["event_id"], "clock": context["clock"], "score": context["score"],
            "moment": context["moment"],
            "analyst": {"headline": f"fake insight for {context['moment']['kind']}", "why_it_matters": "x",
                        "tactical_read": "y", "key_stat": "z", "confidence": 0.5},
            "viewers": {p.key: {"profile": p.model_dump(), "narration": {"text": "fake", "language": p.language, "mode": p.mode},
                                "decision": {"show": ["narration"], "priority": 3, "headline": "h", "personalized_note": None}}
                        for p in profiles},
            "errors": [], "latency_ms": 1,
        }


@pytest.fixture(scope="module")
def data_dir(match, tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    write_match(*match, out_dir=d)
    return d


@pytest.fixture(scope="module")
def client(data_dir):
    with TestClient(create_app(data_dir=data_dir, enable_agents=False)) as c:
        yield c


@pytest.fixture()
def fake_pipeline():
    return FakePipeline()


@pytest.fixture()
def agent_client(data_dir, fake_pipeline):
    with TestClient(create_app(data_dir=data_dir, pipeline=fake_pipeline)) as c:
        yield c


def _drain(ws):
    """Collect every message after the meta one until 'end'."""
    msgs = []
    while True:
        msg = ws.receive_json()
        msgs.append(msg)
        if msg["kind"] == "end":
            return msgs


# ---------------------------------------------------------------- REST

def test_root_redirects_to_interactive_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/docs"


def test_health_reports_agent_availability(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["agents"] is False


def test_lists_available_matches(client, meta):
    r = client.get("/matches")
    assert r.status_code == 200
    ids = [m["match_id"] for m in r.json()]
    assert ids == [meta["match_id"]]
    assert r.json()[0]["score"] == meta["score"]


def test_returns_match_meta_without_latent_state(client, meta):
    r = client.get(f"/matches/{meta['match_id']}/meta")
    assert r.status_code == 200
    assert "fatigue" not in r.text and "susceptib" not in r.text
    assert r.json()["teams"].keys() == meta["teams"].keys()


def test_unknown_match_is_404(client):
    assert client.get("/matches/NOPE/meta").status_code == 404


# ---------------------------------------------------------------- WebSocket

def test_websocket_streams_every_event_in_order_with_snapshots(client, meta, events):
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0") as ws:
        first = ws.receive_json()
        assert first["kind"] == "meta"
        assert first["meta"]["match_id"] == meta["match_id"]
        assert first["agents"] is False and first["profile"]["mode"] == "analyst"
        msgs = _drain(ws)
    evs = [m for m in msgs if m["kind"] == "event"]
    assert [m["event"]["event_id"] for m in evs] == [e["event_id"] for e in events]
    assert [m["kind"] for m in msgs if m["kind"] not in ("event",)] == ["end"]
    with_state = [m for m in evs if "state" in m]
    assert with_state and with_state[-1]["state"]["score"] == meta["score"]


def test_key_events_always_carry_a_snapshot(client, meta):
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0") as ws:
        ws.receive_json()
        msgs = _drain(ws)
    assert all("state" in m for m in msgs if m["kind"] == "event" and m["event"]["type"] in SNAPSHOT_TYPES)


def test_unknown_match_websocket_closes_with_error(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/matches/NOPE?speed=0") as ws:
            ws.receive_json()


def test_bad_viewer_profile_closes_with_error(client, meta):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&mode=vip") as ws:
            ws.receive_json()


def test_client_can_change_speed_and_profile_mid_stream(client, meta):
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0") as ws:
        ws.receive_json()
        ws.send_json({"speed": 0})
        ws.send_json({"profile": {"mode": "casual", "language": "es"}})
        msgs = _drain(ws)
    acks = [m for m in msgs if m["kind"] == "ack"]
    assert {"speed": 0.0} in [{k: v for k, v in a.items() if k != "kind"} for a in acks]
    assert any(a.get("profile", {}).get("mode") == "casual" for a in acks)


# ---------------------------------------------------------------- agents over WebSocket

def test_insights_arrive_for_key_moments_without_breaking_the_event_stream(agent_client, fake_pipeline, meta, events):
    url = f"/ws/matches/{meta['match_id']}?speed=0&mode=player_focus&player=THU-15"
    with agent_client.websocket_connect(url) as ws:
        first = ws.receive_json()
        assert first["agents"] is True and first["profile"]["favorite_player_id"] == "THU-15"
        msgs = _drain(ws)
    evs = [m for m in msgs if m["kind"] == "event"]
    assert [m["event"]["event_id"] for m in evs] == [e["event_id"] for e in events]
    insights = [m for m in msgs if m["kind"] == "insight"]
    assert insights, "no insight messages"
    assert insights[-1]["moment"]["kind"] == "full_time"  # the last moment is never dropped
    assert all(i["analyst"]["headline"].startswith("fake insight") for i in insights)
    assert all("player_focus:en:THU-15" in i["viewers"] for i in insights)
    ctx, profiles = fake_pipeline.calls[0]
    assert profiles[0].favorite_player_id == "THU-15"
    assert ctx["watched_players"] and ctx["watched_players"][0]["player_id"] == "THU-15"
    assert all(c["moment"]["importance"] >= 3 for c, _ in fake_pipeline.calls)


def test_agents_can_be_switched_off_per_connection(agent_client, fake_pipeline, meta):
    with agent_client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&agents=0") as ws:
        assert ws.receive_json()["agents"] is False
        msgs = _drain(ws)
    assert not [m for m in msgs if m["kind"] == "insight"]
    assert fake_pipeline.calls == []


# ---------------------------------------------------------------- MCP endpoint

def test_mcp_endpoint_lists_tools_over_streamable_http(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=MCP_HEADERS)
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"list_matches", "get_match_state", "get_player_workload", "get_risk_alerts", "get_xg_race"} <= names


def test_mcp_endpoint_serves_preloaded_match_state(client, meta):
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "get_match_state", "arguments": {"match_id": meta["match_id"]}}}
    r = client.post("/mcp", json=body, headers=MCP_HEADERS)
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result
    assert meta["match_id"] in r.text and "momentum" in r.text
