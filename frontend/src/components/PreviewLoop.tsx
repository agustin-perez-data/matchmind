import { useEffect, useMemo, useRef } from 'react'
import { AWAY_IDS, BEATS, HOME_IDS, LOOP_MS, STILL_T, buildKeyframes, interpolate, phaseAt, type Phase } from '../lib/preview'
import { PITCH_H, PITCH_W, PitchLines, Turf } from './PitchLines'

type Props = {
  home: { short_name: string; primary_color: string }
  away: { short_name: string; primary_color: string }
  /** The commentary line the lower third shows. */
  line: string
  /** The verdict stamp, e.g. "Called it · 66 %". */
  verdict: string
}

/**
 * Six seconds of the product, with nothing behind it: a scripted move on a real pitch, a lower third that
 * lands when the shot goes in, and the verdict stamp the Judge would put on the Analyst's call. The dots
 * are moved outside React by a requestAnimationFrame loop, like the live TrackingLayer; the loop stops
 * when the tab is hidden or the element scrolls away, and under reduced motion it shows the final frame.
 */
export function PreviewLoop({ home, away, line, verdict }: Props) {
  const keyframes = useMemo(() => buildKeyframes(), [])
  const root = useRef<HTMLDivElement | null>(null)
  const dots = useRef(new Map<string, SVGCircleElement>())
  const ball = useRef<SVGCircleElement | null>(null)

  useEffect(() => {
    const el = root.current
    if (!el) return
    const draw = (t: number) => {
      const pose = interpolate(keyframes, Math.min(t, BEATS.lowerThird))
      for (const [id, dot] of dots.current) {
        const p = pose.players[id]
        if (p) dot.setAttribute('transform', `translate(${p[0].toFixed(2)} ${p[1].toFixed(2)})`)
      }
      ball.current?.setAttribute('transform', `translate(${pose.ball[0].toFixed(2)} ${pose.ball[1].toFixed(2)})`)
      const phase: Phase = phaseAt(t)
      if (el.dataset.phase !== phase) el.dataset.phase = phase
    }
    const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      draw(STILL_T)
      return
    }
    let raf = 0
    let t0 = performance.now()
    let running = false
    const tick = (now: number) => {
      draw((now - t0) % LOOP_MS)
      raf = requestAnimationFrame(tick)
    }
    const start = () => { if (!running) { running = true; t0 = performance.now(); raf = requestAnimationFrame(tick) } }
    const stop = () => { if (running) { running = false; cancelAnimationFrame(raf) } }
    let visible = true
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (visible && !document.hidden) start(); else stop() }, { threshold: 0.2 })
    io.observe(el)
    const onVisibility = () => { if (document.hidden) stop(); else if (visible) start() }
    document.addEventListener('visibilitychange', onVisibility)
    return () => { stop(); io.disconnect(); document.removeEventListener('visibilitychange', onVisibility) }
  }, [keyframes])

  return (
    <div ref={root} className="preview relative w-full select-none" data-phase="play" aria-label={`Preview: ${line}; ${verdict}`} role="img">
      <svg viewBox={`0 0 ${PITCH_W} ${PITCH_H}`} className="block h-auto w-full" aria-hidden
        style={{ filter: 'drop-shadow(0 24px 36px rgba(0,0,0,.55))' }}>
        <Turf id="turf-preview" />
        <PitchLines />
        <g>
          {AWAY_IDS.map((id) => <circle key={id} r={1.35} fill={away.primary_color} stroke="#ffffff" strokeWidth={0.35} ref={(c) => { if (c) dots.current.set(id, c); else dots.current.delete(id) }} />)}
          {HOME_IDS.map((id) => <circle key={id} r={1.35} fill={home.primary_color} stroke="#0b0f1a" strokeWidth={0.3} ref={(c) => { if (c) dots.current.set(id, c); else dots.current.delete(id) }} />)}
          <circle ref={ball} r={0.9} fill="#ffffff" stroke="#0b0f1a" strokeWidth={0.25} />
        </g>
      </svg>
      <div className="preview-lt pointer-events-none absolute inset-x-3 bottom-3 sm:inset-x-5 sm:bottom-5">
        <div className="lt-bar display text-base font-black uppercase sm:text-lg">{home.short_name} v {away.short_name}</div>
        <div className="lt-sub text-sm sm:text-base">{line}</div>
      </div>
      <div className="preview-stamp display pointer-events-none absolute right-3 top-3 bg-amber px-3 py-1 text-sm font-black uppercase tracking-wide text-ink sm:right-5 sm:top-5 sm:text-base">{verdict}</div>
    </div>
  )
}
