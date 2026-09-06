"""Predict points for the upcoming gameweek.

Everything else in this project scores the past. This is the part that answers
the question the project exists for: who should I pick this week.

How it works
------------
The features are all lags and rolling means of a player's own previous
matches, so predicting an unplayed fixture means appending a placeholder row
for it and running the same feature engineering that produced the training
data. The shift(1) inside every feature then fills that row from the matches
already played, and nothing has to be recomputed by hand.

That last part matters. The previous attempt at this
(advanced_fpl_models.ipynb) rebuilt features from the bootstrap payload with a
separate code path, and it silently produced 54 predictions for 811 players --
one fixture's worth -- because a bare `except: continue` swallowed every
mismatch. Reusing the real feature functions removes the opportunity for that
kind of drift, and the coverage check below turns what is left into a loud
failure rather than a short CSV.

Data sources
------------
FPL API      current prices, availability, and which fixtures fall in the
             target gameweek. Falls back to data/<season>/fixtures.csv when
             the API is unreachable.
local CSVs   every prior match, for the history the features are built from.

Usage
-----
    python scripts/predict_gameweek.py
    python scripts/predict_gameweek.py --gameweek 12 --top 40
    python scripts/predict_gameweek.py --season 2026-27 --no-api
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range  # noqa: E402

NOTEBOOK = 'final.ipynb'
HISTORY = 'all_seasons_data_final.csv'
MODEL_DIR = os.path.join('saved_models', 'direct')
POSITIONS = ('GK', 'DEF', 'MID', 'FWD')
API = 'https://fantasy.premierleague.com/api'
ELEMENT_TYPE = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}

# A player flagged like this is not going to play, whatever their form says.
UNAVAILABLE_STATUS = {'i', 'u', 's', 'n'}


def read_csv_tolerant(path: str, **kwargs) -> pd.DataFrame:
    for encoding in ('utf-8', 'latin-1'):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"could not decode {path}")


def fetch_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (fpl)'})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def load_models() -> dict:
    """The per-position model, scaler and feature list saved by train.py."""
    import joblib

    meta_path = os.path.join(MODEL_DIR, 'meta.json')
    if not os.path.exists(meta_path):
        raise SystemExit(
            f"{meta_path} not found.\n"
            f"Train first (python scripts/train.py), or copy saved_models/ back\n"
            f"from Drive if you trained on Colab -- the .joblib files are gitignored."
        )
    meta = json.load(open(meta_path, encoding='utf-8'))

    models = {}
    for position in POSITIONS:
        pos_dir = os.path.join(MODEL_DIR, position)
        best = meta.get(position, {}).get('best_model')
        model_path = os.path.join(pos_dir, f'{best}.joblib')
        scaler_path = os.path.join(pos_dir, 'scaler.joblib')
        feat_path = os.path.join(pos_dir, 'features.json')

        missing = [p for p in (model_path, scaler_path, feat_path) if not os.path.exists(p)]
        if missing:
            raise SystemExit(
                f"{position}: missing {', '.join(os.path.basename(m) for m in missing)}\n"
                f"saved_models/ holds only JSON in a fresh checkout; the .joblib\n"
                f"files are gitignored. Re-run training or restore them from Drive."
            )

        features = json.load(open(feat_path, encoding='utf-8'))
        if len(features) < 10:
            raise SystemExit(
                f"{position}: features.json lists {len(features)} feature(s). That is\n"
                f"the price-only bug this project exists to fix -- retrain before\n"
                f"predicting anything."
            )
        models[position] = {
            'model': joblib.load(model_path),
            'scaler': joblib.load(scaler_path),
            'features': features,
            'name': best,
        }
        print(f"  {position:<4} {best:<12} {len(features):>3} features")
    return models


# ---------------------------------------------------------------------------
# What is being predicted
# ---------------------------------------------------------------------------
def target_fixtures(season: str, gameweek: int | None, use_api: bool) -> tuple:
    """Fixtures for the gameweek to predict, as (gw, [(home_id, away_id), ...])."""
    bootstrap = None
    if use_api:
        try:
            bootstrap = fetch_json(f'{API}/bootstrap-static/')
        except Exception as exc:
            print(f"  FPL API unreachable ({type(exc).__name__}); using local fixtures")

    if bootstrap and gameweek is None:
        upcoming = [e for e in bootstrap['events'] if not e['finished']]
        gameweek = upcoming[0]['id'] if upcoming else bootstrap['events'][-1]['id']
        print(f"  next unfinished gameweek per the API: GW{gameweek}")

    if gameweek is None:
        raise SystemExit("could not determine the gameweek; pass --gameweek")

    fixtures = None
    if use_api:
        try:
            fixtures = [f for f in fetch_json(f'{API}/fixtures/?event={gameweek}')]
        except Exception:
            fixtures = None

    if not fixtures:
        path = os.path.join('data', season, 'fixtures.csv')
        if not os.path.exists(path):
            raise SystemExit(f"no fixtures from the API and {path} does not exist")
        local = read_csv_tolerant(path)
        event_col = 'event' if 'event' in local.columns else 'GW'
        fixtures = local[local[event_col] == gameweek].to_dict('records')

    # The kickoff time comes along because avail_days_since_last is measured
    # from it. Left unset it defaults to the epoch, which puts the fixture in
    # 1970 and makes "days since the last match" about -20,000 -- a value no
    # training row ever held, and enough on its own to send a prediction to
    # thirty-something points.
    pairs = [(int(f['team_h']), int(f['team_a']), f.get('kickoff_time'))
             for f in fixtures
             if f.get('team_h') is not None and f.get('team_a') is not None]
    if not pairs:
        raise SystemExit(f"no fixtures found for GW{gameweek}")

    if not any(p[2] for p in pairs):
        print("  no kickoff times available; estimating from the previous gameweek")
    return gameweek, pairs, bootstrap


def build_placeholder_rows(season: str, gameweek: int, pairs, bootstrap,
                           history: pd.DataFrame) -> pd.DataFrame:
    """One unplayed row per player whose team features in the gameweek.

    Keyed on the name the history uses, because every rolling feature groups by
    name. Players the history has never seen still get a row -- they simply
    arrive with empty form, which is the honest representation of a new signing.
    """
    teams_path = os.path.join('data', season, 'teams.csv')
    teams = read_csv_tolerant(teams_path)
    id_to_name = dict(zip(teams['id'], teams['name']))

    season_hist = history[history['season'] == season]
    # element ids are only stable within a season, which is exactly the scope
    # needed to turn a bootstrap id into the name the history uses.
    element_to_name = (season_hist.drop_duplicates('element', keep='last')
                       .set_index('element')['name'].to_dict())

    if bootstrap:
        players = pd.DataFrame([{
            'element': p['id'],
            'web_name': p['web_name'],
            'full_name': f"{p['first_name']} {p['second_name']}",
            'team_id': p['team'],
            'position': ELEMENT_TYPE.get(p['element_type']),
            'value': p['now_cost'],
            'status': p.get('status', 'a'),
            'chance': p.get('chance_of_playing_next_round'),
        } for p in bootstrap['elements']])
    else:
        raw = read_csv_tolerant(os.path.join('data', season, 'players_raw.csv'))
        players = pd.DataFrame({
            'element': raw['id'],
            'web_name': raw['web_name'],
            'full_name': raw['first_name'].astype(str) + ' ' + raw['second_name'].astype(str),
            'team_id': raw['team'],
            'position': raw['element_type'].map(ELEMENT_TYPE),
            'value': raw['now_cost'],
            'status': raw.get('status', 'a'),
            'chance': raw.get('chance_of_playing_next_round'),
        })

    opponent, at_home, kickoff = {}, {}, {}
    for home, away, when in pairs:
        opponent[home], at_home[home] = away, True
        opponent[away], at_home[away] = home, False
        kickoff[home] = kickoff[away] = when

    playing = players[players['team_id'].isin(opponent)].copy()
    playing['name'] = playing['element'].map(element_to_name)
    playing['name'] = playing['name'].fillna(playing['full_name'])

    playing['team'] = playing['team_id'].map(id_to_name)
    playing['opponent_team'] = playing['team_id'].map(opponent).map(id_to_name)
    playing['was_home'] = playing['team_id'].map(at_home)
    playing['season'] = season
    playing['GW'] = gameweek
    playing['total_points'] = np.nan          # the thing being predicted
    playing['is_prediction_row'] = True

    # When the fixture kicks off, which avail_days_since_last is measured from.
    # Falling back to a week after the most recent match in the data keeps that
    # feature in a plausible range; leaving it unset would put the fixture at
    # the epoch and hand the model a value 20,000 days out of distribution.
    playing['kickoff_time'] = playing['team_id'].map(kickoff)
    if playing['kickoff_time'].isna().any():
        latest = pd.to_datetime(history['kickoff_time'], errors='coerce',
                                utc=True, format='mixed').max()
        estimate = (latest + pd.Timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
        missing = int(playing['kickoff_time'].isna().sum())
        playing['kickoff_time'] = playing['kickoff_time'].fillna(estimate)
        print(f"  estimated kickoff for {missing} rows as {estimate}")

    # Every remaining column the feature functions touch has to exist. Match
    # stats are zero because this fixture has not happened; the features only
    # ever read them through a shift, so these values are never used for this
    # row -- they exist to keep dtypes and column sets intact. kickoff_time is
    # set above precisely because it is NOT one of those: it is read directly.
    for col in history.columns:
        if col not in playing.columns:
            playing[col] = 0

    print(f"  {len(playing):,} players across {len(pairs)} fixtures")
    unknown = playing['element'].map(element_to_name).isna().sum()
    if unknown:
        print(f"  {unknown} not in this season's history yet (new signings, no form)")
    return playing


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Run the notebook's own feature cells over history + placeholder rows."""
    print("\nbuilding features (final.ipynb cells 84..102)")
    ns = run_range(
        NOTEBOOK,
        first="# Create my_team_score and opponent_team_score columns based on was_home",
        last="# Apply rolling averages for player form",
        namespace={'pd': pd, 'np': np, 'all_seasons_data': frame},
        verbose=False,
    )
    out = ns['all_seasons_data_featured']
    print(f"  {out.shape[0]:,} rows x {out.shape[1]} columns")
    return out


def predict(featured: pd.DataFrame, models: dict) -> pd.DataFrame:
    rows = featured[featured['is_prediction_row'] == True].copy()  # noqa: E712
    if rows.empty:
        raise SystemExit("no prediction rows survived feature engineering")

    out = []
    for position in POSITIONS:
        spec = models[position]
        block = rows[rows['position'] == position].copy()
        if block.empty:
            continue

        missing = [f for f in spec['features'] if f not in block.columns]
        if missing:
            raise SystemExit(
                f"{position}: {len(missing)} of {len(spec['features'])} model features "
                f"are absent after feature engineering, e.g. {missing[:5]}.\n"
                f"The models were trained on a different feature set than this "
                f"pipeline now produces -- retrain."
            )

        X = block[spec['features']].replace([np.inf, -np.inf], np.nan).fillna(0)
        block['predicted_points'] = spec['model'].predict(spec['scaler'].transform(X))
        block['model'] = spec['name']
        out.append(block)

    predictions = pd.concat(out, ignore_index=True)
    predictions['value_m'] = predictions['value'] / 10.0
    predictions['points_per_million'] = (
        predictions['predicted_points'] / predictions['value_m'].replace(0, np.nan)
    )
    return predictions


def debug_row(predictions: pd.DataFrame, featured: pd.DataFrame,
              models: dict, needle: str) -> None:
    """Show which inputs are driving one player's number.

    A prediction row is built from history the player already has, so when it
    comes out wrong the cause is a feature holding a value the model never saw
    in training. This prints the largest deviations and the biggest
    contributions side by side.
    """
    match = predictions[predictions['name'].str.contains(needle, case=False, na=False)]
    if match.empty:
        print()
        print(f"--debug-row: nobody matching {needle!r} in the predictions")
        return
    row = match.iloc[0]
    position = row['position']
    spec = models[position]

    played = featured[(featured['is_prediction_row'] == False) &  # noqa: E712
                      (featured['position'] == position)]
    stats = played[spec['features']].astype(float)
    mean, std = stats.mean(), stats.std().replace(0, 1)

    values = pd.Series(row[spec['features']].values, index=spec['features']).astype(float)
    z = ((values - mean) / std).abs().sort_values(ascending=False)

    print()
    print("=" * 78)
    print(f"DEBUG  {row['name']} ({position})  predicted {row['predicted_points']:.2f}")
    print("=" * 78)
    print()
    print("inputs furthest from what the model saw in training:")
    for name in z.head(12).index:
        print(f"  |z|={z[name]:6.2f}  {name:<34} {values[name]:>10.2f}   "
              f"train mean {mean[name]:>8.2f}")

    model = spec['model']
    if hasattr(model, 'coef_'):
        scaled = spec['scaler'].transform(values.to_frame().T[spec['features']])[0]
        contrib = pd.Series(model.coef_ * scaled, index=spec['features'])
        contrib = contrib.sort_values(key=abs, ascending=False)
        print()
        print(f"largest contributions (intercept {model.intercept_:.2f}):")
        for name in contrib.head(12).index:
            print(f"  {contrib[name]:+8.3f}  {name}")


def check_distribution(predictions: pd.DataFrame, history: pd.DataFrame) -> None:
    """Are these numbers even the right shape?

    The first working version of this script cheerfully predicted 34.9 points
    for Haaland -- more than double the best return of most gameweeks -- because
    a bug reordered each player's history and the lag features were built from
    the wrong matches. Every individual step had succeeded, so nothing
    complained.

    Predicted points are a forecast of a distribution whose mean is about 1.3.
    A forecast averaging 8 is not optimistic, it is broken.
    """
    predicted = predictions['predicted_points']
    actual = history['total_points']

    print(f"\ndistribution check:")
    print(f"  predicted   mean {predicted.mean():6.2f}  max {predicted.max():6.2f}")
    print(f"  historical  mean {actual.mean():6.2f}  max {actual.max():6.2f}")

    problems = []
    if predicted.mean() > actual.mean() * 3:
        problems.append(
            f"mean predicted {predicted.mean():.2f} is more than 3x the historical "
            f"{actual.mean():.2f}")
    if predicted.max() > actual.max():
        problems.append(
            f"top prediction {predicted.max():.2f} exceeds the best score ever "
            f"recorded in the data ({actual.max():.0f})")
    if predicted.min() < -5:
        problems.append(f"lowest prediction {predicted.min():.2f} is implausibly negative")

    if problems:
        raise SystemExit(
            "predictions are not on a plausible scale:\n  - "
            + "\n  - ".join(problems)
            + "\n\nOne feature holding an out-of-distribution value is enough to do "
              "this on\nits own. Re-run with --debug-row on one of the affected "
              "players to see\nwhich input is furthest from the training "
              "distribution and how much of\nthe prediction it accounts for:\n\n"
              "    python scripts/predict_gameweek.py --debug-row Haaland\n\n"
              "The first occurrence was kickoff_time defaulting to the epoch, "
              "which made\navail_days_since_last -20,387 against a training mean "
              "of 9 and added 28\npoints to every prediction by itself."
        )


def check_coverage(predictions: pd.DataFrame, expected: int) -> None:
    """The failure the old pipeline shipped silently: 54 rows out of 811."""
    got, teams = len(predictions), predictions['team'].nunique()
    share = got / max(expected, 1)
    print(f"\ncoverage: {got:,}/{expected:,} players ({share:.0%}) across {teams} teams")
    if share < 0.80:
        raise SystemExit(
            f"only {share:.0%} of players in this gameweek got a prediction.\n"
            f"advanced_fpl_models.ipynb used to fail exactly this way -- 54 of 811,\n"
            f"one fixture's worth -- and reported nothing. Investigate before using\n"
            f"this output."
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--season', default=None, help='defaults to the latest in the data')
    ap.add_argument('--gameweek', type=int, default=None,
                    help='defaults to the next unfinished gameweek per the FPL API')
    ap.add_argument('--top', type=int, default=30)
    ap.add_argument('--no-api', action='store_true', help='use local files only')
    ap.add_argument('--out', default='predictions_next_gw.csv')
    ap.add_argument('--include-unavailable', action='store_true',
                    help='keep injured and suspended players in the output')
    ap.add_argument('--debug-row', metavar='NAME',
                    help='dump one player\'s model inputs against the training '
                         'distribution, for when a prediction looks wrong')
    args = ap.parse_args()

    if not os.path.exists(HISTORY):
        raise SystemExit(f"{HISTORY} not found. Run scripts/build_dataset.py --write first.")

    print("=" * 78)
    print("PREDICT NEXT GAMEWEEK")
    print("=" * 78)

    print("\nloading models")
    models = load_models()

    history = read_csv_tolerant(HISTORY)
    season = args.season or sorted(history['season'].unique())[-1]
    print(f"\nseason: {season}")

    gameweek, pairs, bootstrap = target_fixtures(season, args.gameweek, not args.no_api)
    print(f"target: GW{gameweek}")

    placeholders = build_placeholder_rows(season, gameweek, pairs, bootstrap, history)
    expected = len(placeholders)

    history = history.copy()
    history['is_prediction_row'] = False
    # A rerun should replace its own placeholder rows, not stack on them.
    history = history[~((history['season'] == season) & (history['GW'] == gameweek))]

    # game_number orders a player's season and the rolling features sort on it,
    # so the history's values (assigned from kickoff_time) must survive intact.
    # Recomputing it for the whole frame would silently reorder ten seasons
    # according to however the CSV happened to be laid out.
    next_number = (history[history['season'] == season]
                   .groupby('name')['game_number'].max())
    placeholders['game_number'] = (
        placeholders['name'].map(next_number).fillna(0).astype(int) + 1
    )

    frame = pd.concat([history, placeholders], ignore_index=True)

    featured = build_features(frame)
    predictions = predict(featured, models)

    if args.debug_row:
        debug_row(predictions, featured, models, args.debug_row)

    check_coverage(predictions, expected)
    check_distribution(predictions, history)

    if not args.include_unavailable:
        before = len(predictions)
        predictions = predictions[~predictions['status'].isin(UNAVAILABLE_STATUS)]
        dropped = before - len(predictions)
        if dropped:
            print(f"  dropped {dropped} injured/suspended/unavailable players "
                  f"(--include-unavailable keeps them)")

    predictions = predictions.sort_values('predicted_points', ascending=False)

    cols = ['name', 'team', 'position', 'opponent_team', 'was_home', 'value_m',
            'predicted_points', 'points_per_million', 'status', 'model']
    cols = [c for c in cols if c in predictions.columns]
    predictions[cols].to_csv(args.out, index=False)

    print(f"\n{'=' * 78}\nTOP {args.top} FOR GW{gameweek}\n{'=' * 78}")
    show = predictions[cols].head(args.top).copy()
    show['predicted_points'] = show['predicted_points'].round(2)
    show['points_per_million'] = show['points_per_million'].round(3)
    print(show.to_string(index=False))

    print(f"\nby position:")
    for position in POSITIONS:
        block = predictions[predictions['position'] == position]
        if block.empty:
            continue
        best = block.iloc[0]
        print(f"  {position:<4} {best['name'][:28]:<30} {best['predicted_points']:.2f} pts "
              f"({best['value_m']:.1f}m, {best['team']})")

    print(f"\nwrote {args.out} ({len(predictions):,} players)")
    print("\nThese are expected points, not certainties: test MAE is around one")
    print("point per player, so treat small gaps between players as noise.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
