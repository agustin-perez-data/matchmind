import type { FeedItem } from '../lib/useMatchStream'
import type { MatchEvent, Meta, Snapshot } from '../lib/types'
import { IconChart, IconMic } from './icons'

const W = 105, H = 68
const sx = (x: number) => (x / 100) * W
const sy = (y: number) => (y / 100) * H

type Props = { meta: Meta; trail: MatchEvent[]; lastEvent: MatchEvent | null; snapshot: Snapshot | null; latest: FeedItem | null; keyEvent: MatchEvent | null }

/** Pitch in studio perspective with the lower third of the latest key moment over it. */
export function PitchStage({ meta, trail, lastEvent, snapshot, latest, keyEvent }: Props) {
  const color = (team?: string) => (team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)')
  const passes = trail.filter((e) => e.type === 'pass' && typeof e.end_x === 'number')
  const shots = trail.filter((e) => e.type === 'shot')
  const ball = lastEvent && typeof lastEvent.x === 'number' ? { x: lastEvent.end_x ?? lastEvent.x, y: lastEvent.end_y ?? (lastEvent.y as number) } : null
  const homeRight = snapshot ? snapshot.period === 1 : true
  const left = homeRight ? meta.teams[meta.home_id] : meta.teams[meta.away_id]
  const right = homeRight ? meta.teams[meta.away_id] : meta.teams[meta.home_id]

  return (
    <section className="relative">
      <div className="-mt-4 px-2 sm:-mt-8 sm:px-8" style={{ perspective: '1000px' }}>
        <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto h-auto w-full max-w-[720px]" role="img" aria-label="Pitch with the latest passes and shots"
          style={{ transform: 'rotateX(34deg) scale(1.04)', transformOrigin: '50% 62%', filter: 'drop-shadow(0 30px 40px rgba(0,0,0,.6))' }}>
          <defs><linearGradient id="turf" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#2b7d4c" /><stop offset="1" stopColor="#17532f" /></linearGradient></defs>
          <rect width={W} height={H} fill="url(#turf)" />
          {[0, 2, 4, 6, 8, 10].map((i) => <rect key={i} x={i * (W / 12)} y={0} width={W / 12} height={H} fill="#ffffff0d" />)}
          <g fill="none" stroke="#e6f2ea" strokeWidth={0.4}>
            <rect x={0} y={0} width={W} height={H} /><line x1={W / 2} y1={0} x2={W / 2} y2={H} /><circle cx={W / 2} cy={H / 2} r={9.15} />
            <rect x={0} y={13.85} width={16.5} height={40.3} /><rect x={W - 16.5} y={13.85} width={16.5} height={40.3} />
            <rect x={0} y={24.84} width={5.5} height={18.32} /><rect x={W - 5.5} y={24.84} width={5.5} height={18.32} />
          </g>
          {passes.map((e, i) => (
            <line key={e.event_id} className="enter-fade" x1={sx(e.x!)} y1={sy(e.y!)} x2={sx(e.end_x!)} y2={sy(e.end_y!)}
              stroke={color(e.team_id)} strokeWidth={0.5} strokeLinecap="round" strokeOpacity={0.2 + 0.7 * ((i + 1) / passes.length)}
              strokeDasharray={e.outcome === 'incomplete' ? '1 1' : undefined} />
          ))}
          {shots.map((e) => (
            <g key={e.event_id} className="enter-pop" style={{ transformOrigin: `${sx(e.x!)}px ${sy(e.y!)}px`, transformBox: 'fill-box' }}>
              <circle cx={sx(e.x!)} cy={sy(e.y!)} r={1 + (e.xg ?? 0) * 6} fill={color(e.team_id)} fillOpacity={0.4} stroke={color(e.team_id)} strokeWidth={0.35} />
              {e.outcome === 'goal' && <circle cx={sx(e.x!)} cy={sy(e.y!)} r={2.8 + (e.xg ?? 0) * 6} fill="none" stroke="var(--color-amber)" strokeWidth={0.6} />}
            </g>
          ))}
          {ball && <circle className="move" cx={0} cy={0} r={1.1} fill="#fff" stroke="#000" strokeWidth={0.2} style={{ transform: `translate(${sx(ball.x)}px, ${sy(ball.y)}px)` }} />}
          <text x={2} y={H - 2} fontSize={3.2} fontFamily="Barlow Condensed" fontWeight={700} fill={homeRight ? 'var(--home-ink)' : 'var(--away-ink)'}>{left.short_name.toUpperCase()} ▸</text>
          <text x={W - 2} y={H - 2} fontSize={3.2} textAnchor="end" fontFamily="Barlow Condensed" fontWeight={700} fill={homeRight ? 'var(--away-ink)' : 'var(--home-ink)'}>◂ {right.short_name.toUpperCase()}</text>
        </svg>
      </div>
      <LowerThird meta={meta} latest={latest} keyEvent={keyEvent} />
    </section>
  )
}

export function describe(e: MatchEvent): string {
  switch (e.type) {
    case 'shot': return `${e.player_name}, ${e.outcome === 'saved' ? 'shot saved' : e.outcome === 'blocked' ? 'shot blocked' : 'shot off target'}`
    case 'goal': return `Goal, ${e.player_name}`
    case 'card': return `${e.card} card, ${e.player_name}`
    case 'injury_concern': return `${e.player_name} ${e.detail}`
    case 'substitution': return `${e.player_on_name} on for ${e.player_off_name}${e.forced ? ' (coach)' : ''}`
    case 'tactical_change': return 'Tactical change'
    case 'half_time': return 'Half time'
    case 'full_time': return 'Full time'
    case 'kickoff': case 'second_half_kickoff': return 'Kick off'
    default: return e.type.replace('_', ' ')
  }
}

function LowerThird({ meta, latest, keyEvent }: { meta: Meta; latest: FeedItem | null; keyEvent: MatchEvent | null }) {
  // The latest agent output wins; before the agents speak, the latest key event does.
  const insight = latest?.msg.kind === 'insight' ? latest.msg : null
  const coach = latest?.msg.kind === 'coach' ? latest.msg : null
  const v = insight ? Object.values(insight.viewers)[0] : null
  const title = insight ? `${v?.decision?.headline ?? insight.moment.summary.replace(/^\d+:\d+\s*/, '')} · ${insight.clock}`
    : coach ? `Coach: ${coach.proposal?.action === 'hold' ? 'holding' : 'proposes a change'} · ${coach.clock}`
      : keyEvent ? `${describe(keyEvent)} · ${keyEvent.clock}` : null
  if (!title) return null
  const key = latest?.id ?? `ev-${keyEvent?.event_id}`
  const teamOf = (id?: string) => (id ? meta.teams[id]?.short_name : '')
  return (
    <div key={key} className="relative -mt-8 px-2 sm:-mt-14 sm:px-8">
      <div className="lt-bar wipe-in-left inline-block px-5 py-1 text-2xl sm:text-[40px]">{title}</div>
      {(insight || coach) && (
        <div className="lt-sub enter grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-2 px-5 py-3 text-base leading-snug sm:text-xl">
          {insight && v?.narration && <><span className="tag mt-0.5"><IconMic />{v.narration.language === 'es' ? 'Relator' : 'Narrator'}</span><span>{v.narration.text}</span></>}
          {insight?.analyst && v?.decision?.show.includes('insight') !== false && <><span className="tag tag-w mt-0.5"><IconChart />Analyst</span><span><b>{insight.analyst.headline}.</b> {insight.analyst.why_it_matters}</span></>}
          {coach?.proposal && <><span className="tag tag-t mt-0.5">Coach</span><span>{coach.proposal.rationale}{coach.branch ? ` With the change: ${coach.branch.branch.score[meta.home_id]}-${coach.branch.branch.score[meta.away_id]} (${teamOf(meta.home_id)} ${teamOf(meta.away_id)}), knocks ${coach.branch.actual.injury_concerns_total} to ${coach.branch.branch.injury_concerns_total}.` : ''}</span></>}
        </div>
      )}
    </div>
  )
}
