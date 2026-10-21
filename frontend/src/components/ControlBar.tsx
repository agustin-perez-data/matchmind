import type { MatchRow } from '../lib/api'
import { SEAT_ORDER, SEATS, type Seat } from '../lib/seats'
import type { Player, StreamStatus, ViewerProfile } from '../lib/types'

type Props = {
  matches: MatchRow[]
  matchId: string
  onMatch: (id: string) => void
  speed: number
  onSpeed: (v: number) => void
  language: ViewerProfile['language']
  onLanguage: (l: ViewerProfile['language']) => void
  favoritePlayerId: string | null
  onFavorite: (id: string | null) => void
  seat: Seat | null
  onSeat: (s: Seat) => void
  agents: boolean
  onAgents: (v: boolean) => void
  coach: boolean
  onCoach: (v: boolean) => void
  status: StreamStatus
  onLeave: () => void
  players: Player[]
}

const STATUS: Record<StreamStatus, string> = {
  idle: 'ready', connecting: 'connecting', live: 'live', ended: 'full time', error: 'server unreachable',
}

export function ControlBar(p: Props) {
  const running = p.status === 'live' || p.status === 'connecting'
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-ink/80 px-4 py-2 text-sm backdrop-blur-sm sm:px-6">
      <div className="display mr-2 text-xl font-black uppercase tracking-wide">
        MatchMind <span className="ml-1 text-xs font-semibold tracking-widest text-muted">synthetic league</span>
      </div>
      {p.seat && (
        <div className="flex" role="group" aria-label="seat">
          {SEAT_ORDER.map((s) => (
            <button key={s} type="button" onClick={() => p.onSeat(s)} aria-pressed={p.seat === s}
              className={`display border px-3 py-1 text-sm font-extrabold uppercase tracking-wider transition-colors duration-150 ${p.seat === s ? 'border-white bg-white text-ink' : 'border-white/20 text-fg-2 hover:border-white/50'}`}
              style={p.seat === s ? { background: SEATS[s].rule, borderColor: SEATS[s].rule } : undefined}>
              {SEATS[s].label}
            </button>
          ))}
        </div>
      )}
      <Field label="Match">
        <select value={p.matchId} onChange={(e) => p.onMatch(e.target.value)} disabled={running}>
          {p.matches.map((m) => <option key={m.match_id} value={m.match_id}>{m.home} vs {m.away}</option>)}
        </select>
      </Field>
      <Field label="Speed">
        <input type="number" min={0} max={1000} value={p.speed} className="w-18" aria-label="replay speed" onChange={(e) => p.onSpeed(Math.max(0, Number(e.target.value)))} />
      </Field>
      <Field label="Language">
        <select value={p.language} onChange={(e) => p.onLanguage(e.target.value as ViewerProfile['language'])}>
          <option value="es">Español rioplatense</option>
          <option value="en">English</option>
        </select>
      </Field>
      {p.seat === 'fan' && (
        <Field label="Follow">
          <select value={p.favoritePlayerId ?? ''} onChange={(e) => p.onFavorite(e.target.value || null)}>
            <option value="">nobody in particular</option>
            {p.players.map((pl) => <option key={pl.player_id} value={pl.player_id}>{pl.name}</option>)}
          </select>
        </Field>
      )}
      <label className="flex items-center gap-1 text-muted"><input type="checkbox" checked={p.agents} onChange={(e) => p.onAgents(e.target.checked)} disabled={running} /> agents</label>
      <label className="flex items-center gap-1 text-muted"><input type="checkbox" checked={p.coach} onChange={(e) => p.onCoach(e.target.checked)} disabled={running} /> coach</label>
      <div className="ml-auto flex items-center gap-3">
        <span className={`display text-sm font-bold uppercase tracking-widest ${p.status === 'live' ? 'text-teal' : p.status === 'error' ? 'text-bad' : 'text-muted'}`}>
          {p.status === 'live' && <span aria-hidden className="mr-1.5 inline-block h-2 w-2 bg-teal align-middle" />}{STATUS[p.status]}
        </span>
        {p.seat && <button className="btn-quiet" onClick={p.onLeave}>{running ? 'Stop' : 'Change seat'}</button>}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted">{label}{children}</label>
}
