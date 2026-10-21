import type { BranchSummary, MatchEvent, Meta } from './types'

// Empty in development (Vite proxies to :8000); the Container Apps URL in production.
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''

export function wsUrl(path: string): string {
  if (API_BASE) return API_BASE.replace(/^http/, 'ws') + path
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json() as Promise<T>
}

export type MatchRow = { match_id: string; home: string; away: string; score: Record<string, number> }

export const listMatches = () => getJson<MatchRow[]>('/matches')
export const getMeta = (id: string) => getJson<Meta>(`/matches/${id}/meta`)
export const getBranch = (id: string, branchId: string) =>
  getJson<{ summary: BranchSummary; meta: Meta; events: MatchEvent[] }>(`/matches/${id}/branches/${branchId}`)

export type InterventionRequest = {
  minute: number
  action: 'substitution' | 'tactic'
  team_id: string
  player_off_id?: string
  player_on_id?: string
  press_intensity?: number
  style?: string
}

export async function simulateBranch(id: string, body: InterventionRequest): Promise<BranchSummary> {
  const r = await fetch(`${API_BASE}/matches/${id}/branches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText)
  return r.json() as Promise<BranchSummary>
}
