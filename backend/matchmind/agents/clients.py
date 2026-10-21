"""Azure AI Foundry wiring: Agent Framework chat clients and the three agents.

Two model tiers, both read from the environment (see backend/.env.example):
    fast  -> AZURE_OPENAI_DEPLOYMENT_FAST  (Narrator, Director; many short calls)
    smart -> AZURE_OPENAI_DEPLOYMENT_SMART (Analyst; deeper reasoning)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from matchmind.agents.analyst import ANALYST_INSTRUCTIONS, AnalystAgent
from matchmind.agents.director import DIRECTOR_INSTRUCTIONS, DirectorAgent
from matchmind.agents.narrator import NARRATOR_INSTRUCTIONS, NarratorAgent
from matchmind.agents.pipeline import MomentPipeline

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_API_VERSION = "2024-10-21"


def load_env() -> None:
    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=False)


def foundry_configured() -> bool:
    load_env()
    return bool(os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"))


def chat_client(tier: str = "fast"):
    """Agent Framework chat client bound to one Foundry deployment."""
    from agent_framework.openai import OpenAIChatCompletionClient

    load_env()
    deployment = os.environ[f"AZURE_OPENAI_DEPLOYMENT_{tier.upper()}"]
    return OpenAIChatCompletionClient(
        model=deployment,
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION),
    )


def build_coach(match_tools) -> "CoachPipeline":
    """Coach agent (smart tier) + deterministic branch simulation through MatchTools."""
    from matchmind.agents.coach import COACH_INSTRUCTIONS, CoachAgent, CoachPipeline
    from matchmind.agents.schemas import CoachProposal
    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    agent = chat_client("smart").as_agent(
        name="Coach", instructions=COACH_INSTRUCTIONS,
        tools=[match_tools.get_player_workload, match_tools.get_risk_windows],
        default_options={"temperature": 0.3, "response_format": CoachProposal},
        middleware=TRACE_MIDDLEWARE,
    )
    return CoachPipeline(CoachAgent(agent), match_tools)


def build_judge() -> "JudgePipeline":
    """Judge agent (fast tier): words only; the forecast scores are computed in code."""
    from matchmind.agents.judge import JUDGE_INSTRUCTIONS, JudgeAgent, JudgePipeline
    from matchmind.agents.schemas import JudgeVerdict
    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    agent = chat_client("fast").as_agent(
        name="Judge", instructions=JUDGE_INSTRUCTIONS,
        default_options={"temperature": 0.2, "response_format": JudgeVerdict}, middleware=TRACE_MIDDLEWARE,
    )
    return JudgePipeline(JudgeAgent(agent))


def build_analyst(tools: list | None = None, instructions: str | None = None) -> AnalystAgent:
    """The Analyst alone (smart tier); `instructions` lets an evaluation harness try a prompt variant."""
    from matchmind.agents.schemas import AnalystInsight
    from matchmind.agents.tracing import TRACE_MIDDLEWARE

    agent = chat_client("smart").as_agent(
        name="Analyst", instructions=instructions or ANALYST_INSTRUCTIONS, tools=tools or None,
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
        name="Narrator", instructions=NARRATOR_INSTRUCTIONS,
        default_options={"temperature": 0.8, "response_format": Narration}, middleware=TRACE_MIDDLEWARE,
    )
    director = fast.as_agent(
        name="Director", instructions=DIRECTOR_INSTRUCTIONS,
        default_options={"temperature": 0.2, "response_format": DirectorDecision}, middleware=TRACE_MIDDLEWARE,
    )
    agents = (AnalystAgent(analyst), NarratorAgent(narrator), DirectorAgent(director))
    if os.environ.get("MATCHMIND_ORCHESTRATION", "framework").lower() == "gather":
        return MomentPipeline(*agents)
    return FrameworkMomentPipeline(*agents)
