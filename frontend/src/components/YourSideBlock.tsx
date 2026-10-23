import type { FeedItem } from '../lib/useMatchStream'
import type { Meta, Snapshot } from '../lib/types'
import { Crest, onColor } from './Crest'
import { IconMic } from './icons'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  latest: FeedItem | null
  teamId: string | null
  onTeam: (id: string | null) => void
  favoritePlayerId: string | null
  onFavorite: (id: string | null) => void
}

/** The fan's own corner: pick a side (or stay neutral) and, if you like, one player of yours to follow. */
export function YourSideBlock({ meta, snapshot, latest, teamId, onTeam, favoritePlayerId, onFavorite }: Props) {
  const home = meta.teams[meta.home_id], away = meta.teams[meta.away_id]
  const followed = favoritePlayerId ? snapshot?.players[favoritePlayerId] ?? null : null
  const followedMeta = favoritePlayerId ? Object.values(meta.teams).flatMap((t) => t.players).find((p) => p.player_id === favoritePlayerId) : null
  const note = latest?.msg.kind === 'insight' ? Object.values(latest.msg.viewers)[0]?.decision?.personalized_note ?? null : null
  const sides = teamId ? [teamId] : [meta.home_id, meta.away_id]
  const pick = (id: string | null) => {
    onTeam(id)
    if (id && followedMeta && meta.teams[id].players.every((p) => p.player_id !== followedMeta.player_id)) onFavorite(null) // your player must be one of yours
  }

  return (
    <section className="blk px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Your side</h2>
        <span className="blk-meta">{teamId ? 'the commentary is on your side' : 'neutral: the commentary calls it straight'}</span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2" role="radiogroup" aria-label="your side">
        {[home, null, away].map((t) => {
          const id = t?.team_id ?? null
          const on = teamId === id
          const style = on && t ? { background: t.primary_color, color: onColor(t.primary_color), boxShadow: `0 0 0 3px ${t.primary_color}66` } : on ? { background: '#fff', color: '#0b0f1a' } : undefined
          return (
            <button key={id ?? 'neutral'} type="button" role="radio" aria-checked={on} onClick={() => pick(id)}
              className={`display flex items-center justify-center gap-2 px-2 py-2.5 text-base font-black uppercase tracking-wide transition-[background,color,opacity] duration-150 ${on ? '' : 'bg-white/5 text-fg-2 hover:bg-white/12 hover:text-fg'}`} style={style}>
              {t ? <><Crest team={t} size={26} />{t.short_name}</> : 'Neutral'}
            </button>
          )
        })}
      </div>

      <div className="mt-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="display text-base font-extrabold uppercase tracking-wider text-fg-2">Follow one of {teamId ? 'yours' : 'them'}</h3>
        <span className="blk-meta text-[11px]">{followed ? 'the commentary leans towards them' : 'optional'}</span>
      </div>
      <div className="mt-2 grid gap-3 lg:grid-cols-[minmax(0,1fr)_300px]">
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

        <div className="lt-sub min-h-[96px] px-3 py-2">
          {followedMeta ? (
            <div key={followedMeta.player_id} className="enter-fade">
              <div className="flex items-baseline justify-between gap-2">
                <div className="display text-2xl font-black uppercase leading-none">{followedMeta.name}</div>
                <button type="button" className="btn-quiet px-2 py-0.5 text-xs" onClick={() => onFavorite(null)}>Unfollow</button>
              </div>
              <div className="blk-meta mt-1">{followedMeta.position} · {followed ? (followed.on_pitch ? `${followed.minutes_played}' on the pitch` : 'off the pitch') : 'warming up'}</div>
              {note && <p className="mt-2 flex gap-1.5 text-sm text-fg-2"><IconMic /><span>{note}</span></p>}
            </div>
          ) : (
            <p className="text-sm text-muted">{teamId ? 'Pick one of your players and the commentary keeps an eye on them for you.' : 'Nobody followed. Pick a player from either side and the commentary keeps an eye on them for you.'}</p>
          )}
        </div>
      </div>
    </section>
  )
}
