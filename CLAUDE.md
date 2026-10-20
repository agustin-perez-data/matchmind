# MatchMind — project instructions

Hackathon project: "Inside the Game: Developer Hackathon" (Microsoft × Premier
League). Solo entry by Agustín Pérez. **Submission deadline: Oct 27, 2026,
11:59 PM PT — no extensions.**

## Context — read first

`docs/PLAN.md` is the single source of truth: product concept, agent lineup,
architecture, judging-rubric strategy, compliance checklist, day plan and
current status. Read it at the start of every session and keep its
"Current status" section updated as work progresses.

## Working rules

1. **Verify before declaring done.** Any Python change: run it (or at minimum
   `python -m py_compile`). Any frontend change: build must pass. Never say
   "listo" without having seen the check pass.
2. **No secrets in the repo, ever.** Azure keys/endpoints go in `.env`
   (gitignored). The repo goes PUBLIC at submission time — assume everything
   committed will be read by judges and the internet.
3. **Synthetic data only.** Never introduce real Premier League club names,
   player names, logos or data — not in code, docs, UI or the demo video
   (hackathon rules prohibit third-party trademarks).
4. **Language**: code, comments, docs, commit messages and UI in **English**
   (global judges). Chat with Agustín in Spanish (rioplatense).
5. **Simulator invariant**: player `fatigue` and `injury_susceptibility` are
   latent — never serialize them or expose them to agents. The Load & Risk
   Monitor must infer risk from observables only (load history, physical
   samples, injury_concern events).
6. **Scope discipline**: with the deadline this close, prefer finishing and
   polishing the pipeline end-to-end over adding features. Demo video < 2 min
   and the five brief stages (Ingest → Interpret → Explain → Render →
   Personalize) visibly working are the bar.
7. Azure work uses Agustín's **personal** account (free trial credits).
   Destructive or cost-incurring Azure operations: confirm before running.

## Quickstart

```bash
cd backend
python -m matchmind.generate_match --home THU --away NBF --seed 42 --out ../data
```
