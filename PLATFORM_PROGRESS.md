# FPL Assistant Platform Progress

Last updated: 2026-09-13
Branch: `web-platform`

## Architecture change (2026-09-13)

The user reviewed the Flask/Jinja/vanilla-JS build (documented below as "v1") and asked for a
rebuild on React/Next.js with a real component library, because the vanilla build had visual
mistakes and didn't match `fpl-assistant-prototype.html` closely enough. Decisions taken (see
chat for the full clarifying-question exchange):

- **Next.js frontend + Flask API backend.** `webapp/app.py` stays exactly as-is for its
  `/api/*` endpoints (the optimiser seam is untouched); a `flask-cors` addition is the only
  backend change, needed because the two dev servers run on different ports. The old Jinja
  page routes (`/`, `/team`, etc. returning `index.html`) and `webapp/templates/`,
  `webapp/static/` (the v1 vanilla-JS build) are **still in place and untouched** — they will
  be deleted once the new frontend reaches feature parity across all seven surfaces, not before.
- **UI kit: shadcn/ui (Base UI primitives, not Radix — this shadcn version ships on
  `@base-ui/react`) + Tailwind v4.** In practice, most of the visual system does not come from
  shadcn's default theme at all: `fpl-assistant-prototype.html`'s entire hand-written CSS
  (tokens, chrome, every component class) was ported verbatim into
  `webapp/frontend/app/broadcast.css` and is unlayered so it overrides shadcn's `@layer base`
  defaults. shadcn/Base UI is used only for accessible interaction primitives (Dialog for the
  player drawer and squad editor) with the prototype's own classes applied to their content,
  not shadcn's default styling. This was the deliberate call: reusing CSS that already matches
  `DESIGN.md` exactly is both faster and more faithful than rebuilding the look from Tailwind
  utilities or a component library's default skin.
- **Repo layout: inside `webapp/`, not a new top-level folder.** `webapp/frontend/` is a
  self-contained Next.js (App Router, TypeScript) project; `webapp/app.py` and
  `webapp/platform_data.py` remain the Python backend. Two dev servers: Flask on `:5000`,
  Next on `:3000`.

**Important data-fidelity note carried over from the prototype review:** a large fraction of
`fpl-assistant-prototype.html`'s content is fabricated demo data with no real backend
equivalent — manager overall/GW rank, a live FPL-account "Sync ID", set-piece taker lists, chip
usage state, "what changed since your last visit" feeds, source-reliability dials, and the
analyst "insight" essays are all seeded prototype copy (`DESIGN.md` §Accepted debt says this
explicitly: "All figures are seeded prototype data"). The original task instruction is to
connect only to legitimate local data and never invent production data connections. So the
rebuild matches the prototype's **visual system** (tokens, layout, component shapes, motion)
exactly, but every number and list is either real (local player/team/fixture CSVs, or
predictions when available) or the widget is honestly omitted/simplified rather than faked.

## Completed work

### v1 — Flask/Jinja/vanilla-JS (superseded, still live at :5000 pending full v2 parity)
- `webapp/platform_data.py`: read-only local adapter over `data/<season>/{teams,fixtures,players_raw}.csv`.
- Routed Jinja shell + 6 ES modules implementing all seven surfaces against real local data.
- `tests/test_platform_data.py`, `tests/test_webapp.py` (pytest, still passing, untouched).
- Pushed to `origin/web-platform` at commit `a9a512d4`.

### v2 — Next.js rebuild (in progress, this commit)
- Scaffolded `webapp/frontend/` (Next.js 16, React 19.2, TypeScript, Tailwind v4, Turbopack)
  and initialised shadcn/ui (Dialog, Tabs, Select, Switch, Command, Tooltip, Badge, etc.).
- Ported the full prototype design system into `app/broadcast.css` (tokens, chrome, all
  component classes, responsive breakpoints), imported unlayered ahead of shadcn's theme.
- `lib/types.ts`, `lib/api.ts`, `lib/format.ts`, `lib/squad.ts`: typed client for the Flask API,
  matching `webapp/platform_data.py` and `webapp/app.py` response shapes exactly.
- `components/providers/app-provider.tsx`: root context — fetches `/api/platform` once, holds
  squad selection (persisted to `localStorage`, same key as v1 so a saved squad carries over),
  the last optimiser result, the open player-profile drawer state, and a toast.
- Chrome: `CrestTicker` (real 20 clubs), `MainNav` (real Next.js routing across all six pages,
  travelling ink-blade indicator repositioned via `ResizeObserver` so font-swap reflow doesn't
  desync it), `DeadlineClock` (computed from the real earliest kickoff time in the current
  gameweek's fixtures — not the prototype's fabricated countdown).
- **My Team surface fully rebuilt and verified**: hero with real season/gameweek/player-count
  stats, pitch with club-gradient player markers (captain armband, availability flags), squad
  editor (a `teamsheet`-style picker reusing the prototype's Comparison-screen picker classes,
  since the prototype's own My Team assumes an already-synced FPL account we don't have),
  bench, and an availability-desk rail block using real `news`/`status` data. Auto-pick calls
  the real `/api/squad` optimiser.
- `components/player-drawer.tsx`: a custom Base-UI-Dialog-powered slide-in drawer (not shadcn's
  centered modal) using the prototype's exact `.drawer`/`.dsec`/`.dbugs`/`.fixrib`/`.stable`
  classes. Shows real season stats and a real next-fixture ribbon (with correct FDR colours)
  instead of the prototype's fabricated last-5-gameweek ladder, which needs per-gameweek
  historical data this snapshot doesn't carry.
- `components/player-photo.tsx`: shared broken-image handling (the PL photo CDN 404s for a
  real chunk of players — loans, youth, recent signings). v1 had this via a manual
  `addEventListener("error", ...)`; the first version of the React port dropped it, which
  showed as visible broken-image icons in bench cards — caught in visual QA and fixed with a
  small shared component used everywhere a player photo renders.
- **Transfer Studio fully rebuilt and verified**: dual desks (pink "Player out" / lime
  "Player in", both with position and price/flag filters and search), a transfer channel with
  staged out/in slots and a lane connector, live decision-bugs (bank after, points delta, hit
  cost — points delta honestly shows "--" when predictions are unavailable rather than a fake
  number), and free-transfers/bank inputs (real parameters the actual `/api/transfers`
  optimiser accepts, not fabricated). "Run full analysis" calls the real optimiser and renders
  its actual per-transfer-count rows (gross/hit/net gain, real out→in lists) instead of the
  prototype's fictional 6-metric impact grid (fixture swing, captaincy relevance and risk
  assessment have no real data source, so they're not included — see the fidelity note above).
- Comparison, Captain & Form, News Wire, Fixture Matrix are still **stub pages**
  (`components/coming-soon.tsx`) with working nav — not yet rebuilt in the new system.
- Fixed two real bugs found in visual QA while building Transfer Studio (both explained in
  detail under Test evidence below): a negative-money formatting bug (`money()` rendered `-2.6`
  as `£-2.6m` instead of `-£2.6m`), and a mobile-width layout bug in the ported CSS itself
  (confirmed present in the unmodified `fpl-assistant-prototype.html` too, by serving it
  locally and comparing bounding boxes) where the Transfer Channel's title/decision-read/footer
  rows collapsed to a single narrow column instead of spanning full width, because a
  `max-width:1280px` breakpoint's `grid-column:auto` reset is never undone by the
  `max-width:860px` breakpoint's new `grid-template-areas`. Fixed with a small targeted
  addition inside the 860px block, documented in `broadcast.css` as a correction rather than
  part of the verbatim port.

## Current work in progress

Rebuilding the remaining four surfaces (Comparison, Captain & Form, News Wire, Fixture Matrix)
on the same pattern as My Team and Transfer Studio: prototype markup/classes + real data from
the already-fetched `/api/platform` snapshot, with the same honest-omission rule for
prototype-only fabricated content.

## Remaining work

- Rebuild the four stub surfaces.
- Once all seven have parity with v1's real-data coverage, delete `webapp/templates/`,
  `webapp/static/`, and the Jinja page routes in `webapp/app.py` (keep only `/api/*`), and
  make Next.js the only frontend.
- Decide on a production setup: either Next.js `output: "standalone"` behind the same process
  manager as Flask, or keep them as two separately deployed services. Not needed for local dev.
- Same standing decision as before on `predictions_next_gw.csv` / `saved_models/*/*.joblib` —
  still absent from disk, still needs explicit user go-ahead before any retraining work.
- Optional polish once all seven surfaces exist: keyboard-navigation pass, `next/image` for
  the two remaining plain `<img>` lint warnings if bandwidth/LCP ever matters in production,
  full-page mobile screenshots per surface.

## Known blockers or decisions needed

- `predictions_next_gw.csv` / `saved_models/*/*.joblib` — unchanged from before, see above.
- **`next/font/google` is unreliable in this environment.** It fetches font files from Google's
  servers at build time; `npm run build` crashed the Turbopack worker (`exit code 134`,
  V8 fatal error) intermittently — roughly half the time — whenever `next/font/google` was in
  the tree. Reverted to plain `<link>` tags for Google Fonts in `app/layout.tsx` (a documented,
  valid App Router pattern), which built cleanly 3/3 times after reverting and 1/2 times before
  (i.e. it isn't otherwise flaky). This costs one accepted ESLint warning
  (`@next/next/no-page-custom-font`), suppressed with a comment explaining why. If a future
  session has a more reliable network path to Google Fonts, switching back to `next/font` would
  self-host the fonts and remove that warning for real, but do not do it without confirming
  `npm run build` passes at least 5/5 times first.
- Premier League player photos and crests are external prototype assets; production publication
  still needs rights confirmation, as recorded in `DESIGN.md`.
- **`fonts.gstatic.com` is flaky from this environment generally**, not just at build time —
  Playwright screenshots occasionally timed out on "waiting for fonts to load" with
  `ERR_CONNECTION_TIMED_OUT` / `ERR_QUIC_PROTOCOL_ERROR` in the console. The `display=swap` on
  the font `<link>` means the app itself is unaffected (text renders in the fallback stack
  immediately), but a future session doing visual QA should retry a hung screenshot once or
  raise its timeout rather than assume the page is broken.

## Test and verification evidence

- `npm run build` (webapp/frontend): passes, all 8 routes prerender as static content. Verified
  3 consecutive clean runs after the font revert, and again after the Transfer Studio commit.
- `npm run lint`: 0 errors, 2 accepted warnings (plain `<img>` instead of `next/image` for
  external CDN photos needing custom error handling — a deliberate, documented trade-off, not
  an oversight).
- Live browser verification (Playwright, Next dev server on `:3000` + Flask on `:5000`, real
  local data — 746 players, 20 clubs, GW10):
  - Diagnosed and fixed a real dev-environment trap: opening the Next dev server via the raw
    `127.0.0.1` IP (instead of `localhost`) silently blocked its HMR WebSocket, which aborted
    the client bundle before React ever hydrated — every effect (including the initial data
    fetch) silently never ran, with zero console errors, making it look like a data-fetching
    bug. Fixed properly with `allowedDevOrigins: ["127.0.0.1", "localhost"]` in
    `next.config.ts` rather than just remembering to type `localhost`.
  - Found and killed orphaned `next dev` / stale Python processes left running from earlier
    session restarts (Windows doesn't kill the child when the parent shell task is stopped) —
    an environment artifact, not an app defect, but worth knowing if `next dev` refuses port
    3000 or serves stale content again.
  - Built and saved a legal 15-player squad through the real squad-editor UI (exact-ID
    Playwright automation, not name substring matching, after the first attempt with
    substring-matched names picked the wrong players and correctly failed validation — that
    was a test bug, not an app bug). Pitch rendered 5-3-2, captain armband assigned, bench and
    availability desk populated from real data, toast confirmed the save.
  - Opened a real player profile via the drawer: correct season stats, a real 5-fixture ribbon
    with correct FDR border colours, and the honest "Prediction unavailable" note.
  - Caught and fixed the nav ink-blade mispositioning itself under the wrong tab on first paint
    (Google Fonts loading after first measurement shifted tab widths) via `ResizeObserver`.
  - Caught and fixed broken-image icons on bench player photos with no CDN entry, via the
    shared `PlayerPhoto` component.
  - Checked all 6 routes return 200 and a 375×844 mobile screenshot of My Team — renders
    correctly, matches the prototype's mobile breakpoint behaviour (including its own quirk of
    an odd fifth hero-strip cell wrapping alone in a 2-column mobile grid).
  - Zero console errors on the finished My Team page at both viewport sizes.
  - Transfer Studio: staged a real out→in swap (exact-ID automation again) and confirmed the
    decision-bugs updated correctly, including a negative bank-after value once the money-
    formatting bug above was fixed. Confirmed "Run full analysis" is correctly `disabled` since
    predictions are unavailable (same honest pattern as My Team's auto-pick) — could not
    exercise the live optimiser call itself for that reason, but it reuses the exact same
    `lib/api.ts` client and error handling already verified working for `/api/squad`. Confirmed
    Reset correctly clears both staged players. Checked and fixed the mobile-width Transfer
    Channel layout bug (see above) by comparing bounding boxes against the actual unmodified
    prototype file served locally, not just against intuition.
  - Zero console errors on the finished Transfer Studio page at both viewport sizes.

## Next recommended milestone

Rebuild Comparison next (the prototype's own `.picker`/`.teamsheet` classes are already reused
by the My Team squad editor, so the player-picker half is a known quantity), then Captain &
Form, News Wire, Fixture Matrix in that order, each as its own verified, committed increment.
After all seven exist, remove the superseded v1 Jinja/vanilla-JS files in one cleanup commit.
