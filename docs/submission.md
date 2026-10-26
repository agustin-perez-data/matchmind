# Submission copy (Innovation Studio project page)

Paste-ready text for the hackathon project page. Every number is a measurement reported in the README.

## Project title

MatchMind

## Tagline (one line)

AI match intelligence that gets graded, not just heard: agents explain, narrate and predict a live match, and every prediction is scored in public.

## Description

**What it is.** MatchMind turns a live stream of football events into explainable match intelligence, as a
broadcast with four seats: a fan hears a commentator in their own language and follows a player; an analyst
gets why the match is going the way it goes, with xG, momentum and team shape; the bench sees who is about to
get hurt, what to do about it, and what would have happened; a control room watches the agents work.

**What is different.** Every AI output is graded against what actually happens. The Analyst's ten-minute
forecasts are scored by a Judge and shown next to a naive baseline, so viewers see its credibility move
during the match. The Load & Risk Monitor predicts injuries from workload alone, and across 40 simulated
matches one in three players who got hurt was among the three it had flagged as most at risk (random would be
one in seven), with 25 minutes of warning on average. The Coach proposes a substitution or a tactical change
and a deterministic engine re-simulates the match from that minute, so the counterfactual is shown, not
described.

**How it is built.** Microsoft Agent Framework orchestrates five agents on Microsoft Foundry (Analyst, Narrator,
Director, Coach, Judge), keyless from a managed identity through the Foundry project. The project is the
control plane: model deployments, per-agent traces, evaluations (groundedness 4.9 of 5 on 28 moments, Coach
tool-use accuracy 5 of 5 after one graded fix), a hosted Scout agent whose only tool is our MCP server, a
Content Safety guardrail on every narration, and a red-team scan (0 of 40 adversarial prompts got through
the hardened Scout). It runs on Azure Container Apps with Event Grid, Azure Files, Key Vault, Application
Insights, three Container Apps Jobs and a Static Web App, all as Bicep, deployed by GitHub Actions with OpenID
Connect and no stored cloud secret. A 25-viewer load test completed every replay with a p95 time to first
insight of 8.8 seconds.

**Synthetic by design.** Every club, player, event and number comes from our own simulator. No real
competition, club, person or trademark appears anywhere.

**Try it.** Live at https://lively-mushroom-0cde96c0f.5.azurestaticapps.net (one click opens the derby in the
fan seat; a match replays in about 90 seconds). Source and architecture:
https://github.com/agustin-perez-data/matchmind.

## Short description (if a 2-3 sentence field exists)

MatchMind replays a synthetic football match as a live broadcast where AI agents explain it, narrate it and
predict it, and every prediction is graded against what actually happens. Five Agent Framework agents on
Microsoft Foundry, a workload-based injury Risk Monitor scored over 40 matches, and a Coach whose
counterfactuals are re-simulated, all deployed on Azure Container Apps.

## Technologies (tags)

Microsoft Foundry · Microsoft Agent Framework · Azure OpenAI (gpt-4o, gpt-4.1-mini) · Azure AI Evaluation ·
Azure AI Content Safety · Azure AI Speech · Azure Container Apps · Container Apps Jobs · Azure Event Grid ·
Azure Static Web Apps · Azure Key Vault · Application Insights · Bicep · GitHub Actions (OIDC) · FastAPI ·
React · MCP

## Images

- `video/evidence/azure_menu.png`: the entry screen (the live loop, the three proofs, the four seats).
- `video/evidence/azure_fan.png`, `azure_analyst.png`, `azure_bench.png`, `azure_control.png`: one per seat,
  captured on the deployed app.
- Portal captures still to take: Foundry Traces (one moment with Analyst and Narrator in parallel),
  Evaluations, the Scout in the playground, the red-team run, the App Insights workbook, the green pipeline run.

## Video (under 2 minutes, no copyrighted music)

Suggested beats: 0-10 s the entry screen and one click into the derby; 10-40 s the fan seat (commentary,
the ball, follow a player); 40-70 s the analyst seat (a forecast made, then graded); 70-100 s the bench (a
risk window opens, the Coach proposes, the engine re-simulates); 100-115 s the control room and the Foundry
portal (traces, evaluations, the Scout); 115-120 s the proofs and the URL.
