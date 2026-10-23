import type { Seat } from '../lib/seats'
import type { BallPoint, FeedItem } from '../lib/useMatchStream'
import { touchPoints, type Touch } from '../lib/follow'
import type { MatchEvent, Meta, Snapshot } from '../lib/types'
import { IconChart, IconMic } from './icons'

const W = 105, H = 68
const sx = (x: number) => (x / 100) * W
const sy = (y: number) => (y / 100) * H

type Props = {
  followId?: string | null
  touches?: Touch[]
  meta: Meta; ball: BallPoint[]; shots: MatchEvent[]; lastEvent: MatchEvent | null; snapshot: Snapshot | null
  latest: FeedItem | null; keyEvent: MatchEvent | null; seat: Seat; size?: 'lg' | 'sm'; agentsOn?: boolean
}

/** Pitch in studio perspective: shot map, ball with a short trail, possession chip, and the lower third. */
export function PitchStage({ meta, ball, shots, lastEvent, snapshot, latest, keyEvent, seat, size = 'lg', agentsOn = false, followId = null, touches = [] }: Props) {
  const mine = followId ? touchPoints(touches, followId) : []
  const color = (team?: string) => (team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)')
  const homeRight = snapshot ? snapshot.period === 1 : true
  const left = homeRight ? meta.teams[meta.home_id] : meta.teams[meta.away_id]
  const right = homeRight ? meta.teams[meta.away_id] : meta.teams[meta.home_id]
  const now = ball[ball.length - 1]
  const possession = possessionChip(meta, lastEvent, now, homeRight)

  return (
    <section className="relative">
      <div className="flex flex-wrap items-center justify-between gap-2 px-2 text-xs text-muted sm:px-6">
        {possession
          ? <span className="display text-sm font-extrabold uppercase tracking-wider" style={{ color: possession.color }}>{possession.text}</span>
          : <span>{!snapshot || snapshot.minute === 0 ? 'Waiting for kick off' : ''}</span>}
        {size === 'lg' && <span>dots are shots sized by expected goals, ringed when they went in{followId ? '; amber: your player' : ''}</span>}
      </div>
      <div className={`${size === 'lg' ? '-mt-3 sm:-mt-6' : '-mt-1'} px-2 sm:px-6`} style={{ perspective: '1000px' }}>
        <svg viewBox={`0 0 ${W} ${H}`} className={`mx-auto h-auto w-full ${size === 'lg' ? 'max-w-[720px]' : 'max-w-[460px]'}`} role="img"
          aria-label="Pitch: shot map, ball position and possession"
          style={{ transform: 'rotateX(34deg) scale(1.04)', transformOrigin: '50% 62%', filter: 'drop-shadow(0 30px 40px rgba(0,0,0,.6))' }}>
          <defs><linearGradient id="turf" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#2b7d4c" /><stop offset="1" stopColor="#17532f" /></linearGradient></defs>
          <rect width={W} height={H} fill="url(#turf)" />
          {[0, 2, 4, 6, 8, 10].map((i) => <rect key={i} x={i * (W / 12)} y={0} width={W / 12} height={H} fill="#ffffff0d" />)}
          <g fill="none" stroke="#e6f2ea" strokeWidth={0.4}>
            <rect x={0} y={0} width={W} height={H} /><line x1={W / 2} y1={0} x2={W / 2} y2={H} /><circle cx={W / 2} cy={H / 2} r={9.15} />
            <rect x={0} y={13.85} width={16.5} height={40.3} /><rect x={W - 16.5} y={13.85} width={16.5} height={40.3} />
            <rect x={0} y={24.84} width={5.5} height={18.32} /><rect x={W - 5.5} y={24.84} width={5.5} height={18.32} />
          </g>
          {/* shot map: every shot so far, sized by xG; goals ringed in amber */}
          {shots.map((e, i) => {
            const age = shots.length - 1 - i
            return (
              <g key={e.event_id} className="enter-pop" style={{ transformOrigin: `${sx(e.x!)}px ${sy(e.y!)}px`, transformBox: 'view-box' }} opacity={age > 6 ? 0.55 : 1}>
                <circle cx={sx(e.x!)} cy={sy(e.y!)} r={1 + (e.xg ?? 0) * 7} fill={color(e.team_id)} fillOpacity={0.4} stroke={color(e.team_id)} strokeWidth={0.4} />
                {e.outcome === 'goal' && <circle cx={sx(e.x!)} cy={sy(e.y!)} r={3 + (e.xg ?? 0) * 7} fill="none" stroke="var(--color-amber)" strokeWidth={0.7} />}
                <title>{e.clock} {e.player_name}, {e.outcome}, xG {e.xg?.toFixed(2)}</title>
              </g>
            )
          })}
          {/* the followed player's touches: where they acted on the ball, shots bigger */}
          {mine.map((t, i) => {
            const shot = t.type === 'shot' || t.type === 'goal'
            const newest = i === mine.length - 1
            return (
              <g key={t.event_id}>
                {newest && <circle className="ping" cx={sx(t.x)} cy={sy(t.y)} r={shot ? 2.4 : 1.6} fill="none" stroke="var(--color-amber)" strokeWidth={0.5}
                  style={{ transformOrigin: `${sx(t.x)}px ${sy(t.y)}px`, transformBox: 'view-box' }} />}
                <circle className="enter-pop" style={{ transformOrigin: `${sx(t.x)}px ${sy(t.y)}px`, transformBox: 'view-box' }}
                  cx={sx(t.x)} cy={sy(t.y)} r={shot ? 1.8 : 1} fill="var(--color-amber)" fillOpacity={shot ? 0.95 : 0.45 + Math.min(0.4, i / Math.max(1, mine.length) * 0.4)} stroke={shot ? '#0b0f1a' : 'none'} strokeWidth={0.3} />
              </g>
            )
          })}
          {/* the ball: a short comet trail and the marker */}
          {ball.length > 1 && (
            <polyline points={ball.map((b) => `${sx(b.x)},${sy(b.y)}`).join(' ')} fill="none" stroke="#fff" strokeWidth={0.5} strokeOpacity={0.55} strokeLinejoin="round" strokeLinecap="round" strokeDasharray="1.2 0.8" />
          )}
          {ball.slice(0, -1).map((b, i) => <circle key={i} cx={sx(b.x)} cy={sy(b.y)} r={0.6} fill="#fff" fillOpacity={0.15 + (i / ball.length) * 0.5} />)}
          {now && <circle className="move" cx={0} cy={0} r={1.3} fill="#fff" stroke={color(now.team_id)} strokeWidth={0.5} style={{ transform: `translate(${sx(now.x)}px, ${sy(now.y)}px)` }} />}
          <text x={2} y={H - 2} fontSize={3.2} fontFamily="Barlow Condensed" fontWeight={700} fill={homeRight ? 'var(--home-ink)' : 'var(--away-ink)'}>{left.short_name.toUpperCase()} ▸</text>
          <text x={W - 2} y={H - 2} fontSize={3.2} textAnchor="end" fontFamily="Barlow Condensed" fontWeight={700} fill={homeRight ? 'var(--away-ink)' : 'var(--home-ink)'}>◂ {right.short_name.toUpperCase()}</text>
        </svg>
      </div>
      {size === 'lg' && <LowerThird meta={meta} latest={latest} keyEvent={keyEvent} seat={seat} agentsOn={agentsOn} />}
    </section>
  )
}

function possessionChip(meta: Meta, last: MatchEvent | null, now: BallPoint | undefined, homeRight: boolean) {
  // the ball holder: the last on-ball event's side; a pressure is by the other side, so fall back to the ball's own tag
  const team = last?.team_id && ['pass', 'shot', 'tackle', 'interception'].includes(last.type) ? last.team_id : now?.team_id
  if (!team || !now) return null
  const attacksRight = team === meta.home_id ? homeRight : !homeRight
  const xTeam = attacksRight ? now.x : 100 - now.x
  const zone = xTeam < 33 ? 'own third' : xTeam < 66 ? 'middle third' : 'final third'
  return { text: `${meta.teams[team]?.short_name ?? team} in possession, ${zone}`, color: team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)' }
}

/** A headline as a sentence: one full stop, never two. */
export function sentence(s: string) { return s.replace(/[.!?…]+$/, '') + '.' }

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

function LowerThird({ meta, latest, keyEvent, seat, agentsOn }: { meta: Meta; latest: FeedItem | null; keyEvent: MatchEvent | null; seat: Seat; agentsOn: boolean }) {
  const insight = latest?.msg.kind === 'insight' ? latest.msg : null
  const coach = latest?.msg.kind === 'coach' ? latest.msg : null
  const v = insight ? Object.values(insight.viewers)[0] : null
  const title = insight ? `${v?.decision?.headline ?? insight.moment.summary.replace(/^\d+:\d+\s*/, '')} · ${insight.clock}`
    : coach ? `Coach: ${coach.proposal?.action === 'hold' ? 'holding' : 'proposes a change'} · ${coach.clock}`
      : keyEvent ? `${describe(keyEvent)} · ${keyEvent.clock}` : null
  if (!title) return null
  const key = `${latest?.id ?? 'events'}-${seat}`  // agent outputs animate in; plain event titles just update
  const h = meta.home_id, a = meta.away_id
  const narration = insight && v?.narration ? <><span className="tag"><IconMic />{v.narration.language === 'es' ? 'Relator' : 'Narrator'}</span><span className={seat === 'fan' ? 'display text-2xl font-semibold leading-tight sm:text-[28px]' : ''}>{v.narration.text}</span></> : null
  const analysis = insight?.analyst ? <><span className="tag tag-w"><IconChart />Analyst</span><span><b>{sentence(insight.analyst.headline)}</b> {insight.analyst.why_it_matters}{seat === 'analyst' ? <span className="text-muted"> {insight.analyst.key_stat}</span> : null}{seat === 'analyst' && insight.analyst.forecast && insight.moment.kind !== 'full_time' ? <span className="mt-1 block text-base text-amber">Next 10': {insight.analyst.forecast.claim}</span> : null}</span></> : null
  const bench = coach?.proposal ? <><span className="tag tag-t">Coach</span><span>{coach.proposal.rationale}{coach.branch ? ` With the change: ${coach.branch.branch.score[h]}-${coach.branch.branch.score[a]}, knocks ${coach.branch.actual.injury_concerns_total} to ${coach.branch.branch.injury_concerns_total}.` : ''}</span></> : null
  const rows = seat === 'fan' ? [narration, analysis] : seat === 'analyst' ? [analysis, narration] : [bench, analysis, narration]
  return (
    <div key={key} className="relative -mt-6 px-2 sm:-mt-10 sm:px-6">
      <div className="lt-bar wipe-in-left inline-block px-5 py-1 text-2xl sm:text-[36px]">{title}</div>
      {rows.some(Boolean) ? (
        <div className="lt-sub enter grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-2 px-5 py-3 text-base leading-snug sm:text-lg">
          {rows.filter(Boolean).slice(0, 2)}
        </div>
      ) : agentsOn && !latest ? (
        <div className="lt-sub enter px-5 py-2 text-sm text-muted">{seat === 'fan' ? 'Relator warming up: the first call comes with the first chance, goal or knock.' : 'Agents warming up: the first read comes with the first key moment.'}</div>
      ) : null}
    </div>
  )
}
