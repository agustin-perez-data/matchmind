import { useEffect, useMemo, useState } from 'react'
import { simulateBranch } from '../lib/api'
import { availableSubs, currentHazard, subBudget } from '../lib/bench'
import type { BranchSummary, CoachMsg, MatchEvent, Meta, RiskMsg, Snapshot } from '../lib/types'
import { nameOf, scoreUpTo } from './SidePanels'
import { absMinute } from './Strip'
import { describeIntervention } from './WhatIfBand'

type Props = {
  meta: Meta
  snapshot: Snapshot | null
  risk: RiskMsg | null
  coach: CoachMsg | null
  branches: BranchSummary[]
  selected: BranchSummary | null
  onSelect: (b: BranchSummary | null) => void
  keyEvents: MatchEvent[]
  team: string
  focus: string | null
  ended: boolean
  className?: string
}

/** What the bench can do about it: the Coach's latest proposal with its counterfactual, and a form to try a change of your own. */
export function DecisionCard({ meta, snapshot, risk, coach, branches, selected, onSelect, keyEvents, team, focus, ended, className = '' }: Props) {
  const h = meta.home_id, a = meta.away_id
  const now = snapshot ? absMinute(snapshot) : 0
  const [form, setForm] = useState({ team_id: team, player_off_id: focus ?? '', player_on_id: '', minute: Math.min(95, Math.max(1, now + 1)) })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [minuteTouched, setMinuteTouched] = useState(false)
  // until the bench edits it, the minute follows the match (the next minute), so a change is always tried from now
  useEffect(() => { if (!minuteTouched && now > 0 && !ended) setForm((f) => ({ ...f, minute: Math.min(95, Math.max(1, now + 1)) })) }, [now, minuteTouched, ended])
  useEffect(() => { setForm((f) => ({ ...f, team_id: team, player_off_id: '' })) }, [team])
  useEffect(() => { if (focus) setForm((f) => ({ ...f, team_id: snapshot?.players[focus]?.team_id ?? f.team_id, player_off_id: focus, player_on_id: '' })) }, [focus, snapshot])

  const players = snapshot?.players ?? {}
  const onPitch = useMemo(() => Object.values(players).filter((p) => p.team_id === form.team_id && p.on_pitch)
    .sort((x, y) => (currentHazard(risk?.hazard_series, y.player_id) ?? 0) - (currentHazard(risk?.hazard_series, x.player_id) ?? 0)), [players, form.team_id, risk])
  const offPlayer = form.player_off_id ? players[form.player_off_id] : null
  const bench = useMemo(() => {
    const subs = availableSubs(players, form.team_id)
    return offPlayer ? [...subs.filter((s) => s.position === offPlayer.position), ...subs.filter((s) => s.position !== offPlayer.position)] : subs
  }, [players, form.team_id, offPlayer])
  // the budget as it stood at the chosen minute: a branch diverges there, so later real changes do not count against it
  const budgetThen = subBudget(keyEvents.filter((e) => absMinute(e) <= form.minute), form.team_id)

  const run = async () => {
    if (!form.player_off_id) return
    setBusy(true); setError(null)
    try {
      onSelect(await simulateBranch(meta.match_id, { minute: form.minute, action: 'substitution', team_id: form.team_id, player_off_id: form.player_off_id, ...(form.player_on_id ? { player_on_id: form.player_on_id } : {}) }))
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const p = coach?.proposal, b = coach?.branch
  const upTo = ended || !snapshot ? null : now
  const sa = b ? scoreUpTo(b.actual, h, a, upTo) : null, sb = b ? scoreUpTo(b.branch, h, a, upTo) : null
  const what = !coach ? null : !p ? 'No decision' : p.action === 'hold' ? `Hold, no change at ${coach.clock}`
    : p.action === 'substitution' ? `${nameOf(meta, p.player_off_id)} off at ${p.minute}'${p.player_on_id ? `, ${nameOf(meta, p.player_on_id)} on` : ''}`
      : `Tactics at ${p.minute}': press ${p.press_intensity ?? 'same'}, ${p.style ?? 'same style'}`
  const openWindows = risk?.active_windows.length ?? 0
  const budgetNow = subBudget(keyEvents, team)

  return (
    <section className={`blk blk-coach px-4 py-3 ${className}`}>
      <div className="flex items-baseline justify-between"><h2 className="blk-title">Decision</h2><span className="blk-meta">{coach ? `Coach proposal at ${coach.clock}` : 'the Coach is on the bench'}</span></div>

      {!coach ? (
        <div className="mt-2 text-sm text-fg-2">
          <p><b className="text-fg">{meta.teams[team].short_name}</b>: {budgetNow.left} change{budgetNow.left === 1 ? '' : 's'} left in {budgetNow.windowsLeft} window{budgetNow.windowsLeft === 1 ? '' : 's'} · {openWindows} risk window{openWindows === 1 ? '' : 's'} open.</p>
          <p className="mt-1 text-muted">The Coach wakes on high-risk windows and knocks, proposes a change and lets the engine replay the match with it. Until then, try one yourself below.</p>
        </div>
      ) : (
        <div key={coach.clock} className="enter mt-1.5">
          <div className="display text-2xl font-extrabold leading-tight">{what}</div>
          {p && <p className="mt-1 text-sm text-fg-2">{p.rationale}</p>}
          {b && (
            <>
              <dl className="mt-2 grid grid-cols-[auto_1fr_1fr] gap-x-4 gap-y-0.5 text-[15px]">
                <dt></dt><dd className="blk-meta text-[11px]">as played</dd><dd className="blk-meta text-[11px]">with the change</dd>
                <dt className="text-fg-2">{upTo == null ? 'final score' : `score at ${upTo}'`}</dt><dd className="display text-2xl font-extrabold">{sa![h]} - {sa![a]}</dd><dd className="display text-2xl font-extrabold">{sb![h]} - {sb![a]}</dd>
                {upTo == null && <><dt className="text-fg-2">knocks</dt><dd className="display text-2xl font-extrabold">{b.actual.injury_concerns_total}</dd><dd className="display text-2xl font-extrabold text-teal">{b.branch.injury_concerns_total}</dd></>}
              </dl>
              {upTo != null && <p className="mt-1 text-xs text-muted">Full-time outcomes stay hidden until the final whistle, no spoilers.</p>}
              <button className="btn btn-teal mt-2 text-sm" onClick={() => onSelect(b)}>Show the branch</button>
            </>
          )}
          {coach.errors.length > 0 && <p className="mt-1 text-xs text-bad">{coach.errors.join('; ')}</p>}
        </div>
      )}

      <h3 className="display mt-4 text-base font-extrabold uppercase tracking-wider text-fg-2">Try a change</h3>
      <form className="mt-2 grid grid-cols-2 gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); void run() }}>
        <label className="flex flex-col gap-0.5 text-[11px] uppercase tracking-wider text-muted">Team
          <select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value, player_off_id: '', player_on_id: '' })}>
            {[h, a].map((t) => <option key={t} value={t}>{meta.teams[t].name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] uppercase tracking-wider text-muted">At minute
          <span className="flex items-center gap-1">
            <input type="number" min={1} max={95} value={form.minute} className="w-20" onChange={(e) => { setMinuteTouched(true); setForm({ ...form, minute: Number(e.target.value) }) }} />
            {!ended && <button type="button" className="btn-quiet px-1.5 py-0.5 text-[11px] normal-case tracking-normal" onClick={() => { setMinuteTouched(false); setForm({ ...form, minute: Math.min(95, Math.max(1, now + 1)) }) }}>now</button>}
          </span>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] uppercase tracking-wider text-muted">Take off
          <select value={form.player_off_id} onChange={(e) => setForm({ ...form, player_off_id: e.target.value, player_on_id: '' })}>
            <option value="">pick a player (riskiest first)</option>
            {onPitch.map((pl) => <option key={pl.player_id} value={pl.player_id}>{pl.shirt_number} {pl.name} · hazard {currentHazard(risk?.hazard_series, pl.player_id)?.toFixed(2) ?? '–'} · {pl.minutes_played}'</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5 text-[11px] uppercase tracking-wider text-muted">Bring on
          <select value={form.player_on_id} onChange={(e) => setForm({ ...form, player_on_id: e.target.value })} disabled={!form.player_off_id}>
            <option value="">engine picks (same position)</option>
            {bench.map((s) => <option key={s.player_id} value={s.player_id}>{s.position} · {s.shirt_number} {s.name}{offPlayer && s.position === offPlayer.position ? ' · like for like' : ''}</option>)}
          </select>
        </label>
        <div className="col-span-2 flex flex-wrap items-center gap-2">
          <button className="btn btn-teal" type="submit" disabled={busy || !form.player_off_id}>{busy ? 'Simulating' : 'Simulate'}</button>
          <span className="text-xs text-muted">at {form.minute}' {meta.teams[form.team_id].short_name} had {budgetThen.left} change{budgetThen.left === 1 ? '' : 's'} left in {budgetThen.windowsLeft} window{budgetThen.windowsLeft === 1 ? '' : 's'}</span>
          {branches.length > 0 && (
            <select className="basis-full" value={selected?.branch_id ?? ''} onChange={(e) => onSelect(branches.find((x) => x.branch_id === e.target.value) ?? null)} aria-label="branches proposed by the Coach">
              <option value="">Coach proposals ({branches.length})</option>
              {branches.map((x) => <option key={x.branch_id} value={x.branch_id}>{describeIntervention(meta, x)}</option>)}
            </select>
          )}
          {error && <span className="basis-full text-bad">{error}</span>}
        </div>
      </form>
      <p className="mt-2 text-xs text-muted">Same seed, same match until the change, then the engine plays it out; the branch draws under the pitch.</p>
    </section>
  )
}
