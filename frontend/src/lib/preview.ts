// The entry screen's six-second loop: a scripted build-up, authored as a few keyframes and interpolated
// between them. No backend, no stream: the point is to show the product's shape (22 moving dots, a ball,
// a lower third, a verdict stamp) before anyone has chosen anything. Coordinates are pitch metres,
// 105 x 68, home attacking right.

export type XY = [number, number]
export type Keyframe = { t: number; players: Record<string, XY>; ball: XY }
export type Pose = { players: Record<string, XY>; ball: XY }

export const LOOP_MS = 6000
/** When each layer of the moment lands, in ms from the start of the loop. */
export const BEATS = { play: 0, lowerThird: 3200, verdict: 4400, fade: 5600 } as const
export type Phase = 'play' | 'lowerThird' | 'verdict' | 'fade'

export const HOME_IDS = Array.from({ length: 11 }, (_, i) => `h${i + 1}`)
export const AWAY_IDS = Array.from({ length: 11 }, (_, i) => `a${i + 1}`)

// 4-3-3 for the side on the ball, 4-4-2 for the side defending, both at kick-off depth; the script then
// moves the ball side forward and the defenders back as the move develops.
const HOME_BASE: XY[] = [[8, 34], [24, 10], [22, 26], [22, 42], [24, 58], [40, 20], [38, 34], [40, 48], [58, 12], [60, 34], [58, 56]]
const AWAY_BASE: XY[] = [[98, 34], [84, 12], [86, 26], [86, 42], [84, 56], [70, 10], [68, 26], [68, 42], [70, 58], [56, 28], [56, 40]]

function shift(base: XY[], dx: number, squeeze = 0): XY[] {
  return base.map(([x, y]) => [x + dx, 34 + (y - 34) * (1 - squeeze)])
}

function pose(home: XY[], away: XY[], ball: XY, overrides: Record<string, XY> = {}): Omit<Keyframe, 't'> {
  const players: Record<string, XY> = {}
  home.forEach((p, i) => { players[HOME_IDS[i]] = p })
  away.forEach((p, i) => { players[AWAY_IDS[i]] = p })
  return { players: { ...players, ...overrides }, ball }
}

/** The move: a switch to the right wing, a cut inside, a shot from 14 metres. */
export function buildKeyframes(): Keyframe[] {
  return [
    { t: 0, ...pose(HOME_BASE, AWAY_BASE, [38, 34]) },
    { t: 700, ...pose(shift(HOME_BASE, 6), shift(AWAY_BASE, -3, 0.05), [52, 18], { h9: [60, 16] }) },
    { t: 1500, ...pose(shift(HOME_BASE, 14, 0.1), shift(AWAY_BASE, -9, 0.15), [74, 10], { h9: [76, 9], a2: [78, 14] }) },
    { t: 2300, ...pose(shift(HOME_BASE, 22, 0.2), shift(AWAY_BASE, -15, 0.3), [86, 22], { h9: [88, 20], h10: [84, 32], a2: [84, 18], a3: [88, 30] }) },
    { t: 2900, ...pose(shift(HOME_BASE, 26, 0.25), shift(AWAY_BASE, -17, 0.35), [91, 32], { h9: [88, 20], h10: [91, 33], a3: [90, 36], a1: [99, 33] }) },
    { t: 3200, ...pose(shift(HOME_BASE, 26, 0.25), shift(AWAY_BASE, -17, 0.35), [104, 31], { h9: [88, 20], h10: [92, 34], a3: [91, 37], a1: [102, 30] }) },
  ]
}

const lerp = (a: number, b: number, k: number) => a + (b - a) * k

/** The pose at `t` ms: linear between the two keyframes around it, held at the ends. */
export function interpolate(keyframes: Keyframe[], t: number): Pose {
  const first = keyframes[0], last = keyframes[keyframes.length - 1]
  if (t <= first.t) return { players: first.players, ball: first.ball }
  if (t >= last.t) return { players: last.players, ball: last.ball }
  let i = 1
  while (keyframes[i].t < t) i++
  const a = keyframes[i - 1], b = keyframes[i]
  const k = (t - a.t) / (b.t - a.t)
  const players: Record<string, XY> = {}
  for (const id of Object.keys(a.players)) {
    const pa = a.players[id], pb = b.players[id] ?? pa
    players[id] = [lerp(pa[0], pb[0], k), lerp(pa[1], pb[1], k)]
  }
  return { players, ball: [lerp(a.ball[0], b.ball[0], k), lerp(a.ball[1], b.ball[1], k)] }
}

/** Which layer is showing at `t` ms into the loop. */
export function phaseAt(t: number): Phase {
  if (t >= BEATS.fade) return 'fade'
  if (t >= BEATS.verdict) return 'verdict'
  if (t >= BEATS.lowerThird) return 'lowerThird'
  return 'play'
}

/** The frame reduced-motion viewers see: the end of the move with every layer on. */
export const STILL_T = BEATS.verdict + 200
