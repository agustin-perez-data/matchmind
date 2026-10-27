/** The brand mark (the centre of a pitch on amber) and the name, linking home. */
export function Wordmark() {
  return (
    <a href="/" className="flex items-center gap-3">
      <svg viewBox="0 0 64 64" width="40" height="40" aria-hidden className="shrink-0">
        <rect width="64" height="64" rx="12" fill="#ffd166" />
        <path d="M32 4V60" stroke="#0b0f1a" strokeWidth="7" />
        <circle cx="32" cy="32" r="16" fill="none" stroke="#0b0f1a" strokeWidth="7" />
      </svg>
      <span className="display text-[30px] font-black uppercase leading-none tracking-wide">MatchMind</span>
    </a>
  )
}
