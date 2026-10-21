import { useState } from 'react'
import type { Meta, Snapshot, XgPoint } from '../lib/types'

// Match minute on one axis: first-half stoppage keeps counting, second half restarts at 45.
export const absMinute = (p: { period: number; minute: number }) => (p.period === 1 ? p.minute : Math.max(p.minute, 45))

const W = 320, H = 150, PAD = { l: 26, r: 78, t: 10, b: 20 }

type Props = { meta: Meta; snapshot: Snapshot | null }

export function XgRace({ meta, snapshot }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const race = snapshot?.xg_race ?? []
  const home = meta.home_id, away = meta.away_id
  const maxX = 95, maxY = Math.max(1, ...race.map((p) => Math.max(Number(p[home]), Number(p[away])))) * 1.1
  const x = (m: number) => PAD.l + (m / maxX) * (W - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (1 - v / maxY) * (H - PAD.t - PAD.b)

  const path = (team: string) => {
    let d = `M ${x(0)} ${y(0)}`, last = 0
    for (const p of race) {
      const m = absMinute(p), v = Number(p[team])
      d += ` H ${x(m)} V ${y(v)}`
      last = v
    }
    const end = snapshot ? absMinute(snapshot) : 0
    d += ` H ${x(end)}`
    return { d, last }
  }
  const ph = path(home), pa = path(away)
  const hovered: XgPoint | undefined = hover == null ? undefined : [...race].reverse().find((p) => absMinute(p) <= hover)

  return (
    <section className="panel p-3">
      <h2 className="panel-title">Expected goals race</h2>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full" role="img" aria-label="Cumulative expected goals per team over match time"
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          const m = ((e.clientX - r.left) / r.width * W - PAD.l) / (W - PAD.l - PAD.r) * maxX
          setHover(Math.max(0, Math.min(maxX, m)))
        }}
        onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(f * maxY)} y2={y(f * maxY)} stroke="var(--color-line)" strokeWidth={0.6} />
            <text x={PAD.l - 4} y={y(f * maxY) + 3} fontSize={8} textAnchor="end" fill="var(--color-ink-3)">{(f * maxY).toFixed(1)}</text>
          </g>
        ))}
        {[0, 45, 90].map((m) => <text key={m} x={x(m)} y={H - 6} fontSize={8} textAnchor="middle" fill="var(--color-ink-3)">{m}'</text>)}
        <path d={ph.d} fill="none" stroke="var(--color-home)" strokeWidth={2} strokeLinejoin="round" />
        <path d={pa.d} fill="none" stroke="var(--color-away)" strokeWidth={2} strokeLinejoin="round" />
        <text x={W - PAD.r + 4} y={y(ph.last) + 3} fontSize={9} fill="var(--color-ink)">{meta.teams[home].short_name} {ph.last.toFixed(2)}</text>
        <text x={W - PAD.r + 4} y={y(pa.last) + 3 + (Math.abs(y(pa.last) - y(ph.last)) < 10 ? 10 : 0)} fontSize={9} fill="var(--color-ink)">{meta.teams[away].short_name} {pa.last.toFixed(2)}</text>
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} stroke="var(--color-ink-3)" strokeWidth={0.8} strokeDasharray="2 2" />
            <rect x={Math.min(x(hover) + 6, W - 120)} y={PAD.t} width={112} height={30} rx={3} fill="var(--color-panel-2)" stroke="var(--color-line)" />
            <text x={Math.min(x(hover) + 10, W - 116)} y={PAD.t + 12} fontSize={8} fill="var(--color-ink-2)">{Math.round(hover)}'</text>
            <text x={Math.min(x(hover) + 10, W - 116)} y={PAD.t + 24} fontSize={8} fill="var(--color-ink)">
              {meta.teams[home].short_name} {hovered ? Number(hovered[home]).toFixed(2) : '0.00'} · {meta.teams[away].short_name} {hovered ? Number(hovered[away]).toFixed(2) : '0.00'}
            </text>
          </g>
        )}
      </svg>
    </section>
  )
}
