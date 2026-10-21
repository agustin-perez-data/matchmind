import type { ReactNode } from 'react'
import { SEAT_ORDER, SEATS, type Seat } from '../lib/seats'
import type { StreamStatus, ViewerProfile } from '../lib/types'

type Props = {
  speed: number
  onSpeed: (v: number) => void
  seat: Seat
  onSeat: (s: Seat) => void
  status: StreamStatus
  onLeave: () => void
  language: ViewerProfile['language']
  sound: boolean
  onSound: (on: boolean) => void
}

const SPEEDS = [0, 15, 30, 60, 120, 300, 1000]
const STATUS: Record<StreamStatus, string> = { idle: 'ready', connecting: 'connecting', live: 'live', ended: 'full time', error: 'server unreachable' }

/** The production desk: brand, seat tabs, speed, status. Fixture and language are chosen on the entry page. */
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
        <Desk label="Commentary">
          <span className="display pr-2 text-sm font-extrabold uppercase tracking-wider" title="chosen on the entry page">{p.language}</span>
        </Desk>
        <button type="button" role="switch" aria-checked={p.sound} aria-label="stadium sound" title={p.sound ? 'Stadium sound on' : 'Stadium sound off'}
          onClick={() => p.onSound(!p.sound)} className={`flex h-[30px] items-center gap-1.5 border border-white/15 px-2 ${p.sound ? 'text-fg' : 'text-muted'}`}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M2 6h2.5L8 3v10L4.5 10H2z" fill="currentColor" stroke="none" />
            {p.sound ? <><path d="M10.5 5.5a3.5 3.5 0 0 1 0 5" /><path d="M12.5 3.5a6 6 0 0 1 0 9" /></> : <path d="M10.5 6l4 4M14.5 6l-4 4" />}
          </svg>
          <span className="blk-meta text-[10px]">{p.sound ? 'on' : 'off'}</span>
        </button>
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
