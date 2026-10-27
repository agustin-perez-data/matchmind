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
    team_id: str | None = None  # the side the viewer supports; None = neutral

    @property
    def key(self) -> str:
        base = f"{self.mode}:{self.language}:{self.favorite_player_id or '-'}"
        return f"{base}:{self.team_id}" if self.team_id else base


FORECAST_HORIZON_MIN = 10


class Forecast(BaseModel):
    """A falsifiable call about the next 10 minutes; the Judge grades it against what happens."""

    dominant_team_id: str = Field(description="team_id expected to create more xG over the next 10 minutes")
    goal_probability: float = Field(ge=0.0, le=1.0, description="Probability that ANY goal is scored in the next 10 minutes")
    watch_player_id: str | None = Field(description="player_id most likely to be involved in a shot, goal, assist or knock next; null if no clear candidate")
    claim: str = Field(description="<= 25 words: the call in plain words, e.g. 'Thames keep the ball but Northbridge get the better chances'")


class AnalystInsight(BaseModel):
    """Why a key moment matters (Explain stage), plus a forecast that will be graded."""

    headline: str = Field(description="<= 10 words, broadcast caption style")
    why_it_matters: str = Field(description="<= 40 words, grounded in the numbers provided")
    tactical_read: str = Field(description="<= 40 words: control vs chaos, shape, rhythm, pressing")
    key_stat: str = Field(description="One number-backed fact from the context, e.g. 'xG 1.11 vs 0.71'")
    confidence: float = Field(ge=0.0, le=1.0, description="How well the data supports the read")
    forecast: Forecast


Verdict = Literal["called_it", "partly", "missed"]


class JudgeVerdict(BaseModel):
    """The Judge's reading of a graded forecast (the numbers come from code, the words from the Judge)."""

    verdict: Verdict
    summary: str = Field(description="<= 30 words: what the Analyst called and what actually happened, in the viewer's language")
    lesson: str = Field(description="<= 25 words: what the Analyst over- or under-estimated, or 'nothing' if the call was right")


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
    enforced: bool = Field(default=False, description="True when the house rules corrected the agent's decision (set in code, never by the model)")
