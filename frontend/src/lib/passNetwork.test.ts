import { describe, expect, it } from 'vitest'
import type { Touch } from './follow'
import { MAX_EDGES, passNetwork } from './passNetwork'

const meta = { home_id: 'THU' }
let n = 0
const pass = (from: string, to: string, extra: Partial<Touch> = {}): Touch => ({
  event_id: ++n, clock: '0:00', minute: 1, period: 1, type: 'pass', team_id: 'THU', player_id: from, receiver_id: to,
  x: 20, y: 40, end_x: 40, end_y: 60, outcome: 'complete', ...extra,
})

describe('passNetwork', () => {
  it('merges both directions into one edge and places nodes at their mean involvement', () => {
    const net = passNetwork([pass('THU-01', 'THU-02'), pass('THU-01', 'THU-02'), pass('THU-02', 'THU-01', { x: 60, y: 20, end_x: 80, end_y: 80 })], 'THU', meta)
    expect(net.edges).toEqual([{ from: 'THU-01', to: 'THU-02', count: 3 }])
    expect(net.passes).toBe(3)
    expect(net.completed).toBe(3)
    const a = net.nodes.find((x) => x.pid === 'THU-01')!
    expect(a.passes).toBe(3) // two origins + one reception
    expect(a.x).toBeCloseTo((20 + 20 + 80) / 3)
    expect(a.y).toBeCloseTo((40 + 40 + 80) / 3)
  })

  it('counts an incomplete pass for the passer only and makes no edge below the threshold', () => {
    const net = passNetwork([pass('THU-01', 'THU-02', { outcome: 'incomplete' }), pass('THU-01', 'THU-03')], 'THU', meta)
    expect(net.edges).toEqual([])
    expect(net.passes).toBe(2)
    expect(net.completed).toBe(1)
    expect(net.nodes.map((x) => x.pid)).toEqual(['THU-01', 'THU-03'])
    expect(net.nodes.find((x) => x.pid === 'THU-01')!.passes).toBe(2)
  })

  it('mirrors second-half passes into the same attacking direction and filters by half', () => {
    const second = pass('THU-01', 'THU-02', { period: 2, x: 80, end_x: 60 })
    const all = passNetwork([pass('THU-01', 'THU-02'), second], 'THU', meta)
    expect(all.nodes.find((x) => x.pid === 'THU-01')!.x).toBeCloseTo(20) // 80 mirrored to 20 in the second half
    expect(passNetwork([pass('THU-01', 'THU-02'), second], 'THU', meta, 2).passes).toBe(1)
  })

  it('ignores the other team and players without a pass or a model position, and caps the edges', () => {
    const touches: Touch[] = [pass('NBF-01', 'NBF-02', { team_id: 'NBF' })]
    for (let i = 0; i < 40; i++) for (let k = 0; k < 2; k++) touches.push(pass(`THU-${i}`, `THU-${i + 1}`))
    const net = passNetwork(touches, 'THU', meta)
    expect(net.nodes.some((x) => x.pid.startsWith('NBF'))).toBe(false)
    expect(net.edges).toHaveLength(MAX_EDGES)
  })
})

describe('passNetwork with model positions', () => {
  it('places a node at the given position and keeps the pass mean for the others', () => {
    const net = passNetwork([pass('THU-01', 'THU-02')], 'THU', meta, 'all', { 'THU-01': [70, 30], 'THU-02': null })
    expect(net.nodes.find((x) => x.pid === 'THU-01')).toMatchObject({ x: 70, y: 30, passes: 1 })
    expect(net.nodes.find((x) => x.pid === 'THU-02')).toMatchObject({ x: 40, y: 60 })
  })

  it('adds a player the model places even before their first pass, and flags players off the pitch', () => {
    const net = passNetwork([pass('THU-01', 'THU-02')], 'THU', meta, 'all', { 'THU-01': [70, 30], 'THU-09': [8, 50], 'THU-03': null }, { 'THU-01': false })
    expect(net.nodes.find((x) => x.pid === 'THU-09')).toEqual({ pid: 'THU-09', x: 8, y: 50, passes: 0, onPitch: true })
    expect(net.nodes.find((x) => x.pid === 'THU-01')?.onPitch).toBe(false)
    expect(net.nodes.find((x) => x.pid === 'THU-02')?.onPitch).toBe(true)
    expect(net.nodes.some((x) => x.pid === 'THU-03')).toBe(false)
  })
})
