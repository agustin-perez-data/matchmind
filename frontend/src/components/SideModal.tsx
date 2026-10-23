import { useEffect, useRef } from 'react'
import type { CatalogTeam } from '../lib/api'
import { Crest, onColor } from './Crest'

type Props = { home: CatalogTeam; away: CatalogTeam; onPick: (teamId: string | null) => void }

/** The turnstile: which end are you in? Asked every time a fan takes the seat; the answer holds for the whole match.
 *  Closing it (the X or Escape) means walking in neutral. */
export function SideModal({ home, away, onPick }: Props) {
  const neutral = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    neutral.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onPick(null) } // Escape = just watching
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onPick])

  const End = ({ team, side }: { team: CatalogTeam; side: 'home' | 'away' }) => (
    <button type="button" onClick={() => onPick(team.team_id)}
      className={`group flex min-h-[200px] flex-col items-center justify-center gap-3 px-6 py-6 text-center transition-[transform,filter] duration-200 ease-out hover:brightness-110 active:scale-[0.985] sm:min-h-[260px] ${side === 'home' ? 'wipe-h' : 'wipe-a'}`}
      style={{ color: onColor(team.primary_color) }}>
      <Crest team={team} size={72} />
      <span className="display text-3xl font-black uppercase leading-none sm:text-4xl">{team.name}</span>
      <span className="display text-xs font-bold uppercase tracking-[0.2em] opacity-80">{team.city ?? ''}</span>
      <span className="btn mt-2 bg-white/95 text-sm group-hover:bg-amber">I'm with them</span>
    </button>
  )

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-stage/80 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="side-title">
      <div className="enter-pop blk relative w-full max-w-4xl px-4 py-4 sm:px-6 sm:py-6" style={{ borderTopColor: '#ffd166' }}>
        <button type="button" aria-label="Close, just watching" title="Close (Esc): just watching" onClick={() => onPick(null)}
          className="absolute right-3 top-3 grid h-10 w-10 place-items-center border border-white/15 text-fg-2 transition-[color,border-color,transform] duration-150 hover:border-white/50 hover:text-fg active:scale-90">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M3 3l12 12M15 3L3 15" /></svg>
        </button>
        <div className="flex flex-wrap items-baseline justify-between gap-2 pr-10">
          <h2 id="side-title" className="display text-3xl font-black uppercase leading-none sm:text-5xl">Which end are you in?</h2>
          <span className="blk-meta">{home.short_name} v {away.short_name} · Matchday 9</span>
        </div>
        <p className="mt-2 max-w-prose text-sm text-fg-2">Pick a side and the commentary is yours: it celebrates your goals, suffers theirs and keeps the facts straight. Or stay neutral and hear it called down the middle.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-stretch">
          <End team={home} side="home" />
          <button ref={neutral} type="button" onClick={() => onPick(null)}
            className="display flex min-h-[64px] items-center justify-center gap-2 border border-white/20 px-6 py-3 text-lg font-extrabold uppercase tracking-wider text-fg-2 transition-[border-color,color] duration-150 hover:border-white/60 hover:text-fg sm:min-h-0 sm:flex-col sm:px-4">
            <span>Neutral</span>
            <span className="text-[11px] font-semibold tracking-[0.2em] text-muted">just watching</span>
          </button>
          <End team={away} side="away" />
        </div>
        <p className="mt-3 text-xs text-muted">Your end holds for the whole match. Close this (× or Esc) to walk in neutral.</p>
      </div>
    </div>
  )
}
