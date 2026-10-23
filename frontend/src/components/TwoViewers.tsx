import type { FeedItem } from '../lib/useMatchStream'
import type { InsightMsg, Meta } from '../lib/types'
import { IconMic } from './icons'

const CARDS = ['narration', 'insight', 'risk', 'stat'] as const
const MODE_LABEL: Record<string, string> = { commentator: 'Fan', casual: 'Casual', analyst: 'Analyst', player_focus: 'Follower' }
const MODE_COLOR: Record<string, string> = { commentator: '#ffffff', casual: '#ffffff', analyst: '#ffd166', player_focus: '#ffffff' }

/** The same key moment, as two viewers received it: what the Narrator said to each and what the Director let through. */
export function TwoViewers({ meta, feed }: { meta: Meta; feed: FeedItem[] }) {
  const latest = feed.find((f): f is FeedItem & { msg: InsightMsg } => f.msg.kind === 'insight' && Object.keys(f.msg.viewers).length >= 2)
  const n = latest ? Object.keys(latest.msg.viewers).length : 2
  const who = (p: { mode: string; team_id?: string | null }) => p.team_id ? `${meta.teams[p.team_id]?.short_name ?? p.team_id} fan` : MODE_LABEL[p.mode] ?? p.mode
  const tint = (p: { mode: string; team_id?: string | null }) => p.team_id ? meta.teams[p.team_id]?.primary_color ?? '#fff' : MODE_COLOR[p.mode] ?? '#fff'
  return (
    <section className="blk px-4 py-3" style={{ borderTopColor: '#c084fc' }}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Same moment, {n === 2 ? 'two' : n === 3 ? 'three' : n} viewers</h2>
        <span className="blk-meta">{latest ? `${latest.msg.clock} · ${latest.msg.moment.kind.replace('_', ' ')}` : 'the Director decides per seat'}</span>
      </div>
      {!latest ? (
        <p className="mt-2 text-sm text-muted">One Analyst read, one Narrator line per viewer, one Director decision per viewer. The first comparison appears with the first key moment.</p>
      ) : (
        <>
          <p className="mt-2 text-sm text-fg-2"><span className="tag tag-w mr-1.5 text-[11px]">Analyst</span>{latest.msg.analyst?.headline}</p>
          <div className={`mt-3 grid gap-3 ${n >= 3 ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
            {Object.values(latest.msg.viewers).slice(0, 3).map((v) => {
              const d = v.decision
              const shown = new Set(d?.show ?? [])
              const color = tint(v.profile)
              return (
                <article key={v.profile.mode + v.profile.language + (v.profile.team_id ?? '')} className="enter border-l-2 pl-3" style={{ borderColor: color }}>
                  <div className="display text-lg font-black uppercase leading-none" style={{ color }}>
                    {who(v.profile)} <span className="text-sm font-bold text-muted">{v.profile.language.toUpperCase()}{d ? ` · priority ${d.priority}` : ''}</span>
                  </div>
                  {d?.headline && <div className="lt-bar mt-2 inline-block px-3 py-0.5 text-lg">{d.headline}</div>}
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {CARDS.map((c) => (
                      <span key={c} className={`display px-2 py-0.5 text-[11px] font-extrabold uppercase tracking-wider ${shown.has(c) ? 'bg-white text-ink' : 'border border-white/20 text-muted line-through'}`}>{c}</span>
                    ))}
                  </div>
                  {v.narration?.text && <p className="mt-2 flex gap-1.5 text-sm text-fg-2"><IconMic /><span>{v.narration.text}</span></p>}
                  {d?.personalized_note && <p className="mt-1 text-sm text-amber">{d.personalized_note}</p>}
                </article>
              )
            })}
          </div>
        </>
      )}
    </section>
  )
}
