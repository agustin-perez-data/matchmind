"""Per-moment traces of what the agents did, captured through Agent Framework middleware.

The streamer sends these traces to the Control room seat: which agent ran,
how long it took, which tools it called, how many tokens it used. One trace
per key moment (or per Coach consultation), carried in a context variable so
the middleware finds it without any plumbing through the agents' code.
"""

from __future__ import annotations

import contextvars
import time
from typing import Any

from agent_framework import agent_middleware, function_middleware

current_trace: contextvars.ContextVar["MomentTrace | None"] = contextvars.ContextVar("matchmind_trace", default=None)
# Set by the agent middleware for the duration of a run, so tool calls can be attributed to their agent
# even when several agents run concurrently (each workflow participant runs in its own task).
current_agent: contextvars.ContextVar[str | None] = contextvars.ContextVar("matchmind_agent", default=None)


class MomentTrace:
    def __init__(self, label: str = ""):
        self.label = label
        self._t0 = time.perf_counter()
        self.events: list[dict] = []

    def _now(self) -> int:
        return round((time.perf_counter() - self._t0) * 1000)

    def mark(self, kind: str, agent: str | None = None, **detail: Any) -> dict:
        event = {"t": self._now(), "kind": kind, "agent": agent, **detail}
        self.events.append(event)
        return event

    def to_list(self) -> list[dict]:
        return list(self.events)


def _usage(result: Any) -> dict | None:
    """Token usage from an AgentResponse: a top-level usage_details or the usage content items."""
    candidates = [getattr(result, "usage_details", None)]
    for message in getattr(result, "messages", None) or []:
        for content in getattr(message, "contents", None) or []:
            if getattr(content, "type", None) == "usage":
                candidates.append(getattr(content, "usage_details", None))
    inp = out = None
    for usage in candidates:
        if usage is None:
            continue
        # UsageDetails is a TypedDict in Agent Framework >= 1.20 (a plain mapping); older builds exposed attributes
        get = usage.get if isinstance(usage, dict) else (lambda k, d=None: getattr(usage, k, d))
        i, o = get("input_token_count"), get("output_token_count")
        if i is not None or o is not None:
            inp, out = (inp or 0) + (i or 0), (out or 0) + (o or 0)
    if inp is None and out is None:
        return None
    return {"input": inp, "output": out}


def _summarise_args(arguments: Any) -> dict:
    if hasattr(arguments, "model_dump"):
        arguments = arguments.model_dump()
    try:
        return {k: (v if isinstance(v, (int, float, bool, type(None))) else str(v)[:80]) for k, v in dict(arguments).items()}
    except Exception:  # noqa: BLE001
        return {"value": str(arguments)[:80]}


@agent_middleware
async def trace_agents(context, call_next) -> None:
    """Records every agent run (start, end, latency, tokens) into the active trace."""
    trace = current_trace.get()
    if trace is None:
        await call_next()
        return
    name = getattr(getattr(context, "agent", None), "name", None) or "agent"
    t0 = time.perf_counter()
    trace.mark("agent_start", name)
    token = current_agent.set(name)
    try:
        await call_next()
    except Exception as exc:
        trace.mark("agent_error", name, latency_ms=round((time.perf_counter() - t0) * 1000), error=repr(exc)[:200])
        raise
    finally:
        current_agent.reset(token)
    tokens = _usage(getattr(context, "result", None))
    trace.mark("agent_end", name, latency_ms=round((time.perf_counter() - t0) * 1000), tokens=tokens)
    try:
        from matchmind.agents.observability import record_tokens

        record_tokens(name, tokens)
    except Exception:  # noqa: BLE001  telemetry never breaks an agent run
        pass


@function_middleware
async def trace_tools(context, call_next) -> None:
    """Records every tool call the agents make (name, arguments, latency)."""
    trace = current_trace.get()
    if trace is None:
        await call_next()
        return
    name = getattr(getattr(context, "function", None), "name", None) or "tool"
    agent = current_agent.get()
    t0 = time.perf_counter()
    trace.mark("tool_call", agent, tool=name, args=_summarise_args(getattr(context, "arguments", {})))
    try:
        await call_next()
    except Exception as exc:
        trace.mark("tool_error", agent, tool=name, latency_ms=round((time.perf_counter() - t0) * 1000), error=repr(exc)[:200])
        raise
    trace.mark("tool_result", agent, tool=name, latency_ms=round((time.perf_counter() - t0) * 1000))


TRACE_MIDDLEWARE = [trace_agents, trace_tools]
