import { useCallback, useEffect, useMemo, useState } from 'react'
import { listMatches, type MatchRow } from './lib/api'
import { compareForSeat, controlProfile, parseSeat, profileForSeat, profileSpec, type Seat } from './lib/seats'
import { useMatchStream, type StreamOptions } from './lib/useMatchStream'
import { soundFor, stadium } from './lib/sounds'
import { parseSpeed } from './lib/speed'
import { voice } from './lib/voice'
import type { BranchSummary, ViewerProfile } from './lib/types'
import { ControlBar } from './components/ControlBar'
import { SeatPicker } from './components/SeatPicker'
import { SideModal } from './components/SideModal'
import { MatchStage } from './components/MatchStage'

type Language = ViewerProfile['language']

/** The URL is the state: /?seat=fan&lang=es&speed=60&match=...&agents=1&coach=1 */
function readUrl() {
  const q = new URLSearchParams(location.search)
  return {
    seat: parseSeat(q.get('seat')),
    language: (q.get('lang') === 'es' ? 'es' : 'en') as Language,
    speed: parseSpeed(q.get('speed')),
    match: q.get('match'),
    player: q.get('player'),
    team: q.get('team') === 'neutral' ? null : q.get('team'),
    sideChosen: q.has('team'), // 'neutral' counts as chosen; no param means we still have to ask
    agents: q.get('agents') !== '0',
    coach: q.get('coach') !== '0',
  }
}

function writeUrl(patch: Record<string, string | number | boolean | null | undefined>, replace = false) {
  const q = new URLSearchParams(location.search)
  for (const [k, v] of Object.entries(patch)) {
    if (v == null || v === '' || v === false) q.delete(k)
    else q.set(k, v === true ? '1' : String(v))
  }
  const url = `${location.pathname}${q.toString() ? `?${q}` : ''}`
  if (replace) history.replaceState(null, '', url)
  else history.pushState(null, '', url)
}

export default function App() {
  const initial = useMemo(readUrl, [])
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [matchId, setMatchId] = useState(initial.match ?? '')
  const [speed, setSpeed] = useState(initial.speed)
  const [language, setLanguage] = useState<Language>(initial.language)
  const [favorite, setFavorite] = useState<string | null>(initial.player)
  const [team, setTeam] = useState<string | null>(initial.team)
  const [sideChosen, setSideChosen] = useState(initial.sideChosen)
  const [askSide, setAskSide] = useState(false)
  // agents / coach come only from the URL (dev switches: ?agents=0&coach=0 replays without LLM calls)
  const { agents, coach } = initial
  const [seat, setSeat] = useState<Seat | null>(initial.seat)
  const [selectedBranch, setSelectedBranch] = useState<BranchSummary | null>(null)
  const [benchBranches, setBenchBranches] = useState<BranchSummary[]>([]) // changes the bench tried itself, for the decision log
  const [loadError, setLoadError] = useState<string | null>(null)
  const { state, start, stop, send, frameRef } = useMatchStream()

  const sidesOf = useCallback((id: string, rows: MatchRow[] = matches) => {
    const row = rows.find((m) => m.match_id === id)
    return { home: row?.home_team.team_id ?? null, away: row?.away_team.team_id ?? null }
  }, [matches])

  const begin = useCallback((s: Seat, id: string, opts?: Partial<StreamOptions>, rows?: MatchRow[]) => {
    setSelectedBranch(null)
    setBenchBranches([])
    voice.stop()
    stadium.cutAll()
    const { home, away } = sidesOf(id, rows)  // on autostart the catalogue has just arrived and is not in state yet
    const profile = s === 'control' ? controlProfile(language, home) : profileForSeat(s, language, favorite, team)
    start({ matchId: id, speed, profile, compare: compareForSeat(s, language, away), agents, coach, minImportance: s === 'fan' ? 2 : 3, ...opts })
  }, [start, speed, language, favorite, team, agents, coach, sidesOf])

  // Load the catalogue; a seat in the URL means "straight into the match".
  useEffect(() => {
    listMatches()
      .then((rows) => {
        setMatches(rows)
        const headline = rows.find((r) => r.match_id.startsWith('THU'))?.match_id ?? rows[0]?.match_id
        const id = initial.match && rows.some((r) => r.match_id === initial.match) ? initial.match : headline
        if (id) setMatchId(id)
        if (id && initial.seat) begin(initial.seat, id, undefined, rows)
      })
      .catch((e: Error) => setLoadError(`Could not reach the match server (${e.message}). Start the backend and reload.`))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Browser back/forward: leaving the match screen stops the stream, entering it starts one.
  useEffect(() => {
    const onPop = () => {
      const u = readUrl()
      setSeat(u.seat)
      if (!u.seat) stop()
      else if (state.status !== 'live' && state.status !== 'connecting' && matchId) begin(u.seat, matchId)
    }
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [state.status, matchId, begin, stop])

  const [sound, setSound] = useState(stadium.enabled)
  const onSound = useCallback((on: boolean) => { stadium.setEnabled(on); setSound(on) }, [])

  // The referee follows the events as they arrive: one whistle pattern per moment.
  useEffect(() => {
    const e = state.lastEvent
    if (!e) return
    const kind = soundFor(e.type)
    if (kind) stadium.whistle(kind)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.lastEvent])

  // The commentator's voice: the fan seat hears each narration line as it lands (latest wins).
  useEffect(() => {
    if (seat !== 'fan' || (state.status !== 'live' && state.status !== 'ended')) return // never a stale line from the last match
    const latest = state.feed.find((f) => f.msg.kind === 'insight')
    const text = latest && latest.msg.kind === 'insight' ? Object.values(latest.msg.viewers)[0]?.narration?.text : null
    if (text) voice.say(text, language)
  }, [state.feed, state.status, seat, language])
  useEffect(() => { if (seat !== 'fan' || state.status === 'idle') voice.stop() }, [seat, state.status])

  const pickSeat = useCallback((s: Seat) => {
    if (!matchId) return
    stadium.unlock() // a click: the browser lets audio start from here on
    setSeat(s)
    writeUrl({ seat: s, match: matchId, lang: language, speed, team: null, agents: agents ? null : '0', coach: coach ? null : '0' })
    setTeam(null); setSideChosen(false)
    if (s === 'fan') { setAskSide(true); return } // the turnstile first, every time; the match starts once you have picked an end
    begin(s, matchId)
  }, [matchId, language, speed, agents, coach, begin])

  /** The fan picked an end (or neutral) at the turnstile. */
  const chooseSide = useCallback((id: string | null) => {
    setTeam(id); setSideChosen(true); setAskSide(false)
    writeUrl({ team: id ?? 'neutral' }, true)
    const live = state.status === 'live' || state.status === 'ended' || state.status === 'connecting'
    if (live) send({ profile: profileForSeat('fan', language, favorite, id) })
    else if (matchId) begin('fan', matchId, { profile: profileForSeat('fan', language, favorite, id) })
  }, [state.status, send, begin, matchId, language, favorite])

  const switchSeat = useCallback((s: Seat) => {
    setSeat(s)
    writeUrl({ seat: s }, true)
    const { home, away } = sidesOf(matchId)
    const profile = s === 'control' ? controlProfile(language, home) : profileForSeat(s, language, favorite, team)
    send({ profile, compare: compareForSeat(s, language, away).map(profileSpec) })
    if (s === 'fan' && !sideChosen) setAskSide(true)
  }, [send, language, favorite, team, sideChosen, matchId, sidesOf])

  const leave = useCallback(() => {
    stop()
    voice.stop()
    stadium.cutAll()
    setSeat(null)
    setSelectedBranch(null)
    setBenchBranches([])
    setAskSide(false)
    setTeam(null); setSideChosen(false) // your end is for one match: next time you take the seat you are asked again
    writeUrl({ seat: null, team: null })
  }, [stop])

  const onSpeed = useCallback((v: number) => { setSpeed(v); writeUrl({ speed: v }, true); send({ speed: v }) }, [send])
  const onFavorite = useCallback((id: string | null) => {
    setFavorite(id); writeUrl({ player: id }, true)
    if (seat) send({ profile: profileForSeat(seat, language, id, team) })
  }, [send, seat, language, team])

  const meta = state.meta
  const inMatch = seat !== null && (state.status === 'live' || state.status === 'ended' || state.status === 'connecting')
  const branches = useMemo(() => state.feed.flatMap((f) => (f.msg.kind === 'coach' && f.msg.branch ? [f.msg.branch] : [])), [state.feed])
  const latestCoach = useMemo(() => { const f = state.feed.find((x) => x.msg.kind === 'coach'); return f && f.msg.kind === 'coach' ? f.msg : null }, [state.feed])
  const onBranchCreated = useCallback((b: BranchSummary) => {
    setBenchBranches((list) => (list.some((x) => x.branch_id === b.branch_id) ? list : [...list, b]))
    setSelectedBranch(b)
  }, [])
  const lastGoal = useMemo(() => state.keyEvents.find((e) => e.type === 'goal') ?? null, [state.keyEvents])
  const teamVars = meta ? { ['--home' as string]: meta.teams[meta.home_id].primary_color, ['--away' as string]: meta.teams[meta.away_id].primary_color } : undefined

  return (
    <div className="stage flex min-h-full flex-col" style={teamVars}>
      {inMatch && seat && (
        <ControlBar speed={speed} onSpeed={onSpeed} seat={seat} onSeat={switchSeat} status={state.status} onLeave={leave}
          language={language} sound={sound} onSound={onSound} />
      )}
      {loadError && <p className="mx-6 mt-3 bg-ink px-4 py-3 text-bad">{loadError}</p>}
      {!inMatch && !loadError && (
        <SeatPicker onPick={pickSeat} disabled={!matchId} matches={matches} matchId={matchId}
          onMatch={(id) => { setMatchId(id); writeUrl({ match: id }, true) }}
          language={language} onLanguage={(l) => { setLanguage(l); writeUrl({ lang: l }, true) }} />
      )}
      {inMatch && seat && state.status === 'connecting' && <p className="display px-6 py-10 text-2xl font-bold uppercase tracking-wider text-muted">Connecting to the studio</p>}
      {inMatch && seat && meta && (
        <MatchStage seat={seat} meta={meta} state={state} frameRef={frameRef} speed={speed} branches={branches} latestCoach={latestCoach} lastGoal={lastGoal}
          selectedBranch={selectedBranch} onSelectBranch={setSelectedBranch} benchBranches={benchBranches} onBranchCreated={onBranchCreated}
          favoritePlayerId={favorite} onFavorite={onFavorite} teamId={team} language={language} />
      )}
      {askSide && (() => {
        const row = matches.find((m) => m.match_id === matchId)
        return row ? <SideModal home={row.home_team} away={row.away_team} onPick={chooseSide} onClose={leave} /> : null
      })()}
    </div>
  )
}
