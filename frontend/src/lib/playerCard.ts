/** The end-of-match player card: a 1200×630 PNG drawn on a canvas, downloadable, shareable. */

import type { FanStats } from './follow'
import type { Meta, Team } from './types'

export type CardInput = {
  meta: Meta
  team: Team
  name: string
  position: string
  shirt: number
  minutes: number
  score: Record<string, number>
  stats: FanStats
  points: { x: number; y: number; type: string }[] // team frame: attacking to the right
  heat?: number[] // 12x8 occupancy grid in team frame, from the positional model
  moments: { clock: string; text: string }[]
  language: 'en' | 'es'
}

const T = {
  en: { attacking: 'attacking →', heat: 'heat: positional model', card: 'MATCH CARD', touches: 'TOUCHES', shots: 'SHOTS', goals: 'GOALS', assists: 'ASSISTS', xg: 'xG', key: 'KEY PASSES', duels: 'DUELS WON', min: 'MIN', moments: 'MOMENTS', league: 'MatchMind Synthetic League · fictional clubs and players' },
  es: { attacking: 'atacando →', heat: 'calor: modelo posicional', card: 'FICHA DEL PARTIDO', touches: 'TOQUES', shots: 'TIROS', goals: 'GOLES', assists: 'ASISTENCIAS', xg: 'xG', key: 'PASES CLAVE', duels: 'DUELOS', min: 'MIN', moments: 'MOMENTOS', league: 'Liga sintética MatchMind · clubes y jugadores ficticios' },
}

export function drawPlayerCard(c: CardInput): HTMLCanvasElement {
  const W = 1200, H = 630
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')!
  const t = T[c.language]
  const ink = '#0b0f1a'
  const light = luminance(c.team.primary_color) > 0.6
  const onTeam = light ? ink : '#ffffff'

  // background: team colour wipe on the left, studio dark on the right
  ctx.fillStyle = '#06080f'
  ctx.fillRect(0, 0, W, H)
  const g = ctx.createLinearGradient(0, 0, 520, 0)
  g.addColorStop(0, c.team.primary_color)
  g.addColorStop(1, shade(c.team.primary_color, 0.65))
  ctx.fillStyle = g
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(520, 0); ctx.lineTo(470, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fill()

  // left: name, team, number
  ctx.fillStyle = onTeam
  ctx.font = '800 22px "Barlow Condensed", "Arial Narrow", sans-serif'
  ctx.fillText(t.card, 40, 56)
  ctx.font = '900 150px "Barlow Condensed", "Arial Narrow", sans-serif'
  ctx.globalAlpha = 0.18
  ctx.fillText(String(c.shirt), 40, 300)
  ctx.globalAlpha = 1
  const [first, ...rest] = c.name.split(' ')
  ctx.font = '600 44px "Barlow Condensed", "Arial Narrow", sans-serif'
  ctx.fillText(first.toUpperCase(), 40, 380)
  ctx.font = '900 84px "Barlow Condensed", "Arial Narrow", sans-serif'
  fitText(ctx, rest.join(' ').toUpperCase() || first.toUpperCase(), 40, 460, 420)
  ctx.font = '700 24px "Barlow Condensed", "Arial Narrow", sans-serif'
  ctx.fillText(`${c.team.name.toUpperCase()} · ${c.position} · ${c.minutes}${t.min}`, 40, 505)
  const h = c.meta.teams[c.meta.home_id], a = c.meta.teams[c.meta.away_id]
  ctx.font = '800 30px "Barlow Condensed", "Arial Narrow", sans-serif'
  ctx.fillText(`${h.short_name.toUpperCase()} ${c.score[h.team_id] ?? 0} - ${c.score[a.team_id] ?? 0} ${a.short_name.toUpperCase()}`, 40, 560)

  // right: numbers
  const stats: [string, string][] = [
    [t.touches, String(c.stats.touches)], [t.shots, String(c.stats.shots)], [t.goals, String(c.stats.goals)],
    [t.assists, String(c.stats.assists)], [t.xg, c.stats.xg.toFixed(2)], [t.key, String(c.stats.keyPasses)],
    [t.duels, String(c.stats.tackles + c.stats.interceptions)],
  ]
  stats.forEach(([label, value], i) => {
    const x = 560 + (i % 4) * 155, y = 70 + Math.floor(i / 4) * 95
    ctx.fillStyle = '#9aa3b8'
    ctx.font = '700 15px "Barlow Condensed", "Arial Narrow", sans-serif'
    ctx.fillText(label, x, y)
    ctx.fillStyle = i === 2 && c.stats.goals > 0 ? '#ffd166' : '#ffffff'
    ctx.font = '900 52px "Barlow Condensed", "Arial Narrow", sans-serif'
    ctx.fillText(value, x, y + 50)
  })

  // right: touch map on a small pitch
  const px = 560, py = 265, pw = 300, ph = 190
  ctx.fillStyle = '#1f6b41'
  ctx.fillRect(px, py, pw, ph)
  ctx.strokeStyle = '#d6e9dc'
  ctx.lineWidth = 1.5
  ctx.strokeRect(px, py, pw, ph)
  ctx.beginPath(); ctx.moveTo(px + pw / 2, py); ctx.lineTo(px + pw / 2, py + ph); ctx.stroke()
  ctx.beginPath(); ctx.arc(px + pw / 2, py + ph / 2, 24, 0, Math.PI * 2); ctx.stroke()
  ctx.strokeRect(px, py + ph * 0.21, pw * 0.165, ph * 0.58)
  ctx.strokeRect(px + pw * 0.835, py + ph * 0.21, pw * 0.165, ph * 0.58)
  if (c.heat && c.heat.length === 96) {
    const max = Math.max(...c.heat)
    if (max > 0) c.heat.forEach((v, i) => {
      if (v <= 0) return
      const col = i % 12, row = Math.floor(i / 12)
      ctx.fillStyle = `rgba(255, 209, 102, ${(0.08 + 0.55 * (v / max)).toFixed(3)})`
      ctx.fillRect(px + (col / 12) * pw, py + (row / 8) * ph, pw / 12 + 0.5, ph / 8 + 0.5)
    })
  }
  for (const p of c.points) {
    const x = px + (p.x / 100) * pw, y = py + (p.y / 100) * ph
    ctx.fillStyle = p.type === 'shot' || p.type === 'goal' ? '#ffd166' : 'rgba(255,255,255,0.75)'
    ctx.beginPath(); ctx.arc(x, y, p.type === 'shot' || p.type === 'goal' ? 6 : 3.5, 0, Math.PI * 2); ctx.fill()
  }

  ctx.fillStyle = '#9aa3b8'
  ctx.font = '600 13px "Barlow", system-ui, sans-serif'
  ctx.fillText(`${t.attacking}${c.heat ? ` · ${t.heat}` : ''}`, px, py + ph + 18)

  // right: moments
  ctx.fillStyle = '#9aa3b8'
  ctx.font = '700 15px "Barlow Condensed", "Arial Narrow", sans-serif'
  ctx.fillText(t.moments, 890, 275)
  ctx.font = '600 20px "Barlow", system-ui, sans-serif'
  c.moments.slice(0, 6).forEach((m, i) => {
    ctx.fillStyle = '#ffd166'
    ctx.fillText(m.clock, 890, 305 + i * 28)
    ctx.fillStyle = '#ffffff'
    fitText(ctx, m.text, 955, 305 + i * 28, 215)
  })

  // footer
  ctx.fillStyle = '#9aa3b8'
  ctx.font = '600 14px "Barlow", system-ui, sans-serif'
  ctx.fillText(t.league, 560, 600)
  ctx.fillStyle = '#ffffff'
  ctx.font = '900 22px "Barlow Condensed", "Arial Narrow", sans-serif'
  ctx.fillText('MATCHMIND', 1060, 600)
  return canvas
}

export function downloadPlayerCard(c: CardInput): void {
  const canvas = drawPlayerCard(c)
  if (import.meta.env.DEV) (window as unknown as { __lastCard?: HTMLCanvasElement }).__lastCard = canvas // for visual checks
  const a = document.createElement('a')
  a.href = canvas.toDataURL('image/png')
  a.download = `matchmind-${c.name.toLowerCase().replace(/\s+/g, '-')}-${c.meta.match_id}.png`
  a.click()
}

function fitText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number) {
  let s = text
  while (s.length > 3 && ctx.measureText(s).width > maxWidth) s = s.slice(0, -2)
  if (s !== text) s = s.slice(0, -1) + '…'
  ctx.fillText(s, x, y)
}

function luminance(hex: string): number {
  const n = parseInt(hex.replace('#', ''), 16)
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
}

function shade(hex: string, k: number): string {
  const n = parseInt(hex.replace('#', ''), 16)
  const r = Math.round(((n >> 16) & 255) * k), g = Math.round(((n >> 8) & 255) * k), b = Math.round((n & 255) * k)
  return `rgb(${r},${g},${b})`
}
