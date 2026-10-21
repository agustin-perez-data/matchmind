import type { FeedItem } from '../lib/useMatchStream'
import type { Meta, Snapshot } from '../lib/types'
import { IconMic } from './icons'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  latest: FeedItem | null
  favoritePlayerId: string | null
  onFavorite: (id: string | null) => void
}

/** The fan's own camera: pick one player and the commentary leans towards them. */
export function FollowBlock({ meta, snapshot, latest, favoritePlayerId, onFavorite }: Props) {
  const followed = favoritePlayerId ? snapshot?.players[favoritePlayerId] ?? null : null
  const followedMeta = favoritePlayerId ? Object.values(meta.teams).flatMap((t) => t.players).find((p) => p.player_id === favoritePlayerId) : null
  const note = latest?.msg.kind === 'insight' ? Object.values(latest.msg.viewers)[0]?.decision?.personalized_note ?? null : null
  const sides = [meta.home_id, meta.away_id] as const

  return (
    <section className="blk px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Follow a player</h2>
        <span className="blk-meta">{followed ? 'the commentary leans towards them' : 'tap a name, the commentary leans towards them'}</span>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_300px]">
        {sides.map((tid) => {
          const team = meta.teams[tid]
          const ink = tid === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'
          return (
            <div key={tid}>
              <div className="display text-sm font-extrabold uppercase tracking-wider" style={{ color: ink }}>{team.name}</div>
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

        <div className="lt-sub min-h-[120px] px-3 py-2">
          {followedMeta ? (
            <div key={followedMeta.player_id} className="enter-fade">
              <div className="flex items-baseline justify-between gap-2">
                <div className="display text-2xl font-black uppercase leading-none">{followedMeta.name}</div>
                <button type="button" className="btn-quiet px-2 py-0.5 text-xs" onClick={() => onFavorite(null)}>Unfollow</button>
              </div>
              <div className="blk-meta mt-1">{followedMeta.position} · {followed ? (followed.on_pitch ? `${followed.minutes_played}' on the pitch` : 'off the pitch') : 'warming up'}</div>
              {followed && (
                <dl className="mt-2 grid grid-cols-3 gap-2 text-center">
                  <Stat label="Sprints" value={String(followed.sprints)} />
                  <Stat label="Distance" value={`${(followed.distance_m / 1000).toFixed(1)} km`} />
                  <Stat label="Top speed" value={`${followed.top_speed_kmh.toFixed(0)} km/h`} />
                </dl>
              )}
              {note && <p className="mt-2 flex gap-1.5 text-sm text-fg-2"><IconMic /><span>{note}</span></p>}
            </div>
          ) : (
            <p className="text-sm text-muted">Nobody followed. The commentator calls the whole match; pick a player and the Narrator and Director keep an eye on them for you.</p>
          )}
        </div>
      </div>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="blk-meta text-[10px]">{label}</dt>
      <dd className="display text-xl font-extrabold tabular-nums">{value}</dd>
    </div>
  )
}
