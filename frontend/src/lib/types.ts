// Shapes of what the backend sends (see backend/matchmind/api/app.py docstring).

export type Player = {
  player_id: string
  name: string
  position: string
  shirt_number: number
  starter: boolean
}

export type Team = {
  team_id: string
  name: string
  short_name: string
  primary_color: string
  secondary_color?: string
  pattern?: 'solid' | 'halves' | 'stripes' | 'hoops' | 'sash' | 'sleeves'
  city?: string
  style: string
  players: Player[]
}

export type Meta = {
  match_id: string
  home_id: string
  away_id: string
  score: Record<string, number>
  teams: Record<string, Team>
  n_events: number
  seed: number
}

export type MatchEvent = {
  event_id: number
  period: number
  minute: number
  second: number
  clock: string
  type: string
  team_id?: string
  player_id?: string
  player_name?: string
  x?: number
  y?: number
  end_x?: number
  end_y?: number
  outcome?: string
  xg?: number
  detail?: string
  card?: string
  player_on_name?: string
  player_off_name?: string
  player_on_id?: string
  player_off_id?: string
  receiver_id?: string
  assist_player_id?: string
  score?: Record<string, number>
  forced?: boolean
}

export type TeamStats = {
  passes: number
  passes_completed?: number
  pass_accuracy: number
  possession_pct: number
  shots: number
  shots_on_target: number
  xg: number
  goals: number
  pressures: number
  tackles: number
  interceptions: number
  fouls: number
  yellow_cards: number
  red_cards: number
}

export type PlayerView = {
  player_id: string
  name: string
  team_id: string
  position: string
  on_pitch: boolean
  minutes_played: number
  distance_m: number
  sprints: number
  top_speed_kmh: number
  acwr_pre_match: number
  acwr_live: number
  risk_band: 'undertrained' | 'optimal' | 'elevated' | 'high'
  sprints_per_min: number
  effort_ratio: number
  effort_ratio_recent: number
  injury_concerns: number
  heat?: number[] // 12x8 occupancy grid in team frame, from the positional model; present once frames have been applied
}

/** One second of the positional model: the ball, who carries it and where the 22 are (absolute 0-100). */
export type Frame = {
  kind: 'frame'
  period: number
  minute: number
  second: number
  ball: [number, number]
  carrier: string | null
  players: Record<string, [number, number]>
  at?: number // wall-clock arrival (performance.now), set by the client
}

export type TeamShape = {
  block_height_m: number
  width_m: number
  compactness_m: number
  lines: Record<string, number>
  phase: 'attacking' | 'defending' | 'transition'
}

export type Pressure = {
  carrier: string | null
  team_in_possession: string | null
  opponents_within_8m: number
  under_pressure: boolean
}

export type XgPoint = { period: number; minute: number; clock: string; team_id: string; goal?: boolean } & Record<string, number | string | boolean | undefined>

export type Snapshot = {
  match_id: string
  home_id: string
  away_id: string
  period: number
  minute: number
  clock: string
  last_event_id: number
  score: Record<string, number>
  teams: Record<string, TeamStats>
  momentum: number
  momentum_series: { period: number; minute: number; value: number }[]
  xg_race: XgPoint[]
  players: Record<string, PlayerView>
  shape?: Record<string, TeamShape> | null // positional model, null until the first frame
  shape_last_10?: Record<string, { block_height_m: number; delta_vs_match_m: number }> | null
  press_index?: Record<string, number | null> | null
  block_series?: ({ period: number; minute: number } & Record<string, number>)[] // mean block height per team per minute, metres
  pressure?: Pressure | null
  risk_alerts: { player_id: string; name: string; team_id: string; acwr_live: number; risk_band: string }[]
}

export type ViewerProfile = {
  mode: 'analyst' | 'casual' | 'commentator' | 'player_focus'
  language: 'en' | 'es'
  favorite_player_id: string | null
  team_id?: string | null // the side the viewer supports; null = neutral
}

export type Forecast = {
  dominant_team_id: string
  goal_probability: number
  watch_player_id: string | null
  claim: string
}

export type AnalystInsight = {
  headline: string
  why_it_matters: string
  tactical_read: string
  key_stat: string
  confidence: number
  forecast?: Forecast
}

export type ForecastScores = { dominance: number | null; goal: number | null; watch: number | null; overall: number | null }

export type ScoreDim = 'overall' | 'dominance' | 'goal' | 'watch'

export type Credibility = {
  judged: number
  pending: number
  horizon_min: number
  analyst: ForecastScores
  naive: ForecastScores
  counts?: { analyst: Record<ScoreDim, number>; naive: Record<ScoreDim, number> } // verdicts behind each mean (a dimension can be ungraded)
}

export type VerdictMsg = {
  kind: 'verdict'
  cached?: boolean
  event_id: number
  issued_clock: string
  forecast: Forecast & { dominant_team: string | null; watch_player: string | null }
  facts: {
    window: string
    minutes: number
    truncated: boolean
    xg_gained: Record<string, number>
    goals: { clock: string; team_id: string; player_name: string }[]
    shots: number
    players_involved: string[]
    score_now: Record<string, number>
  }
  scores: ForecastScores
  naive_scores: ForecastScores
  verdict: { verdict: 'called_it' | 'partly' | 'missed'; summary: string | null; lesson: string | null }
  credibility: Credibility | null
  errors: string[]
  latency_ms: number
  trace?: TraceEvent[]
}

export type Narration = { text: string; language: string; mode: string }

export type DirectorDecision = {
  show: ('narration' | 'insight' | 'risk' | 'stat')[]
  priority: number
  headline: string
  personalized_note: string | null
}

export type TraceEvent = {
  t: number
  kind: 'stage' | 'stage_end' | 'agent_start' | 'agent_end' | 'agent_error' | 'tool_call' | 'tool_result' | 'tool_error' | 'fallback'
  agent: string | null
  stage?: string
  tool?: string
  args?: Record<string, unknown>
  latency_ms?: number
  tokens?: { input: number | null; output: number | null } | null
  error?: string
  reason?: string
  participants?: string[]
  trigger?: string
  action?: string
  minute?: number
  branch_id?: string
  status?: string
}

export type InsightMsg = {
  kind: 'insight'
  cached?: boolean
  trace?: TraceEvent[]
  orchestration?: string
  event_id: number
  clock: string
  score: Record<string, number>
  moment: { kind: string; importance: number; summary: string; event_id: number }
  analyst: AnalystInsight | null
  viewers: Record<string, { profile: ViewerProfile; narration: Narration | null; decision: DirectorDecision | null }>
  errors: string[]
  latency_ms: number
}

export type CoachProposal = {
  action: 'substitution' | 'tactic' | 'hold'
  team_id: string
  player_off_id: string | null
  player_on_id: string | null
  press_intensity: number | null
  style: string | null
  minute: number
  rationale: string
  urgency: number
  expected_effect: string
}

export type SideSummary = {
  score: Record<string, number>
  xg: Record<string, number>
  shots: Record<string, number>
  injury_concerns: Record<string, number>
  injury_concerns_total: number
  goals: { clock: string; period: number; minute: number; team_id: string; player_name: string }[]
}

export type BranchSummary = {
  branch_id: string
  match_id: string
  status: 'applied' | 'skipped'
  intervention: Record<string, string | number>
  divergence_minute: number
  actual: SideSummary
  branch: SideSummary
  diff: { goals_home: number; goals_away: number; xg_home: number; xg_away: number; injury_concerns: number }
  branch_event_count: number
  player_off?: {
    player_id: string
    name: string
    concerns_after_actual: number
    concerns_after_branch: number
    minutes_actual: number
    minutes_branch: number
  }
}

export type CoachMsg = {
  cached?: boolean
  kind: 'coach'
  trace?: TraceEvent[]
  trigger: 'risk_alert' | 'injury_concern'
  trigger_detail?: Record<string, unknown>
  clock: string
  minute: number
  score: Record<string, number>
  player: Partial<PlayerView> & { player_id: string }
  proposal: CoachProposal | null
  branch: BranchSummary | null
  errors: string[]
  latency_ms: number
}

export type RiskWindow = {
  player_id: string
  name: string
  team_id: string
  position: string
  open_minute: number
  expires_minute: number
  hazard: number
  level: 'elevated' | 'high'
  clock: string
  minutes_played: number
  acwr_live: number
  effort_ratio_recent?: number
}

export type TrackScore = {
  alerts: number
  true_alerts: number
  precision: number
  concerns: number
  covered: number
  recall: number
  mean_lead_minutes: number | null
  ranked_concerns: number
  top3_hits: number
  top3_rate: number
  top3_random_rate: number
  mean_rank_pct: number
}

export type RiskMsg = {
  kind: 'risk'
  minute: number
  clock: string
  active_windows: RiskWindow[]
  hazards_top: { player_id: string; name: string; team_id: string; hazard: number }[]
  recent_alerts: RiskWindow[]
  concerns: { player_id: string; name: string; minute: number; clock: string; covered: boolean; lead_minutes: number | null; baseline_covered: boolean; detail: string }[]
  scorecard: { model: TrackScore; baseline: TrackScore; horizon_minutes: number; baseline_rule: string }
  note: string
}

export type StreamStatus = 'idle' | 'connecting' | 'live' | 'ended' | 'error'
