"""Register the Judge in the Foundry project as a prompt agent ("matchmind-judge"), straight from the code.

`to_prompt_agent` lifts the model, instructions, temperature and the JudgeVerdict response format from the same
Agent the API builds (agents/clients.py build_judge), so the hosted version and the in-process one are the same
agent. At runtime the API uses the hosted one when MATCHMIND_JUDGE=foundry (FoundryAgent, latest version
unless MATCHMIND_JUDGE_VERSION pins one); otherwise it keeps calling the model directly.

    FOUNDRY_PROJECT_ENDPOINT=... python infra/register_judge.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

AGENT_NAME = "matchmind-judge"


def main() -> int:
    if not os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
        print("set FOUNDRY_PROJECT_ENDPOINT", file=sys.stderr)
        return 2
    from agent_framework_foundry import to_prompt_agent
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    from matchmind.agents.clients import build_judge

    judge = build_judge().judge.agent  # the in-process Agent (FoundryChatClient when the project is configured)
    definition = to_prompt_agent(judge)
    client = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                             credential=DefaultAzureCredential(exclude_interactive_browser_credential=True))
    try:
        versions = list(client.agents.list_versions(AGENT_NAME))
    except Exception:  # noqa: BLE001
        versions = []
    latest = max(versions, key=lambda v: int(getattr(v, "version", 0) or 0)) if versions else None
    if latest is not None:
        cur = getattr(latest, "definition", None)
        if getattr(cur, "instructions", None) == definition.instructions and getattr(cur, "model", None) == definition.model:
            print(f"{AGENT_NAME} version {latest.version} unchanged")
            return 0
    created = client.agents.create_version(AGENT_NAME, definition=definition,
                                           description="Grades the Analyst's forecasts in words; scores are computed in code")
    print(f"{AGENT_NAME} version {created.version} registered (model {definition.model})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
