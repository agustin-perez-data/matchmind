// Control room arithmetic: what the agent system cost and how it ran, read from the traces every message carries.
import type { FeedItem, VerdictItem } from './useMatchStream'
import type { InsightMsg, Lanes, TraceEvent } from './types'

export type Health = {
  status: string
  ready: boolean
  draining?: boolean
  matches: number
  agents: boolean
  coach: boolean
  judge: boolean
  auth: string | null
  project: boolean
  telemetry: boolean
  speech: boolean
  live_sessions: number
  replica: string | null
  revision: string | null
  cache: { hits: number; misses: number; entries: number } | null
  judge_hosted?: boolean
}

/** Input + output tokens recorded on agent_end events of one trace. */
export function traceTokens(trace: TraceEvent[] | undefined): number {
  let n = 0
  for (const e of trace ?? []) {
    if (e.kind === 'agent_end' && e.tokens) n += (e.tokens.input ?? 0) + (e.tokens.output ?? 0)
  }
  return n
}

/** Tokens over every traced message of the feed (cached moments cost nothing: their trace is the original run's). */
export function feedTokens(feed: FeedItem[], verdicts: VerdictItem[] = []): number {
  const fresh = feed.filter((f) => !f.msg.cached)
  return fresh.reduce((n, f) => n + traceTokens(f.msg.trace), 0) + verdicts.filter((v) => !v.msg.cached).reduce((n, v) => n + traceTokens(v.msg.trace), 0)
}

/** Cache hit rate over the messages that could have been cached (insights, coach, verdicts). */
export function cacheRate(feed: FeedItem[], verdicts: VerdictItem[] = []): { hits: number; total: number; rate: number | null } {
  const items = [...feed.map((f) => f.msg.cached), ...verdicts.map((v) => v.msg.cached)]
  const hits = items.filter(Boolean).length
  return { hits, total: items.length, rate: items.length ? hits / items.length : null }
}

/** Nearest-rank percentile; null when empty. */
export function percentile(xs: number[], p: number): number | null {
  if (!xs.length) return null
  const sorted = [...xs].sort((a, b) => a - b)
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))]
}

export function fmtTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n)
}

/** One plain line for the fact check of a moment: "fact check: commentator/es 34 % not backed by the facts, analyst/en all backed". */
export function guardrailLine(trace: TraceEvent[] | undefined): { text: string; clean: boolean } | null {
  const gs = (trace ?? []).filter((e) => e.kind === 'guardrail')
  if (!gs.length) return null
  const who = (g: TraceEvent) => {
    const [mode, lang, , team] = (g.profile ?? '').split(':')
    return [mode, lang, team].filter((x) => x && x !== '-').join('/') || 'viewer'
  }
  const parts = gs.map((g) => (!g.checked ? `${who(g)} not checked` : g.grounded ? `${who(g)} all backed` : `${who(g)} ${Math.round((g.ungrounded_percentage ?? 0) * 100)} % not backed by the facts`))
  const clean = gs.every((g) => !g.checked || g.grounded)
  return { text: `fact check: ${parts.join(', ')}`, clean }
}

/** The Judge ran as the hosted Foundry agent when a verdict trace names it. */
export function hostedJudge(verdicts: VerdictItem[]): boolean {
  return verdicts.some((v) => (v.msg.trace ?? []).some((e) => e.agent === 'matchmind-judge'))
}

/** "3 of 8" when the moments lane dropped some under load; null when nothing was dropped (the plain count is honest). */
export function explainedLine(explained: number, lanes: Lanes | null): { value: string; sub: string } | null {
  const lane = lanes?.insight
  if (!lane || lane.dropped <= 0) return null
  const total = explained + lane.dropped
  return { value: `${explained} of ${total}`, sub: `${lane.dropped} skipped at this speed` }
}

/** How many Director decisions in the feed the house rules corrected. */
export function correctedCount(feed: FeedItem[]): number {
  let n = 0
  for (const f of feed) {
    if (f.msg.kind !== 'insight') continue
    for (const v of Object.values(f.msg.viewers)) if (v.decision?.enforced) n++
  }
  return n
}

/** Does this moment interrupt the broadcast for its first viewer? Results cached before the flag existed count as yes. */
export function isInterrupt(insight: InsightMsg | null | undefined): boolean {
  if (!insight) return false
  const v = Object.values(insight.viewers)[0]
  return v?.interrupt ?? true
}
