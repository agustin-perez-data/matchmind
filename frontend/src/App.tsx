import { useCallback, useEffect, useMemo, useState } from 'react'
import { listMatches, type MatchRow } from './lib/api'
import { useMatchStream, type StreamOptions } from './lib/useMatchStream'
import type { BranchSummary, ViewerProfile } from './lib/types'
import { ControlBar } from './components/ControlBar'
import { TopBand } from './components/TopBand'
import { Strip } from './components/Strip'
import { PitchStage } from './components/PitchStage'
import { MomentsRail } from './components/MomentsRail'
import { CoachBlock, RiskBlock, StatsBlock } from './components/SidePanels'
import { WhatIfBand } from './components/WhatIfBand'

const DEFAULT_PROFILE: ViewerProfile = { mode: 'commentator', language: 'es', favorite_player_id: null }

export default function App() {
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [matchId, setMatchId] = useState('')
  const [speed, setSpeed] = useState(60)
  const [profile, setProfile] = useState<ViewerProfile>(DEFAULT_PROFILE)
  const [agents, setAgents] = useState(true)
  const [coach, setCoach] = useState(true)
  const [selectedBranch, setSelectedBranch] = useState<BranchSummary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const { state, start, stop, send } = useMatchStream()

  // URL parameters prefill the controls and can start the replay, e.g. /?speed=120&mode=casual&lang=en&agents=0&autostart=1
  useEffect(() => {
    const q = new URLSearchParams(location.search)
    const qProfile: ViewerProfile = {
      mode: (q.get('mode') as ViewerProfile['mode']) ?? DEFAULT_PROFILE.mode,
      language: (q.get('lang') as ViewerProfile['language']) ?? DEFAULT_PROFILE.language,
      favorite_player_id: q.get('player'),
    }
    const qSpeed = q.has('speed') ? Math.max(0, Number(q.get('speed'))) : 60
    if (q.has('speed')) setSpeed(qSpeed)
    if (q.has('mode') || q.has('lang') || q.has('player')) setProfile(qProfile)
    if (q.has('agents')) setAgents(q.get('agents') !== '0')
    if (q.has('coach')) setCoach(q.get('coach') !== '0')
    listMatches()
      .then((rows) => {
        setMatches(rows)
        const first = q.get('match') ?? rows[0]?.match_id
        if (first) setMatchId(first)
        if (first && q.get('autostart') === '1') {
          start({ matchId: first, speed: qSpeed, profile: qProfile, agents: q.get('agents') !== '0', coach: q.get('coach') !== '0' })
        }
      })
      .catch((e: Error) => setLoadError(`Could not reach the match server (${e.message}). Start the backend and reload.`))
  }, [start])

  const onStart = useCallback(() => {
    if (!matchId) return
    setSelectedBranch(null)
    const opts: StreamOptions = { matchId, speed, profile, agents, coach }
    start(opts)
  }, [matchId, speed, profile, agents, coach, start])
  const onSpeed = useCallback((v: number) => { setSpeed(v); send({ speed: v }) }, [send])
  const onProfile = useCallback((p: ViewerProfile) => { setProfile(p); send({ profile: p }) }, [send])

  const live = state.status === 'live' || state.status === 'ended'
  const meta = state.meta
  const branches = useMemo(() => state.feed.flatMap((f) => (f.msg.kind === 'coach' && f.msg.branch ? [f.msg.branch] : [])), [state.feed])
  const latestCoach = useMemo(() => {
    const f = state.feed.find((x) => x.msg.kind === 'coach')
    return f && f.msg.kind === 'coach' ? f.msg : null
  }, [state.feed])
  const lastGoal = useMemo(() => state.keyEvents.find((e) => e.type === 'goal') ?? null, [state.keyEvents])
  const teamVars = meta ? { ['--home' as string]: meta.teams[meta.home_id].primary_color, ['--away' as string]: meta.teams[meta.away_id].primary_color } : undefined

  return (
    <div className="stage flex min-h-full flex-col" style={teamVars}>
      <ControlBar
        matches={matches} matchId={matchId} onMatch={setMatchId}
        speed={speed} onSpeed={onSpeed} profile={profile} onProfile={onProfile}
        agents={agents} onAgents={setAgents} coach={coach} onCoach={setCoach}
        status={state.status} onStart={onStart} onStop={stop}
        players={meta ? Object.values(meta.teams).flatMap((t) => t.players) : []}
      />
      {loadError && <p className="mx-6 mt-3 bg-ink px-4 py-3 text-bad">{loadError}</p>}

      {!live && !loadError && (
        <section className="enter mx-auto w-full max-w-5xl px-6 py-14 sm:py-24">
          <h1 className="display max-w-4xl text-[64px] font-black uppercase leading-[0.9] tracking-tight sm:text-[112px]">AI that gets graded,<br /><span className="text-amber">not just heard.</span></h1>
          <p className="mt-8 max-w-prose text-lg leading-relaxed text-fg-2">
            A synthetic match replays as a live broadcast. Agents narrate, explain and personalise it. A Load &amp; Risk Monitor
            predicts who gets hurt from workload alone and is scored against what actually happens. A Coach proposes a change,
            and the engine shows the match that would have followed.
          </p>
          <p className="mt-4 text-muted">Pick a viewer above and press Start. Speed 60 plays the match in about a minute and a half.</p>
        </section>
      )}

      {live && meta && (
        <>
          <TopBand meta={meta} snapshot={state.snapshot} status={state.status} lastGoal={lastGoal} flash={state.goalFlash} />
          <main className="grid gap-3 px-3 pb-4 pt-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_470px]">
            <div className="stagger flex min-w-0 flex-col gap-3">
              <div className="enter" style={{ ['--i' as string]: 1 }}><Strip meta={meta} snapshot={state.snapshot} /></div>
              <div className="enter" style={{ ['--i' as string]: 2 }}>
                <PitchStage meta={meta} trail={state.trail} lastEvent={state.lastEvent} snapshot={state.snapshot}
                  latest={state.feed[0] ?? null} keyEvent={state.keyEvents.find((e) => e.type !== 'kickoff') ?? null} />
              </div>
              <div className="enter" style={{ ['--i' as string]: 3 }}><MomentsRail meta={meta} feed={state.feed} keyEvents={state.keyEvents} agentsOn={state.agentsOn} /></div>
            </div>
            <aside className="stagger flex min-w-0 flex-col gap-3">
              <div className="enter" style={{ ['--i' as string]: 2 }}><StatsBlock meta={meta} snapshot={state.snapshot} /></div>
              <div className="enter" style={{ ['--i' as string]: 3 }}><RiskBlock meta={meta} risk={state.risk} alerts={state.alerts} /></div>
              <div className="enter" style={{ ['--i' as string]: 4 }}><CoachBlock meta={meta} coach={latestCoach} onShowBranch={setSelectedBranch} /></div>
            </aside>
          </main>
          <WhatIfBand meta={meta} snapshot={state.snapshot} actualEvents={state.keyEvents} branches={branches} selected={selectedBranch} onSelect={setSelectedBranch} />
        </>
      )}
    </div>
  )
}
