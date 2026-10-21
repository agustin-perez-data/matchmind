import { useCallback, useEffect, useMemo, useState } from 'react'
import { listMatches, type MatchRow } from './lib/api'
import { useMatchStream, type StreamOptions } from './lib/useMatchStream'
import type { BranchSummary, ViewerProfile } from './lib/types'
import { Header } from './components/Header'
import { Scoreboard } from './components/Scoreboard'
import { Pitch } from './components/Pitch'
import { XgRace } from './components/XgRace'
import { MomentumBar } from './components/MomentumBar'
import { AgentFeed } from './components/AgentFeed'
import { RiskPanel } from './components/RiskPanel'
import { WhatIf } from './components/WhatIf'

const DEFAULT_PROFILE: ViewerProfile = { mode: 'commentator', language: 'es', favorite_player_id: null }

export default function App() {
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [matchId, setMatchId] = useState<string>('')
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
    if (q.has('speed')) setSpeed(Math.max(0, Number(q.get('speed'))))
    if (q.has('mode') || q.has('lang') || q.has('player')) {
      setProfile((p) => ({
        mode: (q.get('mode') as ViewerProfile['mode']) ?? p.mode,
        language: (q.get('lang') as ViewerProfile['language']) ?? p.language,
        favorite_player_id: q.get('player') ?? p.favorite_player_id,
      }))
    }
    if (q.has('agents')) setAgents(q.get('agents') !== '0')
    if (q.has('coach')) setCoach(q.get('coach') !== '0')
    listMatches()
      .then((rows) => {
        setMatches(rows)
        const first = q.get('match') ?? rows[0]?.match_id
        if (first) setMatchId(first)
        if (first && q.get('autostart') === '1') {
          start({
            matchId: first, speed: q.has('speed') ? Math.max(0, Number(q.get('speed'))) : 60,
            profile: {
              mode: (q.get('mode') as ViewerProfile['mode']) ?? DEFAULT_PROFILE.mode,
              language: (q.get('lang') as ViewerProfile['language']) ?? DEFAULT_PROFILE.language,
              favorite_player_id: q.get('player'),
            },
            agents: q.get('agents') !== '0', coach: q.get('coach') !== '0',
          })
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
  const branches = useMemo(
    () => state.feed.flatMap((f) => (f.msg.kind === 'coach' && f.msg.branch ? [f.msg.branch] : [])),
    [state.feed],
  )

  return (
    <div className="min-h-full flex flex-col">
      <Header
        matches={matches} matchId={matchId} onMatch={setMatchId}
        speed={speed} onSpeed={onSpeed}
        profile={profile} onProfile={onProfile}
        agents={agents} onAgents={setAgents} coach={coach} onCoach={setCoach}
        status={state.status} onStart={onStart} onStop={stop}
        players={state.meta ? Object.values(state.meta.teams).flatMap((t) => t.players) : []}
      />
      {loadError && <p className="mx-4 mt-3 panel px-4 py-3 text-bad">{loadError}</p>}

      {!live && !loadError && (
        <section className="mx-auto max-w-3xl px-6 py-16">
          <h1 className="display text-6xl font-bold leading-none tracking-tight">AI that gets graded,<br />not just heard.</h1>
          <p className="mt-6 text-lg text-ink-2 max-w-prose">
            MatchMind replays a synthetic match as a live feed. Agents explain, narrate and personalise it. A Load &amp; Risk
            Monitor predicts injury-risk windows from workload only and is scored against what actually happens. A Coach
            proposes interventions, and the engine shows the match that would have followed.
          </p>
          <p className="mt-4 text-ink-3 max-w-prose">Pick a viewer profile above, then press Start. Speed 60 plays the match in about a minute and a half.</p>
        </section>
      )}

      {live && state.meta && (
        <main className="grid gap-3 px-3 pb-6 pt-3 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <div className="flex flex-col gap-3 min-w-0">
            <Scoreboard meta={state.meta} snapshot={state.snapshot} flash={state.goalFlash} status={state.status} />
            <Pitch meta={state.meta} trail={state.trail} lastEvent={state.lastEvent} snapshot={state.snapshot} />
            <div className="grid gap-3 md:grid-cols-[3fr_2fr]">
              <XgRace meta={state.meta} snapshot={state.snapshot} />
              <MomentumBar meta={state.meta} snapshot={state.snapshot} />
            </div>
            <WhatIf
              meta={state.meta} snapshot={state.snapshot} actualEvents={state.keyEvents} branches={branches}
              selected={selectedBranch} onSelect={setSelectedBranch}
            />
          </div>
          <div className="flex flex-col gap-3 min-w-0">
            <AgentFeed
              meta={state.meta} feed={state.feed} keyEvents={state.keyEvents}
              agentsOn={state.agentsOn} coachOn={state.coachOn} onShowBranch={setSelectedBranch}
            />
            <RiskPanel meta={state.meta} risk={state.risk} alerts={state.alerts} />
          </div>
        </main>
      )}
    </div>
  )
}
