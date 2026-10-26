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
from contextlib import contextmanager
from typing import Callable, Iterator

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
        use_microsoft_opentelemetry(
            enable_azure_monitor=True, azure_monitor_connection_string=cs,
            instrumentation_options={"agent_framework": {"enabled": True}},
            azure_monitor_enable_live_metrics=False,
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
