import { describe, expect, it } from 'vitest'
import { BINS, CALIBRATION, binFor, calibrationNote, hitRateFor } from './calibration'
import { WINDOW_THRESHOLD } from './bench'

describe('calibration bins', () => {
  it('maps a hazard to its bin, with the last bin inclusive of 1.0 and nothing below the threshold', () => {
    expect(binFor(0.49)).toBeNull()
    expect(binFor(0.5)?.lo).toBe(0.5)
    expect(binFor(0.95)).toBe(BINS[BINS.length - 1])
    expect(binFor(1.0)).toBe(BINS[BINS.length - 1])
    expect(binFor(Number.NaN)).toBeNull()
  })
  it('reads the model hit rate and writes the note', () => {
    const top = hitRateFor(0.95)!
    expect(top.n).toBe(164)
    expect(top.hits).toBe(44)
    expect(calibrationNote(0.95)).toBe('windows opened at 0.9-1.0 saw a knock 27% of the time (44 of 164, 40 synthetic matches)')
    expect(calibrationNote(0.55)).toMatch(/0\.5-0\.6 saw a knock 0% of the time/)
    expect(calibrationNote(0.2)).toBeNull()
  })
  it('agrees with the bench threshold constant', () => {
    expect(CALIBRATION.threshold).toBe(WINDOW_THRESHOLD)
  })
})
