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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, ValidationError

from matchmind.agents.coach import build_coach_context
from matchmind.agents.judge import ForecastLedger, build_judge_context, grade_forecast
from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.agents.schemas import ViewerProfile
from matchmind.generate_match import generate, write_match
from matchmind.interpreter.state import MatchState
from matchmind.risk.monitor import RiskMonitor
from matchmind.stream.replay import delay_between, load_events
from matchmind.tools.mcp_server import build_mcp_server
from matchmind.tools.registry import LiveStateRegistry, MatchTools

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

    def final_state(self, match_id: str) -> dict:
        state = MatchState(self.meta(match_id))
        for e in self.events(match_id):
            state.apply(e)
        return state.snapshot()


def create_app(
    data_dir: Path | str | None = None,
    pipeline=None,
    coach=None,
    judge=None,
    enable_agents: bool | None = None,
) -> FastAPI:
    """Build the service.

    pipeline: object with `async run(context, profiles) -> dict` (moments lane; tests inject a fake).
    coach:    object with `async run(context) -> dict` (risk lane; tests inject a fake).
    judge:    object with `async run(context) -> dict` (verdict lane; graded forecasts get their words here).
    enable_agents: None = build the Foundry agents on startup if configured; False = never call an LLM.
    """
    catalog = MatchCatalog(Path(data_dir) if data_dir else default_data_dir())
    registry = LiveStateRegistry()
    tools = MatchTools(registry)
    mcp = build_mcp_server(registry)
    agents = {"pipeline": pipeline, "coach": coach, "judge": judge}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        catalog.ensure_default()
        for mid in catalog.ids():  # MCP clients get full-match state even with no live stream
            try:
                registry.update(mid, catalog.meta(mid), catalog.final_state(mid))
            except Exception as exc:  # noqa: BLE001
                log.warning("could not preload %s: %r", mid, exc)
        if enable_agents is not False and any(agents[k] is None for k in ("pipeline", "coach", "judge")):
            from matchmind.agents.clients import build_coach, build_judge, build_pipeline, foundry_configured

            if foundry_configured():
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
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="MatchMind", version="0.3.0", lifespan=lifespan)
    app.state.catalog, app.state.registry, app.state.agents = catalog, registry, agents
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
    def health() -> dict:
        return {"status": "ok", "matches": len(catalog.ids()), "agents": agents["pipeline"] is not None,
                "coach": agents["coach"] is not None}

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
        agents_on: bool = Query(True, alias="agents"),
        coach_on: bool = Query(True, alias="coach"),
        min_importance: int = Query(3, ge=1, le=5),
    ) -> None:
        await websocket.accept()
        meta = catalog.meta(match_id)
        if meta is None:
            await websocket.close(code=4404, reason=f"unknown match {match_id!r}")
            return
        try:
            profile = ViewerProfile(mode=mode, language=lang, favorite_player_id=player)
        except ValidationError as exc:
            await websocket.close(code=4400, reason=f"bad viewer profile: {exc.errors()[0]['msg']}")
            return
        session = StreamSession(
            websocket, meta, catalog.events(match_id), registry,
            pipeline=agents["pipeline"] if agents_on else None,
            coach=agents["coach"] if coach_on else None,
            judge=agents["judge"] if agents_on else None,
            profile=profile, speed=speed, min_importance=min_importance,
        )
        await session.run()

    # MCP server (streamable HTTP) lives at /mcp; mounted last so API routes win.
    app.mount("/", mcp.streamable_http_app())
    return app


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


class StreamSession:
    """One WebSocket connection: replay loop + control reader + agent lanes + single sender."""

    def __init__(self, websocket, meta, events, registry, *, pipeline, coach, profile, speed, min_importance, judge=None):
        self.ws, self.meta, self.events, self.registry = websocket, meta, events, registry
        self.pipeline, self.coach, self.judge, self.profile, self.speed = pipeline, coach, judge, profile, speed
        self.min_importance = min_importance
        self.match_id = meta["match_id"]
        self.closed = False
        self.out: asyncio.Queue = asyncio.Queue()
        self.ledger = ForecastLedger()  # the Analyst's forecasts, graded 10 match minutes later

    async def _run_moment(self, context: dict) -> dict:
        """Moments lane runner: the insight goes to the viewer, its forecast into the ledger."""
        result = await self.pipeline.run(context, [self.profile])
        self.ledger.add(result, context)
        return result

    async def _run_verdict(self, context: dict) -> dict:
        """Verdict lane runner: the Judge's words also go back into the ledger, for the Analyst's next call."""
        result = await self.judge.run(context)
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
            "note": summary["note"],
        }

    # ------------------------------------------------------------ main

    async def run(self) -> None:
        sender = asyncio.create_task(self._sender())
        reader = asyncio.create_task(self._read_controls())
        moments = _Lane(self._run_moment, "insight", self.out,
                        lambda c: c["moment"]["importance"]) if self.pipeline is not None else None
        coach = _Lane(self.coach.run, "coach", self.out,
                      lambda c: 5 if c["trigger"] == "injury_concern" else 3) if self.coach is not None else None
        judge = _Lane(self._run_verdict, "verdict", self.out, lambda c: c["scores"].get("overall") or 0,
                      capacity=8) if self.judge is not None and moments is not None else None  # verdicts are few; keep them all
        state, monitor = MatchState(self.meta), RiskMonitor(self.meta)
        try:
            await self.out.put({
                "kind": "meta", "meta": self.meta, "speed": self.speed,
                "agents": self.pipeline is not None, "coach": self.coach is not None,
                "profile": self.profile.model_dump(),
            })
            prev: dict | None = None
            n = len(self.events)
            pending_risk = False
            for i, event in enumerate(self.events, start=1):
                if self.closed:
                    return
                await asyncio.sleep(delay_between(prev, event, self.speed))
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
                prev = event

            if moments is not None:
                await moments.close(AGENT_DRAIN_TIMEOUT_S)  # the last insight may still add a forecast
                self._grade_due(state.snapshot(), judge, flush=True)  # full time settles what is left
            for lane in (coach, judge):
                if lane is not None:
                    await lane.close(AGENT_DRAIN_TIMEOUT_S)
            await self.out.put({"kind": "end", "state": state.snapshot(), "risk": monitor.summary(),
                                "credibility": self.ledger.summary() if moments is not None else None})
            await self.out.put(None)
            await sender
        except (WebSocketDisconnect, RuntimeError):
            log.info("client disconnected from %s", self.match_id)
        finally:
            for task in (sender, reader, *(lane.task for lane in (moments, coach, judge) if lane is not None)):
                task.cancel()
            try:
                await self.ws.close()
            except RuntimeError:
                pass


app = create_app()
