"""One WebSocket replay: the wall-clock loop, the Interpreter and Risk Monitor state, the agent lanes, resume.

`StreamSession` is created per connection by the `/ws/matches/{match_id}` route in `api/app.py`, which also
documents every message kind. Three `_Lane`s run the LLM work in the background (moments -> Analyst, Narrator,
Director; risk alerts and knocks -> Coach; settled forecasts -> Judge), one item in flight per lane: a more
important item replaces a waiting one, and the lanes report what they dropped.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from fastapi import WebSocketDisconnect
from pydantic import ValidationError

from matchmind.agents.cache import AgentCache, coach_key, insight_key, verdict_key
from matchmind.agents.coach import build_coach_context
from matchmind.agents.guardrails import check_moment, facts_text
from matchmind.agents.judge import ForecastLedger, build_judge_context, grade_forecast
from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.agents.observability import moment_span, record_moment
from matchmind.agents.schemas import ViewerProfile
from matchmind.api.events import match_ended, publisher_from_env, window_opened
from matchmind.interpreter.state import MatchState
from matchmind.risk.monitor import RiskMonitor
from matchmind.stream.replay import delay_between, frame_stride, merge_timeline
from matchmind.tools.registry import current_session

log = logging.getLogger("matchmind.api.stream")

SNAPSHOT_EVERY = 25  # also attach a state snapshot every N events
AGENT_DRAIN_TIMEOUT_S = 45.0  # how long the end of a stream waits for the last agent outputs
HAZARD_TOP_N = 5


def parse_profile_spec(spec: str) -> ViewerProfile:
    """'analyst:en' | 'commentator:es' | 'player_focus:en:THU-15' | 'commentator:es::THU' (mode:lang:player:team)."""
    parts = [p.strip() for p in str(spec).split(":")]
    if not parts or not parts[0]:
        raise ValueError(f"empty profile spec {spec!r}")
    return ViewerProfile(mode=parts[0], language=parts[1] if len(parts) > 1 and parts[1] else "en",
                         favorite_player_id=parts[2] if len(parts) > 2 and parts[2] else None,
                         team_id=parts[3] if len(parts) > 3 and parts[3] else None)


class _Lane:
    """One background agent lane: a 1-slot queue where the more important item survives.

    The lane keeps count of what it was offered, what it ran and what it dropped, and tells the viewer
    each time a drop happens (`{"kind": "stats", "lanes": {...}}`), so a fast replay never looks like a
    complete one: the Control room shows how many moments were skipped under load.
    """

    def __init__(self, runner, kind: str, out: asyncio.Queue, importance, capacity: int = 1, on_drop=None):
        self.runner, self.kind, self.out, self.importance = runner, kind, out, importance
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=capacity)
        self.offered = self.started = self.dropped = 0
        self.on_drop = on_drop
        self.task = asyncio.create_task(self._worker())

    def stats(self) -> dict:
        return {"offered": self.offered, "started": self.started, "dropped": self.dropped}

    async def _worker(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                if item is None:
                    return
                self.started += 1
                try:
                    result = await self.runner(item)
                    await self.out.put({"kind": self.kind, **result})
                except Exception as exc:  # noqa: BLE001
                    log.warning("%s lane failed: %r", self.kind, exc)
                    await self.out.put({"kind": f"{self.kind}_error", "detail": repr(exc)})
            finally:
                self.queue.task_done()

    def offer(self, item: dict) -> None:
        self.offered += 1
        if self.queue.full():
            waiting = self.queue.get_nowait()
            self.queue.task_done()
            if waiting is not None and self.importance(waiting) > self.importance(item):
                item = waiting
            self.dropped += 1  # one of the two never runs
            if self.on_drop is not None:
                self.on_drop()
        self.queue.put_nowait(item)

    async def close(self, timeout: float) -> None:
        await self.queue.put(None)
        try:
            await asyncio.wait_for(self.task, timeout)
        except TimeoutError:
            log.warning("%s lane did not finish within %ss", self.kind, timeout)
            self.task.cancel()


def _time_key(item: dict) -> tuple[int, int]:
    return (int(item.get("period", 1)), int(item.get("minute", 0)) * 60 + int(item.get("second", 0)))


class StreamSession:
    """One WebSocket connection: replay loop + control reader + agent lanes + single sender."""

    def __init__(self, websocket, meta, events, registry, *, pipeline, coach, profile, speed, min_importance, judge=None, cache=None, compare=None,
                 frames=None, frames_mode="auto", resume_from=None):
        self.ws, self.meta, self.events, self.registry = websocket, meta, events, registry
        self.resume_from: int | None = resume_from  # events up to this id are replayed into the state without being sent
        self.events_out = publisher_from_env()  # Event Grid, or None locally
        self.frames: list[dict] = list(frames or [])  # positional frames, a side channel: never events
        self.frames_mode = frames_mode
        self.pipeline, self.coach, self.judge, self.profile, self.speed = pipeline, coach, judge, profile, speed
        self.compare: list[ViewerProfile] = list(compare or [])  # extra viewers explained side by side (Control room)
        self.min_importance = min_importance
        self.match_id = meta["match_id"]
        self.session_id = f"{self.match_id}:{id(websocket):x}:{int(time.time() * 1000) % 1_000_000}"
        self.cache: AgentCache | None = cache
        self.closed = False
        self.out: asyncio.Queue = asyncio.Queue()
        self.ledger = ForecastLedger()  # the Analyst's forecasts, graded 10 match minutes later

    def _cut_time(self) -> tuple[int, int] | None:
        """(period, seconds) of the resume event, so frames up to that second are replayed silently too."""
        for e in self.events:
            if e["event_id"] == self.resume_from:
                return _time_key(e)
        return None

    def _cached(self, kind: str, key: str) -> dict | None:
        return self.cache.get(self.match_id, kind, key) if self.cache is not None else None

    def _remember(self, kind: str, key: str, result: dict) -> None:
        if self.cache is not None:
            self.cache.put(self.match_id, kind, key, result)

    async def _run_moment(self, context: dict) -> dict:
        """Moments lane runner: the insight goes to the viewer, its forecast into the ledger.
        The same moment for the same profile is explained once: later viewers get it from the cache."""
        profiles = [self.profile, *self.compare]
        key = insight_key(context["moment"]["event_id"], "+".join(p.key for p in profiles))
        t0 = time.perf_counter()
        result = self._cached("insight", key)
        hit = result is not None
        with moment_span(self.match_id, context["moment"]["kind"], self.profile.mode, cache_hit=hit):
            if result is None:
                result = await self.pipeline.run(context, profiles)
                await check_moment(result, facts_text(context))  # Content Safety groundedness, when enabled; never blocks
                self._remember("insight", key, result)
        record_moment((time.perf_counter() - t0) * 1000, hit, context["moment"]["kind"])
        self.ledger.add(result, context)
        return result

    async def _run_coach(self, context: dict) -> dict:
        key = coach_key(context.get("trigger", ""), (context.get("player") or {}).get("player_id"), context.get("minute"))
        result = self._cached("coach", key)
        if result is None:
            result = await self.coach.run(context)
            self._remember("coach", key, result)
        return result

    async def _run_verdict(self, context: dict) -> dict:
        """Verdict lane runner: the Judge's words also go back into the ledger, for the Analyst's next call."""
        key = verdict_key(context["event_id"], self.profile.language)
        result = self._cached("verdict", key)
        if result is None:
            assert self.judge is not None  # the verdict lane is only built when a Judge exists
            result = await self.judge.run(context)
            self._remember("verdict", key, result)
        else:  # the scores and the credibility are this session's, only the words are shared
            result = {**result, "scores": context["scores"], "naive_scores": context["naive_scores"],
                      "facts": context["facts"], "credibility": context.get("credibility")}
        self.ledger.remember(result)
        return result

    def _grade_due(self, snapshot: dict, lane, *, flush: bool = False) -> list[dict]:
        """Settle every forecast whose window has closed: scores now (code), words later (Judge lane)."""
        settled = []
        for pending in self.ledger.due(snapshot, flush=flush):
            close = self.ledger.window_close(pending, snapshot)
            facts, scores, naive_scores = grade_forecast(pending, close, self.ledger.window_events(pending, close.get("event_id")))
            self.ledger.record({"event_id": pending.event_id, "scores": scores, "naive_scores": naive_scores})
            summary = self.ledger.summary()
            ctx = build_judge_context(pending, facts, scores, naive_scores, self.meta, self.profile.language)
            ctx["credibility"] = summary
            self.registry.update_credibility(self.match_id, summary, {"event_id": pending.event_id, "scores": scores, "facts": facts})
            settled.append(ctx)
            if lane is not None:
                lane.offer(ctx)
        return settled

    # ------------------------------------------------------------ tasks

    async def _sender(self) -> None:
        while True:
            msg = await self.out.get()
            if msg is None:
                return
            await self.ws.send_json(msg)

    async def _read_controls(self) -> None:
        while True:
            try:
                msg = await self.ws.receive_json()
            except (WebSocketDisconnect, RuntimeError):
                self.closed = True
                return
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if "speed" in msg:
                try:
                    self.speed = max(0.0, float(msg["speed"]))
                except (TypeError, ValueError):
                    continue
                await self.out.put({"kind": "ack", "speed": self.speed})
            if "profile" in msg:
                try:
                    self.profile = ViewerProfile.model_validate(msg["profile"])
                except ValidationError as exc:
                    await self.out.put({"kind": "error", "detail": f"bad profile: {exc.errors()[0]['msg']}"})
                    continue
                await self.out.put({"kind": "ack", "profile": self.profile.model_dump()})
            if "compare" in msg:
                try:
                    specs = msg["compare"] if isinstance(msg["compare"], list) else ([msg["compare"]] if msg["compare"] else [])
                    self.compare = [parse_profile_spec(s) if isinstance(s, str) else ViewerProfile.model_validate(s) for s in specs]
                except (ValidationError, ValueError) as exc:
                    await self.out.put({"kind": "error", "detail": f"bad compare profile: {exc}"})
                    continue
                await self.out.put({"kind": "ack", "compare": [p.model_dump() for p in self.compare]})

    # ------------------------------------------------------------ helpers

    def _risk_message(self, monitor: RiskMonitor, snapshot: dict) -> dict:
        summary = monitor.summary()
        players = snapshot.get("players", {})
        top = sorted(summary["hazards"].items(), key=lambda kv: -kv[1])[:HAZARD_TOP_N]
        self.registry.update_risk(self.match_id, summary)
        return {
            "kind": "risk",
            "minute": summary["minute"],
            "clock": snapshot["clock"],
            "active_windows": summary["active_windows"],
            "hazards_top": [{"player_id": pid, "name": players.get(pid, {}).get("name", pid),
                             "team_id": players.get(pid, {}).get("team_id"), "hazard": h} for pid, h in top],
            "recent_alerts": summary["recent_alerts"],
            "concerns": summary["concerns"],
            "scorecard": summary["scorecard"],
            "hazard_series": monitor.hazard_series(),
            "note": summary["note"],
        }

    # ------------------------------------------------------------ main

    async def run(self) -> None:
        current_session.set(self.session_id)  # the lanes below inherit it: agent tools read this stream's state
        sender = asyncio.create_task(self._sender())
        reader = asyncio.create_task(self._read_controls())
        lanes: dict[str, _Lane] = {}
        lane_stats = lambda: {k: lane.stats() for k, lane in lanes.items()}  # noqa: E731
        report_drop = lambda: self.out.put_nowait({"kind": "stats", "lanes": lane_stats()})  # noqa: E731
        moments = _Lane(self._run_moment, "insight", self.out,
                        lambda c: c["moment"]["importance"], on_drop=report_drop) if self.pipeline is not None else None
        coach = _Lane(self._run_coach, "coach", self.out,
                      lambda c: 5 if c["trigger"] == "injury_concern" else 3, on_drop=report_drop) if self.coach is not None else None
        judge = _Lane(self._run_verdict, "verdict", self.out, lambda c: c["scores"].get("overall") or 0,
                      capacity=8, on_drop=report_drop) if self.judge is not None and moments is not None else None  # verdicts are few; keep them all
        lanes.update({k: lane for k, lane in (("insight", moments), ("coach", coach), ("verdict", judge)) if lane is not None})
        state, monitor = MatchState(self.meta), RiskMonitor(self.meta)
        try:
            await self.out.put({
                "kind": "meta", "meta": self.meta, "speed": self.speed,
                "agents": self.pipeline is not None, "coach": self.coach is not None,
                "profile": self.profile.model_dump(),
                "compare": [p.model_dump() for p in self.compare],
            })
            prev: dict | None = None
            n = len(self.events)
            pending_risk = False
            i = 0
            frame_no = 0
            # wall-clock schedule: each item is due at the previous due time plus its delay, and we only sleep
            # until then. The OS timer floor (~15 ms on Windows) overshoots every sleep; measuring against the
            # clock absorbs that instead of letting it pile up over thousands of frames.
            due = time.monotonic()
            timeline = merge_timeline(self.events, self.frames) if self.frames_mode != "0" and self.frames else self.events
            # resume: everything up to the cut is applied silently (state, frames, risk monitor), nothing is sent and no
            # agent lane is offered; forecasts that were pending before the cut are not re-created (documented)
            cut = self._cut_time() if self.resume_from is not None else None
            resumed = False
            for item in timeline:
                if self.closed:
                    return
                if cut is not None and not resumed:
                    is_frame = item.get("kind") == "frame"
                    if (not is_frame and item["event_id"] <= self.resume_from) or (is_frame and _time_key(item) <= cut):
                        if is_frame:
                            state.apply_frame(item)
                        else:
                            i += 1
                            state.apply(item)
                            monitor.observe(item, state.snapshot())
                            prev = item
                        continue
                    resumed = True
                    snapshot = state.snapshot()
                    self.registry.update(self.match_id, self.meta, snapshot)
                    await self.out.put({"kind": "resume", "from": self.resume_from, "state": snapshot})
                    if monitor.minute:
                        await self.out.put(self._risk_message(monitor, snapshot))
                    prev = None  # the next item is due now
                    due = time.monotonic()
                due = max(due + delay_between(prev, item, self.speed), time.monotonic() - 1.0)  # a stall never bursts > 1 s
                wait = due - time.monotonic()
                if item.get("kind") != "frame":
                    await asyncio.sleep(max(wait, 0.0))  # events always yield so the lanes can send
                elif wait >= 0.005:
                    await asyncio.sleep(wait)
                prev = item
                if item.get("kind") == "frame":
                    # a side channel: the Interpreter learns shape/heat/pressure; nothing else sees frames
                    state.apply_frame(item)
                    frame_no += 1
                    stride = 1 if self.frames_mode == "all" else frame_stride(self.speed)
                    if stride and frame_no % stride == 0:
                        await self.out.put(item)
                    continue
                event = item
                i += 1
                state.apply(event)
                snapshot = state.snapshot()
                message: dict = {"kind": "event", "event": event}
                if moments is not None:
                    self.ledger.observe(event, snapshot)
                    if self.ledger.pending and event["type"] != "physical_sample":
                        self._grade_due(snapshot, judge)
                key_event = event["type"] in MatchState.SNAPSHOT_TYPES
                if key_event or i % SNAPSHOT_EVERY == 0 or i == n:
                    message["state"] = snapshot
                    self.registry.update(self.match_id, self.meta, snapshot)
                    if moments is not None and key_event:
                        moment = detect_key_moment(event, snapshot)
                        if moment is not None and moment.importance >= self.min_importance:
                            watched = [self.profile.favorite_player_id] if self.profile.favorite_player_id else None
                            moments.offer(build_moment_context(moment, snapshot, self.meta, watched_players=watched,
                                                               track_record=self.ledger.track_record()))

                # Risk Monitor: alerts immediately, a summary after every 5-minute sample batch
                for alert in monitor.observe(event, snapshot):
                    await self.out.put({"kind": "risk_alert", **alert})
                    if self.events_out is not None and alert["level"] == "high":
                        self.events_out.publish(window_opened(self.match_id, event["event_id"], alert))
                    if coach is not None and alert["level"] == "high":
                        coach.offer(build_coach_context({**alert, "other_windows": monitor.active_windows()},
                                                        snapshot, self.meta, trigger="risk_alert"))
                if event["type"] == "physical_sample":
                    pending_risk = True
                elif pending_risk:
                    pending_risk = False
                    await self.out.put(self._risk_message(monitor, snapshot))
                if event["type"] == "injury_concern" and coach is not None:
                    coach.offer(build_coach_context(
                        {"player_id": event["player_id"], "name": event.get("player_name"), "clock": event.get("clock"),
                         "detail": event.get("detail"), "other_windows": monitor.active_windows()},
                        snapshot, self.meta, trigger="injury_concern"))

                await self.out.put(message)

            if moments is not None:
                await moments.close(AGENT_DRAIN_TIMEOUT_S)  # the last insight may still add a forecast
                self._grade_due(state.snapshot(), judge, flush=True)  # full time settles what is left
            for lane in (coach, judge):
                if lane is not None:
                    await lane.close(AGENT_DRAIN_TIMEOUT_S)
            final_state, risk_summary = state.snapshot(), monitor.summary()
            credibility = self.ledger.summary() if moments is not None else None
            await self.out.put({"kind": "end", "state": final_state, "risk": risk_summary,
                                "hazard_series": monitor.hazard_series(), "credibility": credibility, "lanes": lane_stats()})
            if self.events_out is not None:
                try:  # a domain event must never cost the viewer the end message
                    self.events_out.publish(match_ended(self.match_id, self.profile.key, self.meta, final_state, risk_summary, credibility))
                except Exception as exc:  # noqa: BLE001
                    log.warning("match.ended event not published: %r", exc)
            await self.out.put(None)
            await sender
        except (WebSocketDisconnect, RuntimeError):
            log.info("client disconnected from %s", self.match_id)
        finally:
            self.registry.drop_session(self.session_id)
            for task in (sender, reader, *(lane.task for lane in (moments, coach, judge) if lane is not None)):
                task.cancel()
            with suppress(RuntimeError):
                await self.ws.close()
