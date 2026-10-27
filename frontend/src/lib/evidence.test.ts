import { describe, expect, it } from 'vitest'
import { PROOFS } from './evidence'

describe('the proofs on the entry screen', () => {
  it('are three, each with a value, a caption and a source', () => {
    expect(PROOFS).toHaveLength(3)
    for (const p of PROOFS) {
      expect(p.value.trim().length).toBeGreaterThan(0)
      expect(p.caption.endsWith('.')).toBe(true)
      expect(p.source.length).toBeGreaterThan(10)
    }
  })

  it('carry the numbers the README reports', () => {
    expect(PROOFS[0].value).toBe('2x')
    expect(PROOFS[0].source).toContain('27 %')
    expect(PROOFS[0].source).toContain('14 %')
    expect(PROOFS[1].value).toBe('27 min')
    expect(PROOFS[2].value).toBe('4.9 / 5')
  })
})
