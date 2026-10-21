# MatchMind frontend

React + Vite + TypeScript + Tailwind. One page: scoreboard, pitch, xG race,
momentum, agent feed, Load & Risk Monitor and the what-if panel.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /matches, /ws and /mcp to the backend on :8000
npm run build    # dist/ for Azure Static Web Apps
```

In production set `VITE_API_BASE` to the backend URL (Container Apps) at build time.

URL parameters prefill the controls and can start the replay, handy for demos:
`/?speed=120&mode=casual&lang=en&player=THU-15&agents=1&coach=1&autostart=1`.

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
