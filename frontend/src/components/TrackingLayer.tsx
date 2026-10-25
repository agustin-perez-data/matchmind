import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { STALE_MS, attacksRight, convexHull, glideMs, lerpFrame, rosterKey } from '../lib/tracking'
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
  /** Shade each side's block (convex hull of the outfield players). */
  hull?: boolean
  /** Called when frames start or stop flowing; the pitch hides its event-driven ball while the layer is live. */
  onActive?: (active: boolean) => void
  /** Called when the side on the ball or the third it is in changes (rare), so the possession chip follows the frames. */
  onPossession?: (p: { team_id: string; x: number; y: number }) => void
}

/**
 * The 22 players and the ball from the positional model, moved outside React.
 *
 * Frames arrive up to once per match second and never touch React state: a requestAnimationFrame loop reads the
 * latest frame from `frameRef` and writes transforms straight onto the SVG groups. React only re-renders this
 * component when the roster changes (a substitution) or the glide duration changes (speed). The team blocks are
 * recomputed every animation frame from positions interpolated with the same linear timing as the dots' CSS
 * transition, so the shaded block moves with its players instead of jumping.
 */
export function TrackingLayer({ meta, frameRef, speed, followId, size, ended, hull = false, onActive, onPossession }: Props) {
  const [roster, setRoster] = useState<string[]>([])
  const rosterRef = useRef('')
  const els = useRef(new Map<string, SVGGElement>())
  const ballEl = useRef<SVGCircleElement | null>(null)
  const layerEl = useRef<SVGGElement | null>(null)
  const hullEls = useRef<Record<string, SVGPolygonElement | null>>({})
  const lastFrame = useRef<Frame | null>(null)
  const prevFrame = useRef<Frame | null>(null)
  const frameAt = useRef(0)
  const hullSettled = useRef(false)
  const carrier = useRef<string | null>(null)
  const active = useRef(false)
  const endedRef = useRef(ended)
  endedRef.current = ended
  const hullRef = useRef(hull)
  hullRef.current = hull
  const glideRef = useRef(glideMs(speed))
  glideRef.current = glideMs(speed)
  const players = useMemo(() => new Map(Object.values(meta.teams).flatMap((t) => t.players.map((p) => [p.player_id, { ...p, team_id: t.team_id }] as const))), [meta])
  const possTeam = useRef<string | null>(null)
  const possKey = useRef('')

  const place = (pid: string, el: SVGGElement, f: Frame) => {
    const p = f.players[pid]
    if (p) el.style.transform = `translate(${sx(p[0])}px, ${sy(p[1])}px)`
    el.classList.toggle('trk-carrier', f.carrier === pid)
  }

  useEffect(() => {
    let raf = 0
    const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
    const drawHulls = (positions: Record<string, [number, number]>) => {
      const byTeam: Record<string, [number, number][]> = { [meta.home_id]: [], [meta.away_id]: [] }
      for (const [pid, xy] of Object.entries(positions)) {
        const p = players.get(pid)
        if (p && p.position !== 'GK' && byTeam[p.team_id]) byTeam[p.team_id].push([sx(xy[0]), sy(xy[1])])
      }
      for (const tid of [meta.home_id, meta.away_id]) {
        const el = hullEls.current[tid]
        if (el) el.setAttribute('points', convexHull(byTeam[tid]).map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' '))
      }
    }
    const tick = () => {
      const f = frameRef.current
      const now = performance.now()
      const live = !!f && (endedRef.current || now - (f.at ?? 0) <= STALE_MS)
      if (live !== active.current) {
        active.current = live
        if (layerEl.current) layerEl.current.style.opacity = live ? '1' : '0.35'
        if (ballEl.current) ballEl.current.style.opacity = live ? '1' : '0'
        onActive?.(live)
      }
      if (f && f !== lastFrame.current) {
        prevFrame.current = lastFrame.current
        lastFrame.current = f
        frameAt.current = now
        hullSettled.current = false
        const key = rosterKey(f)
        if (key !== rosterRef.current) {
          rosterRef.current = key
          setRoster(Object.keys(f.players).sort())
        }
        for (const [pid, el] of els.current) place(pid, el, f)
        if (ballEl.current) ballEl.current.style.transform = `translate(${sx(f.ball[0])}px, ${sy(f.ball[1])}px)`
        carrier.current = f.carrier
        const team = f.carrier ? players.get(f.carrier)?.team_id ?? possTeam.current : possTeam.current
        if (team && onPossession) {
          possTeam.current = team
          const xTeam = attacksRight(meta, team, f.period) ? f.ball[0] : 100 - f.ball[0]
          const key = `${team}:${xTeam < 33 ? 0 : xTeam < 66 ? 1 : 2}`
          if (key !== possKey.current) {
            possKey.current = key
            onPossession({ team_id: team, x: f.ball[0], y: f.ball[1] })
          }
        }
      }
      // the blocks: follow the dots' glide, then rest until the next frame
      if (hullRef.current && f && !hullSettled.current) {
        const glide = glideRef.current
        const t = reduced || glide <= 0 ? 1 : Math.min(1, (now - frameAt.current) / glide)
        drawHulls(lerpFrame(prevFrame.current, f, t))
        if (t >= 1) hullSettled.current = true
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [frameRef, onActive, onPossession, players, meta])

  // switching the blocks on draws them at once from the last frame
  useEffect(() => { hullSettled.current = false }, [hull])

  // a dot mounted after a substitution takes its place at once instead of waiting for the next frame
  const mount = useCallback((pid: string) => (el: SVGGElement | null) => {
    if (el) {
      els.current.set(pid, el)
      if (lastFrame.current) place(pid, el, lastFrame.current)
    } else els.current.delete(pid)
  }, [])

  const transition = `transform ${glideMs(speed)}ms linear`
  const r = size === 'lg' ? 1.4 : 1.1

  return (
    <g ref={layerEl} className="trk" style={{ opacity: 0.35, transition: 'opacity 300ms linear' }} aria-label="players, from the positional model">
      {[meta.home_id, meta.away_id].map((tid) => (
        <polygon key={tid} ref={(el) => { hullEls.current[tid] = el }} className="trk-hull" points=""
          fill={tid === meta.home_id ? 'var(--home)' : 'var(--away)'} fillOpacity={0.16}
          stroke={tid === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'} strokeWidth={0.45} strokeOpacity={0.8} strokeLinejoin="round"
          style={{ display: hull ? undefined : 'none' }} />
      ))}
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
