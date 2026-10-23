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
    ("player_focus", "en"): "English, play-by-play energy; the viewer follows ONE player like a fan does: centre the line on that player and what they did or could do in this moment (touches, chances, duels, their role in the play). If they were not involved, say what it means for them. Workload numbers only when they are the story.",
    ("player_focus", "es"): "Español rioplatense de relator; el espectador sigue a UN jugador como hincha: centrá la frase en ese jugador y en lo que hizo o puede hacer en esta jugada (toques, chances, duelos, su rol). Si no participó, decí qué significa para él. Datos de carga física solo si son la noticia.",
}


def _favorite(context: dict, profile: ViewerProfile) -> dict | None:
    if not profile.favorite_player_id:
        return None
    for key in ("players_involved", "watched_players", "risk_alerts"):
        for p in context.get(key, []):
            if p["player_id"] == profile.favorite_player_id:
                return {**p, "involved_in_this_moment": key == "players_involved"}
    return {"player_id": profile.favorite_player_id, "involved_in_this_moment": False}


ALLEGIANCE = {
    "en": "The viewer supports {team}. Take their side openly: celebrate their goals and chances, suffer the other side's, "
          "praise their players, grumble about decisions that go against them. Keep every fact straight; the bias is in the "
          "emotion and the framing, never in the numbers.",
    "es": "El espectador es hincha de {team}. Ponete de su lado sin disimulo: festejá sus goles y sus chances, sufrí las del "
          "rival, elogiá a sus jugadores, quejate de lo que le juega en contra. Los hechos siempre exactos; la parcialidad va en "
          "la emoción y el enfoque, nunca en los números.",
}


def _allegiance(context: dict, profile: ViewerProfile) -> str:
    if not profile.team_id:
        return "Neutral viewer: no side."
    name = context.get("teams", {}).get(profile.team_id, {}).get("name", profile.team_id)
    return ALLEGIANCE.get(profile.language, ALLEGIANCE["en"]).format(team=name)


def narrator_brief(context: dict, profile: ViewerProfile) -> str:
    """The viewer-specific part of the Narrator's prompt (shared with the concurrent orchestration)."""
    style = STYLE_GUIDES[(profile.mode, profile.language)]
    return (
        f"Viewer profile: mode={profile.mode}, language={profile.language}, team={profile.team_id or 'neutral'}, "
        f"favorite_player={json.dumps(_favorite(context, profile), ensure_ascii=False)}\n"
        f"Style guide: {style}\n"
        f"Allegiance: {_allegiance(context, profile)}\n"
    )


class NarratorAgent:
    def __init__(self, agent):
        self.agent = agent

    async def narrate(self, context: dict, profile: ViewerProfile) -> Narration:
        prompt = (
            narrator_brief(context, profile)
            + "\nKey moment context (JSON):\n"
            + json.dumps(context, ensure_ascii=False)
            + "\n\nWrite the commentary line now."
        )
        response = await self.agent.run(prompt, options={"response_format": Narration})
        if response.value is None:
            raise ValueError(f"Narrator returned no structured output: {getattr(response, 'text', '')[:200]!r}")
        return response.value
