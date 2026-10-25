/** The Risk Monitor's calibration (40 synthetic matches): how often a window opened at a given hazard saw a knock. */

import calibration from '../data/risk_calibration.json'

export type CalSide = { n: number; hits: number; hit_rate: number | null; mean_hazard: number | null }
export type CalBin = { lo: number; hi: number; model: CalSide; baseline: CalSide }
export const CALIBRATION = calibration as { matches: number; horizon_minutes: number; threshold: number; bins: CalBin[]; model: { windows: number; hits: number; base_rate: number | null }; baseline: { windows: number; hits: number; base_rate: number | null } }
export const BINS = CALIBRATION.bins

/** The bin a hazard falls in: `lo <= h < hi`, the last bin inclusive of its top (a hazard of exactly 1.0 counts). */
export function binFor(hazard: number): CalBin | null {
  if (!Number.isFinite(hazard) || !BINS.length || hazard < BINS[0].lo) return null
  for (let i = 0; i < BINS.length; i++) {
    const b = BINS[i]
    if (hazard >= b.lo && (hazard < b.hi || (i === BINS.length - 1 && hazard <= b.hi))) return b
  }
  return null
}

export function hitRateFor(hazard: number): { lo: number; hi: number; n: number; hits: number; rate: number | null } | null {
  const b = binFor(hazard)
  return b ? { lo: b.lo, hi: b.hi, n: b.model.n, hits: b.model.hits, rate: b.model.hit_rate } : null
}

/** One line for a card: the empirical frequency behind a ranking score. */
export function calibrationNote(hazard: number): string | null {
  const r = hitRateFor(hazard)
  if (!r || r.rate == null) return null
  return `windows opened at ${r.lo.toFixed(1)}-${r.hi.toFixed(1)} saw a knock ${Math.round(r.rate * 100)}% of the time (${r.hits} of ${r.n}, ${CALIBRATION.matches} synthetic matches)`
}
