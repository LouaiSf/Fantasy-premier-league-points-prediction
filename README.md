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

Those are from the full 220-feature set. The default is now the 54-feature
compact set, which costs 0.0004 R2 on average and improves MAE everywhere --
see "Most of the features are redundant" below.

The last column is the one that matters. `rolling_5` — predict a player's mean
over their last five matches — is the heuristic the whole model has to justify
itself against. **+0.11 to +0.14 R² over it**, on 50,000 held-out rows.

For scale: predicting from a single previous match (`prev_1`) scores *negative*
R² at every position, worse than predicting the overall mean.

Run `python scripts/baselines.py` to reproduce the comparison.

### Does it pick better teams?

R2 measures the wrong thing for FPL: it rewards being close on the 60% of
players who score two points, while selection only rewards being right at the
top of the ranking. `scripts/validate_selection.py` solves the same integer
program once per gameweek under three objectives, with identical budget,
formation and max-three-per-club constraints, and adds up what those elevens
actually scored.

All 34 gameweeks of 2025-26, 83m budget:

| strategy | total | per GW | vs. `rolling_5` |
|---|---|---|---|
| model predictions | 1614 | 47.5 | **+196** |
| `rolling_5` average | 1418 | 41.7 | — |
| perfect foresight | 4621 | 135.9 | +3203 |

The model beat `rolling_5` in **22 of 34 gameweeks**, mean +5.76 per gameweek,
paired t = 2.61. So the better R2 does translate into better teams.

It captures 6.1% of the distance between the heuristic and perfect foresight —
better than the obvious alternative, nowhere near the ceiling. Note this picks
a fresh XI each week with no transfer limit and no captain, so it measures
ranking quality rather than achievable FPL performance.

## Quick start

```bash
pip install -r requirements.txt

python scripts/fetch_data.py            # refresh 2025-26 / 2026-27 from upstream
python scripts/rebuild_merged_gw.py     # audit merged_gw.csv against its parts
python scripts/build_dataset.py --write # -> all_seasons_data_final.csv
python scripts/build_features.py        # -> all_seasons_data_featured.csv
python scripts/train.py                 # -> saved_models/, model_metrics.json
python scripts/predict_gameweek.py      # -> predictions_next_gw.csv
python scripts/optimise.py squad --budget 100        # best legal 15 + XI + captain
python scripts/optimise.py transfers --squad example_squad.txt --free 1
python scripts/optimise.py chips --squad example_squad.txt --horizon 8
python scripts/optimise.py watchlist --max-ownership 5
python scripts/validate_selection.py    # does it pick better teams than a heuristic?
python scripts/train.py --features full # all 220 features instead of 54
python scripts/ablate.py --prefix avail_ opponent_   # what a group is worth
```

Training needs `xgboost` and `lightgbm` and takes about an hour on a laptop
CPU. **`FPL_Colab.ipynb` runs the whole thing on Colab free tier** — upload
`fpl_colab.zip` (built by `scripts/make_colab_bundle.py`) to Drive, upload the
notebook to Colab, Run all. No GPU required; none of these models use one.

## Making decisions

`optimise.py` turns predicted points into the choices a manager actually
faces. Each answer is a single integer program, so it is optimal under the
stated constraints rather than a greedy pick.

**`squad`** picks the best legal 15 under a budget, and decides the XI, bench
order and captain *in the same program* — a cheap bench is only worth having
for what it frees up in the XI, so choosing the 15 and the 11 separately gives
a worse answer. Constraints are the real ones: 2/5/5/3, £100m, max 3 per club,
a legal formation. `--lock` and `--ban` force players in or out.

**`transfers`** takes the 15 you already own and reports the best move at
every transfer count, net of the −4 hits:

```
moves     gross   hit     net    vs 0
0         56.66     0   56.66   +0.00
1         57.13     0   57.13   +0.48
2         57.13     4   53.13   -3.52
```

Showing every count matters: a second transfer nearly always buys raw points
and nearly never survives the hit. It also says when a gain is inside the
model's error (~1.0 MAE per player) and the transfer is worth rolling.

**`chips`** ranks gameweeks for Triple Captain, Bench Boost, Free Hit and
Wildcard over a horizon, using fixture counts, FDR, and how much of *your*
squad plays. It is explicit that the model's per-player number does not vary
by gameweek — opponent features were measured and dropped — so the
gameweek-to-gameweek signal is fixtures, not the model. When no double or
blank gameweek is scheduled it says so rather than inventing a recommendation.

**`watchlist`** surfaces value picks, differentials by ownership, players
priced above what they return, and anyone whose number comes from no prior
data at all.

Copy `example_squad.txt` and edit it to your own 15.

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
| `predict_gameweek.py` | rank every player for the upcoming gameweek |
| `validate_selection.py` | score the XI the model picks against a rolling-average XI |
| `optimise.py` | squad, transfers, chip timing and watchlist |
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

Minutes history alone reaches 0.326 against the full model's 0.339.

**So the compact set is now the default**: `minutes`, `avail_`,
`total_points_`, `bps`, `value`, `ict_index` — **54 features instead of 220**,
chosen by searching five candidate sets. Ridge, against the full set:

| position | features | R² | vs. full | MAE | vs. full |
|---|---|---|---|---|---|
| GK  | 159 → 46 | 0.4250 | **+0.0015** | 0.663 | **−0.040** |
| DEF | 220 → 54 | 0.2749 | −0.0044 | 1.145 | **−0.014** |
| MID | 220 → 54 | 0.3346 | −0.0046 | 0.991 | **−0.014** |
| FWD | 220 → 54 | 0.3381 | **+0.0061** | 1.110 | **−0.040** |

Mean R² cost is 0.0004, and **MAE improves at every position** — the dropped
columns were adding variance, not signal. `--features full` restores all 220.

Two consequences worth taking seriously. The 17 opponent-strength and
fixture-difficulty features score *below* the mean on their own and add
+0.001 in company. And the FBref defensive merge — a 757-line fuzzy name
matcher plus a scrape of roughly 380 requests per season — produces features
worth −0.0001 marginally. This is fundamentally a model of whether a player
will be on the pitch.

The FBref *data* stays regardless: `defensive_contribution` decides a +2 point
bonus on 10,604 rows, so it is part of the target even though it is nearly
worthless as a feature. Only the derived columns are dropped.

To re-run the search:

```bash
python scripts/ablate.py --prefix minutes avail_ opponent_ bps ict_index
python scripts/ablate.py --keep-only minutes avail_ total_points_ bps value ict_index
```

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
