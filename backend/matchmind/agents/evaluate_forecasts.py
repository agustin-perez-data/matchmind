"""Offline evaluation of the Analyst's 10-minute forecasts over many simulated matches.

    .venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10
    .venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10 --label baseline --out eval/forecasts_baseline.json
    .venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10 --instructions prompts/analyst_v2.txt --label v2

Every match is a fresh seed and a fresh pairing of the eight fictional clubs. The real
Analyst (Azure AI Foundry) is called once per key moment, exactly as in the live stream;
its forecasts are graded by the same code the stream uses (`agents/judge.py`), on windows
closed at the exact minute mark, next to the naive baseline. The Judge agent is not
needed here: the scores are deterministic, only the words are the Judge's.

The report is what goes in the README, and what makes a prompt change measurable:
run it before, run it after, compare the pooled means.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from matchmind.agents.judge import ForecastLedger, grade_forecast
from matchmind.agents.moments import build_moment_context, detect_key_moment
from matchmind.generate_match import generate
from matchmind.interpreter.state import MatchState
from matchmind.sim.league import CLUBS

COMPONENTS = ("overall", "dominance", "goal", "watch")


def replay(events: list[dict], meta: dict, min_importance: int) -> tuple[ForecastLedger, list[dict], dict]:
    """One pass over a match: the ledger learns the minute marks and settling events, we collect the key moments."""
    state, ledger, contexts = MatchState(meta), ForecastLedger(), []
    for e in events:
        state.apply(e)
        snapshot = state.snapshot()
        ledger.observe(e, snapshot)
        if e["type"] in MatchState.SNAPSHOT_TYPES:
            moment = detect_key_moment(e, snapshot)
            if moment is not None and moment.importance >= min_importance and moment.kind != "full_time":
                contexts.append(build_moment_context(moment, snapshot, meta))
    return ledger, contexts, state.snapshot()


async def forecast_with_retries(analyst, context: dict, sem: asyncio.Semaphore, attempts: int = 4) -> dict | None:
    """One Analyst call; Foundry's Standard deployment rate-limits, so back off on failure."""
    async with sem:
        for i in range(attempts):
            try:
                insight = await analyst.explain(context, "en")
                return insight.model_dump()
            except Exception as exc:  # noqa: BLE001
                wait = 2.0 * (2 ** i)
                print(f"    retry {i + 1}/{attempts} after {type(exc).__name__}: {str(exc)[:80]} (sleep {wait:.0f}s)")
                await asyncio.sleep(wait)
    return None


def grade_match(ledger: ForecastLedger, contexts: list[dict], insights: list[dict | None], final: dict) -> list[dict]:
    rows = []
    for ctx, analyst in zip(contexts, insights):
        if analyst is None:
            continue
        pending = ledger.add({"event_id": ctx["moment"]["event_id"], "analyst": analyst}, ctx)
        if pending is None:
            continue
        close = ledger.window_close(pending, final)
        facts, scores, naive = grade_forecast(pending, close, ledger.window_events(pending, close.get("event_id")))
        rows.append({
            "match_id": ctx["match_id"], "clock": ctx["clock"], "moment": ctx["moment"]["kind"],
            "forecast": pending.forecast, "naive": pending.naive, "facts": facts, "scores": scores, "naive_scores": naive,
            "picked_home": pending.forecast.get("dominant_team_id") == ctx["home_id"],
            "picked_possession_leader": pending.forecast.get("dominant_team_id") == max(
                (ctx["home_id"], ctx["away_id"]), key=lambda t: ctx["teams"][t].get("possession_pct", 0)),
            "picked_xg_leader": pending.forecast.get("dominant_team_id") == pending.naive["dominant_team_id"],
        })
    return rows


def pooled(rows: list[dict], who: str) -> dict:
    out = {}
    for c in COMPONENTS:
        vals = [r[who][c] for r in rows if r[who].get(c) is not None]
        out[c] = {"mean": round(sum(vals) / len(vals), 3) if vals else None, "n": len(vals)}
    return out


def summarize(rows: list[dict], matches: int, label: str, seconds: float) -> dict:
    n = len(rows)
    return {
        "label": label, "matches": matches, "forecasts": n, "seconds": round(seconds),
        "analyst": pooled(rows, "scores"), "naive": pooled(rows, "naive_scores"),
        "wins": {  # per window, who scored higher on the claims both made
            "analyst": sum(1 for r in rows if (r["scores"]["overall"] or 0) > (r["naive_scores"]["overall"] or 0)),
            "naive": sum(1 for r in rows if (r["scores"]["overall"] or 0) < (r["naive_scores"]["overall"] or 0)),
            "tie": sum(1 for r in rows if (r["scores"]["overall"] or 0) == (r["naive_scores"]["overall"] or 0)),
        },
        "habits": {
            "picked_home": round(sum(r["picked_home"] for r in rows) / n, 2) if n else None,
            "picked_possession_leader": round(sum(r["picked_possession_leader"] for r in rows) / n, 2) if n else None,
            "picked_xg_leader": round(sum(r["picked_xg_leader"] for r in rows) / n, 2) if n else None,
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
    h = report["habits"]
    print(f"  habits: picked home {h['picked_home']}, possession leader {h['picked_possession_leader']}, xG leader {h['picked_xg_leader']}, "
          f"named a player {h['named_a_player']}, P(goal) mean {h['goal_probability_mean']} spread {h['goal_probability_spread']}, "
          f"windows with a goal {h['windows_with_a_goal']}")


async def main_async(args: argparse.Namespace) -> int:
    from matchmind.agents.clients import build_analyst, foundry_configured

    if not foundry_configured():
        print("Foundry is not configured: set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY in backend/.env")
        return 2
    instructions = Path(args.instructions).read_text(encoding="utf-8") if args.instructions else None
    analyst = build_analyst(tools=None, instructions=instructions)
    rng = random.Random(args.seed0)
    ids = [c[0] for c in CLUBS]
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.perf_counter()
    rows: list[dict] = []
    for i in range(args.matches):
        home, away = rng.sample(ids, 2)
        events, meta = generate(home, away, seed=args.seed0 + i)
        ledger, contexts, final = replay(events, meta, args.min_importance)
        contexts = contexts[: args.limit] if args.limit else contexts
        print(f"[{i + 1}/{args.matches}] {meta['match_id']}: {len(contexts)} key moments", flush=True)
        insights = await asyncio.gather(*(forecast_with_retries(analyst, c, sem) for c in contexts))
        match_rows = grade_match(ledger, contexts, list(insights), final)
        rows.extend(match_rows)
        for r in match_rows:
            s, nv = r["scores"], r["naive_scores"]
            print(f"    {r['clock']} {r['moment']:<15} analyst {s['overall']!s:<6} naive {nv['overall']!s:<6} "
                  f"dom {s['dominance']} goal {s['goal']} watch {s['watch']}  | {r['forecast']['claim'][:70]}", flush=True)
    report = summarize(rows, args.matches, args.label, time.perf_counter() - t0)
    report["seed0"], report["min_importance"], report["instructions"] = args.seed0, args.min_importance, args.instructions
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
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--instructions", default=None, help="file with alternative Analyst instructions (prompt variant)")
    parser.add_argument("--label", default="current")
    parser.add_argument("--out", default=None, help="write report + per-forecast rows as JSON")
    raise SystemExit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
