"""FastAPI streamer: replays recorded synthetic matches as a live WebSocket feed.

REST
    GET  /health
    GET  /matches                      -> catalogue of matches in the data dir
    GET  /matches/{match_id}/meta      -> teams, squads, load history (no latent state)

WebSocket
    WS   /ws/matches/{match_id}?speed=10
        server -> client
            {"kind": "meta",  "meta": {...}, "speed": 10}
            {"kind": "event", "event": {...}, "state": {...}?}   # state on key events / every N
            {"kind": "ack",   "speed": 50}                       # after a speed change
            {"kind": "end",   "state": {...}}
        client -> server
            {"speed": 50}                                        # change replay speed live

speed: 1 = real time, 10 = ten times faster, 0 = as fast as possible.
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

from matchmind.generate_match import generate, write_match
from matchmind.interpreter.state import MatchState
from matchmind.stream.replay import delay_between, load_events

log = logging.getLogger("matchmind.api")

SNAPSHOT_EVERY = 25  # also attach a state snapshot every N events
DEFAULT_MATCH = ("THU", "NBF", 42)


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


def create_app(data_dir: Path | str | None = None) -> FastAPI:
    catalog = MatchCatalog(Path(data_dir) if data_dir else default_data_dir())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        catalog.ensure_default()
        yield

    app = FastAPI(title="MatchMind streamer", version="0.1.0", lifespan=lifespan)
    app.state.catalog = catalog

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=307)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "matches": len(catalog.ids())}

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
    async def stream_match(websocket: WebSocket, match_id: str, speed: float = Query(1.0, ge=0)) -> None:
        await websocket.accept()
        meta = catalog.meta(match_id)
        if meta is None:
            await websocket.close(code=4404, reason=f"unknown match {match_id!r}")
            return
        events = catalog.events(match_id)
        await _replay(websocket, meta, events, speed)

    return app


async def _replay(websocket: WebSocket, meta: dict, events: list[dict], speed: float) -> None:
    control = {"speed": speed, "closed": False, "acks": []}

    async def read_controls() -> None:
        while True:
            try:
                msg = await websocket.receive_json()
            except (WebSocketDisconnect, RuntimeError):
                control["closed"] = True
                return
            except ValueError:
                continue  # not JSON: ignore
            if isinstance(msg, dict) and "speed" in msg:
                try:
                    new_speed = max(0.0, float(msg["speed"]))
                except (TypeError, ValueError):
                    continue
                control["speed"] = new_speed
                control["acks"].append(new_speed)

    reader = asyncio.create_task(read_controls())
    state = MatchState(meta)
    try:
        await websocket.send_json({"kind": "meta", "meta": meta, "speed": control["speed"]})
        prev: dict | None = None
        for i, event in enumerate(events, start=1):
            if control["closed"]:
                return
            delay = delay_between(prev, event, control["speed"])
            await asyncio.sleep(delay)  # sleep(0) still yields so control messages get read
            while control["acks"]:
                await websocket.send_json({"kind": "ack", "speed": control["acks"].pop(0)})
            state.apply(event)
            message: dict = {"kind": "event", "event": event}
            if event["type"] in MatchState.SNAPSHOT_TYPES or i % SNAPSHOT_EVERY == 0 or i == len(events):
                message["state"] = state.snapshot()
            await websocket.send_json(message)
            prev = event
        await websocket.send_json({"kind": "end", "state": state.snapshot()})
    except (WebSocketDisconnect, RuntimeError):
        log.info("client disconnected from %s", meta.get("match_id"))
    finally:
        reader.cancel()
        try:
            await websocket.close()
        except RuntimeError:
            pass


app = create_app()
