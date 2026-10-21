"""CLI: run the Analyst / Narrator / Director pipeline on a match's key moments.

    python -m matchmind.agents.demo --match THU-NBF-42 --limit 3 --mode analyst --mode commentator:es

Replays the recorded match through the Interpreter, picks the most important
key moments and calls the real Foundry agents. Prints every card and latency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from matchmind.agents.clients import build_pipeline, foundry_configured
from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.agents.schemas import ViewerProfile
from matchmind.interpreter.state import MatchState
from matchmind.stream.replay import load_events
from matchmind.tools.registry import LiveStateRegistry, MatchTools


def parse_profile(spec: str) -> ViewerProfile:
    """'analyst' | 'commentator:es' | 'player_focus:en:THU-19'."""
    parts = spec.split(":")
    return ViewerProfile(
        mode=parts[0],
        language=parts[1] if len(parts) > 1 else "en",
        favorite_player_id=parts[2] if len(parts) > 2 else None,
    )


def collect_moments(
    data_dir: Path, match_id: str, min_importance: int, watched: list[str] | None = None
) -> tuple[dict, list[tuple[dict, dict]]]:
    meta = json.loads((data_dir / f"{match_id}_meta.json").read_text(encoding="utf-8"))
    state = MatchState(meta)
    out = []
    for e in load_events(data_dir / f"{match_id}_events.jsonl"):
        state.apply(e)
        m = detect_key_moment(e, state.snapshot())
        if m is not None and m.importance >= min_importance:
            out.append((build_moment_context(m, state.snapshot(), meta, watched_players=watched), state.snapshot()))
    return meta, out


async def main_async(args: argparse.Namespace) -> int:
    if not foundry_configured():
        print("Foundry is not configured: set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY in backend/.env")
        return 2
    data_dir = Path(args.data_dir)
    profiles = [parse_profile(s) for s in args.mode] or [ViewerProfile()]
    watched = [p.favorite_player_id for p in profiles if p.favorite_player_id]
    meta, moments = collect_moments(data_dir, args.match, args.min_importance, watched)
    moments = moments[: args.limit]

    registry = LiveStateRegistry()
    tools = MatchTools(registry)
    pipeline = build_pipeline(tools=tools.as_functions())
    print(f"{meta['teams'][meta['home_id']]['name']} vs {meta['teams'][meta['away_id']]['name']} - {len(moments)} moments, profiles {[p.key for p in profiles]}\n")

    for ctx, snapshot in moments:
        registry.update(args.match, meta, snapshot)
        result = await pipeline.run(ctx, profiles)
        print("=" * 78)
        print(f"{ctx['clock']}  {ctx['moment']['summary']}   [{result['latency_ms']} ms]")
        if result["analyst"]:
            a = result["analyst"]
            print(f"  ANALYST   {a['headline']}  (confidence {a['confidence']:.2f})")
            print(f"            why: {a['why_it_matters']}")
            print(f"            read: {a['tactical_read']}")
            print(f"            stat: {a['key_stat']}")
        for key, view in result["viewers"].items():
            n, d = view["narration"], view["decision"]
            print(f"  [{key}]")
            if n:
                print(f"    NARRATOR  {n['text']}")
            if d:
                print(f"    DIRECTOR  show={d['show']} priority={d['priority']} headline={d['headline']!r}"
                      + (f" note={d['personalized_note']!r}" if d.get("personalized_note") else ""))
        for err in result["errors"]:
            print(f"  ERROR {err}")
        print(f"  ORCHESTRATION {result.get('orchestration', 'direct')}")
        for ev in result.get("trace", []):
            extra = {k: v for k, v in ev.items() if k not in ("t", "kind", "agent")}
            print(f"    {ev['t']:>6} ms  {ev['kind']:<11} {ev.get('agent') or '':<9} {extra}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MatchMind LLM agents on a recorded match")
    parser.add_argument("--match", default="THU-NBF-42")
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[3] / "data"))
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--min-importance", type=int, default=3)
    parser.add_argument("--mode", action="append", default=[], help="viewer profile, e.g. analyst, casual:es, player_focus:en:THU-19")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
