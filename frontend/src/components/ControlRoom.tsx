import { useEffect, useState } from 'react'
import { getHealth } from '../lib/api'
import { cacheRate, correctedCount, explainedLine, feedTokens, fmtTokens, guardrailLine, hostedJudge, percentile, type Health } from '../lib/control'
import type { FeedItem, VerdictItem } from '../lib/useMatchStream'
import type { CoachMsg, Credibility, InsightMsg, Lanes, Meta, RiskMsg, TraceEvent } from '../lib/types'

type Props = { meta: Meta; feed: FeedItem[]; risk: RiskMsg | null; agentsOn: boolean; coachOn: boolean; verdicts: VerdictItem[]; credibility: Credibility | null; lanes?: Lanes | null }

const LANES = ['Analyst', 'Narrator', 'Director', 'Coach', 'Engine'] as const
const LANE_COLOR: Record<string, string> = { Analyst: '#ffd166', Narrator: '#ffffff', Director: '#c084fc', Coach: '#2dd4bf', Engine: '#8fb0ff', Judge: '#f6a6ff' }

/** The studio's control room: the agent system at work, moment by moment. */
export function ControlRoom({ meta, feed, risk, agentsOn, coachOn, verdicts, credibility, lanes = null }: Props) {
  const [now, setNow] = useState(() => Date.now())  // lazy: the clock is read when the component mounts, not on every render
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(id) }, [])
  const latest = feed[0]
  const fresh = latest ? now - latest.at < 2500 : false
  const traced = feed.filter((f) => (f.msg.trace?.length ?? 0) > 0)
  const insights = feed.filter((f): f is FeedItem & { msg: InsightMsg } => f.msg.kind === 'insight')
  const coaches = feed.filter((f): f is FeedItem & { msg: CoachMsg } => f.msg.kind === 'coach')
  const toolCalls = traced.reduce((n, f) => n + (f.msg.trace ?? []).filter((e) => e.kind === 'tool_call').length, 0)
  const fanOut = insights.map((f) => f.msg.trace?.find((e) => e.kind === 'stage_end' && e.stage === 'fan-out')?.latency_ms).filter((x): x is number => x != null)
  const mean = (xs: number[]) => (xs.length ? Math.round(xs.reduce((a, b) => a + b, 0) / xs.length) : null)
  const orchestration = insights[0]?.msg.orchestration ?? (agentsOn ? 'waiting for the first key moment' : 'agents off')
  const litNodes = new Set<string>()
  if (fresh && latest) {
    if (latest.msg.kind === 'insight') ['stream', 'interpreter', 'gate', 'Analyst', 'Narrator', 'guardrail', 'Director', 'seat'].forEach((n) => litNodes.add(n))
    else ['stream', 'interpreter', 'risk', 'Coach', 'Engine', 'whatif'].forEach((n) => litNodes.add(n))
  }
  if (verdicts[0] && now - verdicts[0].at < 2500) ['ledger', 'Judge', 'credibility'].forEach((n) => litNodes.add(n))
  const judgeLatency = mean(verdicts.map((v) => v.msg.latency_ms))
  const tokens = feedTokens(feed, verdicts)
  const cache = cacheRate(feed, verdicts)
  const explainP95 = percentile(insights.filter((f) => !f.msg.cached).map((f) => f.msg.latency_ms), 95)
  const [health, setHealth] = useState<Health | null>(null)
  const judgeHosted = hostedJudge(verdicts) || !!health?.judge_hosted
  useEffect(() => {
    let alive = true
    const load = () => getHealth().then((h) => { if (alive) setHealth(h) }).catch(() => undefined)
    load()
    const id = setInterval(load, 30000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  return (
    <section className="blk px-4 py-3" style={{ borderTopColor: '#c084fc' }}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="blk-title">Control room</h2>
        <span className="blk-meta normal-case">{orchestration}</span>
      </div>

      {health && (
        <p className="blk-meta mt-2 flex flex-wrap gap-x-3 gap-y-0.5 normal-case" data-runtime>
          <span>{health.replica ? `Azure Container Apps · replica ${health.replica.split('-').slice(-1)[0]}` : 'local server'}{health.revision ? ` · ${health.revision.split('--').slice(-1)[0]}` : ''}</span>
          <span>agents {health.agents ? (health.auth === 'project' ? 'on, Foundry project, keyless' : `on, ${health.auth}`) : 'off'}</span>
          <span>telemetry {health.telemetry ? 'on' : 'off'}</span>
          {health.cache && <span>cache {health.cache.entries} entries · {health.cache.hits} hits / {health.cache.misses} misses since start</span>}
          <span>{health.live_sessions} live session{health.live_sessions === 1 ? '' : 's'}</span>
        </p>
      )}

      <div className="mt-2 grid gap-x-6 gap-y-2 text-sm md:grid-cols-3">
        <StatGroup title="Throughput">
          {(() => {
            const skipped = explainedLine(insights.length, lanes)
            return skipped
              ? <Stat label="Key moments explained" value={skipped.value} sub={skipped.sub} />
              : <Stat label="Key moments explained" value={`${insights.length}${insights.some((f) => f.msg.cached) ? ` (${insights.filter((f) => f.msg.cached).length} cached)` : ''}`} />
          })()}
          <Stat label="Coach consultations" value={coachOn ? String(coaches.length) : 'off'} />
          <Stat label="Director corrected" value={String(correctedCount(feed))} sub="by the house rules" />
          <Stat label="Tool calls by agents" value={String(toolCalls)} />
          <Stat label="Risk windows open" value={risk ? String(risk.active_windows.length) : '–'} />
        </StatGroup>
        <StatGroup title="Graded in public">
          <Stat label="Forecasts graded" value={credibility ? `${credibility.judged}${credibility.pending ? ` +${credibility.pending} pending` : ''}` : '0'} />
          <Stat label="Analyst credibility" value={credibility?.analyst.overall != null ? `${Math.round(credibility.analyst.overall * 100)}%` : '–'} sub={credibility ? `n=${credibility.judged}` : undefined} />
          <Stat label="Naive baseline" value={credibility?.naive.overall != null ? `${Math.round(credibility.naive.overall * 100)}%` : '–'} sub={credibility ? 'same windows' : undefined} />
          <Stat label="Judge" value={judgeLatency != null ? `${(judgeLatency / 1000).toFixed(1)}s` : '–'} sub={judgeHosted ? 'hosted in Foundry' : 'in-process'} />
        </StatGroup>
        <StatGroup title="Cost and latency">
          <Stat label="Foundry tokens this replay" value={tokens ? fmtTokens(tokens) : '0'} sub="fresh runs only" />
          <Stat label="Served from cache" value={cache.rate != null ? `${Math.round(cache.rate * 100)}%` : '–'} sub={cache.total ? `${cache.hits} of ${cache.total}` : undefined} />
          <Stat label="Fan-out, mean" value={mean(fanOut) != null ? `${(mean(fanOut)! / 1000).toFixed(1)}s` : '–'} />
          <Stat label="Explain, p95 fresh" value={explainP95 != null ? `${(explainP95 / 1000).toFixed(1)}s` : '–'} />
        </StatGroup>
      </div>

      <div className="hidden sm:block"><PipelineMap lit={litNodes} judgeHosted={judgeHosted} guardrails={feed.some((f) => (f.msg.trace ?? []).some((e) => e.kind === 'guardrail'))} /></div>
      <ol className="mt-3 grid gap-1 text-sm sm:hidden">
        {[['1 Ingest', 'Event stream'], ['2 Interpret', 'Interpreter, key-moment gate, Risk Monitor, forecast ledger'], ['3 Explain', 'Analyst and Narrator in parallel, Coach, Judge'], ['5 Personalize', 'Director, engine branch, credibility'], ['4 Render', 'Your seat, what-if']].map(([stage, what]) => (
          <li key={stage} className="grid grid-cols-[92px_1fr] gap-2 border-t border-line py-1"><span className="blk-meta text-[11px]">{stage}</span><span className="text-fg-2">{what}</span></li>
        ))}
      </ol>

      <h3 className="blk-meta mt-4">Latest moments, as the agents ran them</h3>
      <div className="mt-2 grid gap-3 lg:grid-cols-2">
        {traced.length === 0 && <p className="text-sm text-muted">The first swimlane appears a few seconds after the first key moment.</p>}
        {traced.slice(0, 6).map((f) => <Swimlane key={f.id} item={f} meta={meta} />)}
      </div>
    </section>
  )
}

function StatGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <dl className="m-0">
      <div className="blk-meta text-[11px]">{title}</div>
      {children}
    </dl>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-line py-0.5">
      <dt className="text-muted">{label}</dt>
      <dd className="display m-0 text-2xl font-extrabold">{value}{sub && <span className="blk-meta ml-1.5 text-[10px] font-semibold normal-case tracking-normal text-muted">{sub}</span>}</dd>
    </div>
  )
}

/** Static map of the system; nodes light briefly when a message arrives. */
function PipelineMap({ lit, judgeHosted, guardrails }: { lit: Set<string>; judgeHosted: boolean; guardrails: boolean }) {
  const nodes: { id: string; label: string; x: number; y: number; w?: number }[] = [
    { id: 'stream', label: 'Event stream', x: 10, y: 40 }, { id: 'interpreter', label: 'Interpreter', x: 150, y: 40 },
    { id: 'gate', label: 'Key-moment gate', x: 290, y: 14 }, { id: 'Analyst', label: 'Analyst · gpt-4o', x: 450, y: 0 },
    { id: 'Narrator', label: 'Narrator · gpt-4.1-mini', x: 450, y: 30 }, { id: 'Director', label: 'Director', x: 640, y: 14 },
    ...(guardrails ? [{ id: 'guardrail', label: 'Guardrail · Content Safety', x: 450, y: 56, w: 160 }] : []),
    { id: 'seat', label: 'Your seat', x: 780, y: 14 },
    { id: 'risk', label: 'Risk Monitor', x: 290, y: 88 }, { id: 'Coach', label: 'Coach · gpt-4o', x: 450, y: 88 },
    { id: 'Engine', label: 'Engine, re-simulated branch', x: 640, y: 88, w: 160 }, { id: 'whatif', label: 'What-if', x: 820, y: 88 },
    { id: 'ledger', label: 'Forecast ledger, +10 min', x: 290, y: 130, w: 150 }, { id: 'Judge', label: judgeHosted ? 'Judge · hosted in Foundry' : 'Judge · gpt-4.1-mini', x: 450, y: 130, w: judgeHosted ? 150 : undefined },
    { id: 'credibility', label: 'Credibility vs naive', x: 640, y: 130, w: 160 },
  ]
  const edges: [string, string][] = [['stream', 'interpreter'], ['interpreter', 'gate'], ['gate', 'Analyst'], ['gate', 'Narrator'], ['Analyst', 'Director'], ['Narrator', 'Director'], ['Director', 'seat'], ['interpreter', 'risk'], ['risk', 'Coach'], ['Coach', 'Engine'], ['Engine', 'whatif'], ['Analyst', 'ledger'], ['ledger', 'Judge'], ['Judge', 'credibility'], ...(guardrails ? [['guardrail', 'Director'] as [string, string]] : [])]
  const pos = Object.fromEntries(nodes.map((n) => [n.id, n]))
  const W = (n: (typeof nodes)[number]) => n.w ?? 120
  // the brief's five stages, as bands over the map: every node sits in the stage it serves
  const STAGES: { label: string; x0: number; x1: number }[] = [
    { label: '1 Ingest', x0: 0, x1: 140 }, { label: '2 Interpret', x0: 140, x1: 440 }, { label: '3 Explain', x0: 440, x1: 630 },
    { label: '5 Personalize', x0: 630, x1: 770 }, { label: '4 Render', x0: 770, x1: 960 },
  ]
  const TOP = 24
  return (
    <svg viewBox={`0 -${TOP} 960 ${158 + TOP}`} className="mt-3 w-full" role="img" aria-label="Agent pipeline over the five stages of the brief: ingest, interpret, explain, render, personalize">
      {STAGES.map((s) => (
        <g key={s.label}>
          <line x1={s.x0} x2={s.x0} y1={-TOP} y2={158} stroke="#3a4560" strokeWidth={1} strokeDasharray="2 4" />
          <text x={s.x0 + 6} y={-TOP + 12} fontSize={10} fontFamily="Barlow Condensed" fontWeight={800} fill="var(--color-muted)" letterSpacing={1.2}>{s.label.toUpperCase()}</text>
        </g>
      ))}
      {edges.map(([a, b]) => {
        const A = pos[a], B = pos[b]
        const on = lit.has(a) && lit.has(b)
        const down = B.y > A.y + 30 && B.x <= A.x  // the ledger hangs below the Analyst: ten match minutes later
        return down
          ? <path key={`${a}-${b}`} d={`M ${A.x + 20} ${A.y + 22} V ${B.y + 11} H ${B.x + W(B)}`} fill="none" stroke={on ? '#c084fc' : '#3a4560'} strokeWidth={on ? 2 : 1.2} strokeDasharray="4 3" />
          : <line key={`${a}-${b}`} x1={A.x + W(A)} y1={A.y + 11} x2={B.x} y2={B.y + 11} stroke={on ? '#c084fc' : '#3a4560'} strokeWidth={on ? 2 : 1.2} />
      })}
      {nodes.map((n) => {
        const on = lit.has(n.id)
        const color = LANE_COLOR[n.id]
        return (
          <g key={n.id} style={{ transition: 'opacity 320ms var(--ease-out)' }} opacity={on || lit.size === 0 ? 1 : 0.55}>
            <rect x={n.x} y={n.y} width={W(n)} height={22} fill={on ? (color ?? '#c084fc') : '#141a2a'} stroke={color ?? '#5c6782'} strokeWidth={1} />
            <text x={n.x + 8} y={n.y + 15} fontSize={11} fontFamily="Barlow Condensed" fontWeight={700} fill={on ? '#0b0f1a' : '#e9eef2'} letterSpacing={0.4}>{n.label.toUpperCase()}</text>
          </g>
        )
      })}
    </svg>
  )
}

/** One moment: agents as lanes, time left to right, tool calls as ticks. */
function Swimlane({ item, meta }: { item: FeedItem; meta: Meta }) {
  const trace = item.msg.trace ?? []
  const total = Math.max(1, ...trace.map((e) => e.t))
  const W = 520, L = 72, R = 60, ROW = 18
  const x = (t: number) => L + (t / total) * (W - L - R)
  const lanes = LANES.filter((lane) => trace.some((e) => e.agent === lane || (lane === 'Engine' && e.stage === 'engine')))
  const H = 12 + lanes.length * ROW + 16
  const bars = lanes.map((lane) => {
    const start = trace.find((e) => e.kind === 'agent_start' && e.agent === lane)?.t ?? trace.find((e) => e.kind === 'stage' && e.stage === 'engine')?.t
    const endEv = trace.find((e) => (e.kind === 'agent_end' || e.kind === 'agent_error') && e.agent === lane) ?? trace.find((e) => e.kind === 'stage_end' && e.stage === 'engine')
    const tok = endEv?.tokens ? (endEv.tokens.input ?? 0) + (endEv.tokens.output ?? 0) : 0
    return { lane, start: start ?? 0, end: endEv?.t ?? total, error: endEv?.kind === 'agent_error' || !!endEv?.error, tools: trace.filter((e) => e.kind === 'tool_call' && e.agent === lane), tok }
  })
  const fallback = trace.find((e) => e.kind === 'fallback')
  const guard = guardrailLine(trace)
  const title = item.msg.kind === 'insight' ? `${item.msg.clock} · ${item.msg.moment.summary.replace(/^\d+:\d+\s*/, '')}` : `${item.msg.clock} · Coach, ${item.msg.trigger === 'injury_concern' ? 'knock' : 'risk window'} on ${item.msg.player.name}`
  void meta
  return (
    <article className="enter border-t border-line pt-2 first:border-0">
      <div className="flex items-baseline justify-between gap-2 text-sm"><span className="truncate font-semibold">{title}</span><span className="shrink-0 tabular-nums text-muted">{item.msg.cached ? 'from cache, ran in ' : ''}{(total / 1000).toFixed(1)}s</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full" role="img" aria-label="agent timeline">
        {bars.map((b, i) => {
          const y = 8 + i * ROW
          return (
            <g key={b.lane}>
              <text x={0} y={y + 10} fontSize={10} fontFamily="Barlow Condensed" fontWeight={700} fill={LANE_COLOR[b.lane]}>{b.lane.toUpperCase()}</text>
              <rect x={x(b.start)} y={y + 2} width={Math.max(2, x(b.end) - x(b.start))} height={10} fill={b.error ? 'var(--color-bad)' : LANE_COLOR[b.lane]} fillOpacity={0.85} />
              {b.tools.map((t, j) => (
                <g key={j}><line x1={x(t.t)} x2={x(t.t)} y1={y} y2={y + 14} stroke="#0b0f1a" strokeWidth={2} /><title>{t.tool}({Object.values(t.args ?? {}).join(', ')})</title></g>
              ))}
              <text x={x(b.end) + 4} y={y + 10} fontSize={9} fill="var(--color-muted)">{Math.round(b.end - b.start)} ms{b.tools.length ? `, ${b.tools.length} tool call${b.tools.length > 1 ? 's' : ''}` : ''}{b.tok ? `, ${fmtTokens(b.tok)} tok` : ''}</text>
            </g>
          )
        })}
        {fallback && <text x={L} y={H - 4} fontSize={9} fill="var(--color-risk)">fallback: {fallback.reason}</text>}
        {guard && <text x={fallback ? W / 2 : L} y={H - 4} fontSize={9} fill={guard.clean ? 'var(--color-teal)' : 'var(--color-risk)'}><title>Azure AI Content Safety checks each commentary line against the facts the agents were given for this moment. Commentary adds colour, so a share not backed is normal; it is a drift signal.</title>{guard.text}</text>}
      </svg>
      {item.msg.kind === 'insight' && <Decision msg={item.msg} />}
      {item.msg.kind === 'coach' && item.msg.proposal && (
        <p className="text-xs text-fg-2">Coach: {item.msg.proposal.action} at {item.msg.proposal.minute}'{item.msg.branch ? `, branch ${item.msg.branch.status} (${item.msg.branch.branch_event_count} events re-simulated, compared in the Bench seat)` : ''}</p>
      )}
    </article>
  )
}

function Decision({ msg }: { msg: InsightMsg }) {
  const v = Object.values(msg.viewers)[0]
  if (!v?.decision) return null
  const all = ['narration', 'insight', 'risk', 'stat']
  const hid = all.filter((c) => !v.decision!.show.includes(c as never))
  return (
    <p className="text-xs text-fg-2">
      Director for <b>{v.profile.mode}/{v.profile.language}</b>: showed {v.decision.show.join(', ') || 'nothing'}{hid.length ? `, hid ${hid.join(', ')}` : ''}, priority {v.decision.priority}{v.decision.personalized_note ? ', personal note added' : ''}{v.decision.enforced ? ', corrected by the house rules' : ''}.
    </p>
  )
}

export type { TraceEvent }
