"""Synthetic positional data: 22 players and the ball, one frame per match second.

The engine decides what happens (passes, shots, duels) and where the ball is at each
event. This module places the players so that every event is consistent with them: the
passer is on the ball when the pass leaves, the receiver is where it lands, the shooter is
where the shot is taken, the defender is where the ball is won. Between events, players
follow a positional model: a formation anchor, a block that shifts and compresses with the
ball, role-weighted attraction to it, the nearest defenders pressing the carrier, inertia
with a top speed, and a little noise from the module's own random stream.

What this is: a positional model driven by the event stream, deterministic per seed.
What this is not: measured tracking. Nothing here is drawn from the engine's RNG, so
building frames never changes a match, a branch or an agent cache.

    frames = build_tracking(events, meta)
    frame  = {"kind": "frame", "period", "minute", "second", "ball": [x, y],
              "carrier": player_id | None, "players": {player_id: [x, y]}}

Coordinates are absolute, 0-100 on both axes, like the events; metres are 105 x 68.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

PITCH_LENGTH_M, PITCH_WIDTH_M = 105.0, 68.0
TRACKING_SALT = 0x7A4C

# Formation anchors in team frame (attacking towards x = 100), 1-4-4-2 like the engine's XI.
ANCHORS: dict[str, list[tuple[float, float]]] = {
    "GK": [(6.0, 50.0)],
    "DF": [(22.0, 15.0), (20.0, 38.0), (20.0, 62.0), (22.0, 85.0)],
    "MF": [(45.0, 12.0), (42.0, 38.0), (42.0, 62.0), (45.0, 88.0)],
    "FW": [(68.0, 38.0), (68.0, 62.0)],
}
ATTRACTION = {"FW": 0.25, "MF": 0.20, "DF": 0.08, "GK": 0.0}
ATTRACTION_RADIUS_M = 30.0
PRESS_RADIUS_M = 2.0
V_MAX_MPS, V_SPRINT_MPS = 7.0, 12.0
APPOINTMENT_HORIZON_S = 4
DEAD_BALL_CARRY_S = 3
NOISE_SIGMA, NOISE_CLAMP = 0.6, 4.0
COORD_TYPES = ("pass", "shot", "tackle", "interception", "foul")


@dataclass
class Keyframe:
    t: int
    x: float
    y: float
    carrier: str | None
    hold: bool  # the carrier keeps the ball until the next keyframe (vs. a ball in flight)
    order: int = 0


@dataclass
class _Player:
    pid: str
    team: str
    position: str
    slot: int
    x: float = 0.0
    y: float = 0.0
    nx: float = 0.0  # noise
    ny: float = 0.0
    appointments: list[tuple[int, float, float]] = field(default_factory=list)


PERIOD_BASE = 100_000  # seconds are keyed per period: first-half stoppage at 45:xx never collides with 45:xx of the second half


def _t(e: dict) -> int:
    """Period-aware time key."""
    return int(e["period"]) * PERIOD_BASE + int(e["minute"]) * 60 + int(e["second"])


def _real(e: dict) -> int:
    return int(e["minute"]) * 60 + int(e["second"])


def _dist_m(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot((ax - bx) / 100 * PITCH_LENGTH_M, (ay - by) / 100 * PITCH_WIDTH_M)


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


class _Model:
    def __init__(self, events: list[dict], meta: dict):
        self.events = events
        self.meta = meta
        self.home, self.away = meta["home_id"], meta["away_id"]
        self.rng = random.Random(int(meta.get("seed", 0)) ^ TRACKING_SALT)
        self.press = {tid: float(meta["teams"][tid].get("press_intensity", 0.6)) for tid in (self.home, self.away)}
        self.players: dict[str, _Player] = {}
        self.position_of: dict[str, str] = {}
        self.team_of: dict[str, str] = {}
        self.gk_of: dict[str, str] = {}
        self.starters: dict[str, list[str]] = {self.home: [], self.away: []}
        for tid in (self.home, self.away):
            for p in meta["teams"][tid]["players"]:
                self.position_of[p["player_id"]] = p["position"]
                self.team_of[p["player_id"]] = tid
                if p.get("starter"):
                    self.starters[tid].append(p["player_id"])
        self.keyframes: list[Keyframe] = []
        self.subs: list[tuple[int, str, str]] = []  # (t, off, on)
        self.pressures: list[tuple[int, str]] = []
        self.periods: list[tuple[int, int, int, bool]] = []  # (period, t_start, t_end, home_attacking_right)

    # ------------------------------------------------------------ pre-pass: ball, appointments, rosters

    def _key(self, t: int, x: float, y: float, carrier: str | None, hold: bool) -> None:
        self.keyframes.append(Keyframe(t, _clamp(float(x), 0.0, 100.0), _clamp(float(y), 0.0, 100.0), carrier, hold, len(self.keyframes)))

    def _appoint(self, pid: str | None, t: int, x: float, y: float) -> None:
        if pid and pid in self.position_of:
            self.players_appointments.setdefault(pid, []).append((t, _clamp(float(x), 0.0, 100.0), _clamp(float(y), 0.0, 100.0)))

    def prepass(self) -> None:
        ev = self.events
        self.players_appointments: dict[str, list[tuple[int, float, float]]] = {}
        period_start: dict[int, tuple[int, bool]] = {}
        period_end: dict[int, int] = {}
        attack_right: dict[int, bool] = {1: True, 2: False}
        consumed: set[int] = set()
        i = 0
        while i < len(ev):
            e = ev[i]
            t, kind = _t(e), e["type"]
            if kind in ("kickoff", "second_half_kickoff"):
                attack_right[int(e["period"])] = bool(e.get("home_attacking_right", kind == "kickoff"))
                period_start[int(e["period"])] = (_real(e), attack_right[int(e["period"])])
                self._key(t, 50, 50, None, True)
            elif kind in ("half_time", "full_time"):
                period_end[int(e["period"])] = _real(e)
            elif kind == "pass":
                passer = e.get("player_id")
                self._key(t, e["x"], e["y"], passer, False)
                self._appoint(passer, t, e["x"], e["y"])
                if e.get("outcome") == "complete":
                    flight = int(_clamp(round(float(e.get("distance_m", 15.0)) / 15.0), 1, 3))
                    t1 = t + flight
                    for j in range(i + 1, min(i + 6, len(ev))):  # the next placed event caps the flight
                        if ev[j]["type"] in COORD_TYPES:
                            t1 = min(t1, max(t + 1, _t(ev[j])))
                            break
                    self._key(t1, e["end_x"], e["end_y"], e.get("receiver_id"), True)
                    self._appoint(e.get("receiver_id"), t1, e["end_x"], e["end_y"])
                else:
                    turn = next((ev[j] for j in range(i + 1, min(i + 5, len(ev))) if ev[j]["type"] in ("interception", "tackle")), None)
                    if turn is not None:  # the ball flies straight to where it is won; that event is then consumed
                        tv = max(t, _t(turn))
                        self._key(tv, turn["x"], turn["y"], turn.get("player_id"), True)
                        self._appoint(turn.get("player_id"), tv, turn["x"], turn["y"])
                        consumed.add(id(turn))
                    else:
                        self._key(t + 1, e["end_x"], e["end_y"], None, True)
            elif kind in ("interception", "tackle", "foul"):
                if id(e) not in consumed:
                    self._key(t, e["x"], e["y"], e.get("player_id"), True)
                    self._appoint(e.get("player_id"), t, e["x"], e["y"])
            elif kind == "shot":
                shooter, team = e.get("player_id"), e.get("team_id")
                self._key(t, e["x"], e["y"], shooter, False)
                self._appoint(shooter, t, e["x"], e["y"])
                right = attack_right[int(e["period"])] if team == self.home else not attack_right[int(e["period"])]
                gx = 100.0 if right else 0.0
                gy = 50.0 if e.get("outcome") in ("goal", "saved", "blocked") else (62.0 if float(e["y"]) > 50 else 38.0)
                keeper = None
                if e.get("outcome") == "saved":
                    nxt = next((ev[j] for j in range(i + 1, min(i + 3, len(ev))) if ev[j]["type"] == "save"), None)
                    keeper = nxt.get("player_id") if nxt else None
                self._key(t + 1, gx, gy, keeper, True)
                if e.get("outcome") == "goal":
                    self._key(t + 2, 50, 50, None, True)
            elif kind == "pressure" and e.get("player_id"):
                self.pressures.append((t, e["player_id"]))
            elif kind == "substitution":
                self.subs.append((t, e["player_off_id"], e["player_on_id"]))
            i += 1

        for period in (1, 2):
            if period in period_start:
                t0, right = period_start[period]
                t_end = period_end.get(period, t0 + 45 * 60)
                self.periods.append((period, t0, t_end, right))

        # keyframes in time order; the loose-ball rule: nobody walks the ball for 30 s, it is picked up
        self.keyframes.sort(key=lambda k: (k.t, k.order))
        extra: list[Keyframe] = []
        for a, b in zip(self.keyframes, self.keyframes[1:], strict=False):
            if b.t - a.t > DEAD_BALL_CARRY_S and a.hold and b.carrier:
                extra.append(Keyframe(b.t - DEAD_BALL_CARRY_S, a.x, a.y, b.carrier, True, len(self.keyframes) + len(extra)))
                self._appoint(b.carrier, b.t - DEAD_BALL_CARRY_S, a.x, a.y)
        self.keyframes.extend(extra)
        self.keyframes.sort(key=lambda k: (k.t, k.order))
        # pressers meet the ball where it is at that second, two metres goal-side
        for t, pid in self.pressures:
            bx, by = self.ball_at(t)
            right = self._attacks_right(self.team_of.get(pid, self.home), t)
            self._appoint(pid, t, bx + (-2.0 if right else 2.0) / PITCH_LENGTH_M * 100, by)
        for apps in self.players_appointments.values():
            apps.sort()

    def _period_at(self, t: int) -> tuple[int, int, int, bool]:
        period = t // PERIOD_BASE
        for p in self.periods:
            if p[0] == period:
                return p
        return self.periods[-1]

    def _attacks_right(self, team: str, t: int) -> bool:
        right = self._period_at(t)[3]
        return right if team == self.home else not right

    def _kf_index(self, t: int) -> int:
        """Index of the last keyframe at or before t (bisect on sorted times)."""
        lo, hi = 0, len(self.keyframes)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.keyframes[mid].t <= t:
                lo = mid + 1
            else:
                hi = mid
        return lo - 1

    def ball_at(self, t: int) -> tuple[float, float]:
        i = self._kf_index(t)
        if i < 0:
            return 50.0, 50.0
        a = self.keyframes[i]
        if i + 1 >= len(self.keyframes) or a.hold:
            return a.x, a.y
        b = self.keyframes[i + 1]
        if b.t <= a.t:
            return b.x, b.y
        f = (t - a.t) / (b.t - a.t)
        return a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f

    def carrier_at(self, t: int) -> str | None:
        i = self._kf_index(t)
        if i < 0:
            return None
        a = self.keyframes[i]
        return a.carrier if (a.hold or a.t == t) else None

    # ------------------------------------------------------------ per-second loop

    def _roster(self, period_start: int) -> None:
        """Starting XI on their anchors at the start of a period, subs already applied."""
        on: dict[str, list[str]] = {tid: list(self.starters[tid]) for tid in (self.home, self.away)}
        for t, off, on_id in self.subs:
            if t < period_start:  # period_start is a period-aware key
                for tid in on:
                    if off in on[tid]:
                        on[tid][on[tid].index(off)] = on_id
        self.players = {}
        for tid in (self.home, self.away):
            slot_counter = dict.fromkeys(ANCHORS, 0)
            for pid in on[tid]:
                pos = self.position_of[pid]
                slots = ANCHORS[pos]
                slot = slot_counter[pos] % len(slots)
                slot_counter[pos] += 1
                p = _Player(pid, tid, pos, slot)
                p.appointments = list(self.players_appointments.get(pid, []))
                self.players[pid] = p
                if pos == "GK":
                    self.gk_of[tid] = pid

    def _to_abs(self, team: str, right: bool, x: float, y: float) -> tuple[float, float]:
        return (x if right else 100.0 - x), y

    def run(self) -> list[dict]:
        self.prepass()
        frames: list[dict] = []
        for period, t0, t_end, home_right in self.periods:
            self._roster(period * PERIOD_BASE + t0)
            # everyone on their anchor, facing the right way, no noise: no sprint across the pitch at 45:00
            for p in self.players.values():
                right = home_right if p.team == self.home else not home_right
                ax, ay = ANCHORS[p.position][p.slot]
                p.x, p.y = self._to_abs(p.team, right, ax, ay)
                p.nx = p.ny = 0.0
            base = period * PERIOD_BASE
            pending_subs = [s for s in self.subs if base + t0 <= s[0] <= base + t_end]
            last_team = self.home
            for real in range(t0, t_end + 1):
                t = base + real
                while pending_subs and pending_subs[0][0] < t:  # a sub takes effect the second after the event (the engine stacks seconds)
                    _, off, on_id = pending_subs.pop(0)
                    if off in self.players:
                        old = self.players.pop(off)
                        new = _Player(on_id, old.team, self.position_of.get(on_id, old.position), old.slot, old.x, old.y)
                        new.appointments = list(self.players_appointments.get(on_id, []))
                        self.players[on_id] = new
                bx, by = self.ball_at(t)
                carrier = self.carrier_at(t)
                if carrier and carrier in self.team_of:
                    last_team = self.team_of[carrier]
                poss = last_team
                self._step(t, bx, by, carrier, poss, home_right)
                frames.append({
                    "kind": "frame", "period": period, "minute": real // 60, "second": real % 60,
                    "ball": [round(bx, 1), round(by, 1)], "carrier": carrier if carrier in self.players else None,
                    "players": {pid: [round(p.x, 1), round(p.y, 1)] for pid, p in sorted(self.players.items())},
                })
        return frames

    def _step(self, t: int, bx: float, by: float, carrier: str | None, poss: str, home_right: bool) -> None:
        for tid in (self.home, self.away):
            right = home_right if tid == self.home else not home_right
            attacking = tid == poss
            bx_team = bx if right else 100.0 - bx
            team_players = [p for p in self.players.values() if p.team == tid]
            pressers: set[str] = set()
            if not attacking and carrier:
                k = 2 if self.press[tid] > 0.6 else 1
                outfield = [p for p in team_players if p.position != "GK"]
                outfield.sort(key=lambda p: _dist_m(p.x, p.y, bx, by))
                pressers = {p.pid for p in outfield[:k]}
            for p in sorted(team_players, key=lambda p: p.pid):
                ax, ay = ANCHORS[p.position][p.slot]
                if p.position == "GK":
                    tx, ty = ax + 0.05 * (bx_team - 50), ay + 0.15 * (by - 50)
                else:
                    tx = ax + (0.3 if attacking else 0.4) * (bx_team - 50)
                    if not attacking:
                        tx = 10 + (tx - 10) * 0.8
                    ty = ay + 0.3 * (by - 50)
                tx_abs, ty_abs = self._to_abs(tid, right, tx, ty)
                gain, vmax = 0.5, V_MAX_MPS
                if attacking and p.position != "GK" and _dist_m(tx_abs, ty_abs, bx, by) < ATTRACTION_RADIUS_M:
                    w = ATTRACTION[p.position]
                    tx_abs += w * (bx - tx_abs)
                    ty_abs += w * (by - ty_abs)
                # appointments: the model sees the future, so players arrive on time
                while p.appointments and p.appointments[0][0] < t:
                    p.appointments.pop(0)
                if p.appointments and p.appointments[0][0] - t <= APPOINTMENT_HORIZON_S:
                    ta, axp, ayp = p.appointments[0]
                    tx_abs, ty_abs = axp, ayp
                    gain, vmax = 1.0, (V_SPRINT_MPS if ta - t <= 1 else V_MAX_MPS)
                elif p.pid in pressers:
                    tx_abs = bx + (-PRESS_RADIUS_M if right else PRESS_RADIUS_M) / PITCH_LENGTH_M * 100
                    ty_abs = by
                    gain = self.press[tid]
                p.nx = _clamp(p.nx + self.rng.gauss(0, NOISE_SIGMA), -NOISE_CLAMP, NOISE_CLAMP)
                p.ny = _clamp(p.ny + self.rng.gauss(0, NOISE_SIGMA), -NOISE_CLAMP, NOISE_CLAMP)
                dx = (tx_abs + p.nx - p.x) * gain
                dy = (ty_abs + p.ny - p.y) * gain
                step_m = math.hypot(dx / 100 * PITCH_LENGTH_M, dy / 100 * PITCH_WIDTH_M)
                if step_m > vmax:
                    dx, dy = dx * vmax / step_m, dy * vmax / step_m
                p.x = _clamp(p.x + dx, 0.0, 100.0)
                p.y = _clamp(p.y + dy, 0.0, 100.0)
        if carrier and carrier in self.players:
            self.players[carrier].x, self.players[carrier].y = bx, by


def build_tracking(events: list[dict], meta: dict) -> list[dict]:
    """One frame per match second, consistent with every placed event. Pure: never mutates its inputs."""
    if not events:
        return []
    return _Model(events, meta).run()
