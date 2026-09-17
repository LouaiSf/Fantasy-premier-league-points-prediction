# Project status

_Last updated: 2026-09-17._

A running record of what has been built, what the numbers currently are, and
what is still open. `README.md` documents the finished pipeline; this file
tracks the work around it.

---

## Where the work lives

| branch | state |
|---|---|
| `pipeline-for-public` (local) | where the work is committed |
| `public/fix/training-pipeline` | identical to the above, always pushed first |
| `public/main` | **has the work**, merged via PRs #22, #23 and #24 |
| `main` (local) | the inherited baseline, one commit — not the project |

Two things to be aware of before picking this up again:

1. The working tree is currently checked out on local `main`, which is the
   **inherited baseline** — old notebooks, no `scripts/`, no `webapp/`, and
   only the 2018-19 season. `git switch pipeline-for-public` first.
   (`data/2024-25/`, `data/2025-26/`, `data/2026-27/` and `fpl_colab.zip` sit
   untracked in the folder and need stashing, since the branch tracks those
   paths.) Committing while on `main` also uses the *inherited* `.gitignore`,
   which lacks the `*.zip`, `*.prev` and `*.bak` rules — a `git add .` there
   once swept a 25 MB Colab bundle into a commit.
2. A bare `git push` targets `origin` (`mohameddddt/…`), a private repo the
   branch was published to by mistake early on. The public repo is the remote
   named `public`: `git push public HEAD:fix/training-pipeline`.

---

## Done

### Phase 1 — Correctness (2026-09-03 to 09-04)

- [x] Repaired `2024-25/merged_gw.csv`, recovering **13,105 dropped rows**
- [x] Replaced the random `train_test_split` with a **season-level holdout**
      (train up to 2022-23, validate 2023-24, test 2024-25 + 2025-26)
- [x] Moved every transform — scalers, encoders, hyperparameter search — inside
      the training fold, so nothing leaks from test into train
- [x] Fixed the silent feature-count collapse that had been training every
      model on a single column (price) and reporting it as a working model
- [x] Fixed an index misalignment that silently rewrote the target
- [x] Added a coverage guard that raises rather than training on whatever
      columns happen to be present

### Phase 2 — Making it runnable (2026-09-04)

- [x] `FPL_Colab.ipynb` + `scripts/make_colab_bundle.py` — full pipeline on
      Colab free tier from a 24 MB zip (122 files, not 17,000). No GPU needed;
      none of these models use one
- [x] `run()` helper that halts Run-all on a failed stage and streams the real
      error text, instead of cascading into a confusing `FileNotFoundError`
- [x] Standardised CSV encoding across the pipeline (utf-8 write, tolerant read)
- [x] Made the dataset rebuild **idempotent** — `has_fbref_defensive` is
      carried forward so written-out zeros are not mistaken for real data
- [x] `--allow-missing-defensive` now refuses by default, after a mid-run
      failure once produced a dataset with zero defensive stats, silently

### Phase 3 — Measurement (2026-09-04 to 09-05)

- [x] `scripts/baselines.py` — heuristics scored on the identical test rows
- [x] Established that **FPL's own `xP` is not a usable benchmark**: captured
      at or after lineup announcement for 2023-24/2024-25, and simply broken
      for 2025-26 (negative R²). Flagged per season as `UNFAIR` / `BROKEN`
- [x] `scripts/ablate.py` — marginal R² *and* standalone R² per feature family
- [x] Re-centred the hyperparameter grids three times; concluded tuning is
      finished (moved test R² by less than 0.005). The ceiling is the features
- [x] Cut **220 features to 54**, chosen by searching five candidate sets

### Phase 4 — Availability and data (2026-09-04)

- [x] 16 availability features — played/started rates over 3/5/10, minutes
      volatility, blank and start streaks, role flags. Built from `minutes`
      rather than `starts`, which does not exist before 2023-24
- [x] Dropped the PCA branch (measured: no benefit, real complexity cost)
- [x] Added the 2025-26 and 2026-27 seasons; `build_dataset.py` picks up new
      season folders automatically

### Phase 5 — The decision layer (2026-09-06)

- [x] `scripts/predict_gameweek.py` — pulls the live FPL bootstrap, appends
      placeholder rows for the upcoming fixture, reruns the **real** feature
      functions, and ranks every player. Refuses below 80% coverage
- [x] `scripts/validate_selection.py` — judges the model by the team it picks,
      not by R²
- [x] `scripts/optimise.py` — squad, transfers, chip timing, watchlist. Each
      answer is one integer program under the real FPL constraints (2/5/5/3,
      £100m, max 3 per club, legal formation), so it is optimal rather than
      greedy
- [x] `webapp/` — Flask UI over the same `optimise.py`, no reimplementation,
      so the browser and the CLI cannot disagree
- [x] Rebuilt the UI around a real player browser: pick from a list with price,
      stats, team and country, instead of typing names

### Phase 6 — Consolidation (2026-09-06)

- [x] Whole pipeline in one notebook, `fpl_pipeline.ipynb` (77 cells, 6 stages).
      `scripts/nbrun.py` executes ranges of its cells by text anchor, so the
      scripts cannot drift from the notebook
- [x] Deleted the five superseded exploratory notebooks and every unused asset
- [x] Rewrote the inherited cells and markdown — the notebook now explains
      *why*, not just what
- [x] Four measured improvements, two of them negative results (below)
- [x] Two-stage `HurdleModel` — P(plays) × E[points | plays] — plus a P(haul)
      classifier
- [x] `scripts/test_notebook_fixes.py` — 25 regression tests over the split,
      the coverage guard, the availability features and the defensive join

### Phase 7 — Documentation (2026-09-06 to 09-11)

- [x] `README.md` with the measured results
- [x] CV bullet points updated to the final numbers
- [x] Commits re-authored to the real GitHub identity
- [x] **Website requirements document** —
      <https://claude.ai/code/artifact/3db42394-c47f-4d4b-92f7-b7bec905b63f>
      (4 built pages, 2 to build, 7 proposed, 8 cross-cutting requirements)

---

## Current numbers

Test fold is 2024-25 + 2025-26, **50,048 player-matches**, held out entirely.

| position | best model | features | test R² | test MAE | vs. `rolling_5` |
|---|---|---|---|---|---|
| GK  | ElasticNet | 66 | 0.430 | 0.668 | **+0.108** |
| DEF | LightGBM | 74 | 0.283 | 1.135 | **+0.131** |
| MID | LightGBM | 74 | 0.338 | 0.982 | **+0.115** |
| FWD | ElasticNet | 74 | 0.336 | 1.113 | **+0.111** |

Run-to-run variation from the boosters is around ±0.005; treat smaller gaps as
noise.

> **These are lower than the figures this table carried before 2026-09-17, and
> the earlier ones were wrong.** `add_fixture_features` keyed its team-match
> table on `game_number`, a per-player index, which let the rolling team form
> attached to a match include that match's own scoreline. Re-keyed on
> `fixture`, R² falls at every position — that is the leak leaving rather than
> accuracy being lost, since the leaked feature cannot exist at prediction
> time. See "Key team form on the fixture id" below.

**Selection backtest** — the same integer program per gameweek, all 33
gameweeks of 2025-26, £83m budget:

| strategy | total | per GW |
|---|---|---|
| model predictions | 3380 | 51.2 |
| `rolling_5` average | 2873 | 43.5 |
| perfect foresight | 8873 | 134.4 |

**+507 points**, better in 51 of 66 gameweeks (77%), paired t = 4.34. That
captures **8.5%** of the gap between the heuristic and perfect foresight.

Now run over both holdout seasons rather than 2025-26 alone. On 2025-26 by
itself the model scores 50.5 per gameweek against the heuristic's 41.7 — an
edge of +8.7, where this section previously claimed +14.6. The baseline and
the foresight ceiling are unchanged; the whole of the difference is the
fixture-feature leak coming out of the model.

**Classifiers** (trained, not yet surfaced anywhere): P(plays) **0.954 AUC**,
P(haul at least 10) **0.869 AUC**.

### Negative results, kept on the record

| change | marginal R² | verdict |
|---|---|---|
| expected goals (`xg_*`, 26 features) | **−0.0000** | 0.282 alone, but fully redundant with rolling `total_points` / `bps` / `ict_index` |
| P(haul) for captaincy | — | 0.869 AUC, but does not beat expected points at picking a captain |
| FBref defensive features | −0.0001 | a 757-line name matcher plus ~380 requests per season, worth nothing as features |
| old `opponent_*` family | +0.0012 | scored −0.009 *alone*; replaced by `fx_*` |

The one that worked: the **fixture rebuild** (`fx_*`), +0.0045 marginal,
+0.009 to +0.027 R² once in the compact set, and +285 selection points.

FBref *data* stays regardless — `defensive_contribution` decides a +2 bonus on
10,604 rows, so it is part of the target. Only the derived columns were dropped.

---

## Upcoming

### 1. Release

- [x] Merged into `public/main` — PRs #22 and #23 carried the pipeline, the
      progress doc and the data removal; #24 the requirements doc and 2026-27
- [ ] `git switch pipeline-for-public` (the working tree is on the baseline)
- [ ] Delete the stale remote branches on `public/` now that main has the work
      (about 20 remain from the original group project)
- [ ] Add a repository description and topics on GitHub; consider GitHub Pages
      off `docs/` so `website_requirements.html` renders instead of showing
      source

### 2. Website — from the requirements document

Ordered by value for effort. The first two are the pages that were asked for;
the third and fourth are the cheapest way to show more of what the model does,
because both models already exist and only need wiring.

- [ ] **News page** (`NW-1..6`) — `bootstrap-static` carries a `news` field
      with return notes and playing percentages; **180 of 655 players** have
      one right now. This covers the model's biggest blind spot: it has no
      team-news feature and will happily rate a player who is out for months
- [ ] **My Team page** (`MT-1..7`) — import by FPL manager ID rather than
      typing 15 names. `/api/entry/{id}/event/{gw}/picks/` returns the real
      fifteen, captain, vice and bench order. Verified working
- [ ] **Captain picker** — surfaces P(haul), which is trained and shown nowhere
- [ ] **"Will they play?"** — surfaces P(plays) at 0.954 AUC, the single most
      accurate output this project produces
- [ ] Fixture ticker — fixture data is already loaded for the Chips tab
- [ ] "How it works" model card — probably the most important page for anyone
      assessing this project
- [ ] Price watch, gameweek review, wildcard planner
- [ ] Cross-cutting requirements `NF-1..8`, led by **NF-1: never show a
      prediction as a fact**, when measured error is around ±1.0 points

### 3. Model

- [ ] Add a team-news / injury feature. Everything measured so far says this is
      fundamentally a model of *whether a player will be on the pitch* — and
      the one source that knows that is the `news` field, which is unused
- [ ] Feed the two-stage output into `optimise.py`. Selection currently uses
      the direct regressor; the hurdle model's split of P(plays) from
      E[points | plays] is exactly the distinction a captain or bench decision
      needs
- [ ] Re-run the selection backtest on 2026-27 once about GW6 exists, as an
      out-of-sample check on a season that postdates every design decision

### 4. Data

- [ ] **2026-27 contributes nothing yet** — GW1 is now committed (all that
      exists upstream as of 2026-09-11), but rolling features need five
      matches, so every row is still dropped. It starts counting around GW6.
      Re-run `fetch_data.py` as gameweeks land; no code change needed
- [ ] The FBref merge covers 2024-25 only through GW21; later rows carry
      `has_fbref_defensive=0` and honest zeros. Extend it or retire it
- [ ] **`all_seasons_data_final.csv` is load-bearing and has no backup.** It is
      the only surviving copy of the FBref defensive merge — `defensive_stats_raw.csv`
      is gitignored and the scraping notebook was deleted, so `build_dataset.py`
      lifts the defensive columns straight back out of this file. Re-scraping
      costs ~380 requests per season. Never delete it; consider committing the
      defensive columns on their own as a smaller, clearer artifact

### 5. Housekeeping

- [x] Removed the 2,944 `data/*/understat/` files (38.8 MB) — grepped the whole
      codebase, nothing reads them — and the regenerable `all_seasons_data.csv`
      (41.9 MB). Tip went from 4,135 files / 220 MB to 1,190 / 139 MB
- [ ] Add a `LICENSE`, and an MIT notice for the redistributed data. Upstream
      (`vaastav/Fantasy-Premier-League`) is MIT, © 2017-19 Vaastav Anand, which
      requires the notice to travel with the data. There is currently no
      licence file of any kind
- [ ] `README.md` has a **duplicated block**: the scripts table lists
      `predict_gameweek.py`, `optimise.py` and `validate_selection.py` twice,
      and the Layout section says the old notebooks "have been removed" and
      then describes them as if they are still present. Contradictory — fix
- [ ] `model_metrics.json` still carries an empty `"pca": {}` key from the
      dropped branch
- [ ] Decide whether `.prev` dataset snapshots and `fpl_colab.zip` belong in
      `.gitignore`

---

## Open questions

These came out of the requirements document and cannot be answered without a
decision:

1. **Is the website deployed, or local only?** This changes the caching and
   FPL API rate-limit answers substantially, and whether importing a manager
   ID needs any privacy handling
2. How often should predictions refresh — once per deadline, or on demand?
3. Is the audience a marker/interviewer, or real FPL managers? A model card
   matters enormously to the first and not at all to the second
4. Does 2026-27 get backfilled weekly, or is the project frozen at 2025-26?

---

## Web platform and model work (branches `web-platform`, `model-improvements`)

Dated entries carried over from those branches. The sections above describe the
pipeline as it stood on 2026-09-11; everything below happened after that and is
appended in chronological order rather than folded in, so the earlier record
stays readable as written.

### 2026-09-17 — Task 1.3: Model path fallback
Added fallback from `saved_models/direct/meta.json` to `fpl_results/saved_models/direct/meta.json` in `model_summary()`.

### 2026-09-17 — Task 1.4: Prediction merge on element ID
Changed `/api/platform` enrichment join from player name to `element` (FPL integer ID) to prevent mis-matches and ghost entries.

### 2026-09-17 — Task 3: Chips page broadcast rewrite
Rewrote `app/chips/page.tsx` using broadcast design system — replaced all inline styles and emoji icons with CSS classes, added `chip-advisor-*` and `chip-conf` classes to broadcast.css, replaced emoji with styled letter-circle icons (TC/BB/FH/WC).

### 2026-09-17 — Task 4: Watchlist page broadcast rewrite
Rewrote `app/watchlist/page.tsx` using broadcast design system — removed all inline styles and `onMouseEnter`/`onMouseLeave` handlers, added `watch-*` CSS classes to broadcast.css with CSS `:hover` effects, responsive breakpoints at 860px/560px.

### 2026-09-17 — Task 5: Captain badge (pm-badge verified)
Confirmed `.pm-badge` class in broadcast.css and usage in `player-marker.tsx` are correctly aligned with the gold circle spec.

### 2026-09-17 — Task 6: Loading and empty state components
Created `components/loading.tsx` and `components/empty-state.tsx` with broadcast spinner and styling. Added `.loading-state`, `.loading-spinner`, `.loading-label`, `.empty-state`, `.empty-title`, `.empty-message` to broadcast.css. Updated all 8 page routes and player-drawer to use `<Loading />` component.

### 2026-09-17 — Task 7: Error boundary fix
Fixed `error-boundary.tsx` — removed non-existent `panel card-tint` and `btn-primary` CSS classes, changed `--muted-foreground` to `--muted-mid`, using `.btn` directly.

### 2026-09-17 — CSS additions: blade vars + badge
Added `--blade` and `--blade-sm` CSS variables to `:root` in broadcast.css. Added `.badge` utility class for page header eyebrow labels.

### 2026-09-17 — Task 1.1/1.2: Regenerate predictions for 2026-27
`predictions_next_gw.csv` was still stale (Burnley/West Ham/Wolves, missing Coventry/Hull/Ipswich) despite earlier Phase 1 commits. Re-ran `predict_gameweek.py --season 2026-27 --no-api` via the anaconda3 Python environment (the default `python` on PATH lacks lightgbm). All 616 2026-27 players now resolve with 0 id mismatches against `players_raw.csv`, all 20 correct teams present. File is gitignored (all `*.csv` are), so nothing to commit for it directly — anyone continuing this work must regenerate it locally the same way if it goes stale again.

### 2026-09-17 — Task 8: Nav responsive + crest ticker accessibility
`.nav-actions` (refresh button, deadline clock) was `display:none` below 1080px, hiding functionality on tablets. Now shrinks instead: refresh becomes icon-only, deadline clock drops its context label. Crest ticker crests were `<button>` elements with no `onClick`, an unlabeled non-functional control for screen readers — changed to `<span role="img" aria-label="{team} crest">`.

### 2026-09-17 — Task 1.5: Model info footnote
Added `prediction_timestamp` to `/api/platform`. New `ModelInfo` component shows model name, test R², and time since predictions were generated; wired into Team, Captain, and Transfer Studio.

### 2026-09-17 — Task 2.5: NEW badge for players with no PL history
Added `.badge.new` and surfaced it in the Captain shortlist, Transfer Studio rows, and the Player Drawer (plus a caveat note in the drawer). Captain ranking now tie-breaks near-equal scores (within 0.3 pts) in favour of players with prior history. Also replaced two remaining inline-styled eyebrow badges (Chips, Watchlist) with `.badge` color modifiers while in the area.

### 2026-09-17 — Task 15: Dead code cleanup
Removed 12 unused shadcn/ui components (all zero-importer outside their own dead cross-references; only `tooltip.tsx` is actually used, via `layout.tsx`'s `TooltipProvider`), `lib/utils.ts` (zero importers), the now-unused `lucide-react`/`cmdk`/`class-variance-authority` deps, the default create-next-app SVGs in `public/`, and stripped `globals.css` down to the tailwind/tw-animate-css/broadcast.css imports plus the two theme tokens `tooltip.tsx` still reads.

### 2026-09-17 — Task 17.1: Lazy-load images
`PlayerPhoto` and `ClubCrest` now default to `loading="lazy" decoding="async"`; the Captain page's above-the-fold hero portrait opts back in to `loading="eager" fetchPriority="high"`.

### 2026-09-17 — Task 11.2/11.4: Transfer Studio price indicators + market cap
Threaded `cost_change_event` from `players_raw.csv` through `platform_data.py` into `/api/platform`; Transfer Studio rows now show a rising/falling triangle when a player's price moved this event. Raised the incoming-player list cap from 120 to 200.

### 2026-09-17 — Task 12.4: Shareable comparison URL
Comparison page seats now mirror to `?a=<element>&b=<element>` via `useSearchParams`/`router.replace`, wrapped in `React.Suspense` per Next's requirement for `useSearchParams` in a statically-rendered route.

### 2026-09-17 — Task 1.0: olbauday data source integration
Added `--source olbauday` mode to `scripts/fetch_data.py` that downloads from `olbauday/FPL-Core-Insights`, translates to vaastav format, and writes `players_raw.csv` (659 players, all with valid codes/teams/positions), `teams.csv` (20 correct 2026-27 clubs), `fixtures.csv` (380 PL fixtures, GW1-38), and `gws/gw{N}.csv` + `merged_gw.csv` (GW1-4, 2,583 rows) with `kickoff_time`, `fixture`, `opponent_team`, and `was_home` derived from fixture data. Fixed `build_dataset.py` namespace alias bug. Rebuilt `all_seasons_data_final.csv` (256,152 rows) and regenerated `predictions_next_gw.csv` (484 players, all 20 correct 2026-27 teams, mean 1.11 pts GW5).

### Discovered Issues
- Several pages (watchlist, chips, comparison, fixtures, news, team, transfers, plus deadline-clock, toast, club-crest, error-boundary, pitch, squad-editor) still contain non-trivial numbers of inline `style={{ }}` props beyond what's been cleaned up so far — some are legitimately dynamic (widths, gradients, transforms) and allowed per the rules, but a good number are static layout/color choices that should move into broadcast.css. A full pass wasn't done this session (large surface area); flagging so it isn't mistaken for finished.
- `python` on PATH (C:\Python313) does not have lightgbm/xgboost installed; the anaconda3 install at `C:\Users\HP\anaconda3\python.exe` does. Use that interpreter for `predict_gameweek.py` and any other modelling script until the environments are reconciled.

### 2026-09-17 — Prediction quality: repaired the live season, split the points model

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

### 2026-09-17 — Multi-gameweek squad planning

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
