/** Replay speed control.
 *
 *  Speeds are multiples of real time; 0 means "as fast as the server can send" (max).
 *  The ladder is ordered from slowest to fastest, with max at the top, so "−" always
 *  slows the replay down and "+" always speeds it up, from any starting value,
 *  including values that are not on the ladder (a hand-edited URL).
 */

export const MAX = 0
export const LADDER: readonly number[] = [15, 30, 60, 120, 300, 1000, MAX]
export const DEFAULT_SPEED = 60

/** Position of a speed on the ladder; off-ladder values map to the nearest rung above them (max stays max). */
export function rungOf(speed: number): number {
  if (speed === MAX) return LADDER.length - 1
  const i = LADDER.findIndex((s) => s !== MAX && s >= speed)
  return i < 0 ? LADDER.length - 1 : i
}

/** The next speed after pressing − (dir -1) or + (dir +1). Clamped at both ends. */
export function stepSpeed(speed: number, dir: 1 | -1): number {
  const i = rungOf(speed)
  const onLadder = LADDER[i] === speed
  // Off-ladder: "+" goes to the rung above, "−" to the rung below it
  const target = onLadder ? i + dir : dir > 0 ? i : i - 1
  return LADDER[Math.max(0, Math.min(LADDER.length - 1, target))]
}

export const canSlowDown = (speed: number) => stepSpeed(speed, -1) !== speed
export const canSpeedUp = (speed: number) => stepSpeed(speed, 1) !== speed

export function labelSpeed(speed: number): string {
  return speed === MAX ? 'max' : `×${speed}`
}

/** Parse a speed from the URL: non-negative numbers only; anything else is the default. */
export function parseSpeed(raw: string | null): number {
  if (raw == null || raw === '') return DEFAULT_SPEED
  const n = Number(raw)
  return Number.isFinite(n) && n >= 0 ? n : DEFAULT_SPEED
}
