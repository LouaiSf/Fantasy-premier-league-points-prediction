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

### 2026-09-17 — Task 9: Player drawer enrichment
Added a Forecast section leading with the projection (colour-banded: lime ≥6, cyan ≥4), beside the inputs it is built from — form over the last five gameweeks from the history endpoint, next opponent, venue, and fixture difficulty (green ≤2, pink ≥4) — with a caveat line for players with no prior PL record. Added a CSS sparkline of the last eight gameweeks scaled to the player's own best in the window, hauls in lime and blanks greyed. Added a Transfer momentum section showing net transfers this gameweek. Replaced the duplicated Projection tile in Season numbers with Points/90.

Fixed `player_history()` in `platform_data.py` reading `opponent_team` as an integer id when the olbauday translation and `build_dataset.py` both resolve it to a club name — every 2026-27 fixture in the drawer read "Team 0 (A)". It now accepts either form, for the current and previous season lookups.

### 2026-09-17 — Task 10: Team page + squad identity fix
Squads are now held as element ids rather than names. `/api/squad` returns the prediction export's short name ("Haaland") while the snapshot lists players under a full name ("Erling Haaland"), so the old name join matched 0 of 15 players: squad availability read 0/15, the flagged-players warning never fired, `saveSquadData` persisted an empty id list so squads vanished on reload, and the "My squad" pools on Captain, Comparison, Chips and Transfers were all empty. `squadPlayers` now resolves by element; `squadNames` is derived as `web_name`, which is exactly what the API matches on (verified 483/483). The squad editor keys selection on element too, which also removes a latent duplicate-name bug.

Added remaining budget ("In the bank") to the rail, turning pink when a squad is over 100.0m. Formation display (10.4), squad cost (10.1), auto-pick (10.2) and bench ordering (10.3) were already in place and verified against the running stack.

### 2026-09-17 — Task 13: News page
Added a chance-of-playing badge for the partial cases only — red 25%, orange 50%, yellow 75% — matching the data exactly (3/6/15). 0% is left to the Injured/Unavailable label beside it rather than rendered as "0% fit" on players who have left the club. Added the `n` (not in squad) status label, which previously fell through to the generic one, and made `d` explicit. Replaced the hard cap of 24 wire items with a count and a Show all toggle; a busy week had 228 stories and 204 of them were unreachable. Verified every item opens the player drawer (13.4).

Extended the element-id squad fix to ownership checks on News, Comparison and Transfers — all three compared `squadNames` against `player.name`, the mismatch fixed in Task 10.

### 2026-09-17 — Task 12: Comparison page
Comparison bars now carry a 3px minimum width, so a genuine zero shows as a sliver instead of disappearing (verified: Goals 4 v 0 renders 452px v 3px). Added a width transition so changing a seat animates, disabled under `prefers-reduced-motion`, and moved the bar colours out of inline styles into `.side-a`/`.side-b` classes with an `.is-leader` highlight on the winning side of each category. The picker now opens on the "My squad" pool when a squad exists, applied once so it never resets the user's own choice. "Projected points" was already the first metric (12.3) and the shareable URL was done in 12.4.

### 2026-09-17 — Task 16: Backend hardening
16.1 (join on element) and 16.4 (`prediction_available` / `prediction_timestamp`) were already done; verified. 16.2 verified — every endpoint returns `{ok: false, error}`.

16.3: prediction-dependent endpoints now return **503** rather than 400, via a dedicated `unavailable()` helper — the request is fine, the server has no model output to answer it with. `/api/platform` already degraded correctly (659 players, `predicted_points: null`, `prediction_available: false`).

Two bugs found while testing it. `/api/meta` was gated on predictions although it reports model metadata read from `saved_models/`, so a missing export took down the model footnote on every page; it is now ungated and reports `predictions_available` instead. And `state()` only re-read the file via an `mtime` comparison, which the error path never sets — so once predictions went missing the process stayed broken for its whole life, even after the pipeline it told you to run had produced the file. It now retries whenever the file exists and the last attempt failed. Verified: 503 → 200 in the same process, no restart.

### 2026-09-17 — Task 17: Accessibility (17.2–17.5)
Ran a real contrast audit in the browser rather than working from the token values — walked every text node on all eight pages, resolved the effective background, and measured against AA.

The plan's premise was wrong: `--muted-mid` on `--night-900` is **6.08:1** and already passes. The genuine failures were elsewhere. The muted tokens are tuned for the dark pages but reused inside the light `paper-scope` sections, where they fall to 2.91:1 and 1.62:1 — fixed by rebinding them within that scope, so no call site changes. `--pink` reaches only 4.30:1 on dark and 4.12:1 on paper for small text, so each scope now has its own variant (6.16 and 5.50). Two inline `style={{ color: "var(--pink)" }}` eyebrows became `.eyebrow.alert`, which also removes an inline colour the plan disallows.

All flat-background failures are now clear. What remains in the audit is text over club-colour gradients and `rgba(0,0,0,0)` decorative ghost numerals, which the walker cannot resolve a background for.

17.3: global `:focus-visible` outline, purple inside paper sections; verified every element in the tab order shows a ring. 17.4: the existing reduced-motion block already covers the ticker, page entry, transitions and the spinner; verified with an emulated `prefers-reduced-motion`. 17.5: `<main>`, `<nav>` and `<header>` were already present; added `aria-label` to the content `<section>` of all eight pages.

### 2026-09-17 — Task 14: Fixtures page
14.1 and 14.3 verified against the running stack: all 20 clubs, GW5–12 starting from the next unfinished gameweek, FDR colours and H/A indicators correct, and an independent recompute of the easiest-run averages from `fixtures.csv` matches the cards (CRY 2.62, HUL 2.75, EVE/COV 2.88).

14.2: blanks were already handled. Doubles were not — the matrix keyed a `Map` on gameweek, so a second fixture in the same week silently replaced the first and was also dropped from the difficulty average. The current fixture list has none (it is the schedule as first published) but they appear every season once postponements are rearranged. Fixtures are now grouped into arrays: a double renders both opponents with a DGW tag, shaded by the harder leg, and both legs count toward the average. Verified by intercepting `/api/platform` and injecting a synthetic double and blank.

### 2026-09-17 — Task 11: Transfer Studio
11.1 verified end to end against the running stack: staged analysis completes, net is gross minus hit cost, and a freshly auto-picked squad correctly reports "0 transfers lead the model". 11.3: the spinner and status line were already there; wired `.lane.is-live` to the analysing state — broadcast.css has carried that flowing-lime channel animation since the layout landed but nothing ever applied the class.

Found a real problem behind 11.2. Raising the market cap from 120 to 200 did not help, because the list was never sorted — it arrived in `players_raw` order, which is by element id and therefore effectively by club, so the column showed Arsenal, Aston Villa and Bournemouth. **7 of the 10 best players in the game, Haaland included, were unreachable without searching by name.** The market is now ranked by projection.

### 2026-09-17 — Task 2: Player data accuracy
2.1 verified — `latest_local_season()` resolves 2026-27 and the API reports it. 2.4 verified — zero prediction elements fall outside the 2026-27 roster, and neither `/api/platform` nor `/api/players` returns a ghost entry.

2.2: the photo URL pattern is correct but **half the squad has no portrait**. A sampled check of 24 codes returned 403 for 12. The plan's suggested remedy in 2.3 — retry at 110x140 — does not work: where 250x250 is missing, every size is (checked 110x140, 40x40 and 250x250 for six failing codes, all 403). Adding that retry would have doubled the failed requests for half the roster, so it was deliberately not implemented.

2.3: since the fallback is what a lot of the roster actually renders as, it now draws a silhouette behind the initials rather than initials alone. Failed URLs are recorded in a module-level set shared by every instance, not per-component state — the same player appears in the market column, a shortlist and the pitch at once, and each used to re-request a URL already known to be missing. Verified on a full scroll of the Transfer Studio: 13 fallbacks rendered, 78 distinct CDN URLs requested, **0 requested more than once**.

### 2026-09-18 — Tasks 5.2/5.3/8.3/13.1 + platform motion
**5.2 — Captain hero readability:** Added `cap-hero::after` dark gradient overlay (`rgba(26,0,34,.74)→transparent`) behind the text column so copy stays legible against any club colour. Cap-crest and armband-ring CSS were already present; verified sizes correct.

**5.3 — Captaincy battle duel track:** Replaced inline `background:"var(--pl-purple)"` / `background:"var(--pink)"` with `.duel-a` / `.duel-b` CSS classes. Added `is-leader` highlight (brightness + inner glow) on the winning bar. Added `min-width:3px` so genuine zeros render as a sliver. Added `@keyframes duelbarsGrow` (width 0→var(--w)) so both bars animate in on mount, B bar offset by 60ms for a sequential feel.

**8.3 — Nav ink underline on page load:** Removed `transition` from `.nav-ink` default; added it only on `.nav-ink.is-ready`. `main-nav.tsx` adds `is-ready` after the first `requestAnimationFrame` in `useLayoutEffect`, so the ink jumps to the active tab on mount without animating, then slides correctly on every subsequent tab switch.

**13.1 — News status badge colours:** `lead-badges .sev` now takes `data-status` and maps `i`→pink, `s`→orange, `d`→yellow/dark-text, `u`/`n`→muted-mid. Wire-item tagline status spans get `.tagline-status[data-status]` (tinted backgrounds, matching foreground colours). News-card meta spans get `.news-status[data-status]` text colour variants.

**Platform motion:** Added `@keyframes candIn` with `animation-delay:calc(var(--i)*48ms)` so candidate rows stagger in. `@keyframes battleIn` slides the battle section up on appearance (120ms delay). `@keyframes heroFloat` gives the captain hero photo a continuous 5s float. `@keyframes wireIn` staggers news wire items in by index. All suppressed by the existing `prefers-reduced-motion` block.

### 2026-09-18 — Task 18: End-to-end smoke tests
Automated the plan's manual script (Playwright, all 8 pages, three viewports): 21 checks, all passing, 0 console or page errors. Root redirects to /team, 20 crests, season 2026-27, auto-pick fills the pitch with 11 markers carrying projections and a captain badge, every page renders, no emoji, no plain-text loading states, no horizontal overflow at 1440/768/375.

It found three real defects, all now fixed:

1. **A crash I had introduced in Task 9.** `/api/squad` answers with a trimmed player shape carrying no `transfers_in_event`, so clicking a pitch marker threw on `toLocaleString`. The drawer now resolves the snapshot's full record by element and falls back to whatever it was handed — which also fills in the minutes, ICT and expected-goals the trimmed shape was missing.
2. **Watchlist overflowed the viewport** by 57px at 1440 and 61px at 375. Two separate causes: `.sub-head` was a nowrap flex row inside a 432px column, and the section grid used `minmax(420px, 1fr)` — a floor the track cannot go below, so at 375px it stayed 420px wide. Now `minmax(min(420px,100%),1fr)` with `min-width:0` on the items. The inline layout styles moved into broadcast.css in the process, per the plan's own rule.
3. A test-side false positive: markers use `.pm-pred`, not `.pm-pts`.

### 2026-09-18 — Release cleanup, housekeeping, data backup

**Commit and push:** Staged the 2026-09-18 grand-plan changes that had never been committed (broadcast.css, captain, news, main-nav, calibration files, PROGRESS.md). Rebased on a remote commit ("Separate the transfer optimum from what it is worth acting on") and pushed.

**Branch cleanup:** Deleted 22 stale remote branches from `origin` (abdou, defcon, singleNotebook×3, tomerge, training, and 15 others from the original group project). `main` is now the only branch.

**GitHub description/topics:** `YahiaKerroum` lacks admin access on `LouaiSf`'s repo so `gh repo edit` returns 404. Needs manual action: Settings → About on the repo page. Suggested description and topics in the corresponding PROGRESS entry.

**Hurdle output in optimise.py:** Verified as already complete. `predictions_next_gw.csv` carries `predicted_points = p_plays × predicted_points_if_plays`; `optimise.py` reads `predicted_points`. No code change needed.

**FBref defensive backup:** Extracted the 5 defensive columns + join keys (`season`, `element`, `fixture`) from `all_seasons_data_final.csv` into `data/fbref_defensive.csv` (7.7 MB, 246,978 rows with `has_fbref_defensive=1`). Added `!data/fbref_defensive.csv` exception to `.gitignore`. This is the committed backup of data that cannot be re-scraped without ~380 requests per season.

**LICENSE:** Added MIT licence. First copyright line: "2017-2019 Vaastav Anand" (upstream data); second: "2024-2026 Yahia Kerroum" (this work). Notice note at the bottom explains data/code split.

**README fixes:** Removed the duplicated scripts-table block (predict_gameweek / optimise / validate_selection appeared twice). Removed the contradictory Layout paragraph that described the deleted exploratory notebooks as still present after saying they had been removed.

**model_metrics.json:** Removed empty `"pca": {}` key left from the dropped PCA branch.

**`.gitignore` decision:** `*.prev` and `*.zip` are already gitignored and should stay that way — both are large regenerable artifacts.

### 2026-09-18 — Task 19: Inline style cleanup (complete)

Removed all static inline `style={{ }}` blocks from the frontend, replacing each with a named CSS class in `broadcast.css`. Files changed:

- **broadcast.css:** Added ~55 new utility classes and appended 3 more this pass (`.watchlist-page .search`, `.kicker.muted`, `.chip-advisor-heatmap .trend`). Also fixed two existing rules (`.watch-grid` `margin-top`, `.teamsheet` `flex`).
- **app/transfers/page.tsx:** Removed 3 redundant inline styles (`.shot` position, `.desk.out`/`.desk.in` CSS custom properties already in CSS).
- **app/watchlist/page.tsx:** Replaced all 26 inline styles with classes (`shell--padded`, `section-head--mt`, `section-head-actions`, `kicker kicker-row`, `ctrl-select`, `watch-name-row`, `watch-ownership`, `watch-pts-row`, `watch-pts-unit`, `watch-price-row`, `watch-section-desc`, `data-section` attributes on watch sections).
- **app/chips/page.tsx:** Replaced ~18 inline styles (`shell--padded`, `section-head--mt`, `section-head-actions`, `kicker kicker-row`, `ctrl-select`, `chip-heatmap-section`, `chip-heatmap-scroll`, `col-gw`, removed inherited `fontFamily` from table cells, `chip-note-banner-icon/body/title`).
- **app/comparison/page.tsx:** `.eyebrow.cyan` replaces inline colour.
- **app/fixtures/page.tsx:** `.eyebrow.lime` replaces inline colour.
- **app/news/page.tsx:** `.kicker.muted`, `.lead-note`, `.wire-fresh` colour, `.wire-layout--single`, stripped static props from `.wire-item` button (kept dynamic `--i`).
- **app/team/page.tsx:** `shell--lg`, `.eyebrow.muted` ×3, `btn w-full`, `squad-alerts-list`, `squad-alerts-row`.
- **components/error-boundary.tsx:** `page--centered`, `error-card`, `eyebrow.alert`.
- **components/chrome/toast.tsx:** `toast-dismiss`.
- **components/team/pitch.tsx:** `formation--empty`.
- **components/team/squad-editor.tsx:** `picker-dialog`, `scrim.squad-scrim`, `dialog-actions`, removed `teamsheet` flex (in CSS).
- **components/club-crest.tsx:** Stripped 9 static props from crest-fallback; kept only `width`, `height`, `background` inline.
