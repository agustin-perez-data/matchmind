import type { MatchRow } from './api'

/** Match ids made by the nightly job end in the date they were made: HOME-AWAY-YYYYMMDD. */
const DAILY = /-(\d{8})$/

export const isDaily = (id: string): boolean => DAILY.test(id)

export type MenuFixture = { row: MatchRow; daily: boolean }

/**
 * What the menu lists, and in what order: the headline derby first, then the rest of the matchday, then only
 * the newest match of the day. The catalogue grows by one match every night; older daily matches stay
 * reachable by URL but would otherwise turn the menu into a list.
 */
export function menuFixtures(rows: MatchRow[], headlinePrefix = 'THU'): MenuFixture[] {
  const matchday = rows.filter((r) => !isDaily(r.match_id))
  const headline = matchday.filter((r) => r.match_id.startsWith(headlinePrefix))
  const rest = matchday.filter((r) => !r.match_id.startsWith(headlinePrefix))
  const dailies = rows.filter((r) => isDaily(r.match_id)).sort((a, b) => b.match_id.slice(-8).localeCompare(a.match_id.slice(-8)))
  const today = dailies[0]
  return [...headline, ...rest].map((row) => ({ row, daily: false })).concat(today ? [{ row: today, daily: true }] : [])
}

/** The fixture the primary action opens: the derby when it exists, else the first listed. */
export function headlineFixture(rows: MatchRow[], headlinePrefix = 'THU'): MatchRow | null {
  return rows.find((r) => r.match_id.startsWith(headlinePrefix)) ?? menuFixtures(rows, headlinePrefix)[0]?.row ?? null
}

export type QuickStart = { matchId: string; url: Record<string, string | null> }

/** What the entry screen's primary action does: the derby, fan seat, neutral side (no turnstile), current language and speed. */
export function quickStartPlan(rows: MatchRow[], selected: string | null, language: string, speed: number, agents: boolean, coach: boolean): QuickStart | null {
  const id = headlineFixture(rows)?.match_id ?? selected
  if (!id) return null
  return { matchId: id, url: { seat: 'fan', match: id, lang: language, speed: String(speed), team: 'neutral', agents: agents ? null : '0', coach: coach ? null : '0' } }
}
