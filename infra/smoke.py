"""Smoke test of a deployed MatchMind: health keys, catalogue, one fast replay to full time, MCP and the frontend.

    MATCHMIND_API_URL=https://... MATCHMIND_WEB_URL=https://... python infra/smoke.py

Exit code 1 on the first failure, with the reason. Agents are off for the replay (fast and free); the health
keys prove the agents, the project auth and telemetry are on.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx
import websockets

API = os.environ.get("MATCHMIND_API_URL", "http://127.0.0.1:8000").rstrip("/")
WEB = os.environ.get("MATCHMIND_WEB_URL", "").rstrip("/")
REQUIRE_AGENTS = os.environ.get("MATCHMIND_SMOKE_REQUIRE_AGENTS", "1") != "0"


def fail(msg: str) -> None:
    print(f"FAIL {msg}")
    sys.exit(1)


def check_health(client: httpx.Client) -> dict:
    r = client.get(f"{API}/health")
    if r.status_code != 200:
        fail(f"/health {r.status_code}: {r.text[:200]}")
    h = r.json()
    for key in ("ready", "draining", "matches", "agents", "auth", "project", "telemetry", "replica", "cache"):
        if key not in h:
            fail(f"/health lacks {key}")
    if not h["ready"] or h["draining"]:
        fail(f"/health not ready: {h}")
    if REQUIRE_AGENTS and not (h["agents"] and h["auth"] == "project" and h["project"]):
        fail(f"agents are not on the Foundry project: {h}")
    print("health", json.dumps({k: h[k] for k in ("ready", "matches", "agents", "auth", "project", "telemetry", "replica")}))
    return h


def check_catalogue(client: httpx.Client) -> str:
    rows = client.get(f"{API}/matches").json()
    if not rows:
        fail("no matches in the catalogue")
    ids = [r["match_id"] for r in rows]
    print("matches", ids)
    return "THU-NBF-40" if "THU-NBF-40" in ids else ids[0]


async def replay(match_id: str) -> None:
    url = API.replace("http", "ws", 1) + f"/ws/matches/{match_id}?speed=0&agents=0&coach=0&frames=0"
    t0 = time.monotonic()
    kinds: dict[str, int] = {}
    async with websockets.connect(url, max_size=None, open_timeout=20) as ws:
        async for raw in ws:
            m = json.loads(raw)
            kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
            if m["kind"] == "end":
                if "risk" not in m or "hazard_series" not in m:
                    fail("end message lacks the risk summary")
                print(f"replay {match_id} to full time in {time.monotonic() - t0:.1f}s: {kinds}")
                return
    fail("the stream closed before full time")


async def resume(match_id: str) -> None:
    url = API.replace("http", "ws", 1) + f"/ws/matches/{match_id}?speed=0&agents=0&coach=0&frames=0&from=900"
    async with websockets.connect(url, max_size=None, open_timeout=20) as ws:
        first_event = None
        async for raw in ws:
            m = json.loads(raw)
            if m["kind"] == "resume" and m["from"] != 900:
                fail(f"resume echoed {m['from']}")
            if m["kind"] == "event":
                first_event = first_event or m["event"]["event_id"]
            if m["kind"] == "end":
                break
        if first_event is None or first_event <= 900:
            fail(f"resume replayed an event before the cut: {first_event}")
    print("resume from 900 ok (first live event", first_event, ")")


def check_mcp(client: httpx.Client) -> None:
    r = client.post(f"{API}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}},
                    headers={"Accept": "application/json, text/event-stream"})
    if r.status_code >= 400:
        fail(f"/mcp initialize {r.status_code}: {r.text[:200]}")
    print("mcp initialize", r.status_code)


def check_web(client: httpx.Client) -> None:
    """The demo must stay anonymous; only the club area asks for a sign-in. A deploy that breaks this fails here."""
    if not WEB:
        print("web: skipped (MATCHMIND_WEB_URL not set)")
        return
    with httpx.Client(timeout=30, follow_redirects=False) as raw:
        for path in ("/", "/?seat=bench&match=THU-NBF-40", "/signin"):
            r = raw.get(WEB + path)
            if r.status_code != 200 or '<div id="root"' not in r.text:
                fail(f"{path} is not open to anonymous visitors: {r.status_code}")
        r = raw.get(WEB + "/club")
        if r.status_code not in (301, 302) or "/signin" not in r.headers.get("location", ""):
            fail(f"/club should send anonymous visitors to /signin, got {r.status_code} {r.headers.get('location')}")
    r = client.get(f"{API}/matches/THU-NBF-40/report")
    if r.status_code != 200 or "scorecard" not in r.text:
        fail(f"match report {r.status_code}")
    print("web ok: demo open, /club behind sign-in, report served", WEB)


def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        check_health(client)
        match_id = check_catalogue(client)
        asyncio.run(replay(match_id))
        asyncio.run(resume(match_id))
        check_mcp(client)
        check_web(client)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
