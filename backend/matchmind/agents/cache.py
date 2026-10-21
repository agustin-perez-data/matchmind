"""Agent-output cache: the same key moment, for the same viewer profile, is explained once.

A replay is deterministic, so the Analyst/Narrator/Director result for (match, moment,
profile) can be reused by every later viewer: no second Foundry call, no latency, no
rate-limit pile-up when several judges open the demo at once. Results are kept in memory
and written through to one JSON file per match under MATCHMIND_CACHE_DIR (default
data/cache), so a restart or a scale-to-zero does not lose them.

Cached results are served with `"cached": true` so the Control room can say so; the
original trace is kept, which is what the swimlanes draw.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("matchmind.agents.cache")

KINDS = ("insight", "coach", "verdict")


class AgentCache:
    def __init__(self, directory: Path | str | None):
        self.dir = Path(directory) if directory else None
        self._mem: dict[str, dict[str, dict]] = {}  # match_id -> "kind:key" -> result
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    # ------------------------------------------------------------ persistence

    def _file(self, match_id: str) -> Path | None:
        return self.dir / f"{match_id}.json" if self.dir else None

    def _load(self, match_id: str) -> dict[str, dict]:
        if match_id in self._mem:
            return self._mem[match_id]
        entries: dict[str, dict] = {}
        f = self._file(match_id)
        if f is not None and f.is_file():
            try:
                entries = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning("cache file %s unreadable, starting empty: %r", f, exc)
        self._mem[match_id] = entries
        return entries

    def _flush(self, match_id: str) -> None:
        f = self._file(match_id)
        if f is None:
            return
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._mem[match_id], ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
        except OSError as exc:
            log.warning("could not write cache %s: %r", f, exc)

    # ------------------------------------------------------------ api

    def get(self, match_id: str, kind: str, key: str) -> dict | None:
        with self._lock:
            hit = self._load(match_id).get(f"{kind}:{key}")
            if hit is None:
                self.misses += 1
                return None
            self.hits += 1
            return {**hit, "cached": True}

    def put(self, match_id: str, kind: str, key: str, result: dict) -> None:
        if result is None or result.get("errors"):
            return  # never cache a degraded result; the next viewer gets another try
        with self._lock:
            self._load(match_id)[f"{kind}:{key}"] = {k: v for k, v in result.items() if k != "cached"}
            self._flush(match_id)

    def size(self, match_id: str | None = None) -> int:
        with self._lock:
            if match_id is not None:
                return len(self._load(match_id))
            return sum(len(v) for v in self._mem.values())

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "entries": self.size(), "dir": str(self.dir) if self.dir else None}


def cache_from_env(data_dir: Path | None = None) -> AgentCache | None:
    """MATCHMIND_CACHE=0 disables; MATCHMIND_CACHE_DIR overrides the location (default <data>/cache)."""
    if os.environ.get("MATCHMIND_CACHE", "1").lower() in ("0", "false", "off"):
        return None
    directory = os.environ.get("MATCHMIND_CACHE_DIR") or (Path(data_dir) / "cache" if data_dir else None)
    return AgentCache(directory)


def insight_key(event_id: int, profile_key: str, min_importance: int | None = None) -> str:
    return f"{event_id}:{profile_key}"


def coach_key(trigger: str, player_id: str | None, minute: int | None) -> str:
    return f"{trigger}:{player_id}:{minute}"


def verdict_key(event_id: int, language: str) -> str:
    return f"{event_id}:{language}"
