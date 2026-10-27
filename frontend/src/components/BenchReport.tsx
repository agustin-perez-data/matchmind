import type { VerdictItem } from '../lib/useMatchStream'
import type { DecisionEntry } from '../lib/bench'
import { staffReportHtml } from '../lib/staffReport'
import type { Credibility, Meta, RiskMsg, Snapshot } from '../lib/types'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  risk: RiskMsg | null
  verdicts: VerdictItem[]
  credibility: Credibility | null
  entries: DecisionEntry[]
  ended: boolean
}

/** What the bench takes home at full time: knocks and warnings, every decision taken or tried (the Coach's and the
 *  bench's own) with its counterfactual, the Analyst's credibility. Opens as a printable staff report. */
export function BenchReport({ meta, snapshot, risk, verdicts, credibility, entries, ended }: Props) {
  const h = meta.home_id, a = meta.away_id
  const sc = risk?.scorecard.model, base = risk?.scorecard.baseline
  const bySource = { coach: entries.filter((e) => e.source === 'coach').length, bench: entries.filter((e) => e.source === 'bench').length }
  const save = (body: string, type: string, name: string) => {
    const url = URL.createObjectURL(new Blob([body], { type }))
    const el = document.createElement('a')
    el.href = url
    el.download = name
    el.click()
    URL.revokeObjectURL(url)
  }
  // the Monday report: one printable page for the staff (open it, print to PDF, forward it)
  const downloadStaff = () => save(staffReportHtml({ meta, score: snapshot?.score ?? meta.score, risk, entries, credibility, generatedAt: new Date() }),
    'text/html', `matchmind-staff-report-${meta.match_id}.html`)
  if (!ended) {
    return (
      <details className="blk blk-coach px-4 py-2 text-sm">
        <summary className="display cursor-pointer text-base font-extrabold uppercase tracking-wider text-fg-2">Bench report <span className="blk-meta ml-2 normal-case">at full time</span></summary>
        <p className="mt-2 text-sm text-muted">Knocks and warnings, every decision taken or tried with its branch, and the Analyst's credibility, in one page and one file when the whistle goes.</p>
      </details>
    )
  }
  return (
    <section className="blk blk-coach px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Bench report</h2>
        <span className="flex flex-wrap gap-2">
          <button className="btn btn-teal text-sm" onClick={downloadStaff}>Staff report</button>
          <a className="btn-quiet text-sm" href="/club" target="_blank" rel="noreferrer" title="Every match's report, behind sign-in (opens in a new tab, this match stays here)">Club area</a>
        </span>
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

      <h3 className="blk-meta mt-3">Decisions</h3>
      {entries.length === 0 ? <p className="text-sm text-muted">Nothing was proposed or tried.</p> : (
        <table className="br-decisions mt-1 w-full text-sm">
          <thead><tr className="blk-meta text-[11px]"><th className="text-left font-semibold">min</th><th className="text-left font-semibold">source</th><th className="text-left font-semibold">trigger</th><th className="text-left font-semibold">decision</th><th className="text-right font-semibold">as played</th><th className="text-right font-semibold">with the change</th><th className="text-right font-semibold">knocks</th></tr></thead>
          <tbody>
            {entries.map((e) => {
              const b = e.branch
              return (
                <tr key={e.id} className="border-t border-line align-top">
                  <td className="py-1 tabular-nums text-muted">{e.clock}</td>
                  <td className="py-1"><span className={`display px-1 text-[10px] font-extrabold uppercase tracking-wider ${e.source === 'coach' ? 'bg-teal/20 text-teal' : 'bg-amber/20 text-amber'}`}>{e.source}</span></td>
                  <td className="py-1 text-fg-2">{e.trigger ? `${e.trigger}${e.player ? ` on ${e.player}` : ''}` : 'bench'}</td>
                  <td className="py-1 font-semibold">{e.decision}{b?.status === 'skipped' ? <span className="font-normal text-muted"> (not applied)</span> : null}</td>
                  <td className="py-1 text-right tabular-nums">{b ? `${b.actual.score[h]}-${b.actual.score[a]}` : '–'}</td>
                  <td className="py-1 text-right tabular-nums text-teal">{b ? `${b.branch.score[h]}-${b.branch.score[a]}` : '–'}</td>
                  <td className="py-1 text-right tabular-nums">{b ? `${b.actual.injury_concerns_total} → ${b.branch.injury_concerns_total}` : '–'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {entries.length > 0 && <p className="mt-1 text-xs text-muted">{bySource.coach} Coach decision{bySource.coach === 1 ? '' : 's'}, {bySource.bench} tried by the bench; branches simulated as counterfactuals, same seed until the change.</p>}

      <h3 className="blk-meta mt-3">Analyst credibility</h3>
      {credibility?.judged ? (
        <p className="text-sm text-fg-2">{credibility.judged} forecast{credibility.judged === 1 ? '' : 's'} graded: Analyst {Math.round((credibility.analyst.overall ?? 0) * 100)}% vs naive {Math.round((credibility.naive.overall ?? 0) * 100)}%. {verdicts.filter((v) => v.msg.verdict.verdict === 'called_it').length} called, {verdicts.filter((v) => v.msg.verdict.verdict === 'missed').length} missed.</p>
      ) : <p className="text-sm text-muted">No forecasts graded (agents off).</p>}
      <p className="mt-2 text-xs text-muted">Synthetic league. Decision support, not medical advice.</p>
    </section>
  )
}
