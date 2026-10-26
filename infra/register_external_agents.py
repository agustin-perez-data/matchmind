"""Register MatchMind's in-process agents as Foundry external agents (preview), for the trace and Monitor views.

The Analyst, Narrator, Director and Coach run inside the API, not in Foundry, so Foundry only sees their
OpenTelemetry spans. Registering each one as an `external` agent tells the project that the spans carrying
`gen_ai.agent.id = matchmind-<agent>` (set by the stable ids in agents/clients.py) belong to a named agent, which
lights up the per-agent Traces and Monitor tabs and trace-based evaluations. Registration is metadata only:
Foundry never hosts, proxies or invokes anything, and no AI Gateway is involved (that is the Control Plane's
"custom agent", a different thing).

    FOUNDRY_PROJECT_ENDPOINT=... python infra/register_external_agents.py

Idempotent: an existing registration with the same otel_agent_id is left alone. The hosted Judge
(infra/register_judge.py) is a prompt agent and is not registered here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

AGENTS = {
    "matchmind-analyst": "Reads the match state and explains why a key moment matters, with a 10-minute forecast the Judge grades later.",
    "matchmind-narrator": "Writes one line of commentary per key moment, in the viewer's language, mode and allegiance.",
    "matchmind-director": "Decides what each viewer sees of a moment: narration, insight, risk, stat, and the priority.",
    "matchmind-coach": "Turns a risk window or a knock into a substitution or a tactical change, after reading the player's workload with its tools.",
}


def main() -> int:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("set FOUNDRY_PROJECT_ENDPOINT", file=sys.stderr)
        return 2
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import ExternalAgentDefinition
    from azure.identity import DefaultAzureCredential

    from matchmind.agents.clients import AGENT_IDS

    expected = set(AGENTS)
    missing = expected - set(AGENT_IDS.values())
    if missing:  # the ids in the code are the contract; a typo here would silently orphan the traces
        print(f"these registrations have no agent id in clients.py: {sorted(missing)}", file=sys.stderr)
        return 2

    client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
                             allow_preview=True)
    for name, description in AGENTS.items():
        try:
            existing = client.agents.get(agent_name=name)
            current = getattr(getattr(getattr(existing, "versions", None), "latest", None), "definition", None)
            if getattr(current, "otel_agent_id", None) == name:
                print(f"{name}: already registered")
                continue
        except Exception:  # noqa: BLE001  (not registered yet)
            pass
        agent = client.agents.create_version(agent_name=name, description=description,
                                             definition=ExternalAgentDefinition(otel_agent_id=name))
        print(f"{name}: registered ({getattr(agent, 'name', name)})")
    print("\nTraces appear under Agents > <name> > Traces a few minutes after the next replay with agents on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
