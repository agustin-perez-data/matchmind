import { describe, expect, it } from 'vitest'
import { DEFAULT_SPEED, LADDER, MAX, canSlowDown, canSpeedUp, labelSpeed, parseSpeed, rungOf, stepSpeed } from './speed'

describe('the speed ladder', () => {
  it('is ordered slow to fast with max on top', () => {
    const real = LADDER.filter((s) => s !== MAX)
    expect(real).toEqual([...real].sort((a, b) => a - b))
    expect(LADDER[LADDER.length - 1]).toBe(MAX)
    expect(LADDER).toContain(DEFAULT_SPEED)
  })

  it('walks every rung up with + and back down with −', () => {
    let s = LADDER[0]
    const up: number[] = [s]
    for (let i = 0; i < LADDER.length - 1; i++) { s = stepSpeed(s, 1); up.push(s) }
    expect(up).toEqual([...LADDER])
    const down: number[] = [s]
    for (let i = 0; i < LADDER.length - 1; i++) { s = stepSpeed(s, -1); down.push(s) }
    expect(down).toEqual([...LADDER].reverse())
  })

  it('from max, − slows down to the fastest real speed and + stays at max', () => {
    expect(stepSpeed(MAX, -1)).toBe(1000)
    expect(stepSpeed(MAX, 1)).toBe(MAX)
    expect(canSlowDown(MAX)).toBe(true)
    expect(canSpeedUp(MAX)).toBe(false)
  })

  it('from the slowest, − stays put and + goes up', () => {
    expect(stepSpeed(15, -1)).toBe(15)
    expect(stepSpeed(15, 1)).toBe(30)
    expect(canSlowDown(15)).toBe(false)
    expect(canSpeedUp(15)).toBe(true)
  })

  it('never produces a value outside the ladder', () => {
    for (const start of [...LADDER, 1, 7, 50, 99, 150, 299, 301, 999, 5000]) {
      expect(LADDER).toContain(stepSpeed(start, 1))
      expect(LADDER).toContain(stepSpeed(start, -1))
    }
  })

  it('snaps hand-edited URL speeds onto the ladder in the right direction', () => {
    expect(stepSpeed(50, 1)).toBe(60)
    expect(stepSpeed(50, -1)).toBe(30)
    expect(stepSpeed(1, -1)).toBe(15) // nothing slower than the first rung
    expect(stepSpeed(1, 1)).toBe(15)
    expect(stepSpeed(5000, 1)).toBe(MAX) // faster than the top rung: next is max
    expect(stepSpeed(5000, -1)).toBe(1000)
    expect(rungOf(5000)).toBe(LADDER.length - 1)
  })

  it('labels max as "max" and the rest as multipliers', () => {
    expect(labelSpeed(MAX)).toBe('max')
    expect(labelSpeed(60)).toBe('×60')
    expect(labelSpeed(1000)).toBe('×1000')
  })

  it('parses the URL speed defensively', () => {
    expect(parseSpeed(null)).toBe(DEFAULT_SPEED)
    expect(parseSpeed('')).toBe(DEFAULT_SPEED)
    expect(parseSpeed('abc')).toBe(DEFAULT_SPEED)
    expect(parseSpeed('-5')).toBe(DEFAULT_SPEED)
    expect(parseSpeed('0')).toBe(MAX)
    expect(parseSpeed('120')).toBe(120)
    expect(parseSpeed('Infinity')).toBe(DEFAULT_SPEED)
  })
})
