import { describe, expect, it } from 'vitest'
import { cacheRate, feedTokens, fmtTokens, guardrailLine, hostedJudge, percentile, traceTokens } from './control'
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
    expect(guardrailLine(trace)).toEqual({ text: 'guardrail: commentator/es 99 %, analyst/en grounded ungrounded', clean: false })
    expect(guardrailLine([])).toBeNull()
  })

  it('detects the hosted Judge from the verdict trace', () => {
    const v = (agent: string) => ({ id: 'v', at: 0, msg: { kind: 'verdict', trace: [{ t: 1, kind: 'agent_end', agent }] } }) as unknown as VerdictItem
    expect(hostedJudge([v('Judge')])).toBe(false)
    expect(hostedJudge([v('matchmind-judge')])).toBe(true)
  })
})
