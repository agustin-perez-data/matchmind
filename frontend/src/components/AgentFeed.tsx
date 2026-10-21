import type { FeedItem } from '../lib/useMatchStream'
import type { BranchSummary, CoachMsg, InsightMsg, MatchEvent, Meta } from '../lib/types'
import { describe } from './Pitch'

type Props = {
  meta: Meta
  feed: FeedItem[]
  keyEvents: MatchEvent[]
  agentsOn: boolean
  coachOn: boolean
  onShowBranch: (b: BranchSummary) => void
}

export function AgentFeed({ meta, feed, keyEvents, agentsOn, coachOn, onShowBranch }: Props) {
  return (
    <section className="panel flex max-h-[70vh] flex-col p-3 lg:max-h-[62vh]">
      <div className="flex items-baseline justify-between">
        <h2 className="panel-title">Agents</h2>
        <span className="text-xs text-ink-3">{agentsOn ? 'Analyst, Narrator, Director' : 'narration agents off'}{coachOn ? ' and Coach' : ''}</span>
      </div>
      <div className="scroll-quiet mt-2 flex-1 overflow-auto pr-1">
        {feed.length === 0 && (
          <p className="text-sm text-ink-3">Agents wake up on key moments (goals, big chances, knocks). The first card arrives a few seconds after the first one.</p>
        )}
        {feed.map((f) => (f.msg.kind === 'insight'
          ? <InsightCard key={f.id} meta={meta} m={f.msg} />
          : <CoachCard key={f.id} meta={meta} m={f.msg} onShowBranch={onShowBranch} />))}
      </div>
      <details className="mt-2 border-t border-line pt-2 text-sm">
        <summary className="cursor-pointer text-ink-2">Key events ({keyEvents.length})</summary>
        <ul className="scroll-quiet mt-1 max-h-40 overflow-auto">
          {keyEvents.map((e) => (
            <li key={e.event_id} className={`py-0.5 ${e.type === 'goal' ? 'text-amber' : 'text-ink-2'}`}>
              <span className="tabular-nums text-ink-3">{e.clock}</span> {e.team_id ? <span style={{ color: e.team_id === meta.home_id ? 'var(--color-home)' : 'var(--color-away)' }}>{meta.teams[e.team_id]?.short_name}</span> : null} {describe(e)}
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}

function InsightCard({ meta, m }: { meta: Meta; m: InsightMsg }) {
  const v = Object.values(m.viewers)[0]
  const d = v?.decision, n = v?.narration, a = m.analyst
  const top = d?.priority === 5
  const show = new Set(d?.show ?? ['narration', 'insight'])
  const team = (m.moment.summary.match(/\b(THU|NBF|IRA|MRV|CRC|ALV|SGW|KPF)\b/) ?? [])[1]
  return (
    <article className="border-t border-line py-3 first:border-t-0 first:pt-0">
      <div className="flex items-baseline gap-2 text-xs text-ink-3">
        <span className="tabular-nums text-ink-2">{m.clock}</span>
        <span>{m.moment.kind.replace('_', ' ')}{team ? `, ${meta.teams[team]?.short_name ?? team}` : ''}</span>
        <span className="ml-auto">{(m.latency_ms / 1000).toFixed(1)}s</span>
      </div>
      {d && <h3 className={`display mt-0.5 text-xl font-semibold leading-tight ${top ? 'text-amber' : ''}`}>{d.headline}</h3>}
      {n && show.has('narration') && <p className="mt-1 text-[15px] leading-snug">{n.text}</p>}
      {a && show.has('insight') && (
        <p className="mt-1 text-sm text-ink-2"><span className="text-ink">{a.headline}.</span> {a.why_it_matters} {a.tactical_read}</p>
      )}
      {a && show.has('stat') && <p className="mt-1 text-xs text-ink-3">{a.key_stat}</p>}
      {d?.personalized_note && <p className="mt-1 text-sm text-good">{d.personalized_note}</p>}
      {m.errors.length > 0 && <p className="mt-1 text-xs text-bad">{m.errors.join('; ')}</p>}
    </article>
  )
}

function CoachCard({ meta, m, onShowBranch }: { meta: Meta; m: CoachMsg; onShowBranch: (b: BranchSummary) => void }) {
  const p = m.proposal, b = m.branch
  const h = meta.home_id, a = meta.away_id
  const what = !p ? 'no decision' : p.action === 'hold' ? 'Hold, no change'
    : p.action === 'substitution' ? `Substitute ${nameOf(meta, p.player_off_id)} at ${p.minute}'`
      : `Change tactics at ${p.minute}' (press ${p.press_intensity ?? 'same'}, ${p.style ?? 'same style'})`
  return (
    <article className="border-t border-line py-3 first:border-t-0 first:pt-0">
      <div className="flex items-baseline gap-2 text-xs text-ink-3">
        <span className="tabular-nums text-ink-2">{m.clock}</span>
        <span><span className="text-good">Coach</span>, {m.trigger === 'injury_concern' ? `${m.player.name} picked up a knock` : `risk window for ${m.player.name}`}</span>
        <span className="ml-auto">{(m.latency_ms / 1000).toFixed(1)}s</span>
      </div>
      <h3 className="display mt-0.5 text-xl font-semibold leading-tight text-good">{what}</h3>
      {p && <p className="mt-1 text-sm text-ink-2">{p.rationale}</p>}
      {b && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span>Actual <b className="tabular-nums">{b.actual.score[h]}:{b.actual.score[a]}</b></span>
          <span>What-if <b className="tabular-nums">{b.branch.score[h]}:{b.branch.score[a]}</b></span>
          <span className="text-ink-2">knocks {b.actual.injury_concerns_total} → {b.branch.injury_concerns_total}</span>
          <button className="btn-quiet ml-auto" onClick={() => onShowBranch(b)}>Show the branch</button>
        </div>
      )}
      {m.errors.length > 0 && <p className="mt-1 text-xs text-bad">{m.errors.join('; ')}</p>}
    </article>
  )
}

export function nameOf(meta: Meta, playerId: string | null | undefined): string {
  if (!playerId) return '?'
  for (const t of Object.values(meta.teams)) {
    const p = t.players.find((x) => x.player_id === playerId)
    if (p) return p.name
  }
  return playerId
}
