"""Coach agent: turns a risk alert into an intervention, then the engine shows the counterfactual.

    risk alert / injury concern ──► Coach (LLM) proposes substitution | tactic | hold
                                       └──► simulate_intervention (deterministic branch)
                                                └──► {"kind": "coach", proposal, branch comparison}

The LLM decides *what*; the simulator decides *what would have happened*.
"""

from __future__ import annotations

import json
import logging
import time

from matchmind.agents.schemas import CoachProposal

log = logging.getLogger("matchmind.agents.coach")

COACH_INSTRUCTIONS = """You are the Coach agent of MatchMind, advising the bench of a football club during a match.
You receive a trigger (an injury-risk alert from the Load & Risk Monitor, or an injury concern that
just happened), the player's live workload (minutes, distance, sprints, ACWR = acute:chronic workload
ratio, metres-per-minute vs the position norm, previous knocks), the bench options of the same
position, the score and the match state.

Decide ONE of:
- substitution: take the player off (player_off_id) for a bench option (player_on_id, or null for the
  default same-position replacement). Use when the risk is high and the bench option is sensible.
- tactic: change the team's pressing intensity (0-1) and/or style (possession|balanced|direct) to
  protect the squad, e.g. lower the press when several players are at risk.
- hold: do nothing yet (low urgency, or the player is decisive and the risk is only elevated).

Rules: minute must be >= the current minute. Ground the rationale in the numbers you were given
(ACWR, effort drop, minutes, concerns, score). Never invent players: only use ids from the context.
Workload is decision support, never a medical diagnosis. Keep rationale <= 40 words."""


def build_coach_context(trigger_payload: dict, snapshot: dict, meta: dict, trigger: str = "risk_alert") -> dict:
    """Compact JSON for the Coach: the player, their bench alternatives, the team and the match."""
    pid = trigger_payload["player_id"]
    players = snapshot.get("players", {})
    player = players.get(pid, {"player_id": pid})
    team_id = player.get("team_id") or trigger_payload.get("team_id")
    team_meta = meta["teams"].get(team_id, {})
    bench = [
        {k: q[k] for k in ("player_id", "name", "position", "minutes_played", "acwr_pre_match", "risk_band")}
        for q in players.values()
        if q.get("team_id") == team_id and not q.get("on_pitch") and q.get("minutes_played", 0) == 0
        and q.get("position") == player.get("position")
    ]
    at_risk = [w for w in trigger_payload.get("other_windows", [])]
    return {
        "trigger": trigger,
        "trigger_detail": {k: v for k, v in trigger_payload.items() if k != "other_windows"},
        "match_id": snapshot["match_id"],
        "clock": snapshot["clock"],
        "minute": snapshot["minute"],
        "period": snapshot["period"],
        "score": dict(snapshot["score"]),
        "home_id": snapshot["home_id"],
        "away_id": snapshot["away_id"],
        "team": {"team_id": team_id, "name": team_meta.get("name", team_id), "style": team_meta.get("style"),
                 "stats": {k: snapshot["teams"].get(team_id, {}).get(k) for k in ("goals", "xg", "shots", "possession_pct", "pressures")}},
        "player": {k: v for k, v in player.items() if k in (
            "player_id", "name", "team_id", "position", "minutes_played", "distance_m", "sprints", "sprints_per_min",
            "top_speed_kmh", "acwr_pre_match", "acwr_live", "risk_band", "effort_ratio", "effort_ratio_recent", "injury_concerns")},
        "bench_options": bench,
        "other_players_at_risk": at_risk[:4],
        "momentum": snapshot.get("momentum"),
    }


class CoachAgent:
    def __init__(self, agent):
        self.agent = agent

    async def propose(self, context: dict) -> CoachProposal:
        prompt = (
            "Bench situation (JSON):\n" + json.dumps(context, ensure_ascii=False)
            + "\n\nDecide the intervention now (or hold)."
        )
        response = await self.agent.run(prompt, options={"response_format": CoachProposal})
        if response.value is None:
            raise ValueError(f"Coach returned no structured output: {getattr(response, 'text', '')[:200]!r}")
        return response.value


class CoachPipeline:
    """Coach proposal + deterministic counterfactual, failure-isolated."""

    def __init__(self, coach: CoachAgent, tools):
        self.coach, self.tools = coach, tools

    async def run(self, context: dict) -> dict:
        t0 = time.perf_counter()
        errors: list[str] = []
        proposal = branch = None
        try:
            proposal = await self.coach.propose(context)
        except Exception as exc:  # noqa: BLE001
            log.warning("coach failed: %r", exc)
            errors.append(f"coach: {exc!r}")
        if proposal is not None and proposal.action != "hold":
            try:
                minute = max(int(proposal.minute), int(context.get("minute", 0)))
                branch = self.tools.simulate_intervention(
                    context["match_id"], minute, proposal.action, proposal.team_id,
                    player_off_id=proposal.player_off_id, player_on_id=proposal.player_on_id,
                    press_intensity=proposal.press_intensity, style=proposal.style,
                )
            except (KeyError, ValueError) as exc:
                log.warning("branch simulation failed: %r", exc)
                errors.append(f"simulate_intervention: {exc!r}")
        return {
            "trigger": context.get("trigger"),
            "trigger_detail": context.get("trigger_detail"),
            "clock": context.get("clock"),
            "minute": context.get("minute"),
            "score": context.get("score"),
            "player": context.get("player"),
            "proposal": proposal.model_dump() if proposal else None,
            "branch": branch,
            "errors": errors,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }
