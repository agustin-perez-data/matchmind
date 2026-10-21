import type { FeedItem, VerdictItem } from '../lib/useMatchStream'
import type { CoachMsg, Credibility, Meta, RiskMsg, Snapshot } from '../lib/types'
import { nameOf } from './SidePanels'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  risk: RiskMsg | null
  feed: FeedItem[]
  verdicts: VerdictItem[]
  credibility: Credibility | null
  ended: boolean
}

/** What the bench takes home at full time: knocks and warnings, the Coach's proposals and their branches,
 *  the Analyst's credibility. Downloadable as JSON for the performance staff. */
export function BenchReport({ meta, snapshot, risk, feed, verdicts, credibility, ended }: Props) {
  const h = meta.home_id, a = meta.away_id
  const coaches = feed.filter((f): f is FeedItem & { msg: CoachMsg } => f.msg.kind === 'coach').map((f) => f.msg).reverse()
  const sc = risk?.scorecard.model, base = risk?.scorecard.baseline
  const proposals = coaches.filter((c) => c.proposal && c.proposal.action !== 'hold')
  const report = () => ({
    match_id: meta.match_id, generated_at: new Date().toISOString(),
    score: snapshot?.score ?? meta.score, teams: { [h]: meta.teams[h].name, [a]: meta.teams[a].name },
    risk: risk ? { scorecard: risk.scorecard, concerns: risk.concerns, windows_open_at_full_time: risk.active_windows, note: risk.note } : null,
    coach: coaches.map((c) => ({ clock: c.clock, trigger: c.trigger, player: c.player, proposal: c.proposal, branch: c.branch ? { status: c.branch.status, intervention: c.branch.intervention, actual: c.branch.actual, branch: c.branch.branch, diff: c.branch.diff } : null })),
    analyst: { credibility, verdicts: verdicts.map((v) => ({ issued: v.msg.issued_clock, claim: v.msg.forecast.claim, scores: v.msg.scores, naive: v.msg.naive_scores, verdict: v.msg.verdict })) },
    disclaimer: 'Synthetic league, fictional clubs and players. Risk windows are inferred from observable workload only: decision support, not medical advice.',
  })
  const download = () => {
    const blob = new Blob([JSON.stringify(report(), null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const el = document.createElement('a')
    el.href = url
    el.download = `matchmind-bench-report-${meta.match_id}.json`
    el.click()
    URL.revokeObjectURL(url)
  }
  if (!ended) {
    return (
      <section className="blk blk-coach px-4 py-3">
        <div className="flex items-baseline justify-between"><h2 className="blk-title">Bench report</h2><span className="blk-meta">at full time</span></div>
        <p className="mt-2 text-sm text-muted">Knocks and warnings, the Coach's proposals with their branches, and the Analyst's credibility, in one page and one file when the whistle goes.</p>
      </section>
    )
  }
  return (
    <section className="blk blk-coach px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Bench report</h2>
        <button className="btn btn-teal text-sm" onClick={download}>Download JSON</button>
      </div>
      <div className="display mt-2 text-2xl font-extrabold">{meta.teams[h].short_name} {snapshot?.score[h] ?? meta.score[h]} - {snapshot?.score[a] ?? meta.score[a]} {meta.teams[a].short_name}</div>

      <h3 className="blk-meta mt-3">Knocks and warnings</h3>
      {risk && sc && base ? (
        <>
          <p className="text-sm text-fg-2">{sc.concerns} knock{sc.concerns === 1 ? '' : 's'}, {sc.covered} inside an open window{sc.mean_lead_minutes != null ? ` (mean warning ${sc.mean_lead_minutes}')` : ''}; {sc.alerts} windows opened, {sc.true_alerts} came true. Minutes-only rule: {base.covered}/{base.concerns} covered from {base.alerts} windows.</p>
          <ul className="mt-1 text-sm">
            {risk.concerns.map((c) => (
              <li key={`${c.player_id}-${c.minute}`} className="py-0.5"><span className="tabular-nums text-muted">{c.clock}</span> {c.name} {c.detail}<span className={c.covered ? 'text-teal' : 'text-bad'}> · {c.covered ? `warned ${c.lead_minutes}' before` : 'not warned'}</span></li>
            ))}
            {risk.concerns.length === 0 && <li className="text-muted">No knocks today.</li>}
          </ul>
        </>
      ) : <p className="text-sm text-muted">No risk data.</p>}

      <h3 className="blk-meta mt-3">Coach</h3>
      {coaches.length === 0 ? <p className="text-sm text-muted">The Coach was not consulted.</p> : (
        <ul className="text-sm">
          {coaches.map((c, i) => {
            const p = c.proposal, b = c.branch
            const what = !p ? 'no decision' : p.action === 'hold' ? 'hold' : p.action === 'substitution' ? `${nameOf(meta, p.player_off_id)} off at ${p.minute}'${p.player_on_id ? `, ${nameOf(meta, p.player_on_id)} on` : ''}` : `tactics at ${p.minute}': press ${p.press_intensity ?? 'same'}, ${p.style ?? 'same style'}`
            return (
              <li key={i} className="py-0.5">
                <span className="tabular-nums text-muted">{c.clock}</span> {c.trigger === 'injury_concern' ? 'knock' : 'risk window'} on {c.player?.name}: <b>{what}</b>
                {b && <span className="text-fg-2"> · with the change {b.branch.score[h]}-{b.branch.score[a]} (as played {b.actual.score[h]}-{b.actual.score[a]}), knocks {b.actual.injury_concerns_total} to {b.branch.injury_concerns_total}</span>}
              </li>
            )
          })}
        </ul>
      )}
      {proposals.length > 0 && <p className="mt-1 text-xs text-muted">{proposals.length} proposal{proposals.length === 1 ? '' : 's'} simulated as counterfactual branches, same seed until the change.</p>}

      <h3 className="blk-meta mt-3">Analyst credibility</h3>
      {credibility?.judged ? (
        <p className="text-sm text-fg-2">{credibility.judged} forecast{credibility.judged === 1 ? '' : 's'} graded: Analyst {Math.round((credibility.analyst.overall ?? 0) * 100)}% vs naive {Math.round((credibility.naive.overall ?? 0) * 100)}%. {verdicts.filter((v) => v.msg.verdict.verdict === 'called_it').length} called, {verdicts.filter((v) => v.msg.verdict.verdict === 'missed').length} missed.</p>
      ) : <p className="text-sm text-muted">No forecasts graded (agents off).</p>}
      <p className="mt-2 text-xs text-muted">Synthetic league. Decision support, not medical advice.</p>
    </section>
  )
}
