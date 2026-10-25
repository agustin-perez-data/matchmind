/** Chart hygiene helpers shared by the strips. */

const STEPS = [0.25, 0.5, 1, 2, 5, 10, 20, 50]

/** A "nice" axis for a positive quantity: the top is a round multiple of a step, with at most four intervals. */
export function niceAxis(max: number, floor = 0.5): { top: number; ticks: number[] } {
  const m = Math.max(Number.isFinite(max) ? max : 0, floor)
  for (const step of STEPS) {
    const top = Math.ceil(m / step - 1e-9) * step
    if (top / step <= 4) return { top: round(top), ticks: Array.from({ length: Math.round(top / step) + 1 }, (_, i) => round(i * step)) }
  }
  const step = STEPS[STEPS.length - 1]
  const top = Math.ceil(m / step) * step
  return { top, ticks: [0, top / 2, top].map(round) }
}

const round = (v: number) => Math.round(v * 100) / 100
