import { describe, expect, it } from 'vitest'
import { staffReportHtml, warningSummary } from './staffReport'
import type { Meta, RiskMsg } from './types'

const meta = { match_id: 'THU-NBF-40', home_id: 'THU', away_id: 'NBF', teams: { THU: { name: 'Thames United', short_name: 'Thames' }, NBF: { name: 'Northbridge FC', short_name: 'Northbridge' } } } as unknown as Meta
const risk = {
  scorecard: { model: { concerns: 2, covered: 1, mean_lead_minutes: 17 } },
  concerns: [
    { player_id: 'THU-3', name: 'Lindqvist <b>', minute: 78, clock: '78:10', covered: true, lead_minutes: 17, baseline_covered: false, detail: 'holding hamstring' },
    { player_id: 'NBF-9', name: 'Ojo', minute: 84, clock: '84:02', covered: false, lead_minutes: null, baseline_covered: false, detail: 'limping briefly' },
  ],
  active_windows: [{ player_id: 'NBF-7', name: 'Mbeki' }],
} as unknown as RiskMsg

describe('the staff report', () => {
  it('says how many knocks were warned and how early, in a sentence', () => {
    expect(warningSummary(risk)).toBe('2 knocks; the Risk Monitor had warned about 1 of them, with 17 minutes of notice on average.')
    expect(warningSummary(null)).toBe('No knocks in this match.')
  })

  it('is a self-contained printable page with knocks, decisions and the disclaimer, and escapes names', () => {
    const html = staffReportHtml({ meta, score: { THU: 1, NBF: 2 }, risk, entries: [], credibility: null, generatedAt: new Date('2026-10-27T12:00:00Z') })
    expect(html.startsWith('<!doctype html>')).toBe(true)
    expect(html).toContain('Thames United 1 - 2 Northbridge FC')
    expect(html).toContain('warned, 17 min before')
    expect(html).toContain('Still in a risk window at full time: Mbeki.')
    expect(html).toContain('Lindqvist &lt;b&gt;')
    expect(html).toContain('not medical advice')
    expect(html).toContain('No change was proposed or tried.')
  })
})
