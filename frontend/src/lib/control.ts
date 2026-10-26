// Control room arithmetic: what the agent system cost and how it ran, read from the traces every message carries.
import type { FeedItem, VerdictItem } from './useMatchStream'
import type { TraceEvent } from './types'

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

/** One compact line for the guardrail verdicts of a moment: "guardrail: fan/es 99 %, analyst/en 12 % ungrounded". */
export function guardrailLine(trace: TraceEvent[] | undefined): { text: string; clean: boolean } | null {
  const gs = (trace ?? []).filter((e) => e.kind === 'guardrail')
  if (!gs.length) return null
  const who = (g: TraceEvent) => (g.profile ?? '').split(':').slice(0, 2).join('/') || 'viewer'
  const parts = gs.map((g) => (!g.checked ? `${who(g)} unchecked` : g.grounded ? `${who(g)} grounded` : `${who(g)} ${Math.round((g.ungrounded_percentage ?? 0) * 100)} %`))
  const clean = gs.every((g) => !g.checked || g.grounded)
  const anyUngrounded = gs.some((g) => g.checked && !g.grounded)
  return { text: `guardrail: ${parts.join(', ')}${anyUngrounded ? ' ungrounded' : ''}`, clean }
}

/** The Judge ran as the hosted Foundry agent when a verdict trace names it. */
export function hostedJudge(verdicts: VerdictItem[]): boolean {
  return verdicts.some((v) => (v.msg.trace ?? []).some((e) => e.agent === 'matchmind-judge'))
}
