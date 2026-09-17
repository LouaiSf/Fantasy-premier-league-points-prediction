# FPL Assistant Platform Progress

Last updated: 2026-09-15
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
  `webapp/static/` (the v1 vanilla-JS build) were deleted after the new frontend reached feature
  parity across all seven surfaces; `webapp/app.py` now serves the API surface only.
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
- **Comparison fully rebuilt and verified**: plinth A/B seats, a picker reusing the same
  teamsheet pattern as the My Team squad editor (pool/position/club filters, search), club-
  gradient duel cards, and a 12-category accordion of real dual-bar comparisons (season totals,
  form, ICT/xG/xA, ownership) with a genuine leader tick per row. The prototype's per-category
  analyst prose and multi-week "comparison horizon" tabs (Next GW/3/5/Season) have no real data
  source (no multi-gameweek forecast, no written analysis), so they're replaced with an honestly
  *computed* verdict — "X leads N of 12 categories" tallied from the real numbers, not invented
  commentary — shown in the same `.verdict`/`.stamp` visual treatment.
- Extracted `lib/club-colors.ts` after finding the same club-name-needs-quoting bug (see below)
  duplicated between `player-marker.tsx` and the new Comparison page — one shared, typo-checked
  map now, instead of copy-pasting it into every surface that needs a club gradient.
- **Captain & Form fully rebuilt and verified**: spotlight-gradient hero naming the real lead
  candidate, a squad/all-players toggle (reusing `.mini-chip`, not the prototype's own
  nonexistent-in-CSS "segmented" pattern that the old v1 build had invented), a 10-candidate
  runway with real next-fixture/FDR, form and ICT meters, and a risk badge derived from real
  `status`/`chance_of_playing_next_round` (nailed on / some doubt / high risk — not fabricated),
  plus a top-2 "Captaincy battle" head-to-head reusing the same dual-bar pattern as Comparison.
  The prototype's Form Timeline (needs per-gameweek history this snapshot doesn't carry),
  Opponent Vulnerability (needs defensive analysis not in the data), Upside/Safety grid
  (redundant with the runway's meters), and the analyst "Insight" essay (pure invented prose)
  are all omitted rather than faked — see the fidelity note at the top of this document.
- **News Wire fully rebuilt and verified**: a real scrolling ticker of every flagged player's
  status text, filters that map onto real FPL `status` codes (Injuries → `status === "i"`,
  Suspensions → `status === "s"`, Doubtful → `chance_of_playing_next_round < 100`, not
  free-text categorisation the data doesn't carry), a lead story built from the single most
  severe real note, and two reading modes (Desk list / Cards grid) over the same filtered real
  data. The prototype's fabricated press-conference quotes/citations, "what changed since your
  last visit" feed, price-watch panel, return-date timeline, and source-reliability dial are all
  omitted — none of those are derivable from a single-snapshot dataset with no timestamps or
  price history, so showing them would mean inventing data, not reporting it. The prototype's
  third reading mode ("Picture line" horizontal reel) is also skipped: it's the same content in
  a different layout, and two modes already demonstrate the pattern without meaningfully adding
  more real information.
- **Fixture Matrix fully rebuilt and verified**: renders the next eight gameweeks from the live
  `/api/platform` snapshot, FDR/venue cells for all 20 clubs, four easiest-run summaries,
  squad-only filtering, and a keyboard-reachable horizontal matrix reel with sticky club labels
  and a scroll cue. Responsive desktop, tablet, and phone layouts were checked against the
  prototype's broadcast styling.
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

## Current status

The eight React/Next.js surfaces are complete: My Team, Transfer Studio, Comparison, Captain &
Form, News Wire, Watchlist & Differentials, Chip Advisor, and Fixture Matrix. Fixture Matrix uses
the same prototype markup/classes and real `/api/platform` snapshot data as the other surfaces.

## Remaining work

- Legacy Jinja/static frontend removal is complete in commit `58cf9e09`; Next.js is now the only
  frontend and `webapp/app.py` retains only `/api/*` routes.
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

## Verification refresh (2026-09-15)

- React 19 hook lint blockers were fixed with derived fallback state and cancel-safe deferred
  loading effects in the shared photo, crest, drawer, toast, Watchlist, and Chip Advisor paths.
  Dev-only `react-grab`, `react-scan`, and `react-doctor` tooling is installed for continued
  frontend inspection.
- Fixed desktop navigation overflow alignment by making the tab rail start-aligned while keeping
  the active-tab scroll behavior.
- `npm run lint` (webapp/frontend): passes with 0 errors and 2 accepted external-asset `<img>`
  warnings in the shared photo and crest fallbacks.
- `npm run build` (webapp/frontend): passes with TypeScript and static generation complete across
  the application routes.
- `python -m pytest -q`: 6 tests passed; one pre-existing pandas/bottleneck version warning
  remains.
- `npm run doctor -- --json`: `ok: true`, 0 errors, and 34 advisory warnings, primarily the
  pre-existing complexity/accessibility suggestions documented by the tool.
- Manual browser QA against a fresh production build at 1280×900, 768×900, and 375×844 found
  no document overflow, 20 club rows, 160 fixture cells, working horizontal matrix scrolling,
  sticky club labels, and zero console errors. Live squad-only filtering was also exercised with
  the saved 15-player squad and correctly reduced the matrix to 10 club rows.
- An independent visual-QA reviewer subagent was unavailable in this host; the recorded browser
  checks were performed directly with Playwright and CUA instead.

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
  - Comparison: filled both seats through the real teamsheet picker, confirmed the arena
    (duel cards, ribbon, 12-category accordion) renders with correctly computed dual-bar widths
    and leader ticks, and the auto-generated verdict text and category tally matched the
    underlying numbers by hand-check. Verified at 375×844 — plinths stack to one column per the
    prototype's own mobile rule, no overlap.
  - Zero console errors on the finished Comparison page at both viewport sizes.
  - Captain & Form: caught mid-build that `.segmented` (used for the squad/all toggle) does not
    exist anywhere in the ported prototype CSS — it was invented for the old v1 vanilla-JS
    build and doesn't belong in a "verbatim port" — swapped for the real `.mini-chip` pattern
    before it ever reached a screenshot. Toggled squad → all players live and confirmed the
    runway re-ranks correctly (all-players pool surfaced a real 746-player top scorer by form,
    different from the squad-only leader). Clicked a runway candidate and confirmed the real
    player drawer opens. Verified at 375×844, no overlap.
  - Zero console errors on the finished Captain & Form page at both viewport sizes.
  - News Wire: found and fixed a real rendering bug via full-page screenshot comparison, not
    just code review — an inline `style={{border: 0}}` meant to reset the `<button>` default
    for `.wire-item` rows was overriding the CSS class's own `border-left`/`border-top` accent
    styling (inline styles always beat external stylesheet rules regardless of specificity), so
    every wire item was silently missing its priority-colour left bar and its divider line.
    Fixed by resetting only `background`/`font` inline and leaving all border management to the
    CSS class. Verified the five filters (all real `status`-code-backed) change the note count
    correctly, the Desk/Cards view switch renders the same filtered data in both layouts, and
    checked the codebase for the same border-reset mistake elsewhere (none found). Verified at
    375×844, no overlap.
  - Zero console errors on the finished News Wire page at both viewport sizes.

## Comprehensive Fix & 2026-27 Elevation (Completed 2026-09-14)

Following `COMPREHENSIVE_FIX_PLAN.md`:

### 1. Season Data & Model Pipeline
- **2026-27 Season Loaded**: Acquired official 2026-27 season data (`teams.csv`, `fixtures.csv`, `players_raw.csv`, `cleaned_players.csv`, `player_idlist.csv`, `gws/merged_gw.csv`, `gws/gw1.csv`).
- **Models & Predictions Deployed**: Transferred precomputed Colab model weights (`saved_models/direct/{GK,DEF,MID,FWD}/` with 159–220 features per position) and `predictions_next_gw.csv` (489 players, 20 clubs) into active paths. Added `fpl_results/` to `.gitignore`.
- **Roster & Alignment**: Resolved league roster alignment (Coventry, Hull, and Ipswich confirmed as active promoted clubs).

### 2. Backend & Optimization Fixes
- **NameError Fix**: Resolved `best = max(data['rows'], key=lambda r: r['net'])` in `scripts/optimise.py` line 360.
- **Exception Cleanliness**: Replaced `SystemExit` with `ValueError` in `squad_from_names()`.
- **IDE & Static Resolution**: Added `scripts/__init__.py` and fallback import `from scripts import optimise as opt` in `webapp/app.py` to eliminate IDE language-server warnings.
- **Player History**: Added `player_history(root, season, element_id)` in `webapp/platform_data.py` reading `merged_gw.csv` and exposed `GET /api/player/<id>/history`.
- **Live Refresh & Mtime Watcher**: Added `POST /api/refresh` to pull new season data and predictions, and added automatic file `mtime` check in `app.py`'s `state()`.
- **V1 Elimination**: Deleted superseded `webapp/templates/` and `webapp/static/` directories and removed legacy Jinja routes from `webapp/app.py`. All 6 pytest backend tests pass green.

### 3. Frontend Resiliency & Design System Elevation
- **Error Boundary**: Created `components/error-boundary.tsx` with broadcast styling and wrapped app layout.
- **Crest Handling**: Created `components/club-crest.tsx` with club color gradient & short-name badge fallback on CDN 404; replaced raw `<img>` crests across all surfaces.
- **Photo Initials Fallback**: Enhanced `components/player-photo.tsx` to render `.photo-fb` initials on image 404s.
- **Mobile Responsive Alignment**: Fixed `.pm-badge`, `.pm-flag`, `.pm-pred`, and `.armband-ring` geometry in `broadcast.css` for mobile screens (<560px and <860px).
- **Squad Persistence**: Updated `components/providers/app-provider.tsx` to persist squad by element ID with season scoping, budget warning, and queued toasts with dismiss buttons.
- **Watchlist & Differentials Surface**: Built `app/watchlist/page.tsx` featuring Best Value (points-per-million), Differentials (customizable ownership cutoff), Overpriced traps, and Promoted/New signings with drawer inspection.
- **Chip Advisor Surface**: Built `app/chips/page.tsx` featuring recommendations for Triple Captain, Bench Boost, Free Hit, and Wildcard alongside a schedule congestion and FDR fixture heatmap.
- **Zero Build Errors**: Full `npm run build` static compilation succeeded across all 9 App Router pages.
