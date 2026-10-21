import type { MatchEvent, Meta, Snapshot, StreamStatus, Team } from '../lib/types'
import { Crest, onColor } from './Crest'

type Props = { meta: Meta; snapshot: Snapshot | null; status: StreamStatus; lastGoal: MatchEvent | null; flash: number }

export function TopBand({ meta, snapshot, status, lastGoal, flash }: Props) {
  const h = meta.teams[meta.home_id], a = meta.teams[meta.away_id]
  const score = snapshot?.score ?? { [h.team_id]: 0, [a.team_id]: 0 }
  const th = snapshot?.teams[h.team_id], ta = snapshot?.teams[a.team_id]
  const flashSide = lastGoal?.team_id === h.team_id ? 'flash-h' : lastGoal?.team_id === a.team_id ? 'flash-a' : ''
  return (
    <header className="grid grid-cols-[1fr_auto_1fr] sm:h-[104px]" aria-live="polite">
      <div key={`h${flash}`} className={`wipe-h slide-in-left flex items-center gap-3 px-4 sm:gap-5 sm:px-11 ${lastGoal?.team_id === h.team_id ? flashSide : ''}`} style={{ color: onColor(h.primary_color) }}>
        <span className="hidden sm:block"><Crest team={h} size={56} /></span>
        <TeamSide team={h} sub={th ? `${th.shots_on_target} on target · xG ${th.xg.toFixed(2)}` : ''} />
      </div>
      <div className="drop-in grid min-w-[136px] grid-rows-[1fr_auto] place-items-center bg-white px-3 pt-1 text-ink sm:min-w-[340px] sm:px-4">
        <div className="display flex items-baseline text-5xl font-black leading-none sm:text-7xl">
          <Flip value={score[h.team_id]} />
          <span className="mx-2 text-3xl sm:text-5xl">-</span>
          <Flip value={score[a.team_id]} />
        </div>
        <div className="display flex items-center gap-2 whitespace-nowrap pb-2 text-xs font-bold tracking-widest text-[#3b4252] sm:gap-3 sm:text-lg">
          <b className="bg-amber px-2">{snapshot?.clock ?? '00:00'}</b>
          <span>{status === 'ended' ? 'FULL TIME' : snapshot?.period === 2 ? '2ND HALF' : '1ST HALF'}</span>
        </div>
      </div>
      <div key={`a${flash}`} className={`wipe-a slide-in-right flex items-center justify-end gap-3 px-4 text-right sm:gap-5 sm:px-11 ${lastGoal?.team_id === a.team_id ? flashSide : ''}`} style={{ color: onColor(a.primary_color) }}>
        <TeamSide team={a} sub={ta ? `xG ${ta.xg.toFixed(2)} · ${ta.shots_on_target} on target` : ''} />
        <span className="hidden sm:block"><Crest team={a} size={56} /></span>
      </div>
    </header>
  )
}

function TeamSide({ team, sub }: { team: Team; sub: string }) {
  const { name, short_name: short } = team
  return (
    <div className="min-w-0 py-2 sm:py-0">
      <div className="display truncate text-2xl font-extrabold uppercase leading-none sm:text-[46px]" title={name}>
        <span className="sm:hidden">{team.team_id}</span><span className="hidden sm:inline md:hidden">{short}</span><span className="hidden md:inline">{name}</span>
      </div>
      {sub && <div className="display mt-1.5 hidden text-sm font-semibold tracking-[0.14em] uppercase opacity-80 sm:block">{sub}</div>}
    </div>
  )
}

/** A digit that drops in when it changes (keyed remount + @starting-style). */
function Flip({ value }: { value: number }) {
  return <span key={value} className="enter-up inline-block tabular-nums">{value}</span>
}
