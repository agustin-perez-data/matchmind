import { useMemo } from 'react'
import { fanStats, playerEvents, ticker, touchPoints, type Touch } from '../lib/follow'
import { downloadPlayerCard } from '../lib/playerCard'
import type { FeedItem, VerdictItem } from '../lib/useMatchStream'
import type { InsightMsg, Meta, Snapshot } from '../lib/types'
import { Crest, onColor } from './Crest'
import { IconMic } from './icons'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  feed: FeedItem[]
  verdicts: VerdictItem[]
  touches: Touch[]
  language: 'en' | 'es'
  ended: boolean
  teamId: string | null
  favoritePlayerId: string | null
  onFavorite: (id: string | null) => void
}

/** The fan's own corner: pick a side (or stay neutral) and one player to follow; their match told the fan's way. */
export function YourSideBlock({ meta, snapshot, feed, verdicts, touches, language, ended, teamId, favoritePlayerId, onFavorite }: Props) {
  const allPlayers = useMemo(() => Object.values(meta.teams).flatMap((t) => t.players.map((p) => ({ ...p, team_id: t.team_id }))), [meta])
  const followedMeta = favoritePlayerId ? allPlayers.find((p) => p.player_id === favoritePlayerId) ?? null : null
  const followed = favoritePlayerId ? snapshot?.players[favoritePlayerId] ?? null : null
  const latestInsight = feed.find((f): f is FeedItem & { msg: InsightMsg } => f.msg.kind === 'insight') ?? null
  const note = latestInsight ? Object.values(latestInsight.msg.viewers)[0]?.decision?.personalized_note ?? null : null
  const mine = useMemo(() => (favoritePlayerId ? playerEvents(touches, favoritePlayerId) : []), [touches, favoritePlayerId])
  const stats = useMemo(() => (favoritePlayerId ? fanStats(touches, favoritePlayerId) : null), [touches, favoritePlayerId])
  const lines = useMemo(() => (favoritePlayerId ? ticker(touches, favoritePlayerId, meta, 6) : []), [touches, favoritePlayerId, meta])
  const sides = teamId ? [teamId] : [meta.home_id, meta.away_id]

  // the Analyst's eye: the latest pending forecast that names this player, and whether a verdict settled it
  const analystCall = favoritePlayerId && latestInsight?.msg.analyst?.forecast?.watch_player_id === favoritePlayerId ? latestInsight.msg : null
  const settled = analystCall ? verdicts.find((v) => v.msg.event_id === analystCall.event_id) ?? null : null
  const subbedOff = mine.find((e) => e.type === 'substitution' && e.player_off_id === favoritePlayerId) ?? null
  const subName = subbedOff?.player_on_id ? allPlayers.find((p) => p.player_id === subbedOff.player_on_id)?.name.split(' ').slice(-1)[0] ?? null : null
  // involvement: touches in the last 10 match minutes against the player's own pace over the match
  const nowMin = snapshot ? (snapshot.period === 2 ? Math.max(snapshot.minute, 45) : snapshot.minute) : 0
  const onBall = mine.filter((e) => e.player_id === favoritePlayerId && ['pass', 'shot', 'goal', 'tackle', 'interception'].includes(e.type))
  const recent = onBall.filter((e) => (e.period === 2 ? Math.max(e.minute, 45) : e.minute) >= nowMin - 10).length
  const pace = followed && followed.minutes_played > 0 ? (onBall.length / followed.minutes_played) * 10 : 0
  const involvement = !followed || !followed.on_pitch || followed.minutes_played < 10 ? null : recent >= pace * 1.3 ? 'in the game' : recent <= pace * 0.6 ? 'quiet spell' : 'steady'

  const download = () => {
    if (!followedMeta || !stats) return
    downloadPlayerCard({
      meta, team: meta.teams[followedMeta.team_id], name: followedMeta.name, position: followedMeta.position, shirt: followedMeta.shirt_number,
      minutes: followed?.minutes_played ?? 0, score: snapshot?.score ?? meta.score, stats, points: touchPoints(touches, followedMeta.player_id),
      moments: [...lines].reverse().filter((l) => l.big || lines.length <= 6).slice(0, 6).map((l) => ({ clock: l.clock, text: l.text })), language,
    })
  }

  return (
    <section className="blk px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Your side</h2>
        <span className="blk-meta">{teamId ? 'the commentary is on your side' : 'neutral: the commentary calls it straight'}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {teamId ? (() => { const t = meta.teams[teamId]; return (
          <span className="display inline-flex items-center gap-2 px-3 py-1.5 text-lg font-black uppercase tracking-wide" style={{ background: t.primary_color, color: onColor(t.primary_color) }}>
            <Crest team={t} size={26} />{t.name}
          </span>
        ) })() : (
          <span className="display inline-flex items-center gap-2 border border-white/20 px-3 py-1.5 text-lg font-black uppercase tracking-wide text-fg-2">Neutral <span className="text-[11px] font-semibold tracking-[0.2em] text-muted">just watching</span></span>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="display text-base font-extrabold uppercase tracking-wider text-fg-2">Follow one of {teamId ? 'yours' : 'them'}</h3>
        <span className="blk-meta text-[11px]">{followedMeta ? 'their touches light up on the pitch' : 'optional'}</span>
      </div>
      <div className="mt-2 grid gap-3 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="grid gap-3 sm:grid-cols-2">
          {sides.map((tid) => {
            const team = meta.teams[tid]
            const ink = tid === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'
            return (
              <div key={tid} className={sides.length === 1 ? 'sm:col-span-2' : ''}>
                {sides.length > 1 && <div className="display text-sm font-extrabold uppercase tracking-wider" style={{ color: ink }}>{team.name}</div>}
                <div className="mt-1.5 flex flex-wrap gap-1.5" role="radiogroup" aria-label={`${team.name} players`}>
                  {team.players.filter((p) => p.starter || snapshot?.players[p.player_id]?.on_pitch).map((p) => {
                    const on = p.player_id === favoritePlayerId
                    const off = snapshot ? snapshot.players[p.player_id]?.on_pitch === false : false
                    return (
                      <button key={p.player_id} type="button" role="radio" aria-checked={on} onClick={() => onFavorite(on ? null : p.player_id)}
                        className={`display flex items-center gap-1.5 px-2 py-1 text-sm font-bold uppercase tracking-wide transition-[background,color,transform] duration-150 active:scale-95 ${on ? 'bg-amber text-ink' : 'bg-white/5 text-fg-2 hover:bg-white/12 hover:text-fg'} ${off && !on ? 'opacity-45' : ''}`}>
                        <span className="tabular-nums" style={{ color: on ? undefined : ink }}>{p.shirt_number}</span>
                        {p.name.split(' ').slice(-1)[0]}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>

        <div className="lt-sub min-h-[120px] px-3 py-2">
          {followedMeta && stats ? (
            <div key={followedMeta.player_id} className="enter-fade">
              <div className="flex items-baseline justify-between gap-2">
                <div key={onBall.length} className="name-flash display text-2xl font-black uppercase leading-none">{followedMeta.name}</div>
                <button type="button" className="btn-quiet px-2 py-0.5 text-xs" onClick={() => onFavorite(null)}>Unfollow</button>
              </div>
              <div className="blk-meta mt-1">{followedMeta.position} · {followed ? (followed.on_pitch ? `${followed.minutes_played}' on the pitch` : 'off the pitch') : 'warming up'}{involvement ? <span className={involvement === 'in the game' ? 'text-teal' : involvement === 'quiet spell' ? 'text-muted' : 'text-fg-2'}> · {involvement}: {recent} touch{recent === 1 ? '' : 'es'} in the last 10'</span> : null}</div>
              {subbedOff && (
                <p className="mt-2 border-l-2 border-amber pl-2 text-sm text-fg-2">
                  Off at {subbedOff.clock}{subName ? `, ${subName} came on` : ''}. {ended ? 'Their card is ready below.' : 'Stay with their numbers, or'}
                  {!ended && subbedOff.player_on_id && <button type="button" className="btn ml-2 bg-amber px-2 py-0.5 text-xs" onClick={() => onFavorite(subbedOff.player_on_id!)}>follow {subName} instead</button>}
                </p>
              )}
              <dl className="mt-2 grid grid-cols-4 gap-x-2 gap-y-1 text-center">
                <Stat label="Touches" value={String(stats.touches)} />
                <Stat label="Shots" value={String(stats.shots)} />
                <Stat label="Goals" value={String(stats.goals)} hot={stats.goals > 0} />
                <Stat label="Assists" value={String(stats.assists)} hot={stats.assists > 0} />
                <Stat label="xG" value={stats.xg.toFixed(2)} />
                <Stat label="Key passes" value={String(stats.keyPasses)} />
                <Stat label="Duels won" value={String(stats.tackles + stats.interceptions)} />
                <Stat label="Pass acc." value={stats.passes ? `${Math.round((stats.passesCompleted / stats.passes) * 100)}%` : '–'} />
              </dl>
              {analystCall && (
                <p className="mt-2 flex gap-1.5 text-sm text-amber">
                  <span className="tag tag-w shrink-0 text-[10px]">Analyst</span>
                  <span>{settled ? (settled.msg.scores.watch === 1 ? `called it at ${analystCall.clock}: ${followedMeta.name.split(' ').slice(-1)[0]} got involved.` : `named ${followedMeta.name.split(' ').slice(-1)[0]} at ${analystCall.clock}, and was wrong.`) : `has an eye on ${followedMeta.name.split(' ').slice(-1)[0]} for the next 10 minutes too.`}</span>
                </p>
              )}
              {lines.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-sm">
                  {lines.map((l) => <li key={l.event_id} className={l.big ? 'font-semibold text-fg' : 'text-fg-2'}><span className="tabular-nums text-muted">{l.clock}</span> {l.text}</li>)}
                </ul>
              )}
              {lines.length === 0 && <p className="mt-2 text-sm text-muted">Nothing yet: the first touch shows up here.</p>}
              {note && <p className="mt-2 flex gap-1.5 text-sm text-fg-2"><IconMic /><span>{note}</span></p>}
              {ended && <button type="button" className="btn btn-teal mt-3 text-sm" onClick={download}>Download their card</button>}
            </div>
          ) : (
            <p className="text-sm text-muted">{teamId ? 'Pick one of your players: their touches light up on the pitch and their match is told here.' : 'Nobody followed. Pick a player from either side: their touches light up on the pitch and their match is told here.'}</p>
          )}
        </div>
      </div>
    </section>
  )
}

function Stat({ label, value, hot = false }: { label: string; value: string; hot?: boolean }) {
  return (
    <div>
      <dt className="blk-meta text-[10px]">{label}</dt>
      <dd className={`display text-xl font-extrabold tabular-nums ${hot ? 'text-amber' : ''}`}>{value}</dd>
    </div>
  )
}
