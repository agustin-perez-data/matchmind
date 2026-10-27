// The Monday report: the bench report as one printable page a performance staff can read, forward or print to PDF.
// Pure (data in, HTML string out) so it is tested without a browser; the bench seat downloads it at full time.
import type { DecisionEntry } from './bench'
import type { Credibility, Meta, RiskMsg } from './types'

export type StaffReportInput = {
  meta: Meta
  score: Record<string, number>
  risk: RiskMsg | null
  entries: DecisionEntry[]
  credibility: Credibility | null
  generatedAt: Date
}

const esc = (s: unknown): string =>
  String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

const pct = (x: number | null | undefined): string => (x == null ? 'n/a' : `${Math.round(x * 100)} %`)

/** The headline sentence about warnings, written for a person, not a dashboard. */
export function warningSummary(risk: RiskMsg | null): string {
  const sc = risk?.scorecard.model
  if (!sc || !sc.concerns) return 'No knocks in this match.'
  const knocks = `${sc.concerns} knock${sc.concerns === 1 ? '' : 's'}`
  const warned = sc.covered === sc.concerns ? 'all of them' : `${sc.covered} of them`
  const lead = sc.mean_lead_minutes != null && sc.covered ? `, with ${Math.round(sc.mean_lead_minutes)} minutes of notice on average` : ''
  return `${knocks}; the Risk Monitor had warned about ${sc.covered ? warned : 'none of them'}${lead}.`
}

export function staffReportHtml({ meta, score, risk, entries, credibility, generatedAt }: StaffReportInput): string {
  const h = meta.home_id, a = meta.away_id
  const home = meta.teams[h], away = meta.teams[a]
  const concerns = risk?.concerns ?? []
  const knockRows = concerns.map((c) => `<tr><td>${esc(c.clock)}</td><td>${esc(c.name)}</td><td>${esc(c.detail)}</td><td>${c.covered ? `warned${c.lead_minutes != null ? `, ${c.lead_minutes} min before` : ''}` : 'not warned'}</td></tr>`).join('')
  const decisionRows = entries.map((e) => {
    const b = e.branch
    const outcome = b && b.status === 'applied'
      ? `${b.actual.score?.[h] ?? '?'}-${b.actual.score?.[a] ?? '?'} as played, ${b.branch.score?.[h] ?? '?'}-${b.branch.score?.[a] ?? '?'} with the change; knocks ${b.actual.injury_concerns_total} to ${b.branch.injury_concerns_total}`
      : b ? 'the change could not be applied' : 'not simulated'
    return `<tr><td>${esc(e.clock)}</td><td>${e.source === 'coach' ? 'Coach' : 'Bench'}</td><td>${esc(e.player ?? '')}</td><td>${esc(e.decision)}</td><td>${esc(outcome)}</td></tr>`
  }).join('')
  // the three most at risk by name, the rest as a count: a staff report names who to look at, not the whole squad
  const windows = [...(risk?.active_windows ?? [])].sort((x, y) => (y.hazard ?? 0) - (x.hazard ?? 0))
  const named = windows.slice(0, 3).map((w) => esc(w.name ?? w.player_id)).join(', ')
  const open = windows.length > 3 ? `${named} and ${windows.length - 3} more` : named
  const cred = credibility?.judged
    ? `<p>The Analyst made ${credibility.judged} graded forecasts: ${pct(credibility.analyst.overall)} against ${pct(credibility.naive.overall)} for a naive rule on the same windows.</p>`
    : '<p>No forecast was graded in this match.</p>'
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>${esc(home.short_name)} v ${esc(away.short_name)}: staff report</title>
<style>
body{font:15px/1.5 system-ui,sans-serif;color:#111;max-width:860px;margin:32px auto;padding:0 20px}
h1{font-size:26px;margin:0}h2{font-size:17px;margin:28px 0 8px;border-bottom:2px solid #111;padding-bottom:4px}
.meta{color:#555;font-size:13px}.lead{font-size:18px;margin:16px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd;vertical-align:top}
th{background:#f3f3f3}.note{color:#555;font-size:12px;margin-top:32px}
@media print{body{margin:0}a{color:inherit}}
</style></head><body>
<h1>${esc(home.name)} ${score[h] ?? ''} - ${score[a] ?? ''} ${esc(away.name)}</h1>
<div class="meta">MatchMind staff report · ${esc(meta.match_id)} · generated ${esc(generatedAt.toISOString().slice(0, 16).replace('T', ' '))} UTC</div>
<p class="lead">${esc(warningSummary(risk))}${open ? ` Still in a risk window at full time: ${open}.` : ''}</p>
<h2>Knocks</h2>
${concerns.length ? `<table><tr><th>Clock</th><th>Player</th><th>What happened</th><th>Warning</th></tr>${knockRows}</table>` : '<p>None.</p>'}
<h2>Decisions taken or tried</h2>
${entries.length ? `<table><tr><th>Clock</th><th>By</th><th>Player</th><th>Decision</th><th>Re-simulated outcome</th></tr>${decisionRows}</table>` : '<p>No change was proposed or tried.</p>'}
<h2>How far to trust the Analyst</h2>
${cred}
<p class="note">Synthetic league, fictional clubs and players. Risk windows are inferred from observable workload only; this is decision support, not medical advice. Outcomes of changes come from re-simulating the match from that minute with the same seed.</p>
</body></html>`
}
