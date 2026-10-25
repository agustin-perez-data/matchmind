import { subBudget } from '../lib/bench'
import type { MatchEvent, Meta, Snapshot } from '../lib/types'

type Props = { meta: Meta; snapshot: Snapshot | null; keyEvents: MatchEvent[] }

const mean = (xs: number[]) => (xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : null)

/** Collective load per side: where the block sits by half, how hard the side presses, how the XI's pace holds, changes used. */
export function TeamLoadBlock({ meta, snapshot, keyEvents }: Props) {
  const h = meta.home_id, a = meta.away_id
  if (!snapshot) {
    return <section className="blk px-4 py-3"><h2 className="blk-title">Team load</h2><p className="mt-2 text-sm text-muted">Waiting for kick off.</p></section>
  }
  const series = snapshot.block_series ?? []
  const blockBy = (tid: string, period: number) => mean(series.filter((p) => p.period === period && typeof p[tid] === 'number').map((p) => p[tid]))
  const outfield = (tid: string) => Object.values(snapshot.players).filter((p) => p.team_id === tid && p.on_pitch && p.position !== 'GK')
  const effort = (tid: string) => mean(outfield(tid).filter((p) => p.minutes_played >= 10).map((p) => p.effort_ratio_recent))
  const mpm = (tid: string) => mean(outfield(tid).filter((p) => p.minutes_played > 0).map((p) => p.distance_m / p.minutes_played))
  const fmtM = (v: number | null) => (v == null ? '–' : `${Math.round(v)} m`)
  const block = (tid: string) => {
    const b1 = blockBy(tid, 1), b2 = blockBy(tid, 2)
    return b1 == null ? '–' : b2 == null ? fmtM(b1) : `${Math.round(b1)} → ${Math.round(b2)} m`
  }
  const rows: [string, string, string, string][] = [
    ['block height, 1st → 2nd half', block(h), block(a), 'mean distance of the outfield block from its own goal, by half; a sinking block is a tired or pinned side'],
    ['press index', snapshot.press_index?.[h]?.toFixed(1) ?? '–', snapshot.press_index?.[a]?.toFixed(1) ?? '–', 'mean opponents within 8 m of the ball carrier while defending'],
    ['recent effort, XI', pctOf(effort(h)), pctOf(effort(a)), 'last five minutes against the position norm, outfield players with 10+ minutes'],
    ['metres per minute, XI', mpm(h) == null ? '–' : `${Math.round(mpm(h)!)}`, mpm(a) == null ? '–' : `${Math.round(mpm(a)!)}`, 'match average per outfield player on the pitch'],
    ['changes used', `${subBudget(keyEvents, h).used} · ${subBudget(keyEvents, h).windows} win.`, `${subBudget(keyEvents, a).used} · ${subBudget(keyEvents, a).windows} win.`, 'substitutions made and stoppages used (five in three)'],
  ]
  return (
    <section className="blk px-4 py-3">
      <div className="flex items-baseline justify-between"><h2 className="blk-title">Team load</h2><span className="blk-meta">{snapshot.clock}</span></div>
      <dl className="mt-2">
        {rows.map(([label, hv, av, tip]) => (
          <div key={label} className="display grid grid-cols-[1fr_auto_1fr] items-center border-b border-line py-0.5 text-[22px] font-extrabold leading-tight last:border-0" title={tip}>
            <dd className="m-0 tabular-nums" style={{ color: 'var(--home-ink)' }}>{hv}</dd>
            <dt className="blk-meta px-3 text-center text-[11px]">{label}</dt>
            <dd className="m-0 text-right tabular-nums" style={{ color: 'var(--away-ink)' }}>{av}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-muted">Block and press from the positional model built on the event stream; effort and metres from the workload samples.</p>
    </section>
  )
}

function pctOf(v: number | null): string {
  return v == null ? '–' : `${Math.round(v * 100)}%`
}
