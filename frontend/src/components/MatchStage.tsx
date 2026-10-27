import { useEffect, useMemo, useState, type RefObject } from 'react'
import type { Seat } from '../lib/seats'
import type { StreamState } from '../lib/useMatchStream'
import type { BranchSummary, CoachMsg, Frame, MatchEvent, Meta } from '../lib/types'
import { TopBand } from './TopBand'
import { BlockDiffStrip, Momentum, XgRace } from './Strip'
import { PitchStage } from './PitchStage'
import { MomentsRail } from './MomentsRail'
import { RiskBlock, StatsBlock } from './SidePanels'
import { WhatIfBand } from './WhatIfBand'
import { ControlRoom } from './ControlRoom'
import { YourSideBlock } from './YourSideBlock'
import { ForecastLedger } from './ForecastLedger'
import { TwoViewers } from './TwoViewers'
import { ReliabilityBlock } from './ReliabilityBlock'
import { BenchReport } from './BenchReport'
import { ShapeBlock } from './ShapeBlock'
import { PassNetwork } from './PassNetwork'
import { AnalystRead } from './AnalystRead'
import { ReadinessBoard } from './ReadinessBoard'
import { decisionLog } from '../lib/bench'
import { DecisionCard } from './DecisionCard'
import { RiskTimeline } from './RiskTimeline'
import { LeadTimeBlock } from './LeadTimeBlock'
import { TeamLoadBlock } from './TeamLoadBlock'

type Props = {
  favoritePlayerId: string | null
  onFavorite: (id: string | null) => void
  teamId: string | null
  language: 'en' | 'es'
  seat: Seat
  meta: Meta
  state: StreamState
  frameRef: RefObject<Frame | null>
  speed: number
  branches: BranchSummary[]
  latestCoach: CoachMsg | null
  lastGoal: MatchEvent | null
  selectedBranch: BranchSummary | null
  onSelectBranch: (b: BranchSummary | null) => void
  benchBranches: BranchSummary[]
  onBranchCreated: (b: BranchSummary) => void
}

/** One match, three compositions: what each seat sees. */
export function MatchStage({ seat, meta, state, frameRef, speed, branches, latestCoach, lastGoal, selectedBranch, onSelectBranch, benchBranches, onBranchCreated, favoritePlayerId, onFavorite, teamId, language }: Props) {
  const keyEvent = state.keyEvents.find((e) => e.type !== 'kickoff') ?? null
  // bench: which side the board shows and which player is in focus (ringed amber on the pitch, preselected in the decision card)
  const [benchTeam, setBenchTeam] = useState(meta.home_id)
  const [benchFocus, setBenchFocus] = useState<string | null>(null)
  const [possTeam, setPossTeam] = useState<string | null>(null) // from the positional frames, shared by the pitch chip and the shape block
  useEffect(() => { if (benchFocus && state.snapshot && state.snapshot.players[benchFocus]?.on_pitch === false) setBenchFocus(null) }, [benchFocus, state.snapshot])
  const rings = useMemo(() => Object.fromEntries((state.risk?.active_windows ?? []).map((w) => [w.player_id, w.level === 'high' ? '#e8405a' : '#f97316'])), [state.risk])
  const entries = useMemo(() => decisionLog(state.feed, benchBranches, meta), [state.feed, benchBranches, meta])
  // what the lower third shows: the bench follows every agent (its Coach included); the other seats follow the latest insight
  const latestForSeat = seat === 'bench' ? state.feed[0] ?? null : state.feed.find((f) => f.msg.kind === 'insight') ?? null
  const pitch = (size: 'lg' | 'sm') => (
    <PitchStage meta={meta} ball={state.ball} shots={state.shots} lastEvent={state.lastEvent} snapshot={state.snapshot}
      latest={latestForSeat} keyEvent={keyEvent} seat={seat} size={size} agentsOn={state.agentsOn}
      followId={seat === 'fan' ? favoritePlayerId : seat === 'bench' ? benchFocus : null} touches={state.touches} ended={ended} frameRef={frameRef} speed={speed}
      rings={seat === 'bench' ? rings : undefined} onPossessionTeam={setPossTeam} />
  )
  const rail = <MomentsRail meta={meta} feed={state.feed} keyEvents={state.keyEvents} agentsOn={state.agentsOn} seat={seat} shownId={latestForSeat?.id} />
  const band = <TopBand meta={meta} snapshot={state.snapshot} status={state.status} lastGoal={lastGoal} flash={state.goalFlash} teamId={seat === 'fan' ? teamId : null} />
  const ended = state.status === 'ended'
  const ledger = (compact = false, className = '', fill = false) => (
    <ForecastLedger meta={meta} snapshot={state.snapshot} feed={state.feed} verdicts={state.verdicts} credibility={state.credibility} agentsOn={state.agentsOn} ended={ended} compact={compact} className={className} fill={fill} />
  )

  if (seat === 'fan') {
    return (
      <>
        {band}
        <main key="fan" className="stagger mx-auto grid w-full max-w-6xl gap-3 px-3 pb-6 pt-4 sm:px-6">
          <div className="enter" style={{ ['--i' as string]: 1 }}>{pitch('lg')}</div>
          <div className="enter" style={{ ['--i' as string]: 2 }}><Momentum meta={meta} snapshot={state.snapshot} /></div>
          <div className="enter" style={{ ['--i' as string]: 3 }}>
            <YourSideBlock meta={meta} snapshot={state.snapshot} feed={state.feed} verdicts={state.verdicts} touches={state.touches} language={language} ended={ended} teamId={teamId} favoritePlayerId={favoritePlayerId} onFavorite={onFavorite} />
          </div>
          <div className="enter" style={{ ['--i' as string]: 4 }}>{rail}</div>
        </main>
      </>
    )
  }

  if (seat === 'control') {
    return (
      <>
        {band}
        <main key="control" className="grid gap-3 px-3 pb-6 pt-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="stagger flex min-w-0 flex-col gap-3">
            <div className="enter" style={{ ['--i' as string]: 1 }}><ControlRoom meta={meta} feed={state.feed} risk={state.risk} agentsOn={state.agentsOn} coachOn={state.coachOn} verdicts={state.verdicts} credibility={state.credibility} lanes={state.lanes} /></div>
            <div className="enter" style={{ ['--i' as string]: 2 }}><TwoViewers meta={meta} feed={state.feed} /></div>
          </div>
          <aside className="stagger flex min-w-0 flex-col gap-3">
            <div className="enter" style={{ ['--i' as string]: 2 }}>{ledger(true)}</div>
            <div className="enter" style={{ ['--i' as string]: 3 }}>{pitch('sm')}</div>
            <div className="enter" style={{ ['--i' as string]: 3 }}><RiskBlock meta={meta} risk={state.risk} alerts={state.alerts} /></div>
            <div className="enter" style={{ ['--i' as string]: 4 }}>{rail}</div>
          </aside>
        </main>
      </>
    )
  }

  if (seat === 'analyst') {
    return (
      <>
        {band}
        <main key="analyst" className="stagger grid gap-3 px-3 pb-6 pt-4 sm:px-6">
          <div className="enter grid gap-3 lg:grid-cols-2" style={{ ['--i' as string]: 1 }}>
            <Momentum meta={meta} snapshot={state.snapshot} />
            <BlockDiffStrip meta={meta} snapshot={state.snapshot} />
          </div>
          <div className="enter grid gap-3 lg:grid-cols-[minmax(0,1fr)_470px]" style={{ ['--i' as string]: 2 }}>
            <div className="flex min-w-0 flex-col gap-3">
              {pitch('lg')}
              <AnalystRead meta={meta} feed={state.feed} verdicts={state.verdicts} credibility={state.credibility} agentsOn={state.agentsOn} ended={ended} />
              <MomentsRail meta={meta} feed={state.feed} keyEvents={state.keyEvents} agentsOn={state.agentsOn} seat={seat} shownId={latestForSeat?.id} />
            </div>
            {/* the pitch column sets the row height (h-0 + min-h-full keeps this column out of the measurement);
                the full ledger fills what is left and the column scrolls as a whole, the pass network keeps its size at the bottom */}
            <div className="scroll-quiet flex min-w-0 flex-col gap-3 lg:h-0 lg:min-h-full lg:overflow-auto">
              {ledger(false, 'lg:min-h-[220px] lg:flex-1 lg:shrink-0 lg:overflow-auto scroll-quiet', true)}
              <PassNetwork meta={meta} touches={state.touches} snapshot={state.snapshot} ended={ended} compact />
            </div>
          </div>
          <div className="enter grid gap-3 md:grid-cols-2 lg:grid-cols-3" style={{ ['--i' as string]: 3 }}>
            <XgRace meta={meta} snapshot={state.snapshot} size="lg" />
            <StatsBlock meta={meta} snapshot={state.snapshot} />
            <ShapeBlock meta={meta} snapshot={state.snapshot} ended={ended} possessionTeam={possTeam} />
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      {band}
      <main key="bench" className="stagger grid gap-3 px-3 pb-6 pt-4 sm:px-6">
        <div className="enter" style={{ ['--i' as string]: 1 }}>
          <ReadinessBoard meta={meta} snapshot={state.snapshot} risk={state.risk} keyEvents={state.keyEvents} team={benchTeam}
            onTeam={(tid) => { setBenchTeam(tid); setBenchFocus(null) }} focus={benchFocus} onFocus={setBenchFocus} />
        </div>
        <div className="enter grid gap-3 lg:grid-cols-[minmax(0,1fr)_470px]" style={{ ['--i' as string]: 2 }}>
          <div className="min-w-0">{pitch('lg')}</div>
          {/* the pitch column sets the row height; the decision card fills the right column and scrolls inside if it must */}
          <div className="scroll-quiet flex min-w-0 flex-col gap-3 lg:h-0 lg:min-h-full lg:overflow-auto">
            <DecisionCard meta={meta} snapshot={state.snapshot} risk={state.risk} coach={latestCoach} branches={branches} selected={selectedBranch} onSelect={onSelectBranch}
              onBranchCreated={onBranchCreated} entries={entries} keyEvents={state.keyEvents} team={benchTeam} focus={benchFocus} ended={ended} className="lg:min-h-[300px] lg:flex-1" />
          </div>
        </div>
        {selectedBranch && <div className="enter" style={{ ['--i' as string]: 3 }}><WhatIfBand meta={meta} snapshot={state.snapshot} actualEvents={state.keyEvents} branches={branches} selected={selectedBranch} onSelect={onSelectBranch} ended={ended} timelineOnly /></div>}
        <div className="enter grid gap-3 md:grid-cols-2 lg:grid-cols-3" style={{ ['--i' as string]: 3 }}>
          <RiskTimeline meta={meta} snapshot={state.snapshot} risk={state.risk} team={benchTeam} focus={benchFocus} />
          <LeadTimeBlock risk={state.risk} />
          <TeamLoadBlock meta={meta} snapshot={state.snapshot} keyEvents={state.keyEvents} />
        </div>
        <div className="enter flex flex-col gap-3" style={{ ['--i' as string]: 4 }}>
          <BenchReport meta={meta} snapshot={state.snapshot} risk={state.risk} verdicts={state.verdicts} credibility={state.credibility} entries={entries} ended={ended} />
          <details className="blk px-4 py-2 text-sm">
            <summary className="display cursor-pointer text-base font-extrabold uppercase tracking-wider text-fg-2">How the monitor was calibrated <span className="blk-meta ml-2 normal-case">40 synthetic matches</span></summary>
            <div className="mt-2"><ReliabilityBlock risk={state.risk} alerts={state.alerts} /></div>
          </details>
          {rail}
        </div>
      </main>
    </>
  )
}
