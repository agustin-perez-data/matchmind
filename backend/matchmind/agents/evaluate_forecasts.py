"""Offline evaluation of the Analyst's 10-minute forecasts over many simulated matches.

    .venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10
    .venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10 --label baseline --out eval/forecasts_baseline.json
    .venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10 --instructions prompts/analyst_v2.txt --label v2
    .venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10 --no-loop --label no_feedback   # ablation

Every match is a fresh seed and a fresh pairing of the eight fictional clubs. The real
Analyst (Azure AI Foundry) is called once per key moment, in match order, exactly as in
the live stream: forecasts whose window has closed are graded (same code as the stream,
`agents/judge.py`) and, unless --no-loop, the Judge's verdicts feed the Analyst's next
call through `analyst_track_record`. The naive baseline is graded on the same windows.

The report is what goes in the README, and what makes a prompt change measurable:
run it before, run it after on the same seeds, compare the pooled means.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from matchmind.agents.judge import ForecastLedger, build_judge_context, grade_forecast, verdict_from_score
from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.generate_match import generate
from matchmind.interpreter.state import MatchState
from matchmind.sim.league import CLUBS

COMPONENTS = ("overall", "dominance", "goal", "watch")


def replay(events: list[dict], meta: dict, min_importance: int) -> tuple[ForecastLedger, list[tuple[object, dict]], dict]:
    """One pass over a match: the ledger learns the minute marks and settling events; key moments are kept
    with their snapshot, so each context can be built later with the track record of that moment."""
    state, ledger, moments = MatchState(meta), ForecastLedger(), []
    for e in events:
        state.apply(e)
        snapshot = state.snapshot()
        ledger.observe(e, snapshot)
        if e["type"] in MatchState.SNAPSHOT_TYPES:
            moment = detect_key_moment(e, snapshot)
            if moment is not None and moment.importance >= min_importance and moment.kind != "full_time":
                moments.append((moment, snapshot))
    return ledger, moments, state.snapshot()


async def call_with_retries(fn, sem: asyncio.Semaphore, attempts: int = 4, label: str = "call"):
    """One agent call; Foundry's Standard deployment rate-limits, so back off on failure."""
    async with sem:
        for i in range(attempts):
            try:
                return await fn()
            except Exception as exc:  # noqa: BLE001
                wait = 2.0 * (2 ** i)
                print(f"    {label} retry {i + 1}/{attempts} after {type(exc).__name__}: {str(exc)[:80]} (sleep {wait:.0f}s)")
                await asyncio.sleep(wait)
    return None


def _row(ctx: dict, pending, facts: dict, scores: dict, naive: dict) -> dict:
    return {
        "match_id": ctx["match_id"], "clock": ctx["clock"], "moment": ctx["moment"]["kind"],
        "forecast": pending.forecast, "naive": pending.naive, "facts": facts, "scores": scores, "naive_scores": naive,
        "had_track_record": ctx.get("analyst_track_record") is not None,
        "picked_home": pending.forecast.get("dominant_team_id") == ctx["home_id"],
        "picked_possession_leader": pending.forecast.get("dominant_team_id") == max(
            (ctx["home_id"], ctx["away_id"]), key=lambda t: ctx["teams"][t].get("possession_pct", 0)),
        "picked_xg_leader": pending.forecast.get("dominant_team_id") == pending.naive["dominant_team_id"],
        "picked_recent_xg_leader": pending.forecast.get("dominant_team_id") == max(
            (ctx["home_id"], ctx["away_id"]), key=lambda t: (ctx.get("last_10_minutes") or {"teams": {}})["teams"].get(t, {}).get("xg", 0)),
    }


async def run_match(analyst, judge, meta: dict, ledger: ForecastLedger, moments: list, final: dict, *,
                    sem: asyncio.Semaphore, loop: bool, language: str = "en") -> list[dict]:
    """Moments in order: settle what is due, feed the record back, forecast, repeat; flush at full time."""
    rows: list[dict] = []
    pendings: dict[int, tuple[object, dict]] = {}

    async def settle(snapshot: dict, *, flush: bool = False) -> None:
        for pending in ledger.due(snapshot, flush=flush):
            close = ledger.window_close(pending, final)
            facts, scores, naive = grade_forecast(pending, close, ledger.window_events(pending, close.get("event_id")))
            ledger.record({"event_id": pending.event_id, "scores": scores, "naive_scores": naive})
            ctx = pendings[pending.event_id][1]
            rows.append(_row(ctx, pending, facts, scores, naive))
            if loop:
                jctx = build_judge_context(pending, facts, scores, naive, meta, language)
                result = None
                if judge is not None:
                    result = await call_with_retries(lambda ctx=jctx: judge.run(ctx), sem, label="judge")
                if result is None:  # no Judge, or it failed: code words, no lesson
                    result = {"event_id": pending.event_id, "issued_clock": pending.issued_clock, "forecast": pending.forecast,
                              "facts": facts, "verdict": {"verdict": verdict_from_score(scores["overall"]), "lesson": None}}
                ledger.remember(result)

    for moment, snapshot in moments:
        await settle(snapshot)
        ctx = build_moment_context(moment, snapshot, meta, track_record=ledger.track_record() if loop else None)
        insight = await call_with_retries(lambda c=ctx: analyst.explain(c, language), sem, label="analyst")
        if insight is None:
            continue
        pending = ledger.add({"event_id": ctx["moment"]["event_id"], "analyst": insight.model_dump()}, ctx)
        if pending is not None:
            pendings[pending.event_id] = (pending, ctx)
    await settle(final, flush=True)
    return rows


def pooled(rows: list[dict], who: str) -> dict:
    out = {}
    for c in COMPONENTS:
        vals = [r[who][c] for r in rows if r[who].get(c) is not None]
        out[c] = {"mean": round(sum(vals) / len(vals), 3) if vals else None, "n": len(vals)}
    return out


def summarize(rows: list[dict], matches: int, label: str, seconds: float) -> dict:
    n = len(rows)
    share = lambda key: round(sum(1 for r in rows if r[key]) / n, 2) if n else None  # noqa: E731
    return {
        "label": label, "matches": matches, "forecasts": n, "seconds": round(seconds),
        "analyst": pooled(rows, "scores"), "naive": pooled(rows, "naive_scores"),
        "wins": {  # per window, who scored higher
            "analyst": sum(1 for r in rows if (r["scores"]["overall"] or 0) > (r["naive_scores"]["overall"] or 0)),
            "naive": sum(1 for r in rows if (r["scores"]["overall"] or 0) < (r["naive_scores"]["overall"] or 0)),
            "tie": sum(1 for r in rows if (r["scores"]["overall"] or 0) == (r["naive_scores"]["overall"] or 0)),
        },
        "with_track_record": pooled([r for r in rows if r["had_track_record"]], "scores")["overall"],
        "without_track_record": pooled([r for r in rows if not r["had_track_record"]], "scores")["overall"],
        "habits": {
            "picked_home": share("picked_home"),
            "picked_possession_leader": share("picked_possession_leader"),
            "picked_xg_leader": share("picked_xg_leader"),
            "picked_recent_xg_leader": share("picked_recent_xg_leader"),
            "named_a_player": round(sum(1 for r in rows if r["forecast"].get("watch_player_id")) / n, 2) if n else None,
            "goal_probability_mean": round(sum(r["forecast"]["goal_probability"] for r in rows) / n, 3) if n else None,
            "goal_probability_spread": round(max(r["forecast"]["goal_probability"] for r in rows) - min(r["forecast"]["goal_probability"] for r in rows), 2) if n else None,
            "windows_with_a_goal": round(sum(1 for r in rows if r["facts"]["goals"]) / n, 2) if n else None,
        },
    }


def print_report(report: dict) -> None:
    a, b = report["analyst"], report["naive"]
    print(f"\n{report['label']}: {report['matches']} matches, {report['forecasts']} forecasts graded, {report['seconds']} s")
    print(f"  {'claim':<16}{'Analyst':>10}{'naive':>10}{'n':>6}")
    for c in COMPONENTS:
        av, nv = a[c]["mean"], b[c]["mean"]
        print(f"  {c:<16}{(f'{av:.2f}' if av is not None else '-'):>10}{(f'{nv:.2f}' if nv is not None else '-'):>10}{a[c]['n']:>6}")
    w = report["wins"]
    print(f"  windows won: Analyst {w['analyst']}, naive {w['naive']}, tie {w['tie']}")
    wt, wo = report["with_track_record"], report["without_track_record"]
    print(f"  overall with a track record in the prompt: {wt['mean']} (n={wt['n']}), without: {wo['mean']} (n={wo['n']})")
    h = report["habits"]
    print(f"  habits: picked home {h['picked_home']}, possession leader {h['picked_possession_leader']}, xG leader {h['picked_xg_leader']}, "
          f"last-10 xG leader {h['picked_recent_xg_leader']}, named a player {h['named_a_player']}, "
          f"P(goal) mean {h['goal_probability_mean']} spread {h['goal_probability_spread']}, windows with a goal {h['windows_with_a_goal']}")


async def main_async(args: argparse.Namespace) -> int:
    from matchmind.agents.clients import build_analyst, build_judge, foundry_configured

    if not foundry_configured():
        print("Foundry is not configured: set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY in backend/.env")
        return 2
    instructions = Path(args.instructions).read_text(encoding="utf-8") if args.instructions else None
    analyst = build_analyst(tools=None, instructions=instructions)
    judge = None if (args.no_loop or args.no_judge) else build_judge()
    rng = random.Random(args.seed0)
    ids = [c[0] for c in CLUBS]
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.perf_counter()
    rows: list[dict] = []

    async def one(i: int) -> list[dict]:
        home, away = rng_pairs[i]
        events, meta = generate(home, away, seed=args.seed0 + i)
        ledger, moments, final = replay(events, meta, args.min_importance)
        moments = moments[: args.limit] if args.limit else moments
        print(f"[{i + 1}/{args.matches}] {meta['match_id']}: {len(moments)} key moments", flush=True)
        match_rows = await run_match(analyst, judge, meta, ledger, moments, final, sem=sem, loop=not args.no_loop)
        for r in match_rows:
            s, nv = r["scores"], r["naive_scores"]
            print(f"    {meta['match_id']} {r['clock']} {r['moment']:<15} analyst {s['overall']!s:<6} naive {nv['overall']!s:<6} "
                  f"dom {s['dominance']} goal {s['goal']} watch {s['watch']}{' *' if r['had_track_record'] else '  '} | {r['forecast']['claim'][:66]}", flush=True)
        return match_rows

    rng_pairs = [tuple(rng.sample(ids, 2)) for _ in range(args.matches)]
    for batch in (list(range(args.matches))[k:k + args.parallel_matches] for k in range(0, args.matches, args.parallel_matches)):
        for match_rows in await asyncio.gather(*(one(i) for i in batch)):
            rows.extend(match_rows)
    report = summarize(rows, args.matches, args.label, time.perf_counter() - t0)
    report.update({"seed0": args.seed0, "min_importance": args.min_importance, "instructions": args.instructions,
                   "loop": not args.no_loop, "judge_words": judge is not None})
    print_report(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"report": report, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  written {out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade the Analyst's forecasts over simulated matches")
    parser.add_argument("--matches", type=int, default=10)
    parser.add_argument("--seed0", type=int, default=5000, help="first match seed; same seeds = same matches for A/B runs")
    parser.add_argument("--min-importance", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="max key moments per match (0 = all)")
    parser.add_argument("--concurrency", type=int, default=3, help="simultaneous Foundry calls")
    parser.add_argument("--parallel-matches", type=int, default=3, help="matches in flight at once (each one is sequential inside)")
    parser.add_argument("--instructions", default=None, help="file with alternative Analyst instructions (prompt variant)")
    parser.add_argument("--no-loop", action="store_true", help="ablation: do not feed graded verdicts back to the Analyst")
    parser.add_argument("--no-judge", action="store_true", help="feed back code verdicts without the Judge's words")
    parser.add_argument("--label", default="current")
    parser.add_argument("--out", default=None, help="write report + per-forecast rows as JSON")
    raise SystemExit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
