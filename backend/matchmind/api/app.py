"""FastAPI service: live replay + Interpreter + Risk Monitor + LLM agents + MCP server.

REST
    GET  /health
    GET  /matches                                   -> catalogue of matches in the data dir
    GET  /matches/{match_id}/meta                   -> teams, squads, load history (no latent state)
    GET  /matches/{match_id}/branches               -> counterfactual branches simulated so far
    POST /matches/{match_id}/branches               -> simulate an intervention (body: InterventionRequest)
    GET  /matches/{match_id}/branches/{branch_id}   -> branch summary + meta + full event stream
    POST /mcp                                       -> MCP server (streamable HTTP) with match-state tools
    GET  /live                                      -> no-build dev viewer

WebSocket
    WS   /ws/matches/{match_id}?speed=10&mode=analyst&lang=en&player=THU-15&agents=1&coach=1&min_importance=3
        server -> client
            {"kind": "meta",       "meta": {...}, "speed": 10, "agents": true, "coach": true, "profile": {...}}
            {"kind": "event",      "event": {...}, "state": {...}?}   # state on key events / every N
            {"kind": "risk",       "minute", "clock", "active_windows", "hazards_top", "scorecard", ...}  # every 5'
            {"kind": "risk_alert", ...window}                          # a risk window just opened
            {"kind": "insight",    "event_id", "clock", "moment", "analyst", "viewers", "latency_ms"}
            {"kind": "coach",      "trigger", "player", "proposal", "branch", "latency_ms"}
            {"kind": "ack",        "speed": 50} | {"kind": "ack", "profile": {...}}
            {"kind": "resume",     "from": event_id, "state": {...}}   # only with ?from=, once, before the first live item
            {"kind": "end",        "state": {...}, "risk": {...}}
        client -> server
            {"speed": 50}                                      # change replay speed live
            {"profile": {"mode": "casual", "language": "es"}}  # switch viewer profile live

speed: 1 = real time, 10 = ten times faster, 0 = as fast as possible.
LLM agents run in the background on two lanes (moments -> Analyst/Narrator/Director,
risk alerts -> Coach), one item in flight per lane; a more important item replaces a waiting one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError

from matchmind.api.tts import Speaker, speech_config
from matchmind.agents.cache import AgentCache, cache_from_env, coach_key, insight_key, verdict_key
from matchmind.agents.coach import build_coach_context
from matchmind.agents.judge import ForecastLedger, build_judge_context, grade_forecast
from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.agents.observability import configure_observability, moment_span, record_moment, telemetry_enabled
from matchmind.agents.schemas import ViewerProfile
from matchmind.generate_match import generate, write_match
from matchmind.interpreter.state import MatchState
from matchmind.risk.monitor import RiskMonitor
from matchmind.sim.tracking import build_tracking
from matchmind.stream.replay import delay_between, frame_stride, load_events, merge_timeline
from matchmind.tools.mcp_server import build_mcp_server
from matchmind.tools.registry import LiveStateRegistry, MatchTools, current_session

log = logging.getLogger("matchmind.api")

SNAPSHOT_EVERY = 25  # also attach a state snapshot every N events
DEFAULT_MATCH = ("THU", "NBF", 42)
AGENT_DRAIN_TIMEOUT_S = 45.0  # how long the end of a stream waits for the last agent outputs
HAZARD_TOP_N = 5


def default_data_dir() -> Path:
    env = os.environ.get("MATCHMIND_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "data"


class InterventionRequest(BaseModel):
    minute: int = Field(ge=0, le=100)
    action: str
    team_id: str
    player_off_id: str | None = None
    player_on_id: str | None = None
    press_intensity: float | None = Field(default=None, ge=0, le=1)
    style: str | None = None


class MatchCatalog:
    """Matches available on disk: `<id>_meta.json` + `<id>_events.jsonl`."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._frames: dict[str, list[dict]] = {}

    def ids(self) -> list[str]:
        return sorted(p.name[: -len("_meta.json")] for p in self.data_dir.glob("*_meta.json"))

    def meta(self, match_id: str) -> dict | None:
        path = self.data_dir / f"{match_id}_meta.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def events(self, match_id: str) -> list[dict]:
        return load_events(self.data_dir / f"{match_id}_events.jsonl")

    def ensure_default(self) -> None:
        if self.ids():
            return
        home, away, seed = DEFAULT_MATCH
        log.info("No matches in %s - generating default %s vs %s (seed %s)", self.data_dir, home, away, seed)
        write_match(*generate(home, away, seed), out_dir=self.data_dir)

    def frames(self, match_id: str) -> list[dict]:
        """Positional frames, built once per match from its events (pure, deterministic) and kept in memory."""
        if match_id not in self._frames:
            meta = self.meta(match_id)
            self._frames[match_id] = build_tracking(self.events(match_id), meta) if meta else []
        return self._frames[match_id]

    def final_state(self, match_id: str) -> dict:
        state = MatchState(self.meta(match_id))
        for item in merge_timeline(self.events(match_id), self.frames(match_id)):
            if item.get("kind") == "frame":
                state.apply_frame(item)
            else:
                state.apply(item)
        return state.snapshot()


def create_app(
    data_dir: Path | str | None = None,
    pipeline=None,
    coach=None,
    judge=None,
    enable_agents: bool | None = None,
    cache: AgentCache | None | bool = True,
    speech_transport=None,
) -> FastAPI:
    """Build the service.

    pipeline: object with `async run(context, profiles) -> dict` (moments lane; tests inject a fake).
    coach:    object with `async run(context) -> dict` (risk lane; tests inject a fake).
    judge:    object with `async run(context) -> dict` (verdict lane; graded forecasts get their words here).
    enable_agents: None = build the Foundry agents on startup if configured; False = never call an LLM.
    cache: an AgentCache, True = from the environment (default <data>/cache), False/None = no cache.
    speech_transport: httpx transport for Azure Speech (tests inject a mock).
    """
    data_path = Path(data_dir) if data_dir else default_data_dir()
    catalog = MatchCatalog(data_path)
    registry = LiveStateRegistry()
    tools = MatchTools(registry)
    mcp = build_mcp_server(registry)
    agent_cache = cache_from_env(data_path) if cache is True else (cache or None)
    agents = {"pipeline": pipeline, "coach": coach, "judge": judge, "cache": agent_cache}
    speaker = Speaker(data_path / "cache" / "tts", transport=speech_transport)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        catalog.ensure_default()
        for mid in catalog.ids():  # MCP clients get full-match state even with no live stream
            try:
                registry.update(mid, catalog.meta(mid), catalog.final_state(mid))
            except Exception as exc:  # noqa: BLE001
                log.warning("could not preload %s: %r", mid, exc)
        configure_observability(app, sessions=registry.sessions)
        if enable_agents is not False and any(agents[k] is None for k in ("pipeline", "coach", "judge")):
            from matchmind.agents.clients import build_coach, build_judge, build_pipeline, describe_auth, foundry_configured

            if foundry_configured():
                log.info("Foundry auth: %s", describe_auth())
                try:
                    if agents["pipeline"] is None:
                        agents["pipeline"] = build_pipeline(tools=tools.as_functions())
                    if agents["coach"] is None:
                        agents["coach"] = build_coach(tools)
                    if agents["judge"] is None:
                        agents["judge"] = build_judge()
                    log.info("LLM agents enabled (Azure AI Foundry)")
                except Exception as exc:  # noqa: BLE001
                    log.warning("LLM agents disabled: %r", exc)
            else:
                log.info("LLM agents disabled: Foundry not configured")
        app.state.ready = True
        async with mcp.session_manager.run():
            yield
        app.state.draining = True  # the platform stopped routing to us; live sessions finish within the grace period

    app = FastAPI(title="MatchMind", version="0.3.0", lifespan=lifespan)
    app.state.catalog, app.state.registry, app.state.agents = catalog, registry, agents
    app.state.ready, app.state.draining = False, False
    # Public read-mostly demo API consumed by the Static Web Apps frontend: open CORS is intended.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=307)

    @app.get("/live", include_in_schema=False)
    def live_page() -> HTMLResponse:
        """Minimal dev viewer: events + agent insights, no build step (the React UI comes later)."""
        return HTMLResponse((Path(__file__).with_name("live.html")).read_text(encoding="utf-8"))

    @app.get("/health")
    def health(response: Response) -> dict:
        """Startup, readiness and liveness probe. 503 while not ready or while draining, so the platform stops
        routing new viewers to this replica; the keys are what the runbook and the smoke script read."""
        from matchmind.agents.clients import auth_mode, project_endpoint

        ready, draining = bool(app.state.ready), bool(app.state.draining)
        if not ready or draining:
            response.status_code = 503
        return {"status": "ok" if ready and not draining else "unavailable", "ready": ready, "draining": draining,
                "matches": len(catalog.ids()), "agents": agents["pipeline"] is not None,
                "coach": agents["coach"] is not None, "judge": agents["judge"] is not None,
                "cache": agents["cache"].stats() if agents["cache"] is not None else None,
                "speech": speech_config() is not None,
                "live_sessions": registry.sessions(),
                "auth": auth_mode() if agents["pipeline"] is not None else None,
                "project": bool(project_endpoint()) if agents["pipeline"] is not None else False,
                "telemetry": telemetry_enabled(),
                "replica": os.environ.get("CONTAINER_APP_REPLICA_NAME"),
                "revision": os.environ.get("CONTAINER_APP_REVISION")}

    @app.get("/matches")
    def list_matches() -> list[dict]:
        out = []
        keys = ("team_id", "name", "short_name", "primary_color", "secondary_color", "pattern", "city")
        for mid in catalog.ids():
            m = catalog.meta(mid) or {}
            home, away = m.get("teams", {}).get(m.get("home_id"), {}), m.get("teams", {}).get(m.get("away_id"), {})
            out.append({
                "match_id": mid,
                "home_id": m.get("home_id"),
                "away_id": m.get("away_id"),
                "home": home.get("name"),
                "away": away.get("name"),
                "home_team": {k: home.get(k) for k in keys},
                "away_team": {k: away.get(k) for k in keys},
                "score": m.get("score"),
                "n_events": m.get("n_events"),
            })
        return out

    def _meta_or_404(match_id: str) -> dict:
        meta = catalog.meta(match_id)
        if meta is None:
            raise HTTPException(status_code=404, detail=f"unknown match {match_id!r}")
        return meta

    @app.get("/matches/{match_id}/meta")
    def match_meta(match_id: str) -> dict:
        return _meta_or_404(match_id)

    @app.get("/matches/{match_id}/branches")
    def list_branches(match_id: str) -> list[dict]:
        _meta_or_404(match_id)
        return registry.branches(match_id)

    @app.post("/matches/{match_id}/branches")
    def simulate_branch(match_id: str, body: InterventionRequest) -> dict:
        meta = _meta_or_404(match_id)
        if registry.get(match_id) is None:
            registry.update(match_id, meta, catalog.final_state(match_id))
        try:
            return tools.simulate_intervention(match_id, body.minute, body.action, body.team_id,
                                               player_off_id=body.player_off_id, player_on_id=body.player_on_id,
                                               press_intensity=body.press_intensity, style=body.style)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/matches/{match_id}/branches/{branch_id}")
    def get_branch(match_id: str, branch_id: str) -> dict:
        _meta_or_404(match_id)
        branch = registry.branch(match_id, branch_id)
        if branch is None:
            raise HTTPException(status_code=404, detail=f"unknown branch {branch_id!r}")
        return branch

    @app.websocket("/ws/matches/{match_id}")
    async def stream_match(
        websocket: WebSocket,
        match_id: str,
        speed: float = Query(1.0, ge=0),
        mode: str = Query("analyst"),
        lang: str = Query("en"),
        player: str | None = Query(None),
        team: str | None = Query(None, description="the side the viewer supports (team_id); omit for neutral"),
        agents_on: bool = Query(True, alias="agents"),
        coach_on: bool = Query(True, alias="coach"),
        min_importance: int = Query(3, ge=1, le=5),
        compare: str | None = Query(None, description="extra viewer profiles to compare, comma-separated mode:lang:player:team (Control room)"),
        frames: str = Query("auto", pattern="^(auto|all|0)$", description="positional frames: auto = by speed, all = every frame, 0 = none"),
        resume_from: int | None = Query(None, alias="from", ge=0, description="resume after this event id: the state is rebuilt silently up to it (a viewer reconnecting to another replica)"),
    ) -> None:
        await websocket.accept()
        meta = catalog.meta(match_id)
        if meta is None:
            await websocket.close(code=4404, reason=f"unknown match {match_id!r}")
            return
        try:
            profile = ViewerProfile(mode=mode, language=lang, favorite_player_id=player, team_id=team or None)
            compare_profiles = [parse_profile_spec(s) for s in compare.split(",") if s.strip()] if compare else []
        except ValidationError as exc:
            await websocket.close(code=4400, reason=f"bad viewer profile: {exc.errors()[0]['msg']}")
            return
        session = StreamSession(
            websocket, meta, catalog.events(match_id), registry,
            pipeline=agents["pipeline"] if agents_on else None,
            coach=agents["coach"] if coach_on else None,
            judge=agents["judge"] if agents_on else None,
            profile=profile, speed=speed, min_importance=min_importance, cache=agents["cache"], compare=compare_profiles,
            frames=catalog.frames(match_id), frames_mode=frames, resume_from=resume_from,
        )
        await session.run()

    @app.get("/tts", summary="The commentator's voice: one narration line as MP3 (Azure AI Speech, cached)")
    async def tts(text: str = Query(..., min_length=1, max_length=600), lang: str = Query("en", pattern="^(en|es)$")) -> Response:
        audio = await speaker.say(text, lang)
        if audio is None:
            raise HTTPException(status_code=503, detail="speech is not configured or synthesis failed")
        return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    # MCP server (streamable HTTP) lives at /mcp; mounted last so API routes win.
    app.mount("/", mcp.streamable_http_app())
    return app


def parse_profile_spec(spec: str) -> ViewerProfile:
    """'analyst:en' | 'commentator:es' | 'player_focus:en:THU-15' | 'commentator:es::THU' (mode:lang:player:team)."""
    parts = [p.strip() for p in str(spec).split(":")]
    if not parts or not parts[0]:
        raise ValueError(f"empty profile spec {spec!r}")
    return ViewerProfile(mode=parts[0], language=parts[1] if len(parts) > 1 and parts[1] else "en",
                         favorite_player_id=parts[2] if len(parts) > 2 and parts[2] else None,
                         team_id=parts[3] if len(parts) > 3 and parts[3] else None)


class _Lane:
    """One background agent lane: a 1-slot queue where the more important item survives."""

    def __init__(self, runner, kind: str, out: asyncio.Queue, importance, capacity: int = 1):
        self.runner, self.kind, self.out, self.importance = runner, kind, out, importance
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=capacity)
        self.task = asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                if item is None:
                    return
                try:
                    result = await self.runner(item)
                    await self.out.put({"kind": self.kind, **result})
                except Exception as exc:  # noqa: BLE001
                    log.warning("%s lane failed: %r", self.kind, exc)
                    await self.out.put({"kind": f"{self.kind}_error", "detail": repr(exc)})
            finally:
                self.queue.task_done()

    def offer(self, item: dict) -> None:
        if self.queue.full():
            waiting = self.queue.get_nowait()
            self.queue.task_done()
            if waiting is not None and self.importance(waiting) > self.importance(item):
                item = waiting
        self.queue.put_nowait(item)

    async def close(self, timeout: float) -> None:
        await self.queue.put(None)
        try:
            await asyncio.wait_for(self.task, timeout)
        except asyncio.TimeoutError:
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
        moments = _Lane(self._run_moment, "insight", self.out,
                        lambda c: c["moment"]["importance"]) if self.pipeline is not None else None
        coach = _Lane(self._run_coach, "coach", self.out,
                      lambda c: 5 if c["trigger"] == "injury_concern" else 3) if self.coach is not None else None
        judge = _Lane(self._run_verdict, "verdict", self.out, lambda c: c["scores"].get("overall") or 0,
                      capacity=8) if self.judge is not None and moments is not None else None  # verdicts are few; keep them all
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
            await self.out.put({"kind": "end", "state": state.snapshot(), "risk": monitor.summary(),
                                "hazard_series": monitor.hazard_series(),
                                "credibility": self.ledger.summary() if moments is not None else None})
            await self.out.put(None)
            await sender
        except (WebSocketDisconnect, RuntimeError):
            log.info("client disconnected from %s", self.match_id)
        finally:
            self.registry.drop_session(self.session_id)
            for task in (sender, reader, *(lane.task for lane in (moments, coach, judge) if lane is not None)):
                task.cancel()
            try:
                await self.ws.close()
            except RuntimeError:
                pass


app = create_app()
