"""Possession-chain match engine.

Simulates a match minute by minute as a stream of timestamped events:
passes, shots, tackles, interceptions, pressure, fouls, cards, subs,
goals and periodic physical-load samples.

Realism model (calibrated against public top-league aggregates):
- ~900 passes, ~80% completion, ~25 shots, ~2.7 goals per match
- xG decays exponentially with shot distance
- Fatigue is a LATENT state: it degrades performance and raises injury
  concern frequency, but is never serialized. Downstream agents only see
  observable workload (distance, sprints, speed, load history).
"""

from __future__ import annotations

import math
import random

from matchmind.sim.models import Player, Team

# Distance covered per minute on the ball-side of a top-flight match (metres)
POSITION_METRES_PER_MIN = {"GK": 45.0, "DF": 102.0, "MF": 118.0, "FW": 108.0}

FORMATION = {"GK": 1, "DF": 4, "MF": 4, "FW": 2}


INTERVENTION_TYPES = ("substitution", "tactic")


class MatchSimulator:
    """Simulates one match. `interventions` is an optional plan of coach actions
    applied at the start of a given minute (before that minute's possessions):

        {"minute": 62, "type": "substitution", "team_id": "THU", "player_off_id": "THU-04",
         "player_on_id": "THU-07" (optional), "reason": "coach" (optional)}
        {"minute": 60, "type": "tactic", "team_id": "NBF", "press_intensity": 0.9, "style": "direct"}

    Interventions never touch the RNG before their minute, so a run with the
    same seed is identical to the base match up to the first intervention and
    only diverges afterwards: a deterministic counterfactual branch.
    """

    def __init__(self, home: Team, away: Team, seed: int = 42, match_id: str = "M0001",
                 interventions: list[dict] | None = None):
        self.home = home
        self.away = away
        self.rng = random.Random(seed)
        # Cosmetic draws (knock descriptions) use their own stream so the injury
        # model can change without altering a single pass or shot of the match.
        self._flavour_rng = random.Random(seed ^ 0x5EED)
        self.match_id = match_id
        self.events: list[dict] = []
        self.score = {home.team_id: 0, away.team_id: 0}
        self._event_seq = 0
        self._second = 0  # running second within the current minute
        self.period = 1
        self.minute = 0
        self._subs_used = {home.team_id: 0, away.team_id: 0}
        self.interventions = [dict(iv) for iv in (interventions or [])]
        for iv in self.interventions:
            if iv.get("type") not in INTERVENTION_TYPES:
                raise ValueError(f"unknown intervention type {iv.get('type')!r}; expected one of {INTERVENTION_TYPES}")
            if iv.get("team_id") not in (home.team_id, away.team_id):
                raise ValueError(f"unknown team {iv.get('team_id')!r} in intervention")
            iv.setdefault("status", "pending")

    # ---------------------------------------------------------- interventions

    def _team(self, team_id: str) -> Team:
        return self.home if team_id == self.home.team_id else self.away

    def _apply_interventions(self) -> None:
        for iv in self.interventions:
            if iv["status"] != "pending" or iv["minute"] != self.minute:
                continue
            if self.period == 1 and iv["minute"] >= 45:
                continue  # minutes >= 45 belong to the second half; first-half stoppage is skipped
            iv["status"] = self._force_substitution(iv) if iv["type"] == "substitution" else self._apply_tactic(iv)

    def _force_substitution(self, iv: dict) -> str:
        team = self._team(iv["team_id"])
        off = next((p for p in team.on_pitch() if p.player_id == iv.get("player_off_id")), None)
        if off is None:
            return "skipped"
        bench = team.bench()
        on = next((p for p in bench if p.player_id == iv.get("player_on_id")), None)
        if on is None:
            on = next((p for p in bench if p.position == off.position), None)
        if on is None:
            return "skipped"
        off.on_pitch, on.on_pitch = False, True
        self._subs_used[team.team_id] += 1
        self._emit(
            "substitution",
            team,
            on,
            player_off_id=off.player_id,
            player_off_name=off.name,
            player_on_id=on.player_id,
            player_on_name=on.name,
            forced=True,
            reason=iv.get("reason", "coach"),
        )
        return "applied"

    def _apply_tactic(self, iv: dict) -> str:
        team = self._team(iv["team_id"])
        if "press_intensity" in iv:
            team.press_intensity = max(0.0, min(1.0, float(iv["press_intensity"])))
        if "style" in iv:
            if iv["style"] not in ("possession", "balanced", "direct"):
                return "skipped"
            team.style = iv["style"]
        self._emit("tactical_change", team, press_intensity=round(team.press_intensity, 2), style=team.style,
                   reason=iv.get("reason", "coach"))
        return "applied"

    # ------------------------------------------------------------------ setup

    def _pick_lineups(self) -> None:
        for team in (self.home, self.away):
            for pos, count in FORMATION.items():
                candidates = sorted(
                    [p for p in team.players if p.position == pos],
                    key=lambda p: p.passing + p.defending + p.shooting,
                    reverse=True,
                )
                for player in candidates[:count]:
                    player.on_pitch = True
            for player in team.players:
                # Congestion carries over: a heavy acute load means the player
                # starts the match already short of freshness.
                acute = sum(d["distance_m"] for d in player.load_history[-7:]) / 7.0
                chronic = sum(d["distance_m"] for d in player.load_history) / 28.0
                acwr = acute / chronic if chronic > 0 else 1.0
                player.acwr_pre = acwr
                player.fatigue = max(0.0, min(0.3, (acwr - 1.0) * 0.5))

    # ------------------------------------------------------------- event emit

    def _clock(self) -> str:
        return f"{self.minute:02d}:{self._second:02d}"

    def _tick(self, seconds: int = 4) -> None:
        self._second = min(59, self._second + self.rng.randint(2, seconds + 2))

    def _emit(self, etype: str, team: Team | None = None, player: Player | None = None, **fields) -> dict:
        self._event_seq += 1
        event = {
            "event_id": self._event_seq,
            "match_id": self.match_id,
            "period": self.period,
            "minute": self.minute,
            "second": self._second,
            "clock": self._clock(),
            "type": etype,
        }
        if team is not None:
            event["team_id"] = team.team_id
        if player is not None:
            event["player_id"] = player.player_id
            event["player_name"] = player.name
        event.update(fields)
        self.events.append(event)
        return event

    # ------------------------------------------------------------ coordinates

    def _attacking_right(self, team: Team) -> bool:
        home_right = self.period == 1
        return home_right if team is self.home else not home_right

    def _abs_coords(self, team: Team, x_team: float, y: float) -> tuple[float, float]:
        """Team-frame x (0=own goal, 100=opponent goal) -> absolute pitch coords."""
        x_abs = x_team if self._attacking_right(team) else 100.0 - x_team
        return round(x_abs, 1), round(y, 1)

    # ------------------------------------------------------------- selections

    def _weighted_player(self, team: Team, zone_x: float) -> Player:
        """Pick who is on the ball: midfielders dominate build-up, forwards
        appear more often the deeper the ball is in the final third."""
        weights = []
        for p in team.outfield():
            w = {"DF": 1.0, "MF": 1.6, "FW": 0.7}[p.position]
            if zone_x > 65:
                w = {"DF": 0.3, "MF": 1.2, "FW": 2.0}[p.position]
            weights.append(w)
        return self.rng.choices(team.outfield(), weights=weights, k=1)[0]

    def _attack_weight(self, team: Team, opponent: Team) -> float:
        w = team.overall ** 2
        # Trailing sides push harder late on
        if self.minute >= 70 and self.score[team.team_id] < self.score[opponent.team_id]:
            w *= 1.35
        return w

    # ----------------------------------------------------------------- events

    def _maybe_pressure(self, defending: Team, zone_x: float) -> bool:
        """Defending team presses the ball carrier; returns under_pressure."""
        p = defending.press_intensity * (0.45 if zone_x < 55 else 0.30)
        if self.rng.random() < p:
            presser = self._weighted_player(defending, 100 - zone_x)
            presser.sprints += 1
            self._emit(
                "pressure",
                defending,
                presser,
                target_zone_x=round(zone_x, 1),
                intensity=round(self.rng.uniform(0.5, 1.0) * defending.press_intensity, 2),
            )
            return True
        return False

    def _shot(self, team: Team, opponent: Team, shooter: Player, x_team: float, y: float, assist: Player | None) -> None:
        goal_y = 50.0
        dist = math.hypot((100 - x_team) * 1.05, (y - goal_y) * 0.68)  # metres
        xg = max(0.02, min(0.65, 0.9 * math.exp(-dist / 9.0)))
        shot_speed = round(self.rng.gauss(85, 12) * (0.8 + 0.4 * shooter.effective(shooter.shooting)), 1)
        x_abs, y_abs = self._abs_coords(team, x_team, y)

        p_goal = xg * (0.75 + 0.5 * shooter.effective(shooter.shooting))
        p_goal *= 1.2 - 0.45 * opponent.goalkeeper().defending
        roll = self.rng.random()
        if roll < p_goal:
            outcome = "goal"
        elif roll < p_goal + (0.40 + 0.2 * shooter.shooting) * (1 - p_goal):
            outcome = "saved"
        else:
            outcome = "off_target" if self.rng.random() < 0.7 else "blocked"

        self._emit(
            "shot",
            team,
            shooter,
            x=x_abs,
            y=y_abs,
            distance_m=round(dist, 1),
            xg=round(xg, 3),
            shot_speed_kmh=shot_speed,
            outcome=outcome,
            assist_player_id=assist.player_id if assist else None,
            assist_player_name=assist.name if assist else None,
        )
        if outcome == "goal":
            self.score[team.team_id] += 1
            self._emit(
                "goal",
                team,
                shooter,
                assist_player_id=assist.player_id if assist else None,
                assist_player_name=assist.name if assist else None,
                score={self.home.team_id: self.score[self.home.team_id],
                       self.away.team_id: self.score[self.away.team_id]},
            )
        elif outcome == "saved":
            gk = opponent.goalkeeper()
            self._emit("save", opponent, gk, shot_speed_kmh=shot_speed)

    def _turnover(self, winning: Team, losing: Team, zone_x: float, via: str) -> None:
        defender = self._weighted_player(winning, 100 - zone_x)
        x_abs, y_abs = self._abs_coords(losing, zone_x, self.rng.uniform(15, 85))
        self._emit(via, winning, defender, x=x_abs, y=y_abs)
        if via == "tackle":
            defender.sprints += 1
            # Tackles occasionally produce fouls, cards and knocks
            if self.rng.random() < 0.18:
                self._emit("foul", winning, defender, x=x_abs, y=y_abs)
                if self.rng.random() < (1 - defender.discipline) * 0.45:
                    self._emit("card", winning, defender, card="yellow")
        self._emit("possession_change", winning, won_by=via)

    def _maybe_injury_concern(self, player: Player) -> None:
        """Ground-truth injury model: latent state surfacing as an observable knock.

        Per-minute hazard, shaped after the sports-science evidence the Risk
        Monitor is meant to recover:
        - convex in accumulated fatigue (a tired player is disproportionately
          exposed; fatigue itself is latent but leaks into metres per minute),
        - a congestion spike when the pre-match ACWR exceeds the 1.3 sweet-spot
          ceiling (fully observable from the 28-day load history),
        - scaled by an individual susceptibility (latent, 0.5-1.0) so that
          players with identical load still differ, as in real squads.
        Draws exactly one random number per player-minute, so changing the
        formula never alters the rest of the match.
        """
        congestion = max(0.0, player.acwr_pre - 1.3) * 2.0
        load = 2.5 * player.fatigue ** 2 + congestion
        p = 0.004 * load * player.injury_susceptibility
        if self.rng.random() < p:
            self._emit(
                "injury_concern",
                None,
                player,
                team_id_affected=player.player_id.split("-")[0],
                detail=self._flavour_rng.choice(
                    ["holding hamstring", "slow to get up", "receiving treatment",
                     "stretching calf", "limping briefly"]
                ),
            )

    # ------------------------------------------------------------------ chain

    def _possession_chain(self) -> None:
        w_home = self._attack_weight(self.home, self.away)
        w_away = self._attack_weight(self.away, self.home)
        attacking = self.rng.choices([self.home, self.away], weights=[w_home, w_away], k=1)[0]
        defending = self.away if attacking is self.home else self.home

        style_len = {"possession": (5, 14), "balanced": (4, 10), "direct": (3, 7)}
        max_passes = self.rng.randint(*style_len[attacking.style])
        x = self.rng.uniform(20, 45)  # team frame: 0 own goal -> 100 opponent goal
        passer = self._weighted_player(attacking, x)

        for _ in range(max_passes):
            under_pressure = self._maybe_pressure(defending, x)
            receiver = self._weighted_player(attacking, x)
            while receiver is passer:
                receiver = self._weighted_player(attacking, x)

            long_ball = attacking.style == "direct" and self.rng.random() < 0.3
            pass_dist = abs(self.rng.gauss(32 if long_ball else 16, 7))
            forward = self.rng.random() < 0.62
            difficulty = min(0.95, pass_dist / 55 + (0.18 if forward else 0.0) + (0.22 if under_pressure else 0.0))
            p_complete = max(0.50, min(0.97, 0.60 + passer.effective(passer.passing) * 0.50 - difficulty * 0.32))

            y = self.rng.uniform(10, 90)
            x_end_team = min(98.0, x + (pass_dist * 0.7 if forward else -pass_dist * 0.3))
            x0, y0 = self._abs_coords(attacking, x, y)
            x1, y1 = self._abs_coords(attacking, x_end_team, self.rng.uniform(10, 90))
            complete = self.rng.random() < p_complete
            self._emit(
                "pass",
                attacking,
                passer,
                receiver_id=receiver.player_id,
                receiver_name=receiver.name,
                x=x0, y=y0, end_x=x1, end_y=y1,
                distance_m=round(pass_dist, 1),
                pass_difficulty=round(difficulty, 2),
                ball_speed_kmh=round(self.rng.gauss(45, 10) + pass_dist * 0.5, 1),
                under_pressure=under_pressure,
                outcome="complete" if complete else "incomplete",
            )
            self._tick()
            if not complete:
                via = "interception" if self.rng.random() < 0.6 else "tackle"
                self._turnover(defending, attacking, x_end_team, via)
                return

            x = x_end_team
            passer = receiver
            if forward and pass_dist > 20:
                receiver.sprints += 1
                speed = round(receiver.effective(receiver.pace) * 11 + 24, 1)
                receiver.top_speed_kmh = max(receiver.top_speed_kmh, speed)

            # In the final third: decide between shooting and recycling
            if x > 68 and self.rng.random() < 0.30 + 0.15 * (x - 68) / 32:
                shooter = self._weighted_player(attacking, x)
                assist = passer if passer is not shooter else None
                self._shot(attacking, defending, shooter, x, self.rng.uniform(30, 70), assist=assist)
                self._tick()
                self._emit("possession_change", defending, won_by="restart")
                return

        # Chain fizzles out without a shot
        self._turnover(defending, attacking, x, "interception" if self.rng.random() < 0.5 else "tackle")

    # ------------------------------------------------------------ maintenance

    def _update_physical(self) -> None:
        for team in (self.home, self.away):
            for p in team.on_pitch():
                p.minutes_played += 1
                base = POSITION_METRES_PER_MIN[p.position]
                p.distance_m += max(0.0, self.rng.gauss(base, 12) * (1 - 0.25 * p.fatigue))
                p.fatigue = min(1.0, p.fatigue + 0.012 * (1.25 - p.stamina) + 0.004 * (p.sprints / max(1, p.minutes_played)))
                if p.top_speed_kmh == 0.0:
                    p.top_speed_kmh = round(p.pace * 9 + 22, 1)
                self._maybe_injury_concern(p)

    def _emit_physical_samples(self) -> None:
        for team in (self.home, self.away):
            for p in team.on_pitch():
                self._emit(
                    "physical_sample",
                    team,
                    p,
                    minutes_played=p.minutes_played,
                    distance_m=round(p.distance_m, 1),
                    sprints=p.sprints,
                    top_speed_kmh=p.top_speed_kmh,
                )

    def _maybe_substitution(self) -> None:
        if not (55 <= self.minute <= 82):
            return
        for team in (self.home, self.away):
            if self._subs_used[team.team_id] >= 3 or self.rng.random() > 0.10:
                continue
            tired = max(team.outfield(), key=lambda p: p.fatigue)
            options = [b for b in team.bench() if b.position == tired.position]
            if not options:
                continue
            fresh = options[0]
            tired.on_pitch, fresh.on_pitch = False, True
            self._subs_used[team.team_id] += 1
            self._emit(
                "substitution",
                team,
                fresh,
                player_off_id=tired.player_id,
                player_off_name=tired.name,
                player_on_id=fresh.player_id,
                player_on_name=fresh.name,
            )

    # -------------------------------------------------------------------- run

    def run(self) -> dict:
        self._pick_lineups()
        starters = [p.player_id for team in (self.home, self.away) for p in team.on_pitch()]
        halves = [
            (1, 0, 45 + self.rng.randint(1, 3)),
            (2, 45, 90 + self.rng.randint(2, 6)),
        ]
        self._emit("kickoff", self.home, home_attacking_right=True)
        for period, start, end in halves:
            self.period = period
            if period == 2:
                self.minute, self._second = start, 0
                self._emit("second_half_kickoff", self.away, home_attacking_right=False)
            for minute in range(start, end):
                self.minute = minute
                self._second = self.rng.randint(0, 15)
                self._apply_interventions()
                # ~2 possessions per minute (~190 per match, realistic tempo)
                self._possession_chain()
                self._possession_chain()
                if self.rng.random() < 0.15:
                    self._possession_chain()
                self._update_physical()
                self._maybe_substitution()
                if minute % 5 == 4:
                    self._emit_physical_samples()
            self._emit(
                "half_time" if period == 1 else "full_time",
                None,
                score={self.home.team_id: self.score[self.home.team_id],
                       self.away.team_id: self.score[self.away.team_id]},
            )
        self._emit_physical_samples()
        for iv in self.interventions:
            if iv["status"] == "pending":
                iv["status"] = "skipped"
        return {"events": self.events, "score": dict(self.score), "interventions": self.interventions,
                "starters": starters}
