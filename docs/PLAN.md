# MatchMind — Hackathon Master Plan

> Working doc for "Inside the Game: Developer Hackathon" (Microsoft × Premier League).
> **SUBMISSION DEADLINE: Oct 27, 2026, 11:59 PM PT** (Oct 28 ~4 AM Argentina time).
> Solo entry: Agustín Pérez. This file is the single source of context — any new
> dev session (human or AI) should read it first.

## 1. The product

**MatchMind — Agentic Match Intelligence Studio.** A multi-agent AI engine that
turns a live stream of synthetic football events into explainable match
intelligence, real-time narration and personalized viewing experiences, plus a
sports-science-grounded **Player Load & Risk Monitor**.

### Agent lineup (pipeline order)

1. **Simulator** (no LLM) — synthetic match engine. DONE (v1, calibrated).
2. **Interpreter agent** — aggregates events into stats: momentum, xG race,
   pass networks, pressure maps, live ACWR per player.
3. **Analyst agent** — detects key moments and explains WHY they matter
   (control vs chaos, tactical shifts, rhythm changes).
4. **Narrator agent** — multi-language live commentary + auto match recaps.
   Modes include English analytical and "Relator Rioplatense" 🇦🇷.
5. **Director agent** — personalization: decides what reaches each viewer
   (Analyst / Casual / Commentator / Player-Focus modes, favorite player,
   language).
6. **Load & Risk Monitor** — flags injury-risk workload patterns via ACWR
   (acute:chronic workload ratio) using ONLY observable metrics.
   Framing: decision support, NOT medical advice (Responsible AI note).

### Key design invariant

The simulator's player fatigue and injury susceptibility are **latent** —
never serialized. The Risk Monitor must infer risk from observables
(28-day load history, live distance/sprints/speed samples, injury_concern
events). This keeps the prediction honest, not circular.

## 2. Architecture (target)

- **Azure AI Foundry**: model hosting — `gpt-4.1-mini` (high-volume agents;
  `gpt-4o-mini` is blocked for new deployments since Oct 2026) and `gpt-4o`
  (Analyst). Use Foundry evals/tracing if time allows.
- **Microsoft Agent Framework** (Python) for multi-agent orchestration.
- **Custom MCP server** exposing match-state tools to agents (match stats,
  player workload, score state) — scores points in Agentic Design.
- **Backend**: Python + FastAPI + WebSocket streamer replaying event JSONL in
  real time. Deploy: **Azure Container Apps**.
- **Frontend**: React + Vite + Tailwind. Animated 2D SVG pitch, broadcast-style
  overlay cards, mode/language selector, player-focus view, risk panel.
  Deploy: **Azure Static Web Apps**.
- Mention **GitHub Copilot** usage in the pitch (judges look for it).

## 3. Judging rubric strategy (5 × 20%)

| Criterion | How we win it |
|---|---|
| Tech implementation | Real Foundry + Agent Framework usage, clean documented code, deployed to Azure |
| Agentic design | 5 genuine agents + MCP tools + orchestration, not a single prompt |
| Real-world impact | Studio/broadcast framing + player welfare (injury risk) angle |
| UX & presentation | Broadcast-quality UI; same match shown as 2 different experiences; crisp <2min video |
| Category adherence | All 5 brief stages visible: Ingest → Interpret → Explain → Render → Personalize |

Category prizes to aim for: Best Multi-Agent System, Best Use of Microsoft
Foundry, Best Azure Cloud Native Integration.

## 4. Compliance checklist (hard rules)

- [x] Synthetic data only — own simulator, fictional clubs/players
- [x] MIT license, public GitHub repo at submission time
- [ ] NO secrets in repo ever (.env/.azure gitignored; use env vars + Key Vault)
- [ ] Demo video < 2 min, no copyrighted music, no third-party trademarks
      (no real PL club names/logos anywhere, including the video)
- [ ] Video on YouTube/Vimeo public URL
- [ ] Project pitch text: what it does, problem solved, MSFT tech used
- [ ] Working demo URL for judges (free access through Nov 10)
- [ ] Submit on Innovation Studio BEFORE Oct 27 11:59 PM PT (buffer: Oct 26)

## 5. Day plan

- **D1 (Oct 20) DONE**: decisions, scaffold, simulator v1 calibrated
  (~900 passes @82-88%, 24-33 shots, 1-4 goals, possession 39-61%).
- **D2 (Oct 21) DONE**: machine migration, Azure Foundry setup + model
  deployments, FastAPI WebSocket streamer (replay JSONL at real/accelerated
  speed), Interpreter agent (pure Python stats + ACWR). 29 tests green.
- **D3 (Oct 22)**: Agent Framework + Foundry: Analyst, Narrator, Director
  agents; MCP server with match-state tools.
- **D4 (Oct 23)**: Risk Monitor agent + end-to-end pipeline wiring.
- **D5 (Oct 24)**: React frontend (pitch, overlays, modes, risk panel).
- **D6 (Oct 25)**: Azure deploy (Container Apps + Static Web Apps), README
  polish, architecture diagram.
- **D7 (Oct 26)**: demo video (scripted), pitch text, SUBMIT with buffer.

## 6. Current status / handoff notes

- Simulator v1 done and verified on this repo (`backend/matchmind/sim/`).
  CLI: `python -m matchmind.generate_match --home THU --away NBF --seed 42 --out ../data`
- **Streamer + Interpreter done (D2)**: `backend/matchmind/api/app.py`
  (REST catalogue + `WS /ws/matches/{id}?speed=N`, hot speed change via
  `{"speed": N}`), `backend/matchmind/stream/replay.py` (clock-gap scheduling),
  `backend/matchmind/interpreter/state.py` (team stats, xG race, momentum,
  per-player ACWR + risk bands, `risk_alerts`). Message protocol documented in
  the app module docstring. Tests: `cd backend && .venv/Scripts/python -m pytest`.
- Simulator fix (D2): `second_half_kickoff` now stamped 45:00 (was carrying the
  first-half stoppage clock). Minutes restart at 45 for period 2, so consumers
  must order by `(period, minute)`.
- **Azure provisioned (D2, personal subscription "Azure subscription 1")**:
  resource group `rg-matchmind` (eastus2), Azure AI Foundry resource
  `matchmind-foundry` (kind AIServices, SKU S0), deployments `gpt-4o`
  (2024-11-20, Standard, 30K TPM) and `gpt-4.1-mini` (2025-04-14,
  GlobalStandard, 100K TPM). Both smoke-tested. Endpoint/key live in
  `backend/.env` (gitignored; template in `backend/.env.example`).
  Quota lesson: the free trial has 0 GlobalStandard quota for gpt-4o and
  gpt-4o-mini (2024-07-18) is "Deprecating" and cannot be deployed at all.
  NOTE: keep hackathon Azure fully separate from any work credentials; on
  shared machines use `AZURE_CONFIG_DIR` isolation.
- Known tuning note: goal conversion runs slightly below cumulative xG;
  revisit if time allows (Interpreter already reports both).
- Innovation Studio page: registration + project "Premier league project"
  already created (tag: Injury Risk Prediction).
- Known issue: Innovation Studio login from a fresh machine throws
  AADSTS500200 (personal MSA via /organizations endpoint). Fix: redeem the
  original invitation email or pick "Work or school account" identity at the
  account picker. Does NOT block development — only needed for submission.
