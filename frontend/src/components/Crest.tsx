import type { Team } from '../lib/types'

/** A fictional club crest: a shield in the club's colours with its kit pattern and initials. No real badge motifs. */
export function Crest({ team, size = 40 }: { team: Pick<Team, 'team_id' | 'short_name' | 'primary_color' | 'secondary_color' | 'pattern'>; size?: number }) {
  const p = team.primary_color, s = team.secondary_color ?? '#ffffff', pattern = team.pattern ?? 'solid'
  const id = `crest-${team.team_id}`
  const initials = team.short_name.slice(0, 2).toUpperCase()
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label={`${team.short_name} crest`} className="shrink-0">
      <defs><clipPath id={id}><path d="M20 2 L36 7 V20 C36 30 28 36 20 38 C12 36 4 30 4 20 V7 Z" /></clipPath></defs>
      <g clipPath={`url(#${id})`}>
        <rect width="40" height="40" fill={p} />
        {pattern === 'halves' && <rect x="20" width="20" height="40" fill={s} />}
        {pattern === 'stripes' && [4, 12, 20, 28].map((x) => <rect key={x} x={x} width="4" height="40" fill={s} />)}
        {pattern === 'hoops' && [6, 16, 26].map((y) => <rect key={y} y={y} width="40" height="5" fill={s} />)}
        {pattern === 'sash' && <polygon points="0,30 40,0 40,10 0,40" fill={s} />}
        {pattern === 'sleeves' && <><rect width="8" height="40" fill={s} /><rect x="32" width="8" height="40" fill={s} /></>}
      </g>
      <path d="M20 2 L36 7 V20 C36 30 28 36 20 38 C12 36 4 30 4 20 V7 Z" fill="none" stroke="#0b0f1a" strokeWidth="1.6" />
      <rect x="11" y="15" width="18" height="12" fill="#0b0f1a" fillOpacity="0.78" />
      <text x="20" y="24.5" textAnchor="middle" fontSize="10" fontFamily="Barlow Condensed" fontWeight="800" fill="#fff" letterSpacing="0.5">{initials}</text>
    </svg>
  )
}

/** Dark text on light club colours, white text otherwise. */
export function onColor(hex: string): string {
  const n = parseInt(hex.replace('#', ''), 16)
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
  return lum > 0.6 ? '#0b0f1a' : '#ffffff'
}
