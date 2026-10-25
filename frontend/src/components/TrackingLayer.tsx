import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { STALE_MS, glideMs, rosterKey } from '../lib/tracking'
import type { Frame, Meta } from '../lib/types'

const W = 105, H = 68
const sx = (x: number) => (x / 100) * W
const sy = (y: number) => (y / 100) * H

type Props = {
  meta: Meta
  frameRef: RefObject<Frame | null>
  speed: number
  followId: string | null
  size: 'lg' | 'sm'
  ended: boolean
  /** Called when frames start or stop flowing; the pitch hides its event-driven ball while the layer is live. */
  onActive?: (active: boolean) => void
}

/**
 * The 22 players and the ball from the positional model, moved outside React.
 *
 * Frames arrive up to once per match second and never touch React state: a requestAnimationFrame loop reads the
 * latest frame from `frameRef` and writes transforms straight onto the SVG groups. React only re-renders this
 * component when the roster changes (a substitution) or the glide duration changes (speed).
 */
export function TrackingLayer({ meta, frameRef, speed, followId, size, ended, onActive }: Props) {
  const [roster, setRoster] = useState<string[]>([])
  const rosterRef = useRef('')
  const els = useRef(new Map<string, SVGGElement>())
  const ballEl = useRef<SVGCircleElement | null>(null)
  const layerEl = useRef<SVGGElement | null>(null)
  const lastFrame = useRef<Frame | null>(null)
  const carrier = useRef<string | null>(null)
  const active = useRef(false)
  const endedRef = useRef(ended)
  endedRef.current = ended

  const place = (pid: string, el: SVGGElement, f: Frame) => {
    const p = f.players[pid]
    if (p) el.style.transform = `translate(${sx(p[0])}px, ${sy(p[1])}px)`
    el.classList.toggle('trk-carrier', f.carrier === pid)
  }

  useEffect(() => {
    let raf = 0
    const tick = () => {
      const f = frameRef.current
      const live = !!f && (endedRef.current || performance.now() - (f.at ?? 0) <= STALE_MS)
      if (live !== active.current) {
        active.current = live
        if (layerEl.current) layerEl.current.style.opacity = live ? '1' : '0.35'
        if (ballEl.current) ballEl.current.style.opacity = live ? '1' : '0'
        onActive?.(live)
      }
      if (f && f !== lastFrame.current) {
        lastFrame.current = f
        const key = rosterKey(f)
        if (key !== rosterRef.current) {
          rosterRef.current = key
          setRoster(Object.keys(f.players).sort())
        }
        for (const [pid, el] of els.current) place(pid, el, f)
        if (ballEl.current) ballEl.current.style.transform = `translate(${sx(f.ball[0])}px, ${sy(f.ball[1])}px)`
        carrier.current = f.carrier
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [frameRef, onActive])

  // a dot mounted after a substitution takes its place at once instead of waiting for the next frame
  const mount = useCallback((pid: string) => (el: SVGGElement | null) => {
    if (el) {
      els.current.set(pid, el)
      if (lastFrame.current) place(pid, el, lastFrame.current)
    } else els.current.delete(pid)
  }, [])

  const players = new Map(Object.values(meta.teams).flatMap((t) => t.players.map((p) => [p.player_id, { ...p, team_id: t.team_id }] as const)))
  const transition = `transform ${glideMs(speed)}ms linear`
  const r = size === 'lg' ? 1.4 : 1.1

  return (
    <g ref={layerEl} className="trk" style={{ opacity: 0.35, transition: 'opacity 300ms linear' }} aria-label="players, from the positional model">
      {roster.map((pid) => {
        const p = players.get(pid)
        const fill = p?.team_id === meta.home_id ? 'var(--home)' : 'var(--away)'
        const followed = pid === followId
        return (
          <g key={pid} ref={mount(pid)} className="trk-dot" style={{ transition }}>
            <circle className="trk-ring" r={r + 0.8} fill="none" stroke="#fff" strokeWidth={0.45} />
            {followed && <circle r={r + 1.2} fill="none" stroke="var(--color-amber)" strokeWidth={0.55} />}
            <circle r={r} fill={fill} stroke={p?.position === 'GK' ? '#fff' : '#0b0f1a'} strokeWidth={p?.position === 'GK' ? 0.35 : 0.25} />
            {followed && p && (
              <text y={-(r + 2)} textAnchor="middle" fontSize={2.8} fontFamily="Barlow Condensed" fontWeight={800} fill="var(--color-amber)" stroke="#0b0f1a" strokeWidth={0.5} style={{ paintOrder: 'stroke' }}>
                {p.name.split(' ').slice(-1)[0].toUpperCase()}
              </text>
            )}
            {size === 'lg' && !followed && p && (
              <text className="trk-num" y={-(r + 1.4)} textAnchor="middle" fontSize={2.4} fontFamily="Barlow Condensed" fontWeight={800} fill="#fff" stroke="#0b0f1a" strokeWidth={0.5} style={{ paintOrder: 'stroke' }}>
                {p.shirt_number} {p.name.split(' ').slice(-1)[0].toUpperCase()}
              </text>
            )}
            <title>{p ? `${p.shirt_number} ${p.name}` : pid}</title>
          </g>
        )
      })}
      <circle ref={ballEl} className="trk-dot" style={{ transition, opacity: 0 }} r={1.2} fill="#fff" stroke="#0b0f1a" strokeWidth={0.35} />
    </g>
  )
}
