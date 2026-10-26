"""Domain events to Azure Event Grid (CloudEvents 1.0), published off the hot path.

Two event types, both facts about a match the product already computed:
    matchmind.risk.window_opened   a high-risk window opened for a player (the bench's alert)
    matchmind.match.ended          full time: score, knocks, warning time, credibility

Gated by MATCHMIND_EVENTGRID_ENDPOINT (the topic endpoint; auth is the managed identity with EventGrid Data
Sender). Without it every call is a no-op. Publishing never blocks or breaks a replay: it runs in a thread
with a short timeout and errors are logged only. Every viewer replays the same match, so an event id is
`<match>:<event_id>` and a per-process set keeps one publish per fact; the consumer tolerates the duplicates
two replicas can still produce (same blob name). Never includes the hazard series or any latent simulator state.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

WINDOW_OPENED = "matchmind.risk.window_opened"
MATCH_ENDED = "matchmind.match.ended"
SOURCE = "/matchmind/api"
SEND_TIMEOUT_S = 2.0
DEDUPE_LIMIT = 2000
ALERT_FIELDS = ("player_id", "name", "team_id", "position", "clock", "open_minute", "hazard", "level",
                "minutes_played", "acwr_live", "effort_ratio_recent", "reasons")


def cloud_event(event_type: str, subject: str, event_id: str, data: dict) -> dict:
    """A CloudEvents 1.0 envelope as a plain dict (the SDK's CloudEvent accepts the same fields)."""
    return {"specversion": "1.0", "type": event_type, "source": SOURCE, "subject": subject, "id": event_id,
            "time": datetime.now(timezone.utc).isoformat(), "datacontenttype": "application/json", "data": data}


def window_opened(match_id: str, event_id: int, alert: dict) -> dict:
    data = {"match_id": match_id, "event_id": event_id, **{k: alert[k] for k in ALERT_FIELDS if k in alert}}
    return cloud_event(WINDOW_OPENED, f"matches/{match_id}/players/{alert.get('player_id')}", f"{match_id}:{event_id}", data)


def match_ended(match_id: str, profile_key: str, meta: dict, state: dict, risk: dict, credibility: dict | None) -> dict:
    score = state.get("score", {})
    scorecard = (risk.get("scorecard") or {}).get("model") or {}  # the model's card; the baseline's stays out of the event
    data = {
        "match_id": match_id, "profile": profile_key,
        "home": meta.get("teams", {}).get(meta.get("home_id"), {}).get("short_name") or meta.get("home_id"),
        "away": meta.get("teams", {}).get(meta.get("away_id"), {}).get("short_name") or meta.get("away_id"),
        "score": score, "minute": state.get("minute"),
        "knocks": len(risk.get("concerns", [])),
        "windows": scorecard.get("alerts"), "windows_hit": scorecard.get("true_alerts"),
        "warned": scorecard.get("covered"), "mean_warning_minutes": scorecard.get("mean_lead_minutes"),
        "credibility": {k: credibility[k] for k in ("hit_rate", "graded", "hits") if credibility and k in credibility} if credibility else None,
    }
    return cloud_event(MATCH_ENDED, f"matches/{match_id}", f"{match_id}:ended:{profile_key}", data)


class EventPublisher:
    """Sends CloudEvents to one topic; `client` is anything with `send(list)` (the SDK client or a fake)."""

    def __init__(self, client: Any, timeout_s: float = SEND_TIMEOUT_S) -> None:
        self.client = client
        self.timeout_s = timeout_s
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.sent = 0
        self.failed = 0

    def _first_time(self, event_id: str) -> bool:
        if event_id in self._seen:
            return False
        self._seen[event_id] = None
        while len(self._seen) > DEDUPE_LIMIT:
            self._seen.popitem(last=False)
        return True

    def publish(self, event: dict) -> asyncio.Task | None:
        """Fire and forget from the event loop; returns the task (tests await it)."""
        if not self._first_time(event["id"]):
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._send(event)
            return None
        return loop.create_task(self._send_async(event))

    async def _send_async(self, event: dict) -> None:
        try:
            await asyncio.wait_for(asyncio.to_thread(self._send, event), self.timeout_s)
        except Exception as exc:  # noqa: BLE001
            self.failed += 1
            log.warning("event %s not published: %r", event["id"], exc)

    def _send(self, event: dict) -> None:
        from azure.core.messaging import CloudEvent

        payload = CloudEvent(source=event["source"], type=event["type"], data=event["data"], subject=event["subject"],
                             id=event["id"], datacontenttype=event["datacontenttype"])
        self.client.send([payload])
        self.sent += 1


_publisher: EventPublisher | None = None
_resolved = False


def publisher_from_env() -> EventPublisher | None:
    """The process-wide publisher, or None when MATCHMIND_EVENTGRID_ENDPOINT is not set."""
    global _publisher, _resolved
    if _resolved:
        return _publisher
    _resolved = True
    endpoint = os.environ.get("MATCHMIND_EVENTGRID_ENDPOINT")
    if not endpoint:
        return None
    try:
        from azure.eventgrid import EventGridPublisherClient
        from azure.identity import DefaultAzureCredential

        client = EventGridPublisherClient(endpoint, DefaultAzureCredential(exclude_interactive_browser_credential=True))
        _publisher = EventPublisher(client)
        log.info("Event Grid publisher on %s", endpoint)
    except Exception as exc:  # noqa: BLE001
        log.warning("Event Grid publisher disabled: %r", exc)
    return _publisher


def reset_for_tests() -> None:
    global _publisher, _resolved
    _publisher, _resolved = None, False
