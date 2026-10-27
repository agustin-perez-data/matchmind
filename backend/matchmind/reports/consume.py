"""Event-driven report writer: drains the `matchmind-events` queue into Blob storage.

Runs as the Container Apps job `matchmind-report` (KEDA azure-queue trigger, one execution per message
batch). Event Grid delivers each CloudEvent to the queue base64-encoded; this job decodes it and writes
`reports/<match_id>/<type>-<event_id>.json` to the `reports` container, then deletes the message.

Honest about delivery: Event Grid and the queue are at-least-once, so a fact can arrive twice; the blob name
is a function of the fact, so a duplicate overwrites the same file. The storage account comes from
MATCHMIND_STORAGE_ACCOUNT and the identity from DefaultAzureCredential (Storage Queue/Blob Data Contributor).

    python -m matchmind.reports.consume [--max 50]
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
from typing import Any

log = logging.getLogger(__name__)
QUEUE = "matchmind-events"
CONTAINER = "reports"


def decode_message(content: str | bytes) -> dict:
    """Queue messages from Event Grid are base64 JSON; a plain JSON body (tests, manual sends) is accepted too."""
    raw = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8")
    try:
        return json.loads(raw)
    except ValueError:
        return json.loads(base64.b64decode(raw))


def blob_name(event: dict) -> str:
    data = event.get("data") or {}
    match_id = data.get("match_id") or (event.get("subject") or "unknown").split("/")[1:2] or "unknown"
    if isinstance(match_id, list):
        match_id = match_id[0] if match_id else "unknown"
    kind = (event.get("type") or "event").rsplit(".", 1)[-1]
    safe_id = str(event.get("id", "")).replace(":", "-").replace("/", "-") or "no-id"
    return f"{match_id}/{kind}-{safe_id}.json"


def report_document(event: dict) -> dict:
    """What the blob holds: the event plus a one-line summary a human can read in the portal."""
    data = event.get("data") or {}
    if event.get("type", "").endswith("window_opened"):
        summary = (f"{data.get('name', data.get('player_id'))} entered a {data.get('level')} risk window at {data.get('clock')} "
                   f"(hazard {data.get('hazard')}, ACWR {data.get('acwr_live')})")
    elif event.get("type", "").endswith("ended"):
        score = " - ".join(str(v) for v in (data.get("score") or {}).values()) or "?"
        summary = (f"{data.get('home')} {score} {data.get('away')}: {data.get('knocks')} knocks, "
                   f"{data.get('warned')} warned, {data.get('windows_hit')}/{data.get('windows')} windows hit")
    else:
        summary = event.get("type", "event")
    return {"summary": summary, "event": event}


def process(queue: Any, blobs: Any, max_messages: int = 50) -> int:
    """Drain up to `max_messages`; `queue` and `blobs` are the SDK clients or fakes with the same two methods each."""
    done = 0
    for msg in queue.receive_messages(messages_per_page=min(32, max_messages), visibility_timeout=120):
        try:
            event = decode_message(msg.content)
            name = blob_name(event)
            blobs.upload_blob(name, json.dumps(report_document(event), ensure_ascii=False, indent=1), overwrite=True)
            log.info("wrote %s", name)
        except Exception as exc:  # noqa: BLE001
            log.warning("message %s skipped: %r", getattr(msg, "id", "?"), exc)
        queue.delete_message(msg)  # a poison message is not retried forever: it is logged and dropped
        done += 1
        if done >= max_messages:
            break
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--max", type=int, default=50)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    account = os.environ.get("MATCHMIND_STORAGE_ACCOUNT")
    if not account:
        print("MATCHMIND_STORAGE_ACCOUNT is not set", file=sys.stderr)
        return 2
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient
    from azure.storage.queue import BinaryBase64DecodePolicy, QueueClient

    cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    queue = QueueClient(f"https://{account}.queue.core.windows.net", QUEUE, credential=cred,
                        message_decode_policy=BinaryBase64DecodePolicy())
    blobs = ContainerClient(f"https://{account}.blob.core.windows.net", CONTAINER, credential=cred)
    n = process(queue, blobs, args.max)
    log.info("%d message(s) processed", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
