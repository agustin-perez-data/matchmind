// Tiny inline icon set (one stroke weight), so tags never fall back to emoji.
const base = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2.4, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }

export const IconMic = () => <svg {...base}><path d="M12 3v10M8 7v6M16 7v6M4 11v2M20 11v2" /></svg>
export const IconChart = () => <svg {...base}><path d="M4 19h16M6 15l4-6 4 3 4-7" /></svg>
export const IconCoach = () => <svg {...base}><path d="M4 20h16M6 20V9l6-4 6 4v11M10 20v-5h4v5" /></svg>
export const IconRisk = () => <svg {...base}><path d="M12 4l9 16H3zM12 10v4M12 17v.5" /></svg>
export const IconDirector = () => <svg {...base}><path d="M3 7h18v12H3zM3 11h18M8 7V5M16 7V5" /></svg>
export const IconPlay = () => <svg {...base}><path d="M7 5v14l11-7z" fill="currentColor" stroke="none" /></svg>
