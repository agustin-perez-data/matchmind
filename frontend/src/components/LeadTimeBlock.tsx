import type { RiskMsg, TrackScore } from '../lib/types'

const pct = (v: number) => `${Math.round(v * 100)}%`

/** How early the monitor warned, against a minutes-only rule: the bench's own credibility number. */
export function LeadTimeBlock({ risk }: { risk: RiskMsg | null }) {
  const m = risk?.scorecard.model, b = risk?.scorecard.baseline
  const open = risk?.active_windows.length ?? 0
  return (
    <section className="blk blk-risk px-4 py-3">
      <div className="flex items-baseline justify-between"><h2 className="blk-title">Warning time</h2><span className="blk-meta">model vs minutes-only rule</span></div>
      {!risk || !m || !b ? (
        <p className="mt-2 text-sm text-muted">Workload samples arrive every five match minutes.</p>
      ) : m.concerns === 0 ? (
        <>
          <div className="mt-2 grid grid-cols-[auto_1fr] items-end gap-x-4">
            <div className="display text-[44px] font-black leading-none text-amber">{open}</div>
            <p className="pb-1 text-sm text-fg-2">risk window{open === 1 ? '' : 's'} open, no knock yet. Each window is graded when a knock happens or when it expires after {risk.scorecard.horizon_minutes} minutes.</p>
          </div>
          <p className="mt-2 text-xs text-muted">The grey column is the rule "warn whoever has played longest"; the monitor has to beat it on the same windows.</p>
        </>
      ) : (
        <>
          <div className="mt-2 grid grid-cols-[auto_1fr] items-end gap-x-4">
            <div className="display text-[44px] font-black leading-none text-amber tabular-nums">{m.mean_lead_minutes == null ? '–' : `${m.mean_lead_minutes}'`}</div>
            <p className="pb-1 text-sm text-fg-2">mean warning before a knock, vs <b className="text-fg">{b.mean_lead_minutes == null ? '–' : `${b.mean_lead_minutes}'`}</b> for the minutes-only rule.</p>
          </div>
          <table className="mt-2 w-full text-sm">
            <thead><tr className="blk-meta text-[11px]"><th className="text-left font-semibold"></th><th className="text-right font-semibold">model</th><th className="text-right font-semibold">minutes only</th></tr></thead>
            <tbody>
              <Row label="Knocks warned in advance" m={m} b={b} f={(s) => `${s.covered} of ${s.concerns}`} />
              <Row label="Windows that came true" m={m} b={b} f={(s) => `${s.true_alerts} of ${s.alerts}`} />
              <Row label="Knocks on a top-3 risk player" m={m} b={b} f={(s) => (s.ranked_concerns ? `${s.top3_hits} of ${s.ranked_concerns}` : '–')} />
            </tbody>
          </table>
          <p className="mt-1 text-xs text-muted">Random would hit a top-3 player {pct(m.top3_random_rate)} of the time.</p>
          <ul className="mt-2 text-sm">
            {risk.concerns.map((c) => (
              <li key={`${c.player_id}-${c.minute}`} className="py-0.5"><span className="tabular-nums text-muted">{c.clock}</span> {c.name} {c.detail}<span className={c.covered ? 'text-teal' : 'text-muted'}> · {c.covered ? `warned ${c.lead_minutes}' earlier` : 'not warned'}</span></li>
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
      <td className="py-1 text-fg-2">{label}</td>
      <td className="py-1 text-right tabular-nums">{f(m)}</td>
      <td className="py-1 text-right tabular-nums text-muted">{f(b)}</td>
    </tr>
  )
}
