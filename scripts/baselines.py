"""Score cheap baselines on exactly the test fold the models are scored on.

An R2 of 0.33 means nothing on its own. It only means something next to what a
three-line heuristic gets on the same rows -- and next to FPL's own expected
points, which the game publishes for free.

The comparison is only honest if the rows match, so the baselines are computed
from the same namespace the training cells ran in: the same featured frame,
the same game_number >= 5 filter, the same dropna, the same
prepare_position_data call, and the same season split. Nothing is recomputed.

Baselines
---------
train_mean     predict the training-fold mean for everyone. The floor: any
               model scoring at or below this has learned nothing.
prev_1         predict the player's points from their previous match.
rolling_3      predict their mean over the last 3 matches.
rolling_5      their mean over the last 5.
fpl_xp         FPL's own expected-points figure for that fixture, read from
               data/<season>/gws/merged_gw.csv. NOT a fair comparison, and
               reported separately for that reason -- see below.

Why fpl_xp is reported per season, and never scored against the models
----------------------------------------------------------------------
The xP column is not the same thing from one season to the next, so pooling it
across a multi-season test fold produces a number that means nothing.

    season     R2 all   R2 played   mean xP (played)   %DNP below 0.5
    2023-24    0.4568      0.2630              2.523            82.5%
    2024-25    0.4217      0.1999              2.299            82.1%
    2025-26   -0.0169     -0.6249              0.779            94.2%

Two different problems:

  2023-24 and 2024-25 were snapshotted at or after lineup announcement, so
  they already know who started. No genuine pre-match forecast separates
  played from did-not-play that cleanly -- late benchings are exactly what a
  forecast cannot see -- and more than half the apparent accuracy disappears
  once you condition on having appeared. Flagged UNFAIR.

  2025-26 is simply broken: players who appeared average 0.779 expected points
  against roughly 2.3 in prior seasons, and the R2 is negative, meaning it is
  worse than predicting the mean. Most likely the feed did not keep up with
  that season's scoring change. Flagged BROKEN via a calibration ratio of mean
  predicted to mean actual among players who appeared.

Either way the models, which have no team-news feature, cannot be judged
against it, so the verdict is taken against the fair baselines alone.

Usage
-----
    python scripts/baselines.py                 # runs preprocessing, then scores
    (train.py calls compute_baselines() directly with its own namespace)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range  # noqa: E402

NOTEBOOK = 'final.ipynb'
POSITIONS = ('GK', 'DEF', 'MID', 'FWD')
OUT_FILE = 'baseline_metrics.json'


def read_csv_tolerant(path: str, **kwargs) -> pd.DataFrame:
    for encoding in ('utf-8', 'latin-1'):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"could not decode {path}")


def load_fpl_xp(seasons) -> pd.DataFrame:
    """FPL's published expected points, keyed by (season, element, fixture).

    The notebook drops the xP column early on for cross-season consistency
    (it does not exist before 2020-21), so it is read back from source here.
    """
    frames = []
    for season in seasons:
        path = os.path.join('data', season, 'gws', 'merged_gw.csv')
        if not os.path.exists(path):
            continue
        head = read_csv_tolerant(path, nrows=0)
        if 'xP' not in head.columns:
            print(f"    {season}: no xP column, skipping")
            continue
        df = read_csv_tolerant(path, usecols=['element', 'fixture', 'xP'])
        df['season'] = season
        frames.append(df)
        print(f"    {season}: {len(df):,} xP rows")

    if not frames:
        return pd.DataFrame(columns=['season', 'element', 'fixture', 'xP'])
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=['season', 'element', 'fixture'], keep='first')


def _score(y_true, y_pred, fair: bool = True) -> dict:
    return {
        'r2': float(r2_score(y_true, y_pred)),
        'mae': float(mean_absolute_error(y_true, y_pred)),
        'rmse': float(np.sqrt(mean_squared_error(y_true, y_pred))),
        'n': int(len(y_true)),
        # False means the predictor saw something the models did not, so it
        # must not be used to judge them.
        'fair': fair,
    }


def diagnose_xp_leakage(seasons, verbose: bool = True) -> dict:
    """Quantify how much of xP's accuracy comes from knowing the lineup."""
    frames = []
    for season in seasons:
        path = os.path.join('data', season, 'gws', 'merged_gw.csv')
        if not os.path.exists(path):
            continue
        head = read_csv_tolerant(path, nrows=0)
        if not {'xP', 'minutes', 'total_points'} <= set(head.columns):
            continue
        frames.append(read_csv_tolerant(path, usecols=['xP', 'minutes', 'total_points']))
    if not frames:
        return {}

    df = pd.concat(frames, ignore_index=True).dropna(subset=['xP', 'total_points'])
    played = df['minutes'] > 0
    if played.sum() < 100 or (~played).sum() < 100:
        return {}

    out = {
        'mean_xp_did_not_play': float(df.loc[~played, 'xP'].mean()),
        'mean_xp_played': float(df.loc[played, 'xP'].mean()),
        'pct_dnp_under_half': float(100 * (df.loc[~played, 'xP'] < 0.5).mean()),
        'pct_played_under_half': float(100 * (df.loc[played, 'xP'] < 0.5).mean()),
        'r2_all_rows': float(r2_score(df['total_points'], df['xP'])),
        'r2_played_only': float(r2_score(df.loc[played, 'total_points'],
                                         df.loc[played, 'xP'])),
    }

    if verbose:
        print("\n  xP leakage check:")
        print(f"    mean xP, did not play : {out['mean_xp_did_not_play']:.3f} "
              f"({out['pct_dnp_under_half']:.1f}% below 0.5)")
        print(f"    mean xP, played       : {out['mean_xp_played']:.3f} "
              f"({out['pct_played_under_half']:.1f}% below 0.5)")
        print(f"    R2 all rows           : {out['r2_all_rows']:.4f}")
        print(f"    R2 players who played : {out['r2_played_only']:.4f}")
        print("    -> xP knows the starting XI; the models do not.")
    return out


def compute_baselines(ns: dict, verbose: bool = True) -> dict:
    """Score the baselines using the training run's own namespace."""
    df = ns['df']
    position_features = ns['POSITION_FEATURES']
    prepare_position_data = ns['prepare_position_data']
    temporal_masks = ns['temporal_masks']
    chronological_order = ns['chronological_order']
    test_seasons = ns['TEST_SEASONS']

    if verbose:
        print("\nloading FPL xP from source merged_gw files:")
    xp = load_fpl_xp(test_seasons)
    diagnose_xp_leakage(test_seasons, verbose=verbose)
    xp_lookup = xp.set_index(['season', 'element', 'fixture'])['xP'] if len(xp) else None

    results = {}
    for position in POSITIONS:
        X, y, _features, pos_df = prepare_position_data(
            df, position, position_features[position]
        )
        order = chronological_order(pos_df)
        y = y.loc[order]
        pos_df = pos_df.loc[order]
        train_mask, _val_mask, test_mask = (m.loc[order] for m in temporal_masks(pos_df))

        y_test = y[test_mask]
        test_rows = pos_df[test_mask]
        entry = {'n_test': int(len(y_test)), 'baselines': {}}

        # The floor: no signal at all.
        entry['baselines']['train_mean'] = _score(
            y_test, np.full(len(y_test), y[train_mask].mean())
        )

        for name, column in (
            ('prev_1', 'total_points_prev_1'),
            ('rolling_3', 'total_points_rolling_3'),
            ('rolling_5', 'total_points_rolling_5'),
        ):
            if column in test_rows.columns:
                entry['baselines'][name] = _score(
                    y_test, test_rows[column].fillna(0).to_numpy()
                )

        # FPL's own expected points.
        if xp_lookup is not None and {'season', 'element', 'fixture'} <= set(test_rows.columns):
            keys = pd.MultiIndex.from_arrays([
                test_rows['season'].astype(str),
                test_rows['element'],
                test_rows['fixture'],
            ])
            joined = xp_lookup.reindex(keys)
            covered = joined.notna().to_numpy()
            # Report xP per season, never pooled. The column is not the same
            # thing from one season to the next: 2024-25's was snapshotted
            # after lineups and scores an inflated 0.42, while 2025-26's is
            # simply broken -- players who appeared average 0.779 expected
            # points against roughly 2.3 in prior seasons, giving a negative
            # R2. Averaging a leaky season with a broken one produces a number
            # that means nothing at all.
            seasons_in_test = test_rows['season'].astype(str)
            for season in sorted(seasons_in_test.unique()):
                in_season = (seasons_in_test == season).to_numpy() & covered
                if in_season.sum() <= 100:
                    continue
                truth = y_test.to_numpy()[in_season]
                pred = joined.to_numpy()[in_season]
                score = _score(truth, pred, fair=False)
                score['coverage_pct'] = round(
                    100 * in_season.sum() / max((seasons_in_test == season).sum(), 1), 1
                )

                # A usable expected-points column should predict roughly the
                # right magnitude for players who took the field.
                appeared = test_rows['minutes'].to_numpy()[in_season] > 0 \
                    if 'minutes' in test_rows.columns else None
                if appeared is not None and appeared.sum() > 50:
                    ratio = pred[appeared].mean() / max(truth[appeared].mean(), 1e-9)
                    score['calibration_ratio'] = round(float(ratio), 3)
                    score['usable'] = bool(0.5 <= ratio <= 2.0 and score['r2'] > 0)
                else:
                    score['usable'] = score['r2'] > 0

                entry['baselines'][f'fpl_xp[{season}]'] = score

            if verbose and not covered.any():
                print(f"    {position}: no xP rows matched, skipping")

        results[position] = entry

    return results


def print_table(baselines: dict, model_metrics: dict | None = None) -> None:
    print("\n" + "=" * 78)
    print("BASELINES vs MODELS  (test fold: 2024-25 + 2025-26)")
    print("=" * 78)

    rows = []
    for position, entry in baselines.items():
        for name, s in entry['baselines'].items():
            if s.get('fair', True):
                kind = 'baseline'
            elif s.get('usable', True):
                kind = 'UNFAIR'
            else:
                kind = 'BROKEN'
            rows.append({
                'pos': position, 'method': name, 'kind': kind,
                'r2': round(s['r2'], 4), 'mae': round(s['mae'], 4),
                'n': s['n'], 'calib': s.get('calibration_ratio', ''),
            })

    if model_metrics:
        for approach in ('direct', 'pca'):
            for position, res in model_metrics.get(approach, {}).items():
                if not res.get('models'):
                    continue
                best = max(res['models'].items(), key=lambda kv: kv[1]['test_r2'])
                rows.append({
                    'pos': position, 'method': f"{approach}:{best[0]}", 'kind': 'MODEL',
                    'r2': round(best[1]['test_r2'], 4),
                    'mae': round(best[1]['test_mae'], 4),
                    'n': res.get('split', {}).get('n_test', 0),
                })

    table = pd.DataFrame(rows).sort_values(['pos', 'r2'], ascending=[True, False])
    print(table.to_string(index=False))

    if any(r['kind'] == 'UNFAIR' for r in rows):
        print("\n  UNFAIR = the predictor saw something the models did not.")
        print("  fpl_xp was snapshotted at or after lineup announcement, so it")
        print("  knows who started; the models have no team-news feature.")
    if any(r['kind'] == 'BROKEN' for r in rows):
        print()
        print("  BROKEN = that season's xP column is unusable. 'calib' is mean")
        print("  predicted over mean actual for players who appeared; far from 1.0")
        print("  means miscalibrated, not merely inaccurate.")
    if any(r['kind'] in ('UNFAIR', 'BROKEN') for r in rows):
        print("  Both are excluded from the verdict below.")

    # The question the whole exercise turns on.
    if model_metrics:
        print("\n" + "-" * 78)
        print("Does the model beat the best FAIR baseline?")
        print("-" * 78)
        for position, entry in baselines.items():
            fair = {k: v for k, v in entry['baselines'].items() if v.get('fair', True)}
            if not fair:
                continue
            best_base = max(fair.items(), key=lambda kv: kv[1]['r2'])
            model_r2 = -99.0
            model_name = 'none'
            for approach in ('direct', 'pca'):
                res = model_metrics.get(approach, {}).get(position, {})
                for name, m in res.get('models', {}).items():
                    if m['test_r2'] > model_r2:
                        model_r2, model_name = m['test_r2'], f"{approach}:{name}"
            margin = model_r2 - best_base[1]['r2']
            verdict = 'YES' if margin > 0 else 'NO -- the model adds nothing'
            print(f"  {position:<4} model {model_name:<20} {model_r2:.4f}   "
                  f"best baseline {best_base[0]:<12} {best_base[1]['r2']:.4f}   "
                  f"margin {margin:+.4f}  {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--notebook', default=NOTEBOOK)
    args = ap.parse_args()

    if not os.path.exists('all_seasons_data_featured.csv'):
        raise SystemExit("all_seasons_data_featured.csv not found. "
                         "Run scripts/build_features.py first.")

    print("=" * 78)
    print("BASELINES  (re-running preprocessing to reproduce the exact test rows)")
    print("=" * 78)

    # Stop at the feature-group cell: everything the baselines need exists by
    # then, and no model has to be trained.
    ns = run_range(
        args.notebook,
        first="all_seasons_data_featured = pd.read_csv('all_seasons_data_featured.csv')",
        # Must reach prepare_position_data, which is defined after
        # POSITION_FEATURES. Stopping at the latter left the namespace
        # without it and only showed up when running standalone, since
        # train.py passes its own fully-populated namespace.
        last="# Prepare data for modeling",
        namespace={'pd': pd, 'np': np},
    )

    baselines = compute_baselines(ns)

    model_metrics = None
    if os.path.exists('model_metrics.json'):
        model_metrics = json.load(open('model_metrics.json'))

    print_table(baselines, model_metrics)

    with open(OUT_FILE, 'w', encoding='utf-8') as fh:
        json.dump(baselines, fh, indent=2)
    print(f"\nwrote {OUT_FILE}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
