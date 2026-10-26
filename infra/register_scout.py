"""Register "matchmind-scout" in the Foundry project: a prompt agent whose only tools are MatchMind's MCP server.

The Scout is the agent a club analyst would talk to in the Foundry playground ("who is at highest injury risk
for Thames right now, and why?"): it reads the live state through the public /mcp endpoint of the deployed API
and must cite the tool outputs. It never gets `simulate_intervention` (read-only by construction).

    FOUNDRY_PROJECT_ENDPOINT=... MATCHMIND_API_URL=https://... python infra/register_scout.py

Idempotent: a new version is created only when the definition changed. Prints the agent name and version.
"""

from __future__ import annotations

import os
import sys

AGENT_NAME = "matchmind-scout"
MODEL = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4.1-mini")
ALLOWED_TOOLS = ["list_matches", "get_match_state", "get_player_workload", "get_risk_alerts", "get_risk_windows",
                 "get_xg_race", "get_analyst_credibility", "get_team_shape", "get_player_heatmap"]
INSTRUCTIONS = """You are the MatchMind Scout, a decision-support assistant for a football club's bench and analysts.

Everything you can see comes from the MatchMind tools: a synthetic league (fictional clubs and players; no real
competition, club or person). Use the tools before answering: list the matches, read the match state, the player
workloads, the open risk windows and the risk alerts, the xG race, the team shape and the Analyst's credibility.

Rules:
- Cite the numbers the tools returned (ACWR, minutes, sprint density, hazard, xG) and the clock they refer to.
- Injury risk is a workload signal (acute:chronic workload ratio, minutes, sprint density, pace drop, previous
  knocks). Say "risk window" and "workload", never diagnose; this is decision support, not medical advice.
- Player positions come from a positional model built from the event stream, not tracking data; say so if asked.
- Be concise: lead with the answer, then the two or three numbers that support it, then what to watch next.
- If a tool returns nothing for a match, say the match has not been streamed yet.
"""


def main() -> int:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    api = (os.environ.get("MATCHMIND_API_URL") or "").rstrip("/")
    if not endpoint or not api:
        print("set FOUNDRY_PROJECT_ENDPOINT and MATCHMIND_API_URL", file=sys.stderr)
        return 2
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPTool, PromptAgentDefinition
    from azure.identity import DefaultAzureCredential

    client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential(exclude_interactive_browser_credential=True))
    definition = PromptAgentDefinition(
        model=MODEL, instructions=INSTRUCTIONS, temperature=0.3,
        tools=[MCPTool(server_label="matchmind", server_url=f"{api}/mcp", require_approval="never", allowed_tools=ALLOWED_TOOLS)],
    )
    latest = None
    try:
        versions = list(client.agents.list_versions(AGENT_NAME))
        latest = max(versions, key=lambda v: int(getattr(v, "version", 0) or 0)) if versions else None
    except Exception:  # noqa: BLE001  (first registration)
        latest = None
    if latest is not None:
        cur = getattr(latest, "definition", None)
        same = (getattr(cur, "instructions", None) == INSTRUCTIONS and getattr(cur, "model", None) == MODEL
                and any(getattr(t, "server_url", None) == f"{api}/mcp" for t in (getattr(cur, "tools", None) or [])))
        if same:
            print(f"{AGENT_NAME} version {latest.version} unchanged")
            return 0
    created = client.agents.create_version(AGENT_NAME, definition=definition,
                                           description="Reads MatchMind's live match state through its MCP server; read-only; synthetic league")
    print(f"{AGENT_NAME} version {created.version} registered with MCP {api}/mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
