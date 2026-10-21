"""Core data models for the MatchMind synthetic match simulator."""

from __future__ import annotations

from dataclasses import dataclass, field

PITCH_LENGTH = 105.0  # metres
PITCH_WIDTH = 68.0  # metres


@dataclass
class Player:
    player_id: str
    name: str
    position: str  # GK | DF | MF | FW
    shirt_number: int
    # Ability attributes in [0, 1]
    passing: float
    shooting: float
    defending: float
    pace: float
    stamina: float
    discipline: float
    # Latent state. Hidden from every downstream agent: the Load & Risk
    # Monitor must infer risk purely from observable workload metrics.
    injury_susceptibility: float = 0.75
    fatigue: float = 0.0
    acwr_pre: float = 1.0  # pre-match acute:chronic workload ratio (derived from observable load history)
    # Observable: last 28 days of workload, one dict per day
    # {"day": -28..-1, "distance_m": float, "hsr_m": float} (hsr = high-speed running)
    load_history: list = field(default_factory=list)
    # In-match state
    on_pitch: bool = False
    minutes_played: int = 0
    distance_m: float = 0.0
    sprints: int = 0
    top_speed_kmh: float = 0.0

    def effective(self, attr_value: float) -> float:
        """Ability degraded by current fatigue."""
        return attr_value * (1.0 - 0.35 * self.fatigue)


@dataclass
class Team:
    team_id: str
    name: str
    short_name: str
    primary_color: str
    overall: float  # 0-1 squad strength
    press_intensity: float  # 0-1 how aggressively the team presses
    style: str  # "possession" | "direct" | "balanced"
    secondary_color: str = "#ffffff"
    pattern: str = "solid"  # kit pattern for the crest: solid | halves | stripes | hoops | sash | sleeves
    city: str = ""  # fictional region, for flavour only
    players: list = field(default_factory=list)

    def on_pitch(self) -> list:
        return [p for p in self.players if p.on_pitch]

    def bench(self) -> list:
        return [p for p in self.players if not p.on_pitch and p.minutes_played == 0]

    def outfield(self) -> list:
        return [p for p in self.on_pitch() if p.position != "GK"]

    def goalkeeper(self) -> Player:
        return next(p for p in self.on_pitch() if p.position == "GK")
