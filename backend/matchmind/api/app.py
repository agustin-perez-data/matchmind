"""FastAPI service: live replay streamer + Interpreter + LLM agents + MCP server.

REST
    GET  /health
    GET  /matches                      -> catalogue of matches in the data dir
    GET  /matches/{match_id}/meta      -> teams, squads, load history (no latent state)
    POST /mcp                          -> MCP server (streamable HTTP) with match-state tools

WebSocket
    WS   /ws/matches/{match_id}?speed=10&mode=analyst&lang=en&player=THU-19&agents=1&min_importance=3
        server -> client
            {"kind": "meta",    "meta": {...}, "speed": 10, "agents": true, "profile": {...}}
            {"kind": "event",   "event": {...}, "state": {...}?}  # state on key events / every N
            {"kind": "insight", "event_id": 812, "clock": "34:41", "moment": {...},
                                "analyst": {...}, "viewers": {"<profile key>": {...}}, "latency_ms": 4100}
            {"kind": "ack",     "speed": 50} | {"kind": "ack", "profile": {...}}
            {"kind": "end",     "state": {...}}
        client -> server
            {"speed": 50}                                   # change replay speed live
            {"profile": {"mode": "casual", "language": "es"}}  # switch viewer profile live

speed: 1 = real time, 10 = ten times faster, 0 = as fast as possible.
Agents run in the background, one key moment at a time per connection; if a
new moment arrives while one is being explained, the more important one wins.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.agents.schemas import ViewerProfile
from matchmind.generate_match import generate, write_match
from matchmind.interpreter.state import MatchState
from matchmind.stream.replay import delay_between, load_events
from matchmind.tools.mcp_server import build_mcp_server
from matchmind.tools.registry import LiveStateRegistry, MatchTools

log = logging.getLogger("matchmind.api")

SNAPSHOT_EVERY = 25  # also attach a state snapshot every N events
DEFAULT_MATCH = ("THU", "NBF", 42)
AGENT_DRAIN_TIMEOUT_S = 45.0  # how long the end of a stream waits for the last insight


def default_data_dir() -> Path:
    env = os.environ.get("MATCHMIND_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "data"


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
    enable_agents: bool | None = None,
) -> FastAPI:
    """Build the service.

    pipeline: object with `async run(context, profiles) -> dict` (tests inject a fake).
    enable_agents: None = build the Foundry pipeline on startup if configured;
                   False = never call an LLM.
    """
    catalog = MatchCatalog(Path(data_dir) if data_dir else default_data_dir())
    registry = LiveStateRegistry()
    mcp = build_mcp_server(registry)
    agents = {"pipeline": pipeline}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        catalog.ensure_default()
        for mid in catalog.ids():  # MCP clients get full-match state even with no live stream
            try:
                registry.update(mid, catalog.meta(mid), catalog.final_state(mid))
            except Exception as exc:  # noqa: BLE001
                log.warning("could not preload %s: %r", mid, exc)
        if agents["pipeline"] is None and enable_agents is not False:
            from matchmind.agents.clients import build_pipeline, foundry_configured

            if foundry_configured():
                try:
                    agents["pipeline"] = build_pipeline(tools=MatchTools(registry).as_functions())
                    log.info("LLM agents enabled (Azure AI Foundry)")
                except Exception as exc:  # noqa: BLE001
                    log.warning("LLM agents disabled: %r", exc)
            else:
                log.info("LLM agents disabled: Foundry not configured")
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="MatchMind", version="0.2.0", lifespan=lifespan)
    app.state.catalog, app.state.registry, app.state.agents = catalog, registry, agents

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=307)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "matches": len(catalog.ids()), "agents": agents["pipeline"] is not None}

    @app.get("/matches")
    def list_matches() -> list[dict]:
        out = []
        for mid in catalog.ids():
            m = catalog.meta(mid) or {}
            out.append({
                "match_id": mid,
                "home_id": m.get("home_id"),
                "away_id": m.get("away_id"),
                "home": m.get("teams", {}).get(m.get("home_id"), {}).get("name"),
                "away": m.get("teams", {}).get(m.get("away_id"), {}).get("name"),
                "score": m.get("score"),
                "n_events": m.get("n_events"),
            })
        return out

    @app.get("/matches/{match_id}/meta")
    def match_meta(match_id: str) -> dict:
        meta = catalog.meta(match_id)
        if meta is None:
            raise HTTPException(status_code=404, detail=f"unknown match {match_id!r}")
        return meta

    @app.websocket("/ws/matches/{match_id}")
    async def stream_match(
        websocket: WebSocket,
        match_id: str,
        speed: float = Query(1.0, ge=0),
        mode: str = Query("analyst"),
        lang: str = Query("en"),
        player: str | None = Query(None),
        agents_on: bool = Query(True, alias="agents"),
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
        pipeline = agents["pipeline"] if agents_on else None
        session = StreamSession(websocket, meta, catalog.events(match_id), registry, pipeline, profile, speed, min_importance)
        await session.run()

    # MCP server (streamable HTTP) lives at /mcp; mounted last so API routes win.
    app.mount("/", mcp.streamable_http_app())
    return app


class StreamSession:
    """One WebSocket connection: replay loop + control reader + agent worker + single sender."""

    def __init__(self, websocket, meta, events, registry, pipeline, profile, speed, min_importance):
        self.ws, self.meta, self.events, self.registry = websocket, meta, events, registry
        self.pipeline, self.profile, self.speed, self.min_importance = pipeline, profile, speed, min_importance
        self.match_id = meta["match_id"]
        self.closed = False
        self.out: asyncio.Queue = asyncio.Queue()
        self.moments: asyncio.Queue = asyncio.Queue(maxsize=1)

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

    async def _agent_worker(self) -> None:
        while True:
            ctx = await self.moments.get()
            try:
                if ctx is None:
                    return
                try:
                    result = await self.pipeline.run(ctx, [self.profile])
                    await self.out.put({"kind": "insight", **result})
                except Exception as exc:  # noqa: BLE001
                    log.warning("agent pipeline failed at %s: %r", ctx.get("clock"), exc)
                    await self.out.put({"kind": "insight_error", "event_id": ctx["moment"]["event_id"], "detail": repr(exc)})
            finally:
                self.moments.task_done()

    def _offer_moment(self, ctx: dict) -> None:
        """Keep at most one pending moment; the more important one survives."""
        if self.moments.full():
            waiting = self.moments.get_nowait()
            self.moments.task_done()
            if waiting is not None and waiting["moment"]["importance"] > ctx["moment"]["importance"]:
                ctx = waiting
        self.moments.put_nowait(ctx)

    # ------------------------------------------------------------ main

    async def run(self) -> None:
        sender = asyncio.create_task(self._sender())
        reader = asyncio.create_task(self._read_controls())
        worker = asyncio.create_task(self._agent_worker()) if self.pipeline is not None else None
        state = MatchState(self.meta)
        try:
            await self.out.put({
                "kind": "meta", "meta": self.meta, "speed": self.speed,
                "agents": self.pipeline is not None, "profile": self.profile.model_dump(),
            })
            prev: dict | None = None
            n = len(self.events)
            for i, event in enumerate(self.events, start=1):
                if self.closed:
                    return
                await asyncio.sleep(delay_between(prev, event, self.speed))
                state.apply(event)
                message: dict = {"kind": "event", "event": event}
                key_event = event["type"] in MatchState.SNAPSHOT_TYPES
                if key_event or i % SNAPSHOT_EVERY == 0 or i == n:
                    snapshot = state.snapshot()
                    message["state"] = snapshot
                    self.registry.update(self.match_id, self.meta, snapshot)
                    if worker is not None and key_event:
                        moment = detect_key_moment(event, snapshot)
                        if moment is not None and moment.importance >= self.min_importance:
                            watched = [self.profile.favorite_player_id] if self.profile.favorite_player_id else None
                            self._offer_moment(build_moment_context(moment, snapshot, self.meta, watched_players=watched))
                await self.out.put(message)
                prev = event
            if worker is not None:
                await self.moments.put(None)
                try:
                    await asyncio.wait_for(worker, AGENT_DRAIN_TIMEOUT_S)
                except asyncio.TimeoutError:
                    log.warning("agent worker did not finish within %ss", AGENT_DRAIN_TIMEOUT_S)
            await self.out.put({"kind": "end", "state": state.snapshot()})
            await self.out.put(None)
            await sender
        except (WebSocketDisconnect, RuntimeError):
            log.info("client disconnected from %s", self.match_id)
        finally:
            for task in (sender, reader, worker):
                if task is not None:
                    task.cancel()
            try:
                await self.ws.close()
            except RuntimeError:
                pass


app = create_app()
