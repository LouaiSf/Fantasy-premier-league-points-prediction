# Fantasy Premier League points prediction

Predicts a player's FPL points for an upcoming gameweek from their history,
their team's form, and the opponent. Ten seasons of data, four position-specific
models, evaluated on seasons the models never saw.

## Results

Test fold is **2024-25 and 2025-26**, 50,048 player-matches, held out entirely.
Training stops at 2022-23; 2023-24 is the validation season.

| position | best model | test R² | test MAE | vs. `rolling_5` |
|---|---|---|---|---|
| GK  | LightGBM   | 0.429 | 0.655 | **+0.110** |
| DEF | LightGBM   | 0.284 | 1.137 | **+0.136** |
| MID | LightGBM   | 0.339 | 1.031 | **+0.118** |
| FWD | ElasticNet | 0.337 | 1.157 | **+0.113** |

The last column is the one that matters. `rolling_5` — predict a player's mean
over their last five matches — is the heuristic the whole model has to justify
itself against. **+0.11 to +0.14 R² over it**, on 50,000 held-out rows.

For scale: predicting from a single previous match (`prev_1`) scores *negative*
R² at every position, worse than predicting the overall mean.

Run `python scripts/baselines.py` to reproduce the comparison.

## Quick start

```bash
pip install -r requirements.txt

python scripts/fetch_data.py            # refresh 2025-26 / 2026-27 from upstream
python scripts/rebuild_merged_gw.py     # audit merged_gw.csv against its parts
python scripts/build_dataset.py --write # -> all_seasons_data_final.csv
python scripts/build_features.py        # -> all_seasons_data_featured.csv
python scripts/train.py                 # -> saved_models/, model_metrics.json
```

Training needs `xgboost` and `lightgbm` and takes about an hour on a laptop
CPU. **`FPL_Colab.ipynb` runs the whole thing on Colab free tier** — upload
`fpl_colab.zip` (built by `scripts/make_colab_bundle.py`) to Drive, upload the
notebook to Colab, Run all. No GPU required; none of these models use one.

## How it fits together

```
data/<season>/gws/merged_gw.csv          raw, from vaastav/Fantasy-Premier-League
        |
        |  build_dataset.py     merge 11 seasons, harmonise columns, map teams,
        |                       assign game_number, carry over FBref defensive
        v                       stats, re-apply the scoring rules
all_seasons_data_final.csv               254,188 rows x 42 cols
        |
        |  build_features.py    lags 1-5, rolling 3/5/10, opponent strength,
        v                       price momentum, availability
all_seasons_data_featured.csv            254,188 rows x 289 cols
        |
        |  train.py             per-position models, season-holdout split,
        v                       TimeSeriesSplit hyperparameter search
saved_models/ + model_metrics.json + baseline_metrics.json
```

The heavy lifting still lives in `final.ipynb`. The scripts execute ranges of
its cells rather than reimplementing them (`scripts/nbrun.py`), so the notebook
stays the single source of truth and the scripts cannot drift from it.

## Scripts

| script | what it does |
|---|---|
| `fetch_data.py` | pull season data from the upstream mirror; resumable, verifies each file |
| `rebuild_merged_gw.py` | check each `merged_gw.csv` against its per-gameweek files, rebuild if short |
| `build_dataset.py` | merge every season into one frame with consistent columns |
| `build_features.py` | lagged, rolling, opponent and availability features |
| `train.py` | train, evaluate, save models, report feature importance |
| `baselines.py` | score heuristics on the identical test rows |
| `ablate.py` | measure what one feature group is worth, holding all else fixed |
| `summarise_run.py` | render `model_metrics.json` as a table |
| `test_notebook_fixes.py` | 25 regression tests over the split, guards and features |
| `make_colab_bundle.py` | package the 122 files Colab needs (24 MB, not 17,000 files) |

## Things worth knowing

**Evaluation is by season, not shuffled.** The original notebook used a random
`train_test_split` on panel data, which puts a player's adjacent gameweeks on
both sides of the split. Every figure it reported was optimistic. Scalers,
correlation filters and PCA bases are all fitted on the training fold only.

**FPL's own `xP` is not a usable benchmark**, in two different ways. For
2023-24 and 2024-25 it was captured at or after lineup announcement, so it
knows who started — an advantage no model here has, worth roughly half its
apparent accuracy. For 2025-26 it is simply broken: negative R², with players
who appeared averaging 0.779 expected points against ~2.3 in earlier seasons.
`baselines.py` scores it per season and labels each `UNFAIR` or `BROKEN`.
Neither counts toward the verdict.

**Defensive stats come from two places.** 2019-20 to 2024-25 were merged from
FBref, and that merge covers 2024-25 only through GW21 — later rows carry
`has_fbref_defensive=0` and zeros rather than pretending. Every other season
carries FPL's own defensive columns, which the FBref join must not overwrite.

**Hyperparameter tuning is finished.** Three rounds of re-centring the grids
moved test R² by less than 0.005 while the chosen values stayed pinned to the
grid edges. The ceiling here is the features, not the search.

**Most of the 220 features are redundant.** `scripts/ablate.py` measures each
family two ways — what it adds on top of everything else, and what it scores
alone:

| family | features | marginal R² | alone R² |
|---|---|---|---|
| `minutes*` | 8 | +0.0036 | **0.326** |
| `avail_*` | 16 | +0.0033 | 0.321 |
| `total_points_*` | 8 | +0.0003 | 0.294 |
| `bps*` | 8 | +0.0006 | 0.279 |
| `ict_index*` | 8 | −0.0000 | 0.268 |
| `tackles*` | 5 | −0.0001 | 0.097 |
| `recoveries*` | 5 | −0.0001 | 0.081 |
| `opponent_*` | 17 | +0.0012 | −0.009 |

Minutes history alone reaches 0.326 against the full model's 0.339. Keeping
only `minutes`, `avail_`, `total_points_` and `bps` — **40 features instead of
220** — costs 0.003 R² on average and is *better* for forwards:

```
python scripts/ablate.py --keep-only minutes avail_ total_points_ bps
```

Two consequences worth taking seriously. The 17 opponent-strength and
fixture-difficulty features score *below* the mean on their own and add
+0.001 in company. And the FBref defensive merge — a 757-line fuzzy name
matcher plus a scrape of roughly 380 requests per season — produces features
worth −0.0001 marginally. This is fundamentally a model of whether a player
will be on the pitch.

**2026-27 contributes nothing yet.** Only GW1 exists upstream, and rolling
features need five matches, so every row is dropped. It will start counting
around GW6. `build_dataset.py` picks up new season folders automatically, so
that needs a fetch and no code change.

## Layout

```
final.ipynb              the pipeline: merge, features, models, squad optimiser
FPL_Colab.ipynb          runs the whole pipeline on Colab
scripts/                 the pipeline as runnable stages
data/<season>/           raw season data
saved_models/direct/     per-position models, scalers, feature lists
```

`advanced_fpl_models.ipynb`, `prediction_workflow.ipynb`,
`fetching_defensive_data.ipynb`, `using_api.ipynb` and `add_game_number.ipynb`
are earlier explorations. They are **not** part of the pipeline and still carry
the bugs described in the git history — notably the silent feature-count
collapse that trained models on price alone.

## Tests

```bash
python scripts/test_notebook_fixes.py
```

25 tests over the season split, the feature-coverage guard, the availability
features (including one that tampers with a row's own minutes and asserts the
row's features do not move), and the native-defensive-stats join.
