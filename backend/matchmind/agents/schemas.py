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


class DirectorDecision(BaseModel):
    """What reaches this viewer and how loudly (Personalize stage)."""

    show: list[Card] = Field(description="Cards to display, most relevant first")
    priority: int = Field(ge=1, le=5, description="5 interrupts the broadcast, 1 is a quiet ticker item")
    headline: str = Field(description="<= 8 words for the overlay title")
    personalized_note: str | None = Field(description="Only for player_focus viewers or when a risk alert concerns their player")
