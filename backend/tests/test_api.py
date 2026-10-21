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


class FakeCoach:
    """Stands in for CoachPipeline: records contexts, returns a canned proposal + no branch."""

    def __init__(self):
        self.calls: list[dict] = []

    async def run(self, context):
        self.calls.append(context)
        return {"trigger": context["trigger"], "clock": context["clock"], "minute": context["minute"],
                "score": context["score"], "player": context["player"],
                "proposal": {"action": "hold", "team_id": context["team"]["team_id"], "player_off_id": None,
                             "player_on_id": None, "press_intensity": None, "style": None, "minute": context["minute"],
                             "rationale": "fake", "urgency": 2, "expected_effect": "none"},
                "branch": None, "errors": [], "latency_ms": 1}


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
def fake_coach():
    return FakeCoach()


@pytest.fixture()
def agent_client(data_dir, fake_pipeline, fake_coach):
    with TestClient(create_app(data_dir=data_dir, pipeline=fake_pipeline, coach=fake_coach)) as c:
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


def test_live_page_is_served(client):
    r = client.get("/live")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "WebSocket" in r.text and "/ws/matches/" in r.text


def test_cors_allows_the_frontend_origin(client):
    r = client.get("/matches", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


def test_health_reports_agent_availability(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["agents"] is False


def test_lists_available_matches(client, meta):
    r = client.get("/matches")
    assert r.status_code == 200
    ids = [m["match_id"] for m in r.json()]
    assert ids == [meta["match_id"]]
    assert r.json()[0]["score"] == meta["score"]
    assert r.json()[0]["home_team"]["primary_color"] == meta["teams"][meta["home_id"]]["primary_color"]
    assert r.json()[0]["away_team"]["pattern"] in ("solid", "halves", "stripes", "hoops", "sash", "sleeves")


def test_returns_match_meta_without_latent_state(client, meta):
    r = client.get(f"/matches/{meta['match_id']}/meta")
    assert r.status_code == 200
    assert "fatigue" not in r.text and "susceptib" not in r.text
    assert r.json()["teams"].keys() == meta["teams"].keys()


def test_unknown_match_is_404(client):
    assert client.get("/matches/NOPE/meta").status_code == 404


# ---------------------------------------------------------------- counterfactual branches

def _starting_gk(meta, team_id):
    return next(p["player_id"] for p in meta["teams"][team_id]["players"] if p["position"] == "GK" and p["starter"])


def test_post_branch_simulates_and_get_branch_returns_its_events(client, meta):
    body = {"minute": 60, "action": "substitution", "team_id": "THU", "player_off_id": _starting_gk(meta, "THU")}
    r = client.post(f"/matches/{meta['match_id']}/branches", json=body)
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["status"] == "applied" and summary["divergence_minute"] == 60
    r2 = client.get(f"/matches/{meta['match_id']}/branches/{summary['branch_id']}")
    assert r2.status_code == 200
    assert r2.json()["summary"] == summary
    assert r2.json()["events"][0]["match_id"] == summary["branch_id"]
    assert "fatigue" not in r2.text
    listed = client.get(f"/matches/{meta['match_id']}/branches").json()
    assert summary["branch_id"] in [b["branch_id"] for b in listed]


def test_post_branch_validates_input(client, meta):
    assert client.post(f"/matches/{meta['match_id']}/branches", json={"minute": 60, "action": "teleport", "team_id": "THU"}).status_code == 400
    assert client.post(f"/matches/{meta['match_id']}/branches", json={"minute": 60, "action": "substitution", "team_id": "THU"}).status_code == 400
    assert client.post("/matches/NOPE/branches", json={"minute": 60, "action": "tactic", "team_id": "THU", "style": "direct"}).status_code == 404
    assert client.get(f"/matches/{meta['match_id']}/branches/nope").status_code == 404


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
    assert [m["kind"] for m in msgs if m["kind"] not in ("event", "risk", "risk_alert")] == ["end"]
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


def test_websocket_streams_risk_summaries_and_alerts(client, meta):
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0") as ws:
        ws.receive_json()
        msgs = _drain(ws)
    risk = [m for m in msgs if m["kind"] == "risk"]
    assert len(risk) >= 10  # one per 5-minute physical sample batch
    assert risk[-1]["scorecard"]["model"]["concerns"] == risk[-1]["scorecard"]["baseline"]["concerns"] >= 1
    assert all({"minute", "clock", "active_windows", "hazards_top", "scorecard"} <= set(m) for m in risk)
    alerts = [m for m in msgs if m["kind"] == "risk_alert"]
    assert alerts and all({"player_id", "name", "level", "hazard", "open_minute"} <= set(a) for a in alerts)
    assert "fatigue" not in str(msgs)


# ---------------------------------------------------------------- agents over WebSocket

def test_coach_is_consulted_on_high_risk_alerts_and_concerns(agent_client, fake_coach, meta):
    with agent_client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&agents=0") as ws:
        ws.receive_json()
        msgs = _drain(ws)
    coach = [m for m in msgs if m["kind"] == "coach"]
    assert coach, "no coach messages"
    assert all(m["proposal"]["action"] == "hold" for m in coach)
    assert {c["trigger"] for c in fake_coach.calls} <= {"risk_alert", "injury_concern"}
    assert any(c["trigger"] == "injury_concern" for c in fake_coach.calls)
    assert all(c["player"]["player_id"] for c in fake_coach.calls)


def test_coach_can_be_switched_off(agent_client, fake_coach, meta):
    with agent_client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&agents=0&coach=0") as ws:
        ws.receive_json()
        msgs = _drain(ws)
    assert not [m for m in msgs if m["kind"] == "coach"] and fake_coach.calls == []

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
