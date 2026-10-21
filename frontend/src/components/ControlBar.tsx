import type { MatchRow } from '../lib/api'
import type { Player, StreamStatus, ViewerProfile } from '../lib/types'

type Props = {
  matches: MatchRow[]
  matchId: string
  onMatch: (id: string) => void
  speed: number
  onSpeed: (v: number) => void
  profile: ViewerProfile
  onProfile: (p: ViewerProfile) => void
  agents: boolean
  onAgents: (v: boolean) => void
  coach: boolean
  onCoach: (v: boolean) => void
  status: StreamStatus
  onStart: () => void
  onStop: () => void
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
      <Field label="Match">
        <select value={p.matchId} onChange={(e) => p.onMatch(e.target.value)} disabled={running}>
          {p.matches.map((m) => <option key={m.match_id} value={m.match_id}>{m.home} vs {m.away}</option>)}
        </select>
      </Field>
      <Field label="Speed">
        <input type="number" min={0} max={1000} value={p.speed} className="w-18" aria-label="replay speed"
          onChange={(e) => p.onSpeed(Math.max(0, Number(e.target.value)))} />
      </Field>
      <Field label="Viewer">
        <select value={p.profile.mode} onChange={(e) => p.onProfile({ ...p.profile, mode: e.target.value as ViewerProfile['mode'] })}>
          <option value="commentator">Commentator</option>
          <option value="analyst">Analyst</option>
          <option value="casual">Casual fan</option>
          <option value="player_focus">Follow one player</option>
        </select>
      </Field>
      <Field label="Language">
        <select value={p.profile.language} onChange={(e) => p.onProfile({ ...p.profile, language: e.target.value as ViewerProfile['language'] })}>
          <option value="es">Español rioplatense</option>
          <option value="en">English</option>
        </select>
      </Field>
      {p.profile.mode === 'player_focus' && (
        <Field label="Player">
          <select value={p.profile.favorite_player_id ?? ''} onChange={(e) => p.onProfile({ ...p.profile, favorite_player_id: e.target.value || null })}>
            <option value="">choose</option>
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
        {running
          ? <button className="btn-quiet" onClick={p.onStop}>Stop</button>
          : <button className="btn" onClick={p.onStart} disabled={!p.matchId}>{p.status === 'ended' ? 'Replay' : 'Start'}</button>}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted">{label}{children}</label>
}
