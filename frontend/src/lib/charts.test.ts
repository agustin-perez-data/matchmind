import { describe, expect, it } from 'vitest'
import { niceAxis } from './charts'

describe('niceAxis', () => {
  it('rounds the top to a nice step with at most four intervals', () => {
    expect(niceAxis(1.46)).toEqual({ top: 1.5, ticks: [0, 0.5, 1, 1.5] })
    expect(niceAxis(0.84)).toEqual({ top: 1, ticks: [0, 0.25, 0.5, 0.75, 1] })
    expect(niceAxis(2.3)).toEqual({ top: 3, ticks: [0, 1, 2, 3] })
    expect(niceAxis(7.2)).toEqual({ top: 8, ticks: [0, 2, 4, 6, 8] })
  })
  it('never drops below the floor, so an early race is not zoomed into noise', () => {
    expect(niceAxis(0.1)).toEqual({ top: 0.5, ticks: [0, 0.25, 0.5] })
    expect(niceAxis(0)).toEqual({ top: 0.5, ticks: [0, 0.25, 0.5] })
    expect(niceAxis(Number.NaN)).toEqual({ top: 0.5, ticks: [0, 0.25, 0.5] })
  })
  it('keeps a value exactly on a step as the top', () => {
    expect(niceAxis(1).top).toBe(1)
    expect(niceAxis(0.5).top).toBe(0.5)
  })
})
