# MatchMind — Hackathon Master Plan

> Working doc for "Inside the Game: Developer Hackathon" (Microsoft × Premier League).
> **SUBMISSION DEADLINE: Oct 27, 2026, 11:59 PM PT** (Oct 28 ~4 AM Argentina time).
> Solo entry: Agustín Pérez. This file is the single source of context — any new
> dev session (human or AI) should read it first.
>
> **Revised Oct 20 (after D3)**: the product story pivoted from "AI commentary"
> to "agents that make falsifiable predictions, get graded live, and let you
> rewrite the match". Sections 1-3 and 5 reflect the pivot; nothing built in
> D1-D3 is thrown away.

## 1. The product

**MatchMind — Agentic Match Intelligence Studio.**
*AI that gets graded, not just heard.*

A multi-agent engine that turns a live stream of synthetic football events into
explainable match intelligence, live narration and personalized viewing, AND:

- makes **falsifiable predictions** (injury-risk windows per player, short-term
  match forecasts) that are **scored live against ground truth**;
- lets viewers and coaches **rewrite the match**: an agent proposes an
  intervention (substitution, tactical change) and the engine re-simulates the
  match from that minute as a **counterfactual branch**, shown side by side.

Why this is defensible: our simulator has a *latent* player state (fatigue,
injury susceptibility) that no agent can see, and it is deterministic by seed.
That enables two things nobody with real or flat synthetic data can do:
measure whether the risk agent is right, and branch the match.

### Agent lineup (pipeline order)

1. **Simulator** (no LLM) — synthetic match engine with latent state and an
   intervention plan (forced substitutions / tactical changes from minute M). DONE v1; interventions D4.
2. **Interpreter agent** (no LLM) — stats: momentum, xG race, per-player live
   ACWR, risk bands. DONE.
3. **Load & Risk Monitor** (no LLM for the model, LLM for the explanation) —
   per-player **risk windows** ("high risk in the next 15 min") from observables
   only; **self-evaluating**: scored against the injury_concern events the
   latent state produces (precision, recall, lead time) vs a naive baseline. D4.
4. **Analyst agent** (gpt-4o) — why a key moment matters, grounded in numbers,
   plus a structured 10-minute forecast (dominant side, goal probability,
   player to watch). DONE.
4b. **Judge agent** (gpt-4.1-mini) — the forecast ledger closes each window on
   the minute mark, code scores every claim (xG dominance, Brier on the goal
   call, involvement of the watched player) next to a naive baseline, and the
   Judge writes verdict + lesson in the viewer's language → live Analyst
   credibility on the Analyst seat, the Control room and the MCP tool
   `get_analyst_credibility`. DONE (Oct 22).
5. **Coach agent** (gpt-4o) — proposes interventions when risk/momentum calls for
   it, via the MCP tool `simulate_intervention`; returns the counterfactual
   branch comparison (score, xG, alerts, concerns). D4.
6. **Narrator agent** (gpt-4.1-mini) — commentary per viewer profile, incl.
   "Relator Rioplatense" 🇦🇷. DONE.
7. **Director agent** (gpt-4.1-mini) — personalization: which cards reach each
   viewer and how loudly. DONE.

### Key design invariant

The simulator's player fatigue and injury susceptibility are **latent** —
never serialized, never visible to agents or the API. Ground truth for the
risk evaluation is the *observable* `injury_concern` event stream (which the
latent state generates). This keeps the prediction honest, not circular.

## 2. Architecture (target)

- **Azure AI Foundry**: `gpt-4o` (Analyst, Coach), `gpt-4.1-mini` (Narrator,
  Director, Judge). `gpt-4o-mini` cannot be deployed any more (deprecating).
- **Microsoft Agent Framework** (Python): `OpenAIChatCompletionClient` on
  Foundry, `as_agent`, structured outputs (Pydantic `response_format`),
  function tools for Analyst/Coach.
- **MCP server** (FastMCP, streamable HTTP at `/mcp`): match-state tools
  (`list_matches`, `get_match_state`, `get_player_workload`, `get_risk_alerts`,
  `get_xg_race`) + D4 `get_risk_windows`, `simulate_intervention`. Same
  functions are the agents' in-process tools (one registry, two surfaces).
- **Backend**: FastAPI + WebSocket replay (speed, hot profile switch, insights
  streamed as `insight` messages). Deploy: **Azure Container Apps**.
- **Frontend**: React + Vite + Tailwind. Agent feed, risk panel with live
  calibration, **what-if view with two timelines**, simple 2D SVG pitch, mode /
  language selector. Deploy: **Azure Static Web Apps**.
- Mention **GitHub Copilot** usage in the pitch (judges look for it).

## 3. Judging rubric strategy (5 × 20%)

| Criterion | How we win it |
|---|---|
| Tech implementation | Foundry + Agent Framework + MCP, 60+ tests, deterministic replay/branching, deployed on Azure |
| Agentic design | 7 agents with distinct roles; agents that *act* through MCP tools (simulate_intervention) and are *evaluated* (Risk Monitor scorecard, Judge) |
| Real-world impact | Player welfare (risk windows, honest evaluation) + coaching decisions (counterfactuals) + broadcast personalization |
| UX & presentation | Side-by-side counterfactual timelines; risk calibration panel; same match as two different experiences; crisp < 2 min video |
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

## 5. Day plan (revised Oct 20)

- **D1 (Oct 20) DONE**: decisions, scaffold, simulator v1 calibrated.
- **D2 (Oct 20) DONE**: Azure Foundry + deployments, FastAPI WebSocket
  streamer, Interpreter (momentum, xG race, ACWR).
- **D3 (Oct 20) DONE**: Analyst / Narrator / Director on Agent Framework,
  key-moment gate, MCP server, insights over WebSocket, `/live` dev viewer.
- **D4 (Oct 20-21) MOSTLY DONE** — *innovation core, backend*. Done on Oct 20:
  engine interventions, Risk Monitor + evaluator, `simulate_intervention` +
  `get_risk_windows` tools, Coach agent, WS `risk`/`risk_alert`/`coach`
  messages, branch REST endpoints (100 tests, live E2E OK). Left for Oct 21:
  finish weight calibration with `python -m matchmind.risk.evaluate --grid`,
  update `/live` viewer with risk + coach cards, README section, LLM
  explanation of alerts (optional). Original scope:
  1. Engine interventions: `MatchSimulator(..., interventions=[...])`
     (forced substitution at minute M; tactical change of press/style);
     deterministic branch = same seed, same events until M.
  2. Risk Monitor: hazard model from observables → risk windows per player;
     evaluator against `injury_concern` events (precision / recall / lead time)
     vs naive baseline; end-of-match scorecard; LLM explanation of each alert.
  3. MCP tools `get_risk_windows`, `simulate_intervention` (branch summary +
     diff vs actual); Coach agent proposing interventions on high-risk alerts.
  4. WebSocket messages: `risk` (windows + running scorecard), `coach`
     (proposal + counterfactual summary). Tests for all of it.
- **D5 (Oct 21) DONE a day early** — *frontend*: React + Vite + Tailwind in
  `frontend/`. Scoreboard, SVG pitch (recent passes/shots), xG race, momentum,
  agent feed (insight + coach cards), Risk Monitor panel with live scorecard
  vs baseline, what-if panel with the double timeline and a substitution form,
  URL params + autostart. Design tokens in `src/index.css`; palette validated
  with the dataviz validator; reviewed against frontend-design / Impeccable
  craft floor / Emil Kowalski checklists (desktop + 390px screenshots).
  **Oct 22 redesign (v2)**: Agustín found v1 generic. Ran a direction round
  (bench whiteboard / teletext / broadcast canon mockups in the scratchpad),
  he chose the broadcast studio done with commitment. Rebuilt the UI on that
  world: `ControlBar`, `TopBand` (team-colour wipes + white score), `Strip`
  (xG race + momentum), `PitchStage` (perspective pitch + lower third of the
  latest insight), `SidePanels` (stats / risk / coach blocks), `WhatIfBand`
  (double timeline + form), `MomentsRail`. Motion grammar in `index.css`
  (`@starting-style` transitions, no keyframe loops). Design notes in
  `frontend/README.md`. Third-party design skills installed project-scope
  under `.claude/skills/` (untracked; see its SOURCES.md).
  **Oct 22 v3 (seats + readable pitch)**: entry screen "pick your seat"
  (`SeatPicker`), `MatchStage` composes fan / analyst / bench layouts,
  `lib/seats.ts` maps seats to viewer profiles, URL is the state, live seat
  switching re-sends the profile over the open socket. Pitch: shot map + ball
  trail + possession chip; engine keeps the ball continuous inside a move
  (`_possession_chain` carries `y`; shots use the ball's `y`), test in
  `test_engine.py`. Data now holds two demo matches: THU-NBF-40 (1-2, 4 knocks,
  late goal; the default in the catalogue) and THU-NBF-42 (test fixture).
  **Oct 22, orchestration + Control room**: key moments now run through
  `agents/orchestration.py` (`FrameworkMomentPipeline`: Agent Framework
  `ConcurrentBuilder` fan-out Analyst + Narrator, Director fan-in; structured
  outputs via `default_options.response_format`; direct-call fallback;
  `MATCHMIND_ORCHESTRATION=gather` switches back). `agents/tracing.py`: agent +
  function middleware record runs, latency, tool calls (attributed via a
  contextvar) and tokens into a per-moment trace carried in `insight` /
  `coach` messages. Frontend: 4th seat "Control room" (`ControlRoom.tsx`):
  pipeline map lit by the latest message, per-moment swimlanes, Director
  decisions. Entry page carries the real-world impact line (bench warnings
  ~25' ahead, graded live). Verified live: Analyst calls tools on its own,
  fan-out ~2.4-4 s, Director ~0.8-1.3 s.
  **Oct 22, matchday + crests**: league redefined with indirect archetypes
  (colours/regions/styles only; no real names, nicknames or badge motifs):
  THU Thames United (red, white sleeves, North London), NBF Northbridge
  (royal blue, West London), IRA Ironfield Athletic (sky blue, Manchester,
  strongest), MRV Mersey Rovers (red, Merseyside, high press), CRC Crowmoor
  Town (navy/white halves, North London), ALV Albion Vale (claret/sky
  sleeves, Midlands), TGW Tynegate Wanderers (black/white stripes, North
  East), KPF Kestrel Park (gold/black, Black Country). Team meta carries
  `secondary_color`, `pattern`, `city`; `/matches` returns `home_team` /
  `away_team` for crests (`Crest.tsx`, geometric shield + initials; light
  colours get dark text via `onColor`). Data = Matchday 9: THU-NBF-40 (1-2,
  headline), IRA-MRV-21 (2-2), CRC-ALV-47 (3-2), TGW-KPF-46 (2-1, 6 knocks).
  THU-NBF-42 stays only as the in-memory test fixture.
  **Oct 22, language + desk**: the Analyst (and so the Director's headline)
  now follows the viewer's language — `analyst_prompt(context, language)`
  carries it in both the direct and the Agent Framework fan-out paths
  (verified live: Spanish fan seat gets a Spanish Analyst). The entry page
  asks for the language ("The agents speak": English first and by default,
  then rioplatense Spanish) between the fixture
  and the seats, so the first key moment already arrives in the chosen
  language. The top bar is now a production desk: brand, seat tabs filled
  in the seat colour, then speed (− / + over the preset ladder), ES/EN
  segmented, Agents/Coach switches, Follow (fan seat only), status, Stop.
  The fixture select left the bar: a fixture is chosen on the entry page.
  Analyst headlines are normalised to one full stop (`sentence()`).
  **Oct 22, desk trimmed + Follow block**: once seated the language cannot
  change (it is a decision taken on the entry page); the Agents / Coach
  switches left the UI — they were dev controls (replay without LLM calls)
  and now live only as URL params `agents=0&coach=0`. "Follow a player" is
  a proper block on the fan seat (`FollowBlock.tsx`): starters and anyone on
  the pitch as chips per team, the followed one in amber with live sprints /
  distance / top speed and the Director's personalised note; clicking a chip
  re-sends the profile as `player_focus` over the open socket.
  **Oct 22, commentary language + stadium sound**: decided (option 2) that
  the UI stays in English and the language is presented as the commentary
  language ("Commentary language" on the entry page, a fixed EN/ES indicator
  on the desk). Full UI i18n only if time remains after deploy and video.
  Stadium sound (`lib/sounds.ts`, Web Audio synthesis, no samples or
  licences): short pea whistle on kick-off / half-time / second-half
  kick-off, a crowd roar on goals (32 detuned sawtooth voices with shout
  contour and vibrato through "ah" formant filters + a pink-noise bed), a
  long whistle at full time; limiter on the master bus; on/off switch on the
  desk, remembered in localStorage; audio is unlocked by the seat click.
  Evaluated by capturing the output bus from headless Edge
  (`scratchpad/capture_audio.py` + `analyze_audio.py`) and comparing with a
  reference goal-cheer recording Agustín supplied (decoded with the browser,
  `decode_mp3.py`; NOT shipped: ringtone-site file of unknown licence). The
  roar was reshaped to match it: 0.4 s of expectation, crescendo to the peak
  at ~1 s, ~2 s sustain, fade by 4.3 s; highpass 480 Hz with shouting
  formants at 820/1150/1550 Hz (centroid ≈ 1120 Hz vs 1116 reference, band
  shares within a few points), clap bursts plus a slow "surge" modulation
  for texture (10 ms envelope roughness 0.25-0.28 vs 0.28 reference), peak
  ≈ 0.8, no clipping. Whistles rms ≈ 0.12-0.15. Capture on the entry page:
  during a replay the match whistles contaminate the measurement.
  **Oct 22, pillar 3 (Analyst forecast + Judge)**: `agents/judge.py` holds
  the `ForecastLedger` (pending forecasts, settling-event history sliced by
  event_id, per-minute state marks so windows close exactly on the due
  minute even when insights arrive late at replay speed), `grade_forecast`
  (deterministic: dominance 1/0 by xG gained, goal = 1 − Brier, watch 1/0 by
  involvement; unsettleable claims are left out of the mean), the naive
  baseline, `JudgeAgent`/`JudgePipeline` (fast tier, structured
  `JudgeVerdict`; code verdict thresholds as fallback). Stream: moments lane
  runner feeds the ledger; `_grade_due` runs on every non-physical event and
  at full time (flush); verdicts go out on a `verdict` lane with capacity 8
  so none is dropped; `end` carries the credibility summary; the registry
  exposes it as `get_analyst_credibility`. No forecast is taken at full
  time. Live run (THU-NBF-40, speed 150): 6 forecasts graded, Analyst
  0.57 vs naive 0.52 overall — the home/possession bias of the Analyst's
  dominance calls is visible (0.5 vs 0.33 on dominance, 0.4 on watched
  players), which is the point: a credibility that is earned. Frontend:
  `ForecastLedger.tsx` on the Analyst seat (full) and Control room
  (compact), forecast line in the analyst lower third, Judge row + stats in
  the Control room pipeline map. 126 backend tests.
  **Oct 22, raising the credibility (measured)**: harness
  `agents/evaluate_forecasts.py` (real Analyst, same seeds, match-order loop
  with the Judge, ablation flags `--no-loop` / `--no-judge`, prompt variants
  via `--instructions`). Baseline on seeds 5000-5009 (66 forecasts): Analyst
  0.60 vs naive 0.62; it picked the possession leader 80 % of the time, P(goal)
  stuck at 0.30, named a player 91 % and hit 27 %. League base rate measured:
  2.1 goals/match, P(goal in 10') = 0.20 (constant fixed). Naive now also
  names the top shooter so far, so both make three claims. Levers:
  Interpreter keeps per-minute marks → `snapshot["recent"]` (last-10-minute
  xG/shots/pressures/passes per team + shooters) and `top_shooters`;
  `game_state` (leading/trailing, minutes left); `analyst_track_record`
  (ledger summary + last 3 verdicts with the Judge's lessons) injected into
  the moment context (the verdict lane writes the Judge's words back into the
  ledger); instructions rewritten (dominance = xG, default to the xG leader
  unless the last 10 minutes clearly say otherwise, goal odds tied to recent
  shots, watch = recent/top shooters). Results on the same matches: v2
  window only 0.61 / with loop 0.64 / v3 with the xG-default rule 0.66 vs
  naive 0.64 (dominance 0.64, watch 0.41). Table in the README. Live stream
  verified after the change (7 insights, 6 verdicts).
  **Oct 22, demo robustness (list item 2)**: `agents/cache.py` AgentCache
  (memory + write-through JSON per match under `<data>/cache`, keys
  insight `event_id:profile.key`, coach `trigger:player:minute`, verdict
  `event_id:lang`; degraded results never cached; `cached: true` on served
  messages; `MATCHMIND_CACHE=0` disables, `MATCHMIND_CACHE_DIR` relocates);
  cached verdicts keep the session's own scores/credibility, only the words
  are shared. `LiveStateRegistry` is session-aware through the
  `current_session` contextvar set at the top of `StreamSession.run` (the
  lanes inherit it): each stream's tools read that stream's minute, outsiders
  (MCP/REST) read the latest view; sessions are dropped on disconnect.
  `/health` reports cache stats and live sessions. `agents/warm_cache.py`
  drives the live server over WebSocket per (match, profile). Measured:
  THU-NBF-40 fan/es warm run 131 s (14 insights, 7 coach, 13 verdicts),
  replay at max speed 15 s with 20 cache hits. Control room shows "from
  cache". 142 tests.
  **Oct 22, "same moment, two viewers" (list item 3)**: a stream can carry
  extra compared profiles (`?compare=mode:lang[:player]`, control message
  `{"compare": [...]}`, echoed in `meta`/`ack`); `FrameworkMomentPipeline`
  keeps one fan-out for the seat's own profile and adds, per extra viewer, a
  Narrator line and a Director decision in parallel (trace stage "extra
  viewers"; orchestration label says "+N compared viewer(s)"); cache key
  joins all profile keys. The Control room seat sends its own commentator
  profile plus `analyst:<lang>` and renders `TwoViewers.tsx`: per viewer the
  Director headline, the four cards shown/struck through, priority, the
  Narrator line and any personal note. Verified live on IRA-MRV-21.
  **Oct 22, five stages labelled (item 4) + reliability and bench report
  (item 5)**: the Control room pipeline map carries stage bands (Ingest,
  Interpret, Explain, Personalize, Render); README table updated.
  `risk/evaluate.py --calibration --out eval/risk_calibration.json` bins
  windows by opening hazard vs observed knock rate (40 matches, 604 windows:
  0 % below 0.8, 1.5 % at 0.8-0.9, 27 % above 0.9; overall 8 %); the hazard
  is presented as a ranking score, not a probability. A copy ships in
  `frontend/src/data/` and `ReliabilityBlock.tsx` draws it on the bench seat
  with this match's windows as amber bars. `BenchReport.tsx` appears at full
  time on the bench seat: knocks with warning times, Coach proposals with
  branch outcomes, Analyst credibility, Download JSON.
  **Oct 22, groundedness (item 6)**: `agents/evaluate_groundedness.py`
  rebuilds each cached moment's context by replaying the match and scores
  the Analyst read and the Narrator line with `GroundednessEvaluator` from
  `azure-ai-evaluation` (installed from `requirements-eval.txt`, kept out of
  the service image; config `AzureOpenAIModelConfiguration` on the fast
  deployment). THU-NBF-40, fan/es, 28 items: Analyst 4.86, Narrator 5.0.
  `--run analyst:en` fills the cache first for uncached moments. Also fixed a
  flaky API test (control acks could land after "end" at max speed).
  **Oct 22, mobile pass (item 7 of the list, last before deploy)**: screens
  checked at 390 px for the entry page and the four seats. Fixes: the top
  band shows team codes (THU / NBF) below `sm`, short names up to `md`, full
  names above; the score block is narrower on phones; the Control room's
  pipeline map is replaced below `sm` by a five-row stage list; the
  possession chip no longer says "Waiting for kick off" mid-match (a pressure
  event by the other side now falls back to the ball's own tag, and the
  placeholder only shows before kick-off).
  **Feature list agreed Oct 22 (time is not the constraint)**: 1 forecast +
  Judge (done) · 2 demo robustness (insight cache per moment+profile,
  per-viewer registry sessions) · 3 "same moment, two viewers" in the
  Control room · 4 the five brief stages labelled in UI + README · 5 Risk
  Monitor reliability diagram + post-match bench report · 6 groundedness
  evaluation with the Azure AI evaluation SDK · 7 mobile pass · 8 deploy
  (Key Vault + managed identity + Application Insights), then video, pitch,
  submit.
  Deploy plan agreed in principle, NOT yet authorised: ACR Basic + Container
  Apps scale-to-zero (min 1 replica only before submission) + Static Web Apps
  Free, ~USD 20 total through Nov 10.
- **D6 bis (Oct 24-25)**: deploy (Container Apps + Static Web Apps), README
  with architecture diagram, Analyst forecast + Judge credibility if time.
- **D7 (Oct 26)**: demo video (scripted), pitch text, SUBMIT with buffer.

Scope rules: protect pillars 1-2 (evaluable Risk Monitor, counterfactuals)
over eye candy. The pitch is simple SVG, not an animation showcase. The
evaluation is shown honestly even if the numbers are modest — a baseline next
to it makes the point.

## 6. Current status / handoff notes

- **Ground-truth injury model (Oct 21)**: `engine._maybe_injury_concern` is
  now convex in fatigue + congestion spike (pre-match ACWR > 1.3) x latent
  susceptibility 0.5-1.0, drawn from a separate RNG stream (`_flavour_rng`
  for descriptions too) so the match flow never depends on it (test in
  `test_engine.py`). Risk windows open only for the top-5 hazards on the pitch
  (`TOP_N_WINDOWS`), same policy for the baseline. Evaluation over 40 matches:
  top-3 0.32 vs baseline 0.16 vs random 0.14; recall 0.46 vs 0.26; lead 25'
  vs 18'; 14 alerts/match. Weights still default (grid showed the rank metric
  is flat across weights; the policy mattered more than the weights). The
  canonical demo match is now THU-NBF-40 (see v3 note).
- **D4 backend (Oct 20)**: `sim/engine.py` takes `interventions=[...]`
  (substitution / tactic at minute M; status applied|skipped; same seed =
  identical events until M). `generate(..., interventions, match_id)`; meta now
  has `seed`, `league_seed`, `interventions`, and `starter` means the real
  starting XI. `risk/monitor.py`: `RiskModel` (logistic over ACWR, minutes,
  sprint density, previous knocks, metres-per-minute drop vs position norm),
  `NaiveMinutesBaseline`, `Track` (windows + scoring: precision/recall/lead and
  top-3 ranking vs random), `RiskMonitor`. `risk/evaluate.py` CLI (40 matches:
  model recall 0.60 vs baseline 0.51, rank% 41 vs 48, top-3 0.17 vs random
  0.14 — modest, honest; weights still to be tuned with `--grid`). Interpreter
  player view gained `effort_ratio` / `effort_ratio_recent`. `tools/registry.py`:
  `simulate_intervention` (deterministic branch, cached by intervention hash,
  summary actual vs branch + diff + player_off), `get_risk_windows`, branch
  storage. `agents/coach.py`: `CoachProposal`, `build_coach_context`,
  `CoachAgent`, `CoachPipeline` (propose → simulate). API: `GET/POST
  /matches/{id}/branches`, `GET .../branches/{branch_id}`; WS lanes `_Lane`
  (moments → insight, risk → coach), params `coach=0/1`. Measured live: Coach
  ~2 s per proposal, branch simulation < 100 ms.

- **Streamer + Interpreter done (D2)**: `backend/matchmind/api/app.py`
  (REST catalogue + `WS /ws/matches/{id}?speed=N`, hot speed change via
  `{"speed": N}`), `backend/matchmind/stream/replay.py` (clock-gap scheduling),
  `backend/matchmind/interpreter/state.py` (team stats, xG race, momentum,
  per-player ACWR + risk bands, `risk_alerts`). Message protocol documented in
  the app module docstring. Tests: `cd backend && .venv/Scripts/python -m pytest`.
- **Agents + MCP done (D3)**: `backend/matchmind/agents/` — `moments.py`
  (deterministic key-moment gate + compact LLM context), `analyst.py` /
  `narrator.py` / `director.py` (prompts + Pydantic structured outputs in
  `schemas.py`), `pipeline.py` (Analyst ∥ Narrators → Directors, failure-isolated),
  `clients.py` (Agent Framework `OpenAIChatCompletionClient` on Foundry; Analyst
  gets the match-state tools as function tools), `demo.py` CLI. `backend/matchmind/tools/`
  — `registry.py` (`LiveStateRegistry` + `MatchTools`, observables only) and
  `mcp_server.py` (FastMCP, streamable HTTP at `/mcp`, DNS-rebinding check off
  because it is a public hosted endpoint). WS params: `mode`, `lang`, `player`,
  `agents`, `min_importance`; messages `insight` / `insight_error`; one moment in
  flight per connection, more important moment wins. Measured: ~3-6 s per moment
  (Analyst gpt-4o + 2 fast calls per viewer). Live check: `MATCHMIND_LIVE=1 pytest
  tests/test_live.py` and `python -m matchmind.agents.demo --mode commentator:es`.
  `/live` serves a no-build dev viewer (events + insights).
- Known limitation: the registry keeps ONE live snapshot per match (last writer
  wins across concurrent viewers); fine for the demo, note it in the README.
- Simulator fixes: `second_half_kickoff` stamped 45:00 (D2); a shooter is never
  credited with their own assist (D3). Minutes restart at 45 for period 2, so
  consumers must order by `(period, minute)`.
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
  already created (tag: Injury Risk Prediction — now the core of the pitch).
- Known issue: Innovation Studio login from a fresh machine throws
  AADSTS500200 (personal MSA via /organizations endpoint). Fix: redeem the
  original invitation email or pick "Work or school account" identity at the
  account picker. Does NOT block development — only needed for submission.
