"""Generate a synthetic match: library API + CLI.

Usage (CLI):
    python -m matchmind.generate_match --home THU --away NBF --seed 42 --out ../data

Usage (library):
    events, meta = generate("THU", "NBF", seed=42)
    write_match(events, meta, out_dir)
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


def generate(home: str = "THU", away: str = "NBF", seed: int = 42, league_seed: int = 7) -> tuple[list[dict], dict]:
    """Simulate one match. Returns (events, meta); meta carries no latent state."""
    league = build_league(league_seed)
    home_team, away_team = league[home], league[away]
    match_id = f"{home}-{away}-{seed}"
    result = MatchSimulator(home_team, away_team, seed=seed, match_id=match_id).run()
    events = result["events"]
    meta = {
        "match_id": match_id,
        "competition": "MatchMind Synthetic League",
        "disclaimer": "All clubs, players and events are fictional and synthetically generated.",
        "home_id": home_team.team_id,
        "away_id": away_team.team_id,
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
            for team in (home_team, away_team)
        },
        "summary": _summary(events, home_team.team_id, away_team.team_id),
        "n_events": len(events),
    }
    return events, meta


def write_match(events: list[dict], meta: dict, out_dir: Path | str) -> tuple[Path, Path]:
    """Write `<match_id>_events.jsonl` and `<match_id>_meta.json` into out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / f"{meta['match_id']}_events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    meta_path = out_dir / f"{meta['match_id']}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return events_path, meta_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic MatchMind match")
    parser.add_argument("--home", default="THU", choices=[c[0] for c in CLUBS])
    parser.add_argument("--away", default="NBF", choices=[c[0] for c in CLUBS])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--league-seed", type=int, default=7)
    parser.add_argument("--out", default="../data")
    args = parser.parse_args()

    events, meta = generate(args.home, args.away, args.seed, args.league_seed)
    events_path, _ = write_match(events, meta, args.out)

    home, away = meta["teams"][meta["home_id"]], meta["teams"][meta["away_id"]]
    print(f"{home['name']} {meta['score'][home['team_id']]} - {meta['score'][away['team_id']]} {away['name']}")
    print(f"events: {len(events)} -> {events_path}")
    for team in (home, away):
        st = meta["summary"][team["team_id"]]
        print(
            f"  {team['short_name']:<12} shots {st['shots']:>2}  xG {st['xg']:>5.2f}  "
            f"passes {st['passes']:>3} ({st['pass_accuracy']:.0%})  "
            f"possession {st['possession_pct']:.0f}%  pressures {st['pressures']}"
        )


if __name__ == "__main__":
    main()
