"""Microsoft Foundry wiring: Agent Framework chat clients and the agents.

Two model tiers, both read from the environment (see backend/.env.example):
    fast  -> AZURE_OPENAI_DEPLOYMENT_FAST  (Narrator, Director, Judge; many short calls)
    smart -> AZURE_OPENAI_DEPLOYMENT_SMART (Analyst, Coach; deeper reasoning)

Three ways to reach Foundry, chosen by `auth_mode()`:
    project  -> FOUNDRY_PROJECT_ENDPOINT set: the Foundry project is the control plane. Keyless
                (DefaultAzureCredential: a managed identity on Azure, `az login` locally), Responses API,
                traces and evaluations land in the same project. This is how the deployed app runs.
    identity -> AZURE_OPENAI_ENDPOINT + MATCHMIND_AUTH=identity: keyless on the account endpoint.
    key      -> AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY: the local fallback.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from matchmind.agents.analyst import ANALYST_INSTRUCTIONS, AnalystAgent
from matchmind.agents.director import DIRECTOR_INSTRUCTIONS, DirectorAgent
from matchmind.agents.narrator import NARRATOR_INSTRUCTIONS, NarratorAgent
from matchmind.agents.pipeline import MomentPipeline

if TYPE_CHECKING:  # import cycles at runtime; these are only annotations
    from matchmind.agents.coach import CoachPipeline
    from matchmind.agents.judge import JudgePipeline

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
# Stable ids, emitted as gen_ai.agent.id on every span: Foundry matches them to the external-agent
# registrations created by infra/register_external_agents.py (see infra/README.md).
AGENT_IDS = {"Analyst": "matchmind-analyst", "Narrator": "matchmind-narrator", "Director": "matchmind-director",
             "Coach": "matchmind-coach", "Judge": "matchmind-judge-inprocess"}
DEFAULT_API_VERSION = "2024-10-21"
log = logging.getLogger(__name__)


def load_env() -> None:
    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=False)


def auth_mode() -> str | None:
    """'project' | 'identity' | 'key' | None (not configured)."""
    load_env()
    if os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
        return "project"
    if os.environ.get("AZURE_OPENAI_ENDPOINT"):
        if os.environ.get("AZURE_OPENAI_API_KEY"):
            return "key"
        if os.environ.get("MATCHMIND_AUTH", "").lower() == "identity":
            return "identity"
    return None


def foundry_configured() -> bool:
    return auth_mode() is not None


def project_endpoint() -> str | None:
    load_env()
    return os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or None


def _credential():
    """Managed identity in Container Apps (AZURE_CLIENT_ID picks the user-assigned one), `az login` on a laptop."""
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def chat_client(tier: str = "fast"):
    """Agent Framework chat client bound to one Foundry deployment, by the configured auth mode."""
    load_env()
    deployment = os.environ[f"AZURE_OPENAI_DEPLOYMENT_{tier.upper()}"]
    mode = auth_mode()
    if mode == "project":
        from agent_framework.foundry import FoundryChatClient

        return FoundryChatClient(project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], model=deployment, credential=_credential())
    if mode is None:
        raise RuntimeError("Foundry is not configured: set FOUNDRY_PROJECT_ENDPOINT, or AZURE_OPENAI_ENDPOINT with a key or MATCHMIND_AUTH=identity")
    from agent_framework.openai import OpenAIChatCompletionClient

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    version = os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
    if mode == "identity":
        return OpenAIChatCompletionClient(model=deployment, azure_endpoint=endpoint, api_version=version, credential=_credential())
    return OpenAIChatCompletionClient(model=deployment, azure_endpoint=endpoint, api_version=version, api_key=os.environ["AZURE_OPENAI_API_KEY"])


def foundry_client(tier: str = "fast"):
    """The project's chat client, for the Foundry evaluation APIs (they need the project, not the account endpoint)."""
    from agent_framework.foundry import FoundryChatClient

    load_env()
    endpoint = project_endpoint()
    if not endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is required for Foundry evaluations")
    return FoundryChatClient(project_endpoint=endpoint, model=os.environ[f"AZURE_OPENAI_DEPLOYMENT_{tier.upper()}"], credential=_credential())


def describe_auth() -> str:
    mode = auth_mode()
    return {"project": "Foundry project, managed identity", "identity": "account endpoint, managed identity",
            "key": "account endpoint, API key"}.get(mode or "", "not configured")


def build_coach(match_tools) -> CoachPipeline:
    """Coach agent (smart tier) + deterministic branch simulation through MatchTools."""
    from matchmind.agents.coach import COACH_INSTRUCTIONS, CoachAgent, CoachPipeline
    from matchmind.agents.schemas import CoachProposal
    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    agent = chat_client("smart").as_agent(
        id=AGENT_IDS["Coach"], name="Coach", instructions=COACH_INSTRUCTIONS,
        tools=[match_tools.get_player_workload, match_tools.get_risk_windows],
        default_options={"temperature": 0.3, "response_format": CoachProposal},
        middleware=TRACE_MIDDLEWARE,
    )
    return CoachPipeline(CoachAgent(agent), match_tools)


def build_judge() -> JudgePipeline:
    """Judge agent (fast tier): words only; the forecast scores are computed in code."""
    from matchmind.agents.judge import JUDGE_INSTRUCTIONS, JudgeAgent, JudgePipeline
    from matchmind.agents.schemas import JudgeVerdict
    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    if os.environ.get("MATCHMIND_JUDGE", "").lower() == "foundry" and auth_mode() == "project":
        try:
            return JudgePipeline(JudgeAgent(hosted_judge(), hosted=True))
        except Exception as exc:  # noqa: BLE001  (not registered yet: the first deploy registers it after the API starts)
            log.warning("hosted Judge unavailable (%r); using the in-process Judge", exc)
    agent = chat_client("fast").as_agent(
        id=AGENT_IDS["Judge"], name="Judge", instructions=JUDGE_INSTRUCTIONS,
        default_options={"temperature": 0.2, "response_format": JudgeVerdict}, middleware=TRACE_MIDDLEWARE,
    )
    return JudgePipeline(JudgeAgent(agent))


def hosted_judge():
    """The Judge as the prompt agent registered in the project (infra/register_judge.py): same instructions, same
    model, same JudgeVerdict schema, versioned and visible under Agents. Latest version unless MATCHMIND_JUDGE_VERSION."""
    from agent_framework_foundry import FoundryAgent
    from azure.ai.projects import AIProjectClient

    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    endpoint, credential = os.environ["FOUNDRY_PROJECT_ENDPOINT"], _credential()
    version = os.environ.get("MATCHMIND_JUDGE_VERSION")
    if not version:
        versions = list(AIProjectClient(endpoint=endpoint, credential=credential).agents.list_versions("matchmind-judge"))
        if not versions:
            raise RuntimeError("matchmind-judge is not registered in the project (run infra/register_judge.py)")
        version = str(max(int(getattr(v, "version", 0) or 0) for v in versions))
    log.info("Judge: hosted agent matchmind-judge v%s", version)
    # temperature and the JSON schema live in the registered version; Foundry rejects a request that sets them again
    return FoundryAgent(project_endpoint=endpoint, agent_name="matchmind-judge", agent_version=version, credential=credential,
                        middleware=TRACE_MIDDLEWARE)


def build_analyst(tools: list | None = None, instructions: str | None = None) -> AnalystAgent:
    """The Analyst alone (smart tier); `instructions` lets an evaluation harness try a prompt variant."""
    from matchmind.agents.schemas import AnalystInsight
    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    agent = chat_client("smart").as_agent(
        id=AGENT_IDS["Analyst"], name="Analyst", instructions=instructions or ANALYST_INSTRUCTIONS, tools=tools or None,
        default_options={"temperature": 0.4, "response_format": AnalystInsight}, middleware=TRACE_MIDDLEWARE,
    )
    return AnalystAgent(agent)


def build_pipeline(tools: list | None = None):
    """The three LLM agents on Foundry, orchestrated with Agent Framework workflows.

    `tools` are given to the Analyst only. Set MATCHMIND_ORCHESTRATION=gather to use the
    plain asyncio pipeline instead of the ConcurrentBuilder fan-out.
    """
    from matchmind.agents.orchestration import FrameworkMomentPipeline
    from matchmind.agents.schemas import DirectorDecision, Narration
    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    fast = chat_client("fast")
    analyst = build_analyst(tools).agent
    narrator = fast.as_agent(
        id=AGENT_IDS["Narrator"], name="Narrator", instructions=NARRATOR_INSTRUCTIONS,
        default_options={"temperature": 0.8, "response_format": Narration}, middleware=TRACE_MIDDLEWARE,
    )
    director = fast.as_agent(
        id=AGENT_IDS["Director"], name="Director", instructions=DIRECTOR_INSTRUCTIONS,
        default_options={"temperature": 0.2, "response_format": DirectorDecision}, middleware=TRACE_MIDDLEWARE,
    )
    agents = (AnalystAgent(analyst), NarratorAgent(narrator), DirectorAgent(director))
    if os.environ.get("MATCHMIND_ORCHESTRATION", "framework").lower() == "gather":
        return MomentPipeline(*agents)
    return FrameworkMomentPipeline(*agents)
