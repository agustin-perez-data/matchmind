"""Are the agents' words grounded in the numbers? Scored with the Azure AI Evaluation SDK.

    .venv/Scripts/python -m matchmind.agents.evaluate_groundedness --match THU-NBF-40
    .venv/Scripts/python -m matchmind.agents.evaluate_groundedness --match THU-NBF-40 --out eval/groundedness_THU-NBF-40.json

For every cached agent output of a match (data/cache/<match>.json, written by the live
stream or by warm_cache.py) the moment context the agents were given is rebuilt by
replaying the match, and `GroundednessEvaluator` (gpt-4.1-mini on Foundry as the judge)
scores, 1 to 5, whether the Narrator's line and the Analyst's read are substantiated by
that context. The Analyst's forecast is graded elsewhere (judge.py); this is about the
explanation and the commentary never inventing facts. With --run the pipeline is called
first for the moments that are not cached yet.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.interpreter.state import MatchState
from matchmind.stream.replay import load_events

AGENT_QUERIES = {
    "analyst": "Explain why this key moment of the match matters, grounded in the numbers provided.",
    "narrator": "Narrate this key moment of the match for the viewer, using only what happened.",
}


def contexts_for(match_id: str, data_dir: Path) -> tuple[dict, dict[int, dict]]:
    """Replay the match and keep the moment context of every key event, keyed by event_id."""
    meta = json.loads((data_dir / f"{match_id}_meta.json").read_text(encoding="utf-8"))
    state, out = MatchState(meta), {}
    for e in load_events(data_dir / f"{match_id}_events.jsonl"):
        state.apply(e)
        if e["type"] in MatchState.SNAPSHOT_TYPES:
            moment = detect_key_moment(e, state.snapshot())
            if moment is not None:
                out[int(e["event_id"])] = build_moment_context(moment, state.snapshot(), meta)
    return meta, out


def cached_insights(cache_dir: Path, match_id: str) -> list[tuple[str, int, dict]]:
    """(profile_key, event_id, result) for every cached insight of the match."""
    f = cache_dir / f"{match_id}.json"
    if not f.is_file():
        return []
    entries = json.loads(f.read_text(encoding="utf-8"))
    rows = []
    for key, result in entries.items():
        if not key.startswith("insight:"):
            continue
        _, event_id, profile_key = key.split(":", 2)
        rows.append((profile_key, int(event_id), result))
    return sorted(rows, key=lambda r: (r[0], r[1]))


def context_text(ctx: dict) -> str:
    """The facts the agents were given, minus the viewer bookkeeping, as the evaluator's source."""
    keep = ("clock", "score", "moment", "event", "teams", "momentum", "last_10_minutes", "players_involved",
            "watched_players", "risk_alerts", "game_state", "top_shooters")
    return json.dumps({k: ctx[k] for k in keep if k in ctx}, ensure_ascii=False)


def items_to_score(contexts: dict[int, dict], insights: list[tuple[str, int, dict]]) -> list[dict]:
    """One item per (moment, agent, profile): what was said, against what was known."""
    items = []
    for profile_key, event_id, result in insights:
        ctx = contexts.get(event_id)
        if ctx is None:
            continue
        analyst = result.get("analyst")
        if analyst:
            items.append({"agent": "analyst", "profile": profile_key, "event_id": event_id, "clock": ctx["clock"],
                          "response": f"{analyst['headline']}. {analyst['why_it_matters']} {analyst['tactical_read']} ({analyst['key_stat']})",
                          "context": context_text(ctx)})
        for vkey, view in (result.get("viewers") or {}).items():
            narration = (view or {}).get("narration")
            if narration and narration.get("text"):
                items.append({"agent": "narrator", "profile": vkey, "event_id": event_id, "clock": ctx["clock"],
                              "response": narration["text"], "context": context_text(ctx)})
    return items


def score_items(evaluator, items: list[dict]) -> list[dict]:
    """Run the evaluator on every item; it is synchronous, so this is plain sequential work."""
    scored = []
    for it in items:
        try:
            res = evaluator(query=AGENT_QUERIES[it["agent"]], context=it["context"], response=it["response"])
            score = float(res.get("groundedness", res.get("gpt_groundedness")))
            reason = res.get("groundedness_reason")
        except Exception as exc:  # noqa: BLE001
            score, reason = None, f"evaluator error: {exc!r}"
        scored.append({**it, "groundedness": score, "reason": reason})
        print(f"  {it['clock']} {it['agent']:<9} {it['profile']:<20} {score!s:>4}  {it['response'][:70]}", flush=True)
    return scored


def summarize(scored: list[dict], match_id: str, label: str) -> dict:
    out = {"match_id": match_id, "label": label, "items": len(scored), "agents": {}}
    for agent in ("analyst", "narrator"):
        rows = [r for r in scored if r["agent"] == agent and r["groundedness"] is not None]
        dist = Counter(int(r["groundedness"]) for r in rows)
        out["agents"][agent] = {
            "n": len(rows), "mean": round(sum(r["groundedness"] for r in rows) / len(rows), 2) if rows else None,
            "share_at_least_4": round(sum(1 for r in rows if r["groundedness"] >= 4) / len(rows), 2) if rows else None,
            "distribution": {str(k): dist.get(k, 0) for k in range(1, 6)},
            "weakest": sorted(rows, key=lambda r: r["groundedness"])[:3],
        }
    return out


def print_report(report: dict) -> None:
    print(f"\n{report['label']}: {report['match_id']}, {report['items']} items scored")
    for agent, a in report["agents"].items():
        print(f"  {agent:<9} n={a['n']:<3} mean {a['mean']}  >=4: {a['share_at_least_4']}  distribution 1..5: {list(a['distribution'].values())}")
        for w in a["weakest"][:2]:
            print(f"      weakest {w['groundedness']}: {w['response'][:80]!r}\n        {str(w['reason'])[:160]}")


def build_evaluator():
    from azure.ai.evaluation import AzureOpenAIModelConfiguration, GroundednessEvaluator

    from matchmind.agents.clients import load_env

    load_env()
    config = AzureOpenAIModelConfiguration(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4.1-mini"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    return GroundednessEvaluator(model_config=config)


async def run_missing(match_id: str, data_dir: Path, contexts: dict[int, dict], profile_spec: str, min_importance: int) -> None:
    """Call the real pipeline for the key moments not cached yet, writing them to the same cache the server uses."""
    from matchmind.agents.cache import AgentCache, insight_key
    from matchmind.agents.clients import build_pipeline, foundry_configured
    from matchmind.api.app import parse_profile_spec

    if not foundry_configured():
        print("Foundry is not configured; cannot run the pipeline")
        return
    profile = parse_profile_spec(profile_spec)
    cache = AgentCache(data_dir / "cache")
    pipeline = build_pipeline()
    for event_id, ctx in contexts.items():
        if ctx["moment"]["importance"] < min_importance or cache.get(match_id, "insight", insight_key(event_id, profile.key)):
            continue
        result = await pipeline.run(ctx, [profile])
        cache.put(match_id, "insight", insight_key(event_id, profile.key), result)
        print(f"  ran {ctx['clock']} {ctx['moment']['kind']} for {profile.key}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Groundedness of the agents' explanations and commentary")
    ap.add_argument("--match", default="THU-NBF-40")
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[3] / "data"))
    ap.add_argument("--run", default=None, help="profile spec (e.g. analyst:en) to run the pipeline for uncached moments first")
    ap.add_argument("--min-importance", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="max items to score (0 = all)")
    ap.add_argument("--label", default="groundedness")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    meta, contexts = contexts_for(args.match, data_dir)
    if args.run:
        asyncio.run(run_missing(args.match, data_dir, contexts, args.run, args.min_importance))
    insights = cached_insights(data_dir / "cache", args.match)
    items = items_to_score(contexts, insights)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print(f"nothing cached for {args.match}: stream it with the agents on, run warm_cache.py, or pass --run analyst:en")
        sys.exit(2)
    print(f"{meta['teams'][meta['home_id']]['name']} v {meta['teams'][meta['away_id']]['name']}: scoring {len(items)} items with GroundednessEvaluator")
    t0 = time.perf_counter()
    scored = score_items(build_evaluator(), items)
    report = summarize(scored, args.match, args.label)
    report["seconds"] = round(time.perf_counter() - t0)
    print_report(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"report": report, "scored": scored}, indent=1, ensure_ascii=False), encoding="utf-8")
        print("  written", out)


if __name__ == "__main__":
    main()
