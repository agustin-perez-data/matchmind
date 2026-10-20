"""Narrator agent: one line of live commentary tuned to a viewer profile (Render stage)."""

from __future__ import annotations

import json

from matchmind.agents.schemas import Narration, ViewerProfile

NARRATOR_INSTRUCTIONS = """You are the Narrator agent of MatchMind, a live football broadcast engine.
For each key moment you write ONE short piece of commentary (<= 45 words) that matches the
viewer's style guide exactly. Use only the facts in the context: club and player names as given,
the score, the clock, the numbers. Never mention real-world clubs, players or competitions.
Never add medical claims; an injury concern is "a worry", nothing more.
Return the text in the requested language and echo the viewer's mode and language."""

STYLE_GUIDES = {
    ("analyst", "en"): "English, analytical co-commentator tone, calm, cite exactly one number (xG, possession, momentum or workload).",
    ("analyst", "es"): "Español neutro rioplatense, tono de comentarista analítico, sereno, citá exactamente un número.",
    ("casual", "en"): "Plain, casual, fun English for someone who barely follows football; no jargon, no numbers, at most one emoji.",
    ("casual", "es"): "Español casual y divertido para alguien que casi no sigue fútbol; sin jerga ni números, máximo un emoji.",
    ("commentator", "en"): "English play-by-play commentator, high energy, present tense, short punchy sentences.",
    ("commentator", "es"): "Relator rioplatense de radio (voseo, ¡GOOOL! en los goles, pasión, frases cortas); español del Río de la Plata.",
    ("player_focus", "en"): "English; the viewer follows ONE player: centre the line on that player, and if they were not involved, relate the moment to them (their workload, their role, what it means for them).",
    ("player_focus", "es"): "Español rioplatense; el espectador sigue a UN jugador: centrá la frase en ese jugador y, si no participó, relacioná el momento con él.",
}


def _favorite(context: dict, profile: ViewerProfile) -> dict | None:
    if not profile.favorite_player_id:
        return None
    for key in ("players_involved", "watched_players", "risk_alerts"):
        for p in context.get(key, []):
            if p["player_id"] == profile.favorite_player_id:
                return {**p, "involved_in_this_moment": key == "players_involved"}
    return {"player_id": profile.favorite_player_id, "involved_in_this_moment": False}


class NarratorAgent:
    def __init__(self, agent):
        self.agent = agent

    async def narrate(self, context: dict, profile: ViewerProfile) -> Narration:
        style = STYLE_GUIDES[(profile.mode, profile.language)]
        prompt = (
            f"Viewer profile: mode={profile.mode}, language={profile.language}, "
            f"favorite_player={json.dumps(_favorite(context, profile), ensure_ascii=False)}\n"
            f"Style guide: {style}\n\n"
            "Key moment context (JSON):\n"
            + json.dumps(context, ensure_ascii=False)
            + "\n\nWrite the commentary line now."
        )
        response = await self.agent.run(prompt, options={"response_format": Narration})
        if response.value is None:
            raise ValueError(f"Narrator returned no structured output: {getattr(response, 'text', '')[:200]!r}")
        return response.value
