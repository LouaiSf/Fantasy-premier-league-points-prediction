# Project history

_Last updated: 2026-11-22._

The single record of what has been built, the decisions behind it, and what is
still open. It replaces the per-session plan, prompt, progress and handoff files
that used to sit at the repository root (`GRAND_PLAN.md`, `PROGRESS.md`,
`PLATFORM_PROGRESS.md`, `PLATFORM_V2_*`, `PLATFORM_V3_*`,
`FPL_MANAGER_PLANNER_CHIPS_*`, `FPL_PLATFORM_FIX_*`, `COMPREHENSIVE_FIX_PLAN.md`,
`CONTINUE_*`, `IMPLEMENTATION_PROMPT.md`). Those are still in git history
(`git log --all -- PROGRESS.md`) if the full session-by-session detail is ever
needed.

`README.md` documents how to run the pipeline, the API and the site. This file
documents how they came to be.

---

## Contents

1. [Timeline](#timeline)
2. [Current numbers](#current-numbers)
3. [Decisions and negative results](#decisions-and-negative-results)
4. [Data notes](#data-notes)
5. [Working environment](#working-environment)
6. [Open items](#open-items)

---

## Timeline

### Dec 2025 – Feb 2026 — The original group project

Notebooks, per-season data from `vaastav/Fantasy-Premier-League`, an FBref
scraper for defensive contributions, a `game_number` attribute, position-based
models, and a first save-and-predict workflow. Merged through PRs #1–#20.

### 2026-09-03 → 09-11 — Making the model honest (PRs #22, #23)

**Correctness**
- Repaired `2024-25/merged_gw.csv`, recovering 13,105 dropped rows.
- Replaced the random `train_test_split` with a season-level holdout: train up
  to 2022-23, validate 2023-24, test 2024-25 + 2025-26.
- Moved every transform (scalers, encoders, hyperparameter search) inside the
  training fold.
- Fixed a silent feature-count collapse that had trained every model on one
  column (price), and an index misalignment that rewrote the target.
- Added a coverage guard that refuses to train on whatever columns happen to
  be present.

**Runnable pipeline**
- `FPL_Colab.ipynb` + `scripts/make_colab_bundle.py`: the full pipeline on the
  Colab free tier from one zip. A `run()` helper halts Run-all on a failed stage.
- Consistent CSV encoding, and an idempotent dataset rebuild
  (`has_fbref_defensive` is carried forward).

**Measurement**
- `scripts/baselines.py` scores heuristics on the identical test rows. FPL's
  own `xP` turned out not to be a fair benchmark: it was captured at or after
  lineup announcement for 2023-25, and broken (negative R²) for 2025-26.
- `scripts/ablate.py`: marginal and standalone R² per feature family. Tuning
  moved test R² by under 0.005, so the ceiling is the features. 220 features
  were cut to 54.
- 16 availability features (played/started rates, minutes volatility, streaks,
  role flags). The PCA branch was dropped because it made no measured difference.

**Decision layer**
- `scripts/predict_gameweek.py`: pulls the live FPL bootstrap, appends rows for
  the upcoming fixture, reruns the real feature functions, ranks every player.
- `scripts/validate_selection.py`: judges the model by the team it picks.
- `scripts/optimise.py`: squad, transfers, chips, watchlist. Each answer is an
  integer program under the real FPL rules (2/5/5/3, £100m, 3 per club, legal
  formation).
- The whole pipeline consolidated into `fpl_pipeline.ipynb`. `scripts/nbrun.py`
  executes its cells by text anchor so the scripts cannot drift from it.
- Website requirements document: `docs/website_requirements.html`.

### 2026-09-13 → 09-18 — The web platform, v1 and v2

- v1 (Flask + Jinja + vanilla JS) was built, reviewed, and replaced the same
  week by a **Next.js 16 / React 19 frontend** in `webapp/frontend/` over the
  Flask API in `webapp/app.py`. The prototype's CSS
  (`docs/fpl-assistant-prototype.html`, spec in `docs/DESIGN.md`) was ported
  verbatim into `broadcast.css`. Base UI supplies only the accessible primitives
  (dialog, tooltip).
- **Data-fidelity rule, kept ever since:** much of the prototype is seeded demo
  data (ranks, set-piece lists, analyst essays, "since your last visit" feeds).
  The app matches its visual system, but every number comes from real data. A
  widget with no real source is left out.
- Surfaces: My Team, Transfer Studio, Comparison, Captain & Form, News Wire,
  Watchlist & Differentials, Chip Advisor, Fixture Matrix.
- Grand-plan tasks 1–19 (all done): predictions joined on element id, not name;
  squads held as element ids (the name join had matched 0 of 15); chips and
  watchlist rewritten in the design system; loading/empty states; error
  boundary; responsive nav; player drawer with forecast, sparkline and transfer
  momentum; ranked transfer market (7 of the top 10 players were unreachable
  before); comparison bars and shareable URLs; news badges and "show all"
  (204 of 228 stories had been unreachable); double gameweeks in the fixture
  matrix; 503 for prediction-dependent endpoints; a measured AA contrast audit;
  lazy images; Playwright smoke tests over 8 pages × 3 viewports; every static
  inline style moved to CSS.
- Photo fallback: about half the roster has no CDN portrait at any size, so
  retrying other sizes was deliberately not implemented. Failed URLs are
  remembered across instances.
- Housekeeping: MIT `LICENSE` (with the upstream data notice), README dedup,
  `data/fbref_defensive.csv` committed as the backup of the un-rescrapable
  FBref merge, 22 stale remote branches deleted.

### 2026-09-17 → 09-18 — Prediction quality

- **The "goalkeeper captain" bug** was in the olbauday translation layer, not in
  the models: fourteen columns were never copied and `value` was in millions
  instead of tenths, so attackers looked like players who had done nothing.
  The mapping was fixed and `build_dataset.py` now fails when the latest season
  is blank where earlier seasons are not.
- **Two-stage model** (`scripts/train_availability.py`): P(plays) ×
  E[points | plays]. Captain mean return went from 5.05 to 6.71 points, and
  blanks from 46.1% to 30.3%.
- **Fixture-feature leak fixed:** team form was keyed on `game_number` (a
  per-player index), so a match's rolling form could include its own
  scoreline. Re-keyed on `fixture`. Test R² fell at every position, which is
  the leak leaving.
- Availability gated on published team news, and a multi-gameweek horizon
  (`--horizon N`) for squad selection: the player is frozen and only the
  fixture moves. 95.9% of the signal is retained at k=1 and 87.4% at k=5.
- Per-position calibration (`scripts/calibrate.py`). Transfer advice separates
  the optimum from what is worth acting on. Seeds let different users get
  different, equally good teams.

### 2026-09-21 → 09-24 — Deployment, manager planner, platform repair, v2

- **Deployment:** Render blueprint for the API (`render.yaml`), Vercel for the
  frontend (`NEXT_PUBLIC_API_BASE`). Production CORS fails closed, there is a
  bearer token plus rate limit and cooldown on the refresh endpoints, every
  route's input is validated through `webapp/contracts.py`, and structured
  logs, metrics, alerts and readiness checks live in `webapp/observability.py`.
- **Reproducible artifact:** `scripts/artifacts.py` writes or verifies a
  manifest for the predictions CSV (sha256, git commit, model-bundle
  fingerprint). In production, readiness fails unless the manifest verifies.
- **Safe refresh:** `scripts/refresh_pipeline.py` fetches, rebuilds history if
  it lags, predicts into a temporary file, validates, then atomically replaces
  the CSV. It runs under a lock.
- **Manager planner** (6 phases): public FPL manager lookup by id or profile
  URL, lineup preview and explicit import, a combined transfer and lineup
  planner, horizon projections in the Chip Advisor, and auditable chip
  evidence. FPL has no public global name search, so name search is bounded to
  a known league (up to 5 standings pages per request).
- **Platform repair** (phases 0–4): a browser-side check of the `/api/chips`
  contract, one finance model for owned squads, an optimiser that spends sale
  proceeds rather than market value, an exact transfer-plan layout, and
  honest advisor and transfer state.
- **v2 slices:** multi-transfer drafts in Transfer Studio (locked out/in
  pairs, evaluate, save, hold, review then apply); Chip Advisor contract v3
  with per-gameweek eligibility across the GW19/20 split; goalkeeper
  captaincy allowed (the official rules permit it); a deadline decision board
  on My Team; up to three saved transfer scenarios, flagged stale when the
  squad or snapshot changes.

### 2026-09-27 → 09-30 — v3: visual foundations and the chip rebuild

- **V0:** self-hosted variable fonts (Fontsource), an 11px type floor, a motion
  system (stagger, count-up, FLIP reorder, drawer and toast transitions),
  page-shaped skeleton loaders, and an inline-SVG chart kit (Sparkline,
  BarStrip, DeltaBar, Scatter).
- **Slice A, Chip Advisor contract v4** (`scripts/chip_engine.py`,
  `scripts/chip_policy.py`):
  - Chips, free transfers and bank sync from the manager's FPL history.
  - A per-week projection matrix for the actual squad.
  - Every chip's gain is measured in points against the best no-chip play that
    week:
    - TC: the best captain's points.
    - BB: bench points net of expected autosubs.
    - FH: an unrestricted squad against `max_changes = FT`.
    - WC: a 6-week horizon, unlimited against FT+5.
  - One joint plan through GW38, with no two chips in the same week.
  - A reduced market and threaded CBC solves cut a cold run from 55 s to about
    8 s.
- `pulp` pinned below 4.0, because 4.0 removed direct `LpVariable` construction.

### 2026-10-18 → 10-22 — FotMob, data audit, Stats Lab, ownership, Slice D

- The pipeline holds back unplayed matches and rebuilds history when a
  gameweek fills in. Availability models are refit on every season.
- **FotMob scraper** (`scripts/fetch_fotmob.py`): only robots-compliant public
  pages, at least 3 s between requests, and a cache that never refetches
  finished matches. 52 stat columns plus shot data per player per match.
  Backfilled 2019-20 → 2026-27, and every season maps 100% of FotMob minutes
  to FPL elements.
- **Data audit:**
  - Stable `player_id` (FPL `code`) replaces the name as the cross-season key.
    Names had linked 0 of 625 players into 2018-19.
  - `team` is taken from the fixture side (1,080 rows in 2016-20 named a club
    in neither side).
  - FotMob defensive stats replace FBref's, which correlated only 0.34–0.62
    with Opta and gave 11,087 non-playing rows defensive actions.
  - Covid phantom rows dropped, `GKP` → `GK`, and lags carry across seasons.
  - The chance-of-playing field is read for the gameweek being described.
- **Chips:** one plan slot per chip per half; extrapolated weeks discounted;
  second-half chips held for doubles and blanks; reasons say why a
  better-looking week was passed over.
- **Stats Lab API** (`/api/stats/players`, `/api/player/<id>/underlying`) and
  **effective ownership** (`webapp/ownership.py`, `/api/ownership`, sampled
  top-10k/top-1k/overall teams).
- **Slice D:** FotMob (`fm_*`) and FPL defensive (`def_*`) feature families
  were evaluated on the served two-stage model by `scripts/ablate_two_stage.py`
  (results in `reports/ablation_two_stage*.json`). Only `def_` for MID passed
  the bar of R² up and MAE down on both folds. A leak was caught along the
  way: a recorded-flag encoded "played this match". All models were retrained
  and predictions regenerated.
- Visual work for this session (the Stats Lab page, EO panels, phone bottom nav,
  V1 polish) went to the `stats-lab-preview` branch for review.

### 2026-10-30 — Double gameweeks, stable ids, client races

- **Double gameweeks:** olbauday's one row per gameweek is split into one row
  per match using FPL's `element-summary` history. Rows that history cannot
  cover are held back, not misfiled. Blank-gameweek zero rows are dropped.
- **Stable fixture ids:** `home club id × 100 + away club id`, instead of row
  order, which moved between fetches.
- **FPL client:** the shared cache is locked (concurrent inserts could kill an
  ownership run), bulk pick reads bypass the cache, and bootstrap-static gets
  its own 8 MB ceiling.
- `keep_fotmob_seasons`: a rebuild on a machine without the gitignored FotMob
  cache no longer silently reverts 2019-25 to FBref defensive stats.
- Free Hit and Wildcard in/out lists. Transfer Studio and the deadline board
  share the chip state and free transfers.
- Data refreshed through GW8; predictions GW9–GW20.

### 2026-11-22 — Repository tidy-up

- Root reorganised: datasets in `data/`, predictions and manifest in
  `predictions/`, metrics in `reports/`, squad files in `squads/`, design docs,
  prototype and screenshots in `docs/`. Every script, test and notebook path
  was updated to match.
- The 16 plan, prompt, progress and handoff files and `debug.log` were deleted.
  This file replaces them.

---

## Current numbers

**Two-stage model, holdout** (retrained 2026-10-22; validation 2023-24, test
2024-25 + 2025-26). Details are in `reports/availability_metrics.json`.

| position | R² | MAE |
|---|---|---|
| GK  | 0.384 | 0.667 |
| DEF | 0.273 | 1.128 |
| MID | 0.341 | 1.009 |
| FWD | 0.335 | 1.081 |

These numbers cannot be compared with earlier tables. The defensive-stats
correction changed 9,692 targets, which on its own raises the DEF and MID MAE.
Run-to-run noise from the boosters is about ±0.005.

**Selection backtest** (2026-09-17; the same integer program each gameweek over
both holdout seasons, £83m): model 51.2 points per gameweek against 43.5 for a
`rolling_5` heuristic. That is +507 points, better in 51 of 66 gameweeks
(paired t = 4.34), and captures 8.5% of the gap to perfect foresight.

**Horizon backtest:** over 28 six-gameweek windows the horizon squad scored
+17.8 points and was better in 19 of 28 (t = 2.20). The windows overlap, so
this is suggestive rather than settled.

**Classifiers:** P(plays) 0.954 AUC; P(haul ≥ 10) 0.869 AUC.

---

## Decisions and negative results

| change | result | verdict |
|---|---|---|
| expected goals (`xg_*`) | −0.0000 marginal R² | redundant with rolling points, bps and ICT |
| FBref-derived features | −0.0001 | dropped. The data stays, because DefCon is part of the target |
| old `opponent_*` family | +0.0012 (−0.009 alone) | replaced by `fx_*` |
| `fx_*` fixture rebuild | +0.0045 marginal, +285 selection points | kept |
| P(haul) for captaincy | 0.869 AUC | does not beat expected points |
| FotMob `fm_*` features | fail on every position | kept out of the model, used in Stats Lab |
| `def_*` for MID | val +0.0058 R² / −0.0072 MAE | kept (`EXTRA_PREFIXES`) |
| training from 2019-20 only | below full history everywhere | rejected |
| horizon decay < 1.0 | monotonically worse | `--decay` defaults to 1.0 |
| PCA branch | no benefit | removed |

Standing product rules:
- Never show a prediction as a fact.
- Never fabricate data the backend does not have.
- Chip verdicts stay conservative (`MIN_GAIN`, close-call flags).

---

## Data notes

- `data/all_seasons_data_final.csv` is tracked and load-bearing. The
  rebuild lifts defensive columns out of it, and `data/fbref_defensive.csv` is
  the committed FBref backup. `build_dataset.py --write` snapshots the old file
  to `data/all_seasons_data_final.csv.prev` first.
- `data/<season>/fotmob/` is gitignored. Rebuild it with
  `python scripts/fetch_fotmob.py --season 2026-27 --backfill 2019-20,...`.
  It replays from cache without refetching. `data/fotmob_overrides.csv`
  (committed) wins over the name matcher.
- The refresh pipeline never retrains. Re-run `build_features.py`,
  `train_availability.py` and `calibrate.py` every few gameweeks so new weeks
  count.
- 2026/27 rules checked against the official sources: two chip sets split
  after GW19, one chip per gameweek, no WC or FH in GW1, a GW19 Free Hit blocks
  FH in GW20, free transfers roll up to five.

---

## Working environment

- Use an interpreter that has lightgbm and xgboost for the modelling scripts.
  Training runs locally in about 3 minutes with `LOKY_MAX_CPU_COUNT=3`; the
  default 12 workers ran out of memory on 16 GB. Colab is no longer required.
- Frontend checks: `npm exec tsc -- --noEmit`, `npm run build`, `npm run lint`.
  Backend checks: `python -m pytest -q tests` (441 passing as of 2026-11-22).
- Open the Next dev server through `localhost` or `127.0.0.1`. Both are in
  `allowedDevOrigins`, and another host silently blocks hydration.
- On Windows, stopping a shell task can leave orphaned `next dev` or Python
  processes holding ports 3000 and 5000.
- The remotes are `origin` (GitHub, `LouaiSf/Fantasy-premier-league-points-prediction`)
  and `vercel`. Many `remotes/origin/*` refs are stale local copies of
  branches already deleted on GitHub; `git fetch --prune` clears them.

---

## Open items

**Waiting on review**
- [ ] `stats-lab-preview` branch: the Stats Lab page, EO panels, phone bottom
      nav and More sheet, and V1 page polish. Merge into `main` once approved.
      Expect small conflicts in chips, Transfer Studio and team pages.

**Data**
- [ ] A double gameweek's per-match split needs FPL's history to contain both
      matches. Until it does, those rows are held back (logged).
- [ ] After the next fetch, re-run `--with-fotmob` so `player_match.csv`
      carries the new stable fixture ids.
- [ ] FBref-era defensive values (2019-23) remain on the few played rows
      FotMob could not map.

**Product**
- [ ] V1 leftovers: My Team hero height on phones, duplicate ownership text in
      Watchlist, the scale caption for captain Form and ICT, and the
      `docs/DESIGN.md` §5 update for the bottom nav and Stats Lab.
- [ ] Add "My league" EO to the tier selector. The API supports `?league=`,
      but sampling a 500-member league takes about 60 s.
- [ ] A horizon evaluator for multi-week scenario totals. `/api/lineup` covers
      a single gameweek only.
- [ ] Projection-change explainer, personal alerts, model reliability card.
      Each needs stored history that does not exist yet.
- [ ] Bench Boost historical calibration before any chip verdict is phrased
      as "play".

**Release**
- [ ] Confirm the rights to Premier League photos and crests before public
      launch (`docs/DESIGN.md`, Accepted debt).
- [ ] Add a GitHub repository description and topics. This needs an account
      with admin access on the repo.
