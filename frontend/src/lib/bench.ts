/** Bench-seat helpers: substitution budget, readiness states, available substitutes, hazard series, decision log. Pure. */

import type { FeedItem } from './useMatchStream'
import type { BranchSummary, CoachMsg, MatchEvent, Meta, PlayerView, RiskWindow } from './types'

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
export const FADING_MIN_MINUTES = 20 // a pace drop is only called with this much play behind it
export const FRESH_MINUTES = 15
export const WINDOW_THRESHOLD = 0.5 // the Risk Monitor opens a window at this hazard (within the five highest on the pitch)

/** One word for the bench, with its reason. Precedence: at risk, fading, fresh, steady. */
export function readiness(p: Pick<PlayerView, 'minutes_played' | 'effort_ratio' | 'effort_ratio_recent' | 'risk_band'>, window?: RiskWindow | null): { state: Readiness; reason: string } {
  if (window) return { state: 'at risk', reason: `${window.level} risk window since ${window.open_minute}'` }
  if (p.risk_band === 'high') return { state: 'at risk', reason: 'workload ratio in the high band' }
  if (p.minutes_played >= FADING_MIN_MINUTES && p.effort_ratio > 0 && p.effort_ratio_recent / p.effort_ratio <= FADING_RATIO) {
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

/** The order of the board as a string: changes only when cards swap places (what a reorder animation keys on). */
export function orderKey(pids: string[]): string {
  return pids.join(',')
}

// ---------------------------------------------------------------- names and branches

export function nameOf(meta: Meta, playerId: string | null | undefined): string {
  if (!playerId) return '?'
  for (const t of Object.values(meta.teams)) {
    const p = t.players.find((x) => x.player_id === playerId)
    if (p) return p.name
  }
  return playerId
}

/** A branch in words: what the bench or the Coach tried. */
export function describeBranch(meta: Meta, b: BranchSummary): string {
  const iv = b.intervention
  if (iv.type === 'substitution') return `What if ${nameOf(meta, String(iv.player_off_id))} comes off at ${iv.minute}'`
  return `What if ${meta.teams[String(iv.team_id)]?.short_name ?? iv.team_id} changes tactics at ${iv.minute}'`
}

/** The Coach's proposal in words (shared by the decision card, the log and the report). */
export function describeProposal(meta: Meta, c: CoachMsg): string {
  const p = c.proposal
  if (!p) return 'no decision'
  if (p.action === 'hold') return 'hold'
  if (p.action === 'substitution') return `${nameOf(meta, p.player_off_id)} off at ${p.minute}'${p.player_on_id ? `, ${nameOf(meta, p.player_on_id)} on` : ''}`
  return `tactics at ${p.minute}': press ${p.press_intensity ?? 'same'}, ${p.style ?? 'same style'}`
}

export type DecisionEntry = {
  id: string
  source: 'coach' | 'bench'
  minute: number
  clock: string
  trigger?: string
  player?: string
  decision: string
  branch: BranchSummary | null
}

/** Everything that was decided or tried, in match order: the Coach's proposals (with or without a branch) and the
 *  bench's own simulations. A bench branch identical to a Coach one (same branch id) is listed once, as the Coach's. */
export function decisionLog(feed: FeedItem[], benchBranches: BranchSummary[], meta: Meta): DecisionEntry[] {
  const coach: DecisionEntry[] = [...feed].reverse()
    .filter((f): f is FeedItem & { msg: CoachMsg } => f.msg.kind === 'coach')
    .map((f) => ({
      id: `coach-${f.id}`, source: 'coach', minute: f.msg.minute, clock: f.msg.clock,
      trigger: f.msg.trigger === 'injury_concern' ? 'knock' : 'risk window', player: f.msg.player?.name,
      decision: describeProposal(meta, f.msg), branch: f.msg.branch,
    }))
  const seen = new Set(coach.map((e) => e.branch?.branch_id).filter(Boolean))
  const bench: DecisionEntry[] = benchBranches
    .filter((b) => !seen.has(b.branch_id))
    .map((b) => ({ id: `bench-${b.branch_id}`, source: 'bench', minute: b.divergence_minute, clock: `${b.divergence_minute}'`, decision: describeBranch(meta, b), branch: b }))
  return [...coach, ...bench].sort((a, b) => a.minute - b.minute || (a.source === b.source ? 0 : a.source === 'coach' ? -1 : 1))
}
