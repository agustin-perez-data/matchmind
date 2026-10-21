import type { Meta, Snapshot } from '../lib/types'

type Props = { meta: Meta; snapshot: Snapshot | null }

export function MomentumBar({ meta, snapshot }: Props) {
  const m = snapshot?.momentum ?? 0
  const series = snapshot?.momentum_series.slice(-30) ?? []
  const h = meta.teams[meta.home_id], a = meta.teams[meta.away_id]
  const leader = Math.abs(m) < 0.15 ? 'balanced' : m > 0 ? `${h.short_name} pushing` : `${a.short_name} pushing`
  return (
    <section className="panel p-3">
      <h2 className="panel-title">Momentum</h2>
      <div className="mt-2 flex items-center justify-between text-xs text-ink-3">
        <span>{a.short_name}</span><span className="text-ink-2">{leader}</span><span>{h.short_name}</span>
      </div>
      <div className="relative mt-1 h-4 rounded-sm bg-panel-2" role="meter" aria-valuemin={-1} aria-valuemax={1} aria-valuenow={m} aria-label="momentum, positive favours the home side">
        <div className="absolute inset-y-0 left-1/2 w-px bg-ink-3" />
        <div className="absolute inset-y-1 rounded-sm" style={{
          left: m >= 0 ? '50%' : `${50 + m * 50}%`, width: `${Math.abs(m) * 50}%`,
          background: m >= 0 ? 'var(--color-home)' : 'var(--color-away)',
        }} />
      </div>
      <svg viewBox="0 0 300 50" className="mt-2 w-full" role="img" aria-label="momentum over the last minutes">
        <line x1={0} x2={300} y1={25} y2={25} stroke="var(--color-line)" />
        {series.map((p, i) => {
          const x = (i / Math.max(1, series.length - 1)) * 296 + 2
          const hgt = Math.abs(p.value) * 22
          return <rect key={`${p.period}-${p.minute}`} x={x - 3} y={p.value >= 0 ? 25 - hgt : 25} width={6} height={hgt} rx={1}
            fill={p.value >= 0 ? 'var(--color-home)' : 'var(--color-away)'} />
        })}
      </svg>
      <p className="text-xs text-ink-3">Attacking events push the bar towards the attacking side and fade with time.</p>
    </section>
  )
}
