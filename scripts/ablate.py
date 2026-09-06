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


def stub_boosters_if_absent() -> None:
    """Let the preprocessing cells import xgboost/lightgbm when they are absent.

    The cell range this script runs stops before any model is trained, but it
    passes through the notebook's import cell. This script only ever fits Ridge
    and ElasticNet, so a placeholder that satisfies the import is enough -- and
    it means the ablation runs on a laptop without a booster toolchain.

    Nothing here is ever fitted. If that changes, this must go.
    """
    for name in ('xgboost', 'lightgbm'):
        try:
            __import__(name)
            continue
        except ImportError:
            pass

        import types

        class _Unusable:
            def __init__(self, *_args, **_kwargs):
                raise RuntimeError(
                    f"{name} is not installed. scripts/ablate.py only fits "
                    f"linear models; use scripts/train.py on Colab for boosters."
                )

        module = types.ModuleType(name)
        if name == 'xgboost':
            module.XGBRegressor = _Unusable
        else:
            module.LGBMRegressor = _Unusable
        sys.modules[name] = module
        print(f"note: {name} not installed -- import placeholder in use "
              f"(this script fits linear models only)")

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
        only = [c for c in X.columns if c.startswith(prefix)]
        entry = {
            'n_test': int(test_mask.sum()),
            'n_dropped': len(only),
            'dropped': sorted(only),
            'models': {},
        }

        for name in model_names:
            with_it = fit_and_score(X[train_mask], y[train_mask],
                                    X[test_mask], y[test_mask], name)
            without = fit_and_score(X.loc[train_mask, keep], y[train_mask],
                                    X.loc[test_mask, keep], y[test_mask], name)

            # Marginal value understates a group whenever something else
            # carries the same signal, and with 220 correlated features that is
            # the norm. Fitting the group on its own separates "adds nothing"
            # from "adds nothing the rest does not already say".
            alone = fit_and_score(X.loc[train_mask, only], y[train_mask],
                                  X.loc[test_mask, only], y[test_mask], name)

            entry['models'][name] = {
                'with': with_it,
                'without': without,
                'alone': alone,
                'delta_r2': with_it['r2'] - without['r2'],
                'delta_mae': without['mae'] - with_it['mae'],   # positive = better
                'alone_r2': alone['r2'],
            }
            print(f"  {position:<4} {name:<11} "
                  f"full {with_it['r2']:.4f}  without {without['r2']:.4f}  "
                  f"marginal {with_it['r2'] - without['r2']:+.4f}  "
                  f"alone {alone['r2']:+.4f}")

        results[position] = entry
    return results


def compare_subset(ns: dict, prefixes, positions, model_names, out_path: str) -> int:
    """Train on a handful of feature families and see what the rest was worth.

    The per-group ablations say no single family is worth more than +0.005
    marginally, while minutes history alone reaches 0.326 against the full
    model's 0.339. That points at heavy redundancy, and the way to confirm it
    is to keep only the families that carry signal and check what the other
    two hundred columns were actually buying.
    """
    df = ns['df']
    position_features = ns['POSITION_FEATURES']
    prepare_position_data = ns['prepare_position_data']
    temporal_masks = ns['temporal_masks']
    chronological_order = ns['chronological_order']

    print("\n" + "=" * 78)
    print(f"SUBSET: keeping only {', '.join(p + '*' for p in prefixes)}")
    print("=" * 78)

    rows = []
    for position in positions:
        X, y, _available, pos_df = prepare_position_data(
            df, position, position_features[position])
        order = chronological_order(pos_df)
        X, y, pos_df = X.loc[order], y.loc[order], pos_df.loc[order]
        train_mask, _val, test_mask = (m.loc[order] for m in temporal_masks(pos_df))

        subset = [c for c in X.columns if c.startswith(tuple(prefixes))]
        if not subset:
            continue

        for name in model_names:
            full = fit_and_score(X[train_mask], y[train_mask],
                                 X[test_mask], y[test_mask], name)
            small = fit_and_score(X.loc[train_mask, subset], y[train_mask],
                                  X.loc[test_mask, subset], y[test_mask], name)
            rows.append({
                'pos': position, 'model': name,
                'full_n': full['n_features'], 'full_R2': round(full['r2'], 4),
                'subset_n': small['n_features'], 'subset_R2': round(small['r2'], 4),
                'cost': round(small['r2'] - full['r2'], 4),
                'retained': f"{100 * small['r2'] / full['r2']:.1f}%" if full['r2'] else '',
            })
            print(f"  {position:<4} {name:<11} full {full['n_features']:>3} feats "
                  f"{full['r2']:.4f}   subset {small['n_features']:>3} feats "
                  f"{small['r2']:.4f}   {small['r2'] - full['r2']:+.4f}")

    table = pd.DataFrame(rows)
    print()
    print(table.to_string(index=False))
    if len(table):
        print(f"\nmean cost of dropping everything else: "
              f"{table['cost'].mean():+.4f} R2")
        print(f"features: {table['full_n'].max()} -> {table['subset_n'].max()}")

    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump({'keep_only': list(prefixes), 'rows': rows}, fh, indent=2)
    print(f"\nwrote {out_path}")
    return 0


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
    ap.add_argument('--prefix', nargs='+', default=['avail_'],
                    help='drop every feature starting with this; repeatable, and '
                         'each group is measured separately against the full set '
                         'in a single preprocessing pass')
    ap.add_argument('--positions', nargs='+', default=list(POSITIONS))
    ap.add_argument('--models', nargs='+', default=['Ridge'],
                    choices=sorted(BUILDERS),
                    help='Ridge by default: it has a closed-form solution and '
                         'fits in seconds. ElasticNet is coordinate descent and '
                         'takes minutes per fit at this width, which multiplies '
                         'badly across groups x positions x three fits each.')
    ap.add_argument('--keep-only', nargs='+', default=None, metavar='PREFIX',
                    help='instead of ablating, train on the union of these '
                         'prefixes and compare against the full feature set')
    ap.add_argument('--out', default='ablation_metrics.json')
    ap.add_argument('--notebook', default=NOTEBOOK)
    args = ap.parse_args()

    if not os.path.exists(IN_FILE):
        raise SystemExit(f"{IN_FILE} not found. Run scripts/build_features.py first.")

    print("=" * 78)
    print(f"ABLATING {args.prefix}*  (same rows, same split, same seed)")
    print("=" * 78)

    # The notebook now trims to the compact set by default. Ablation has to see
    # every feature, or the groups it is asked to measure will already be gone.
    os.environ['FPL_FEATURE_SET'] = 'full'
    stub_boosters_if_absent()

    started = time.time()
    ns = run_range(
        args.notebook,
        first=f"all_seasons_data_featured = pd.read_csv('{IN_FILE}')",
        # Must reach prepare_position_data, which is defined after
        # POSITION_FEATURES. Stopping at the latter left the namespace
        # without it and only showed up when running standalone, since
        # train.py passes its own fully-populated namespace.
        last="# Prepare data for modeling",
        namespace={'pd': pd, 'np': np},
        verbose=False,
    )
    print(f"preprocessing done in {(time.time() - started) / 60:.1f} min\n")

    if args.keep_only:
        return compare_subset(ns, args.keep_only, args.positions, args.models, args.out)

    payload = {}
    summary = []
    for prefix in args.prefix:
        print(f"\n--- {prefix}* ---")
        results = ablate(ns, prefix, args.positions, args.models)
        if not results:
            continue
        print_report(results, prefix)
        payload[prefix] = results

        deltas = [m['delta_r2']
                  for entry in results.values()
                  for m in entry['models'].values()]
        alones = [m['alone_r2']
                  for entry in results.values()
                  for m in entry['models'].values()]
        summary.append({
            'group': f'{prefix}*',
            'features': max(e['n_dropped'] for e in results.values()),
            'marginal_R2': round(sum(deltas) / len(deltas), 4),
            'alone_R2': round(sum(alones) / len(alones), 4),
            'best_marginal': round(max(deltas), 4),
        })

    if len(summary) > 1:
        print("\n" + "=" * 78)
        print("WHAT EACH FEATURE GROUP IS WORTH")
        print("=" * 78)
        table = pd.DataFrame(summary).sort_values('alone_R2', ascending=False)
        print(table.to_string(index=False))
        print()
        print("marginal_R2  what the group adds on top of everything else.")
        print("alone_R2     what it scores by itself, with nothing else.")
        print()
        print("A group can be strong alone and worthless marginally: that means")
        print("its signal is already carried by something else. Read both against")
        print("the +0.11 to +0.14 the whole model gains over a rolling-5 average.")

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump({'summary': summary, 'results': payload}, fh, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
