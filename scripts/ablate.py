"""Measure what a group of features is actually worth.

Adding features and watching the score go up proves nothing when the data
changed in the same run. That is exactly what happened with the availability
features: they landed alongside a complete 2025-26 season, so improvement and
better data were confounded and neither could be credited.

This holds everything else fixed and removes one group of columns. Same rows,
same split, same search, same seed -- the only difference is the features. The
delta is then attributable.

Only the linear models are used by default. They fit in seconds rather than
minutes, need no xgboost or lightgbm, and answer the question that is actually
being asked: does this information help at all? If a group is worth nothing to
a well-regularised linear model on 50,000 held-out rows, it is unlikely to be
carrying a booster.

Usage
-----
    python scripts/ablate.py --prefix avail_
    python scripts/ablate.py --prefix avail_ --models Ridge ElasticNet
    python scripts/ablate.py --prefix opponent_ --positions MID FWD
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range  # noqa: E402

NOTEBOOK = 'final.ipynb'
IN_FILE = 'all_seasons_data_featured.csv'
POSITIONS = ('GK', 'DEF', 'MID', 'FWD')

BUILDERS = {
    'Ridge': lambda: Ridge(alpha=1000),
    'ElasticNet': lambda: ElasticNet(alpha=0.1, l1_ratio=0.3, max_iter=10000),
}


def fit_and_score(X_train, y_train, X_test, y_test, model_name):
    """One fit. The scaler is fitted on the training fold only."""
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = BUILDERS[model_name]()
    model.fit(X_train_s, y_train)
    pred = model.predict(X_test_s)
    return {
        'r2': float(r2_score(y_test, pred)),
        'mae': float(mean_absolute_error(y_test, pred)),
        'n_features': int(X_train.shape[1]),
    }


def ablate(ns: dict, prefix: str, positions, model_names) -> dict:
    df = ns['df']
    position_features = ns['POSITION_FEATURES']
    prepare_position_data = ns['prepare_position_data']
    temporal_masks = ns['temporal_masks']
    chronological_order = ns['chronological_order']

    results = {}
    for position in positions:
        features = position_features[position]
        dropped = [f for f in features if f.startswith(prefix)]
        if not dropped:
            print(f"  {position}: no features match {prefix!r}, skipping")
            continue

        X, y, available, pos_df = prepare_position_data(df, position, features)
        order = chronological_order(pos_df)
        X, y, pos_df = X.loc[order], y.loc[order], pos_df.loc[order]
        train_mask, _val, test_mask = (m.loc[order] for m in temporal_masks(pos_df))

        keep = [c for c in X.columns if not c.startswith(prefix)]
        entry = {
            'n_test': int(test_mask.sum()),
            'n_dropped': len(X.columns) - len(keep),
            'dropped': sorted(c for c in X.columns if c.startswith(prefix)),
            'models': {},
        }

        for name in model_names:
            with_it = fit_and_score(X[train_mask], y[train_mask],
                                    X[test_mask], y[test_mask], name)
            without = fit_and_score(X.loc[train_mask, keep], y[train_mask],
                                    X.loc[test_mask, keep], y[test_mask], name)
            entry['models'][name] = {
                'with': with_it,
                'without': without,
                'delta_r2': with_it['r2'] - without['r2'],
                'delta_mae': without['mae'] - with_it['mae'],   # positive = better
            }
            print(f"  {position:<4} {name:<11} "
                  f"with {with_it['r2']:.4f}  without {without['r2']:.4f}  "
                  f"delta {with_it['r2'] - without['r2']:+.4f}")

        results[position] = entry
    return results


def print_report(results: dict, prefix: str) -> None:
    print("\n" + "=" * 78)
    print(f"ABLATION: what {prefix}* is worth")
    print("=" * 78)

    rows = []
    for position, entry in results.items():
        for name, m in entry['models'].items():
            rows.append({
                'pos': position, 'model': name,
                'dropped': entry['n_dropped'],
                'R2_with': round(m['with']['r2'], 4),
                'R2_without': round(m['without']['r2'], 4),
                'delta_R2': round(m['delta_r2'], 4),
                'delta_MAE': round(m['delta_mae'], 4),
                'n_test': entry['n_test'],
            })
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))

    deltas = [r['delta_R2'] for r in rows]
    if not deltas:
        return
    mean_delta = sum(deltas) / len(deltas)
    print(f"\nmean delta R2: {mean_delta:+.4f} across {len(deltas)} fits")
    if mean_delta > 0.005:
        print(f"{prefix}* is earning its place.")
    elif mean_delta > 0.0:
        print(f"{prefix}* helps, but only marginally -- worth keeping, not worth")
        print("building on.")
    else:
        print(f"{prefix}* is not helping. The gains seen when it was introduced")
        print("came from something else that changed at the same time.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--prefix', default='avail_',
                    help='drop every feature starting with this (default: avail_)')
    ap.add_argument('--positions', nargs='+', default=list(POSITIONS))
    ap.add_argument('--models', nargs='+', default=['Ridge', 'ElasticNet'],
                    choices=sorted(BUILDERS))
    ap.add_argument('--out', default='ablation_metrics.json')
    ap.add_argument('--notebook', default=NOTEBOOK)
    args = ap.parse_args()

    if not os.path.exists(IN_FILE):
        raise SystemExit(f"{IN_FILE} not found. Run scripts/build_features.py first.")

    print("=" * 78)
    print(f"ABLATING {args.prefix}*  (same rows, same split, same seed)")
    print("=" * 78)

    started = time.time()
    ns = run_range(
        args.notebook,
        first=f"all_seasons_data_featured = pd.read_csv('{IN_FILE}')",
        last="POSITION_FEATURES = {",
        namespace={'pd': pd, 'np': np},
        verbose=False,
    )
    print(f"preprocessing done in {(time.time() - started) / 60:.1f} min\n")

    results = ablate(ns, args.prefix, args.positions, args.models)
    print_report(results, args.prefix)

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump({'prefix': args.prefix, 'results': results}, fh, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
