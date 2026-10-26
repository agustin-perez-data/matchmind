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
    value: '1 in 3',
    compare: 'random would be 1 in 7',
    caption: 'Of the players who got hurt, one in three was among the three the Risk Monitor had flagged as most at risk.',
    source: '40 simulated matches: 32 % against 14 % for a random pick',
  },
  {
    value: '25 min',
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
