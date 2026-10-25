import type { FeedItem, VerdictItem } from '../lib/useMatchStream'
import type { Credibility, InsightMsg, Meta } from '../lib/types'
import { sentence, stamp } from './PitchStage'

type Props = { meta: Meta; feed: FeedItem[]; verdicts: VerdictItem[]; credibility: Credibility | null; agentsOn: boolean; ended: boolean }

/** The Analyst's current read, kept on screen: the tactical read in metres, the key number and the live call being graded. */
export function AnalystRead({ meta, feed, verdicts, credibility, agentsOn, ended }: Props) {
  const latest = feed.find((f): f is FeedItem & { msg: InsightMsg } => f.msg.kind === 'insight' && !!f.msg.analyst) ?? null
  const a = latest?.msg.analyst ?? null
  if (!latest || !a) {
    return (
      <section className="blk px-4 py-3">
        <div className="flex items-baseline justify-between"><h2 className="blk-title">Analyst's read</h2><span className="blk-meta">{agentsOn ? 'waiting' : 'agents off'}</span></div>
        <p className="mt-2 text-sm text-muted">{agentsOn ? 'The first read comes with the first key moment.' : 'Agents off: no reads are generated in this replay.'}</p>
      </section>
    )
  }
  const judged = new Set(verdicts.map((v) => v.msg.event_id))
  const forecast = a.forecast && latest.msg.moment.kind !== 'full_time' && !judged.has(latest.msg.event_id) ? a.forecast : null
  const issued = Number(latest.msg.clock.split(':')[0])
  const due = issued + (credibility?.horizon_min ?? 10)
  return (
    <section key={latest.id} className="blk enter px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Analyst's read</h2>
        <span className="blk-meta">{stamp(latest.msg)} · {sentence(a.headline)}</span>
      </div>
      <p className="display mt-2 text-lg font-semibold leading-snug sm:text-xl">{a.tactical_read}</p>
      {a.key_stat && <p className="mt-1 text-sm text-muted">{a.key_stat}</p>}
      {forecast && (
        <p className="mt-2 border-l-2 border-amber pl-2 text-sm text-amber">
          <b>Next 10' from {stamp(latest.msg)}:</b> {forecast.claim}
          <span className="text-muted"> · {meta.teams[forecast.dominant_team_id]?.short_name ?? forecast.dominant_team_id} to create more, goal {Math.round(forecast.goal_probability * 100)}%{ended ? ' · settling at full time' : ` · graded at ${due}'`}</span>
        </p>
      )}
    </section>
  )
}
