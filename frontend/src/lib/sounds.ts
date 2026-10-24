/** Stadium sounds, synthesised in the browser with Web Audio: no samples, no licences.
 *
 *  whistle('kickoff')    one short blast: kick-off, second-half kick-off
 *  whistle('goal')       two quick blasts
 *  whistle('half_time')  two medium blasts
 *  whistle('full_time')  short, short, long: the classic
 *
 *  Browsers only start audio after a user gesture, so `unlock()` is called from
 *  the entry page click; `enabled` is remembered per viewer in localStorage.
 */

const KEY = 'matchmind.sound'

export type WhistlePattern = 'kickoff' | 'goal' | 'half_time' | 'full_time'
/** blasts as [duration, gap after] in seconds */
const PATTERNS: Record<WhistlePattern, [number, number][]> = {
  kickoff: [[0.45, 0]],
  goal: [[0.14, 0.1], [0.14, 0]],
  half_time: [[0.5, 0.2], [0.5, 0]],
  full_time: [[0.3, 0.12], [0.3, 0.12], [1.4, 0]],
}

class Stadium {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  /** exposed so dev tooling can tap the signal that actually reaches the speakers */
  limiter: DynamicsCompressorNode | null = null
  enabled: boolean
  onMute: (() => void) | null = null // the commentator's voice stops too

  constructor() {
    let saved: string | null = null
    try { saved = localStorage.getItem(KEY) } catch { /* private window */ }
    this.enabled = saved !== 'off'
  }

  setEnabled(on: boolean) {
    this.enabled = on
    if (!on) this.onMute?.()
    try { localStorage.setItem(KEY, on ? 'on' : 'off') } catch { /* ignore */ }
    if (on) this.unlock()
  }

  /** Cut everything still ringing (a long whistle) in a few milliseconds: leaving the match. */
  cutAll() {
    if (!this.ctx || !this.master) return
    const t = this.ctx.currentTime
    this.master.gain.cancelScheduledValues(t)
    this.master.gain.setValueAtTime(this.master.gain.value, t)
    this.master.gain.linearRampToValueAtTime(0, t + 0.04)
    this.master.gain.setValueAtTime(0.6, t + 0.6) // every scheduled source has finished by then; back to normal for the next match
  }

  /** Create or resume the context; must run inside a user gesture at least once. */
  unlock() {
    if (!this.ctx) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return
      this.ctx = new Ctor()
      this.master = this.ctx.createGain()
      this.master.gain.value = 0.6
      // a gentle limiter so overlapping whistles never clip
      const limiter = this.ctx.createDynamicsCompressor()
      this.limiter = limiter
      limiter.threshold.value = -10
      limiter.knee.value = 6
      limiter.ratio.value = 8
      limiter.attack.value = 0.003
      limiter.release.value = 0.2
      this.master.connect(limiter).connect(this.ctx.destination)
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume()
  }

  private ready(): { ctx: AudioContext; out: GainNode } | null {
    if (!this.enabled) return null
    this.unlock()
    if (!this.ctx || !this.master || this.ctx.state !== 'running') return null
    return { ctx: this.ctx, out: this.master }
  }

  /** A referee's pea whistle: two close tones beating, warbled at ~35 Hz, with a breathy noise bed. */
  private blast(at: number, dur: number) {
    const ctx = this.ctx as AudioContext, out = this.master as GainNode
    const env = ctx.createGain()
    env.gain.setValueAtTime(0, at)
    env.gain.linearRampToValueAtTime(0.32, at + 0.015)
    env.gain.setValueAtTime(0.32, at + Math.max(0.03, dur - 0.08))
    env.gain.exponentialRampToValueAtTime(0.001, at + dur)
    env.connect(out)

    const warble = ctx.createGain()
    warble.gain.value = 0.55
    const lfo = ctx.createOscillator()
    lfo.type = 'sine'
    lfo.frequency.value = dur > 1 ? 32 : 38
    const lfoDepth = ctx.createGain()
    lfoDepth.gain.value = 0.45
    lfo.connect(lfoDepth).connect(warble.gain)
    warble.connect(env)

    for (const f of [2720, 2790]) {
      const o = ctx.createOscillator()
      o.type = 'sine'
      o.frequency.setValueAtTime(f, at)
      o.frequency.linearRampToValueAtTime(f * 1.012, at + 0.05)
      o.connect(warble)
      o.start(at)
      o.stop(at + dur + 0.05)
    }
    const breath = this.noise(dur + 0.05)
    const bp = ctx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.frequency.value = 2900
    bp.Q.value = 6
    const breathGain = ctx.createGain()
    breathGain.gain.value = 0.25
    breath.connect(bp).connect(breathGain).connect(env)
    breath.start(at)
    lfo.start(at)
    lfo.stop(at + dur + 0.05)
  }

  /** Each match moment has its own pattern, so a fan can tell them apart with eyes closed. */
  whistle(pattern: WhistlePattern = 'kickoff') {
    const r = this.ready()
    if (!r) return
    let at = r.ctx.currentTime + 0.02
    for (const [dur, gap] of PATTERNS[pattern]) {
      this.blast(at, dur)
      at += dur + gap
    }
  }

  private noise(seconds: number): AudioBufferSourceNode {
    const ctx = this.ctx as AudioContext
    const frames = Math.ceil(ctx.sampleRate * seconds)
    const buffer = ctx.createBuffer(1, frames, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    let b0 = 0, b1 = 0, b2 = 0
    for (let i = 0; i < frames; i++) {
      // Paul Kellet's cheap pink-noise approximation
      const white = Math.random() * 2 - 1
      b0 = 0.99765 * b0 + white * 0.099046
      b1 = 0.963 * b1 + white * 0.2965164
      b2 = 0.57 * b2 + white * 1.0526913
      data[i] = (b0 + b1 + b2 + white * 0.1848) * 0.25
    }
    const src = ctx.createBufferSource()
    src.buffer = buffer
    return src
  }
}

export const stadium = new Stadium()
if (import.meta.env.DEV) (window as unknown as { __stadium?: Stadium }).__stadium = stadium // for manual checks from the console

/** Which whistle, if any, a match event triggers. */
export function soundFor(type: string): WhistlePattern | null {
  switch (type) {
    case 'kickoff':
    case 'second_half_kickoff':
      return 'kickoff'
    case 'goal':
      return 'goal'
    case 'half_time':
      return 'half_time'
    case 'full_time':
      return 'full_time'
    default:
      return null
  }
}
