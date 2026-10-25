import { useMemo, useState } from 'react'
import type { Touch } from '../lib/follow'
import { passNetwork } from '../lib/passNetwork'
import type { Meta, Snapshot } from '../lib/types'

const W = 105, H = 68
const sx = (x: number) => (x / 100) * W
const sy = (y: number) => (y / 100) * H

type Props = { meta: Meta; touches: Touch[]; snapshot: Snapshot | null; ended: boolean }

/** One team's pass network: nodes where each player tends to be involved, links by completed passes between them. */
export function PassNetwork({ meta, touches, snapshot, ended }: Props) {
  const [team, setTeam] = useState(meta.home_id)
  const [pick, setPick] = useState<1 | 2 | 'all' | null>(null)
  const half: 1 | 2 | 'all' = pick ?? (ended ? 'all' : snapshot?.period === 2 ? 2 : 1)
  const net = useMemo(() => passNetwork(touches, team, meta, half), [touches, team, meta, half])
  const info = meta.teams[team]
  const players = useMemo(() => new Map(info.players.map((p) => [p.player_id, p])), [info])
  const ink = team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'
  const fill = team === meta.home_id ? 'var(--home)' : 'var(--away)'
  const pos = new Map(net.nodes.map((n) => [n.pid, n]))
  const maxEdge = Math.max(1, ...net.edges.map((e) => e.count))
  const name = (pid: string) => players.get(pid)?.name.split(' ').slice(-1)[0] ?? pid

  return (
    <section className="blk px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="blk-title">Pass network</h2>
        <div className="flex items-stretch border border-white/20 bg-ink" role="radiogroup" aria-label="which half">
          {(['all', 1, 2] as const).map((h) => (
            <button key={String(h)} type="button" role="radio" aria-checked={half === h} onClick={() => setPick(h)}
              className={`display px-2.5 py-1 text-xs font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${half === h ? 'bg-amber text-ink' : 'text-fg-2 hover:bg-white/10 hover:text-fg'}`}>
              {h === 1 ? '1st' : h === 2 ? '2nd' : 'All'}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2 flex gap-1.5" role="radiogroup" aria-label="team">
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
      <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto mt-3 h-auto w-full max-w-[560px]" role="img" aria-label={`${info.name} pass network, attacking to the right`}>
        <rect width={W} height={H} fill="#1f5c38" />
        <g fill="none" stroke="#d6e9dc" strokeWidth={0.35} strokeOpacity={0.8}>
          <rect x={0} y={0} width={W} height={H} /><line x1={W / 2} y1={0} x2={W / 2} y2={H} /><circle cx={W / 2} cy={H / 2} r={9.15} />
          <rect x={0} y={13.85} width={16.5} height={40.3} /><rect x={W - 16.5} y={13.85} width={16.5} height={40.3} />
        </g>
        {net.edges.map((e) => {
          const a = pos.get(e.from), b = pos.get(e.to)
          if (!a || !b) return null
          return (
            <line key={`${e.from}-${e.to}`} x1={sx(a.x)} y1={sy(a.y)} x2={sx(b.x)} y2={sy(b.y)} stroke={ink}
              strokeWidth={Math.min(1.6, 0.25 + 0.18 * e.count)} strokeOpacity={0.35 + 0.55 * (e.count / maxEdge)} strokeLinecap="round">
              <title>{name(e.from)} – {name(e.to)}: {e.count} passes</title>
            </line>
          )
        })}
        {net.nodes.map((n) => {
          const p = players.get(n.pid)
          const r = Math.min(3.4, 1.1 + 0.28 * Math.sqrt(n.passes))
          return (
            <g key={n.pid} transform={`translate(${sx(n.x)}, ${sy(n.y)})`}>
              <circle r={r} fill={fill} stroke="#0b0f1a" strokeWidth={0.3} />
              <text y={0.9} textAnchor="middle" fontSize={2.3} fontFamily="Barlow Condensed" fontWeight={800} fill="#fff" stroke="#0b0f1a" strokeWidth={0.4} style={{ paintOrder: 'stroke' }}>{p?.shirt_number ?? ''}</text>
              <title>{p ? `${p.shirt_number} ${p.name}` : n.pid}: involved in {n.passes} passes</title>
            </g>
          )
        })}
        <text x={W - 2} y={H - 2} fontSize={3} textAnchor="end" fontFamily="Barlow Condensed" fontWeight={700} fill="#e6f2ea" fillOpacity={0.8}>attacking ▸</text>
      </svg>
      <p className="mt-2 text-xs text-muted">
        {net.completed} completed of {net.passes} passes{half === 'all' ? '' : half === 1 ? ' in the first half' : ' in the second half'}, {net.edges.length} link{net.edges.length === 1 ? '' : 's'} of 2 or more.
        Nodes sit at each player's mean involvement, sized by passes; from the event stream, attacking left to right.
      </p>
    </section>
  )
}
