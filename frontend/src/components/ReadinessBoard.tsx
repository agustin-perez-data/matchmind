import { useCallback, useLayoutEffect, useMemo, useRef } from 'react'
import { FADING_MIN_MINUTES, FADING_RATIO, FRESH_MINUTES, WINDOW_THRESHOLD, availableSubs, currentHazard, effortDelta, orderKey, readiness, subBudget, subbedOff, type Readiness } from '../lib/bench'
import { calibrationNote } from '../lib/calibration'
import type { MatchEvent, Meta, PlayerView, RiskMsg, RiskWindow, Snapshot } from '../lib/types'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  risk: RiskMsg | null
  keyEvents: MatchEvent[]
  team: string
  onTeam: (tid: string) => void
  focus: string | null
  onFocus: (pid: string | null) => void
}

const STATE_STYLE: Record<Readiness, string> = {
  'at risk': 'bg-risk/20 text-risk',
  fading: 'bg-amber/20 text-amber',
  fresh: 'bg-teal/20 text-teal',
  steady: 'bg-white/8 text-fg-2',
}
const HIGH_STYLE = 'bg-bad/20 text-bad'
const GK_NOTE = 'the load model is not position-aware: a goalkeeper can rank on minutes alone'

const surname = (name: string) => name.split(' ').slice(-1)[0]
const chipFor = (state: Readiness, window: RiskWindow | null) => (window?.level === 'high' ? { text: 'at risk · high', cls: HIGH_STYLE } : { text: state, cls: STATE_STYLE[state] })

/** The bench's first screen: the XI as a readiness board, sorted by hazard, with the substitutes still available and the change budget. */
export function ReadinessBoard({ meta, snapshot, risk, keyEvents, team, onTeam, focus, onFocus }: Props) {
  const players = snapshot?.players ?? {}
  const series = risk?.hazard_series
  const windows = useMemo(() => new Map((risk?.active_windows ?? []).map((w) => [w.player_id, w])), [risk])
  const xi = useMemo(() => Object.values(players)
    .filter((p) => p.team_id === team && p.on_pitch)
    .map((p) => ({ p, hazard: currentHazard(series, p.player_id), window: windows.get(p.player_id) ?? null }))
    .sort((a, b) => (b.hazard ?? -1) - (a.hazard ?? -1) || a.p.shirt_number - b.p.shirt_number), [players, team, series, windows])
  const bench = useMemo(() => availableSubs(players, team), [players, team])
  const off = useMemo(() => subbedOff(players, team), [players, team])
  const budget = subBudget(keyEvents, team)
  const focused = focus ? players[focus] ?? null : null
  const info = meta.teams[team]
  const ink = team === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)'

  // FLIP: when the order changes, cards glide from where they were to where they are (Web Animations API)
  const els = useRef(new Map<string, HTMLButtonElement>())
  const rects = useRef(new Map<string, DOMRect>())
  const lastOrder = useRef('')
  const order = orderKey(xi.map((x) => x.p.player_id))
  useLayoutEffect(() => {
    const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
    const reordered = lastOrder.current !== '' && lastOrder.current !== order
    lastOrder.current = order
    const next = new Map<string, DOMRect>()
    for (const [pid, el] of els.current) {
      const now = el.getBoundingClientRect()
      const was = rects.current.get(pid)
      if (reordered && was && !reduced) {
        const dx = was.left - now.left, dy = was.top - now.top
        if (dx || dy) el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 400, easing: 'cubic-bezier(.2,.8,.2,1)' })
      }
      next.set(pid, now)
    }
    rects.current = next // every commit, so a resize or a wrapped row never leaves a stale starting point
  })
  const mount = useCallback((pid: string) => (el: HTMLButtonElement | null) => { if (el) els.current.set(pid, el); else els.current.delete(pid) }, [])

  return (
    <section className="blk blk-risk px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="blk-title">Readiness</h2>
          <div className="flex gap-1.5" role="radiogroup" aria-label="team">
            {[meta.home_id, meta.away_id].map((tid) => {
              const on = tid === team
              return (
                <button key={tid} type="button" role="radio" aria-checked={on} onClick={() => onTeam(tid)}
                  className={`display px-3 py-1 text-sm font-extrabold uppercase tracking-wider transition-[background,color] duration-150 ${on ? 'bg-amber text-ink' : 'bg-white/5 hover:bg-white/12'}`}
                  style={on ? undefined : { color: tid === meta.home_id ? 'var(--home-ink)' : 'var(--away-ink)' }}>
                  {meta.teams[tid].short_name}
                </button>
              )
            })}
          </div>
        </div>
        <span className={`display text-sm font-extrabold uppercase tracking-wider ${budget.exhausted ? 'text-bad' : 'text-fg-2'}`} title="five changes in three stoppages; the half-time break is free">
          {budget.left} change{budget.left === 1 ? '' : 's'} left · {budget.windowsLeft} window{budget.windowsLeft === 1 ? '' : 's'}
        </span>
      </div>

      {!snapshot ? (
        <p className="mt-2 text-sm text-muted">Waiting for kick off.</p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6" role="listbox" aria-label={`${info.name} players on the pitch`}>
            {xi.map(({ p, hazard, window }) => {
              const r = readiness(p, window)
              const chip = chipFor(r.state, window)
              const delta = effortDelta(p)
              const on = p.player_id === focus
              const note = hazard != null && hazard >= WINDOW_THRESHOLD ? calibrationNote(hazard) : null
              return (
                <button key={p.player_id} ref={mount(p.player_id)} type="button" role="option" aria-selected={on} onClick={() => onFocus(on ? null : p.player_id)}
                  className={`rb-card min-w-0 border px-2 py-1.5 text-left transition-[border-color,background] duration-150 ${on ? 'border-amber bg-amber/10' : 'border-white/10 bg-white/[0.03] hover:border-white/30'}`}
                  title={`${p.name} · ${r.reason}${p.position === 'GK' ? ` · ${GK_NOTE}` : ''}`}>
                  <div className="flex items-baseline justify-between gap-1">
                    <span className="display truncate text-base font-extrabold uppercase leading-none"><span className="tabular-nums" style={{ color: ink }}>{p.shirt_number}</span> {surname(p.name)}</span>
                    <span className="blk-meta shrink-0 text-[10px]">{p.position} · {p.minutes_played}'</span>
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <span className="relative block h-2 flex-1 bg-ink-2" aria-hidden>
                      <span className="absolute inset-y-0 w-px bg-white/40" style={{ left: `${WINDOW_THRESHOLD * 100}%` }} />
                      <span className="block h-full" style={{ width: `${Math.round((hazard ?? 0) * 100)}%`, background: 'linear-gradient(90deg,#f97316,#e8405a)' }} />
                    </span>
                    <span className="display w-9 text-right text-sm font-extrabold tabular-nums">{hazard == null ? '–' : hazard.toFixed(2)}</span>
                  </div>
                  <div className="mt-1 text-[11px] leading-tight text-fg-2">
                    <span className="tabular-nums">ACWR {p.acwr_live.toFixed(2)}</span> <span className="text-muted">(pre {p.acwr_pre_match.toFixed(2)})</span>
                    <span className="text-muted"> · effort </span><span className={`tabular-nums ${delta != null && delta <= -12 ? 'text-amber' : ''}`}>{delta == null ? '–' : `${delta > 0 ? '+' : ''}${delta}%`}</span>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-1">
                    <span className={`display px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${chip.cls}`}>{chip.text}</span>
                    {window && <span className="blk-meta shrink-0 text-[10px]">since {window.open_minute}'</span>}
                  </div>
                  {note && <div className="rb-note mt-1 text-[10px] leading-tight text-muted">{note}</div>}
                </button>
              )
            })}
          </div>

          {focused && (
            <FocusStrip key={focused.player_id} p={focused} hazard={currentHazard(series, focused.player_id)} window={windows.get(focused.player_id) ?? null} />
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <span className="blk-meta text-[11px]">Bench</span>
            {bench.length === 0 && <span className="text-muted">no substitutes left</span>}
            {bench.map((s) => {
              const match = focused ? s.position === focused.position : false
              return (
                <span key={s.player_id} className={`display inline-flex items-center gap-1.5 px-2 py-0.5 text-sm font-bold uppercase tracking-wide ${match ? 'bg-teal/20 text-teal' : 'bg-white/5 text-fg-2'}`} title={`${s.name}, fresh${match ? `: same position as ${surname(focused!.name)}` : ''}`}>
                  <span className="text-[10px] text-muted">{s.position}</span>{s.shirt_number} {surname(s.name)}
                </span>
              )
            })}
            {off.length > 0 && <span className="text-muted">· off: {off.map((p) => `${surname(p.name)} ${p.minutes_played}'`).join(', ')}</span>}
          </div>
          <p className="mt-2 text-xs text-muted">
            Hazard from the Risk Monitor (0 to 1), updated with every workload sample, every five match minutes; a window opens at {WINDOW_THRESHOLD.toFixed(2)} within the five highest on the pitch. ACWR is the acute:chronic workload ratio (7-day over 28-day load). Effort compares the last five minutes with the player's own match pace: fading = {Math.round((1 - FADING_RATIO) * 100)}% under it with {FADING_MIN_MINUTES}+ minutes; fresh = under {FRESH_MINUTES} minutes. The load model does not distinguish positions, so a goalkeeper can rank. Decision support, not medical advice.
          </p>
        </>
      )}
    </section>
  )
}

/** The focused player in one line: why he is in that state, and what windows like his did in the calibration. */
function FocusStrip({ p, hazard, window }: { p: PlayerView; hazard: number | null; window: RiskWindow | null }) {
  const r = readiness(p, window)
  const delta = effortDelta(p)
  const note = hazard != null ? calibrationNote(hazard) : null
  return (
    <div className="rb-focus enter mt-2 border-l-2 border-amber px-3 py-1.5 text-sm text-fg-2">
      <b className="text-fg">{p.shirt_number} {p.name}</b> · {p.position} · {p.minutes_played}' · <span className="capitalize">{r.state}</span>: {r.reason}
      {hazard != null && <> · hazard <b className="text-fg tabular-nums">{hazard.toFixed(2)}</b></>}
      <span> · ACWR {p.acwr_live.toFixed(2)} (pre {p.acwr_pre_match.toFixed(2)}), 7-day over 28-day load</span>
      {delta != null && <> · effort {delta > 0 ? '+' : ''}{delta}% vs own pace</>}
      {note && <span className="text-muted"> · {note}</span>}
      {!note && hazard != null && hazard < WINDOW_THRESHOLD && <span className="text-muted"> · below the window threshold: no calibration bin</span>}
      {p.position === 'GK' && <span className="text-muted"> · {GK_NOTE}</span>}
    </div>
  )
}
