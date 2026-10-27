"""Per-moment orchestration: Analyst + Narrators in parallel, then the Director.

    key moment ──► Analyst (smart model) ──┐
               ├► Narrator × viewer ───────┤──► Director × viewer ──► insight message
               └► (risk alerts from state) ┘

Every agent call is isolated: one failure degrades the result, never the stream.
"""

from __future__ import annotations

import asyncio
import logging
import time

from matchmind.agents.analyst import AnalystAgent
from matchmind.agents.director import INTERRUPT_PRIORITY, DirectorAgent
from matchmind.agents.narrator import NarratorAgent
from matchmind.agents.schemas import ViewerProfile

log = logging.getLogger("matchmind.agents")


class MomentPipeline:
    def __init__(
        self,
        analyst: AnalystAgent,
        narrator: NarratorAgent,
        director: DirectorAgent,
        profiles: list[ViewerProfile] | None = None,
    ):
        self.analyst, self.narrator, self.director = analyst, narrator, director
        self.profiles = profiles or [ViewerProfile()]

    async def run(self, context: dict, profiles: list[ViewerProfile] | None = None) -> dict:
        profiles = profiles or self.profiles
        errors: list[str] = []
        t0 = time.perf_counter()

        async def guarded(label: str, coro):
            try:
                return await coro
            except Exception as exc:  # noqa: BLE001 - any agent failure must not kill the stream
                log.warning("%s failed: %r", label, exc)
                errors.append(f"{label}: {exc!r}")
                return None

        insight, *narrations = await asyncio.gather(
            guarded("analyst", self.analyst.explain(context, profiles[0].language)),
            *[guarded(f"narrator[{p.key}]", self.narrator.narrate(context, p)) for p in profiles],
        )
        decisions = await asyncio.gather(
            *[guarded(f"director[{p.key}]", self.director.direct(context, insight, n, p)) for p, n in zip(profiles, narrations, strict=True)]
        )

        return {
            "event_id": context.get("moment", {}).get("event_id"),
            "clock": context.get("clock"),
            "score": context.get("score"),
            "moment": context.get("moment"),
            "analyst": insight.model_dump() if insight else None,
            "viewers": {
                p.key: {
                    "profile": p.model_dump(),
                    "narration": n.model_dump() if n else None,
                    "decision": d.model_dump() if d else None,
                    "interrupt": bool(d and d.priority >= INTERRUPT_PRIORITY),
                }
                for p, n, d in zip(profiles, narrations, decisions, strict=True)
            },
            "errors": errors,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }
