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


def build_pipeline(tools: list | None = None) -> MomentPipeline:
    """The three LLM agents on Foundry. `tools` are given to the Analyst only."""
    smart, fast = chat_client("smart"), chat_client("fast")
    analyst = smart.as_agent(
        name="Analyst", instructions=ANALYST_INSTRUCTIONS, tools=tools or None,
        default_options={"temperature": 0.4},
    )
    narrator = fast.as_agent(name="Narrator", instructions=NARRATOR_INSTRUCTIONS, default_options={"temperature": 0.8})
    director = fast.as_agent(name="Director", instructions=DIRECTOR_INSTRUCTIONS, default_options={"temperature": 0.2})
    return MomentPipeline(AnalystAgent(analyst), NarratorAgent(narrator), DirectorAgent(director))
