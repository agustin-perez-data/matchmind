"""Domain events, the report consumer and the nightly fixture: no Azure, fakes only."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import date

from matchmind.api import events
from matchmind.jobs.nightly import match_of_the_day
from matchmind.reports import consume
from tests.test_api import _drain, client, data_dir  # noqa: E402,F401  (fixtures)

ALERT = {"player_id": "THU-7", "name": "Ferrant", "team_id": "THU", "position": "FW", "clock": "61:10", "open_minute": 61,
         "hazard": 0.93, "level": "high", "hit": False, "minutes_played": 61, "acwr_live": 1.41, "effort_ratio_recent": 0.84,
         "reasons": ["acwr"], "fatigue": 0.9}  # a latent field never reaches an event


class FakeClient:
    def __init__(self):
        self.sent = []

    def send(self, batch):
        self.sent.extend(batch)


def test_window_event_forwards_only_observable_fields_and_dedupes():
    ev = events.window_opened("THU-NBF-40", 1203, ALERT)
    assert ev["type"] == events.WINDOW_OPENED and ev["id"] == "THU-NBF-40:1203" and ev["subject"] == "matches/THU-NBF-40/players/THU-7"
    assert "fatigue" not in json.dumps(ev) and ev["data"]["hazard"] == 0.93
    pub = events.EventPublisher(FakeClient())

    async def go():
        tasks = [pub.publish(ev), pub.publish(ev), pub.publish(events.window_opened("THU-NBF-40", 1300, ALERT))]
        await asyncio.gather(*(t for t in tasks if t is not None))
        return tasks

    tasks = asyncio.run(go())
    assert tasks[1] is None and pub.sent == 2 and len(pub.client.sent) == 2
    assert pub.client.sent[0].type == events.WINDOW_OPENED and pub.client.sent[0].data["match_id"] == "THU-NBF-40"


def test_match_ended_event_summarises_without_the_hazard_series():
    meta = {"home_id": "THU", "away_id": "NBF", "teams": {"THU": {"short_name": "Thames"}, "NBF": {"short_name": "Northbridge"}}}
    state = {"score": {"THU": 1, "NBF": 2}, "minute": 95}
    risk = {"concerns": [1, 2], "scorecard": {"alerts": 5, "true_alerts": 2, "covered": 1, "mean_lead_minutes": 12.5}, "hazards": [1], "series": [1]}
    ev = events.match_ended("THU-NBF-40", "analyst:en:-", meta, state, risk, {"hit_rate": 0.6, "graded": 5, "hits": 3, "rows": []})
    assert ev["id"] == "THU-NBF-40:ended:analyst:en:-" and ev["data"]["home"] == "Thames" and ev["data"]["knocks"] == 2
    assert ev["data"]["credibility"] == {"hit_rate": 0.6, "graded": 5, "hits": 3} and "series" not in ev["data"]


def test_publish_errors_never_raise():
    class Broken:
        def send(self, batch):
            raise RuntimeError("down")

    pub = events.EventPublisher(Broken(), timeout_s=1)

    async def go():
        t = pub.publish(events.window_opened("M", 1, ALERT))
        await t

    asyncio.run(go())
    assert pub.failed == 1 and pub.sent == 0


def test_publisher_from_env_is_none_without_endpoint(monkeypatch):
    monkeypatch.delenv("MATCHMIND_EVENTGRID_ENDPOINT", raising=False)
    events.reset_for_tests()
    assert events.publisher_from_env() is None
    events.reset_for_tests()


class Msg:
    def __init__(self, content, id="m1"):
        self.content, self.id = content, id


class FakeQueue:
    def __init__(self, msgs):
        self.msgs, self.deleted = msgs, []

    def receive_messages(self, **_):
        return list(self.msgs)

    def delete_message(self, msg):
        self.deleted.append(msg.id)


class FakeBlobs:
    def __init__(self):
        self.blobs = {}

    def upload_blob(self, name, data, overwrite=False):
        self.blobs[name] = json.loads(data)


def test_consumer_writes_one_blob_per_fact_and_tolerates_duplicates_and_poison():
    ev = events.window_opened("THU-NBF-40", 1203, ALERT)
    encoded = base64.b64encode(json.dumps(ev).encode()).decode()
    ended = events.match_ended("THU-NBF-40", "fan:es:-", {"home_id": "THU", "away_id": "NBF", "teams": {}}, {"score": {"THU": 1, "NBF": 2}}, {"scorecard": {}}, None)
    q = FakeQueue([Msg(encoded, "a"), Msg(json.dumps(ev), "b"), Msg("not json at all", "c"), Msg(json.dumps(ended), "d")])
    b = FakeBlobs()
    assert consume.process(q, b) == 4
    assert set(b.blobs) == {"THU-NBF-40/window_opened-THU-NBF-40-1203.json", "THU-NBF-40/ended-THU-NBF-40-ended-fan-es--.json"}
    assert "Ferrant" in b.blobs["THU-NBF-40/window_opened-THU-NBF-40-1203.json"]["summary"]
    assert q.deleted == ["a", "b", "c", "d"]


def test_match_of_the_day_is_deterministic_and_never_a_club_against_itself():
    for d in (date(2026, 10, 27), date(2026, 12, 31), date(2027, 1, 1)):
        home, away, seed = match_of_the_day(d)
        assert home != away and seed == int(d.strftime("%Y%m%d"))
    assert match_of_the_day(date(2026, 10, 27)) == match_of_the_day(date(2026, 10, 27))


def test_stream_publishes_the_ended_event_and_still_sends_end(client, meta, monkeypatch):
    """The deployed app lost `end` when the match.ended event raised (profile.key is a property): never again."""
    from matchmind.api import app as app_module

    pub = events.EventPublisher(FakeClient())
    monkeypatch.setattr(app_module, "publisher_from_env", lambda: pub)
    with client.websocket_connect(f"/ws/matches/{meta['match_id']}?speed=0&frames=0") as ws:
        ws.receive_json()
        msgs = _drain(ws)
    assert msgs[-1]["kind"] == "end"
    assert any(e.type == events.MATCH_ENDED for e in pub.client.sent) and pub.failed == 0
