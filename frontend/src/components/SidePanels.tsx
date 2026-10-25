import type { BranchSummary, Meta, RiskMsg, RiskWindow, Snapshot, TrackScore } from '../lib/types'
import { absMinute } from './Strip'

/** Goals of one timeline up to a match minute (keeps the live viewer spoiler-free). */
export function scoreUpTo(side: BranchSummary['actual'], home: string, away: string, minute: number | null): Record<string, number> {
  const out: Record<string, number> = { [home]: 0, [away]: 0 }
  for (const g of side.goals) if (minute == null || absMinute(g) <= minute) out[g.team_id] = (out[g.team_id] ?? 0) + 1
  return out
}

const pct = (v: number) => `${Math.round(v * 100)}%`

export function StatsBlock({ meta, snapshot }: { meta: Meta; snapshot: Snapshot | null }) {
  const th = snapshot?.teams[meta.home_id], ta = snapshot?.teams[meta.away_id]
  if (!th || !ta) return <section className="blk px-4 py-3"><h2 className="blk-title">Match stats</h2><p className="mt-2 text-sm text-muted">Waiting for kick off.</p></section>
  const rows = [
    ['possession', `${Math.round(th.possession_pct)}%`, `${Math.round(ta.possession_pct)}%`],
    ['shots', String(th.shots), String(ta.shots)],
    ['pass accuracy', `${Math.round(th.pass_accuracy * 100)}%`, `${Math.round(ta.pass_accuracy * 100)}%`],
    ['pressures', String(th.pressures), String(ta.pressures)],
    // rates, which is what an analyst compares: quality per shot, and pressing intensity against the ball the opponent has
    ['xG per shot', th.shots ? (th.xg / th.shots).toFixed(2) : '–', ta.shots ? (ta.xg / ta.shots).toFixed(2) : '–'],
    ['pressures per 100 opp. passes', ta.passes ? String(Math.round((th.pressures / ta.passes) * 100)) : '–', th.passes ? String(Math.round((ta.pressures / th.passes) * 100)) : '–'],
  ]
  return (
    <section className="blk px-4 py-3">
      <div className="flex items-baseline justify-between" title="pressures per 100 opponent passes is a PPDA-style pressing rate: higher means the side presses more"><h2 className="blk-title">Match stats</h2><span className="blk-meta">{snapshot?.clock}</span></div>
      <dl className="mt-2">
        {rows.map(([label, h, a]) => (
          <div key={label} className="display grid grid-cols-[1fr_auto_1fr] items-center border-b border-line py-0.5 text-[26px] font-extrabold leading-tight last:border-0">
            <dd className="m-0" style={{ color: 'var(--home-ink)' }}>{h}</dd>
            <dt className="blk-meta px-3 text-xs">{label}</dt>
            <dd className="m-0 text-right" style={{ color: 'var(--away-ink)' }}>{a}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

export function RiskBlock({ meta, risk, alerts, expanded = false }: { meta: Meta; risk: RiskMsg | null; alerts: RiskWindow[]; expanded?: boolean }) {
  const teamColor = (id: string) => (id === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)')
  const sc = risk?.scorecard.model, base = risk?.scorecard.baseline
  return (
    <section className="blk blk-risk px-4 py-3">
      <div className="flex items-baseline justify-between"><h2 className="blk-title">Risk monitor</h2><span className="blk-meta">graded live</span></div>
      {!risk && <p className="mt-2 text-sm text-muted">Workload samples arrive every five match minutes.</p>}
      {risk && sc && base && (
        <>
          <div className="mt-2 grid grid-cols-[auto_1fr] items-center gap-4">
            <div key={`${sc.top3_hits}/${sc.ranked_concerns}`} className="display enter-up text-[54px] font-black leading-none text-amber">
              {sc.ranked_concerns ? `${sc.top3_hits}/${sc.ranked_concerns}` : '—'}
            </div>
            <p className="m-0 text-sm leading-snug text-fg-2">
              {sc.ranked_concerns
                ? <><b className="text-white">knocks so far hit a top-3 risk player.</b> Random would hit {pct(sc.top3_random_rate)}. Minutes-only rule: {base.top3_hits} of {base.ranked_concerns}.</>
                : <>No knocks yet. {risk.active_windows.length} risk window{risk.active_windows.length === 1 ? '' : 's'} open; every one gets graded when a knock happens.</>}
            </p>
          </div>
          <ul className="mt-2">
            {risk.hazards_top.slice(0, expanded ? 5 : 4).map((h) => (
              <li key={h.player_id} className="my-1 grid grid-cols-[112px_1fr_44px] items-center gap-2.5 text-[15px]">
                <span className="truncate" title={h.name}><span className="mr-1.5 inline-block h-3 w-1 align-middle" style={{ background: teamColor(h.team_id) }} />{h.name}</span>
                <span className="block h-2.5 bg-ink-2"><span className="grow-x block h-full w-full" style={{ transform: `scaleX(${h.hazard})`, background: 'linear-gradient(90deg,#f97316,#e8405a)' }} /></span>
                <Band windows={risk.active_windows} id={h.player_id} />
              </li>
            ))}
          </ul>
          <details className="mt-2 text-sm" open={expanded}>
            <summary className="cursor-pointer text-muted">Scorecard, windows and knocks</summary>
            <table className="mt-2 w-full text-sm">
              <thead><tr className="blk-meta text-[11px]"><th className="text-left font-semibold"></th><th className="text-right font-semibold">model</th><th className="text-right font-semibold">minutes only</th></tr></thead>
              <tbody>
                <Row label="Knocks covered by a window" m={sc} b={base} f={(s) => `${s.covered}/${s.concerns}`} />
                <Row label="Windows that came true" m={sc} b={base} f={(s) => `${s.true_alerts}/${s.alerts}`} />
                <Row label="Warning time" m={sc} b={base} f={(s) => (s.mean_lead_minutes == null ? '–' : `${s.mean_lead_minutes}'`)} />
              </tbody>
            </table>
            {risk.active_windows.length > 0 && (
              <p className="mt-2 text-fg-2">Open windows: {[...risk.active_windows].sort((x, y) => y.hazard - x.hazard).slice(0, 6).map((w) => `${w.name} (${w.level}, since ${w.open_minute}')`).join('; ')}{risk.active_windows.length > 6 ? ` and ${risk.active_windows.length - 6} more` : ''}.</p>
            )}
            {risk.concerns.length > 0 && (
              <ul className="mt-2">
                {risk.concerns.map((c) => (
                  <li key={`${c.player_id}-${c.minute}`} className="py-0.5"><span className="tabular-nums text-muted">{c.clock}</span> {c.name} {c.detail}<span className={c.covered ? 'text-teal' : 'text-muted'}> · {c.covered ? `warned ${c.lead_minutes}' earlier` : 'not warned'}</span></li>
                ))}
              </ul>
            )}
            {alerts.length > 0 && <p className="mt-2 text-muted">Latest alert: {alerts[0].clock} {alerts[0].name}, {alerts[0].level}.</p>}
          </details>
        </>
      )}
    </section>
  )
}

function Band({ windows, id }: { windows: RiskWindow[]; id: string }) {
  const w = windows.find((x) => x.player_id === id)
  if (!w) return <span className="blk-meta text-[11px] text-muted">watch</span>
  return <span className={`blk-meta text-[11px] ${w.level === 'high' ? 'text-bad' : 'text-risk'}`}>{w.level === 'high' ? 'high' : 'elev.'}</span>
}

function Row({ label, m, b, f }: { label: string; m: TrackScore; b: TrackScore; f: (s: TrackScore) => string }) {
  return (
    <tr className="border-t border-line">
      <td className="py-1 text-fg-2">{label}</td>
      <td className="py-1 text-right tabular-nums">{f(m)}</td>
      <td className="py-1 text-right tabular-nums text-muted">{f(b)}</td>
    </tr>
  )
}

export { nameOf } from '../lib/bench'
