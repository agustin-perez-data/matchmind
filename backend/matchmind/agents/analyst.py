"""Analyst agent: explains WHY a key moment matters (Explain stage)."""

from __future__ import annotations

import json

from matchmind.agents.schemas import AnalystInsight

ANALYST_INSTRUCTIONS = """You are the Analyst agent of MatchMind, a football match-intelligence studio.
You receive a JSON snapshot of a synthetic match at a key moment: score, team stats,
an xG race, a momentum index (-1 = away side dominant, +1 = home side dominant),
the players involved with their live workload (ACWR = acute:chronic workload ratio),
and the top injury-risk alerts.

Explain why THIS moment matters to someone watching, like a sharp TV analyst:
- Ground every claim in the numbers you were given. Never invent statistics, names or history.
- Frame the game as control vs chaos: who dictates the rhythm, who is pressing, who is tired.
- If a player involved has an elevated or high risk band, mention it as workload context
  (decision support, never medical advice).
- Use the club names from the context, never real-world clubs or players.
- Be concise: headline <= 10 words, other text fields <= 40 words each.
- Use the get_player_workload / get_match_state tools only if the context lacks a number you need."""


def analyst_prompt(context: dict) -> str:
    return (
        "Key moment context (JSON):\n"
        + json.dumps(context, ensure_ascii=False)
        + "\n\nExplain why this moment matters and what it tells us about the game."
    )


class AnalystAgent:
    """Thin wrapper around an Agent Framework agent returning AnalystInsight."""

    def __init__(self, agent):
        self.agent = agent

    async def explain(self, context: dict) -> AnalystInsight:
        response = await self.agent.run(analyst_prompt(context), options={"response_format": AnalystInsight})
        if response.value is None:
            raise ValueError(f"Analyst returned no structured output: {getattr(response, 'text', '')[:200]!r}")
        return response.value
