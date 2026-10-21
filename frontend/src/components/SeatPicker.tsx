import type { MatchRow } from '../lib/api'
import { SEAT_ORDER, SEATS, type Seat } from '../lib/seats'
import { Crest } from './Crest'

type Props = { onPick: (seat: Seat) => void; disabled: boolean; matches: MatchRow[]; matchId: string; onMatch: (id: string) => void }

/** Entry screen: the thesis, then three doors into the same match. */
export function SeatPicker({ onPick, disabled, matches, matchId, onMatch }: Props) {
  return (
    <section className="enter mx-auto w-full max-w-6xl px-6 pb-16 pt-6 sm:pt-10">
      <div className="display text-xl font-black uppercase tracking-wide">MatchMind <span className="ml-1 text-xs font-semibold tracking-widest text-muted">synthetic league, fictional clubs</span></div>
      <h1 className="display max-w-4xl text-[56px] font-black uppercase leading-[0.9] tracking-tight sm:text-[96px]">AI that gets graded,<br /><span className="text-amber">not just heard.</span></h1>
      <p className="mt-6 max-w-prose text-lg leading-relaxed text-fg-2">
        A synthetic match replays as a live broadcast. Agents narrate, explain and personalise it; a Load &amp; Risk Monitor
        predicts who gets hurt from workload alone and is scored against what actually happens; a Coach proposes a change and the
        engine shows the match that would have followed.
      </p>
      <p className="mt-4 max-w-prose text-base text-fg-2">
        <span className="text-teal">For the bench:</span> injury-risk warnings about 25 minutes ahead, from workload any club already measures, graded live against the knocks that happen. Decision support, not medical advice.
      </p>
      <p className="display mt-10 text-xl font-extrabold uppercase tracking-wider text-muted">Matchday 9, pick a fixture</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4" role="radiogroup" aria-label="fixture">
        {[...matches].sort((a, b) => Number(!a.match_id.startsWith('THU')) - Number(!b.match_id.startsWith('THU'))).map((m) => {
          // the Thames derby is the headline fixture; the rest follow in catalogue order
          const on = m.match_id === matchId
          return (
            <button key={m.match_id} type="button" role="radio" aria-checked={on} onClick={() => onMatch(m.match_id)}
              className={`blk flex items-center gap-3 px-3 py-2 text-left transition-[background,border-color] duration-150 ${on ? 'bg-ink-2' : 'hover:bg-ink-2/60'}`}
              style={{ borderTopColor: on ? '#ffd166' : 'rgba(255,255,255,0.25)' }}>
              <Crest team={m.home_team} size={36} />
              <span className="min-w-0 flex-1">
                <span className="display block truncate text-lg font-extrabold uppercase leading-tight">{m.home_team.short_name} <span className="text-muted">v</span> {m.away_team.short_name}</span>
                <span className="block truncate text-xs text-muted">{m.home_team.name} hosts {m.away_team.name}</span>
              </span>
              <Crest team={m.away_team} size={36} />
            </button>
          )
        })}
      </div>
      <p className="display mt-8 text-xl font-extrabold uppercase tracking-wider text-muted">Pick your seat</p>
      <div className="stagger mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {SEAT_ORDER.map((seat, i) => {
          const s = SEATS[seat]
          return (
            <button key={seat} type="button" disabled={disabled} onClick={() => onPick(seat)} style={{ ['--i' as string]: i + 1, borderTopColor: s.rule }}
              className="enter blk group flex min-h-[260px] flex-col items-start px-5 py-4 text-left transition-[transform,background] duration-200 ease-out hover:bg-ink-2 active:scale-[0.985] disabled:opacity-50">
              <span className="display text-4xl font-black uppercase leading-none" style={{ color: s.rule }}>{s.label}</span>
              <span className="mt-2 text-base text-fg">{s.tagline}</span>
              <ul className="mt-4 space-y-1 text-sm text-fg-2">
                {s.bullets.map((b) => <li key={b} className="flex gap-2"><span aria-hidden className="mt-2 inline-block h-1.5 w-1.5 shrink-0" style={{ background: s.rule }} />{b}</li>)}
              </ul>
              <span className="btn mt-auto inline-block transition-[filter,transform] duration-150 group-hover:brightness-110" style={{ background: s.rule, color: '#0b0f1a' }}>Take this seat</span>
            </button>
          )
        })}
      </div>
      <p className="mt-4 text-sm text-muted">Speed, language, agents and the seat itself can be changed during the match from the bar that appears once you are seated. Speed 60 plays a match in about a minute and a half.</p>
    </section>
  )
}
