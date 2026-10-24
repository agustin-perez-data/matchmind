/** The commentator's voice: one player for the whole app, one line at a time.
 *
 *  A line in progress is never cut: a newer line waits, and only the newest waiting line
 *  survives (a fan does not need three stale lines read back to back). Leaving the seat,
 *  muting or starting another match stops everything.
 */

import { API_BASE } from './api'
import { stadium } from './sounds'

class Voice {
  private readonly audio: HTMLAudioElement | null = typeof Audio !== 'undefined' ? new Audio() : null
  private current = ''
  private waiting: { text: string; lang: 'en' | 'es' } | null = null
  private busy = false
  spoken = 0
  played = 0
  interrupted = 0
  lastError: string | null = null

  constructor() {
    if (!this.audio) return
    this.audio.preload = 'auto'
    this.audio.volume = 0.95
    const done = () => { this.busy = false; this.next() }
    this.audio.addEventListener('ended', done)
    this.audio.addEventListener('error', () => { this.lastError = `audio error ${this.audio?.error?.code ?? '?'}`; done() })
    this.audio.addEventListener('playing', () => { this.played++ })
  }

  /** Say this line when the current one ends; a newer waiting line replaces an older waiting one. */
  say(text: string, lang: 'en' | 'es'): void {
    if (!this.audio || !stadium.enabled || !text || text === this.current) return
    this.current = text
    if (this.busy) { this.waiting = { text, lang }; return }
    this.start(text, lang)
  }

  private start(text: string, lang: 'en' | 'es'): void {
    if (!this.audio) return
    this.busy = true
    this.spoken++
    this.audio.src = `${API_BASE}/tts?${new URLSearchParams({ text, lang })}`
    void this.audio.play().catch((e: Error) => { this.lastError = e.message; this.busy = false /* autoplay blocked until the first click */ })
  }

  private next(): void {
    const w = this.waiting
    this.waiting = null
    if (w && stadium.enabled) this.start(w.text, w.lang)
  }

  /** Silence now and forget what was waiting (leaving the seat, muting, another match). */
  stop(): void {
    this.waiting = null
    this.current = ''
    if (this.audio && this.busy) { this.interrupted++; this.audio.pause(); this.busy = false }
  }
}

export const voice = new Voice()
stadium.onMute = () => voice.stop()
if (import.meta.env.DEV) (window as unknown as { __voice?: Voice }).__voice = voice
