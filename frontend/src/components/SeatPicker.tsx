import { SEAT_ORDER, SEATS, type Seat } from '../lib/seats'

type Props = { onPick: (seat: Seat) => void; disabled: boolean }

/** Entry screen: the thesis, then three doors into the same match. */
export function SeatPicker({ onPick, disabled }: Props) {
  return (
    <section className="enter mx-auto w-full max-w-6xl px-6 pb-16 pt-10 sm:pt-16">
      <h1 className="display max-w-4xl text-[56px] font-black uppercase leading-[0.9] tracking-tight sm:text-[96px]">AI that gets graded,<br /><span className="text-amber">not just heard.</span></h1>
      <p className="mt-6 max-w-prose text-lg leading-relaxed text-fg-2">
        A synthetic match replays as a live broadcast. Agents narrate, explain and personalise it; a Load &amp; Risk Monitor
        predicts who gets hurt from workload alone and is scored against what actually happens; a Coach proposes a change and the
        engine shows the match that would have followed.
      </p>
      <p className="display mt-10 text-xl font-extrabold uppercase tracking-wider text-muted">Pick your seat</p>
      <div className="stagger mt-3 grid gap-3 md:grid-cols-3">
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
              <span className="display mt-auto pt-5 text-sm font-bold uppercase tracking-widest text-muted group-hover:text-fg">Take this seat</span>
            </button>
          )
        })}
      </div>
      <p className="mt-4 text-sm text-muted">Match, speed, language and agents are set in the bar above. Speed 60 plays a match in about a minute and a half. You can change seats during the match.</p>
    </section>
  )
}
