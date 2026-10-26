# MatchMind on Azure

Everything the product runs on, what each piece does for it, how it is operated, and what was deliberately
not used. Resource group `rg-matchmind` (eastus2). Infrastructure is code: `infra/acr.bicep` (registry) and
`infra/main.bicep` (everything else); `infra/deploy.ps1` bootstraps once; `.github/workflows/deploy.yml`
deploys every push to `main`.

```
 GitHub Actions (OIDC, no stored cloud secrets) ─ build image ─► ACR ─► Bicep ─► warm job ─► health ─► SWA deploy
                                                                                 │
 Static Web Apps (Free) ── React build with VITE_API_BASE ───────────────────────┼─────────────────┐
                                                                                 ▼                 ▼
 Browser ── HTTPS / WSS (sticky, resumable) ──► Container App "matchmind-api" (1-2 replicas, probes, grace 120 s)
                            │  /ws  /matches  /tts  /mcp  /health (ready, draining, replica, auth, telemetry)
                            │  user-assigned identity ──► Foundry PROJECT "matchmind" (FoundryChatClient, keyless)
                            │       ├─ deployments gpt-4o, gpt-4.1-mini      ├─ Observability > Traces
                            │       ├─ Evaluations: groundedness, Coach tool use   ├─ Agents: matchmind-scout, matchmind-judge
                            │       └─ Content Safety groundedness (guardrail)   └─ Speech (same resource, key in Key Vault)
                            │  OpenTelemetry (microsoft-opentelemetry) ──► Application Insights ◄── connected to the Foundry account
                            │  /data ◄── Azure Files "matchmind-data" (matches, warmed agent cache, TTS cache)
                            │  Event Grid topic "evgt-matchmind" ◄── risk window opened (high), match ended (CloudEvents 1.0)
                            └────────────────────────────────────────────────────────────────────────
 Event Grid ──► Storage queue "matchmind-events" ──► Job "matchmind-report" (KEDA azure-queue) ──► Blob reports/<match>/<fact>.json
 Job "matchmind-warm" (manual, started by the pipeline after every deploy): warms the agent cache
 Job "matchmind-nightly" (04:00 UTC): match of the day into /data, warm, risk scorecard + calibration + forecast sample to Blob eval/<date>/
 Log Analytics (1 GB/day cap) · workbook "MatchMind operations" · availability web test · 3 alerts · budget USD 30
```

## What each service does for the product

| Service | Resource | Why it is here |
|---|---|---|
| Container Apps | `matchmind-api` in `cae-matchmind` | The FastAPI streamer, Interpreter, Risk Monitor, agents and MCP server. One revision at a time, sticky sessions (a WebSocket replay is per-process state), startup/readiness/liveness probes on `/health`, 120 s termination grace so live replays finish, HTTP scaling 1-2 replicas at 20 concurrent streams, 30 min cool-down. |
| Container Apps Jobs | `matchmind-warm`, `matchmind-report`, `matchmind-nightly` | Same image, same identity. Warm after deploy (manual trigger from the pipeline), event-driven report writer (scales from 0 on queue length), nightly schedule. |
| Azure Files | share `matchmind-data` mounted at `/data` | Matches, the warmed agent cache and the TTS cache survive revisions and are shared by both replicas (the cache re-reads and merges on a miss and before every write). |
| Microsoft Foundry | account `matchmind-foundry`, project `matchmind` | The control plane for the AI: model deployments, keyless access from the API through `FoundryChatClient` on the project endpoint, Observability > Traces (via the Application Insights connection), Evaluations (groundedness, Coach tool-call accuracy / task adherence / intent resolution), hosted agents (`matchmind-scout` with our MCP server as its only tool, `matchmind-judge` v1 from the same code the API runs), Content Safety groundedness as a post-hoc guardrail, Speech for the commentator voice. |
| Managed identities | `id-matchmind-api`, `id-github-deploy` | The API pulls its image, reads Key Vault, calls Foundry, Content Safety, Event Grid and Storage with roles, never keys (`AZURE_CLIENT_ID` = the identity's client id). The pipeline signs in with a federated credential on `refs/heads/main`: no cloud secret in GitHub. |
| Key Vault | `kv-mm-*` | Holds only the Speech key (the one data-plane API here with header auth only), surfaced to the app as a Key Vault secret reference. |
| Event Grid | topic `evgt-matchmind` + subscription to the queue | The product publishes two facts: a high risk window opened, a match ended. CloudEvents 1.0, managed-identity delivery, local auth off. |
| Storage | `stmatchmind*`: queue `matchmind-events`, containers `reports`, `eval` | Durable bench reports written by the event job; nightly evaluation outputs. |
| Application Insights + Log Analytics | `appi-matchmind`, `log-matchmind` | Agent spans (gen_ai), FastAPI requests, the per-moment span and four `matchmind.*` metrics; capped at 1 GB/day. |
| Monitor | workbook, web test (3 locations, 5 min), alerts (availability, failed requests, restarts), action group, budget | Operations: the workbook shows requests, moment latency by cache hit, cache hit ratio, tokens by agent, Foundry dependencies, live viewers. |
| Static Web Apps (Free) | `swa-matchmind` | The React frontend, SPA fallback and immutable asset caching from `frontend/staticwebapp.config.json`. |
| Container Registry (Basic) | `acrmatchmind*` | The API image, pushed by the pipeline (AcrPush) and pulled by the app's identity (AcrPull). ACR Tasks is not permitted on this subscription, so GitHub Actions builds the image. |

## SLOs (and how they are checked)

| SLO | Target | Check |
|---|---|---|
| Availability of `/health` | 99.5 % of 5-minute probes | Standard web test from 3 locations; alert when 2 of 3 fail over 15 min |
| Replay completeness | 100 % of viewers reach `end` | `backend/loadtest/stream_load.py` (25 viewers at speed 300) and the smoke test on every deploy |
| Time to first insight | p95 < 8 s uncached, < 1 s cached | `stream_load.py --agents 1`; the `matchmind.moment.latency_ms` histogram by `cache_hit` in the workbook |
| Resume after a replica loss | viewers back within 2 s + backoff | `?from=<event_id>` + client reconnect (1/2/4/8/16 s); verified by restarting the revision mid-replay |
| Cost per cached replay | < USD 0.05 | Tokens by agent (`matchmind.tokens`) and the cache hit ratio in the workbook; the budget alerts at 80 % actual and 100 % forecast of USD 30 |

## Runbook

- **`/health` says `agents: false`**: the identity cannot reach the project. Check `AZURE_CLIENT_ID` is the
  client id of `id-matchmind-api`, the Foundry User role on the project and the Cognitive Services OpenAI User
  role on the account; `az containerapp logs show -n matchmind-api -g rg-matchmind --tail 200`.
- **Replays stall or drop**: `az containerapp replica list -n matchmind-api -g rg-matchmind` and the
  `RestartCount` alert; a restart drops sockets, viewers resume from their last event on the new replica. If a
  revision is wedged: `az containerapp revision restart -n matchmind-api -g rg-matchmind --revision <name>`.
- **Foundry 429s** (`insight_error` in traces, `dependencies` with 429 in the workbook): the cache serves every
  viewer once warmed; re-run the warm job at a lower speed: `az containerapp job start -n matchmind-warm -g rg-matchmind`
  (edit the args to `--speed 20` if the quota is tight).
- **Deploying while people watch**: single-revision mode replaces the revision after the new one is ready;
  the old one has 120 s to finish; viewers reconnect with `from=<id>` and continue. Measured: an
  `az containerapp revision restart` during a 100x replay never dropped the viewer's socket (the old replica
  drained the replay to full time); the reconnect path was exercised by killing the process locally.
- **Rotate the Speech key**: `az keyvault secret set --vault-name <kv> -n speech-key --value <new>`; then
  `az containerapp revision restart` (the secret reference is read at start).
- **Scale down / park**: run the workflow with `min_replicas=0` (or `az containerapp update -n matchmind-api -g rg-matchmind --min-replicas 0`);
  the first viewer pays a cold start (~10 s) and the cache is on the share, so no re-warm is needed.
- **Rollback**: `az containerapp revision list -n matchmind-api -g rg-matchmind -o table` then
  `az containerapp revision copy -n matchmind-api -g rg-matchmind --from-revision <good>`; or re-run the
  workflow on the previous commit.
- **Tear down**: `az group delete -n rg-matchmind` (the Foundry account is in the same group; export the
  evaluations first if they matter).

## Deliberately not used, and why

| Not used | Why |
|---|---|
| Azure Cache for Redis / Cosmos DB for session state | A replay is a per-process generator with wall-clock timing; sticky sessions + resumable streams solve the real problem (a replica going away) without a network round trip per event. Redis Basic/Standard creation is also blocked for new customers since April 2026. |
| Dapr | Jobs do not support it, and the only inter-service traffic is Event Grid → queue, which the SDKs cover. |
| Blue/green traffic splitting | Single-revision mode is required for sticky sessions; the resumable stream makes a cut-over invisible instead. |
| Front Door / WAF, VNet, private endpoints | Public demo API with open CORS and read-mostly endpoints; Container Apps ingress already terminates TLS. The one write-ish tool (`simulate_intervention`) is bounded (50 branches per match). |
| Azure Functions as a second runtime | Three Container Apps Jobs on the same image cover manual, event and schedule triggers with the same identity and code. |
| Model Router, fine-tuning, Foundry Toolbox, hosted Responses server | Two deployments chosen per agent tier are enough; the agents' quality work is in instructions, structured outputs and the grading loop. |
| Prompt Shields | Viewers never type into the agents; the only free-text input is the Scout in the Foundry playground, which is read-only by construction. |
| Defender for Containers runtime protection | Its runtime matrix does not list Container Apps. Compensating controls: pinned base image by digest, lock file, non-root user, no secrets in the image, identities with scoped roles, local auth off on Event Grid, budget and alerts. |
| Azure Load Testing resource | The stream test needs WebSockets; `stream_load.py` runs the same 25-viewer scenario from any machine against the public API and prints the SLO numbers. |

## Agents registered in the project

| Agent | Kind | What it is |
|---|---|---|
| `matchmind-scout` | prompt agent | Hosted in Foundry; its only tool is this API's MCP server. The playground agent. |
| `matchmind-judge` | prompt agent | The Judge, registered from the same code with `to_prompt_agent`; the API calls it when `MATCHMIND_JUDGE=foundry`. |
| `matchmind-analyst`, `matchmind-narrator`, `matchmind-director`, `matchmind-coach` | external agents (preview) | They run inside the API. Registration is metadata only: Foundry matches their spans by `gen_ai.agent.id` and shows per-agent Traces and Monitor tabs. No AI Gateway, no proxying, nothing hosted. |

The ids live in `backend/matchmind/agents/clients.py` (`AGENT_IDS`) and are passed to every agent, so the spans
carry them; `infra/register_external_agents.py` registers the four and refuses to run if an id drifted. The
Control Plane's "custom agents" are the other feature, the one that does route traffic through an AI Gateway;
MatchMind does not use it, because the external-agent path gives the same views without a proxy in the path.

## The groundedness guardrail, and what its number means

Content Safety scores how much of a line is literally supported by the facts it was given. Commentary and
analysis both carry inference, so zero is not the target and a non-zero reading is not a failure: the
Analyst's own text sits near 50 % on this detector. Read it as drift.

Two things were tuned by measuring, not by guessing. The grounding source is now the facts as plain
sentences rather than the JSON the agents receive (8 points better on identical lines), and the call uses the
QnA task with the agent's own brief as the query. Then the detector earned its keep: it kept flagging phrases
like "pushing hard with keen intent" and "the deadlock holds", which are the Narrator asserting mood as fact.
One instruction change later (energy in the verbs; never assert intent, mood or effort without a number),
the same six moments scored 34 % against 57 %, over three samples per moment per condition.

## Red teaming the Scout

The Scout is the only surface that takes free text from a person, so it is the one worth attacking.
`infra/redteam_scout.py` runs the Azure AI Evaluation red teaming agent against the hosted agent.

| Scan | Attacks | Stopped by the input filter | Got through |
|---|---|---|---|
| Scout v1 | 48 | 9 | 6 (12.5 %), all by obfuscation |
| Scout v2, after the instruction fix | 48 | 8 | 0 |

Two things to know before running it again: install the extra in a venv on a short path (`D:
t`), because
PyRIT ships file names that exceed the Windows path limit, and keep the target callback running the agent on a
worker thread. The scanner owns the event loop, so an `asyncio.run` inside the callback raises and every answer
comes back as an error, which scores as a clean 0 %.

```powershell
D:
t\Scripts\python D:\GitHub\matchmind\infra
edteam_scout.py --objectives 3
```

## Before the repository goes public

The history was scanned, not just the working tree: the live Foundry key never appears in any commit
(`git log --all -S <prefix>`), no connection string, storage key or SAS token shape appears anywhere, and the
subscription, tenant and managed-identity ids were never committed. The only GUIDs in the repository are
Azure's built-in role definition ids in `infra/main.bicep`, which are public constants. `backend/.env`,
`.azure/` and `data/` are ignored, and the Speech key lives only in Key Vault.

Repeat the scan after any change with:

```bash
git log --all -S "<first 16 chars of the live key>" --oneline     # must print nothing
git grep -nIE "(AccountKey=|InstrumentationKey=[0-9a-f]{8}-|sv=20[0-9]{2}-)" $(git rev-list --all)
```

## Bootstrap and deploy

```powershell
# once, from the repo root, signed in with az and gh
infra/deploy.ps1 -SpeechKey <key> -AlertEmail you@example.com
# every push to main afterwards: .github/workflows/deploy.yml (OIDC) builds, deploys, warms, publishes, smoke-tests
```

The first `main.bicep` run uses `bootstrap=true` (a public placeholder image) because the Container App needs an
image that exists and ACR Tasks is not permitted on the subscription; the pipeline's first run replaces it.
