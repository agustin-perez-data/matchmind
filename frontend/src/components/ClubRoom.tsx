import { useEffect, useState } from 'react'
import { getMeta, getReport, listMatches, type MatchReport, type MatchRow } from '../lib/api'
import { LOGOUT_URL, getMe, type Me } from '../lib/auth'
import { menuFixtures } from '../lib/fixtures'
import { staffReportHtml, warningSummary } from '../lib/staffReport'
import { Crest } from './Crest'
import { Wordmark } from './Wordmark'

type Card = { row: MatchRow; report: MatchReport | null; error: string | null }

const providerName = (p: string) => (p === 'aad' ? 'Microsoft' : p === 'github' ? 'GitHub' : p)

/** The club area: the matchday's staff reports, behind Static Web Apps sign-in. */
export function ClubRoom() {
  const [me, setMe] = useState<Me | null | undefined>(undefined)
  const [cards, setCards] = useState<Card[] | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    getMe().then((m) => { if (alive) setMe(m) })
    listMatches()
      .then(async (rows) => {
        const list = menuFixtures(rows).map((f) => f.row)
        const filled = await Promise.all(list.map(async (row): Promise<Card> => {
          try { return { row, report: await getReport(row.match_id), error: null } }
          catch (e) { return { row, report: null, error: (e as Error).message } }
        }))
        if (alive) setCards(filled)
      })
      .catch((e: Error) => { if (alive) setFailed(`Could not reach the match server (${e.message}).`) })
    return () => { alive = false }
  }, [])

  const open = async (c: Card) => {
    if (!c.report) return
    const meta = await getMeta(c.row.match_id)
    const html = staffReportHtml({ meta, score: c.report.score, risk: c.report.risk, entries: [], credibility: null, generatedAt: new Date() })
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }

  return (
    <section className="enter mx-auto w-full max-w-6xl px-5 pb-14 pt-6 sm:px-8 sm:pt-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <Wordmark />
        <div className="flex items-center gap-4 text-sm text-fg-2" data-testid="club-user">
          {me === undefined ? null : me
            ? <span>Signed in as <b className="text-fg">{me.name}</b> ({providerName(me.provider)})</span>
            : <span className="text-muted">Local development: Static Web Apps sign-in runs only on the deployed site.</span>}
          {me ? <a className="btn-quiet" href={LOGOUT_URL}>Sign out</a> : null}
        </div>
      </header>
      <h1 className="display mt-8 text-5xl font-black uppercase leading-none">Club area</h1>
      <p className="mt-3 max-w-[66ch] text-base text-fg-2">
        The matchday as the performance staff sees it on Monday: every match's knocks, how early the Risk Monitor warned,
        and who was still at risk at full time. Each report is generated on the server from the match itself; nobody had to watch it.
      </p>
      {failed && <p className="mt-6 text-bad">{failed}</p>}
      {!cards && !failed && <p className="mt-6 text-muted">Preparing the matchday reports.</p>}
      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {cards?.map((c) => {
          const h = c.row.home_team, a = c.row.away_team
          return (
            <article key={c.row.match_id} className="blk blk-coach flex flex-col gap-3 px-5 py-4" data-testid="club-card">
              <div className="flex items-center gap-3">
                <Crest team={h} size={32} />
                <span className="display text-2xl font-black uppercase leading-none">
                  {h.short_name} {c.report?.score[h.team_id] ?? ''} - {c.report?.score[a.team_id] ?? ''} {a.short_name}
                </span>
                <Crest team={a} size={32} />
              </div>
              <p className="text-sm text-fg-2">{c.report ? warningSummary(c.report.risk) : c.error ?? 'Loading.'}</p>
              <div className="mt-auto flex flex-wrap gap-2">
                <button type="button" className="btn btn-teal text-sm" disabled={!c.report} onClick={() => open(c)}>Open the staff report</button>
                <a className="btn-quiet text-sm" href={`/?seat=bench&match=${c.row.match_id}`}>Watch it on the bench</a>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
