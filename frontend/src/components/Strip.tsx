import { useState } from 'react'
import type { Meta, Snapshot } from '../lib/types'

export const absMinute = (p: { period: number; minute: number }) => (p.period === 1 ? p.minute : Math.max(p.minute, 45))

type Props = { meta: Meta; snapshot: Snapshot | null }

/** xG race + momentum as one broadcast strip under the top band. */
export function Strip({ meta, snapshot }: Props) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <XgRace meta={meta} snapshot={snapshot} />
      <Momentum meta={meta} snapshot={snapshot} />
    </div>
  )
}

const W = 300, H = 56, PL = 2, PR = 2, PT = 6, PB = 4

function XgRace({ meta, snapshot }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const race = snapshot?.xg_race ?? []
  const home = meta.home_id, away = meta.away_id
  const maxY = Math.max(0.5, ...race.map((p) => Math.max(Number(p[home]), Number(p[away])))) * 1.08
  const x = (m: number) => PL + (m / 95) * (W - PL - PR)
  const y = (v: number) => PT + (1 - v / maxY) * (H - PT - PB)
  const path = (team: string) => {
    let d = `M ${x(0)} ${y(0)}`, last = 0
    for (const p of race) { const v = Number(p[team]); d += ` H ${x(absMinute(p))} V ${y(v)}`; last = v }
    d += ` H ${x(snapshot ? absMinute(snapshot) : 0)}`
    return { d, last }
  }
  const ph = path(home), pa = path(away)
  const at = hover == null ? null : [...race].reverse().find((p) => absMinute(p) <= hover)
  return (
    <div className="blk grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3.5 py-2">
      <span className="blk-meta">xG race</span>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-9 w-full" preserveAspectRatio="none" role="img" aria-label="cumulative expected goals per team"
        onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(95, ((e.clientX - r.left) / r.width) * 95))) }}
        onMouseLeave={() => setHover(null)}>
        <path d={ph.d} fill="none" stroke="var(--home-ink)" strokeWidth={2.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        <path d={pa.d} fill="none" stroke="var(--away-ink)" strokeWidth={2.4} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="#fff" strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />}
      </svg>
      <span className="display text-xl font-extrabold leading-none">
        {at ? (
          <><span className="text-muted mr-1 text-xs font-semibold">{Math.round(hover!)}'</span><span style={{ color: 'var(--home-ink)' }}>{Number(at[home]).toFixed(2)}</span><span className="mx-1 text-sm text-muted">v</span><span style={{ color: 'var(--away-ink)' }}>{Number(at[away]).toFixed(2)}</span></>
        ) : (
          <><span style={{ color: 'var(--home-ink)' }}>{ph.last.toFixed(2)}</span><span className="mx-1 text-sm text-muted">v</span><span style={{ color: 'var(--away-ink)' }}>{pa.last.toFixed(2)}</span></>
        )}
      </span>
    </div>
  )
}

function Momentum({ meta, snapshot }: Props) {
  const m = snapshot?.momentum ?? 0
  const h = meta.teams[meta.home_id], a = meta.teams[meta.away_id]
  const leader = Math.abs(m) < 0.15 ? 'balanced' : m > 0 ? `${h.short_name} pushing` : `${a.short_name} pushing`
  return (
    <div className="blk grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3.5 py-2">
      <span className="blk-meta">Momentum</span>
      <div className="relative h-3 bg-ink-2" role="meter" aria-valuemin={-1} aria-valuemax={1} aria-valuenow={m} aria-label="momentum, right favours the home side">
        <div className="absolute inset-y-0 left-1/2 w-0.5 bg-white" />
        {/* two half bars, each scaled from the centre line: home grows right, away grows left */}
        <div className="grow-x absolute inset-y-0.5 left-1/2 w-1/2" style={{ transform: `scaleX(${Math.max(0, m)})`, transformOrigin: 'left center', background: 'var(--home-ink)' }} />
        <div className="grow-x absolute inset-y-0.5 right-1/2 w-1/2" style={{ transform: `scaleX(${Math.max(0, -m)})`, transformOrigin: 'right center', background: 'var(--away-ink)' }} />
      </div>
      <span className="display text-lg font-extrabold leading-none" style={{ color: Math.abs(m) < 0.15 ? 'var(--color-muted)' : m > 0 ? 'var(--home-ink)' : 'var(--away-ink)' }}>{leader}</span>
    </div>
  )
}
