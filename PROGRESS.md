# Implementation Progress

## 2026-09-17 — Task 1.3: Model path fallback
Added fallback from `saved_models/direct/meta.json` to `fpl_results/saved_models/direct/meta.json` in `model_summary()`.

## 2026-09-17 — Task 1.4: Prediction merge on element ID
Changed `/api/platform` enrichment join from player name to `element` (FPL integer ID) to prevent mis-matches and ghost entries.

## 2026-09-17 — Task 3: Chips page broadcast rewrite
Rewrote `app/chips/page.tsx` using broadcast design system — replaced all inline styles and emoji icons with CSS classes, added `chip-advisor-*` and `chip-conf` classes to broadcast.css, replaced emoji with styled letter-circle icons (TC/BB/FH/WC).

## 2026-09-17 — Task 4: Watchlist page broadcast rewrite
Rewrote `app/watchlist/page.tsx` using broadcast design system — removed all inline styles and `onMouseEnter`/`onMouseLeave` handlers, added `watch-*` CSS classes to broadcast.css with CSS `:hover` effects, responsive breakpoints at 860px/560px.

## 2026-09-17 — Task 5: Captain badge (pm-badge verified)
Confirmed `.pm-badge` class in broadcast.css and usage in `player-marker.tsx` are correctly aligned with the gold circle spec.

## 2026-09-17 — Task 6: Loading and empty state components
Created `components/loading.tsx` and `components/empty-state.tsx` with broadcast spinner and styling. Added `.loading-state`, `.loading-spinner`, `.loading-label`, `.empty-state`, `.empty-title`, `.empty-message` to broadcast.css. Updated all 8 page routes and player-drawer to use `<Loading />` component.

## 2026-09-17 — Task 7: Error boundary fix
Fixed `error-boundary.tsx` — removed non-existent `panel card-tint` and `btn-primary` CSS classes, changed `--muted-foreground` to `--muted-mid`, using `.btn` directly.

## 2026-09-17 — CSS additions: blade vars + badge
Added `--blade` and `--blade-sm` CSS variables to `:root` in broadcast.css. Added `.badge` utility class for page header eyebrow labels.

## 2026-09-17 — Task 1.1/1.2: Regenerate predictions for 2026-27
`predictions_next_gw.csv` was still stale (Burnley/West Ham/Wolves, missing Coventry/Hull/Ipswich) despite earlier Phase 1 commits. Re-ran `predict_gameweek.py --season 2026-27 --no-api` via the anaconda3 Python environment (the default `python` on PATH lacks lightgbm). All 616 2026-27 players now resolve with 0 id mismatches against `players_raw.csv`, all 20 correct teams present. File is gitignored (all `*.csv` are), so nothing to commit for it directly — anyone continuing this work must regenerate it locally the same way if it goes stale again.

## 2026-09-17 — Task 8: Nav responsive + crest ticker accessibility
`.nav-actions` (refresh button, deadline clock) was `display:none` below 1080px, hiding functionality on tablets. Now shrinks instead: refresh becomes icon-only, deadline clock drops its context label. Crest ticker crests were `<button>` elements with no `onClick`, an unlabeled non-functional control for screen readers — changed to `<span role="img" aria-label="{team} crest">`.

## 2026-09-17 — Task 1.5: Model info footnote
Added `prediction_timestamp` to `/api/platform`. New `ModelInfo` component shows model name, test R², and time since predictions were generated; wired into Team, Captain, and Transfer Studio.

## 2026-09-17 — Task 2.5: NEW badge for players with no PL history
Added `.badge.new` and surfaced it in the Captain shortlist, Transfer Studio rows, and the Player Drawer (plus a caveat note in the drawer). Captain ranking now tie-breaks near-equal scores (within 0.3 pts) in favour of players with prior history. Also replaced two remaining inline-styled eyebrow badges (Chips, Watchlist) with `.badge` color modifiers while in the area.

## 2026-09-17 — Task 15: Dead code cleanup
Removed 12 unused shadcn/ui components (all zero-importer outside their own dead cross-references; only `tooltip.tsx` is actually used, via `layout.tsx`'s `TooltipProvider`), `lib/utils.ts` (zero importers), the now-unused `lucide-react`/`cmdk`/`class-variance-authority` deps, the default create-next-app SVGs in `public/`, and stripped `globals.css` down to the tailwind/tw-animate-css/broadcast.css imports plus the two theme tokens `tooltip.tsx` still reads.

## 2026-09-17 — Task 17.1: Lazy-load images
`PlayerPhoto` and `ClubCrest` now default to `loading="lazy" decoding="async"`; the Captain page's above-the-fold hero portrait opts back in to `loading="eager" fetchPriority="high"`.

## 2026-09-17 — Task 11.2/11.4: Transfer Studio price indicators + market cap
Threaded `cost_change_event` from `players_raw.csv` through `platform_data.py` into `/api/platform`; Transfer Studio rows now show a rising/falling triangle when a player's price moved this event. Raised the incoming-player list cap from 120 to 200.

## 2026-09-17 — Task 12.4: Shareable comparison URL
Comparison page seats now mirror to `?a=<element>&b=<element>` via `useSearchParams`/`router.replace`, wrapped in `React.Suspense` per Next's requirement for `useSearchParams` in a statically-rendered route.

## 2026-09-17 — Task 1.0: olbauday data source integration
Added `--source olbauday` mode to `scripts/fetch_data.py` that downloads from `olbauday/FPL-Core-Insights`, translates to vaastav format, and writes `players_raw.csv` (659 players, all with valid codes/teams/positions), `teams.csv` (20 correct 2026-27 clubs), `fixtures.csv` (380 PL fixtures, GW1-38), and `gws/gw{N}.csv` + `merged_gw.csv` (GW1-4, 2,583 rows) with `kickoff_time`, `fixture`, `opponent_team`, and `was_home` derived from fixture data. Fixed `build_dataset.py` namespace alias bug. Rebuilt `all_seasons_data_final.csv` (256,152 rows) and regenerated `predictions_next_gw.csv` (484 players, all 20 correct 2026-27 teams, mean 1.11 pts GW5).

## Discovered Issues
- Several pages (watchlist, chips, comparison, fixtures, news, team, transfers, plus deadline-clock, toast, club-crest, error-boundary, pitch, squad-editor) still contain non-trivial numbers of inline `style={{ }}` props beyond what's been cleaned up so far — some are legitimately dynamic (widths, gradients, transforms) and allowed per the rules, but a good number are static layout/color choices that should move into broadcast.css. A full pass wasn't done this session (large surface area); flagging so it isn't mistaken for finished.
- `python` on PATH (C:\Python313) does not have lightgbm/xgboost installed; the anaconda3 install at `C:\Users\HP\anaconda3\python.exe` does. Use that interpreter for `predict_gameweek.py` and any other modelling script until the environments are reconciled.

## 2026-09-17 — Task 9: Player drawer enrichment
Added a Forecast section leading with the projection (colour-banded: lime ≥6, cyan ≥4), beside the inputs it is built from — form over the last five gameweeks from the history endpoint, next opponent, venue, and fixture difficulty (green ≤2, pink ≥4) — with a caveat line for players with no prior PL record. Added a CSS sparkline of the last eight gameweeks scaled to the player's own best in the window, hauls in lime and blanks greyed. Added a Transfer momentum section showing net transfers this gameweek. Replaced the duplicated Projection tile in Season numbers with Points/90.

Fixed `player_history()` in `platform_data.py` reading `opponent_team` as an integer id when the olbauday translation and `build_dataset.py` both resolve it to a club name — every 2026-27 fixture in the drawer read "Team 0 (A)". It now accepts either form, for the current and previous season lookups.

## 2026-09-17 — Task 10: Team page + squad identity fix
Squads are now held as element ids rather than names. `/api/squad` returns the prediction export's short name ("Haaland") while the snapshot lists players under a full name ("Erling Haaland"), so the old name join matched 0 of 15 players: squad availability read 0/15, the flagged-players warning never fired, `saveSquadData` persisted an empty id list so squads vanished on reload, and the "My squad" pools on Captain, Comparison, Chips and Transfers were all empty. `squadPlayers` now resolves by element; `squadNames` is derived as `web_name`, which is exactly what the API matches on (verified 483/483). The squad editor keys selection on element too, which also removes a latent duplicate-name bug.

Added remaining budget ("In the bank") to the rail, turning pink when a squad is over 100.0m. Formation display (10.4), squad cost (10.1), auto-pick (10.2) and bench ordering (10.3) were already in place and verified against the running stack.

## 2026-09-17 — Task 13: News page
Added a chance-of-playing badge for the partial cases only — red 25%, orange 50%, yellow 75% — matching the data exactly (3/6/15). 0% is left to the Injured/Unavailable label beside it rather than rendered as "0% fit" on players who have left the club. Added the `n` (not in squad) status label, which previously fell through to the generic one, and made `d` explicit. Replaced the hard cap of 24 wire items with a count and a Show all toggle; a busy week had 228 stories and 204 of them were unreachable. Verified every item opens the player drawer (13.4).

Extended the element-id squad fix to ownership checks on News, Comparison and Transfers — all three compared `squadNames` against `player.name`, the mismatch fixed in Task 10.

## 2026-09-17 — Task 12: Comparison page
Comparison bars now carry a 3px minimum width, so a genuine zero shows as a sliver instead of disappearing (verified: Goals 4 v 0 renders 452px v 3px). Added a width transition so changing a seat animates, disabled under `prefers-reduced-motion`, and moved the bar colours out of inline styles into `.side-a`/`.side-b` classes with an `.is-leader` highlight on the winning side of each category. The picker now opens on the "My squad" pool when a squad exists, applied once so it never resets the user's own choice. "Projected points" was already the first metric (12.3) and the shareable URL was done in 12.4.

## 2026-09-17 — Task 16: Backend hardening
16.1 (join on element) and 16.4 (`prediction_available` / `prediction_timestamp`) were already done; verified. 16.2 verified — every endpoint returns `{ok: false, error}`.

16.3: prediction-dependent endpoints now return **503** rather than 400, via a dedicated `unavailable()` helper — the request is fine, the server has no model output to answer it with. `/api/platform` already degraded correctly (659 players, `predicted_points: null`, `prediction_available: false`).

Two bugs found while testing it. `/api/meta` was gated on predictions although it reports model metadata read from `saved_models/`, so a missing export took down the model footnote on every page; it is now ungated and reports `predictions_available` instead. And `state()` only re-read the file via an `mtime` comparison, which the error path never sets — so once predictions went missing the process stayed broken for its whole life, even after the pipeline it told you to run had produced the file. It now retries whenever the file exists and the last attempt failed. Verified: 503 → 200 in the same process, no restart.
