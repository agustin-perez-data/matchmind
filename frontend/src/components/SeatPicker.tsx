import type { MatchRow } from '../lib/api'
import { PROOFS } from '../lib/evidence'
import { headlineFixture, menuFixtures } from '../lib/fixtures'
import { SEAT_ORDER, SEATS, type Seat } from '../lib/seats'
import type { ViewerProfile } from '../lib/types'
import { Crest } from './Crest'
import { PreviewLoop } from './PreviewLoop'

type Language = ViewerProfile['language']
type Props = {
  onPick: (seat: Seat) => void
  /** The primary action: the headline fixture, fan seat, neutral side. */
  onQuick: () => void
  disabled: boolean
  matches: MatchRow[]; matchId: string; onMatch: (id: string) => void
  language: Language; onLanguage: (l: Language) => void
}

const LANGUAGES: { id: Language; label: string }[] = [
  { id: 'en', label: 'English' },
  { id: 'es', label: 'Español rioplatense' },
]
const REPO = 'https://github.com/agustin-perez-data/matchmind'
const FALLBACK_HOME = { short_name: 'Thames', primary_color: '#d7263d' }
const FALLBACK_AWAY = { short_name: 'Northbridge', primary_color: '#1d3fa8' }

/** Entry screen: the product first, the proof under it, one primary action, then the four seats. */
export function SeatPicker({ onPick, onQuick, disabled, matches, matchId, onMatch, language, onLanguage }: Props) {
  const headline = headlineFixture(matches)
  const fixtures = menuFixtures(matches)
  const home = headline?.home_team ?? FALLBACK_HOME
  const away = headline?.away_team ?? FALLBACK_AWAY
  const sel = matches.find((m) => m.match_id === matchId)

  return (
    <section className="enter mx-auto w-full max-w-7xl px-5 pb-14 pt-5 sm:px-8 sm:pt-8">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <div className="display text-xl font-black uppercase tracking-wide">MatchMind <span className="ml-1 text-xs font-semibold normal-case tracking-normal text-muted">synthetic league, fictional clubs</span></div>
        <nav className="hidden flex-wrap gap-x-5 text-sm text-muted sm:flex" aria-label="about this project">
          <span>Running on Microsoft Foundry and Azure Container Apps</span>
          <a className="underline-offset-4 hover:text-fg hover:underline" href={REPO} target="_blank" rel="noreferrer">GitHub</a>
          <a className="underline-offset-4 hover:text-fg hover:underline" href={`${REPO}/blob/main/infra/README.md`} target="_blank" rel="noreferrer">Architecture</a>
        </nav>
      </header>

      <div className="mt-6 grid items-center gap-8 lg:mt-10 lg:grid-cols-[minmax(0,1fr)_minmax(420px,46%)] lg:gap-12">
        <div>
          <h1 className="display max-w-3xl text-[44px] font-black uppercase leading-[0.92] tracking-tight sm:text-[72px] xl:text-[84px]">AI that gets graded, not just heard.</h1>
          <p className="mt-5 max-w-[62ch] text-lg leading-relaxed text-fg-2">
            A synthetic match replays as a live broadcast. Agents explain it, narrate it and predict it, and every prediction is
            scored against what actually happens. A Risk Monitor warns who is about to get hurt; a Coach proposes a change and the
            engine shows the match that would have followed.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3">
            <button type="button" onClick={onQuick} disabled={disabled}
              className="btn btn-amber display px-7 py-3 text-xl font-black uppercase tracking-wide transition-[filter,transform] duration-150 active:scale-[0.985] disabled:cursor-wait disabled:opacity-60">
              {disabled ? 'Loading the fixture list' : 'Watch the derby'}
            </button>
            <span className="text-sm text-fg-2">
              <span className="inline-flex items-center gap-1.5 align-middle"><Crest team={home as never} size={20} />{home.short_name}</span>
              <span className="mx-1 text-muted">v</span>
              <span className="inline-flex items-center gap-1.5 align-middle"><Crest team={away as never} size={20} />{away.short_name}</span>
              <span className="text-muted">, fan seat, about 90 seconds</span>
            </span>
          </div>
        </div>
        <PreviewLoop home={home} away={away} line="Ferrant cuts inside and fires from 14 metres: 1-0" verdict="Called it · 66 %" />
      </div>

      <dl className="mt-8 grid grid-cols-3 gap-3 sm:mt-10 sm:gap-6 lg:mt-12">
        {PROOFS.map((p) => (
          <div key={p.value} className="border-t-2 border-white/25 pt-3">
            <dt className="display text-[26px] font-black leading-none sm:text-4xl lg:text-5xl">{p.value}{p.compare && <span className="ml-1.5 block text-xs font-bold text-muted sm:ml-2 sm:inline sm:text-base lg:text-lg">{p.compare}</span>}</dt>
            <dd className="mt-2 max-w-[36ch] text-xs leading-snug text-fg-2 sm:text-sm">{p.caption} <span className="text-muted">{p.source}.</span></dd>
          </div>
        ))}
      </dl>

      <div className="mt-14 flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div>
          <h2 className="display text-3xl font-black uppercase leading-none">Or take a seat</h2>
          <p className="mt-2 max-w-[60ch] text-sm text-fg-2">Four views of the same match. You can change seat, speed and sound once you are in; the fixture and the commentary language are chosen here.</p>
        </div>
        <div className="flex flex-wrap gap-x-8 gap-y-4">
          <fieldset className="m-0 min-w-0 border-0 p-0">
            <legend className="mb-2 text-sm text-muted">Fixture</legend>
            <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
              {fixtures.map(({ row: m, daily }) => {
                const on = m.match_id === matchId
                return (
                  <label key={m.match_id} className={`choice relative flex items-center gap-2 px-3 py-2 text-left transition-[background,box-shadow] duration-150 ${on ? 'bg-ink-2 shadow-[0_0_0_2px_#ffd166]' : 'bg-ink hover:bg-ink-2'}`}
                    style={{ borderTop: `3px solid ${on ? '#ffd166' : 'rgba(255,255,255,0.18)'}` }}>
                    <input type="radio" name="fixture" value={m.match_id} checked={on} onChange={() => onMatch(m.match_id)} />
                    <Crest team={m.home_team} size={24} />
                    <span className="display text-base font-black uppercase leading-none">{m.home_team.short_name} <span className="text-muted">v</span> {m.away_team.short_name}</span>
                    <Crest team={m.away_team} size={24} />
                    {daily && <span className="ml-1 text-xs text-muted">today's match</span>}
                  </label>
                )
              })}
            </div>
          </fieldset>
          <fieldset className="m-0 min-w-0 border-0 p-0">
            <legend className="mb-2 text-sm text-muted">Commentary language</legend>
            <div className="flex">
              {LANGUAGES.map((l, i) => {
                const on = l.id === language
                return (
                  <label key={l.id} className={`choice px-3 py-2 text-sm font-semibold transition-[background,color] duration-150 ${on ? 'bg-fg text-ink' : 'bg-ink text-fg-2 hover:bg-ink-2'} ${i === 0 ? '' : 'border-l border-line'}`}>
                    <input type="radio" name="language" value={l.id} checked={on} onChange={() => onLanguage(l.id)} />
                    {l.label}
                  </label>
                )
              })}
            </div>
          </fieldset>
        </div>
      </div>

      <div className="stagger mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {SEAT_ORDER.map((seat, i) => {
          const s = SEATS[seat]
          return (
            <button key={seat} type="button" disabled={disabled} onClick={() => onPick(seat)} style={{ ['--i' as string]: i + 1, borderTopColor: s.rule }}
              className="enter blk group flex flex-col items-start px-5 pb-5 pt-4 text-left transition-[transform,background] duration-200 ease-out hover:bg-ink-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber active:scale-[0.985] disabled:opacity-60">
              <span className="flex items-baseline gap-2">
                <span className="display text-4xl font-black uppercase leading-none" style={{ color: s.rule }}>{s.label}</span>
                {s.start && <span className="display text-sm font-extrabold uppercase tracking-wide text-amber">start here</span>}
              </span>
              <span className="mt-2 text-base leading-snug text-fg">{s.promise}</span>
              <span className="mt-3 text-sm leading-snug text-fg-2"><span className="text-muted">In the first 30 seconds: </span>{s.firstThirtySeconds}</span>
              <span className="display mt-5 text-lg font-extrabold uppercase tracking-wide transition-[color] duration-150 group-hover:text-fg" style={{ color: s.rule }}>Take the {s.label.toLowerCase()} seat{sel && seat !== 'fan' ? '' : ''}</span>
            </button>
          )
        })}
      </div>

      <footer className="mt-14 flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 border-t border-line pt-4 text-sm text-muted">
        <span>Every club, player and number here is synthetic. No real competition, club or person appears.</span>
        <span className="flex flex-wrap gap-x-5">
          <a className="underline-offset-4 hover:text-fg hover:underline" href={`${REPO}#ai-that-gets-graded-not-just-heard`} target="_blank" rel="noreferrer">How it is graded</a>
          <a className="underline-offset-4 hover:text-fg hover:underline" href={`${REPO}/blob/main/infra/README.md`} target="_blank" rel="noreferrer">Architecture</a>
          <a className="underline-offset-4 hover:text-fg hover:underline" href={REPO} target="_blank" rel="noreferrer">Source</a>
        </span>
      </footer>
    </section>
  )
}
