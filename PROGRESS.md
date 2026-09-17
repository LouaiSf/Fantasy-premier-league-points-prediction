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

## 2026-09-17 — Prediction quality: repaired the live season, split the points model

Traced "the model keeps recommending goalkeepers as captain" to the olbauday
translation layer rather than to the models. `fetch_data.py` mapped a fixed
column list out of each gameweek file and let `build_dataset.py` zero-fill the
rest, so fourteen columns the source does provide were never copied — position,
team, influence/creativity/threat, tackles/recoveries/CBI (and therefore
defensive contribution), transfers in/out, round, both scorelines — and `value`
was copied in millions where every training season is in tenths.

Goalkeeping features were among the few that survived, so keepers kept their
signal while attackers arrived looking like players who had done nothing.
Confirmed by corrupting a clean holdout season the same way: captain picks went
from {FWD 21, MID 10, DEF 6, GK 1} to {FWD 20, GK 14, DEF 4}.

Fixed the mapping, added real fixture difficulty from opponent venue strength,
added a `build_dataset.py` guard that fails when the latest season is blank
somewhere earlier seasons are not, added a two-stage model
(`scripts/train_availability.py`: P(plays) × E[points | plays]), and dropped
goalkeepers from the captain shortlist.

Measured over 76 gameweeks of 2024-25 and 2025-26, captain pick mean return
5.05 → 6.71 points, blanks (≤2 pts) 46.1% → 30.3%, hauls 13.2% → 19.7%.
Two-stage alone is worth R² +0.004/+0.003 and lower MAE in both test seasons.

**Not done:** the direct models were not retrained. They were trained on
2016-17..2023-24, which was never affected, so they are still valid — but
`saved_models/direct/*/features.json` lists 20-26 features that no longer exist
in the current feature build, so a retrain via `train.py` is worth doing before
trusting `train_availability.py`'s reuse of those lists (it currently detects
the staleness and derives the compact set instead).

## 2026-09-17 — Multi-gameweek squad planning

The squad optimiser bought the best fifteen for the next gameweek only. Added
a horizon: `predict_gameweek.py --horizon N` predicts each gameweek in the
window, `optimise.py squad --horizon` buys one squad to hold across all of
them, rechoosing the XI and armband each week.

A future gameweek is predicted by freezing the player — form, price, minutes,
availability all stay as they are today — and moving only the fixture. Only the
`fx_*` family depends on which match is played and nothing about the player
enters it, so it alone is recomputed. `scripts/horizon.py` reproduces the real
pipeline exactly (400/400 values match on the last played gameweek of 2025-26).
Signal retained vs a next-gameweek prediction: 95.9% at k=1, 87.4% at k=5.

Backtest over 28 six-gameweek windows: horizon +17.8 points, better in 19/28
(t=2.20). Overlapping windows, so suggestive rather than settled. `--decay`
defaults to 1.0; discounting later gameweeks measured monotonically worse.

**Also fixed a leak.** `add_fixture_features` keyed its team-match table on
`game_number`, a per-player index, so one row could blend several gameweeks —
Arsenal's 37 matches became 75 rows — and the rolling form attached to a match
could include that match's own scoreline. Team-attack-form correlated with the
current match's goals at r=0.295 vs r=0.133 once keyed on `fixture`. Test R²
falls at every position as a result (GK 0.4586→0.4297, MID 0.3483→0.3383);
that is the leak leaving, not accuracy. Window length was checked as an
alternative explanation and every setting lands within 0.004.

Also: the optimiser could still captain a goalkeeper (only the captain *page*
was fixed before), and `p_plays` ignored published injury news — Maatsen made
an XI at 6.10 points on a 25%-chance ankle injury. Both fixed.

**Not done:** transfers are not modelled across the horizon. The horizon says
which squad is worth holding; getting there from an existing squad is still
the single-gameweek `transfers` subcommand.
