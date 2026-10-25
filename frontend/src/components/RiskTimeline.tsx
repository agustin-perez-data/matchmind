import { useState } from 'react'
import { currentHazard, topHazards } from '../lib/bench'
import { labelLayout } from '../lib/charts'
import type { Meta, RiskMsg, Snapshot } from '../lib/types'
import { absMinute } from './Strip'

const W = 320, H = 170, P = { l: 26, r: 64, t: 10, b: 18 }, MAX = 95

type Props = { meta: Meta; snapshot: Snapshot | null; risk: RiskMsg | null; team: string; focus?: string | null }

/** Hazard over the match for the five most loaded players of a side (plus the focused one): one point per workload sample. */
export function RiskTimeline({ meta, snapshot, risk, team, focus = null }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const series = risk?.hazard_series ?? {}
  const players = snapshot?.players ?? {}
  const pids = Object.values(players).filter((p) => p.team_id === team && p.on_pitch).map((p) => p.player_id)
  let drawn = topHazards(series, pids, 5)
  // the focused player joins the picture even outside the top five, and is drawn last so he sits on top
  const focusOk = !!focus && players[focus]?.team_id === team && players[focus]?.on_pitch && currentHazard(series, focus) != null
  if (focusOk && !drawn.some((d) => d.pid === focus)) drawn = [...drawn.slice(0, 4), { pid: focus!, hazard: currentHazard(series, focus!)! }]
  if (focusOk) drawn = [...drawn.filter((d) => d.pid !== focus), drawn.find((d) => d.pid === focus)!]
  const ink = team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'
  const x = (m: number) => P.l + (Math.min(MAX, m) / MAX) * (W - P.l - P.r)
  const y = (v: number) => P.t + (1 - v) * (H - P.t - P.b)
  const path = (pts: [number, number][]) => pts.map((pt, i) => (i === 0 ? `M ${x(pt[0])} ${y(pt[1])}` : `H ${x(pt[0])} V ${y(pt[1])}`)).join(' ')
  const knocks = (risk?.concerns ?? []).filter((c) => players[c.player_id]?.team_id === team)
  const now = snapshot ? absMinute(snapshot) : 0
  const at = (pts: [number, number][], m: number) => [...pts].reverse().find((pt) => pt[0] <= m)?.[1]
  const surname = (pid: string) => players[pid]?.name.split(' ').slice(-1)[0] ?? pid
  const labels = new Map(labelLayout(drawn.map((d) => { const pts = series[d.pid] ?? []; const last = pts[pts.length - 1]; return { pid: d.pid, y: last ? y(last[1]) + 3 : 0 } }), 9, P.t + 6, H - P.b - 2).map((l) => [l.pid, l.y]))

  return (
    <section className="blk blk-risk px-4 py-3">
      <div className="flex items-baseline justify-between"><h2 className="blk-title">Risk over time</h2><span className="blk-meta">{meta.teams[team].short_name} · top 5 now{focusOk ? ' + focus' : ''}</span></div>
      {drawn.length === 0 ? (
        <p className="mt-2 text-sm text-muted">Workload samples arrive every five match minutes; the first curve appears with the first sample.</p>
      ) : (
        <>
          <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" role="img" aria-label="hazard per player over the match"
            onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); const m = ((e.clientX - r.left) / r.width) * W; setHover(Math.max(0, Math.min(MAX, ((m - P.l) / (W - P.l - P.r)) * MAX))) }}
            onMouseLeave={() => setHover(null)}>
            {[0, 0.5, 0.7, 1].map((v) => (
              <g key={v}>
                <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} stroke={v === 0.5 || v === 0.7 ? (v === 0.7 ? 'var(--color-bad)' : 'var(--color-risk)') : 'var(--color-line)'} strokeOpacity={v === 0.5 || v === 0.7 ? 0.6 : 1} strokeDasharray={v === 0.5 || v === 0.7 ? '4 3' : undefined} />
                <text x={P.l - 4} y={y(v) + 3} fontSize={8} textAnchor="end" fill="var(--color-muted)">{v.toFixed(1)}</text>
              </g>
            ))}
            {[0, 45, 90].map((m) => <text key={m} x={x(m)} y={H - 5} fontSize={8} textAnchor="middle" fill="var(--color-muted)">{m}'</text>)}
            {drawn.map(({ pid }, i) => {
              const pts = series[pid] ?? []
              const last = pts[pts.length - 1]
              const isFocus = focusOk && pid === focus
              const opacity = focusOk ? (isFocus ? 1 : 0.35) : 1 - i * 0.14
              return (
                <g key={pid} className={`rt-line${isFocus ? ' rt-focus' : ''}`} opacity={opacity}>
                  <path d={path(pts)} fill="none" stroke={ink} strokeWidth={isFocus ? 3 : 2} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
                  {last && <text x={x(last[0]) + 4} y={labels.get(pid) ?? y(last[1]) + 3} fontSize={8} fontFamily="Barlow Condensed" fontWeight={isFocus ? 800 : 700} fill={ink}>{surname(pid)}</text>}
                  <title>{players[pid]?.name}: hazard {last?.[1].toFixed(2)}</title>
                </g>
              )
            })}
            {knocks.map((c) => (
              <g key={`${c.player_id}-${c.minute}`} className="rt-knock">
                <line x1={x(c.minute)} x2={x(c.minute)} y1={P.t} y2={H - P.b} stroke="var(--color-bad)" strokeWidth={2} />
                <title>{c.clock} knock: {c.name}{c.covered ? `, warned ${c.lead_minutes}' earlier` : ', not warned'}</title>
              </g>
            ))}
            {!hover && now > 0 && <line x1={x(now)} x2={x(now)} y1={P.t} y2={H - P.b} stroke="#fff" strokeOpacity={0.25} vectorEffect="non-scaling-stroke" />}
            {hover != null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="#fff" strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />}
          </svg>
          <div className="mt-1 text-xs text-muted">
            {hover != null
              ? <>{Math.round(hover)}': {drawn.map(({ pid }) => `${surname(pid)} ${at(series[pid] ?? [], hover)?.toFixed(2) ?? '–'}`).join(' · ')}</>
              : <>One point per workload sample (every five match minutes). Dashed: window threshold 0.5 and high 0.7. Red ticks: knocks{knocks.length ? ` (${knocks.filter((c) => c.covered).length} of ${knocks.length} inside a window)` : ''}.{focusOk ? ' Bold: the focused player.' : ''}</>}
          </div>
        </>
      )}
    </section>
  )
}
