"""Fictional league generator.

Every club, player and name here is invented. Any resemblance to real
clubs or players is coincidental — this is a hard requirement of the
hackathon (synthetic data only, no third-party trademarks).
"""

from __future__ import annotations

import random

from matchmind.sim.models import Player, Team

# 8 fictional clubs loosely covering the strength spectrum of a top league
CLUBS = [
    # (team_id, name, short, color, overall, press, style)
    ("THU", "Thames United", "Thames", "#8B0000", 0.86, 0.75, "possession"),
    ("NBF", "Northbridge FC", "Northbridge", "#1E3A8A", 0.84, 0.82, "balanced"),
    ("IRA", "Ironfield Athletic", "Ironfield", "#B45309", 0.78, 0.68, "direct"),
    ("MRV", "Mersey Rovers", "Rovers", "#065F46", 0.76, 0.60, "balanced"),
    ("CRC", "Crowmoor City", "Crowmoor", "#6D28D9", 0.72, 0.55, "possession"),
    ("ALV", "Albion Vale", "Albion", "#0E7490", 0.68, 0.50, "direct"),
    ("SGW", "Southgate Wanderers", "Wanderers", "#9D174D", 0.64, 0.45, "balanced"),
    ("KPF", "Kestrel Park FC", "Kestrel", "#374151", 0.60, 0.40, "direct"),
]

# International mix typical of a top-flight squad; surnames are invented
FIRST_NAMES = [
    "Marcus", "Kai", "Mateo", "Thiago", "Emeka", "Yusuf", "Declan", "Bruno",
    "Luka", "Sadio", "Oliver", "Rafael", "Idris", "Jordan", "Enzo", "Takumi",
    "Pablo", "Noah", "Amara", "Viktor", "Callum", "Diego", "Moussa", "Felix",
    "Andriy", "Harvey", "Nicolas", "Sergei", "Tobias", "Wilfried",
]
SURNAMES = [
    "Okafor", "Vantham", "Silveira", "Brackley", "Dumont", "Kessler",
    "Marwood", "Osei-Tutu", "Ferrant", "Halloway", "Zubiri", "Craven",
    "Mbeki", "Torrisi", "Lindqvist", "Abara", "Pendry", "Roussel",
    "Kovanen", "Delacroix", "Whitlow", "Barzagli-Nunes", "Chowdry",
    "Estevez", "Grimshaw", "Nakamura-Reyes", "Ojo", "Petrakis", "Stanhope",
    "Varela",
]

# 4-4-2-ish squad template: position and base attribute profile per slot
SQUAD_TEMPLATE = (
    [("GK", 1)] * 2
    + [("DF", 2)] * 6
    + [("MF", 3)] * 6
    + [("FW", 4)] * 4
)


def _player_attrs(rng: random.Random, position: str, overall: float) -> dict:
    """Attribute profile centred on club strength, shaped by position."""

    def a(bias: float = 0.0, spread: float = 0.12) -> float:
        return max(0.2, min(0.99, rng.gauss(overall + bias, spread)))

    profiles = {
        "GK": dict(passing=a(-0.15), shooting=a(-0.45), defending=a(0.05), pace=a(-0.25)),
        "DF": dict(passing=a(-0.08), shooting=a(-0.30), defending=a(0.08), pace=a(-0.05)),
        "MF": dict(passing=a(0.08), shooting=a(-0.08), defending=a(-0.05), pace=a(0.0)),
        "FW": dict(passing=a(-0.03), shooting=a(0.10), defending=a(-0.25), pace=a(0.08)),
    }
    attrs = profiles[position]
    attrs["stamina"] = a(0.0, 0.10)
    attrs["discipline"] = max(0.2, min(0.99, rng.gauss(0.75, 0.12)))
    return attrs


def _load_history(rng: random.Random, congested: bool) -> list:
    """28 days of observable workload.

    'Congested' players carry a heavy acute (last-7-day) load relative to
    their chronic load — exactly the pattern the Load & Risk Monitor should
    flag via ACWR. Roughly a quarter of each squad is congested.
    """
    history = []
    for day in range(-28, 0):
        rest_day = rng.random() < 0.25
        base = 0.0 if rest_day else rng.gauss(5200, 900)  # training day metres
        # Match days roughly every 4-7 days push the distance up
        if not rest_day and rng.random() < 0.18:
            base = rng.gauss(9800, 700)
        # Congested players played extra matches in the final week
        if congested and day >= -7 and rng.random() < 0.45:
            base = max(base, rng.gauss(10200, 600))
        distance = max(0.0, base)
        hsr = distance * max(0.0, rng.gauss(0.085, 0.02))
        history.append(
            {"day": day, "distance_m": round(distance, 1), "hsr_m": round(hsr, 1)}
        )
    return history


def build_team(spec: tuple, rng: random.Random) -> Team:
    team_id, name, short, color, overall, press, style = spec
    team = Team(
        team_id=team_id,
        name=name,
        short_name=short,
        primary_color=color,
        overall=overall,
        press_intensity=press,
        style=style,
    )
    used_names = set()
    for idx, (position, _line) in enumerate(SQUAD_TEMPLATE):
        while True:
            full_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
            if full_name not in used_names:
                used_names.add(full_name)
                break
        attrs = _player_attrs(rng, position, overall)
        team.players.append(
            Player(
                player_id=f"{team_id}-{idx + 1:02d}",
                name=full_name,
                position=position,
                shirt_number=idx + 1,
                injury_susceptibility=rng.uniform(0.5, 1.0),  # latent; see engine._maybe_injury_concern
                load_history=_load_history(rng, congested=rng.random() < 0.25),
                **attrs,
            )
        )
    return team


def build_league(seed: int = 7) -> dict:
    """Deterministic league: same seed, same clubs, squads and load history."""
    rng = random.Random(seed)
    return {spec[0]: build_team(spec, rng) for spec in CLUBS}
