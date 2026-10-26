"""Telemetry to Application Insights (and so to the Foundry project's Traces page).

Enabled only when APPLICATIONINSIGHTS_CONNECTION_STRING is set. The Agent Framework emits gen_ai spans
for every agent run and tool call; on top of those this module adds a `moment` span per key moment and
four metrics the bench and the ops dashboard read:
    matchmind.moment.latency_ms  histogram  attrs cache_hit, kind
    matchmind.cache.lookups      counter    attrs hit
    matchmind.tokens             counter    attrs agent, direction
    matchmind.sessions.active    gauge      live viewer sessions
Without the variable every function here is a no-op (the OpenTelemetry API defaults to no-op providers),
so local runs and tests never pay for it. Prompts and completions are never exported (sensitive data off).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from opentelemetry import metrics, trace

log = logging.getLogger(__name__)
SERVICE_NAME = "matchmind-api"
_state: dict[str, object] = {"enabled": False}
_meter = metrics.get_meter("matchmind")
_tracer = trace.get_tracer("matchmind")
_moment_latency = _meter.create_histogram("matchmind.moment.latency_ms", unit="ms", description="time to explain a key moment")
_cache_lookups = _meter.create_counter("matchmind.cache.lookups", description="agent cache lookups by hit/miss")
_tokens = _meter.create_counter("matchmind.tokens", description="Foundry tokens by agent and direction")


def telemetry_enabled() -> bool:
    return bool(_state["enabled"])


def configure_observability(app=None, sessions: Callable[[], int] | None = None) -> bool:
    """Wire Azure Monitor when configured. Returns True when telemetry is on."""
    global _meter, _tracer, _moment_latency, _cache_lookups, _tokens
    cs = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not cs:
        return False
    os.environ.setdefault("OTEL_SERVICE_NAME", SERVICE_NAME)
    try:
        from microsoft.opentelemetry import use_microsoft_opentelemetry

        # the distro instruments the Agent Framework (gen_ai spans per agent/tool), exports to Azure Monitor and
        # keeps prompts out of the telemetry; the instrumentation key is `agent_framework` (underscore)
        # sampling_ratio=1.0 keeps every span: the distro's default is a rate limit per second, which quietly
        # dropped most of a moment's agent spans (a key moment fans out to three agents within two seconds).
        # The volume here is a handful of replays, and Log Analytics is capped at 1 GB/day anyway.
        use_microsoft_opentelemetry(
            enable_azure_monitor=True, azure_monitor_connection_string=cs,
            instrumentation_options={"agent_framework": {"enabled": True}},
            azure_monitor_enable_live_metrics=False, sampling_ratio=1.0,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("microsoft-opentelemetry failed (%r); falling back to the Agent Framework exporter", exc)
        try:
            from agent_framework.observability import configure_otel_providers
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

            configure_otel_providers(service_name=SERVICE_NAME, exporters=[AzureMonitorTraceExporter.from_connection_string(cs)],
                                     enable_sensitive_data=False)
        except Exception as exc2:  # noqa: BLE001
            log.warning("telemetry disabled: %r", exc2)
            return False
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
        except Exception as exc:  # noqa: BLE001
            log.warning("FastAPI instrumentation skipped: %r", exc)
    if sessions is not None:
        try:
            _meter.create_observable_gauge("matchmind.sessions.active", callbacks=[lambda _o: [metrics.Observation(sessions())]],
                                           description="live viewer sessions")
        except Exception as exc:  # noqa: BLE001
            log.warning("sessions gauge skipped: %r", exc)
    # refresh the module-level instruments against the real provider
    _meter = metrics.get_meter("matchmind")
    _tracer = trace.get_tracer("matchmind")
    _moment_latency = _meter.create_histogram("matchmind.moment.latency_ms", unit="ms", description="time to explain a key moment")
    _cache_lookups = _meter.create_counter("matchmind.cache.lookups", description="agent cache lookups by hit/miss")
    _tokens = _meter.create_counter("matchmind.tokens", description="Foundry tokens by agent and direction")
    _state["enabled"] = True
    log.info("telemetry on: Azure Monitor, service %s", os.environ["OTEL_SERVICE_NAME"])
    return True


@contextmanager
def moment_span(match_id: str, kind: str, mode: str, cache_hit: bool | None = None) -> Iterator[trace.Span]:
    with _tracer.start_as_current_span("moment") as span:
        span.set_attribute("matchmind.match_id", match_id)
        span.set_attribute("moment.kind", kind)
        span.set_attribute("profile.mode", mode)
        if cache_hit is not None:
            span.set_attribute("cache.hit", cache_hit)
        yield span


def _framework_emits_agent_spans() -> bool:
    """True when the Agent Framework's own instrumentation is on, so a span of ours would be a duplicate."""
    try:
        from agent_framework.observability import OBSERVABILITY_SETTINGS

        return bool(getattr(OBSERVABILITY_SETTINGS, "enable_instrumentation", False))
    except Exception:  # noqa: BLE001
        return False


@contextmanager
def agent_span(name: str, agent_id: str | None) -> Iterator[trace.Span | None]:
    """The gen_ai span Foundry attributes to a registered agent, when nothing else opened one.

    The Agent Framework emits `invoke_agent` spans when an agent is called directly, but the concurrent
    workflow path does not, so the Analyst, Narrator and Director would appear only as anonymous `chat`
    spans and their external-agent registrations would stay empty. This opens the span ourselves, and
    stays out of the way when the framework already did (it only tops up the id attribute).
    """
    current = trace.get_current_span()
    if getattr(current, "name", "").startswith("invoke_agent"):
        if agent_id and current.is_recording():
            current.set_attribute("gen_ai.agent.id", agent_id)
        yield current
        return
    if _framework_emits_agent_spans():
        yield None  # the Agent Framework will open its own span, carrying the same id
        return
    with _tracer.start_as_current_span(f"invoke_agent {name}") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.agent.name", name)
        if agent_id:
            span.set_attribute("gen_ai.agent.id", agent_id)
        yield span


def record_moment(latency_ms: float, cache_hit: bool, kind: str) -> None:
    _moment_latency.record(latency_ms, {"cache_hit": cache_hit, "kind": kind})
    _cache_lookups.add(1, {"hit": cache_hit})


def record_tokens(agent: str, tokens: dict | None) -> None:
    if not tokens:
        return
    for direction in ("input", "output"):
        n = tokens.get(direction)
        if n:
            _tokens.add(int(n), {"agent": agent, "direction": direction})
