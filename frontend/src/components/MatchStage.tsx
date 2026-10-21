import type { Seat } from '../lib/seats'
import type { StreamState } from '../lib/useMatchStream'
import type { BranchSummary, CoachMsg, MatchEvent, Meta } from '../lib/types'
import { TopBand } from './TopBand'
import { Momentum, XgRace } from './Strip'
import { PitchStage } from './PitchStage'
import { MomentsRail } from './MomentsRail'
import { CoachBlock, RiskBlock, StatsBlock } from './SidePanels'
import { WhatIfBand } from './WhatIfBand'

type Props = {
  seat: Seat
  meta: Meta
  state: StreamState
  branches: BranchSummary[]
  latestCoach: CoachMsg | null
  lastGoal: MatchEvent | null
  selectedBranch: BranchSummary | null
  onSelectBranch: (b: BranchSummary | null) => void
}

/** One match, three compositions: what each seat sees. */
export function MatchStage({ seat, meta, state, branches, latestCoach, lastGoal, selectedBranch, onSelectBranch }: Props) {
  const keyEvent = state.keyEvents.find((e) => e.type !== 'kickoff') ?? null
  const pitch = (size: 'lg' | 'sm') => (
    <PitchStage meta={meta} ball={state.ball} shots={state.shots} lastEvent={state.lastEvent} snapshot={state.snapshot}
      latest={state.feed[0] ?? null} keyEvent={keyEvent} seat={seat} size={size} />
  )
  const rail = <MomentsRail meta={meta} feed={state.feed} keyEvents={state.keyEvents} agentsOn={state.agentsOn} seat={seat} />
  const band = <TopBand meta={meta} snapshot={state.snapshot} status={state.status} lastGoal={lastGoal} flash={state.goalFlash} />
  const ended = state.status === 'ended'
  const whatIf = <WhatIfBand meta={meta} snapshot={state.snapshot} actualEvents={state.keyEvents} branches={branches} selected={selectedBranch} onSelect={onSelectBranch} ended={ended} />

  if (seat === 'fan') {
    return (
      <>
        {band}
        <main key="fan" className="stagger mx-auto grid w-full max-w-6xl gap-3 px-3 pb-6 pt-4 sm:px-6">
          <div className="enter" style={{ ['--i' as string]: 1 }}>{pitch('lg')}</div>
          <div className="enter" style={{ ['--i' as string]: 2 }}><Momentum meta={meta} snapshot={state.snapshot} /></div>
          <div className="enter" style={{ ['--i' as string]: 3 }}>{rail}</div>
        </main>
      </>
    )
  }

  if (seat === 'analyst') {
    return (
      <>
        {band}
        <main key="analyst" className="grid gap-3 px-3 pb-6 pt-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_470px]">
          <div className="stagger flex min-w-0 flex-col gap-3">
            <div className="enter" style={{ ['--i' as string]: 1 }}><Momentum meta={meta} snapshot={state.snapshot} /></div>
            <div className="enter" style={{ ['--i' as string]: 2 }}>{pitch('lg')}</div>
            <div className="enter" style={{ ['--i' as string]: 3 }}>{rail}</div>
          </div>
          <aside className="stagger flex min-w-0 flex-col gap-3">
            <div className="enter" style={{ ['--i' as string]: 2 }}><XgRace meta={meta} snapshot={state.snapshot} size="lg" /></div>
            <div className="enter" style={{ ['--i' as string]: 3 }}><StatsBlock meta={meta} snapshot={state.snapshot} /></div>
          </aside>
        </main>
      </>
    )
  }

  return (
    <>
      {band}
      <div className="enter" style={{ ['--i' as string]: 1 }}>{whatIf}</div>
      <main key="bench" className="grid gap-3 px-3 pb-6 pt-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_470px]">
        <div className="stagger flex min-w-0 flex-col gap-3">
          <div className="enter" style={{ ['--i' as string]: 2 }}><RiskBlock meta={meta} risk={state.risk} alerts={state.alerts} expanded /></div>
          <div className="enter" style={{ ['--i' as string]: 3 }}>{rail}</div>
        </div>
        <aside className="stagger flex min-w-0 flex-col gap-3">
          <div className="enter" style={{ ['--i' as string]: 2 }}><CoachBlock meta={meta} coach={latestCoach} onShowBranch={onSelectBranch} snapshot={state.snapshot} ended={ended} /></div>
          <div className="enter" style={{ ['--i' as string]: 3 }}>{pitch('sm')}</div>
        </aside>
      </main>
    </>
  )
}
