/** The commentator's voice: one line at a time, the latest wins, nothing queued up behind a long one. */

import { API_BASE } from './api'
import { stadium } from './sounds'

class Voice {
  private audio: HTMLAudioElement | null = null
  private current = ''
  spoken = 0
  played = 0 // lines that actually started playing
  lastError: string | null = null

  /** Say this line if sound is on; a newer line interrupts an older one. Repeated lines are not re-read. */
  say(text: string, lang: 'en' | 'es'): void {
    if (!stadium.enabled || !text || text === this.current) return
    this.current = text
    this.stop()
    const url = `${API_BASE}/tts?${new URLSearchParams({ text, lang })}`
    const audio = new Audio(url)
    audio.preload = 'auto'
    audio.volume = 0.95
    this.audio = audio
    this.spoken++
    audio.addEventListener('playing', () => { this.played++ }, { once: true })
    audio.addEventListener('error', () => { this.lastError = `audio error ${audio.error?.code ?? '?'} for ${url.slice(0, 60)}` })
    void audio.play().catch((e: Error) => { this.lastError = e.message /* autoplay blocked until the first click; the next line will play */ })
  }

  stop(): void {
    if (this.audio) {
      this.audio.pause() // just pause and let go: clearing src would fire a bogus error event on the old element
      this.audio = null
    }
  }
}

export const voice = new Voice()
stadium.onMute = () => voice.stop()
if (import.meta.env.DEV) (window as unknown as { __voice?: Voice }).__voice = voice
