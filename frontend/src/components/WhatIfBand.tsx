import { useEffect, useMemo, useState } from 'react'
import { getBranch, simulateBranch } from '../lib/api'
import type { BranchSummary, MatchEvent, Meta, Snapshot } from '../lib/types'
import { nameOf, scoreUpTo } from './SidePanels'
import { absMinute } from './Strip'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  actualEvents: MatchEvent[]
  branches: BranchSummary[]
  selected: BranchSummary | null
  onSelect: (b: BranchSummary | null) => void
  ended: boolean
}

const W = 1100, PL = 112, PR = 340, MAX = 96, Y1 = 30, Y2 = 78

export function WhatIfBand({ meta, snapshot, actualEvents, branches, selected, onSelect, ended }: Props) {
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

  const onPitch = useMemo(() => (snapshot ? Object.values(snapshot.players) : [])
    .filter((p) => p.team_id === form.team_id && p.on_pitch).sort((a, b) => b.acwr_live - a.acwr_live), [snapshot, form.team_id])

  const run = async () => {
    if (!form.player_off_id) return
    setBusy(true); setError(null)
    try { onSelect(await simulateBranch(meta.match_id, { minute: form.minute, action: 'substitution', team_id: form.team_id, player_off_id: form.player_off_id })) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  const h = meta.home_id, a = meta.away_id
  const x = (m: number) => PL + (m / MAX) * (W - PL - PR)
  const upTo = ended || !snapshot ? null : absMinute(snapshot)
  const knocks = (evs: MatchEvent[] | null) => (evs ?? []).filter((e) => e.type === 'injury_concern' && (upTo == null || absMinute(e) <= upTo)).map((e) => ({ minute: absMinute(e), name: e.player_name ?? '' }))
  const goalsOf = (side: BranchSummary['actual']) => side.goals.filter((g) => upTo == null || absMinute(g) <= upTo)
  const title = selected ? describeIntervention(meta, selected) : 'What if the bench had acted?'

  return (
    <section className="relative border-t-[3px] border-teal bg-gradient-to-r from-ink to-[#0f1626]">
      <div className="band-title -mt-[3px]">{title}</div>
      <div className="grid gap-3 px-4 pb-4 pt-3 sm:px-9">
        {selected ? (
          <svg key={selected.branch_id} viewBox={`0 0 ${W} 108`} className="w-full max-w-[1100px]" role="img" aria-label="Actual match and what-if branch timelines">
            <g className="display" fontFamily="Barlow Condensed" fontWeight={800} fontSize={16} fill="var(--color-muted)">
              <text x={0} y={Y1 + 6}>AS PLAYED</text><text x={0} y={Y2 + 6}>WITH THE CHANGE</text>
              {[0, 15, 30, 45, 60, 75, 90].map((m) => <text key={m} x={x(m)} y={104} fontSize={12} fontWeight={600} textAnchor="middle">{m}'</text>)}
            </g>
            <line x1={x(0)} x2={x(MAX)} y1={Y1} y2={Y1} stroke="#5c6782" strokeWidth={3} />
            <line x1={x(0)} x2={x(selected.divergence_minute)} y1={Y2} y2={Y2} stroke="#5c6782" strokeWidth={3} strokeOpacity={0.4} />
            <line className="draw" pathLength={1} x1={x(selected.divergence_minute)} x2={x(MAX)} y1={Y2} y2={Y2} stroke="var(--color-teal)" strokeWidth={3} />
            <line x1={x(selected.divergence_minute)} x2={x(selected.divergence_minute)} y1={8} y2={98} stroke="var(--color-amber)" strokeWidth={2} strokeDasharray="5 4" />
            <text x={x(selected.divergence_minute) + 8} y={14} fontSize={12} fill="var(--color-amber)" fontFamily="Barlow Condensed" fontWeight={700}>{selected.divergence_minute}'</text>
            {upTo != null && <rect x={x(upTo)} y={4} width={Math.max(0, x(MAX) - x(upTo))} height={96} fill="var(--color-ink)" fillOpacity={0.55} />}
            {upTo != null && <text x={x(upTo) + 6} y={56} fontSize={12} fill="var(--color-muted)" fontFamily="Barlow Condensed" fontWeight={700}>LIVE {upTo}', the rest stays hidden until full time</text>}
            <Marks y={Y1} goals={goalsOf(selected.actual)} knocks={knocks(actualEvents)} x={x} h={h} />
            <Marks y={Y2} goals={goalsOf(selected.branch)} knocks={knocks(branchEvents)} x={x} h={h} stagger />
            <g fontFamily="Barlow Condensed" fontWeight={800} fontSize={22} fill="#fff">
              <text x={x(MAX) + 18} y={Y1 + 7}>{scoreUpTo(selected.actual, h, a, upTo)[h]} - {scoreUpTo(selected.actual, h, a, upTo)[a]}</text>
              <text x={x(MAX) + 18} y={Y2 + 7} fill="var(--color-teal)">{scoreUpTo(selected.branch, h, a, upTo)[h]} - {scoreUpTo(selected.branch, h, a, upTo)[a]}</text>
            </g>
            <g fontFamily="Barlow" fontSize={13} fill="var(--color-muted)">
              <text x={x(MAX) + 80} y={Y1 + 6}>{knocks(actualEvents).length} knocks{upTo == null ? `, xG ${selected.actual.xg[h].toFixed(2)}-${selected.actual.xg[a].toFixed(2)}` : ''}</text>
              <text x={x(MAX) + 80} y={Y2 + 6}>{knocks(branchEvents).length} knocks{upTo == null ? `, xG ${selected.branch.xg[h].toFixed(2)}-${selected.branch.xg[a].toFixed(2)}` : ''}{selected.player_off ? `, ${selected.player_off.name} ${upTo == null ? selected.player_off.minutes_branch : Math.min(selected.player_off.minutes_branch, upTo)}'` : ''}</text>
            </g>
            {selected.status === 'skipped' && <text x={x(0)} y={Y2 - 14} fontSize={13} fill="var(--color-risk)">Not applied: that player was not on the pitch at that minute.</text>}
          </svg>
        ) : (
          <p className="max-w-prose text-base text-fg-2">Same seed, same match until the change, then the engine plays it out. Pick a player to take off, or open a Coach proposal, and the second timeline draws next to the real one.</p>
        )}

        <form className="flex flex-wrap items-end gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); void run() }}>
          <label className="flex flex-col gap-0.5 text-[11px] uppercase tracking-wider text-muted">Team
            <select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value, player_off_id: '' })}>
              {[h, a].map((t) => <option key={t} value={t}>{meta.teams[t].name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-0.5 text-[11px] uppercase tracking-wider text-muted">Take off
            <select value={form.player_off_id} onChange={(e) => setForm({ ...form, player_off_id: e.target.value })}>
              <option value="">riskiest first</option>
              {onPitch.map((p) => <option key={p.player_id} value={p.player_id}>{p.name} · ACWR {p.acwr_live} · {p.minutes_played}'</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-0.5 text-[11px] uppercase tracking-wider text-muted">At minute
            <input type="number" min={0} max={95} value={form.minute} className="w-20" onChange={(e) => setForm({ ...form, minute: Number(e.target.value) })} />
          </label>
          <button className="btn btn-teal" type="submit" disabled={busy || !form.player_off_id}>{busy ? 'Simulating' : 'Simulate'}</button>
          {branches.length > 0 && (
            <select value={selected?.branch_id ?? ''} onChange={(e) => onSelect(branches.find((b) => b.branch_id === e.target.value) ?? null)} aria-label="branches proposed by the Coach">
              <option value="">Coach proposals ({branches.length})</option>
              {branches.map((b) => <option key={b.branch_id} value={b.branch_id}>{describeIntervention(meta, b)}</option>)}
            </select>
          )}
          {error && <span className="basis-full text-bad">{error}</span>}
        </form>
      </div>
    </section>
  )
}

function Marks({ y, goals, knocks, x, h, stagger }: {
  y: number; goals: BranchSummary['actual']['goals']; knocks: { minute: number; name: string }[]; x: (m: number) => number; h: string; stagger?: boolean
}) {
  return (
    <g className={stagger ? 'stagger' : undefined}>
      {knocks.map((k, i) => (
        <g key={`k${i}`} className="enter-pop" style={{ ['--i' as string]: i + 2, transformOrigin: `${x(k.minute)}px ${y}px`, transformBox: 'view-box' }}>
          <line x1={x(k.minute)} x2={x(k.minute)} y1={y - 10} y2={y + 10} stroke="var(--color-bad)" strokeWidth={3} />
          <title>{k.minute}' knock: {k.name}</title>
        </g>
      ))}
      {goals.map((g, i) => (
        <g key={`g${i}`} className="enter-pop" style={{ ['--i' as string]: i + 2, transformOrigin: `${x(absMinute(g))}px ${y}px`, transformBox: 'view-box' }}>
          <circle cx={x(absMinute(g))} cy={y} r={9} fill={g.team_id === h ? 'var(--home)' : 'var(--away)'} stroke="var(--color-ink)" strokeWidth={3} />
          <title>{g.clock} goal {g.player_name}</title>
        </g>
      ))}
    </g>
  )
}

export function describeIntervention(meta: Meta, b: BranchSummary): string {
  const iv = b.intervention
  if (iv.type === 'substitution') return `What if ${nameOf(meta, String(iv.player_off_id))} comes off at ${iv.minute}'`
  return `What if ${meta.teams[String(iv.team_id)]?.short_name} changes tactics at ${iv.minute}'`
}
