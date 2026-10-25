import { useState } from 'react'
import { niceAxis } from '../lib/charts'
import { blockDiffSeries, blockLeader } from '../lib/tracking'
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
  const axis = niceAxis(Math.max(0, ...race.map((p) => Math.max(Number(p[home]), Number(p[away])))))
  const x = (m: number) => P.l + (m / 95) * (W - P.l - P.r)
  const y = (v: number) => P.t + (1 - v / axis.top) * (H - P.t - P.b)
  const path = (team: string) => {
    let d = `M ${x(0)} ${y(0)}`, last = 0
    for (const p of race) { const v = Number(p[team]); d += ` H ${x(absMinute(p))} V ${y(v)}`; last = v }
    d += ` H ${x(snapshot ? absMinute(snapshot) : 0)}`
    return { d, last }
  }
  const ph = path(home), pa = path(away)
  const ink = (team: string) => (team === home ? 'var(--home-ink)' : 'var(--away-ink)')
  const goals = race.filter((p) => p.goal === true)
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
    <svg viewBox={`0 0 ${W} ${H}`} className={size === 'lg' ? 'w-full' : 'h-9 w-full'} preserveAspectRatio={size === 'lg' ? 'xMidYMid meet' : 'none'} role="img" aria-label="cumulative expected goals per team, goals marked"
      onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(95, ((e.clientX - r.left) / r.width) * 95))) }}
      onMouseLeave={() => setHover(null)}>
      {size === 'lg' && axis.ticks.map((t) => (
        <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--color-line)" /><text x={P.l - 4} y={y(t) + 3} fontSize={8} textAnchor="end" fill="var(--color-muted)">{t}</text></g>
      ))}
      {size === 'lg' && [0, 45, 90].map((m) => <text key={m} x={x(m)} y={H - 5} fontSize={8} textAnchor="middle" fill="var(--color-muted)">{m}'</text>)}
      <path d={ph.d} fill="none" stroke="var(--home-ink)" strokeWidth={2.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      <path d={pa.d} fill="none" stroke="var(--away-ink)" strokeWidth={2.4} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      {/* goals on the race: the classic marker, so a reader sees where chances turned into goals */}
      {size === 'lg' && goals.map((p) => (
        <circle key={`${p.period}-${p.clock}-${p.team_id}`} className="xg-goal" cx={x(absMinute(p))} cy={y(Number(p[p.team_id]))} r={4} fill={ink(p.team_id)} stroke="#fff" strokeWidth={1.5}>
          <title>{p.clock} goal, {meta.teams[p.team_id]?.short_name ?? p.team_id}</title>
        </circle>
      ))}
      {hover != null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="#fff" strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />}
    </svg>
  )
  if (size === 'lg') {
    return (
      <section className="blk blk-analyst px-4 py-3" style={{ borderTopColor: 'var(--color-amber)' }}>
        <div className="flex items-baseline justify-between"><h2 className="blk-title">xG race</h2>{numbers}</div>
        <div className="mt-1 flex gap-4 text-xs text-muted"><span><span className="inline-block h-0.5 w-5 align-middle" style={{ background: 'var(--home-ink)' }} /> {meta.teams[home].short_name}</span><span><span className="inline-block h-0.5 w-5 border-t-2 border-dashed align-middle" style={{ borderColor: 'var(--away-ink)' }} /> {meta.teams[away].short_name}</span><span><span className="inline-block h-2 w-2 rounded-full border border-white bg-fg-2 align-middle" /> goal</span></div>
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

/** Block height difference over the match: home block minus away block, metres from their own goals, 3-minute trailing mean.
 *  Above the line the home side sits higher (the away side is pushed back); below, the reverse. From the positional model. */
export function BlockDiffStrip({ meta, snapshot }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const diff = blockDiffSeries(snapshot?.block_series, meta)
  const home = meta.teams[meta.home_id], away = meta.teams[meta.away_id]
  const H = 56, P = { l: 2, r: 2, t: 4, b: 4 }, LIM = 25
  const x = (m: number) => P.l + (m / 95) * (W - P.l - P.r)
  const y = (v: number) => P.t + (1 - (Math.max(-LIM, Math.min(LIM, v)) + LIM) / (2 * LIM)) * (H - P.t - P.b)
  const y0 = y(0)
  const area = (sign: 1 | -1) => {
    if (!diff.length) return ''
    let d = `M ${x(absMinute(diff[0])).toFixed(1)} ${y0.toFixed(1)}`
    for (const p of diff) d += ` L ${x(absMinute(p)).toFixed(1)} ${y(sign > 0 ? Math.max(0, p.diff) : Math.min(0, p.diff)).toFixed(1)}`
    d += ` L ${x(absMinute(diff[diff.length - 1])).toFixed(1)} ${y0.toFixed(1)} Z`
    return d
  }
  const at = hover == null ? null : [...diff].reverse().find((p) => absMinute(p) <= hover)
  const shown = at ?? diff[diff.length - 1] ?? null
  const lead = blockLeader(diff)
  const higher = shown ? (shown.diff >= 0 ? home : away) : null
  const leadColor = lead.side === 'home' ? 'var(--home-ink)' : lead.side === 'away' ? 'var(--away-ink)' : 'var(--color-muted)'
  const leadText = lead.side ? `${meta.teams[lead.side === 'home' ? meta.home_id : meta.away_id].short_name} ${lead.text}` : lead.text
  return (
    <div className="blk grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3.5 py-2" title="home block minus away block: mean distance of the outfield players from their own goal, metres, 3-minute trailing mean; a side 8 m or more deeper than the other is pinned back. Positional model built from the event stream.">
      <span className="blk-meta">Block height</span>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-9 w-full" preserveAspectRatio="none" role="img" aria-label="block height difference over the match, home minus away, metres"
        onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(95, ((e.clientX - r.left) / r.width) * 95))) }}
        onMouseLeave={() => setHover(null)}>
        <line x1={P.l} x2={W - P.r} y1={y0} y2={y0} stroke="#fff" strokeOpacity={0.35} vectorEffect="non-scaling-stroke" />
        {diff.length > 1 && <path className="block-diff" d={area(1)} fill="var(--home-ink)" fillOpacity={0.6} />}
        {diff.length > 1 && <path className="block-diff" d={area(-1)} fill="var(--away-ink)" fillOpacity={0.6} />}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="#fff" strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />}
      </svg>
      <span className="display text-right text-lg font-extrabold leading-none">
        {shown && higher ? (
          <span className="block text-sm tabular-nums"><span className="mr-1 text-xs font-semibold text-muted">{at ? `${Math.round(hover!)}'` : ''}</span><span style={{ color: higher === home ? 'var(--home-ink)' : 'var(--away-ink)' }}>{higher.short_name} +{Math.round(Math.abs(shown.diff))} m</span></span>
        ) : null}
        <span className="block" style={{ color: leadColor }}>{diff.length ? leadText : 'waiting for frames'}</span>
      </span>
    </div>
  )
}

export function Momentum({ meta, snapshot }: Props) {
  const m = snapshot?.momentum ?? 0
  const h = meta.teams[meta.home_id], a = meta.teams[meta.away_id]
  const leader = Math.abs(m) < 0.15 ? 'balanced' : m > 0 ? `${h.short_name} pushing` : `${a.short_name} pushing`
  return (
    <div className="blk grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3.5 py-2" title="threat created, decaying with a 2-minute time constant (half-life 83 s): play older than 5 minutes weighs under 10 %. Not reset at half time; right favours the home side. Not the match total: see the xG race for that.">
      <span className="blk-meta">Momentum <span className="text-[11px] normal-case tracking-normal">· last ~5'</span></span>
      <div className="relative h-3 bg-ink-2" role="meter" aria-valuemin={-1} aria-valuemax={1} aria-valuenow={m} aria-label="momentum over the last five minutes or so, right favours the home side">
        <div className="absolute inset-y-0 left-1/2 w-0.5 bg-white" />
        <div className="grow-x absolute inset-y-0.5 left-1/2 w-1/2" style={{ transform: `scaleX(${Math.max(0, m)})`, transformOrigin: 'left center', background: 'var(--home-ink)' }} />
        <div className="grow-x absolute inset-y-0.5 right-1/2 w-1/2" style={{ transform: `scaleX(${Math.max(0, -m)})`, transformOrigin: 'right center', background: 'var(--away-ink)' }} />
      </div>
      <span className="display text-lg font-extrabold leading-none" style={{ color: Math.abs(m) < 0.15 ? 'var(--color-muted)' : m > 0 ? 'var(--home-ink)' : 'var(--away-ink)' }}>{leader}</span>
    </div>
  )
}
