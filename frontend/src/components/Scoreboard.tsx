import type { Meta, Snapshot, StreamStatus } from '../lib/types'

type Props = { meta: Meta; snapshot: Snapshot | null; flash: number; status: StreamStatus }

export function Scoreboard({ meta, snapshot, flash, status }: Props) {
  const h = meta.teams[meta.home_id], a = meta.teams[meta.away_id]
  const score = snapshot?.score ?? { [h.team_id]: 0, [a.team_id]: 0 }
  const th = snapshot?.teams[h.team_id], ta = snapshot?.teams[a.team_id]
  const stats = th && ta ? [
    { label: 'xG', home: th.xg.toFixed(2), away: ta.xg.toFixed(2) },
    { label: 'Possession', home: `${Math.round(th.possession_pct)}%`, away: `${Math.round(ta.possession_pct)}%` },
    { label: 'Shots, on target', home: `${th.shots}, ${th.shots_on_target}`, away: `${ta.shots}, ${ta.shots_on_target}` },
    { label: 'Pass accuracy', home: `${Math.round(th.pass_accuracy * 100)}%`, away: `${Math.round(ta.pass_accuracy * 100)}%` },
    { label: 'Pressures', home: String(th.pressures), away: String(ta.pressures) },
  ] : []

  return (
    <section key={flash} className={`panel px-4 py-3 sm:px-5 ${flash ? 'goal-flash' : ''}`} aria-live="polite">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-4">
        <TeamName team={h} color="var(--color-home)" align="right" />
        <div className="display text-center leading-none">
          <div className="text-5xl font-bold tabular-nums sm:text-6xl">{score[h.team_id]}<span className="mx-1.5 text-ink-3 sm:mx-2">:</span>{score[a.team_id]}</div>
          <div className="mt-1 whitespace-nowrap text-base text-ink-2 sm:text-lg">
            {snapshot?.clock ?? '00:00'}
            {status === 'ended' ? <span className="ml-2 text-amber">full time</span> : snapshot?.period === 2 ? <span className="ml-2 text-ink-3">2nd half</span> : null}
          </div>
        </div>
        <TeamName team={a} color="var(--color-away)" align="left" />
      </div>
      {stats.length > 0 && (
        <ul className="mt-3 grid gap-x-6 gap-y-1 border-t border-line pt-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
          {stats.map((s) => (
            <li key={s.label} className="grid grid-cols-[1fr_auto_1fr] items-baseline gap-2 whitespace-nowrap">
              <span className="text-right tabular-nums">{s.home}</span>
              <span className="text-center text-xs text-ink-3">{s.label}</span>
              <span className="text-left tabular-nums">{s.away}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function TeamName({ team, color, align }: { team: Meta['teams'][string]; color: string; align: 'left' | 'right' }) {
  return (
    <div className={`display flex min-w-0 items-center gap-2 text-lg font-semibold uppercase tracking-wide sm:text-2xl ${align === 'right' ? 'justify-end' : ''}`}>
      {align === 'left' && <span aria-hidden className="h-6 w-1.5 shrink-0 rounded-sm" style={{ background: color }} />}
      <span className="truncate" title={team.name}>
        <span className="sm:hidden">{team.short_name}</span>
        <span className="hidden sm:inline">{team.name}</span>
      </span>
      {align === 'right' && <span aria-hidden className="h-6 w-1.5 shrink-0 rounded-sm" style={{ background: color }} />}
    </div>
  )
}
