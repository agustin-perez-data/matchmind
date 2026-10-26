import { useMemo, useState } from 'react'
import { PitchLines } from './PitchLines'
import type { Touch } from '../lib/follow'
import { passNetwork } from '../lib/passNetwork'
import { heatCentroid } from '../lib/tracking'
import type { Meta, Snapshot } from '../lib/types'

const W = 105, H = 68
const sx = (x: number) => (x / 100) * W
const sy = (y: number) => (y / 100) * H

type Props = { meta: Meta; touches: Touch[]; snapshot: Snapshot | null; ended: boolean; compact?: boolean }

/** One team's pass network: nodes where the positional model has each player on average, links by completed passes between them. */
export function PassNetwork({ meta, touches, snapshot, ended, compact = false }: Props) {
  const [team, setTeam] = useState(meta.home_id)
  const [pick, setPick] = useState<1 | 2 | 'all' | null>(null)
  // a pass network is a match-level picture: the compact block always shows the whole match (the full block has a half picker)
  const half: 1 | 2 | 'all' = compact ? 'all' : pick ?? (ended ? 'all' : snapshot?.period === 2 ? 2 : 1)
  const positions = useMemo(() => {
    const out: Record<string, [number, number] | null> = {}
    for (const p of meta.teams[team].players) out[p.player_id] = heatCentroid(snapshot?.players[p.player_id]?.heat)
    return out
  }, [meta, team, snapshot])
  const onPitch = useMemo(() => {
    const out: Record<string, boolean> = {}
    for (const p of meta.teams[team].players) out[p.player_id] = snapshot?.players[p.player_id]?.on_pitch ?? p.starter
    return out
  }, [meta, team, snapshot])
  const modelled = Object.values(positions).some(Boolean)
  const net = useMemo(() => passNetwork(touches, team, meta, half, positions, onPitch), [touches, team, meta, half, positions, onPitch])
  const info = meta.teams[team]
  const players = useMemo(() => new Map(info.players.map((p) => [p.player_id, p])), [info])
  const ink = team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'
  const fill = team === meta.home_id ? 'var(--home)' : 'var(--away)'
  const pos = new Map(net.nodes.map((n) => [n.pid, n]))
  const maxEdge = Math.max(1, ...net.edges.map((e) => e.count))
  const label = (pid: string) => { const p = players.get(pid); return p ? `${p.shirt_number} ${p.name.split(' ').slice(-1)[0]}` : pid }
  const top = net.edges[0]
  const nodes = [...net.nodes].sort((a, b) => Number(a.onPitch) - Number(b.onPitch)) // off-pitch players drawn first, underneath
  const teamTabs = (
    <div className="flex gap-1.5" role="radiogroup" aria-label="team">
      {[meta.home_id, meta.away_id].map((tid) => {
        const on = tid === team
        const c = tid === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'
        return (
          <button key={tid} type="button" role="radio" aria-checked={on} onClick={() => setTeam(tid)}
            className={`display px-3 py-1 text-sm font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${on ? 'bg-amber text-ink' : 'bg-white/5 hover:bg-white/12'}`}
            style={on ? undefined : { color: c }}>
            {meta.teams[tid].short_name}
          </button>
        )
      })}
    </div>
  )

  return (
    <section className="blk px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="blk-title">Pass network</h2>
        {compact ? teamTabs : (
        <div className="flex items-stretch border border-white/20 bg-ink" role="radiogroup" aria-label="which half">
          {(['all', 1, 2] as const).map((h) => (
            <button key={String(h)} type="button" role="radio" aria-checked={half === h} onClick={() => setPick(h)}
              className={`display px-2.5 py-1 text-xs font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${half === h ? 'bg-amber text-ink' : 'text-fg-2 hover:bg-white/10 hover:text-fg'}`}>
              {h === 1 ? '1st' : h === 2 ? '2nd' : 'All'}
            </button>
          ))}
        </div>
        )}
      </div>
      {!compact && <div className="mt-2">{teamTabs}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} className={`mx-auto mt-3 h-auto w-full ${compact ? '' : 'max-w-[560px]'}`} role="img" aria-label={`${info.name} pass network, attacking to the right`}>
        <rect width={W} height={H} fill="#1f5c38" />
        <PitchLines stroke="#d6e9dc" strokeWidth={0.35} strokeOpacity={0.8} sixYardBoxes={false} />
        {net.edges.map((e) => {
          const a = pos.get(e.from), b = pos.get(e.to)
          if (!a || !b) return null
          return (
            <line key={`${e.from}-${e.to}`} x1={sx(a.x)} y1={sy(a.y)} x2={sx(b.x)} y2={sy(b.y)} stroke={ink}
              strokeWidth={Math.min(1.6, 0.25 + 0.18 * e.count)} strokeOpacity={0.35 + 0.55 * (e.count / maxEdge)} strokeLinecap="round">
              <title>{label(e.from)} – {label(e.to)}: {e.count} passes</title>
            </line>
          )
        })}
        {nodes.map((n) => {
          const p = players.get(n.pid)
          const r = Math.min(3.4, 1.1 + 0.28 * Math.sqrt(n.passes)) * (n.onPitch ? 1 : 0.8)
          return (
            <g key={n.pid} className="pn-node" data-off={n.onPitch ? undefined : '1'} transform={`translate(${sx(n.x)}, ${sy(n.y)})`} opacity={n.onPitch ? 1 : 0.45}>
              <circle r={r} fill={fill} stroke="#0b0f1a" strokeWidth={0.3} />
              <text y={0.9} textAnchor="middle" fontSize={2.3} fontFamily="Barlow Condensed" fontWeight={800} fill={n.passes ? '#fff' : '#cfd6e4'} stroke="#0b0f1a" strokeWidth={0.4} style={{ paintOrder: 'stroke' }}>{p?.shirt_number ?? ''}</text>
              <title>{p ? `${p.shirt_number} ${p.name}` : n.pid}: involved in {n.passes} pass{n.passes === 1 ? '' : 'es'}{n.onPitch ? '' : ' (off)'}</title>
            </g>
          )
        })}
        <text x={W - 2} y={H - 2} fontSize={3} textAnchor="end" fontFamily="Barlow Condensed" fontWeight={700} fill="#e6f2ea" fillOpacity={0.8}>attacking ▸</text>
      </svg>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: fill }} /> size: passes involved</span>
        <span><span className="mr-1 inline-block h-0.5 w-5 align-middle" style={{ background: ink }} /> width: passes between two players (2+)</span>
      </div>
      {top && (
        <p className="pn-insight mt-1 text-sm text-fg-2"><span className="text-muted">Most connected:</span> <b>{label(top.from)}</b> – <b>{label(top.to)}</b>, {top.count} passes</p>
      )}
      <p className="mt-1 text-xs text-muted">
        {net.completed} completed of {net.passes} passes{half === 'all' ? '' : half === 1 ? ' in the first half' : ' in the second half'}, {net.edges.length} link{net.edges.length === 1 ? '' : 's'}.
        {modelled ? ' Nodes where the positional model has each player on average; links from the event stream.' : ' Nodes at mean pass position; from the event stream.'}{compact ? '' : ' Attacking left to right.'}
      </p>
    </section>
  )
}
