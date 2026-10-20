"""FastAPI streamer: REST discovery + WebSocket live replay."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from matchmind.api.app import create_app
from matchmind.generate_match import write_match

SNAPSHOT_TYPES = ("goal", "shot", "half_time", "full_time", "substitution", "injury_concern")


@pytest.fixture(scope="module")
def client(match, tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    write_match(*match, out_dir=data_dir)
    app = create_app(data_dir=data_dir)
    with TestClient(app) as c:
        yield c


def test_root_redirects_to_interactive_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/docs"


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


def test_websocket_streams_every_event_in_order_with_snapshots(client, meta, events):
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0") as ws:
        first = ws.receive_json()
        assert first["kind"] == "meta"
        assert first["meta"]["match_id"] == meta["match_id"]
        seen_ids, snapshots, last = [], 0, None
        while True:
            msg = ws.receive_json()
            if msg["kind"] == "end":
                break
            assert msg["kind"] == "event"
            seen_ids.append(msg["event"]["event_id"])
            if "state" in msg:
                snapshots += 1
                last = msg["state"]
        assert seen_ids == [e["event_id"] for e in events]
        assert snapshots > 0
        assert last["score"] == meta["score"]


def test_key_events_always_carry_a_snapshot(client, meta):
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0") as ws:
        ws.receive_json()
        while True:
            msg = ws.receive_json()
            if msg["kind"] == "end":
                break
            if msg["event"]["type"] in SNAPSHOT_TYPES:
                assert "state" in msg


def test_unknown_match_websocket_closes_with_error(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/matches/NOPE?speed=0") as ws:
            ws.receive_json()


def test_client_can_change_speed_mid_stream(client, meta):
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0") as ws:
        ws.receive_json()
        ws.send_json({"speed": 0})
        while True:
            msg = ws.receive_json()
            if msg["kind"] == "ack":
                assert msg["speed"] == 0
                break
            assert msg["kind"] == "event"
