import { describe, expect, it } from 'vitest'
import { AWAY_IDS, BEATS, HOME_IDS, LOOP_MS, STILL_T, buildKeyframes, interpolate, phaseAt } from './preview'

describe('preview loop', () => {
  const kf = buildKeyframes()

  it('has 22 players and a ball in every keyframe, inside the pitch', () => {
    for (const k of kf) {
      expect(Object.keys(k.players)).toHaveLength(22)
      for (const id of [...HOME_IDS, ...AWAY_IDS]) {
        const [x, y] = k.players[id]
        expect(x).toBeGreaterThanOrEqual(0); expect(x).toBeLessThanOrEqual(105)
        expect(y).toBeGreaterThanOrEqual(0); expect(y).toBeLessThanOrEqual(68)
      }
      expect(k.ball[0]).toBeLessThanOrEqual(105)
    }
    expect(kf.map((k) => k.t)).toEqual([...kf.map((k) => k.t)].sort((a, b) => a - b))
  })

  it('interpolates linearly and holds at both ends', () => {
    const a = kf[1], b = kf[2]
    const mid = interpolate(kf, (a.t + b.t) / 2)
    expect(mid.ball[0]).toBeCloseTo((a.ball[0] + b.ball[0]) / 2, 6)
    expect(mid.players.h9[1]).toBeCloseTo((a.players.h9[1] + b.players.h9[1]) / 2, 6)
    expect(interpolate(kf, -50)).toEqual({ players: kf[0].players, ball: kf[0].ball })
    expect(interpolate(kf, LOOP_MS)).toEqual({ players: kf[kf.length - 1].players, ball: kf[kf.length - 1].ball })
  })

  it('the move ends with a shot: the ball reaches the goal line', () => {
    const end = interpolate(kf, BEATS.lowerThird)
    expect(end.ball[0]).toBeGreaterThan(100)
  })

  it('phases land in order and the still frame shows everything', () => {
    expect(phaseAt(0)).toBe('play')
    expect(phaseAt(BEATS.lowerThird)).toBe('lowerThird')
    expect(phaseAt(BEATS.verdict)).toBe('verdict')
    expect(phaseAt(BEATS.fade)).toBe('fade')
    expect(phaseAt(STILL_T)).toBe('verdict')
    expect(STILL_T).toBeLessThan(LOOP_MS)
  })
})
