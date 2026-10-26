"""Stream load test: N concurrent viewers replay a match to full time against a deployed API.

    python -m loadtest.stream_load --api https://<fqdn> --viewers 25 --speed 300 [--agents 1] [--seat fan]

Measures what the SLOs promise: replay completeness (every viewer reaches `end`), socket errors, time to the
first insight per viewer (with agents on: the cache serves every seat after the warm job), and wall time.
Prints a JSON summary; exit code 1 when a viewer failed or the p95 breaches the target.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import websockets

MODES = {"fan": "commentator", "analyst": "analyst", "bench": "bench", "control": "analyst"}


async def viewer(i: int, api: str, match_id: str, speed: int, agents: bool, seat: str, lang: str, results: list[dict]) -> None:
    q = f"speed={speed}&mode={MODES[seat]}&lang={lang}&agents={'1' if agents else '0'}&coach={'1' if agents else '0'}&min_importance=2&frames=auto"
    url = api.replace("http", "ws", 1) + f"/ws/matches/{match_id}?{q}"
    t0 = time.monotonic()
    rec = {"viewer": i, "ok": False, "first_insight_s": None, "insights": 0, "events": 0, "frames": 0, "alerts": 0, "seconds": None, "error": None}
    try:
        async with websockets.connect(url, max_size=None, open_timeout=30, ping_interval=20) as ws:
            async for raw in ws:
                m = json.loads(raw)
                k = m["kind"]
                if k == "event":
                    rec["events"] += 1
                elif k == "frame":
                    rec["frames"] += 1
                elif k == "insight":
                    rec["insights"] += 1
                    if rec["first_insight_s"] is None:
                        rec["first_insight_s"] = round(time.monotonic() - t0, 2)
                elif k == "risk_alert":
                    rec["alerts"] += 1
                elif k == "end":
                    rec["ok"] = True
                    break
    except Exception as exc:  # noqa: BLE001
        rec["error"] = repr(exc)[:160]
    rec["seconds"] = round(time.monotonic() - t0, 1)
    results.append(rec)


async def main_async(args: argparse.Namespace) -> int:
    results: list[dict] = []
    t0 = time.monotonic()
    tasks = []
    for i in range(args.viewers):
        tasks.append(asyncio.create_task(viewer(i, args.api.rstrip("/"), args.match, args.speed, args.agents, args.seat, args.lang, results)))
        await asyncio.sleep(args.ramp_s / max(1, args.viewers))  # ramp so the viewers do not all hit the same millisecond
    await asyncio.gather(*tasks)
    wall = round(time.monotonic() - t0, 1)
    ok = [r for r in results if r["ok"]]
    firsts = sorted(r["first_insight_s"] for r in results if r["first_insight_s"] is not None)
    p95 = firsts[min(len(firsts) - 1, int(0.95 * len(firsts)))] if firsts else None
    summary = {
        "api": args.api, "match": args.match, "viewers": args.viewers, "speed": args.speed, "agents": args.agents, "seat": args.seat,
        "completed": len(ok), "failed": [r for r in results if not r["ok"]][:5],
        "events_per_viewer": statistics.median(r["events"] for r in results) if results else 0,
        "frames_per_viewer": statistics.median(r["frames"] for r in results) if results else 0,
        "insights_per_viewer": statistics.median(r["insights"] for r in results) if results else 0,
        "first_insight_p50_s": statistics.median(firsts) if firsts else None,
        "first_insight_p95_s": p95,
        "replay_seconds_p50": statistics.median(r["seconds"] for r in results) if results else None,
        "wall_seconds": wall,
    }
    print(json.dumps(summary, indent=1))
    bad = len(ok) != args.viewers or (args.agents and p95 is not None and p95 > args.p95_target_s)
    return 1 if bad else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Concurrent viewers streaming a match to full time")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--match", default="THU-NBF-40")
    ap.add_argument("--viewers", type=int, default=25)
    ap.add_argument("--speed", type=int, default=300)
    ap.add_argument("--agents", type=int, default=1)
    ap.add_argument("--seat", choices=sorted(MODES), default="fan")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--ramp-s", type=float, default=5.0)
    ap.add_argument("--p95-target-s", type=float, default=8.0, help="time-to-first-insight p95 the run must meet when agents are on")
    args = ap.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
