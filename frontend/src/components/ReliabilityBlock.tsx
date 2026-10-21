import calibration from '../data/risk_calibration.json'
import type { RiskMsg, RiskWindow } from '../lib/types'

type Side = { n: number; hits: number; hit_rate: number | null; mean_hazard: number | null }
type Bin = { lo: number; hi: number; model: Side; baseline: Side }
const DATA = calibration as { matches: number; bins: Bin[]; model: { windows: number; hits: number; base_rate: number | null }; baseline: { windows: number; hits: number; base_rate: number | null } }
const BINS = DATA.bins

const W = 320, H = 210, L = 40, B = 30, T = 12, R = 12
const YMAX = Math.max(0.1, Math.ceil(Math.max(...BINS.map((b) => b.model.hit_rate ?? 0), ...BINS.map((b) => b.baseline.hit_rate ?? 0)) * 10) / 10)
const x = (p: number) => L + ((p - 0.5) / 0.5) * (W - L - R)
const y = (p: number) => H - B - (p / YMAX) * (H - B - T)
const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)}%`)

/** Does a higher hazard score really mean more knocks? Windows from 40 simulated matches, binned by the score
 *  they opened with, against how often a knock followed inside the window. The live match's windows are
 *  counted on top so the bench sees where today's alerts sit. */
export function ReliabilityBlock({ risk, alerts }: { risk: RiskMsg | null; alerts: RiskWindow[] }) {
  const pts = BINS.filter((b) => b.model.hit_rate != null)
  const base = BINS.filter((b) => b.baseline.hit_rate != null && b.baseline.n >= 5)
  const live = alerts.map((a) => a.hazard)
  const liveBins = BINS.map((b) => live.filter((h) => h >= b.lo && h < b.hi).length)
  const top = BINS[BINS.length - 1], low = BINS.slice(0, -1)
  const lowRate = low.reduce((s, b) => s + b.model.hits, 0) / Math.max(1, low.reduce((s, b) => s + b.model.n, 0))
  const covered = risk?.concerns.filter((c) => c.covered).length ?? 0
  return (
    <section className="blk blk-risk px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Does a higher score mean more knocks?</h2>
        <span className="blk-meta">{DATA.matches} matches, {DATA.model.windows} windows</span>
      </div>
      <p className="mt-1 text-sm text-fg-2">
        The hazard is a ranking score, not a probability. Windows opened above {top.lo.toFixed(1)} saw a knock {pct(top.model.hit_rate)} of the time; below it, {pct(lowRate)}. The grey line is the minutes-only rule.
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full max-w-[440px]" role="img" aria-label="Knock rate by hazard score bin, risk monitor against the minutes-only rule">
        <g fontFamily="Barlow Condensed" fontSize={10} fill="var(--color-muted)">
          {[0, 0.25, 0.5, 0.75, 1].map((f) => { const p = f * YMAX; return <g key={f}><line x1={L} x2={W - R} y1={y(p)} y2={y(p)} stroke="#2a3348" /><text x={L - 4} y={y(p) + 3} textAnchor="end">{Math.round(p * 100)}%</text></g> })}
          {[0.5, 0.6, 0.7, 0.8, 0.9, 1].map((p) => <text key={p} x={x(p)} y={H - B + 12} textAnchor="middle">{p.toFixed(1)}</text>)}
          <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontWeight={700} letterSpacing={1}>HAZARD SCORE WHEN THE WINDOW OPENED</text>
          <text x={11} y={T + 2} transform={`rotate(-90 11 ${T + 2})`} textAnchor="end" fontWeight={700} letterSpacing={1}>KNOCK FOLLOWED</text>
        </g>
        {base.length > 1 && <polyline fill="none" stroke="#8a93a8" strokeWidth={1.5} points={base.map((b) => `${x(b.baseline.mean_hazard!)},${y(b.baseline.hit_rate!)}`).join(' ')} />}
        {pts.length > 1 && <polyline className="draw" fill="none" stroke="var(--color-risk)" strokeWidth={2} pathLength={1} points={pts.map((b) => `${x(b.model.mean_hazard!)},${y(b.model.hit_rate!)}`).join(' ')} />}
        {pts.map((b) => (
          <g key={b.lo}>
            <circle cx={x(b.model.mean_hazard!)} cy={y(b.model.hit_rate!)} r={3 + Math.min(6, Math.sqrt(b.model.n) / 3)} fill="var(--color-risk)" fillOpacity={0.9} />
            <title>{`score ${b.lo.toFixed(1)}-${b.hi.toFixed(1)}: ${b.model.hits} knocks in ${b.model.n} windows (${pct(b.model.hit_rate)})`}</title>
          </g>
        ))}
        {BINS.map((b, i) => liveBins[i] > 0 && (
          <g key={`live-${b.lo}`}>
            <rect x={x(b.lo) + 3} y={y(0) - 3 - liveBins[i] * 4} width={x(b.hi) - x(b.lo) - 6} height={liveBins[i] * 4} fill="var(--color-amber)" fillOpacity={0.85} />
            <title>{`this match: ${liveBins[i]} window${liveBins[i] === 1 ? '' : 's'} opened at score ${b.lo.toFixed(1)}-${b.hi.toFixed(1)}`}</title>
          </g>
        ))}
      </svg>
      <p className="mt-1 text-xs text-muted">
        Orange: the monitor, dot size by window count. Amber bars: this match's {alerts.length} window{alerts.length === 1 ? '' : 's'} so far{risk?.concerns.length ? `, ${covered} of ${risk.concerns.length} knocks were inside one` : ''}. Overall, {pct(DATA.model.base_rate)} of the monitor's windows see a knock.
      </p>
    </section>
  )
}
