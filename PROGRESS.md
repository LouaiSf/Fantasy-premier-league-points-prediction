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

## Discovered Issues
- Several pages (watchlist, chips, comparison, fixtures, news, team, transfers, plus deadline-clock, toast, club-crest, error-boundary, pitch, squad-editor) still contain non-trivial numbers of inline `style={{ }}` props beyond what's been cleaned up so far — some are legitimately dynamic (widths, gradients, transforms) and allowed per the rules, but a good number are static layout/color choices that should move into broadcast.css. A full pass wasn't done this session (large surface area); flagging so it isn't mistaken for finished.
- `python` on PATH (C:\Python313) does not have lightgbm/xgboost installed; the anaconda3 install at `C:\Users\HP\anaconda3\python.exe` does. Use that interpreter for `predict_gameweek.py` and any other modelling script until the environments are reconciled.
