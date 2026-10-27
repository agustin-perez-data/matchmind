import { useEffect, Fragment, useCallback, useState, type ReactNode, type RefObject } from 'react'
import type { Seat } from '../lib/seats'
import type { BallPoint, FeedItem } from '../lib/useMatchStream'
import { touchPoints, type Touch } from '../lib/follow'
import { attacksRight, heatCellRect, heatCells } from '../lib/tracking'
import type { Frame, InsightMsg, MatchEvent, Meta, Snapshot } from '../lib/types'
import { IconChart, IconMic } from './icons'
import { isInterrupt } from '../lib/control'
import { PitchLines, Turf } from './PitchLines'
import { TrackingLayer } from './TrackingLayer'

const W = 105, H = 68
const sx = (x: number) => (x / 100) * W
const sy = (y: number) => (y / 100) * H

type Props = {
  followId?: string | null
  touches?: Touch[]
  ended?: boolean
  frameRef?: RefObject<Frame | null>
  speed?: number
  rings?: Record<string, string>
  meta: Meta; ball: BallPoint[]; shots: MatchEvent[]; lastEvent: MatchEvent | null; snapshot: Snapshot | null
  /** Called when the side on the ball (from the frames) changes, so other blocks can follow the same source. */
  onPossessionTeam?: (teamId: string | null) => void
  latest: FeedItem | null; keyEvent: MatchEvent | null; seat: Seat; size?: 'lg' | 'sm'; agentsOn?: boolean
}

/** Pitch in studio perspective: shot map, ball with a short trail, possession chip, and the lower third. */
export function PitchStage({ meta, ball, shots, lastEvent, snapshot, latest, keyEvent, seat, size = 'lg', agentsOn = false, followId = null, touches = [], ended = false, frameRef, speed = 1, rings, onPossessionTeam }: Props) {
  const who = seat === 'fan' ? 'your player' : 'the focused player'
  // the positional model: while frames flow the 22 dots and the ball come from them; the event ball stands in otherwise
  const [tracking, setTracking] = useState(false)
  const onActive = useCallback((a: boolean) => setTracking(a), [])
  const [livePoss, setLivePoss] = useState<BallPoint | null>(null) // from the frames: who carries the ball and where
  const onPossession = useCallback((p: BallPoint) => setLivePoss(p), [])
  useEffect(() => { onPossessionTeam?.(tracking ? livePoss?.team_id ?? null : null) }, [tracking, livePoss?.team_id, onPossessionTeam])
  const [heat, setHeat] = useState(false)
  const [shape, setShape] = useState(seat === 'analyst') // the analyst wants the blocks by default; fans see players first
  const heatGrid = followId ? snapshot?.players[followId]?.heat : undefined
  const heatOn = heat && !!heatGrid
  // Which half the map shows. Teams swap ends at half time, so "all" mixes both ends; a half reads clean.
  // Until the viewer picks, the map follows the match: the half being played, then everything at full time.
  const [pick, setPick] = useState<1 | 2 | 'all' | null>(null)
  const half: 1 | 2 | 'all' = pick ?? (ended ? 'all' : snapshot?.period === 2 ? 2 : 1)
  const inHalf = (period: number) => half === 'all' || period === half
  const shownShots = shots.filter((e) => inHalf(e.period))
  const mine = (followId ? touchPoints(touches.filter((t) => inHalf(t.period)), followId) : [])
  const color = (team?: string) => (team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)')
  const currentHalfRight = snapshot ? snapshot.period === 1 : true
  const homeRight = half === 'all' ? currentHalfRight : half === 1
  const left = homeRight ? meta.teams[meta.home_id] : meta.teams[meta.away_id]
  const right = homeRight ? meta.teams[meta.away_id] : meta.teams[meta.home_id]
  const now = ball[ball.length - 1]
  // while frames flow the chip follows the carrier in the frame (the keeper after a save, the interceptor after a pass), not the last event
  const possession = tracking && livePoss ? possessionChip(meta, null, livePoss, homeRight) : possessionChip(meta, lastEvent, now, homeRight)
  const followedTeam = followId ? snapshot?.players[followId]?.team_id ?? null : null
  const heatRight = followedTeam ? attacksRight(meta, followedTeam, half === 'all' ? (snapshot?.period ?? 1) : half) : true

  return (
    <section className="relative">
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-2 px-2 text-xs text-muted sm:px-6">
        <div className="flex items-stretch border border-white/20 bg-ink" role="radiogroup" aria-label="which half the map shows">
          <span className="blk-meta hidden items-center px-2 text-[10px] sm:flex">Map</span>
          {(['all', 1, 2] as const).map((h) => (
            <button key={String(h)} type="button" role="radio" aria-checked={half === h} onClick={() => setPick(h)}
              className={`display px-3 py-1.5 text-sm font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${half === h ? 'bg-amber text-ink' : 'text-fg-2 hover:bg-white/10 hover:text-fg'}`}>
              {h === 1 ? '1st half' : h === 2 ? '2nd half' : 'All'}
            </button>
          ))}
          {!!heatGrid && (
            <button type="button" aria-pressed={heat} onClick={() => setHeat((v) => !v)} title={`where ${who} has been, from the positional model`}
              className={`display border-l border-white/20 px-3 py-1.5 text-sm font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${heat ? 'bg-amber text-ink' : 'text-fg-2 hover:bg-white/10 hover:text-fg'}`}>
              Heat
            </button>
          )}
          {frameRef && (
            <button type="button" aria-pressed={shape} onClick={() => setShape((v) => !v)} title="each side's block, the outfield players' outline, from the positional model"
              className={`display border-l border-white/20 px-3 py-1.5 text-sm font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${shape ? 'bg-amber text-ink' : 'text-fg-2 hover:bg-white/10 hover:text-fg'}`}>
              Shape
            </button>
          )}
        </div>
        {possession
          ? <span className="display text-sm font-extrabold uppercase tracking-wider" style={{ color: possession.color }}>{possession.text}</span>
          : <span>{!snapshot || snapshot.minute === 0 ? 'Waiting for kick off' : ''}</span>}
        {size === 'lg' && <span>{heatOn ? `amber cells: where ${who} has been · ` : ''}shots sized by expected goals, ringed when they went in{followId ? `; amber: ${who}` : ''}{rings && Object.keys(rings).length ? '; dashed ring: open risk window' : ''}{tracking ? `; players${shape ? ' and shaded blocks' : ''}: positional model (away outlined white${shape ? ', dashed block' : ''})` : ''}</span>}
      </div>
      <div className={`${size === 'lg' ? '-mt-3 sm:-mt-6' : '-mt-1'} px-2 sm:px-6`} style={{ perspective: '1000px' }}>
        <svg viewBox={`0 0 ${W} ${H}`} className={`mx-auto h-auto w-full ${size === 'lg' ? 'max-w-[720px]' : 'max-w-[460px]'}`} role="img"
          aria-label="Pitch: shot map, ball position and possession"
          style={{ transform: 'rotateX(34deg) scale(1.04)', transformOrigin: '50% 62%', filter: 'drop-shadow(0 30px 40px rgba(0,0,0,.6))' }}>
          <Turf />
          <PitchLines />
          {/* the followed player's heat: team-frame grid placed for the direction their side attacks in the shown half */}
          {heatOn && heatCells(heatGrid).map((c) => {
            const r = heatCellRect(c.index, heatRight)
            return <rect key={c.index} x={sx(r.x)} y={sy(r.y)} width={sx(r.w)} height={sy(r.h)} fill="var(--color-amber)" fillOpacity={0.1 + 0.6 * c.level} />
          })}
          {/* shot map: every shot so far, sized by xG; goals ringed in amber */}
          {shownShots.map((e, i) => {
            const age = shownShots.length - 1 - i
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
          {now && !tracking && <circle className="move" cx={0} cy={0} r={1.3} fill="#fff" stroke={color(now.team_id)} strokeWidth={0.5} style={{ transform: `translate(${sx(now.x)}px, ${sy(now.y)}px)` }} />}
          {frameRef && <TrackingLayer meta={meta} frameRef={frameRef} speed={speed} followId={followId} size={size} ended={ended} hull={shape} rings={rings} onActive={onActive} onPossession={onPossession} />}
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

/** The clock to print next to an insight: the break moments carry stoppage clocks that read oddly once the next period runs. */
export function stamp(insight: Pick<InsightMsg, 'clock' | 'moment'>): string {
  return insight.moment.kind === 'half_time' ? 'HT' : insight.moment.kind === 'full_time' ? 'FT' : insight.clock
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

function LowerThird({ meta, latest, keyEvent, seat, agentsOn }: { meta: Meta; latest: FeedItem | null; keyEvent: MatchEvent | null; seat: Seat; agentsOn: boolean }) {
  const insight = latest?.msg.kind === 'insight' ? latest.msg : null
  const coach = latest?.msg.kind === 'coach' ? latest.msg : null
  const v = insight ? Object.values(insight.viewers)[0] : null
  const title = insight ? `${v?.decision?.headline ?? insight.moment.summary.replace(/^\d+:\d+\s*/, '')} · ${stamp(insight)}`
    : coach ? `Coach: ${coach.proposal?.action === 'hold' ? 'holding' : 'proposes a change'} · ${coach.clock}`
      : keyEvent ? `${describe(keyEvent)} · ${keyEvent.clock}` : null
  if (!title) return null
  const key = `${latest?.id ?? 'events'}-${seat}`  // agent outputs animate in; plain event titles just update
  const h = meta.home_id, a = meta.away_id
  const narration = insight && v?.narration ? <><span className="tag"><IconMic />{v.narration.language === 'es' ? 'Relator' : 'Narrator'}</span><span className={seat === 'fan' ? 'display text-2xl font-semibold leading-tight sm:text-[28px]' : ''}>{v.narration.text}</span></> : null
  // the analyst seat has its own read card for the key stat and the live call; the bench keeps them here
  const analysis = insight?.analyst ? <><span className="tag tag-w"><IconChart />Analyst</span><span><b>{sentence(insight.analyst.headline)}</b> {insight.analyst.why_it_matters}{seat === 'bench' ? <span className="text-muted"> {insight.analyst.key_stat}</span> : null}{seat === 'bench' && insight.analyst.forecast && insight.moment.kind !== 'full_time' ? <span className="mt-1 block text-base text-amber">Next 10': {insight.analyst.forecast.claim}</span> : null}</span></> : null
  const bench = coach?.proposal ? <><span className="tag tag-t">Coach</span><span>{coach.proposal.rationale}{coach.branch ? ` With the change: ${coach.branch.branch.score[h]}-${coach.branch.branch.score[a]}, knocks ${coach.branch.actual.injury_concerns_total} to ${coach.branch.branch.injury_concerns_total}.` : ''}</span></> : null
  const rows: { key: string; node: ReactNode }[] = seat === 'fan'
    ? [{ key: 'narration', node: narration }, { key: 'analysis', node: analysis }]
    : seat === 'analyst' ? [{ key: 'analysis', node: analysis }, { key: 'narration', node: narration }]
      : [{ key: 'bench', node: bench }, { key: 'analysis', node: analysis }, { key: 'narration', node: narration }]
  // the Director's priority decides how loud the moment is: an interrupt gets the full lower third, the rest one line
  const loud = !insight || isInterrupt(insight)
  const shown = rows.filter((r) => r.node).slice(0, loud ? 2 : 1)
  return (
    <div key={key} className="relative -mt-6 px-2 sm:-mt-10 sm:px-6" data-loud={loud ? '1' : '0'}>
      <div className={`lt-bar wipe-in-left inline-block px-5 py-1 ${loud ? 'text-2xl sm:text-[36px]' : 'text-lg sm:text-2xl'}`}>{title}</div>
      {shown.length ? (
        <div className="lt-sub enter grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-2 px-5 py-3 text-base leading-snug sm:text-lg">
          {shown.map((r) => <Fragment key={r.key}>{r.node}</Fragment>)}
        </div>
      ) : agentsOn && !latest ? (
        <div className="lt-sub enter px-5 py-2 text-sm text-muted">{seat === 'fan' ? 'Relator warming up: the first call comes with the first chance, goal or knock.' : 'Agents warming up: the first read comes with the first key moment.'}</div>
      ) : null}
    </div>
  )
}
