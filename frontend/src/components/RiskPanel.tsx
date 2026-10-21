import type { Meta, RiskMsg, RiskWindow, TrackScore } from '../lib/types'

type Props = { meta: Meta; risk: RiskMsg | null; alerts: RiskWindow[] }

const pct = (v: number) => `${Math.round(v * 100)}%`

export function RiskPanel({ meta, risk, alerts }: Props) {
  const teamColor = (id: string) => (id === meta.home_id ? 'var(--color-home)' : 'var(--color-away)')
  return (
    <section className="panel p-3">
      <div className="flex items-baseline justify-between">
        <h2 className="panel-title">Load &amp; Risk Monitor</h2>
        <span className="text-xs text-ink-3">observable workload only, not medical advice</span>
      </div>

      {!risk && <p className="mt-2 text-sm text-ink-3">The first physical samples arrive after five match minutes.</p>}

      {risk && (
        <>
          <h3 className="mt-3 text-sm text-ink-2">Highest hazard on the pitch, {risk.clock}</h3>
          <ul className="mt-1">
            {risk.hazards_top.map((h) => (
              <li key={h.player_id} className="my-1 flex items-center gap-2 text-sm">
                <span className="w-36 truncate" title={h.name}><span className="mr-1 inline-block h-2.5 w-1 align-middle" style={{ background: teamColor(h.team_id) }} />{h.name}</span>
                <span className="h-2 flex-1 rounded-sm bg-panel-2"><span className="block h-full rounded-sm bg-ink-2" style={{ width: pct(h.hazard) }} /></span>
                <span className="w-10 text-right tabular-nums text-ink-2">{h.hazard.toFixed(2)}</span>
              </li>
            ))}
          </ul>

          <h3 className="mt-3 text-sm text-ink-2">Risk windows open now, next {risk.scorecard.horizon_minutes} minutes</h3>
          {risk.active_windows.length === 0
            ? <p className="text-sm text-ink-3">none</p>
            : <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
              {[...risk.active_windows].sort((x, y) => y.hazard - x.hazard).slice(0, 8).map((w) => (
                <li key={w.player_id}><Band level={w.level} /> <span className="text-sm">{w.name}</span> <span className="text-xs text-ink-3">since {w.open_minute}'</span></li>
              ))}
              {risk.active_windows.length > 8 && <li className="text-sm text-ink-3">and {risk.active_windows.length - 8} more</li>}
            </ul>}

          <h3 className="mt-3 text-sm text-ink-2">Scorecard against what actually happened</h3>
          <table className="mt-1 w-full text-sm">
            <thead><tr className="text-xs text-ink-3"><th className="text-left font-normal"></th><th className="text-right font-normal">model</th><th className="text-right font-normal">minutes-only baseline</th></tr></thead>
            <tbody>
              <Row label="Knocks covered by a window" m={risk.scorecard.model} b={risk.scorecard.baseline} f={(s) => `${s.covered}/${s.concerns}`} />
              <Row label="Windows that came true" m={risk.scorecard.model} b={risk.scorecard.baseline} f={(s) => `${s.true_alerts}/${s.alerts}`} />
              <Row label="Warning time" m={risk.scorecard.model} b={risk.scorecard.baseline} f={(s) => (s.mean_lead_minutes == null ? '–' : `${s.mean_lead_minutes}'`)} />
              <Row label="Knock was in the top 3" m={risk.scorecard.model} b={risk.scorecard.baseline} f={(s) => (s.ranked_concerns ? `${s.top3_hits}/${s.ranked_concerns}` : '–')} />
            </tbody>
          </table>
          {risk.scorecard.model.ranked_concerns > 0 && (
            <p className="mt-1 text-xs text-ink-3">Picking three players at random would hit {pct(risk.scorecard.model.top3_random_rate)} of the time.</p>
          )}
        </>
      )}

      {alerts.length > 0 && (
        <>
          <h3 className="mt-3 text-sm text-ink-2">Latest alerts</h3>
          <ul className="scroll-quiet mt-1 max-h-32 overflow-auto text-sm">
            {alerts.slice(0, 12).map((a) => (
              <li key={`${a.player_id}-${a.open_minute}`} className="py-0.5">
                <span className="tabular-nums text-ink-3">{a.clock}</span> <Band level={a.level} /> {a.name}
                <span className="text-ink-3"> · {a.minutes_played}' · ACWR {a.acwr_live}{a.effort_ratio_recent != null ? ` · effort ${Math.round(a.effort_ratio_recent * 100)}%` : ''}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {risk && risk.concerns.length > 0 && (
        <>
          <h3 className="mt-3 text-sm text-ink-2">Knocks so far</h3>
          <ul className="mt-1 text-sm">
            {risk.concerns.map((c) => (
              <li key={`${c.player_id}-${c.minute}`} className="py-0.5">
                <span className="tabular-nums text-ink-3">{c.clock}</span> {c.name} {c.detail}
                <span className={c.covered ? 'text-good' : 'text-ink-3'}> · {c.covered ? `warned ${c.lead_minutes}' earlier` : 'not warned'}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function Row({ label, m, b, f }: { label: string; m: TrackScore; b: TrackScore; f: (s: TrackScore) => string }) {
  return (
    <tr className="border-t border-line">
      <td className="py-1 text-ink-2">{label}</td>
      <td className="py-1 text-right tabular-nums">{f(m)}</td>
      <td className="py-1 text-right tabular-nums text-ink-2">{f(b)}</td>
    </tr>
  )
}

export function Band({ level }: { level: 'elevated' | 'high' }) {
  const high = level === 'high'
  return (
    <span className={`inline-block rounded-sm px-1.5 text-xs ${high ? 'bg-bad/20 text-bad' : 'bg-warn/20 text-warn'}`}>
      {high ? '▲ high' : '▲ elevated'}
    </span>
  )
}
