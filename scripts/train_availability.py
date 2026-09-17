"""Train the availability half of the two-stage points model.

Why there are two models per position
-------------------------------------
A player's score for a gameweek is two questions stacked on top of each other:
will he be on the pitch at all, and how well will he do if he is. The single
regressor in train.py is asked both at once, and it answers by predicting
something in between -- a number that is neither a forecast of his return nor
a forecast of his chance of playing.

That blend is what puts a player who is not going to feature anywhere near the
top of a ranked list. The regressor sees good underlying numbers, shades them
down a little for patchy minutes, and still lands above a nailed-on starter
with a harder fixture. Splitting the question fixes the shape of the answer:

    E[points] = P(plays) x E[points | plays]

Measured against the single regressor on the 2024-25 and 2025-26 holdout
seasons, this is worth:

    2024-25   R2 0.3259 -> 0.3299   MAE 1.0107 -> 1.0031
    2025-26   R2 0.3430 -> 0.3456   MAE 0.9590 -> 0.9525

which is small, consistent, and in the same direction at every position. The
bigger effect is on the top of the ranking, where the decisions are made: over
the two holdout seasons the captain pick returned two points or fewer in 30.3%
of gameweeks rather than 35.5%.

This trains as a separate step rather than inside train.py because train.py
delegates to fpl_pipeline.ipynb's own cells, and the point of that arrangement
is that the notebook stays the definition of the direct models. The artifacts
land in the same per-position directory and predict_gameweek.py picks them up
when they are there, so an existing checkout keeps working unchanged.

Usage
-----
    python scripts/train_availability.py
    python scripts/train_availability.py --no-save
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

IN_FILE = 'all_seasons_data_featured.csv'
MODEL_DIR = os.path.join('saved_models', 'direct')
METRICS_OUT = 'availability_metrics.json'
POSITIONS = ('GK', 'DEF', 'MID', 'FWD')

# Matches the split in train.py: whole seasons, never shuffled, so a model is
# always scored on football that happened after everything it learned from.
TRAIN_SEASONS = ('2016-17', '2017-18', '2018-19', '2019-20', '2020-21',
                 '2021-22', '2022-23', '2023-24')
TEST_SEASONS = ('2024-25', '2025-26')

# The compact feature set from fpl_pipeline.ipynb, used only when a position
# has no features.json to read. Keep in step with COMPACT_PREFIXES there.
COMPACT_PREFIXES = ('minutes', 'avail_', 'total_points_', 'bps', 'value',
                    'ict_index', 'fx_')

# Current-gameweek columns: known only after the match, so never inputs.
EXCLUDE = {
    'total_points', 'name', 'element', 'fixture', 'kickoff_time', 'round', 'GW',
    'game_number', 'match_number', 'assists', 'bonus', 'bps', 'clean_sheets',
    'clearances_blocks_interceptions', 'creativity', 'goals_conceded',
    'goals_scored', 'ict_index', 'influence', 'minutes', 'own_goals',
    'penalties_missed', 'penalties_saved', 'recoveries', 'red_cards', 'saves',
    'selected', 'tackles', 'team_a_score', 'team_h_score', 'threat',
    'transfers_balance', 'transfers_in', 'transfers_out', 'yellow_cards',
    'defensive_contribution', 'result', 'my_team_score', 'opponent_team_score',
}


def preflight() -> None:
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        raise SystemExit("missing required package: lightgbm\n  pip install lightgbm")
    if not os.path.exists(IN_FILE):
        raise SystemExit(f"{IN_FILE} not found. Run scripts/build_features.py first.")


def features_for(position: str, frame: pd.DataFrame) -> list:
    """The feature list the direct model for this position was trained on.

    Read from features.json when training has already run, so both stages see
    identical inputs and a prediction cannot be assembled from two different
    views of the same player. Derived from the compact prefixes otherwise.
    """
    path = os.path.join(MODEL_DIR, position, 'features.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            saved = json.load(fh)
        usable = [f for f in saved if f in frame.columns]
        missing = len(saved) - len(usable)
        # A handful of absent columns is drift worth mentioning. A large block
        # of them means the file predates the current feature build and does
        # not describe this data at all, and training on what is left of a
        # stale list scores worse than deriving the set fresh -- measured at
        # -0.036 R2 for GK and -0.025 for DEF against the compact prefixes.
        if saved and missing / len(saved) > 0.05:
            print(f"  {position}: features.json is stale ({missing} of "
                  f"{len(saved)} features are not in {IN_FILE}); deriving the "
                  f"set from the compact prefixes instead")
        elif len(usable) >= 10:
            note = f" ({missing} no longer in the data)" if missing else ""
            print(f"  {position}: {len(usable)} features from features.json{note}")
            return usable
        else:
            print(f"  {position}: features.json lists {len(usable)} usable "
                  f"feature(s); falling back to the compact prefixes")

    cols = [c for c in frame.columns
            if c not in EXCLUDE
            and c.startswith(COMPACT_PREFIXES)
            and pd.api.types.is_numeric_dtype(frame[c])]
    if position == 'GK':
        # ICT is an outfield signal; the notebook leaves it out of GK_FEATURES.
        cols = [c for c in cols if not c.startswith('ict_index')]
    print(f"  {position}: {len(cols)} features from the compact prefixes")
    return sorted(cols)


def matrix(block: pd.DataFrame, feats: list) -> pd.DataFrame:
    return block[feats].replace([np.inf, -np.inf], np.nan).fillna(0)


def train_position(position: str, frame: pd.DataFrame, save: bool) -> dict | None:
    import joblib
    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
    from sklearn.preprocessing import StandardScaler

    block = frame[frame['position'] == position]
    train = block[block['season'].isin(TRAIN_SEASONS)]
    test = block[block['season'].isin(TEST_SEASONS)]
    if train.empty or test.empty:
        print(f"  {position}: no rows in one of the folds; skipped")
        return None

    feats = features_for(position, frame)
    X_train, X_test = matrix(train, feats), matrix(test, feats)
    y_train, y_test = train['total_points'].astype(float), test['total_points'].astype(float)
    played_train = (train['minutes'] > 0).astype(int)
    played_test = (test['minutes'] > 0).astype(int)

    # Fitted on the training fold alone, like every other scaler in this
    # project -- a scaler fitted on all of it leaks the test seasons' spread.
    scaler = StandardScaler().fit(X_train)
    Z_train, Z_test = scaler.transform(X_train), scaler.transform(X_test)

    params = dict(n_estimators=400, learning_rate=0.05, num_leaves=31,
                  min_child_samples=40, subsample=0.8, colsample_bytree=0.7,
                  verbose=-1, random_state=0)

    availability = lgb.LGBMClassifier(**params).fit(Z_train, played_train)
    p_play = availability.predict_proba(Z_test)[:, 1]

    # The conditional model only ever sees players who were on the pitch, so
    # it is free to describe a return rather than average one against the
    # chance of there being no return at all.
    appeared = (train['minutes'] > 0).values
    conditional = lgb.LGBMRegressor(**params).fit(Z_train[appeared], y_train[appeared])
    p_cond = conditional.predict(Z_test)

    combined = p_play * p_cond
    metrics = {
        'n_features': len(feats),
        'train_rows': int(len(train)),
        'test_rows': int(len(test)),
        'availability_auc': float(roc_auc_score(played_test, p_play)),
        'played_rate': float(played_test.mean()),
        'combined_test_r2': float(r2_score(y_test, combined)),
        'combined_test_mae': float(mean_absolute_error(y_test, combined)),
        'conditional_test_r2_on_players_who_played': float(
            r2_score(y_test[played_test == 1], p_cond[played_test == 1])),
    }

    print(f"  {position}: P(plays) AUC {metrics['availability_auc']:.3f}  "
          f"combined R2 {metrics['combined_test_r2']:.4f}  "
          f"MAE {metrics['combined_test_mae']:.4f}")

    if save:
        out_dir = os.path.join(MODEL_DIR, position)
        os.makedirs(out_dir, exist_ok=True)
        joblib.dump(availability, os.path.join(out_dir, 'availability.joblib'))
        joblib.dump(conditional, os.path.join(out_dir, 'conditional.joblib'))
        joblib.dump(scaler, os.path.join(out_dir, 'availability_scaler.joblib'))
        with open(os.path.join(out_dir, 'availability_features.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(feats, fh, indent=2)

    return metrics


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--no-save', action='store_true',
                    help='train and report, write nothing')
    args = ap.parse_args()

    preflight()

    print("=" * 78)
    print("TRAIN AVAILABILITY  (P(plays) and E[points | plays], per position)")
    print("=" * 78)
    print(f"input: {IN_FILE} ({os.path.getsize(IN_FILE) / 1e6:.0f} MB)")

    started = time.time()
    frame = pd.read_csv(IN_FILE, low_memory=False)
    frame = frame[frame['position'].isin(POSITIONS)]
    frame = frame.dropna(subset=['total_points', 'minutes'])
    print(f"{len(frame):,} rows  |  train {'/'.join(TRAIN_SEASONS[:1])}"
          f"..{TRAIN_SEASONS[-1]}  test {', '.join(TEST_SEASONS)}\n")

    metrics = {}
    for position in POSITIONS:
        result = train_position(position, frame, save=not args.no_save)
        if result:
            metrics[position] = result

    if not metrics:
        raise SystemExit("no position trained; check the season folds above")

    print(f"\nfinished in {(time.time() - started) / 60:.1f} min")

    with open(METRICS_OUT, 'w', encoding='utf-8') as fh:
        json.dump(metrics, fh, indent=2)
    print(f"wrote {METRICS_OUT}")

    if not args.no_save:
        print(f"availability models written under {MODEL_DIR}/<position>/")
        print("predict_gameweek.py uses them automatically when they are present.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
