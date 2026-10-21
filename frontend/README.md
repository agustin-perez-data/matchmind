# MatchMind frontend

React + Vite + TypeScript + Tailwind. An entry screen where you pick a seat,
then one match stage with three compositions:

- **Fan**: top band, pitch with the commentary lower third, momentum, moments.
- **Analyst**: momentum, pitch with the Analyst lower third, a tall xG race,
  match stats.
- **Bench**: the what-if band right under the score, the Risk Monitor expanded,
  Coach proposals, a small pitch.

The URL is the state (`/?seat=bench&lang=es&speed=60&match=THU-NBF-40`; the
language defaults to English, `lang=es` picks rioplatense Spanish). The
seat buttons in the control bar switch seats mid-match: the stream stays open
and the viewer profile sent to the agents changes, so the Director and the
Narrator adapt on the next key moment.

The pitch shows a shot map (dots sized by xG, goals ringed in amber), the ball
with a short trail, and a possession chip (team and third of the pitch). Pass
lines are not drawn: the simulator now keeps the ball continuous inside a move,
but a web of passes still reads as noise.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /matches, /ws and /mcp to the backend on :8000
npm run build    # dist/ for Azure Static Web Apps
```

In production set `VITE_API_BASE` to the backend URL (Container Apps) at build time.

URL parameters prefill the controls and can start the replay, handy for demos:
`/?seat=fan&speed=120&lang=en&player=THU-15&agents=1&coach=1`.

## Design

Direction: a broadcast studio, committed. The two team colours (taken from the
simulator's `primary_color`) own the top band and tint the stage; the score sits
in a white block with the clock in amber; every panel is a broadcast block with
a role-coloured rule (white stats, orange risk, teal coach); key moments arrive
as a lower third over the pitch; the what-if band at the bottom draws the
alternative timeline next to the real one.

Tokens and primitives live in `src/index.css` (`@theme` + `.wipe-*`, `.blk`,
`.lt-*`, `.tag`, `.band-title`). Typefaces: Barlow Condensed (display) and
Barlow (text), tabular numerals throughout. Icons are inline SVG, never emoji.

Motion grammar (one family of curves, three durations, transform/opacity/
filter/clip-path only, `prefers-reduced-motion` honoured):

- one orchestrated entrance when the match goes live: team bands slide in, the
  score drops, panels stagger 60 ms;
- lower thirds wipe in from the left with a touch of blur; score digits drop in
  when they change and the scoring team's band flashes once;
- the what-if branch line draws from the divergence minute, goals and knocks
  pop in staggered;
- risk and momentum bars scale with a strong ease-out; passes only fade
  (high-frequency motion stays minimal);
- nothing loops, pulses or glows.
