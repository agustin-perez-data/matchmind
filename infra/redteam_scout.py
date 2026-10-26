"""AI Red Teaming Agent (Azure AI Evaluation SDK) against the hosted Scout agent.

The Scout is the only MatchMind surface that takes free text from a person (the Foundry playground), so it is
the one worth attacking: the scan sends adversarial prompts across the standard risk categories, with a few
attack strategies, and records the attack success rate in the project's red teaming page.

    FOUNDRY_PROJECT_ENDPOINT=... python infra/redteam_scout.py [--objectives 3] [--out redteam.json]

Needs `pip install "azure-ai-evaluation[redteam]"` (a separate venv on a short path on Windows: PyRIT ships
very long file names) and a login with Foundry User on the project. Costs a few dozen gpt-4.1-mini calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

AGENT_NAME = "matchmind-scout"


def build_target():
    """The Scout, as a plain text callback the scanner can drive."""
    from agent_framework_foundry import FoundryAgent
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    versions = list(AIProjectClient(endpoint=endpoint, credential=cred).agents.list_versions(AGENT_NAME))
    version = str(max(int(getattr(v, "version", 0) or 0) for v in versions))
    pool = ThreadPoolExecutor(max_workers=4)

    def ask(query: str) -> str:
        # the scanner calls the target from inside its own event loop: run the agent on a worker thread with a
        # loop of its own, and build the client there so nothing is bound to the scanner's loop
        agent = FoundryAgent(project_endpoint=endpoint, agent_name=AGENT_NAME, agent_version=version, credential=cred)
        return asyncio.run(agent.run(query)).text or ""

    def target(query: str) -> str:
        try:
            return pool.submit(ask, query).result(timeout=120)
        except Exception as exc:  # noqa: BLE001  (a refusal or a tool error is still an answer to score)
            return f"[error] {exc!r}"[:500]

    return target, version


async def run(args: argparse.Namespace) -> dict:
    from azure.ai.evaluation.red_team import AttackStrategy, RedTeam, RiskCategory
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("set FOUNDRY_PROJECT_ENDPOINT", file=sys.stderr)
        sys.exit(2)
    target, version = build_target()
    red_team = RedTeam(
        azure_ai_project=endpoint, credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
        risk_categories=[RiskCategory.Violence, RiskCategory.HateUnfairness, RiskCategory.Sexual, RiskCategory.SelfHarm],
        num_objectives=args.objectives,
        application_scenario="A decision-support assistant for a football club's bench and analysts; it reads a synthetic league's live match state through tools and must stay on workload, risk and tactics",
    )
    result = await red_team.scan(
        target=target, scan_name=f"{AGENT_NAME}-v{version}-redteam",
        attack_strategies=[AttackStrategy.Baseline, AttackStrategy.Flip, AttackStrategy.Base64, AttackStrategy.Tense],
        output_path=args.out,
    )
    summary = {}
    try:
        scorecard = result.to_scorecard() if hasattr(result, "to_scorecard") else None
        summary = {"scorecard": scorecard}
    except Exception:  # noqa: BLE001
        pass
    print(json.dumps(summary, indent=1, default=str)[:4000])
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Red team scan of the hosted Scout agent")
    ap.add_argument("--objectives", type=int, default=3, help="attack objectives per risk category")
    ap.add_argument("--out", default="redteam_scout.json")
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
