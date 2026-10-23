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

  /** A crowd roar, shaped after a reference stadium recording: half a second of expectation, a
   *  crescendo to the peak, a short sustain and a fade. Voices are detuned saws with a shout contour,
   *  amplitude flutter and vibrato, through "ah" formants centred near 1 kHz; claps and a thin noise
   *  bed give it texture. Nothing below ~450 Hz: a crowd on a broadcast has no bass. */
  roar() {
    const r = this.ready()
    if (!r) return
    const { ctx, out } = r
    const t0 = ctx.currentTime + 0.02
    const total = 4.6
    const env = ctx.createGain()
    env.gain.setValueAtTime(0, t0)
    env.gain.linearRampToValueAtTime(0.28, t0 + 0.15) // the first voices
    env.gain.setValueAtTime(0.28, t0 + 0.45)
    env.gain.linearRampToValueAtTime(1, t0 + 1.0) // everyone joins
    env.gain.setValueAtTime(1, t0 + 2.3)
    env.gain.linearRampToValueAtTime(0.6, t0 + 3.2)
    env.gain.exponentialRampToValueAtTime(0.001, t0 + total)
    const hp = ctx.createBiquadFilter()
    hp.type = 'highpass'
    hp.frequency.value = 480
    hp.Q.value = 0.7
    hp.connect(env).connect(out)

    // the vowel of a shouting crowd: three bands, the strongest around 1.1 kHz
    const formants = ctx.createGain()
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 3800
    const surge = ctx.createGain() // waves of shouting: slow random modulation of the whole mass
    surge.gain.value = 0.8
    const surgeSrc = this.noise(total)
    const surgeLp = ctx.createBiquadFilter()
    surgeLp.type = 'lowpass'
    surgeLp.frequency.value = 9
    const surgeDepth = ctx.createGain()
    surgeDepth.gain.value = 1.2
    surgeSrc.connect(surgeLp).connect(surgeDepth).connect(surge.gain)
    surgeSrc.start(t0)
    formants.connect(lp).connect(surge).connect(hp)
    const bands = [[820, 4, 0.55], [1150, 4, 1], [1550, 5, 0.8], [2400, 7, 0.3]].map(([f, q, g]) => {
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
    const VOICES = 36
    voicesIn.gain.value = 2.0 / Math.sqrt(VOICES)
    for (const bp of bands) voicesIn.connect(bp)

    for (let i = 0; i < VOICES; i++) {
      // the first few shout at once, the rest pile in during the crescendo
      const at = t0 + (i < 6 ? Math.random() * 0.15 : 0.3 + Math.random() * 0.8)
      const base = 210 + Math.random() * 230 // men, women and kids shouting
      const o = ctx.createOscillator()
      o.type = 'sawtooth'
      o.frequency.setValueAtTime(base * 0.9, at)
      o.frequency.exponentialRampToValueAtTime(base * 1.1, at + 0.2)
      o.frequency.exponentialRampToValueAtTime(base * 0.88, at + 2 + Math.random() * 1.2)
      const vib = ctx.createOscillator()
      vib.frequency.value = 4.5 + Math.random() * 3
      const vibDepth = ctx.createGain()
      vibDepth.gain.value = base * 0.035
      vib.connect(vibDepth).connect(o.frequency)
      // flutter: each voice breathes at its own pace, so the mass of voices shimmers
      const flutter = ctx.createOscillator()
      flutter.frequency.value = 2 + Math.random() * 6
      const flutterDepth = ctx.createGain()
      flutterDepth.gain.value = 0.35
      const g = ctx.createGain()
      const hold = 1.0 + Math.random() * 1.6
      g.gain.setValueAtTime(0, at)
      g.gain.linearRampToValueAtTime(0.65, at + 0.04 + Math.random() * 0.08)
      g.gain.setValueAtTime(0.65, at + hold)
      g.gain.linearRampToValueAtTime(0, at + hold + 0.6 + Math.random() * 1.2)
      flutter.connect(flutterDepth).connect(g.gain)
      o.connect(g).connect(voicesIn)
      o.start(at)
      vib.start(at)
      flutter.start(at)
      o.stop(t0 + total)
      vib.stop(t0 + total)
      flutter.stop(t0 + total)
    }

    // claps and whistles from the stands: short bright bursts, denser at the peak
    const clapBus = ctx.createGain()
    clapBus.gain.value = 0.7
    const clapBp = ctx.createBiquadFilter()
    clapBp.type = 'bandpass'
    clapBp.frequency.value = 2600
    clapBp.Q.value = 1.2
    clapBus.connect(clapBp).connect(hp)
    for (let t = 0.3; t < total - 0.6; t += 0.03 + Math.random() * 0.09) {
      const at = t0 + t
      const burst = this.noise(0.03)
      const g = ctx.createGain()
      g.gain.setValueAtTime(0.2 + Math.random() * 0.5, at)
      g.gain.exponentialRampToValueAtTime(0.001, at + 0.015 + Math.random() * 0.025)
      burst.connect(g).connect(clapBus)
      burst.start(at)
    }

    // the hiss of thousands more, far away
    const bed = this.noise(total)
    const bedBp = ctx.createBiquadFilter()
    bedBp.type = 'bandpass'
    bedBp.frequency.value = 1300
    bedBp.Q.value = 0.8
    const bedGain = ctx.createGain()
    bedGain.gain.value = 0.3
    bed.connect(bedBp).connect(bedGain).connect(hp)
    bed.start(t0)
  }

  /** The home end when the other side scores: a short, falling "ohhh" from the same choir, no claps, no surge. */
  groan() {
    const r = this.ready()
    if (!r) return
    const { ctx, out } = r
    const t0 = ctx.currentTime + 0.02
    const total = 2.6
    const env = ctx.createGain()
    env.gain.setValueAtTime(0, t0)
    env.gain.linearRampToValueAtTime(0.9, t0 + 0.25)
    env.gain.setValueAtTime(0.9, t0 + 0.9)
    env.gain.exponentialRampToValueAtTime(0.001, t0 + total)
    const hp = ctx.createBiquadFilter()
    hp.type = 'highpass'
    hp.frequency.value = 380
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 2200
    const formants = ctx.createGain()
    for (const [f, q, g] of [[520, 4, 1], [900, 4, 0.7], [1500, 6, 0.3]]) {
      const bp = ctx.createBiquadFilter()
      bp.type = 'bandpass'
      bp.frequency.value = f
      bp.Q.value = q
      const bg = ctx.createGain()
      bg.gain.value = g
      formants.connect(bp).connect(bg).connect(lp)
    }
    lp.connect(hp).connect(env).connect(out)
    const VOICES = 24
    const voicesIn = ctx.createGain()
    voicesIn.gain.value = 1.6 / Math.sqrt(VOICES)
    voicesIn.connect(formants)
    for (let i = 0; i < VOICES; i++) {
      const at = t0 + Math.random() * 0.2
      const base = 140 + Math.random() * 160
      const o = ctx.createOscillator()
      o.type = 'sawtooth'
      o.frequency.setValueAtTime(base, at)
      o.frequency.exponentialRampToValueAtTime(base * 0.72, at + 1.8 + Math.random() * 0.6) // everyone's voice sinks
      const g = ctx.createGain()
      g.gain.setValueAtTime(0, at)
      g.gain.linearRampToValueAtTime(0.7, at + 0.1)
      g.gain.setValueAtTime(0.7, at + 0.8 + Math.random() * 0.5)
      g.gain.linearRampToValueAtTime(0, at + 1.6 + Math.random() * 0.8)
      o.connect(g).connect(voicesIn)
      o.start(at)
      o.stop(t0 + total)
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

/** Which sound, if any, a match event triggers. */
export function soundFor(type: string): 'short' | 'long' | 'roar' | null {  // 'roar' becomes a groan when the fan's side conceded
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
