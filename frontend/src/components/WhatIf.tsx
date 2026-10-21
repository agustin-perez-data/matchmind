import { useEffect, useMemo, useState } from 'react'
import { getBranch, simulateBranch } from '../lib/api'
import type { BranchSummary, MatchEvent, Meta, Snapshot } from '../lib/types'
import { nameOf } from './AgentFeed'
import { absMinute } from './XgRace'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  actualEvents: MatchEvent[] // key events seen so far in the real match
  branches: BranchSummary[]
  selected: BranchSummary | null
  onSelect: (b: BranchSummary | null) => void
}

const W = 720, ROW_H = 34, PAD_L = 70, PAD_R = 16, MAX_MIN = 96

export function WhatIf({ meta, snapshot, actualEvents, branches, selected, onSelect }: Props) {
  const [branchEvents, setBranchEvents] = useState<MatchEvent[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ team_id: meta.home_id, player_off_id: '', minute: 60 })

  useEffect(() => {
    setBranchEvents(null)
    if (!selected) return
    let alive = true
    getBranch(meta.match_id, selected.branch_id).then((b) => { if (alive) setBranchEvents(b.events) }).catch(() => undefined)
    return () => { alive = false }
  }, [selected, meta.match_id])

  const onPitch = useMemo(() => {
    const players = snapshot ? Object.values(snapshot.players) : []
    return players.filter((p) => p.team_id === form.team_id && p.on_pitch).sort((a, b) => b.acwr_live - a.acwr_live)
  }, [snapshot, form.team_id])

  const run = async () => {
    if (!form.player_off_id) return
    setBusy(true); setError(null)
    try {
      onSelect(await simulateBranch(meta.match_id, { minute: form.minute, action: 'substitution', team_id: form.team_id, player_off_id: form.player_off_id }))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const h = meta.home_id, a = meta.away_id
  const x = (m: number) => PAD_L + (m / MAX_MIN) * (W - PAD_L - PAD_R)
  const concernsOf = (events: MatchEvent[] | null) =>
    (events ?? []).filter((e) => e.type === 'injury_concern').map((e) => ({ minute: absMinute(e), name: e.player_name ?? '' }))
  const actualConcerns = concernsOf(actualEvents)

  return (
    <section className="panel p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="panel-title">What if the bench had acted?</h2>
        <span className="text-xs text-ink-3">same seed, same match until the change, then the engine plays it out</span>
      </div>

      <form className="mt-2 flex flex-wrap items-end gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); void run() }}>
        <label className="flex flex-col text-xs text-ink-3">Team
          <select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value, player_off_id: '' })}>
            {[h, a].map((t) => <option key={t} value={t}>{meta.teams[t].name}</option>)}
          </select>
        </label>
        <label className="flex flex-col text-xs text-ink-3">Take off
          <select value={form.player_off_id} onChange={(e) => setForm({ ...form, player_off_id: e.target.value })}>
            <option value="">player on the pitch, riskiest first</option>
            {onPitch.map((p) => <option key={p.player_id} value={p.player_id}>{p.name} · ACWR {p.acwr_live} · {p.minutes_played}'</option>)}
          </select>
        </label>
        <label className="flex flex-col text-xs text-ink-3">At minute
          <input type="number" min={0} max={95} value={form.minute} className="w-20" onChange={(e) => setForm({ ...form, minute: Number(e.target.value) })} />
        </label>
        <button className="btn" type="submit" disabled={busy || !form.player_off_id}>{busy ? 'Simulating' : 'Simulate the substitution'}</button>
        {branches.length > 0 && (
          <select className="ml-auto" value={selected?.branch_id ?? ''} onChange={(e) => onSelect(branches.find((b) => b.branch_id === e.target.value) ?? null)} aria-label="branches proposed by the Coach">
            <option value="">Coach proposals ({branches.length})</option>
            {branches.map((b) => <option key={b.branch_id} value={b.branch_id}>{describeIntervention(meta, b)}</option>)}
          </select>
        )}
      </form>
      {error && <p className="mt-2 text-sm text-bad">{error}</p>}

      {!selected && <p className="mt-3 text-sm text-ink-3">Pick a player and a minute, or open a Coach proposal from the feed. The two timelines below show the real match and the alternative one.</p>}

      {selected && (
        <div className="mt-3">
          <p className="text-sm text-ink-2">
            {describeIntervention(meta, selected)}
            {selected.status === 'skipped' && <span className="text-warn"> — not applied: that player was not on the pitch at that minute.</span>}
          </p>
          <svg viewBox={`0 0 ${W} ${ROW_H * 2 + 28}`} className="mt-2 w-full" role="img" aria-label="Actual match and what-if branch timelines">
            {[0, 15, 30, 45, 60, 75, 90].map((m) => (
              <g key={m}>
                <line x1={x(m)} x2={x(m)} y1={6} y2={ROW_H * 2 + 8} stroke="var(--color-line)" strokeWidth={0.8} />
                <text x={x(m)} y={ROW_H * 2 + 22} fontSize={10} textAnchor="middle" fill="var(--color-ink-3)">{m}'</text>
              </g>
            ))}
            <Timeline y={ROW_H / 2 + 6} label="Actual" side={selected.actual} concerns={actualConcerns} meta={meta} x={x} from={0} />
            <Timeline y={ROW_H * 1.5 + 6} label="What-if" side={selected.branch} concerns={concernsOf(branchEvents)} meta={meta} x={x} from={selected.divergence_minute} />
            <line x1={x(selected.divergence_minute)} x2={x(selected.divergence_minute)} y1={2} y2={ROW_H * 2 + 10} stroke="var(--color-amber)" strokeWidth={1.5} strokeDasharray="4 3" />
            <text x={x(selected.divergence_minute) + 4} y={10} fontSize={10} fill="var(--color-amber)">change at {selected.divergence_minute}'</text>
          </svg>

          <dl className="mt-2 grid grid-cols-[auto_1fr_1fr] gap-x-6 gap-y-1 text-sm">
            <dt className="text-ink-3"></dt><dd className="text-xs text-ink-3">actual</dd><dd className="text-xs text-ink-3">what-if</dd>
            <dt className="text-ink-2">Score</dt>
            <dd className="tabular-nums">{selected.actual.score[h]} : {selected.actual.score[a]}</dd>
            <dd className="tabular-nums font-semibold">{selected.branch.score[h]} : {selected.branch.score[a]}</dd>
            <dt className="text-ink-2">Expected goals</dt>
            <dd className="tabular-nums">{selected.actual.xg[h].toFixed(2)} : {selected.actual.xg[a].toFixed(2)}</dd>
            <dd className="tabular-nums">{selected.branch.xg[h].toFixed(2)} : {selected.branch.xg[a].toFixed(2)}</dd>
            <dt className="text-ink-2">Knocks</dt>
            <dd className="tabular-nums">{selected.actual.injury_concerns_total}</dd>
            <dd className="tabular-nums">{selected.branch.injury_concerns_total}</dd>
            {selected.player_off && (
              <>
                <dt className="text-ink-2">{selected.player_off.name} played</dt>
                <dd className="tabular-nums">{selected.player_off.minutes_actual}'</dd>
                <dd className="tabular-nums">{selected.player_off.minutes_branch}'</dd>
              </>
            )}
          </dl>
        </div>
      )}
    </section>
  )
}

function Timeline({ y, label, side, concerns, meta, x, from }: {
  y: number; label: string; side: BranchSummary['actual']; concerns: { minute: number; name: string }[]
  meta: Meta; x: (m: number) => number; from: number
}) {
  const h = meta.home_id
  return (
    <g>
      <text x={PAD_L - 8} y={y + 4} fontSize={12} textAnchor="end" fill="var(--color-ink-2)" fontFamily="Barlow Condensed" fontWeight={600}>{label}</text>
      {from > 0 && <line x1={x(0)} x2={x(from)} y1={y} y2={y} stroke="var(--color-ink-3)" strokeWidth={2} strokeOpacity={0.35} />}
      <line x1={x(from)} x2={x(MAX_MIN)} y1={y} y2={y} stroke="var(--color-ink-2)" strokeWidth={2} />
      {concerns.map((c, i) => (
        <g key={i}>
          <line x1={x(c.minute)} x2={x(c.minute)} y1={y - 9} y2={y + 9} stroke="var(--color-bad)" strokeWidth={2} />
          <title>{c.minute}' knock: {c.name}</title>
        </g>
      ))}
      {side.goals.map((g, i) => (
        <g key={i}>
          <circle cx={x(absMinute(g))} cy={y} r={7} fill={g.team_id === h ? 'var(--color-home)' : 'var(--color-away)'} stroke="var(--color-panel)" strokeWidth={2} />
          <title>{g.clock} goal {g.player_name} ({meta.teams[g.team_id]?.short_name})</title>
        </g>
      ))}
    </g>
  )
}

function describeIntervention(meta: Meta, b: BranchSummary): string {
  const iv = b.intervention
  if (iv.type === 'substitution') return `${nameOf(meta, String(iv.player_off_id))} off at ${iv.minute}' (${meta.teams[String(iv.team_id)]?.short_name})`
  return `${meta.teams[String(iv.team_id)]?.short_name} tactics at ${iv.minute}': press ${iv.press_intensity ?? 'same'}, ${iv.style ?? 'same style'}`
}
