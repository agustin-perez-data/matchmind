"""Director agent: decides what reaches each viewer and how loudly (Personalize stage)."""

from __future__ import annotations

import json
import logging

from matchmind.agents.schemas import AnalystInsight, Card, DirectorDecision, Narration, ViewerProfile

log = logging.getLogger("matchmind.agents.director")

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


# The house rules the prompt states, as code: the LLM proposes an order, a headline and a personal note; the
# house guarantees what each seat is allowed to see. A decision that broke a rule is corrected and flagged,
# so the Control room can show how often the agent and the house disagreed.
MUST_HAVE: dict[str, tuple[Card, ...]] = {"casual": ("narration",), "analyst": ("insight",), "commentator": ("narration",), "player_focus": ("narration",)}
NEVER: dict[str, tuple[Card, ...]] = {"casual": ("stat",), "commentator": ("insight", "stat"), "player_focus": ("stat",), "analyst": ()}
# priority floor and ceiling by moment kind: a goal interrupts the broadcast, a routine chance never does
PRIORITY_BOUNDS: dict[str, tuple[int, int]] = {"goal": (4, 5), "full_time": (4, 5), "card": (2, 5), "big_chance": (2, 4),
                                               "half_time": (2, 4), "injury_concern": (2, 4), "chance": (1, 3), "substitution": (1, 3)}
INTERRUPT_PRIORITY = 4


def house_rules(profile: ViewerProfile, context: dict, insight_present: bool) -> tuple[set[Card], set[Card]]:
    """(cards this seat must see, cards it must not) for this moment."""
    mode = profile.mode
    kind = (context.get("moment") or {}).get("kind")
    involved = {p.get("player_id") for p in context.get("players_involved", []) if isinstance(p, dict)}
    alerts = [a for a in context.get("risk_alerts", []) if isinstance(a, dict)]
    concerns_fav = bool(profile.favorite_player_id and any(a.get("player_id") == profile.favorite_player_id for a in alerts))
    must: set[Card] = set(MUST_HAVE.get(mode, ()))
    never: set[Card] = set(NEVER.get(mode, ()))
    if mode == "casual" and insight_present and kind in ("goal", "full_time"):
        must.add("insight")
    if mode == "casual" and kind not in ("goal", "full_time"):
        never.add("insight")
    if mode == "analyst":
        must.add("stat")
        if alerts:
            must.add("risk")
    if mode == "commentator" and kind == "injury_concern":
        must.add("risk")
    if mode == "player_focus":
        if insight_present and profile.favorite_player_id in involved:
            must.add("insight")
        else:
            never.add("insight")
        if concerns_fav:
            must.add("risk")
        else:
            never.add("risk")
    if not insight_present:
        must.discard("insight")
        must.discard("stat")
    return must, never


def enforce(decision: DirectorDecision, context: dict, must: set[Card], never: set[Card]) -> tuple[DirectorDecision, bool]:
    """Keep the agent's order, drop what the seat may not see, add what it must, bound the priority. Returns (decision, changed)."""
    show = [c for c in decision.show if c not in never]
    for c in must:
        if c not in show:
            show.append(c)
    lo, hi = PRIORITY_BOUNDS.get((context.get("moment") or {}).get("kind") or "", (1, 5))
    priority = min(hi, max(lo, decision.priority))
    changed = show != list(decision.show) or priority != decision.priority
    if not changed:
        return decision, False
    return decision.model_copy(update={"show": show, "priority": priority}), True


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
        must, never = house_rules(profile, context, insight is not None)
        decision, changed = enforce(response.value, context, must, never)
        if changed:
            log.info("Director overruled for %s at %s: %s -> %s, priority %s", profile.key, context.get("clock"),
                     list(response.value.show), decision.show, decision.priority)
        return decision.model_copy(update={"enforced": changed})
