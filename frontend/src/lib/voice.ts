/** The commentator's voice: one line at a time, the latest wins, nothing queued up behind a long one. */

import { API_BASE } from './api'
import { stadium } from './sounds'

class Voice {
  private audio: HTMLAudioElement | null = null
  private current = ''
  spoken = 0

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
    void audio.play().catch(() => { /* autoplay blocked until the first click; the next line will play */ })
  }

  stop(): void {
    if (this.audio) {
      this.audio.pause()
      this.audio.src = ''
      this.audio = null
    }
  }
}

export const voice = new Voice()
stadium.onMute = () => voice.stop()
if (import.meta.env.DEV) (window as unknown as { __voice?: Voice }).__voice = voice
