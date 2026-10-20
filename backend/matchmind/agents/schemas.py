"""Structured contracts between the LLM agents and the rest of the system.

The three output models are used as `response_format` for Azure OpenAI
structured outputs, so every field is required (no defaults) and nullable
fields are typed `X | None`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["analyst", "casual", "commentator", "player_focus"]
Language = Literal["en", "es"]
Card = Literal["narration", "insight", "risk", "stat"]


class ViewerProfile(BaseModel):
    """What one viewer wants from the broadcast (Personalize stage input)."""

    mode: Mode = "analyst"
    language: Language = "en"
    favorite_player_id: str | None = None

    @property
    def key(self) -> str:
        return f"{self.mode}:{self.language}:{self.favorite_player_id or '-'}"


class AnalystInsight(BaseModel):
    """Why a key moment matters (Explain stage)."""

    headline: str = Field(description="<= 10 words, broadcast caption style")
    why_it_matters: str = Field(description="<= 40 words, grounded in the numbers provided")
    tactical_read: str = Field(description="<= 40 words: control vs chaos, shape, rhythm, pressing")
    key_stat: str = Field(description="One number-backed fact from the context, e.g. 'xG 1.11 vs 0.71'")
    confidence: float = Field(ge=0.0, le=1.0, description="How well the data supports the read")


class Narration(BaseModel):
    """One line of live commentary for a specific viewer profile (Render stage)."""

    text: str = Field(description="<= 45 words, ready to display")
    language: Language
    mode: Mode


CoachAction = Literal["substitution", "tactic", "hold"]


class CoachProposal(BaseModel):
    """What the Coach agent wants to do about a risk alert (then simulated as a branch)."""

    action: CoachAction
    team_id: str
    player_off_id: str | None = Field(description="For substitution: the player to take off")
    player_on_id: str | None = Field(description="For substitution: bench player to bring on, or null for same-position default")
    press_intensity: float | None = Field(description="For tactic: new pressing intensity 0-1, or null")
    style: Literal["possession", "balanced", "direct"] | None = Field(description="For tactic: new style, or null")
    minute: int = Field(ge=0, le=100, description="Match minute at which to apply the intervention (>= current minute)")
    rationale: str = Field(description="<= 40 words, grounded in the workload numbers provided")
    urgency: int = Field(ge=1, le=5)
    expected_effect: str = Field(description="<= 25 words: what the coach expects to change")


class DirectorDecision(BaseModel):
    """What reaches this viewer and how loudly (Personalize stage)."""

    show: list[Card] = Field(description="Cards to display, most relevant first")
    priority: int = Field(ge=1, le=5, description="5 interrupts the broadcast, 1 is a quiet ticker item")
    headline: str = Field(description="<= 8 words for the overlay title")
    personalized_note: str | None = Field(description="Only for player_focus viewers or when a risk alert concerns their player")
