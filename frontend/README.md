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

Design tokens live in `src/index.css` (`@theme`): deep blue-green field, amber
reserved for goals and top-priority cards, team colours for identity, a
separate status palette for risk bands. Typefaces: Barlow Condensed (display)
and Barlow (text), tabular numerals throughout.
