# MatchMind — project instructions

Hackathon project: "Inside the Game: Developer Hackathon" (Microsoft × Premier
League). Solo entry by Agustín Pérez. **Submission deadline: Oct 27, 2026,
11:59 PM Pacific — the end of that day, not its start.** The event page states
the hacking period as Oct 6 to Oct 27, 2026, 11:59 PM Pacific; registration
closed Oct 20. In Buenos Aires that cutoff is **04:59 on Oct 28** (Pacific is
UTC-7 in October, Argentina UTC-3). Judging runs to Nov 10, and the deployed
project has to stay reachable until then.

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
3. **Positions are a model, not tracking.** The 22-player frames come from
   `sim/tracking.py`, a positional model built on the event stream. Label them
   "positional model" in UI, docs and tool descriptions; never "tracking data"
   without that caveat. Frames are a side channel (`kind: "frame"`), never
   events: event ids, caches and the risk evaluation must not depend on them.
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
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env   # then fill in the Foundry endpoint/key (never commit)

# generate a synthetic match (writes ../data/<id>_events.jsonl + _meta.json)
.venv/Scripts/python -m matchmind.generate_match --home THU --away NBF --seed 42 --out ../data

# run the test suite (simulator, replay, interpreter, API)
.venv/Scripts/python -m pytest

# run the service (generates the default match on first start if ../data is empty;
# LLM agents switch on automatically when backend/.env has the Foundry credentials)
.venv/Scripts/python -m uvicorn matchmind.api.app:app --reload --port 8000
# REST: GET /matches, GET /matches/{id}/meta | WS: /ws/matches/{id}?speed=10&mode=casual&lang=es | MCP: POST /mcp

# LLM agents on a recorded match (real Foundry calls, costs tokens)
.venv/Scripts/python -m matchmind.agents.demo --limit 3 --mode analyst --mode commentator:es
# opt-in live test (real Foundry call)
MATCHMIND_LIVE=1 .venv/Scripts/python -m pytest tests/test_live.py

# Warm the agent cache through the running server before a demo (all matches, the four seat profiles)
.venv/Scripts/python -m matchmind.agents.warm_cache

# Groundedness of what the agents said in a match (Azure AI Evaluation SDK; pip install -r requirements-eval.txt once)
.venv/Scripts/python -m matchmind.agents.evaluate_groundedness --match THU-NBF-40 --out eval/groundedness_THU-NBF-40.json

# Grade the real Analyst's 10-minute forecasts over simulated matches (costs Foundry tokens; ~1 min per 10 matches)
.venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10 --label baseline --out eval/forecasts_baseline.json
# A/B a prompt variant on the same matches:
.venv/Scripts/python -m matchmind.agents.evaluate_forecasts --matches 10 --instructions prompts/analyst_v2.txt --label v2 --out eval/forecasts_v2.json
# Risk Monitor offline evaluation (no LLM): model vs naive baseline over N simulated matches
.venv/Scripts/python -m matchmind.risk.evaluate --matches 40

# Lint (the same commands CI runs; config in backend/pyproject.toml and the frontend's oxlint defaults)
.venv/Scripts/python -m ruff check matchmind tests ../infra        # --fix applies the safe ones
.venv/Scripts/python -m pyright                                     # basic mode, config in pyproject.toml
cd ../frontend && npm run lint
# Foundry project evaluations (keyless through the project; needs `az login` + Foundry User on the project)
FOUNDRY_PROJECT_ENDPOINT=https://matchmind-foundry.services.ai.azure.com/api/projects/matchmind   .venv/Scripts/python -m matchmind.agents.evaluate_groundedness --foundry --limit 8      # also on the project's grader
FOUNDRY_PROJECT_ENDPOINT=... .venv/Scripts/python -m matchmind.agents.evaluate_coach --limit 6  # Coach tool use, graded
FOUNDRY_PROJECT_ENDPOINT=... ../backend/.venv/Scripts/python ../infra/register_judge.py           # hosted Judge from the same code
# Deployed API checks
MATCHMIND_API_URL=https://<fqdn> .venv/Scripts/python ../infra/smoke.py
.venv/Scripts/python -m loadtest.stream_load --api https://<fqdn> --viewers 25 --speed 300
```

Tests never call Foundry: `create_app(..., enable_agents=False)` or inject a
fake pipeline. Keep it that way — `backend/.env` exists on dev machines.

## Azure deployment (see `infra/README.md` for purposes, SLOs, runbook)

- Infrastructure is code: `infra/acr.bicep`, `infra/main.bicep` (idempotent; `bootstrap=true` deploys a
  placeholder image the first time), `infra/deploy.ps1` (one-time bootstrap: providers, ACR, platform,
  data upload, GitHub secrets), `.github/workflows/deploy.yml` (every push to `main`: OIDC login, image
  build to ACR, Bicep, warm job, frontend to Static Web Apps, agent registration, smoke test).
- The deployed API runs keyless: `FOUNDRY_PROJECT_ENDPOINT` + the user-assigned identity
  (`AZURE_CLIENT_ID`). Locally `backend/.env` keeps the key fallback. `/health` reports `auth`, `project`,
  `telemetry`, `ready`, `draining`, `replica`.
- Replays are per-process: sticky sessions, max 2 replicas, and the stream resumes with `?from=<event_id>`
  (the client reconnects by itself). The agent cache lives on the Azure Files share and merges on a miss.
- Optional runtime switches: `MATCHMIND_JUDGE=foundry` (hosted Judge agent), `MATCHMIND_GUARDRAILS=1`
  (Content Safety groundedness on every uncached moment), `MATCHMIND_EVENTGRID_ENDPOINT` (domain events),
  `MATCHMIND_STORAGE_ACCOUNT` (jobs). All off locally by default.
- Subscription gotchas: ACR Tasks (`az acr build`) is not permitted (the pipeline builds); a
  workload-profile Container Apps environment sat in "Waiting" for an hour (use the Consumption-only one);
  the environment quota is 1 per region; Git Bash needs `MSYS_NO_PATHCONV=1` for `/subscriptions/...` scopes.
- Never commit `backend/.env`, `.azure/`, or any key; the Speech key lives in Key Vault only.

On Windows the `.venv/Scripts/python` prefix matters: the global `python` has
none of the project dependencies installed.
