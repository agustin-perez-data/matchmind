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

const STATUS_LABEL: Record<StreamStatus, string> = {
  idle: 'Ready', connecting: 'Connecting', live: 'Live', ended: 'Full time', error: 'Server unreachable',
}

export function Header(p: Props) {
  const running = p.status === 'live' || p.status === 'connecting'
  return (
    <header className="flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-line bg-panel px-4 py-3">
      <div className="mr-2">
        <div className="display text-2xl font-bold leading-none tracking-tight">MatchMind</div>
        <div className="text-xs text-ink-3">synthetic league, fictional clubs</div>
      </div>

      <Field label="Match">
        <select value={p.matchId} onChange={(e) => p.onMatch(e.target.value)} disabled={running}>
          {p.matches.map((m) => <option key={m.match_id} value={m.match_id}>{m.home} vs {m.away}</option>)}
        </select>
      </Field>
      <Field label="Speed">
        <input type="number" min={0} max={1000} value={p.speed} className="w-20" aria-label="replay speed"
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
            {p.players.map((pl) => <option key={pl.player_id} value={pl.player_id}>{pl.player_id} {pl.name}</option>)}
          </select>
        </Field>
      )}
      <label className="flex items-center gap-1 text-sm text-ink-2">
        <input type="checkbox" checked={p.agents} onChange={(e) => p.onAgents(e.target.checked)} disabled={running} /> agents
      </label>
      <label className="flex items-center gap-1 text-sm text-ink-2">
        <input type="checkbox" checked={p.coach} onChange={(e) => p.onCoach(e.target.checked)} disabled={running} /> coach
      </label>

      <div className="ml-auto flex items-center gap-3">
        <span className={`text-sm ${p.status === 'live' ? 'text-good' : p.status === 'error' ? 'text-bad' : 'text-ink-3'}`}>
          {p.status === 'live' && <span aria-hidden className="mr-1 inline-block h-2 w-2 rounded-full bg-good align-middle" />}
          {STATUS_LABEL[p.status]}
        </span>
        {running
          ? <button className="btn-quiet" onClick={p.onStop}>Stop</button>
          : <button className="btn" onClick={p.onStart} disabled={!p.matchId}>{p.status === 'ended' ? 'Replay' : 'Start'}</button>}
      </div>
    </header>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-0.5 text-xs text-ink-3">
      {label}
      {children}
    </label>
  )
}
