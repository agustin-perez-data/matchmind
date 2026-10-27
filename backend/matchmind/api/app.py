"""FastAPI service: live replay + Interpreter + Risk Monitor + LLM agents + MCP server.

REST
    GET  /health
    GET  /matches                                   -> catalogue of matches in the data dir
    GET  /matches/{match_id}/meta                   -> teams, squads, load history (no latent state)
    GET  /matches/{match_id}/branches               -> counterfactual branches simulated so far
    POST /matches/{match_id}/branches               -> simulate an intervention (body: InterventionRequest)
    GET  /matches/{match_id}/branches/{branch_id}   -> branch summary + meta + full event stream
    POST /mcp                                       -> MCP server (streamable HTTP) with match-state tools

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

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError

from matchmind.agents.cache import AgentCache, cache_from_env
from matchmind.agents.observability import configure_observability, telemetry_enabled
from matchmind.agents.schemas import ViewerProfile
from matchmind.api.stream import StreamSession, parse_profile_spec
from matchmind.api.tts import Speaker, speech_config
from matchmind.generate_match import generate, write_match
from matchmind.interpreter.state import MatchState
from matchmind.sim.tracking import build_tracking
from matchmind.stream.replay import load_events, merge_timeline
from matchmind.tools.mcp_server import build_mcp_server
from matchmind.tools.registry import LiveStateRegistry, MatchTools

log = logging.getLogger("matchmind.api")

DEFAULT_MATCH = ("THU", "NBF", 42)


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

    def meta(self, match_id: str) -> dict:
        path = self.data_dir / f"{match_id}_meta.json"
        if not path.is_file():
            raise KeyError(match_id)
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
            self._frames[match_id] = build_tracking(self.events(match_id), meta)
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
    cache: AgentCache | bool | None = True,
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
                "judge_hosted": type(getattr(getattr(agents["judge"], "judge", None), "agent", None)).__name__ == "FoundryAgent",
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
            m = catalog.meta(mid)
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
        try:
            return catalog.meta(match_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown match {match_id!r}") from None

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
        try:
            meta = catalog.meta(match_id)
        except KeyError:
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


app = create_app()
