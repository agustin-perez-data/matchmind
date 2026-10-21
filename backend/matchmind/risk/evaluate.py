"""Offline evaluation of the Risk Monitor over many simulated matches.

    python -m matchmind.risk.evaluate --matches 40
    python -m matchmind.risk.evaluate --matches 40 --grid      # small weight/threshold sweep

Every match is a fresh seed and a fresh pairing of the eight fictional clubs.
Ground truth is the observable `injury_concern` stream. The report is what goes
in the README: model vs naive baseline, same windows machinery, same horizon.
"""

from __future__ import annotations

import argparse
import itertools
import random

from matchmind.generate_match import generate
from matchmind.interpreter.state import MatchState
from matchmind.risk.monitor import NaiveMinutesBaseline, RiskModel, RiskMonitor
from matchmind.sim.league import CLUBS


def evaluate_matches(n: int = 20, seed0: int = 1000, model: RiskModel | None = None,
                     threshold: float = 0.5, horizon_min: int = 15) -> dict:
    """Aggregate scorecard over n simulated matches (pooled counts, not averaged ratios)."""
    rng = random.Random(seed0)
    totals = {k: {"alerts": 0, "true_alerts": 0, "concerns": 0, "covered": 0, "lead_sum": 0.0,
                  "ranked": 0, "top3": 0, "rank_pct_sum": 0.0, "random_sum": 0.0} for k in ("model", "baseline")}
    ids = [c[0] for c in CLUBS]
    for i in range(n):
        home, away = rng.sample(ids, 2)
        events, meta = generate(home, away, seed=seed0 + i)
        state = MatchState(meta)
        monitor = RiskMonitor(meta, model=model or RiskModel(), baseline=NaiveMinutesBaseline(),
                              horizon_min=horizon_min, threshold=threshold)
        for e in events:
            state.apply(e)
            monitor.observe(e, state.snapshot())
        sc = monitor.scorecard()
        for k in totals:
            for f in ("alerts", "true_alerts", "concerns", "covered"):
                totals[k][f] += sc[k][f]
            if sc[k]["mean_lead_minutes"] is not None:
                totals[k]["lead_sum"] += sc[k]["mean_lead_minutes"] * sc[k]["covered"]
            r = sc[k]["ranked_concerns"]
            totals[k]["ranked"] += r
            totals[k]["top3"] += sc[k]["top3_hits"]
            totals[k]["rank_pct_sum"] += sc[k]["mean_rank_pct"] * r
            totals[k]["random_sum"] += sc[k]["top3_random_rate"] * r
    report = {"matches": n, "horizon_minutes": horizon_min, "threshold": threshold}
    for k, t in totals.items():
        report[k] = {
            "alerts": t["alerts"],
            "true_alerts": t["true_alerts"],
            "precision": round(t["true_alerts"] / t["alerts"], 3) if t["alerts"] else 0.0,
            "concerns": t["concerns"],
            "covered": t["covered"],
            "recall": round(t["covered"] / t["concerns"], 3) if t["concerns"] else 0.0,
            "mean_lead_minutes": round(t["lead_sum"] / t["covered"], 1) if t["covered"] else None,
            "alerts_per_match": round(t["alerts"] / n, 1),
            "ranked_concerns": t["ranked"],
            "top3_rate": round(t["top3"] / t["ranked"], 3) if t["ranked"] else 0.0,
            "top3_random_rate": round(t["random_sum"] / t["ranked"], 3) if t["ranked"] else 0.0,
            "mean_rank_pct": round(t["rank_pct_sum"] / t["ranked"], 1) if t["ranked"] else 0.0,
        }
    return report


def _print(report: dict) -> None:
    print(f"matches={report['matches']}  horizon={report['horizon_minutes']}min  threshold={report['threshold']}")
    print(f"{'':10s}{'alerts':>8s}{'true':>6s}{'precision':>11s}{'concerns':>10s}{'covered':>9s}{'recall':>8s}{'lead':>7s}"
          f"{'/match':>8s}{'top3':>8s}{'random':>8s}{'rank%':>8s}")
    for k in ("model", "baseline"):
        r = report[k]
        print(f"{k:10s}{r['alerts']:8d}{r['true_alerts']:6d}{r['precision']:11.3f}{r['concerns']:10d}{r['covered']:9d}"
              f"{r['recall']:8.3f}{str(r['mean_lead_minutes']):>7s}{r['alerts_per_match']:8.1f}"
              f"{r['top3_rate']:8.3f}{r['top3_random_rate']:8.3f}{r['mean_rank_pct']:8.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the Risk Monitor offline")
    ap.add_argument("--matches", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--grid", action="store_true", help="sweep a few weight/threshold combinations")
    args = ap.parse_args()

    if not args.grid:
        _print(evaluate_matches(args.matches, args.seed0, threshold=args.threshold))
        return

    print("grid over feature weights (threshold fixed at 0.5) -> ranking quality first, windows second")
    rows = []
    for acwr, minutes, effort, sprint in itertools.product((0.0, 2.5), (0.8, 2.4), (4.0, 12.0, 24.0), (0.0, 1.5)):
        model = RiskModel(acwr=acwr, minutes=minutes, effort=effort, sprint_density=sprint)
        m = evaluate_matches(args.matches, args.seed0, model=model, threshold=args.threshold)["model"]
        rows.append((m["top3_rate"], -m["mean_rank_pct"], acwr, minutes, effort, sprint, m))
        print(f"  done acwr={acwr} minutes={minutes} effort={effort} sprint={sprint}: top3={m['top3_rate']:.3f} "
              f"rank%={m['mean_rank_pct']:.1f} R={m['recall']:.3f} alerts/match={m['alerts_per_match']}", flush=True)
    rows.sort(key=lambda r: (-r[0], -r[1]))
    print("\nBEST (by top-3 rate, then mean rank %):")
    for top3, neg_rank, acwr, minutes, effort, sprint, m in rows[:12]:
        print(f"top3={top3:.3f} (random {m['top3_random_rate']:.3f}) rank%={-neg_rank:5.1f}  "
              f"acwr={acwr} minutes={minutes} effort={effort} sprint={sprint}  "
              f"P={m['precision']:.3f} R={m['recall']:.3f} lead={m['mean_lead_minutes']} alerts/match={m['alerts_per_match']}")


if __name__ == "__main__":
    main()
