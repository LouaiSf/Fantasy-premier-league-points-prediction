"""Train the position models with the fixed pipeline, and save them.

Runs final.ipynb's preprocessing and training cells (103..150) plus its
model-saving cell. Everything the fixes changed applies here by construction:

  * the direct models train on the featured frame, not the raw one, and
    prepare_position_data raises rather than quietly dropping features
  * splits are by whole season -- train 2016-17..2022-23, validation 2023-24,
    test 2024-25 + 2025-26
  * scaler, correlation filter and PCA basis are all fitted on the training
    fold only
  * hyperparameter search uses TimeSeriesSplit rather than shuffled KFold

Needs xgboost and lightgbm, which is the other reason this belongs on Colab.

Usage
-----
    python scripts/train.py
    python scripts/train.py --no-save      # train and report, write nothing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range  # noqa: E402

NOTEBOOK = 'final.ipynb'
IN_FILE = 'all_seasons_data_featured.csv'
METRICS_OUT = 'model_metrics.json'


def preflight() -> None:
    missing = []
    for module in ('xgboost', 'lightgbm'):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise SystemExit(
            f"missing required package(s): {', '.join(missing)}\n"
            f"  pip install {' '.join(missing)}"
        )
    if not os.path.exists(IN_FILE):
        raise SystemExit(
            f"{IN_FILE} not found. Run scripts/build_features.py first."
        )


def collect_metrics(ns: dict) -> dict:
    """Pull the per-position results out of the notebook namespace."""
    out: dict = {'direct': {}, 'pca': {}}

    for position, res in ns.get('all_results', {}).items():
        out['direct'][position] = {
            'n_features': len(res['features']),
            'split': res.get('split'),
            'models': {
                name: {
                    'train_r2': m['train_metrics']['r2'],
                    'val_r2': m['val_metrics']['r2'],
                    'test_r2': m['test_metrics']['r2'],
                    'test_mae': m['test_metrics']['mae'],
                    'test_rmse': m['test_metrics']['rmse'],
                    'best_params': m.get('best_params'),
                }
                for name, m in res['models'].items()
            },
        }

    for position, res in ns.get('pca_model_results', {}).items():
        out['pca'][position] = {
            'n_original_features': res['original_features'],
            'n_after_correlation': res['features_after_corr'],
            'n_pca_components': res['n_pca_components'],
            'split': res.get('split'),
            'models': {
                name: {
                    'train_r2': m['train_metrics']['r2'],
                    'val_r2': m['val_metrics']['r2'],
                    'test_r2': m['test_metrics']['r2'],
                    'test_mae': m['test_metrics']['mae'],
                    'test_rmse': m['test_metrics']['rmse'],
                    'best_params': m.get('best_params'),
                }
                for name, m in res['models'].items()
            },
        }
    return out


def report_importances(ns: dict, top: int = 15, out: str = 'feature_importance.json') -> None:
    """Which of the 220 features the best model per position actually uses.

    Two hundred features and no idea which ones matter makes it impossible to
    tell an improvement from noise, or to know what to build next. Tree models
    expose this directly; linear models expose the size of their coefficients,
    which is comparable across features only because everything was scaled.

    Grouped by prefix as well as listed individually, so a family of features
    that is collectively doing nothing is visible even when no single member
    looks obviously useless.
    """
    all_results = ns.get('all_results', {})
    if not all_results:
        return

    print("\n" + "=" * 78)
    print("FEATURE IMPORTANCE  (best model per position)")
    print("=" * 78)

    payload = {}
    for position, res in all_results.items():
        if not res.get('models'):
            continue
        name, best = max(res['models'].items(), key=lambda kv: kv[1]['test_metrics']['r2'])
        model = best['model']
        features = res['features']

        if hasattr(model, 'feature_importances_'):
            weight = np.asarray(model.feature_importances_, dtype=float)
            kind = 'gain'
        elif hasattr(model, 'coef_'):
            weight = np.abs(np.asarray(model.coef_, dtype=float).ravel())
            kind = '|coef|'
        else:
            continue
        if len(weight) != len(features):
            continue

        total = weight.sum() or 1.0
        share = weight / total
        ranked = sorted(zip(features, share), key=lambda kv: kv[1], reverse=True)

        # Group by the family a feature belongs to.
        groups: dict = {}
        for feature, value in zip(features, share):
            base = feature.split('_prev')[0].split('_rolling')[0]
            if feature.startswith('avail_'):
                base = 'avail_*'
            groups[base] = groups.get(base, 0.0) + float(value)
        top_groups = sorted(groups.items(), key=lambda kv: kv[1], reverse=True)[:8]

        payload[position] = {
            'model': name,
            'measure': kind,
            'top_features': [{'feature': f, 'share': round(float(v), 5)}
                             for f, v in ranked[:top]],
            'by_group': [{'group': g, 'share': round(v, 5)} for g, v in top_groups],
            'availability_share': round(float(groups.get('avail_*', 0.0)), 5),
        }

        print(f"\n{position}  ({name}, {kind})")
        for feature, value in ranked[:top]:
            print(f"    {value * 100:5.2f}%  {feature}")
        print(f"    availability features together: "
              f"{groups.get('avail_*', 0.0) * 100:.2f}%")

    if payload:
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nwrote {out}")


def print_summary(metrics: dict) -> None:
    print("\n" + "=" * 78)
    print("TEST-FOLD RESULTS  (2024-25 + 2025-26, never seen during training)")
    print("=" * 78)

    for approach in ('direct', 'pca'):
        block = metrics.get(approach, {})
        if not block:
            continue
        print(f"\n{approach.upper()}")
        header = f"  {'pos':<5} {'features':>9} {'best model':<12} {'test R2':>8} {'test MAE':>9}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for position, res in block.items():
            if not res['models']:
                print(f"  {position:<5} {'-':>9} {'(none trained)':<12}")
                continue
            best = max(res['models'].items(), key=lambda kv: kv[1]['test_r2'])
            n_feat = res.get('n_features') or res.get('n_pca_components')
            print(f"  {position:<5} {n_feat:>9} {best[0]:<12} "
                  f"{best[1]['test_r2']:>8.4f} {best[1]['test_mae']:>9.4f}")

    print("\nThese are season-holdout numbers. They are not comparable to the")
    print("figures in the original notebook, which came from a shuffled split.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--notebook', default=NOTEBOOK)
    ap.add_argument('--with-pca', action='store_true',
                    help='also train the PCA branch (off by default -- it loses '
                         'to the direct models at every position)')
    ap.add_argument('--no-save', action='store_true',
                    help='skip the model-saving cell')
    args = ap.parse_args()

    preflight()

    print("=" * 78)
    print("TRAINING  (final.ipynb cells 103..150)")
    print("=" * 78)
    print(f"input: {IN_FILE} ({os.path.getsize(IN_FILE) / 1e6:.0f} MB)\n")

    started = time.time()
    extra = [] if args.no_save else ["SAVE_DIR = 'saved_models'"]
    ns = run_range(
        args.notebook,
        first=f"all_seasons_data_featured = pd.read_csv('{IN_FILE}')",
        # The PCA branch is off by default. It only ever looked better than
        # "direct" because direct was the price-only bug: with real features it
        # loses at every position (-0.010 GK, -0.010 DEF, -0.017 MID, -0.017
        # FWD) while costing about half the training time. It is lossy
        # compression of features the models handle better raw.
        last=("# Train Models with PCA-Reduced Features" if args.with_pca
              else "# Display best model for each position"),
        namespace={'pd': pd, 'np': np},
        extra_cells=extra,
    )
    print(f"\n[train] finished in {(time.time() - started) / 60:.1f} min")

    metrics = collect_metrics(ns)
    print_summary(metrics)
    report_importances(ns)

    with open(METRICS_OUT, 'w', encoding='utf-8') as fh:
        json.dump(metrics, fh, indent=2, default=float)
    print(f"\nwrote {METRICS_OUT}")

    # Baselines, scored on the same namespace so the test rows are identical.
    # An R2 is only meaningful next to what a heuristic gets on the same rows.
    try:
        from baselines import compute_baselines, print_table
        baselines = compute_baselines(ns)
        print_table(baselines, metrics)
        with open('baseline_metrics.json', 'w', encoding='utf-8') as fh:
            json.dump(baselines, fh, indent=2)
        print("\nwrote baseline_metrics.json")
    except Exception as exc:  # never let this cost you a finished training run
        print(f"\nWARNING: baseline comparison failed ({type(exc).__name__}: {exc})")
        print("The models and metrics above are unaffected; run "
              "scripts/baselines.py separately to retry.")

    if not args.no_save:
        print("models and artifacts written under saved_models/")
        # The bug this whole branch exists to fix showed up here: features.json
        # held a single entry. Fail loudly if that ever comes back.
        for position in ('GK', 'DEF', 'MID', 'FWD'):
            path = os.path.join('saved_models', 'direct', position, 'features.json')
            if os.path.exists(path):
                with open(path, encoding='utf-8') as fh:
                    n = len(json.load(fh))
                if n < 10:
                    raise SystemExit(
                        f"saved_models/direct/{position}/features.json has only "
                        f"{n} feature(s) -- the single-feature bug is back."
                    )
                print(f"  direct/{position}: {n} features saved")
    return 0


if __name__ == '__main__':
    sys.exit(main())
