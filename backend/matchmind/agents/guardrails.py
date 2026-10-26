"""Groundedness guardrail: Azure AI Content Safety checks the Narrator's line against the moment's facts.

The grounding source is the moment's facts written as plain sentences, not the JSON the agents receive: the
detector is tuned for prose and scored the same lines 8 points worse when fed raw JSON. The task is QnA with
the Narrator's own brief as the query, which is what the call actually is.

Enabled with MATCHMIND_GUARDRAILS=1 on the same Foundry (AI Services) resource the agents use
(`text:detectGroundedness`, preview). Runs once per uncached moment, with a short timeout, and never blocks
the broadcast: a failure or a timeout records `checked: false`. The result is appended to the moment's trace
as {"kind": "guardrail", "agent": "Narrator", "grounded": bool, "ungrounded_percentage": float, ...} so the
Control room draws it and the cache keeps it for later viewers. The detector is tuned for English; Spanish
lines are checked too, read those results as indicative.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)
API_VERSION = "2024-09-15-preview"
TIMEOUT_S = 2.5
MAX_TEXT = 7000
MAX_SOURCE = 50000
SCOPE = "https://cognitiveservices.azure.com/.default"
NARRATION_QUERY = "Narrate this key moment of the match for the viewer, using only what happened."


def context_text(ctx: dict) -> str:
    """The facts the agents were given, minus the viewer bookkeeping, as JSON (what the evaluation harness scores)."""
    keep = ("clock", "score", "moment", "event", "teams", "momentum", "last_10_minutes", "players_involved",
            "watched_players", "risk_alerts", "game_state", "top_shooters")
    return json.dumps({k: ctx[k] for k in keep if k in ctx}, ensure_ascii=False)


def facts_text(ctx: dict) -> str:
    """The same facts as plain sentences: the grounding source the detector reads best."""
    teams = ctx.get("teams") or {}
    name = {k: (t.get("name") or k) for k, t in teams.items() if isinstance(t, dict)}
    lines = [f"The clock reads {ctx.get('clock')}."]
    score = ctx.get("score") or {}
    if score:
        lines.append("The score is " + ", ".join(f"{name.get(k, k)} {v}" for k, v in score.items()) + ".")
    moment = ctx.get("moment") or {}
    if moment.get("summary"):
        lines.append(f"The key moment is: {moment['summary']}.")
    e = ctx.get("event") or {}
    if e:
        bits = [f"The event is a {str(e.get('type', '')).replace('_', ' ')}"]
        if e.get("player_name") or e.get("player_id"):
            bits.append(f"by {e.get('player_name') or e.get('player_id')}")
        if e.get("team_id"):
            bits.append(f"of {name.get(e['team_id'], e['team_id'])}")
        for key, unit in (("distance_m", " metres"), ("xg", " expected goals")):
            if e.get(key) is not None:
                bits.append(f"from {e[key]}{unit}" if key == "distance_m" else f"worth {e[key]}{unit}")
        if e.get("outcome"):
            bits.append(f"and the outcome is {e['outcome']}")
        lines.append(" ".join(bits) + ".")
    for tid, team in (teams.items() if isinstance(teams, dict) else []):
        if isinstance(team, dict):
            stats = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in team.items()
                              if k in ("shots", "xg", "possession_pct", "passes", "pressures") and v is not None)
            if stats:
                lines.append(f"{team.get('name', tid)} has {stats}.")
    if ctx.get("momentum") is not None:
        lines.append(f"The momentum value is {ctx['momentum']}, where positive favours the home side.")
    for p in (ctx.get("players_involved") or [])[:4]:
        if isinstance(p, dict) and p.get("name"):
            lines.append(f"{p['name']} has played {p.get('minutes_played')} minutes.")
    for a in (ctx.get("risk_alerts") or [])[:3]:
        if isinstance(a, dict) and a.get("name"):
            lines.append(f"{a['name']} is in a {a.get('level')} injury-risk window opened at minute {a.get('open_minute')}.")
    return "\n".join(lines)


def enabled() -> bool:
    return os.environ.get("MATCHMIND_GUARDRAILS", "0").lower() in ("1", "true", "on") and bool(os.environ.get("AZURE_OPENAI_ENDPOINT"))


def _endpoint() -> str:
    return os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")


_token: dict[str, Any] = {"value": None, "expires": 0.0}


def _headers() -> dict[str, str]:
    key = os.environ.get("AZURE_CONTENT_SAFETY_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")
    if key:
        return {"Ocp-Apim-Subscription-Key": key}
    if _token["value"] is None or _token["expires"] - time.time() < 120:
        from azure.identity import DefaultAzureCredential

        tok = DefaultAzureCredential(exclude_interactive_browser_credential=True).get_token(SCOPE)
        _token["value"], _token["expires"] = tok.token, float(tok.expires_on)
    return {"Authorization": f"Bearer {_token['value']}"}


def detect_groundedness(text: str, sources: list[str], query: str = NARRATION_QUERY) -> dict:
    """Synchronous call; returns the service's JSON ({"ungroundedDetected", "ungroundedPercentage", "ungroundedDetails"})."""
    import httpx

    body = {"domain": "Generic", "task": "QnA", "qna": {"query": query}, "text": text[:MAX_TEXT],
            "groundingSources": [s[:MAX_SOURCE] for s in sources], "reasoning": False}
    r = httpx.post(f"{_endpoint()}/contentsafety/text:detectGroundedness", params={"api-version": API_VERSION},
                   json=body, headers=_headers(), timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def narration_lines(result: dict) -> list[tuple[str, str]]:
    """(viewer profile key, narration text) for every viewer in a moment result."""
    out = []
    for vkey, view in (result.get("viewers") or {}).items():
        text = ((view or {}).get("narration") or {}).get("text")
        if text:
            out.append((vkey, text))
    return out


async def check_moment(result: dict, context_text: str) -> list[dict]:
    """Append one guardrail entry per narrated viewer to result["trace"]; returns the entries."""
    entries: list[dict] = []
    if not enabled() or not isinstance(result, dict):
        return entries
    trace = result.setdefault("trace", [])
    t_last = max((e.get("t", 0) for e in trace if isinstance(e, dict)), default=0)
    for vkey, text in narration_lines(result):
        t0 = time.perf_counter()
        entry: dict[str, Any] = {"t": t_last, "kind": "guardrail", "agent": "Narrator", "profile": vkey, "checked": False}
        try:
            res = await asyncio.wait_for(asyncio.to_thread(detect_groundedness, text, [context_text]), TIMEOUT_S + 0.5)
            pct = float(res.get("ungroundedPercentage", 0.0))
            entry.update({"checked": True, "grounded": not bool(res.get("ungroundedDetected")), "ungrounded_percentage": round(pct, 3),
                          "ungrounded_text": [d.get("text", "")[:120] for d in (res.get("ungroundedDetails") or [])][:3]})
        except Exception as exc:  # noqa: BLE001
            entry["error"] = repr(exc)[:160]
            log.info("guardrail skipped for %s: %r", vkey, exc)
        entry["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        trace.append(entry)
        entries.append(entry)
    return entries
