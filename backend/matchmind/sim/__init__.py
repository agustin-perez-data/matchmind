"""Synthetic, football-realistic match simulator.

Generates event streams (passes, shots, tackles, pressure, physical load)
for entirely fictional clubs and players. No real match data is used.
"""

from matchmind.sim.engine import MatchSimulator
from matchmind.sim.league import build_league

__all__ = ["MatchSimulator", "build_league"]
