import type { FeedItem, VerdictItem } from '../lib/useMatchStream'
import type { Credibility, InsightMsg, Meta, Snapshot } from '../lib/types'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  feed: FeedItem[]
  verdicts: VerdictItem[]
  credibility: Credibility | null
  agentsOn: boolean
  ended: boolean
  compact?: boolean
}

const VERDICT: Record<string, { label: string; color: string }> = {
  called_it: { label: 'Called it', color: '#2dd4bf' },
  partly: { label: 'Partly', color: '#ffd166' },
  missed: { label: 'Missed', color: '#e8405a' },
}
const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)}%`)

/** The Analyst's 10-minute calls and what the Judge made of them: credibility earned, not asserted. */
export function ForecastLedger({ meta, snapshot, feed, verdicts, credibility, agentsOn, ended, compact = false }: Props) {
  const judgedIds = new Set(verdicts.map((v) => v.msg.event_id))
  const pending = feed
    .filter((f): f is FeedItem & { msg: InsightMsg } => f.msg.kind === 'insight' && !!f.msg.analyst?.forecast && f.msg.moment.kind !== 'full_time' && !judgedIds.has(f.msg.event_id))
    .slice(0, compact ? 2 : 4)
  const minute = snapshot ? Math.max(snapshot.minute, snapshot.period === 2 ? 45 : 0) : 0
  const a = credibility?.analyst.overall, n = credibility?.naive.overall
  const beats = a != null && n != null ? a - n : null

  return (
    <section className="blk px-4 py-3" style={{ borderTopColor: '#ffd166' }}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Analyst credibility</h2>
        <span className="blk-meta">{credibility?.judged ? `${credibility.judged} call${credibility.judged > 1 ? 's' : ''} graded` : agentsOn ? 'graded 10 minutes after each call' : 'agents off'}</span>
      </div>

      <div className="mt-2 grid grid-cols-[auto_1fr] items-end gap-x-4">
        <div className="display text-[44px] font-black leading-none tabular-nums" style={{ color: beats == null ? 'var(--color-fg)' : beats >= 0 ? 'var(--color-teal)' : 'var(--color-bad)' }}>{pct(a)}</div>
        <div className="pb-1 text-sm text-fg-2">
          {credibility?.judged
            ? <>forecast score, vs <b className="text-fg">{pct(n)}</b> for a naive call (the xG leader keeps dominating, base-rate goal odds, the top shooter so far), on the same windows.</>
            : <>Every Analyst read ends with a call for the next 10 minutes: who creates more, the odds of a goal, who to watch. Code grades it against what happens; the Judge explains.</>}
        </div>
      </div>
      {credibility?.judged ? (
        <dl className="mt-2 grid grid-cols-3 gap-2 text-center">
          <Part label="Who dominates" a={credibility.analyst.dominance} n={credibility.naive.dominance} />
          <Part label="Goal odds" a={credibility.analyst.goal} n={credibility.naive.goal} />
          <Part label="Player to watch" a={credibility.analyst.watch} n={credibility.naive.watch} />
        </dl>
      ) : null}

      <ul className="scroll-quiet mt-3 max-h-[380px] space-y-2 overflow-auto">
        {pending.map((f) => {
          const fc = f.msg.analyst!.forecast!
          const issued = Number(f.msg.clock.split(':')[0])
          const left = Math.max(0, issued + 10 - minute)
          return (
            <li key={f.id} className="enter border-l-2 border-white/25 pl-3">
              <div className="blk-meta text-[11px]">{f.msg.clock} · pending{snapshot ? (ended ? ' · settling at full time' : ` · graded in ${left}'`) : ''}</div>
              <div className="text-sm text-fg-2">{fc.claim}</div>
              <div className="text-xs text-muted">{meta.teams[fc.dominant_team_id]?.short_name ?? fc.dominant_team_id} to create more · goal {pct(fc.goal_probability)}{fc.watch_player_id ? ` · watch ${nameOf(meta, fc.watch_player_id)}` : ''}</div>
            </li>
          )
        })}
        {verdicts.slice(0, compact ? 3 : 8).map((v) => {
          const m = v.msg
          const tag = VERDICT[m.verdict.verdict]
          const xg = Object.entries(m.facts.xg_gained).map(([tid, g]) => `${meta.teams[tid]?.short_name ?? tid} ${g.toFixed(2)}`).join(' v ')
          return (
            <li key={v.id} className="enter border-l-2 pl-3" style={{ borderColor: tag.color }}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="blk-meta text-[11px]">{m.issued_clock} · next 10'{m.facts.truncated ? `, cut at full time (${m.facts.minutes}')` : ''}</span>
                <span className="display text-sm font-extrabold uppercase tracking-wider" style={{ color: tag.color }}>{tag.label} · {pct(m.scores.overall)}</span>
              </div>
              <div className="text-sm text-fg-2"><span className="text-muted">Call:</span> {m.forecast.claim}</div>
              <div className="text-xs text-muted">Happened: xG {xg}, {m.facts.goals.length} goal{m.facts.goals.length === 1 ? '' : 's'}, {m.facts.shots} shot{m.facts.shots === 1 ? '' : 's'}{m.forecast.watch_player ? `, ${m.forecast.watch_player} ${m.scores.watch === 1 ? 'involved' : 'not involved'}` : ''}</div>
              {!compact && m.verdict.summary && <div className="mt-0.5 text-sm"><span className="tag mr-1.5 text-[11px]">Judge</span>{m.verdict.summary}{m.verdict.lesson && m.verdict.lesson.toLowerCase() !== 'nothing' ? <span className="text-muted"> {m.verdict.lesson}</span> : null}</div>}
            </li>
          )
        })}
        {pending.length === 0 && verdicts.length === 0 && <li className="text-sm text-muted">{agentsOn ? 'The first call comes with the first key moment.' : 'Turn the agents on to see forecasts graded.'}</li>}
      </ul>
    </section>
  )
}

function Part({ label, a, n }: { label: string; a: number | null; n: number | null }) {
  return (
    <div className="border-t border-line pt-1">
      <dt className="blk-meta text-[10px]">{label}</dt>
      <dd className="display text-xl font-extrabold tabular-nums">{pct(a)} <span className="text-sm font-semibold text-muted">vs {pct(n)}</span></dd>
    </div>
  )
}

function nameOf(meta: Meta, id: string): string {
  for (const t of Object.values(meta.teams)) {
    const p = t.players.find((x) => x.player_id === id)
    if (p) return p.name.split(' ').slice(-1)[0]
  }
  return id
}
