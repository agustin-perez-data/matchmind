"""CLI: generate a synthetic match and write its event stream to disk.

Usage:
    python -m matchmind.generate_match --home THU --away NBF --seed 42 --out ../data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from matchmind.sim.engine import MatchSimulator
from matchmind.sim.league import CLUBS, build_league


def _public_player(p) -> dict:
    """Serialize a player WITHOUT latent state (fatigue, susceptibility)."""
    return {
        "player_id": p.player_id,
        "name": p.name,
        "position": p.position,
        "shirt_number": p.shirt_number,
        "starter": p.on_pitch or p.minutes_played > 0,
        "load_history": p.load_history,
    }


def _summary(events: list[dict], home_id: str, away_id: str) -> dict:
    stats = {t: {"passes": 0, "completed": 0, "shots": 0, "xg": 0.0, "goals": 0,
                 "tackles": 0, "pressures": 0}
             for t in (home_id, away_id)}
    for e in events:
        t = e.get("team_id")
        if t not in stats:
            continue
        if e["type"] == "pass":
            stats[t]["passes"] += 1
            stats[t]["completed"] += e["outcome"] == "complete"
        elif e["type"] == "shot":
            stats[t]["shots"] += 1
            stats[t]["xg"] += e["xg"]
        elif e["type"] == "goal":
            stats[t]["goals"] += 1
        elif e["type"] == "tackle":
            stats[t]["tackles"] += 1
        elif e["type"] == "pressure":
            stats[t]["pressures"] += 1
    total_passes = sum(s["passes"] for s in stats.values()) or 1
    for s in stats.values():
        s["xg"] = round(s["xg"], 2)
        s["pass_accuracy"] = round(s["completed"] / s["passes"], 3) if s["passes"] else 0.0
        s["possession_pct"] = round(100 * s["passes"] / total_passes, 1)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic MatchMind match")
    parser.add_argument("--home", default="THU", choices=[c[0] for c in CLUBS])
    parser.add_argument("--away", default="NBF", choices=[c[0] for c in CLUBS])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--league-seed", type=int, default=7)
    parser.add_argument("--out", default="../data")
    args = parser.parse_args()

    league = build_league(args.league_seed)
    home, away = league[args.home], league[args.away]
    match_id = f"{args.home}-{args.away}-{args.seed}"
    sim = MatchSimulator(home, away, seed=args.seed, match_id=match_id)
    result = sim.run()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / f"{match_id}_events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        for event in result["events"]:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    meta = {
        "match_id": match_id,
        "competition": "MatchMind Synthetic League",
        "disclaimer": "All clubs, players and events are fictional and synthetically generated.",
        "score": result["score"],
        "teams": {
            team.team_id: {
                "team_id": team.team_id,
                "name": team.name,
                "short_name": team.short_name,
                "primary_color": team.primary_color,
                "style": team.style,
                "players": [_public_player(p) for p in team.players],
            }
            for team in (home, away)
        },
        "summary": _summary(result["events"], home.team_id, away.team_id),
        "n_events": len(result["events"]),
    }
    meta_path = out_dir / f"{match_id}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    s = meta["summary"]
    print(f"{home.name} {result['score'][home.team_id]} - {result['score'][away.team_id]} {away.name}")
    print(f"events: {len(result['events'])} -> {events_path}")
    for tid, name in ((home.team_id, home.short_name), (away.team_id, away.short_name)):
        st = s[tid]
        print(
            f"  {name:<12} shots {st['shots']:>2}  xG {st['xg']:>5.2f}  "
            f"passes {st['passes']:>3} ({st['pass_accuracy']:.0%})  "
            f"possession {st['possession_pct']:.0f}%  pressures {st['pressures']}"
        )


if __name__ == "__main__":
    main()
