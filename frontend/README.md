# MatchMind frontend

React 19, Vite, TypeScript and Tailwind v4. One entry screen (a live preview loop, three measured proofs, one
primary action into the derby, four seats) and one match stage with four compositions: Fan, Analyst, Bench and
Control room. The pitch draws the 22 players from the positional model the backend streams as `kind: "frame"`.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /matches, /ws, /mcp, /tts and /health to the backend on :8000
npm test         # vitest, pure functions in src/lib
npm run lint     # oxlint
npm run build    # dist/ for Azure Static Web Apps; set VITE_API_BASE to the API URL at build time
```

URL parameters prefill the controls and can start a replay: `/?seat=fan&match=THU-NBF-40&speed=60&lang=es&team=neutral`.

Design tokens and primitives live in `src/index.css` (colours, the broadcast blocks, lower thirds, motion). Display
type is Barlow Condensed, text is Barlow; motion respects `prefers-reduced-motion`.
