"""Replay scheduling: turn a recorded event list into a timed live feed.

Events carry match-clock timestamps (`minute`, `second`). Replaying them
"live" means sleeping the clock gap between consecutive events, divided by
a speed factor (1 = real time, 10 = 10x faster, 0 = no waiting at all).
"""

from __future__ import annotations

import json
from pathlib import Path


def event_seconds(event: dict) -> int:
    """Absolute match time of an event in seconds (minute 46 -> 2760s)."""
    return int(event["minute"]) * 60 + int(event["second"])


def delay_between(prev: dict | None, cur: dict, speed: float) -> float:
    """Seconds to wait before emitting `cur` after `prev` at the given speed.

    - Never negative (the simulator clock can jitter backwards within a minute).
    - A period change (half-time) is emitted immediately: nobody wants to wait
      through the break.
    - speed <= 0 means instant replay.
    """
    if prev is None or speed is None or speed <= 0:
        return 0.0
    if prev.get("period") != cur.get("period"):
        return 0.0
    gap = event_seconds(cur) - event_seconds(prev)
    return max(0.0, gap) / speed


def delays(events: list[dict], speed: float) -> list[float]:
    """Per-event wait times for a whole stream (see `delay_between`)."""
    out: list[float] = []
    prev: dict | None = None
    for e in events:
        out.append(delay_between(prev, e, speed))
        prev = e
    return out


def load_events(path: Path | str) -> list[dict]:
    """Read a JSONL event file in order. Raises FileNotFoundError if missing."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- positional frames

def frame_stride(speed: float) -> int:
    """How many positional frames to skip between the ones sent, by replay speed.

    1 Hz frames at x1-x60 look fluid; faster replays send fewer so the socket and the browser
    keep up; at x400+ (and at 0 = instant) none are sent. 0 means "send no frames".
    """
    if speed is None or speed <= 0:
        return 0
    if speed <= 60:
        return 1
    if speed <= 150:
        return 2
    if speed <= 400:
        return 5
    return 0


def merge_timeline(events: list[dict], frames: list[dict]) -> list[dict]:
    """Events and frames in one clock-ordered list: at the same second the events come first."""
    def key(item: dict, rank: int) -> tuple[int, int, int]:
        return (int(item["period"]), event_seconds(item), rank)

    merged = [(key(e, 0), i, e) for i, e in enumerate(events)] + [(key(f, 1), i, f) for i, f in enumerate(frames)]
    merged.sort(key=lambda t: (t[0], t[1]))
    return [item for _, _, item in merged]
