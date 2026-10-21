"""Moment pipeline orchestrated with Microsoft Agent Framework workflows.

    key moment ──► ConcurrentBuilder([Analyst, Narrator])  (fan-out, same input)
                              └──► Director                 (fan-in, structured decision)

Every run produces a trace (see tracing.py). If the workflow fails for any
reason the moment is still served through the direct-call pipeline, and the
trace says so: the broadcast never waits on the orchestrator.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Awaitable, Callable

from matchmind.agents.analyst import AnalystAgent, analyst_prompt
from matchmind.agents.director import DirectorAgent
from matchmind.agents.narrator import NarratorAgent, narrator_brief
from matchmind.agents.pipeline import MomentPipeline
from matchmind.agents.schemas import AnalystInsight, Narration, ViewerProfile
from matchmind.agents.tracing import MomentTrace, current_trace

log = logging.getLogger("matchmind.agents.orchestration")

WorkflowRunner = Callable[[str], Awaitable[list[tuple[str, str]]]]
ORCHESTRATION_LABEL = "agent-framework concurrent fan-out (Analyst + Narrator), Director fan-in"


def compose_fan_out_prompt(context: dict, profile: ViewerProfile) -> str:
    """One message for both concurrent participants; each agent's instructions pick its part."""
    return (
        analyst_prompt(context, profile.language)
        + "\n\n--- For the Narrator only ---\n"
        + narrator_brief(context, profile)
        + "\nAnalyst: ignore the viewer brief and answer with your structured insight. "
        "Narrator: write the commentary line for this viewer."
    )


def parse_participant(outputs: list[tuple[str, str]], author: str, model):
    """Find the participant's message by author name and parse its JSON into `model`."""
    for name, text in outputs:
        if name == author:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end < 0:
                raise ValueError(f"{author} returned no JSON: {text[:120]!r}")
            return model.model_validate_json(text[start:end + 1])
    raise ValueError(f"{author} produced no output")


class FrameworkMomentPipeline:
    def __init__(
        self,
        analyst: AnalystAgent,
        narrator: NarratorAgent,
        director: DirectorAgent,
        profiles: list[ViewerProfile] | None = None,
        run_workflow: WorkflowRunner | None = None,
    ):
        self.analyst, self.narrator, self.director = analyst, narrator, director
        self.profiles = profiles or [ViewerProfile()]
        self._run_workflow = run_workflow or self._run_concurrent
        self._direct = MomentPipeline(analyst, narrator, director, self.profiles)

    async def _run_concurrent(self, prompt: str) -> list[tuple[str, str]]:
        from agent_framework.orchestrations import ConcurrentBuilder

        workflow = ConcurrentBuilder(participants=[self.analyst.agent, self.narrator.agent]).build()
        events = await workflow.run(prompt)
        outputs = events.get_outputs()
        if not outputs:
            raise RuntimeError("concurrent workflow produced no output")
        final = outputs[0]
        return [(getattr(m, "author_name", None) or "", getattr(m, "text", "") or "") for m in final.messages]

    async def run(self, context: dict, profiles: list[ViewerProfile] | None = None) -> dict:
        profiles = profiles or self.profiles
        trace = MomentTrace("moment")
        token = current_trace.set(trace)
        t0 = time.perf_counter()
        errors: list[str] = []
        try:
            if len(profiles) != 1:
                trace.mark("fallback", None, reason=f"{len(profiles)} viewer profiles, direct path")
                result = await self._direct.run(context, profiles)
                return {**result, "trace": trace.to_list() + result.get("trace", []), "orchestration": "direct (multi-profile)"}
            profile = profiles[0]

            trace.mark("stage", None, stage="fan-out", participants=[self.analyst.agent.name if hasattr(self.analyst.agent, "name") else "Analyst", "Narrator"])
            t_stage = time.perf_counter()
            try:
                outputs = await self._run_workflow(compose_fan_out_prompt(context, profile))
                insight = parse_participant(outputs, "Analyst", AnalystInsight)
                narration = parse_participant(outputs, "Narrator", Narration)
                trace.mark("stage_end", None, stage="fan-out", latency_ms=round((time.perf_counter() - t_stage) * 1000))
            except Exception as exc:  # noqa: BLE001
                log.warning("concurrent workflow failed, falling back: %r", exc)
                errors.append(f"workflow: {exc!r}")
                trace.mark("fallback", None, reason=repr(exc)[:200])
                result = await self._direct.run(context, profiles)
                return {**result, "errors": errors + result["errors"], "trace": trace.to_list(), "orchestration": "direct (fallback)"}

            trace.mark("stage", None, stage="director")
            t_stage = time.perf_counter()
            decision = None
            try:
                decision = await self.director.direct(context, insight, narration, profile)
            except Exception as exc:  # noqa: BLE001
                log.warning("director failed: %r", exc)
                errors.append(f"director: {exc!r}")
            trace.mark("stage_end", None, stage="director", latency_ms=round((time.perf_counter() - t_stage) * 1000))

            return {
                "event_id": context.get("moment", {}).get("event_id"),
                "clock": context.get("clock"),
                "score": context.get("score"),
                "moment": context.get("moment"),
                "analyst": insight.model_dump(),
                "viewers": {profile.key: {"profile": profile.model_dump(), "narration": narration.model_dump(),
                                          "decision": decision.model_dump() if decision else None}},
                "errors": errors,
                "latency_ms": round((time.perf_counter() - t0) * 1000),
                "trace": trace.to_list(),
                "orchestration": ORCHESTRATION_LABEL,
            }
        finally:
            current_trace.reset(token)
