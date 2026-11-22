# FPL Assistant frontend

The Next.js site for FPL Assistant. It renders the pages and calls the Flask API
in `webapp/app.py` for every number it shows. What the site does, how to run the
API beside it, and how the two are deployed are in the
[main README](../../README.md#the-web-ui).

## Commands

```bash
npm install
npm run dev                   # http://localhost:3000, API expected on :5000
npm exec tsc -- --noEmit      # type-check
npm run lint
npm run build                 # production build
```

`NEXT_PUBLIC_API_BASE` points the site at the API (default
`http://127.0.0.1:5000`). Open the dev server through `localhost` or
`127.0.0.1`. Those two are in `allowedDevOrigins`, and any other host blocks
hydration without an error.

## Layout

```text
app/              one folder per page; broadcast.css holds the design system
components/       shared UI: chrome (nav, ticker, clock), team, chips, charts, motion
lib/              API client and types, finance, transfer planning, local storage
```

The visual system is specified in [`docs/DESIGN.md`](../../docs/DESIGN.md) and
ported from [`docs/fpl-assistant-prototype.html`](../../docs/fpl-assistant-prototype.html).
Fonts are self-hosted through Fontsource, not loaded from Google at runtime.
