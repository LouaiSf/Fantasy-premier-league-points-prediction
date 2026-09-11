# Project status

_Last updated: 2026-09-11._

A running record of what has been built, what the numbers currently are, and
what is still open. `README.md` documents the finished pipeline; this file
tracks the work around it.

---

## Where the work lives

| branch | state |
|---|---|
| `pipeline-for-public` (local) | **all 29 commits of work** — this is the real project |
| `public/fix/training-pipeline` | identical to the above, already pushed |
| `public/main` | 29 commits behind — the merge has not happened yet |
| `main` (local) | the inherited baseline, one commit |

Two things to be aware of before picking this up again:

1. The working tree is currently checked out on local `main`, which is the
   **inherited baseline** — old notebooks, no `scripts/`, no `webapp/`.
   `git switch pipeline-for-public` first. (`data/2024-25/`, `data/2025-26/`
   and `fpl_colab.zip` are sitting untracked in the folder and will need
   stashing or removing, since the target branch tracks those paths.)
2. Merging into `public/main` is a clean fast-forward — zero conflicts, no
   rebase needed. It was deliberately deferred until the work was finished.

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
| GK  | LightGBM | 66 | 0.459 | 0.632 | **+0.138** |
| DEF | LightGBM | 74 | 0.303 | 1.128 | **+0.152** |
| MID | LightGBM | 74 | 0.348 | 0.970 | **+0.126** |
| FWD | LightGBM | 74 | 0.348 | 1.067 | **+0.121** |

Run-to-run variation from the boosters is around ±0.005; treat smaller gaps as
noise.

**Selection backtest** — the same integer program per gameweek, all 33
gameweeks of 2025-26, £83m budget:

| strategy | total | per GW |
|---|---|---|
| model predictions | 1856 | 56.2 |
| `rolling_5` average | 1375 | 41.7 |
| perfect foresight | 4499 | 136.3 |

**+481 points**, better in 29 of 33 gameweeks (88%), paired t = 5.64. That
captures **15.4%** of the gap between the heuristic and perfect foresight, up
from 6.1% before the fixture features landed.

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

- [ ] `git switch pipeline-for-public` (the working tree is on the baseline)
- [ ] Merge into `public/main` — clean fast-forward, deliberately deferred
- [ ] Delete the stale remote branches on `public/` once main has the work
      (about 20 remain from the original group project)

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

- [ ] **2026-27 contributes nothing yet** — only GW1 exists upstream, and
      rolling features need five matches, so every row is dropped. It starts
      counting around GW6. Needs a `fetch_data.py` run, no code change
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
