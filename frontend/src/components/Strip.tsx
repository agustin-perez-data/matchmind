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

const W = 300

export function XgRace({ meta, snapshot, size = 'sm' }: Props & { size?: 'sm' | 'lg' }) {
  const [hover, setHover] = useState<number | null>(null)
  const race = snapshot?.xg_race ?? []
  const home = meta.home_id, away = meta.away_id
  const H = size === 'lg' ? 150 : 56
  const P = size === 'lg' ? { l: 26, r: 8, t: 10, b: 18 } : { l: 2, r: 2, t: 6, b: 4 }
  const maxY = Math.max(0.5, ...race.map((p) => Math.max(Number(p[home]), Number(p[away])))) * 1.08
  const x = (m: number) => P.l + (m / 95) * (W - P.l - P.r)
  const y = (v: number) => P.t + (1 - v / maxY) * (H - P.t - P.b)
  const path = (team: string) => {
    let d = `M ${x(0)} ${y(0)}`, last = 0
    for (const p of race) { const v = Number(p[team]); d += ` H ${x(absMinute(p))} V ${y(v)}`; last = v }
    d += ` H ${x(snapshot ? absMinute(snapshot) : 0)}`
    return { d, last }
  }
  const ph = path(home), pa = path(away)
  const at = hover == null ? null : [...race].reverse().find((p) => absMinute(p) <= hover)
  const numbers = (
    <span className="display text-xl font-extrabold leading-none">
      {at ? (
        <><span className="mr-1 text-xs font-semibold text-muted">{Math.round(hover!)}'</span><span style={{ color: 'var(--home-ink)' }}>{Number(at[home]).toFixed(2)}</span><span className="mx-1 text-sm text-muted">v</span><span style={{ color: 'var(--away-ink)' }}>{Number(at[away]).toFixed(2)}</span></>
      ) : (
        <><span style={{ color: 'var(--home-ink)' }}>{ph.last.toFixed(2)}</span><span className="mx-1 text-sm text-muted">v</span><span style={{ color: 'var(--away-ink)' }}>{pa.last.toFixed(2)}</span></>
      )}
    </span>
  )
  const chart = (
    <svg viewBox={`0 0 ${W} ${H}`} className={size === 'lg' ? 'w-full' : 'h-9 w-full'} preserveAspectRatio={size === 'lg' ? 'xMidYMid meet' : 'none'} role="img" aria-label="cumulative expected goals per team"
      onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(95, ((e.clientX - r.left) / r.width) * 95))) }}
      onMouseLeave={() => setHover(null)}>
      {size === 'lg' && [0, 0.5, 1].map((f) => (
        <g key={f}><line x1={P.l} x2={W - P.r} y1={y(f * maxY)} y2={y(f * maxY)} stroke="var(--color-line)" /><text x={P.l - 4} y={y(f * maxY) + 3} fontSize={8} textAnchor="end" fill="var(--color-muted)">{(f * maxY).toFixed(1)}</text></g>
      ))}
      {size === 'lg' && [0, 45, 90].map((m) => <text key={m} x={x(m)} y={H - 5} fontSize={8} textAnchor="middle" fill="var(--color-muted)">{m}'</text>)}
      <path d={ph.d} fill="none" stroke="var(--home-ink)" strokeWidth={2.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      <path d={pa.d} fill="none" stroke="var(--away-ink)" strokeWidth={2.4} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      {hover != null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="#fff" strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />}
    </svg>
  )
  if (size === 'lg') {
    return (
      <section className="blk blk-analyst px-4 py-3" style={{ borderTopColor: 'var(--color-amber)' }}>
        <div className="flex items-baseline justify-between"><h2 className="blk-title">xG race</h2>{numbers}</div>
        <div className="mt-1 flex gap-4 text-xs text-muted"><span><span className="inline-block h-0.5 w-5 align-middle" style={{ background: 'var(--home-ink)' }} /> {meta.teams[home].short_name}</span><span><span className="inline-block h-0.5 w-5 border-t-2 border-dashed align-middle" style={{ borderColor: 'var(--away-ink)' }} /> {meta.teams[away].short_name}</span></div>
        {chart}
      </section>
    )
  }
  return (
    <div className="blk grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3.5 py-2">
      <span className="blk-meta">xG race</span>{chart}{numbers}
    </div>
  )
}

export function Momentum({ meta, snapshot }: Props) {
  const m = snapshot?.momentum ?? 0
  const h = meta.teams[meta.home_id], a = meta.teams[meta.away_id]
  const leader = Math.abs(m) < 0.15 ? 'balanced' : m > 0 ? `${h.short_name} pushing` : `${a.short_name} pushing`
  return (
    <div className="blk grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3.5 py-2">
      <span className="blk-meta">Momentum</span>
      <div className="relative h-3 bg-ink-2" role="meter" aria-valuemin={-1} aria-valuemax={1} aria-valuenow={m} aria-label="momentum, right favours the home side">
        <div className="absolute inset-y-0 left-1/2 w-0.5 bg-white" />
        <div className="grow-x absolute inset-y-0.5 left-1/2 w-1/2" style={{ transform: `scaleX(${Math.max(0, m)})`, transformOrigin: 'left center', background: 'var(--home-ink)' }} />
        <div className="grow-x absolute inset-y-0.5 right-1/2 w-1/2" style={{ transform: `scaleX(${Math.max(0, -m)})`, transformOrigin: 'right center', background: 'var(--away-ink)' }} />
      </div>
      <span className="display text-lg font-extrabold leading-none" style={{ color: Math.abs(m) < 0.15 ? 'var(--color-muted)' : m > 0 ? 'var(--home-ink)' : 'var(--away-ink)' }}>{leader}</span>
    </div>
  )
}
