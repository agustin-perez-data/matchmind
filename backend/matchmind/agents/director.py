"""Director agent: decides what reaches each viewer and how loudly (Personalize stage)."""

from __future__ import annotations

import json

from matchmind.agents.schemas import AnalystInsight, DirectorDecision, Narration, ViewerProfile

DIRECTOR_INSTRUCTIONS = """You are the Director agent of MatchMind: the producer deciding what each viewer sees.
You receive the key moment, the candidate cards (narration, analyst insight, risk alerts, a key stat)
and the viewer profile. Decide:
- show: which cards to display, most relevant first. Cards: narration, insight, risk, stat.
- priority 1-5: 5 interrupts the broadcast (goals, red cards, full-time), 1 is a quiet ticker line.
- headline: <= 8 words for the overlay title, in the viewer's language.
- personalized_note: ONLY for player_focus viewers, or when a risk alert concerns the viewer's
  favorite player; otherwise null.
House rules:
- casual viewers: narration first; add insight only for goals or the final whistle; never stat.
- analyst viewers: insight and stat first, narration after; include risk when an alert exists.
- commentator viewers: narration only, plus risk when an injury concern is the moment.
- player_focus viewers: narration first, insight if their player is involved, risk if it concerns them.
Never invent facts: everything in the headline and note must come from the cards or the context."""


class DirectorAgent:
    def __init__(self, agent):
        self.agent = agent

    async def direct(
        self,
        context: dict,
        insight: AnalystInsight | None,
        narration: Narration | None,
        profile: ViewerProfile,
    ) -> DirectorDecision:
        payload = {
            "moment": context.get("moment"),
            "clock": context.get("clock"),
            "score": context.get("score"),
            "teams": {tid: t.get("name") for tid, t in context.get("teams", {}).items()},
            "profile": profile.model_dump(),
            "cards": {
                "narration": narration.model_dump() if narration else None,
                "insight": insight.model_dump() if insight else None,
                "risk": context.get("risk_alerts", []),
                "stat": insight.key_stat if insight else None,
            },
        }
        prompt = "Produce the viewer's overlay decision for this moment (JSON):\n" + json.dumps(payload, ensure_ascii=False)
        response = await self.agent.run(prompt, options={"response_format": DirectorDecision})
        if response.value is None:
            raise ValueError(f"Director returned no structured output: {getattr(response, 'text', '')[:200]!r}")
        return response.value
