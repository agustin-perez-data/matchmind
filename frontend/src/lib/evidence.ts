// The three proofs the entry screen shows under the headline. Every number is a measurement reported in
// README.md ("AI that gets graded, not just heard"), copied by hand so the landing never claims something
// the write-up does not: the risk table and the ground-truth sweep (README, "AI that gets graded", 40 simulated matches)
// and the groundedness run (28 items scored by Azure AI Evaluation's grader). Update both places together.
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
    value: '2x',
    compare: 'better than chance',
    caption: 'Of the players who got hurt, more than one in four was among the three the Risk Monitor had flagged as most at risk; picking at random gets one in seven.',
    source: '40 simulated matches: 27 % against 14 %, and it holds in five other injury worlds'
  },
  {
    value: '27 min',
    compare: 'a minutes-played rule: 18',
    caption: 'Average warning between the monitor flagging a player and the knock. Time enough to take him off.',
    source: 'same 40 matches',
  },
  {
    value: '4.9 / 5',
    caption: 'How closely the Analyst stuck to the facts it was given, scored by an independent grader, not by us.',
    source: '28 moments, Azure AI Evaluation',
  },
]
