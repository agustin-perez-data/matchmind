/** Stadium sounds, synthesised in the browser with Web Audio: no samples, no licences.
 *
 *  whistle(short)  kick-off, second-half kick-off, half-time
 *  roar()          goal: a crowd swell made of filtered noise
 *  whistle(long)   full time
 *
 *  Browsers only start audio after a user gesture, so `unlock()` is called from
 *  the entry page click; `enabled` is remembered per viewer in localStorage.
 */

const KEY = 'matchmind.sound'

class Stadium {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  /** exposed so dev tooling can tap the signal that actually reaches the speakers */
  limiter: DynamicsCompressorNode | null = null
  enabled: boolean

  constructor() {
    let saved: string | null = null
    try { saved = localStorage.getItem(KEY) } catch { /* private window */ }
    this.enabled = saved !== 'off'
  }

  setEnabled(on: boolean) {
    this.enabled = on
    try { localStorage.setItem(KEY, on ? 'on' : 'off') } catch { /* ignore */ }
    if (on) this.unlock()
  }

  /** Create or resume the context; must run inside a user gesture at least once. */
  unlock() {
    if (!this.ctx) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return
      this.ctx = new Ctor()
      this.master = this.ctx.createGain()
      this.master.gain.value = 0.6
      // a gentle limiter so a roar on top of a whistle never clips
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
  whistle(kind: 'short' | 'long' = 'short') {
    const r = this.ready()
    if (!r) return
    const { ctx, out } = r
    const t0 = ctx.currentTime + 0.02
    const dur = kind === 'long' ? 1.6 : 0.45
    const env = ctx.createGain()
    env.gain.setValueAtTime(0, t0)
    env.gain.linearRampToValueAtTime(0.32, t0 + 0.015)
    env.gain.setValueAtTime(0.32, t0 + dur - 0.08)
    env.gain.exponentialRampToValueAtTime(0.001, t0 + dur)
    env.connect(out)

    const warble = ctx.createGain()
    warble.gain.value = 0.55
    const lfo = ctx.createOscillator()
    lfo.type = 'sine'
    lfo.frequency.value = kind === 'long' ? 32 : 38
    const lfoDepth = ctx.createGain()
    lfoDepth.gain.value = 0.45
    lfo.connect(lfoDepth).connect(warble.gain)
    warble.connect(env)

    for (const f of [2720, 2790]) {
      const o = ctx.createOscillator()
      o.type = 'sine'
      o.frequency.setValueAtTime(f, t0)
      o.frequency.linearRampToValueAtTime(f * 1.012, t0 + 0.05)
      o.connect(warble)
      o.start(t0)
      o.stop(t0 + dur + 0.05)
    }
    const breath = this.noise(dur + 0.05)
    const bp = ctx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.frequency.value = 2900
    bp.Q.value = 6
    const breathGain = ctx.createGain()
    breathGain.gain.value = 0.25
    breath.connect(bp).connect(breathGain).connect(env)
    breath.start(t0)
    lfo.start(t0)
    lfo.stop(t0 + dur + 0.05)
  }

  /** A crowd roar: a choir of shouting voices (detuned saws through "ah" formants) over a thin noise bed,
   *  swelling fast and fading slow, with a second smaller wave as the celebration settles. */
  roar() {
    const r = this.ready()
    if (!r) return
    const { ctx, out } = r
    const t0 = ctx.currentTime + 0.02
    const total = 7
    const env = ctx.createGain()
    env.gain.setValueAtTime(0, t0)
    env.gain.linearRampToValueAtTime(1, t0 + 0.3)
    env.gain.setValueAtTime(1, t0 + 2.0)
    env.gain.linearRampToValueAtTime(0.5, t0 + 4.2)
    env.gain.exponentialRampToValueAtTime(0.001, t0 + total)
    env.connect(out)

    // the vowel: three formant bands of an open "ah", summed, then rolled off
    const formants = ctx.createGain()
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 4200
    formants.connect(lp).connect(env)
    const bands: BiquadFilterNode[] = [[700, 4, 1], [1150, 5, 0.9], [2600, 6, 0.5]].map(([f, q, g]) => {
      const bp = ctx.createBiquadFilter()
      bp.type = 'bandpass'
      bp.frequency.value = f
      bp.Q.value = q
      const bg = ctx.createGain()
      bg.gain.value = g
      bp.connect(bg).connect(formants)
      return bp
    })
    const voicesIn = ctx.createGain()
    const VOICES = 32
    voicesIn.gain.value = 1.8 / Math.sqrt(VOICES)
    for (const bp of bands) voicesIn.connect(bp)

    for (let i = 0; i < VOICES; i++) {
      const at = t0 + Math.random() * 0.25 // nobody shouts at exactly the same instant
      const base = 150 + Math.random() * 200 // from deep to high shouts
      const o = ctx.createOscillator()
      o.type = 'sawtooth'
      o.frequency.setValueAtTime(base * 0.92, at)
      o.frequency.exponentialRampToValueAtTime(base * 1.08, at + 0.25) // the shout rises
      o.frequency.exponentialRampToValueAtTime(base * 0.85, at + 3 + Math.random() * 1.5) // then sags as breath runs out
      const vib = ctx.createOscillator()
      vib.frequency.value = 4 + Math.random() * 3
      const vibDepth = ctx.createGain()
      vibDepth.gain.value = base * 0.03
      vib.connect(vibDepth).connect(o.frequency)
      const g = ctx.createGain()
      const hold = 2.2 + Math.random() * 2.0
      g.gain.setValueAtTime(0, at)
      g.gain.linearRampToValueAtTime(1, at + 0.05 + Math.random() * 0.08)
      g.gain.setValueAtTime(1, at + hold)
      g.gain.linearRampToValueAtTime(0, at + hold + 1.2 + Math.random() * 1.5)
      o.connect(g).connect(voicesIn)
      o.start(at)
      vib.start(at)
      o.stop(t0 + total)
      vib.stop(t0 + total)
    }

    // the hiss of thousands more, far away
    const bed = this.noise(total)
    const bp = ctx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.frequency.value = 1100
    bp.Q.value = 0.6
    const bedGain = ctx.createGain()
    bedGain.gain.value = 0.4
    bed.connect(bp).connect(bedGain).connect(env)
    bed.start(t0)
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

/** Which sound, if any, a match event triggers. */
export function soundFor(type: string): 'short' | 'long' | 'roar' | null {
  switch (type) {
    case 'kickoff':
    case 'second_half_kickoff':
    case 'half_time':
      return 'short'
    case 'goal':
      return 'roar'
    case 'full_time':
      return 'long'
    default:
      return null
  }
}
