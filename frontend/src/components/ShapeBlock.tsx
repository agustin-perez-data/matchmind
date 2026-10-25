import type { Meta, Snapshot } from '../lib/types'

/** Team shape from the positional model: how high, how wide and how tight each block is, and who presses. */
export function ShapeBlock({ meta, snapshot, ended = false }: { meta: Meta; snapshot: Snapshot | null; ended?: boolean }) {
  const sh = snapshot?.shape
  const h = sh?.[meta.home_id], a = sh?.[meta.away_id]
  if (!h || !a) {
    return (
      <section className="blk px-4 py-3">
        <h2 className="blk-title">Team shape</h2>
        <p className="mt-2 text-sm text-muted">Positions arrive with the first frames after kick off.</p>
      </section>
    )
  }
  const home = meta.teams[meta.home_id], away = meta.teams[meta.away_id]
  const press = snapshot?.press_index, last = snapshot?.shape_last_10, pressure = snapshot?.pressure
  const m = (v: number) => `${v.toFixed(0)} m`
  const delta = (tid: string) => {
    const d = last?.[tid]?.delta_vs_match_m
    if (d == null) return '–'
    const r = Math.round(d)
    return r === 0 ? 'level' : `${r > 0 ? '+' : ''}${r} m`
  }
  const rows: [string, string, string][] = [
    ['block height', m(h.block_height_m), m(a.block_height_m)],
    ['width', m(h.width_m), m(a.width_m)],
    ['compactness', m(h.compactness_m), m(a.compactness_m)],
    ['last 10 min', delta(meta.home_id), delta(meta.away_id)],
    ['press index', press?.[meta.home_id]?.toFixed(1) ?? '–', press?.[meta.away_id]?.toFixed(1) ?? '–'],
  ]
  const carrierName = pressure?.carrier ? snapshot?.players[pressure.carrier]?.name ?? pressure.carrier : null
  return (
    <section className="blk px-4 py-3">
      <div className="flex items-baseline justify-between" title="Block height is the outfield mean distance from the own goal; compactness the mean distance to the block's centre; the press index counts opponents near the carrier while defending."><h2 className="blk-title">Team shape</h2><span className="blk-meta">{snapshot?.clock}</span></div>
      {ended ? (
        <div className="display mt-2 text-center text-sm font-extrabold uppercase tracking-wider text-fg-2">full time · final shape</div>
      ) : (
        <div className="display mt-2 grid grid-cols-[1fr_auto_1fr] items-center text-sm font-extrabold uppercase tracking-wider">
          <span style={{ color: 'var(--home-ink)' }}>{home.short_name} {h.phase}</span>
          <span className="blk-meta px-3 text-xs">now</span>
          <span className="text-right" style={{ color: 'var(--away-ink)' }}>{away.short_name} {a.phase}</span>
        </div>
      )}
      <dl className="mt-1">
        {rows.map(([label, hv, av]) => (
          <div key={label} className="display grid grid-cols-[1fr_auto_1fr] items-center border-b border-line py-0.5 text-[26px] font-extrabold leading-tight last:border-0">
            <dd className="m-0 tabular-nums" style={{ color: 'var(--home-ink)' }}>{hv}</dd>
            <dt className="blk-meta px-3 text-xs">{label}</dt>
            <dd className="m-0 text-right tabular-nums" style={{ color: 'var(--away-ink)' }}>{av}</dd>
          </div>
        ))}
      </dl>
      {!ended && carrierName && pressure && (
        <p className={`mt-2 text-sm ${pressure.under_pressure ? 'text-amber' : 'text-fg-2'}`}>
          <b>{carrierName}</b> on the ball, {pressure.opponents_within_8m} opponent{pressure.opponents_within_8m === 1 ? '' : 's'} within 8 m{pressure.under_pressure ? ': under pressure' : ''}.
        </p>
      )}
      <p className="mt-2 text-xs text-muted">Metres, from the positional model built on the event stream, not tracking data.</p>
    </section>
  )
}
