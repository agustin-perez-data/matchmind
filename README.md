# MatchMind: match intelligence that gets graded, not just heard

**Inside the Game: Developer Hackathon (Microsoft × Premier League) submission.**

MatchMind replays a football match as a live broadcast in which AI agents explain it, narrate it, personalise
it and predict it, and every prediction is scored against what actually happens. A Load & Risk Monitor warns
which player is about to get hurt from workload alone; a Coach proposes a change and the engine shows the
match that would have followed.

- **Live:** https://lively-mushroom-0cde96c0f.5.azurestaticapps.net (one click opens the derby; a match
  replays in about 90 seconds)
- **API:** https://matchmind-api.mangopond-a8309942.eastus2.azurecontainerapps.io (`/health`, `/docs`, `/mcp`)
- **Demo video:** https://www.youtube.com/watch?v=MqtQjgP2ZOk (under 2 minutes)

> **Synthetic data only.** Every club, player, event and number comes from our own simulator. The eight clubs
> of the MatchMind Synthetic League echo the archetypes of English football, but their names, kits and crests
> are invented; no real competition, club, person or trademark appears anywhere.

## What it does

Four seats on the same match:

| Seat | What you get |
|---|---|
| Fan | A commentator in your language (English or rioplatense Spanish, voiced), the pitch with the 22 players, a player to follow, and a side to support |
| Analyst | Why the match is going the way it goes: momentum, block height, xG race, team shape, pass networks, and the Analyst's forecasts with its running credibility against a naive baseline |
| Bench | A readiness board of the XI ranked by injury hazard, risk windows over time, the Coach's proposals with the re-simulated outcome, and a what-if you can try yourself |
| Control room | The agents at work: every key moment as a swimlane, tool calls, tokens, cache hits, the Director's decisions and the fact check on each line |

The brief's five stages are each a component, and the Control room's pipeline map draws them:

| Stage | Component |
|---|---|
| Ingest | Synthetic match engine, a positional model that places the 22 players every second, and a WebSocket replay at any speed |
| Interpret | Interpreter (pure Python): team stats, xG race, momentum, per-player ACWR workload, team shape, heat maps, pressure on the ball |
| Explain | Analyst (gpt-4o): why a moment matters, grounded in the Interpreter's numbers, plus a ten-minute forecast the Judge grades |
| Render | Narrator (gpt-4.1-mini) in four styles and two languages, and the broadcast UI |
| Personalize | Director (gpt-4.1-mini): which cards each viewer sees and how loudly, under house rules enforced in code |

## AI that gets graded, not just heard

**The Risk Monitor is scored against ground truth.** It predicts injury-risk windows from observable workload
only (live ACWR, minutes, sprint density, previous knocks, pace drop against the position norm). The
simulator's hidden fatigue produces observable knocks, so every prediction is checked. A minutes-played rule
runs alongside with the same window policy. Over 40 simulated matches (`python -m matchmind.risk.evaluate
--matches 40`):

| | Risk Monitor | Minutes-only rule | Random pick |
|---|---|---|---|
| Knock happened to a top-3 hazard player | 27 % | 8 % | 14 % |
| Knocks covered by an open window | 53 % | 15 % | |
| Mean warning time | 27 min | 18 min | |
| Windows that came true | 8 % | 5 % | |

It ranks risk twice as well as chance and far better than a minutes rule, and most windows still pass without a
knock; that is what the scorecard is for.

**Does it only learn our own formula?** The knock model is ours, so the fair question is whether the monitor
just reverse-engineered it. To check, the same unchanged monitor was run against five other worlds, each with a
different rule for who gets hurt (`python -m matchmind.risk.evaluate --truth-sweep --matches 40`):

| World (who gets hurt) | Top-3 hit | Random | Minutes rule | Warning |
|---|---|---|---|---|
| Published: convex fatigue, workload spike above ACWR 1.3 | 27 % | 14 % | 8 % | 27 min |
| The spike starts at ACWR 1.5, not where the monitor assumes | 25 % | 14 % | 9 % | 27 min |
| Fatigue hurts linearly, not convexly | 21 % | 14 % | 10 % | 27 min |
| Workload history plays no part, only in-match fatigue | 25 % | 14 % | 9 % | 27 min |
| Only the pre-match workload spike, no fatigue | 60 % | 14 % | 14 % | 26 min |
| Individual susceptibility dominates | 29 % | 14 % | 10 % | 28 min |

It beats chance in every world, by 1.6x to 4.4x, including the ones built to break its assumptions. That does not
make it a real-world model, but it is evidence that it finds signal in workload rather than in our formula. The hazard is a ranking, not a probability: windows opened above 0.9 saw a knock
27 % of the time, those below 0.8 almost never (`--calibration`), and the bench seat shows that curve.

**The Analyst is graded too.** Every read ends with a forecast for the next ten minutes (which side creates
more xG, the probability of a goal, the player most likely to be involved). Code settles each claim when the
window closes, the Judge writes the verdict and the lesson, and a naive forecast making the same three claims
is graded on the same windows. Over 10 matches, about 66 forecasts (`python -m
matchmind.agents.evaluate_forecasts --matches 10`):

| Analyst version | Overall | Who dominates | Goal odds | Player to watch |
|---|---|---|---|---|
| Naive baseline | 0.64 | 0.68 | 0.94 | 0.32 |
| v1: season narrative only | 0.60 | 0.60 | 0.90 | 0.27 |
| v2: + last ten minutes, game state, top shooters | 0.61 | 0.56 | 0.92 | 0.34 |
| v2 + the Judge's verdicts fed back | 0.64 | 0.58 | 0.92 | 0.39 |
| v3: + "dominance is xG" | **0.66** | 0.64 | 0.92 | **0.41** |

Ten minutes of football are noisy and the naive rule is hard to beat. The closed loop adds +0.03 overall in the
ablation: the Analyst does not forecast much better than a sensible rule, but the system knows how much to
trust it and shows that number next to the rule's.

**The words are checked.** The Azure AI Evaluation groundedness grader scored the Analyst 4.86 of 5 and the
rioplatense Narrator 5.0 on 28 moments of the derby. In production, Azure AI Content Safety checks every new
commentary line against the moment's facts; when it kept flagging the Narrator asserting mood as fact, one
instruction change took the unsupported share from 57 % to 34 % over 36 samples. Results are in `backend/eval/`.

## Agents

| Agent | Model | Job |
|---|---|---|
| Interpreter | none | Stats, xG race, momentum, workload, team shape |
| Load & Risk Monitor | none | Risk windows from observables; scores itself against ground truth |
| Analyst | gpt-4o | Explains a key moment and makes a forecast; tools for workload and risk |
| Narrator | gpt-4.1-mini | One commentary line per viewer, style and language |
| Director | gpt-4.1-mini | Cards, order, headline and priority per viewer; house rules enforced in code after the call |
| Coach | gpt-4o | Substitution or tactical change on a risk window, after reading the player's workload with its tools; the engine re-simulates the branch |
| Judge | gpt-4.1-mini | Verdict and lesson on each settled forecast (the scores come from code); also hosted in Foundry |
| Scout | gpt-4.1-mini | Hosted in Foundry for the playground; its only tool is this API's MCP server, read-only |

Key moments run as a Microsoft Agent Framework `ConcurrentBuilder` workflow: the Analyst and the Narrator in
parallel, the Director on their outputs. A deterministic key-moment gate decides when agents wake up (about
3-6 s per moment), and every output is cached per match, moment and viewer profile, so the first viewer pays
the call and everyone after gets it instantly. The stream also says what it skipped: at high replay speeds a
lane drops some moments, and a `stats` message reports how many.

## Who would use it

- **Performance and medical staff:** warnings with a lead time from the workload they already track (GPS
  distance, sprints, 28-day load, ACWR), with an honest record of how often they were right.
- **The coaching bench:** a readiness board, the Coach's proposals with their re-simulated outcome, the
  five-changes-in-three-windows budget, and a decision log that ends up in the full-time report.
- **Broadcasters and fans:** the same match personalised by seat and language, every agent decision traceable.

A Monday with it, concretely: a performance analyst opens the bench seat on Saturday's match. The readiness
board says the left back was in a high-risk window from the 61st minute and the knock came in the 78th:
seventeen minutes of notice the staff did not act on. The Coach's proposal from that window, a like-for-like
change, is still in the decision log with the re-simulated outcome next to it, and the calibration says windows
like that one see a knock 27 % of the time. The conversation with the head coach is now about a number and a
timestamp, not an opinion.

## What it costs

Measured from the tokens recorded on 450 agent runs (gpt-4o at USD 2.50 / 10 per million input / output tokens,
gpt-4.1-mini at 0.40 / 1.60):

| | USD |
|---|---|
| One match, every seat explained once | 2.52 |
| A 38-match season | about 96 |
| Every viewer after the first | 0 (served from the cache) |

Hosting at one warm replica adds roughly USD 1.5-3 a day. The cache is what makes the economics work: a club
pays once per match for the explanations, not once per person who watches them.

## Deployed on Azure

Everything is code in `infra/` and deploys on every push to `main` through GitHub Actions with OpenID Connect,
with no cloud secret stored anywhere. [`infra/README.md`](infra/README.md) has each service's purpose, the
SLOs, the runbook and what was deliberately not used.

```
 GitHub Actions (OIDC) ─ build ─► ACR ─► Bicep ─► warm job ─► health ─► Static Web Apps
 Browser ── WSS, sticky, resumable ──► Container App matchmind-api (1-2 replicas, probes, 120 s grace)
     │  managed identity ──► Foundry project "matchmind": gpt-4o / gpt-4.1-mini, Traces, Evaluations,
     │                        Agents (Scout + our MCP server, Judge, four external agents), Content Safety, Speech
     │  OpenTelemetry ──► Application Insights (workbook, web test, alerts, budget)
     │  /data ◄── Azure Files (matches, warmed agent cache, voice cache)
     └─ Event Grid ──► queue ──► Job matchmind-report ──► Blob reports/   ·   Jobs matchmind-warm, matchmind-nightly
```

### Microsoft Foundry as the control plane

| What | How MatchMind uses it |
|---|---|
| Model deployments | gpt-4.1-mini for the Narrator, Director and Judge; gpt-4o for the Analyst and Coach |
| Keyless agents | `FoundryChatClient` on the project endpoint with the app's managed identity; structured outputs for every agent |
| Traces | Every agent run and tool call as gen_ai spans, attributed per agent: the four in-process agents are registered as Foundry external agents |
| Evaluations | Groundedness on the project's grader (7 of 8 items passed); Coach tool-call accuracy went from 2/5 to 5/5 on six bench situations after one graded instruction fix |
| Hosted agents | The Scout (MCP tool only) and the Judge, registered from the same code with `to_prompt_agent` |
| Red teaming | 48 adversarial prompts against the Scout: 12.5 % got through on the first scan, always by obfuscation; after one instruction fix, 0 of 40 |
| Content Safety | The fact check on every new commentary line, shown in the Control room as a drift signal |
| Speech | The commentator's voice, from the same resource |

### Azure, cloud native

| Concern | What is in place |
|---|---|
| Compute | Container Apps, sticky sessions, startup/readiness/liveness probes, 120 s grace, 1-2 replicas at 20 streams each |
| Resilience | The client reconnects with `?from=<event_id>` and the server rebuilds the state silently; verified by killing the process mid-replay |
| Events | CloudEvents to Event Grid on high risk windows and at full time; a queue-triggered job writes bench reports to Blob |
| Automation | Jobs on the same image: warm after every deploy, report on each event, a nightly match of the day with evaluations |
| Identity | Two user-assigned identities with scoped roles; the only key (Speech) lives in Key Vault; pinned non-root image |
| Operations | Log Analytics capped at 1 GB/day, a workbook, an availability test from three locations, alerts, a USD 30 budget |
| Measured | 25 concurrent viewers at 100x: 25 of 25 reached full time, first insight p95 8.8 s, 2 replicas, 0 restarts |

## Limits, honestly

- **The ground truth is ours.** The knock model is our simulator's: hazard convex in latent fatigue, spiking
  above a pre-match ACWR of 1.3, scaled by a latent susceptibility. The monitor never sees those, only what
  leaks into the observables, so the numbers prove the method learns that model, not that it works on real
  players. What transfers is the method: observables only, scored against outcomes, calibrated by bin.
- **Positions are a model, not tracking data.** A positional model places the 22 players each second from
  the events, so the picture never contradicts the data; real tracking works the other way round.
- **The product is a demo.** The demo needs no sign-in, on purpose. The club area (`/club`: the matchday's staff
  reports, generated on the server) sits behind Static Web Apps sign-in with any GitHub or Microsoft account,
  enforced at the edge. The API itself stays public and read-only by design (the one writing tool is capped at
  50 branches per match), and a replica serves about 20 replays. A club deployment would tie the API to the
  identity and isolate each club's data.
- **Decision support, not medical advice.** The Risk Monitor flags workload patterns on synthetic athletes.

## Run it locally

```bash
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env            # Foundry endpoint; agents stay off without it
.venv/Scripts/python -m pytest
.venv/Scripts/python -m uvicorn matchmind.api.app:app --port 8000

cd ../frontend && npm install && npm run dev    # http://localhost:5173
```

The API, in short:

- `GET /matches`, `GET /matches/{id}/meta`: the catalogue, teams, squads and 28-day load history.
- `WS /ws/matches/{id}?speed=60&mode=commentator&lang=es&player=THU-15`: the match as a live stream of events,
  Interpreter snapshots, risk alerts, agent insights, Coach proposals and Judge verdicts; send `{"speed": n}` or
  `{"profile": {...}}` to change them live. Positional frames ride the same socket (`frames=auto|all|0`).
- `POST /matches/{id}/branches`: the what-if, re-simulating the match from a minute with a change.
- `POST /mcp`: the MCP server with the agents' own tools (`get_match_state`, `get_player_workload`,
  `get_risk_windows`, `get_xg_race`, `get_team_shape`, `get_analyst_credibility` and more).
