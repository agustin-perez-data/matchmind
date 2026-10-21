import type { ReactNode } from 'react'
import { SEAT_ORDER, SEATS, type Seat } from '../lib/seats'
import type { Player, StreamStatus, ViewerProfile } from '../lib/types'

type Props = {
  speed: number
  onSpeed: (v: number) => void
  language: ViewerProfile['language']
  onLanguage: (l: ViewerProfile['language']) => void
  favoritePlayerId: string | null
  onFavorite: (id: string | null) => void
  seat: Seat
  onSeat: (s: Seat) => void
  agents: boolean
  onAgents: (v: boolean) => void
  coach: boolean
  onCoach: (v: boolean) => void
  status: StreamStatus
  onLeave: () => void
  players: Player[]
}

const SPEEDS = [0, 15, 30, 60, 120, 300, 1000]
const STATUS: Record<StreamStatus, string> = { idle: 'ready', connecting: 'connecting', live: 'live', ended: 'full time', error: 'server unreachable' }

/** The production desk: brand, seat tabs, and the few controls that matter during a match. */
export function ControlBar(p: Props) {
  const running = p.status === 'live' || p.status === 'connecting'
  const step = (dir: 1 | -1) => {
    const i = SPEEDS.findIndex((s) => s >= p.speed)
    const cur = i < 0 ? SPEEDS.length - 1 : i
    p.onSpeed(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, cur + dir))])
  }
  return (
    <div className="enter-up flex flex-wrap items-stretch gap-x-3 gap-y-2 border-b border-white/10 bg-ink px-3 py-2 sm:px-6">
      <div className="display flex items-center text-xl font-black uppercase tracking-wide">MatchMind</div>

      <div className="flex items-stretch" role="tablist" aria-label="seat">
        {SEAT_ORDER.map((s) => {
          const on = p.seat === s
          return (
            <button key={s} type="button" role="tab" aria-selected={on} onClick={() => p.onSeat(s)}
              className={`display px-3 text-sm font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${on ? 'text-ink' : 'text-fg-2 hover:text-fg'}`}
              style={on ? { background: SEATS[s].rule } : { boxShadow: 'inset 0 -2px 0 rgba(255,255,255,0.15)' }}>
              {SEATS[s].label}
            </button>
          )
        })}
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <Desk label="Speed">
          <button type="button" className="desk-btn" aria-label="slower" onClick={() => step(-1)}>−</button>
          <span className="display w-12 text-center text-base font-extrabold tabular-nums">{p.speed === 0 ? 'max' : `×${p.speed}`}</span>
          <button type="button" className="desk-btn" aria-label="faster" onClick={() => step(1)}>+</button>
        </Desk>
        <Desk label="Language">
          {(['en', 'es'] as const).map((l) => (
            <button key={l} type="button" aria-pressed={p.language === l} onClick={() => p.onLanguage(l)}
              className={`display px-2 text-sm font-extrabold uppercase tracking-wider ${p.language === l ? 'bg-white text-ink' : 'text-fg-2 hover:text-fg'}`}>{l}</button>
          ))}
        </Desk>
        <Toggle label="Agents" on={p.agents} onChange={p.onAgents} hint="restarts the replay" />
        <Toggle label="Coach" on={p.coach} onChange={p.onCoach} hint="restarts the replay" />
        {p.seat === 'fan' && (
          <Desk label="Follow">
            <select value={p.favoritePlayerId ?? ''} onChange={(e) => p.onFavorite(e.target.value || null)} className="border-0 py-0 text-sm">
              <option value="">nobody</option>
              {p.players.map((pl) => <option key={pl.player_id} value={pl.player_id}>{pl.name}</option>)}
            </select>
          </Desk>
        )}
        <span className={`display ml-1 text-sm font-bold uppercase tracking-widest ${p.status === 'live' ? 'text-teal' : p.status === 'error' ? 'text-bad' : 'text-muted'}`}>
          {p.status === 'live' && <span aria-hidden className="mr-1.5 inline-block h-2 w-2 bg-teal align-middle" />}{STATUS[p.status]}
        </span>
        <button className="btn-quiet" onClick={p.onLeave}>{running ? 'Stop' : 'Change seat'}</button>
      </div>
    </div>
  )
}

function Desk({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-1 border border-white/15 pl-2">
      <span className="blk-meta mr-1 text-[10px]">{label}</span>
      <div className="flex items-center">{children}</div>
    </div>
  )
}

function Toggle({ label, on, onChange, hint }: { label: string; on: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <button type="button" role="switch" aria-checked={on} title={hint} onClick={() => onChange(!on)}
      className="flex items-center gap-2 border border-white/15 px-2 py-1">
      <span className="blk-meta text-[10px]">{label}</span>
      <span className={`relative inline-block h-4 w-8 transition-colors duration-150 ${on ? 'bg-amber' : 'bg-white/20'}`}>
        <span className="absolute top-0.5 h-3 w-3 bg-ink transition-transform duration-150" style={{ transform: `translateX(${on ? 18 : 2}px)` }} />
      </span>
    </button>
  )
}
