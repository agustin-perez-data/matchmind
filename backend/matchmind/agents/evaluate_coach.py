"""Coach evaluation on the Foundry project: did the Coach use its tools before deciding?

Takes real bench situations from a replay (every high risk window and knock of a match, as the stream builds
them with build_coach_context), runs the Coach agent on each through Agent Framework's `evaluate_agent`, and
grades the runs with the project's built-in evaluators:
    tool_call_accuracy   were get_player_workload / get_risk_windows called with the right ids, and used
    task_adherence       did the proposal follow the instructions (minute, team, like-for-like, hold allowed)
    intent_resolution    did it answer the bench's actual question
The run lands in the project's Evaluations page (report_url). Needs FOUNDRY_PROJECT_ENDPOINT and `az login`
(or a managed identity) with Foundry User on the project.

    python -m matchmind.agents.evaluate_coach [--match THU-NBF-40] [--limit 10] [--out file.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from matchmind.agents.coach import build_coach_context
from matchmind.interpreter.state import MatchState
from matchmind.risk.monitor import RiskMonitor
from matchmind.tools.registry import LiveStateRegistry, MatchTools


def load_match(data_dir: Path, match_id: str) -> tuple[list[dict], dict]:
    events = [json.loads(line) for line in (data_dir / f"{match_id}_events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = json.loads((data_dir / f"{match_id}_meta.json").read_text(encoding="utf-8"))
    return events, meta


def bench_situations(events: list[dict], meta: dict, registry: LiveStateRegistry, limit: int) -> list[dict]:
    """Replay the match through the Interpreter and the Risk Monitor; collect the Coach's triggers as the stream would."""
    state, monitor = MatchState(meta), RiskMonitor(meta)
    out: list[dict] = []
    for event in events:
        state.apply(event)
        snapshot = state.snapshot()
        for alert in monitor.observe(event, snapshot):
            if alert["level"] == "high":
                registry.update(meta["match_id"], meta, snapshot)
                out.append(build_coach_context({**alert, "other_windows": monitor.active_windows()}, snapshot, meta, trigger="risk_alert"))
        if event["type"] == "injury_concern":
            registry.update(meta["match_id"], meta, snapshot)
            out.append(build_coach_context({"player_id": event["player_id"], "name": event.get("player_name"), "clock": event.get("clock"),
                                            "detail": event.get("detail"), "other_windows": monitor.active_windows()},
                                           snapshot, meta, trigger="injury_concern"))
        if limit and len(out) >= limit:
            break
    registry.update(meta["match_id"], meta, state.snapshot())  # the tools read the latest state
    return out


def _reason(score) -> str | None:
    """The evaluator's rationale, when the provider returns one (Foundry puts it in the sample)."""
    sample = getattr(score, "sample", None) or {}
    for key in ("reason", "rationale", "explanation"):
        if isinstance(sample, dict) and sample.get(key):
            return str(sample[key])[:500]
    if isinstance(sample, dict):
        for v in sample.values():
            if isinstance(v, dict):
                for key in ("reason", "rationale", "explanation"):
                    if v.get(key):
                        return str(v[key])[:500]
    return None


def coach_prompt(context: dict) -> str:
    return "Bench situation (JSON):\n" + json.dumps(context, ensure_ascii=False) + "\n\nDecide the intervention now (or hold)."


async def run(args: argparse.Namespace) -> dict:
    from agent_framework import evaluate_agent
    from agent_framework_foundry import FoundryEvals

    from matchmind.agents.clients import build_coach, foundry_client, project_endpoint

    if not project_endpoint():
        print("FOUNDRY_PROJECT_ENDPOINT is required: the evaluation runs in the project", file=sys.stderr)
        sys.exit(2)
    data_dir = Path(args.data_dir)
    events, meta = load_match(data_dir, args.match)
    registry = LiveStateRegistry()
    tools = MatchTools(registry)
    situations = bench_situations(events, meta, registry, args.limit)
    if not situations:
        print("no bench situations in this match")
        sys.exit(2)
    coach = build_coach(tools).coach.agent
    queries = [coach_prompt(c) for c in situations]
    print(f"{args.match}: {len(queries)} bench situations; running the Coach and grading on the project")
    evals = FoundryEvals(client=foundry_client("fast"), evaluators=[FoundryEvals.TOOL_CALL_ACCURACY, FoundryEvals.TASK_ADHERENCE, FoundryEvals.INTENT_RESOLUTION],
                         timeout=900)
    t0 = time.perf_counter()
    results = await evaluate_agent(agent=coach, queries=queries, evaluators=evals, eval_name=f"matchmind-coach-{args.match}")
    report = {"match_id": args.match, "situations": len(queries), "seconds": round(time.perf_counter() - t0), "runs": []}
    for r in results:
        run_info = {"provider": r.provider, "status": getattr(r, "status", None), "passed": r.passed, "total": r.total,
                    "report_url": getattr(r, "report_url", None),
                    "items": [{"status": it.status,
                               "scores": {s.name: {"score": s.score, "passed": s.passed, "reason": _reason(s)} for s in (it.scores or [])},
                               "output": (it.output_text or "")[:400]}
                              for it in (r.items or [])]}
        report["runs"].append(run_info)
        print(f"  {r.provider}: {r.passed}/{r.total} passed  {run_info['report_url'] or ''}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Coach tool-use evaluation on the Foundry project")
    ap.add_argument("--match", default="THU-NBF-40")
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[3] / "data"))
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    report = asyncio.run(run(args))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        print("  written", out)


if __name__ == "__main__":
    main()
