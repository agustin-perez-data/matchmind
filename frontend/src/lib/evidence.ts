// The three proofs the entry screen shows under the headline. Every number is a measurement reported in
// README.md ("AI that gets graded, not just heard"), copied by hand so the landing never claims something
// the write-up does not: the risk table (README L88-90, 40 simulated matches) and the groundedness run
// (README L170-171, 28 items scored by Azure AI Evaluation's grader). Update both places together.
export type Proof = {
  /** The number as shown, already formatted. */
  value: string
  /** The comparison that gives the number its meaning, when there is one. */
  compare?: string
  /** One short sentence: what the number is. */
  caption: string
  /** Where it was measured. */
  source: string
}

export const PROOFS: readonly Proof[] = [
  {
    value: '32 %',
    compare: 'random 14 %',
    caption: 'of knocks hit a player the Risk Monitor had in its top three.',
    source: '40 simulated matches, offline evaluation',
  },
  {
    value: '25 min',
    compare: 'baseline 18',
    caption: 'average warning before a knock, from workload alone.',
    source: 'same 40 matches, minutes-only rule as the baseline',
  },
  {
    value: '4.9 / 5',
    caption: 'groundedness of what the Analyst said, scored by an independent grader.',
    source: '28 moments, Azure AI Evaluation',
  },
]
