import type { MatchEvent, Meta, Snapshot } from '../lib/types'

// Simulator coordinates are 0-100 on both axes; the drawing is 105 x 68 metres.
const W = 105, H = 68
const sx = (x: number) => (x / 100) * W
const sy = (y: number) => (y / 100) * H

type Props = { meta: Meta; trail: MatchEvent[]; lastEvent: MatchEvent | null; snapshot: Snapshot | null }

export function Pitch({ meta, trail, lastEvent, snapshot }: Props) {
  const color = (team?: string) => (team === meta.home_id ? 'var(--color-home)' : 'var(--color-away)')
  const shots = trail.filter((e) => e.type === 'shot')
  const passes = trail.filter((e) => e.type === 'pass' && typeof e.end_x === 'number')
  const others = trail.filter((e) => ['tackle', 'interception', 'foul'].includes(e.type))
  const ball = lastEvent && typeof lastEvent.x === 'number'
    ? { x: lastEvent.end_x ?? lastEvent.x, y: lastEvent.end_y ?? (lastEvent.y as number) }
    : null
  const homeRight = snapshot ? snapshot.period === 1 : true

  return (
    <section className="panel p-3">
      <svg viewBox={`-2 -2 ${W + 4} ${H + 4}`} className="w-full" role="img" aria-label="Pitch with the latest passes and shots">
        <rect x={0} y={0} width={W} height={H} fill="#12302a" stroke="#3b6b5c" strokeWidth={0.4} />
        {[0, 1, 2, 3, 4, 5].map((i) => <rect key={i} x={(i * W) / 6} y={0} width={W / 12} height={H} fill="#153429" />)}
        <line x1={W / 2} y1={0} x2={W / 2} y2={H} stroke="#3b6b5c" strokeWidth={0.3} />
        <circle cx={W / 2} cy={H / 2} r={9.15} fill="none" stroke="#3b6b5c" strokeWidth={0.3} />
        {[0, W].map((gx) => (
          <g key={gx}>
            <rect x={gx === 0 ? 0 : W - 16.5} y={H / 2 - 20.15} width={16.5} height={40.3} fill="none" stroke="#3b6b5c" strokeWidth={0.3} />
            <rect x={gx === 0 ? 0 : W - 5.5} y={H / 2 - 9.16} width={5.5} height={18.32} fill="none" stroke="#3b6b5c" strokeWidth={0.3} />
          </g>
        ))}

        {passes.map((e, i) => {
          const t = (i + 1) / passes.length
          return (
            <line key={e.event_id} x1={sx(e.x!)} y1={sy(e.y!)} x2={sx(e.end_x!)} y2={sy(e.end_y!)}
              stroke={color(e.team_id)} strokeWidth={0.35} strokeOpacity={0.15 + 0.6 * t}
              strokeDasharray={e.outcome === 'incomplete' ? '1 1' : undefined} />
          )
        })}
        {others.map((e) => (
          <rect key={e.event_id} x={sx(e.x!) - 0.7} y={sy(e.y!) - 0.7} width={1.4} height={1.4} fill={color(e.team_id)} fillOpacity={0.7} />
        ))}
        {shots.map((e) => (
          <g key={e.event_id}>
            <circle cx={sx(e.x!)} cy={sy(e.y!)} r={1 + (e.xg ?? 0) * 6} fill={color(e.team_id)} fillOpacity={0.35} stroke={color(e.team_id)} strokeWidth={0.3} />
            {e.outcome === 'goal' && <circle cx={sx(e.x!)} cy={sy(e.y!)} r={2.6 + (e.xg ?? 0) * 6} fill="none" stroke="var(--color-amber)" strokeWidth={0.5} />}
          </g>
        ))}
        {ball && <circle cx={sx(ball.x)} cy={sy(ball.y)} r={1.1} fill="#fff" stroke="#000" strokeWidth={0.2} />}

        <text x={1.5} y={H - 1.5} fontSize={3} fill={homeRight ? 'var(--color-home)' : 'var(--color-away)'} fontFamily="Barlow Condensed" fontWeight={600}>
          {(homeRight ? meta.teams[meta.home_id] : meta.teams[meta.away_id]).short_name} ▸
        </text>
        <text x={W - 1.5} y={H - 1.5} fontSize={3} textAnchor="end" fill={homeRight ? 'var(--color-away)' : 'var(--color-home)'} fontFamily="Barlow Condensed" fontWeight={600}>
          ◂ {(homeRight ? meta.teams[meta.away_id] : meta.teams[meta.home_id]).short_name}
        </text>
      </svg>
      <p className="mt-1 text-xs text-ink-3">
        {lastEvent ? `${lastEvent.clock} ${describe(lastEvent)}` : 'Waiting for kickoff'}
      </p>
    </section>
  )
}

export function describe(e: MatchEvent): string {
  switch (e.type) {
    case 'pass': return `${e.player_name} pass${e.outcome === 'incomplete' ? ' (incomplete)' : ''}`
    case 'shot': return `${e.player_name} shot, ${e.outcome}, xG ${e.xg?.toFixed(2)}`
    case 'goal': return `GOAL ${e.player_name}`
    case 'save': return `${e.player_name} save`
    case 'pressure': return `${e.player_name} presses`
    case 'tackle': case 'interception': case 'foul': return `${e.player_name} ${e.type}`
    case 'card': return `${e.card} card ${e.player_name}`
    case 'injury_concern': return `${e.player_name} ${e.detail}`
    case 'substitution': return `${e.player_on_name} on for ${e.player_off_name}${e.forced ? ' (coach)' : ''}`
    case 'physical_sample': return 'physical samples'
    case 'possession_change': return 'possession changes'
    case 'half_time': return 'half time'
    case 'full_time': return 'full time'
    case 'kickoff': case 'second_half_kickoff': return 'kick off'
    default: return e.type.replace('_', ' ')
  }
}
