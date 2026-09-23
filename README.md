# Fantasy Premier League points prediction

Predicts a player's FPL points for an upcoming gameweek from their history,
their team's form, and the opponent. Ten seasons of data, four position-specific
models, evaluated on seasons the models never saw.

## Results

Test fold is **2024-25 and 2025-26**, 50,048 player-matches, held out entirely.
Training stops at 2022-23; 2023-24 is the validation season.

| position | best model | features | test R² | test MAE | vs. `rolling_5` |
|---|---|---|---|---|---|
| GK  | LightGBM | 66 | 0.459 | 0.632 | **+0.138** |
| DEF | LightGBM | 74 | 0.303 | 1.128 | **+0.152** |
| MID | LightGBM | 74 | 0.348 | 0.970 | **+0.126** |
| FWD | LightGBM | 74 | 0.348 | 1.067 | **+0.121** |

74 features, not 220, and better than 220 at every position — the fixture
features are worth +0.009 to +0.027 R² over the old set while using a third of
the columns. Run-to-run variation from the boosters is around ±0.005, so treat
differences smaller than that as noise.

The last column is the one that matters. `rolling_5` — predict a player's mean
over their last five matches — is the heuristic the whole model has to justify
itself against. **+0.12 to +0.15 R² over it**, on 50,000 held-out rows.

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

All 33 gameweeks of 2025-26, 83m budget:

| strategy | total | per GW | vs. `rolling_5` |
|---|---|---|---|
| model predictions | 1856 | 56.2 | **+481** |
| `rolling_5` average | 1375 | 41.7 | — |
| perfect foresight | 4499 | 136.3 | +3124 |

The model beat `rolling_5` in **29 of 33 gameweeks (88%)**, mean +14.58 per
gameweek, paired t = 5.64. So the better R² does translate into better teams —
and by considerably more than the R² gap alone suggests.

It captures **15.4%** of the distance between the heuristic and perfect
foresight, up from 6.1% before the fixture features replaced the old opponent
family. The R² gain from that change was +0.01 to +0.03; the selection gain was
+285 points over a season, because ranking the top of the distribution
correctly matters far more here than average closeness does.

Note this picks a fresh XI each week with no transfer limit and no captain, so
it measures ranking quality rather than achievable FPL performance.

## The web UI

```bash
python webapp/app.py       # then open http://127.0.0.1:5000
```

Four tools in one page:

| tab | what it answers |
|---|---|
| **Squad builder** | Best legal 15 for a budget, solved as one LP with the XI and captain. Lock players in, exclude others, see the result laid out on a pitch. |
| **Transfers** | How many moves are worth making, with the −4 hit charged before comparing. Your squad is saved in the browser. |
| **Chips** | When to play Bench Boost, Triple Captain, Free Hit and Wildcard, from the fixture calendar and your squad's blanks. |
| **Watchlist** | Value per million, low-ownership differentials, and expensive players the model does not rate. |

It calls `scripts/optimise.py` directly rather than reimplementing anything, so
the browser and the CLI cannot disagree — the same `solve_squad` produces both.
Needs `predictions_next_gw.csv` from `scripts/predict_gameweek.py`.

## Keeping predictions fresh

`/api/refresh` only pulls raw FPL data; the predictions are a separate export
and would otherwise go on serving last week's numbers. `scripts/refresh_pipeline.py`
runs the whole chain and only swaps the result in once it has checked it:

1. fetch current season data
2. run `predict_gameweek.py --horizon 12` into a temp file
3. validate it: required columns, no blank points, the first gameweek matches the
   freshly fetched fixtures, every week of the horizon present, clubs match
   `teams.csv`, no collapse in player count
4. `os.replace()` it onto `predictions_next_gw.csv`

Any failure leaves the previous export untouched. A lock file stops two runs
overlapping. The web app reloads on the file's mtime, so no restart is needed.

```bash
python scripts/refresh_pipeline.py              # ~90 s; exit code 0 / 1
python scripts/refresh_pipeline.py --no-fetch --horizon 8
```

Schedule it (for example daily, and after each gameweek's deadline) with cron or
Windows Task Scheduler and alert on a non-zero exit. From the site, the Refresh
button fetches the data and then runs the same pipeline in the background
(`POST /api/refresh/predictions`, poll `GET /api/refresh/status`).

If `all_seasons_data_final.csv` lags the fetched data the pipeline runs
`build_dataset.py --write` first (about 30 s, and it keeps a `.prev` copy), since
predictions are built from that history; `--no-rebuild-history` skips it. It never
retrains models.

Every command's exit status is checked, and a failure returns the step, exit
status and stderr (as JSON from the API, on stderr from the CLI). Refreshes are
serialised by a lock (`409` if one is running) and rate limited: `429` with
`Retry-After` for 60 s after a fetch, or 10 s after a failed one. Override with
`REFRESH_COOLDOWN_SECONDS` / `REFRESH_FAILURE_COOLDOWN_SECONDS`.

## Securing the API

| Variable | Effect |
|---|---|
| `APP_ENV=production` | Fail closed: no CORS unless `ALLOWED_ORIGINS` is set, and `*` is refused at startup. |
| `ALLOWED_ORIGINS` | Comma-separated browser origins allowed to call the API. Unset in development = `http://localhost:3000` and `http://127.0.0.1:3000`. |
| `REFRESH_TOKEN` | Bearer token required by `/api/refresh`, `/api/refresh/predictions`, `/api/refresh/status` and `/api/reload`. **Unset = those endpoints accept only direct local requests** (a proxied request, one carrying `X-Forwarded-For`, counts as remote and gets `403 refresh_disabled`). |
| `REFRESH_RATE_LIMIT_PER_MINUTE` | Calls per minute per client to the refresh endpoints, wrong tokens included (default 12). Status polling has its own, larger limit. |
| `REFRESH_COOLDOWN_SECONDS` | Minimum gap after a successful fetch (default 60). |

CORS only constrains browsers; the token is what stops `curl`. The site's Refresh
button asks for the token once per tab and keeps it in `sessionStorage`; it is
never built into the frontend bundle. Rate limits and the cooldown are held in
memory, so they are per server process (run one worker, as `render.yaml` does).

**Market prices fail closed.** Prices come only from `data/<season>/players_raw.csv`.
If that file is missing, unreadable, or prices under half the predicted players,
`/api/players`, `/api/squad`, `/api/lineup`, `/api/transfers`, `/api/chips` and
`/api/watchlist` return `503` with `code: "market_prices_unavailable"`, and
`/api/meta` / `/api/platform` report `market_prices_available: false`. The prediction
export's own prices are never used as a fallback.

**Request contract.** Every route reads input through `webapp/contracts.py`. Bodies
must be JSON objects; numbers are real JSON numbers (never strings, booleans, NaN or
infinity); lists and names are type- and size-checked; unknown player IDs are
rejected. Errors are always `{ok: false, error, code, field?}` with a stable `code`
(listed in that module), and every response carries `api_contract_version` and an
`X-API-Contract-Version` header. Unexpected failures are a generic `500
internal_error`; details go to the server log, not the response.

## Reproducibility: what a deployment consumes

The site never trains or predicts. It serves one **immutable prediction artifact**,
`predictions_next_gw.csv`, and its manifest `predictions_next_gw.manifest.json`
(sha256 of the CSV, when it was generated, season, gameweek range, the git commit,
and a fingerprint of the model bundle that produced it). Commit both together.

The models themselves (`saved_models/**/*.joblib`, ~13 MB) are gitignored, so a
fresh clone **cannot regenerate predictions**, and that is deliberate: training and
prediction are a separate job, run wherever the models live (a Colab/GPU session, or
`scripts/refresh_pipeline.py` on a machine that has them), and their output is
published as the artifact. `scripts/refresh_pipeline.py` writes the manifest with every
run; `python scripts/artifacts.py write` makes one for a CSV produced by hand, and
`python scripts/artifacts.py verify` exits non-zero unless the manifest matches.

In production (`APP_ENV=production`, or `REQUIRE_ARTIFACT_MANIFEST=1`) the server
reports **not ready** unless the manifest verifies, so an unversioned or hand-edited
artifact cannot go live unnoticed. `/api/meta` returns the artifact hash, generation
time and model-bundle hash, so any served number can be traced to the exact models.

## Monitoring

| Endpoint | Purpose |
|---|---|
| `GET /api/health/live` | Process is up. Never touches data. |
| `GET /api/health/ready` | `200` only when predictions load, live prices exist and (in production) the manifest verifies; else `503` with the blocking reasons. Also returns freshness and alerts. Used as Render's health check. |
| `GET /api/metrics` | Prometheus text: data ages, next deadline, `fpl_ready`, one `fpl_alert_active{alert=...}` per alert, artifact identity, request counts and latency. Same token/loopback guard as the refresh endpoints. |

Every request gets an `X-Request-ID` (a safe inbound one is honoured) and one JSON log
line on stderr (`event`, `request_id`, `route`, `status`, `duration_ms`, `error_code`);
unhandled errors log the traceback there and return only a generic 500. `LOG_LEVEL`
sets verbosity; health and metrics calls log at DEBUG.

Alert conditions, all visible in `/api/health/ready` and as metrics, and logged when
raised and cleared: `predictions_unavailable`, `market_prices_unavailable`,
`artifact_manifest_invalid` (the three that block readiness), `predictions_older_than_market`,
`predictions_gameweek_mismatch`, `predictions_too_old` (72 h), `market_data_old` (48 h),
`predictions_stale_before_deadline` (deadline within 24 h and predictions over 12 h old),
`predictions_predate_deadline`, and `predictions_rebuild_failing`. Thresholds:
`MAX_PREDICTION_AGE_HOURS`, `MAX_MARKET_AGE_HOURS`, `DEADLINE_WINDOW_HOURS`,
`STALE_BEFORE_DEADLINE_HOURS`. The deadline is estimated as the gameweek's first
kick-off minus 90 minutes, because the local fixtures file has no official deadline.

This service exposes the alerts; it does not deliver them. Point Prometheus/Alertmanager
(or an uptime monitor on `/api/health/ready`) at it to page someone. Conditions are
evaluated when scraped, so nothing fires unless something is watching.

## Concurrency

Loaded data is an immutable snapshot that is replaced wholesale, never edited: a request
uses one snapshot from start to finish, and rebuilds are serialised by a lock. A snapshot
is rebuilt when any source file changes (predictions, manifest, market prices, teams,
fixtures). During a refresh the last good snapshot keeps being served instead of reading
files mid-write, and a source file that cannot be read never replaces good data. The
server no longer calls `os.chdir`; paths are built from the project root. The
`/api/platform` payload and the ~800-player enrichment are cached by file modification
time. State is per process, so run one worker (as `render.yaml` does).

## Intentional product limitations

- **No accounts or authentication for users.** There is no login and no server-side user
  data. (Only the refresh/metrics endpoints are token-protected, for the operator.)
- **Squad, chip and finance data live in the browser** (`localStorage`), with
  export/import to move between devices. Clearing site data loses them.
- **No global manager-name search.** FPL has no such endpoint; search is scoped to a
  classic league whose ID you supply (or a lineup by entry ID).
- **No built-in background scheduler.** Predictions refresh when someone clicks Refresh
  or when you schedule `python scripts/refresh_pipeline.py` (cron, Task Scheduler, CI).
  The monitoring above tells you when that has not happened.
- **Fetching rewrites data files in place.** Readers are protected by the snapshot, but
  `fetch_data.py` itself is not atomic per file.

## Quick start

```bash
pip install -r requirements.txt

python scripts/fetch_data.py            # refresh 2025-26 / 2026-27 from upstream
python scripts/rebuild_merged_gw.py     # audit merged_gw.csv against its parts
python scripts/build_dataset.py --write # -> all_seasons_data_final.csv
python scripts/build_features.py        # -> all_seasons_data_featured.csv
python scripts/train.py                 # -> saved_models/, model_metrics.json
python scripts/predict_gameweek.py --season 2026-27 --horizon 12 --out predictions_next_gw.csv
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

**Chips** compares Triple Captain, Bench Boost, Free Hit and Wildcard using
the player-by-gameweek matrix in the prediction export. Generate enough weeks
for the horizon you want to inspect. A single-gameweek or partial export shows
fixture-signal indices separately and withholds projected gains. Candidate
weeks show the top three calculations and their inputs. A play recommendation
is limited to the current gameweek, a complete squad, synced inventory, and a
projected gain above the named DECISION_MARGIN policy; this is product policy,
not a learned threshold. Free Hit compares the optimized and current XI plus
captain totals without adding speculative avoided-hit value.

**Watchlist** surfaces value picks, differentials by ownership, players
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
all_seasons_data_final.csv               254,179 rows x 47 cols
        |
        |  build_features.py    lags 1-5, rolling 3/5/10, price momentum,
        v                       availability, expected goals, fixture difficulty
all_seasons_data_featured.csv            254,179 rows x 339 cols
        |
        |  train.py             per-position models, season-holdout split,
        v                       TimeSeriesSplit hyperparameter search
saved_models/ + model_metrics.json + baseline_metrics.json
```

The whole pipeline lives in **`fpl_pipeline.ipynb`**, in the order it runs:
load and merge, match index, features, split and train, two-stage models, save.
The scripts execute ranges of its cells rather than reimplementing them
(`scripts/nbrun.py`), so the notebook stays the single definition and the
scripts cannot drift from it.

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
| `predict_gameweek.py` | predict the upcoming gameweek from the live FPL API; rank every player |
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
fpl_pipeline.ipynb       the pipeline, in the order it runs
FPL_Colab.ipynb          runs the whole pipeline on Colab free tier
scripts/                 each stage as a runnable script, plus the tools
webapp/                  Flask UI over the tools
data/<season>/           raw season data
saved_models/direct/     per-position models, scalers, feature lists
```

Earlier exploratory notebooks (`advanced_fpl_models`, `prediction_workflow`,
`using_api`, `add_game_number`, `fetching_defensive_data`) have been removed:
each was superseded, and each still carried the original bugs. They remain in
git history if you need them.

## Tests

```bash
python scripts/test_notebook_fixes.py
```

25 tests over the season split, the feature-coverage guard, the availability
features (including one that tampers with a row's own minutes and asserts the
row's features do not move), and the native-defensive-stats join.
