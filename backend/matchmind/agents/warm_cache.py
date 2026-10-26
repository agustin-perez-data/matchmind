"""Warm the agent cache before a demo: replay every match through the agents once per profile.

    .venv/Scripts/python -m matchmind.agents.warm_cache                       # all matches, the four seat profiles
    .venv/Scripts/python -m matchmind.agents.warm_cache --match THU-NBF-40 --profile commentator:es --profile analyst:en

Runs the real agents (Foundry) against the live server at --base (default http://127.0.0.1:8000)
by opening a WebSocket replay per (match, profile) at maximum speed with a slow enough lane
cadence that no key moment is dropped. The server writes the cache; this script only drives it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import httpx
import websockets

SEAT_PROFILES = ["commentator:en", "commentator:es", "analyst:en", "analyst:es"]


async def warm(base: str, match_id: str, profile: str, speed: int, min_importance: int) -> dict:
    mode, lang = ([*profile.split(":"), "en"])[:2]
    ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_base}/ws/matches/{match_id}?speed={speed}&mode={mode}&lang={lang}&agents=1&coach=1&min_importance={min_importance}"
    counts: dict[str, int] = {}
    cached = 0
    t0 = time.time()
    async with websockets.connect(url, max_size=None) as ws:
        async for raw in ws:
            m = json.loads(raw)
            counts[m["kind"]] = counts.get(m["kind"], 0) + 1
            if m.get("cached"):
                cached += 1
            if m["kind"] == "end":
                break
    return {"match": match_id, "profile": profile, "seconds": round(time.time() - t0), "insights": counts.get("insight", 0),
            "coach": counts.get("coach", 0), "verdicts": counts.get("verdict", 0), "already_cached": cached}


async def main_async(args: argparse.Namespace) -> int:
    matches = args.match or [m["match_id"] for m in httpx.get(f"{args.base}/matches", timeout=10).json()]
    profiles = args.profile or SEAT_PROFILES
    print(f"warming {len(matches)} match(es) x {len(profiles)} profile(s) at {args.base}, speed {args.speed}")
    for match_id in matches:
        for profile in profiles:
            r = await warm(args.base, match_id, profile, args.speed, args.min_importance)
            print(f"  {r['match']} {r['profile']:<16} {r['seconds']:>4}s  insights {r['insights']}  coach {r['coach']}  "
                  f"verdicts {r['verdicts']}  already cached {r['already_cached']}", flush=True)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm the MatchMind agent cache through the live server")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--match", action="append", default=[])
    parser.add_argument("--profile", action="append", default=[], help="mode:lang, e.g. commentator:es (default: the four seat profiles)")
    parser.add_argument("--speed", type=int, default=40, help="replay speed; slow enough that no key moment is dropped by the lanes")
    parser.add_argument("--min-importance", type=int, default=2, help="2 covers the fan seat's threshold as well")
    sys.exit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
