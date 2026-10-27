import { describe, expect, it } from 'vitest'
import { cacheRate, correctedCount, explainedLine, feedTokens, fmtTokens, guardrailLine, hostedJudge, isInterrupt, percentile, traceTokens } from './control'
import type { FeedItem, VerdictItem } from './useMatchStream'
import type { TraceEvent } from './types'

const trace: TraceEvent[] = [
  { t: 0, kind: 'agent_start', agent: 'Analyst' },
  { t: 900, kind: 'agent_end', agent: 'Analyst', tokens: { input: 1200, output: 150 } },
  { t: 950, kind: 'agent_end', agent: 'Narrator', tokens: { input: 300, output: null } },
  { t: 960, kind: 'guardrail', agent: 'Narrator', profile: 'commentator:es:-:THU', checked: true, grounded: false, ungrounded_percentage: 0.99 },
  { t: 961, kind: 'guardrail', agent: 'Narrator', profile: 'analyst:en:-', checked: true, grounded: true, ungrounded_percentage: 0 },
]

const item = (cached: boolean | undefined, kind: 'insight' | 'coach' = 'insight') =>
  ({ id: `${kind}-${Math.random()}`, at: 0, msg: { kind, cached, trace } }) as unknown as FeedItem

describe('control room arithmetic', () => {
  it('sums tokens on agent_end events only', () => {
    expect(traceTokens(trace)).toBe(1650)
    expect(traceTokens(undefined)).toBe(0)
  })

  it('counts tokens for fresh messages, never for cached ones', () => {
    const feed = [item(false), item(true), item(undefined, 'coach')]
    expect(feedTokens(feed)).toBe(3300)
    const verdicts = [{ id: 'v', at: 0, msg: { kind: 'verdict', cached: false, trace } }] as unknown as VerdictItem[]
    expect(feedTokens(feed, verdicts)).toBe(4950)
  })

  it('cache rate over feed and verdicts', () => {
    expect(cacheRate([item(true), item(false), item(true)])).toEqual({ hits: 2, total: 3, rate: 2 / 3 })
    expect(cacheRate([]).rate).toBeNull()
  })

  it('nearest-rank percentile', () => {
    expect(percentile([5, 1, 9, 3], 50)).toBe(3)
    expect(percentile([5, 1, 9, 3], 95)).toBe(9)
    expect(percentile([], 95)).toBeNull()
  })

  it('formats tokens compactly', () => {
    expect(fmtTokens(850)).toBe('850')
    expect(fmtTokens(1700)).toBe('1.7k')
    expect(fmtTokens(12400)).toBe('12k')
  })

  it('one guardrail line per moment, naming the viewer', () => {
    expect(guardrailLine(trace)).toEqual({ text: 'fact check: commentator/es/THU 99 % not backed by the facts, analyst/en all backed', clean: false })
    expect(guardrailLine([])).toBeNull()
  })

  it('detects the hosted Judge from the verdict trace', () => {
    const v = (agent: string) => ({ id: 'v', at: 0, msg: { kind: 'verdict', trace: [{ t: 1, kind: 'agent_end', agent }] } }) as unknown as VerdictItem
    expect(hostedJudge([v('Judge')])).toBe(false)
    expect(hostedJudge([v('matchmind-judge')])).toBe(true)
  })
})

describe('lane accounting, Director corrections and loudness', () => {
  const insight = (viewers: Record<string, unknown>) => ({ kind: 'insight', viewers }) as never

  it('reports skipped moments only when the lane dropped some', () => {
    expect(explainedLine(3, { insight: { offered: 8, started: 3, dropped: 5 } })).toEqual({ value: '3 of 8', sub: '5 skipped at this speed' })
    expect(explainedLine(3, { insight: { offered: 3, started: 3, dropped: 0 } })).toBeNull()
    expect(explainedLine(3, null)).toBeNull()
  })

  it('counts corrected decisions across the feed', () => {
    const feed = [
      { id: 'a', at: 0, msg: insight({ x: { decision: { enforced: true } }, y: { decision: { enforced: false } } }) },
      { id: 'b', at: 0, msg: insight({ x: { decision: { enforced: true } } }) },
      { id: 'c', at: 0, msg: { kind: 'coach' } },
    ] as unknown as FeedItem[]
    expect(correctedCount(feed)).toBe(2)
  })

  it('a moment is loud when the Director says so, and when the flag is missing (older cached results)', () => {
    expect(isInterrupt(insight({ a: { interrupt: true } }))).toBe(true)
    expect(isInterrupt(insight({ a: { interrupt: false } }))).toBe(false)
    expect(isInterrupt(insight({ a: {} }))).toBe(true)
    expect(isInterrupt(null)).toBe(false)
  })
})
