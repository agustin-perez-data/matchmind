import { sentence } from './PitchStage'
import type { Seat } from '../lib/seats'
import type { FeedItem } from '../lib/useMatchStream'
import type { MatchEvent, Meta } from '../lib/types'
import { describe } from './PitchStage'

type Props = { meta: Meta; feed: FeedItem[]; keyEvents: MatchEvent[]; agentsOn: boolean; seat: Seat }

/** Earlier moments, compact and seat-aware: what the agents said and the key events, newest first. */
export function MomentsRail({ meta, feed, keyEvents, agentsOn, seat }: Props) {
  const earlier = feed.slice(1).filter((f) => (seat === 'bench' ? true : f.msg.kind === 'insight')).slice(0, 12)
  return (
    <details className="blk px-4 py-2 text-sm">
      <summary className="display cursor-pointer text-base font-extrabold uppercase tracking-wider text-fg-2">
        Earlier moments <span className="blk-meta ml-2 normal-case">{agentsOn ? `${feed.length} agent calls` : 'agents off'} · {keyEvents.length} key events</span>
      </summary>
      <div className="scroll-quiet mt-2 grid max-h-64 gap-2 overflow-auto lg:grid-cols-2">
        {earlier.map((f) => {
          const m = f.msg
          if (m.kind === 'insight') {
            const v = Object.values(m.viewers)[0]
            const body = seat === 'fan' ? v?.narration?.text : m.analyst ? `${sentence(m.analyst.headline)} ${m.analyst.why_it_matters}` : v?.narration?.text
            return <article key={f.id} className="border-l-2 border-white/20 pl-3"><div className="blk-meta text-[11px]">{m.clock} · {m.moment.kind.replace('_', ' ')}</div><div className="font-semibold">{v?.decision?.headline ?? m.moment.summary}</div>{body && <div className="text-fg-2">{body}</div>}</article>
          }
          return <article key={f.id} className="border-l-2 border-teal/60 pl-3"><div className="blk-meta text-[11px]">{m.clock} · coach</div><div className="font-semibold">{m.proposal ? (m.proposal.action === 'hold' ? 'Held' : `${m.proposal.action} at ${m.proposal.minute}'`) : 'no decision'}</div>{m.branch && <div className="text-fg-2">What-if {m.branch.branch.score[meta.home_id]}-{m.branch.branch.score[meta.away_id]}, knocks {m.branch.actual.injury_concerns_total} to {m.branch.branch.injury_concerns_total}</div>}</article>
        })}
        <ul className="lg:col-span-2">
          {keyEvents.filter((e) => e.type !== 'shot' || seat !== 'fan').slice(0, 24).map((e) => (
            <li key={e.event_id} className={`py-0.5 ${e.type === 'goal' ? 'text-amber' : 'text-fg-2'}`}>
              <span className="tabular-nums text-muted">{e.clock}</span> {e.team_id ? <span style={{ color: e.team_id === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)' }}>{meta.teams[e.team_id]?.short_name}</span> : null} {describe(e)}
            </li>
          ))}
        </ul>
      </div>
    </details>
  )
}
