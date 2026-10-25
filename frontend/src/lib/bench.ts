/** Bench-seat helpers: substitution budget, readiness states, available substitutes, hazard series lookups. Pure. */

import type { MatchEvent, PlayerView, RiskWindow } from './types'

export const SUBS_ALLOWED = 5
export const SUB_WINDOWS = 3

export type SubBudget = { used: number; left: number; windows: number; windowsLeft: number; exhausted: boolean }

/** Five substitutions in three windows: changes made in the same stoppage are one window; the half-time break is free. */
export function subBudget(keyEvents: MatchEvent[], teamId: string, allowed = SUBS_ALLOWED, windowsAllowed = SUB_WINDOWS): SubBudget {
  const subs = keyEvents.filter((e) => e.type === 'substitution' && e.team_id === teamId)
  const used = subs.length
  const stoppages = new Set<string>()
  for (const s of subs) {
    const atBreak = s.period === 2 && s.minute === 45 && (s.second ?? 0) === 0
    if (!atBreak) stoppages.add(`${s.period}:${s.minute}`)
  }
  const windows = stoppages.size
  const left = Math.max(0, allowed - used)
  const windowsLeft = Math.max(0, windowsAllowed - windows)
  return { used, left, windows, windowsLeft, exhausted: left === 0 || windowsLeft === 0 }
}

export type Readiness = 'at risk' | 'fading' | 'fresh' | 'steady'
export const FADING_RATIO = 0.88 // recent pace 12 % under the player's own match pace
export const FRESH_MINUTES = 15

/** One word for the bench, with its reason. Precedence: at risk, fading, fresh, steady. */
export function readiness(p: Pick<PlayerView, 'minutes_played' | 'effort_ratio' | 'effort_ratio_recent' | 'risk_band'>, window?: RiskWindow | null): { state: Readiness; reason: string } {
  if (window) return { state: 'at risk', reason: `${window.level} risk window since ${window.open_minute}'` }
  if (p.risk_band === 'high') return { state: 'at risk', reason: 'workload ratio in the high band' }
  if (p.minutes_played >= 20 && p.effort_ratio > 0 && p.effort_ratio_recent / p.effort_ratio <= FADING_RATIO) {
    return { state: 'fading', reason: `recent pace ${Math.round((1 - p.effort_ratio_recent / p.effort_ratio) * 100)}% under own pace` }
  }
  if (p.minutes_played < FRESH_MINUTES) return { state: 'fresh', reason: `${p.minutes_played}' played` }
  return { state: 'steady', reason: 'pace holding' }
}

const POS_ORDER: Record<string, number> = { GK: 0, DF: 1, MF: 2, FW: 3 }
const byPosition = (a: PlayerView, b: PlayerView) => (POS_ORDER[a.position] ?? 9) - (POS_ORDER[b.position] ?? 9) || a.shirt_number - b.shirt_number

/** Substitutes still available: on the bench and not used. */
export function availableSubs(players: Record<string, PlayerView>, teamId: string): PlayerView[] {
  return Object.values(players).filter((p) => p.team_id === teamId && !p.on_pitch && p.minutes_played === 0).sort(byPosition)
}

/** Players already taken off. */
export function subbedOff(players: Record<string, PlayerView>, teamId: string): PlayerView[] {
  return Object.values(players).filter((p) => p.team_id === teamId && !p.on_pitch && p.minutes_played > 0).sort(byPosition)
}

export type HazardSeries = Record<string, [number, number][]>

export function currentHazard(series: HazardSeries | null | undefined, pid: string): number | null {
  const s = series?.[pid]
  return s && s.length ? s[s.length - 1][1] : null
}

/** The n players with the highest current hazard among `pids`. */
export function topHazards(series: HazardSeries | null | undefined, pids: string[], n = 5): { pid: string; hazard: number }[] {
  return pids
    .map((pid) => ({ pid, hazard: currentHazard(series, pid) }))
    .filter((x): x is { pid: string; hazard: number } => x.hazard != null)
    .sort((a, b) => b.hazard - a.hazard || a.pid.localeCompare(b.pid))
    .slice(0, n)
}

/** Effort change as a percentage of the player's own match pace, or null before it can be measured. */
export function effortDelta(p: Pick<PlayerView, 'minutes_played' | 'effort_ratio' | 'effort_ratio_recent'>): number | null {
  if (p.minutes_played < 10 || !(p.effort_ratio > 0)) return null
  return Math.round((p.effort_ratio_recent / p.effort_ratio - 1) * 100)
}
