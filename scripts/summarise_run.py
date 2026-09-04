"""Print a compact summary of a completed pipeline run.

Everything needed to judge whether the run is sound, small enough to paste
into a chat: dataset integrity, feature counts, the full model table, and the
train/test gaps that reveal overfitting.

Usage
-----
    python scripts/summarise_run.py          # in Colab: !python scripts/summarise_run.py
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd


def read_csv_tolerant(path, **kwargs):
    for encoding in ('utf-8', 'latin-1'):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"could not decode {path}")


def rule(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def dataset_section():
    rule("1. DATASET")
    path = 'all_seasons_data_final.csv'
    if not os.path.exists(path):
        print(f"  MISSING {path}")
        return
    cols = ['season', 'GW', 'total_points', 'has_fbref_defensive']
    df = read_csv_tolerant(path, usecols=lambda c: c in cols)
    summary = df.groupby('season').agg(
        rows=('total_points', 'size'),
        max_gw=('GW', 'max'),
        mean_pts=('total_points', 'mean'),
        pct_def=('has_fbref_defensive', 'mean'),
    )
    summary['mean_pts'] = summary['mean_pts'].round(3)
    summary['pct_def'] = (100 * summary['pct_def']).round(1)
    print(summary.to_string())
    print(f"  TOTAL {len(df):,} rows")


def features_section():
    rule("2. FEATURES")
    path = 'all_seasons_data_featured.csv'
    if not os.path.exists(path):
        print(f"  MISSING {path}")
        return
    head = read_csv_tolerant(path, nrows=1)
    n_rows = sum(1 for _ in open(path, encoding='utf-8', errors='replace')) - 1
    cols = list(head.columns)
    print(f"  {n_rows:,} rows x {len(cols)} columns")
    for label, test in (
        ('lagged  (_prev_)', lambda c: '_prev_' in c),
        ('rolling (_rolling_)', lambda c: '_rolling_' in c),
        ('opponent', lambda c: c.startswith('opponent_')),
        ('strength/advantage', lambda c: 'strength' in c or 'advantage' in c),
    ):
        print(f"    {label:<22} {sum(1 for c in cols if test(c)):>4}")


def models_section():
    rule("3. MODELS")
    if not os.path.exists('model_metrics.json'):
        print("  MISSING model_metrics.json -- training did not finish")
        return
    metrics = json.load(open('model_metrics.json'))

    rows = []
    for approach in ('direct', 'pca'):
        for position, res in metrics.get(approach, {}).items():
            for name, m in res['models'].items():
                rows.append({
                    'app': approach,
                    'pos': position,
                    'model': name,
                    'n_feat': res.get('n_features') or res.get('n_pca_components'),
                    'train': round(m['train_r2'], 4),
                    'val': round(m['val_r2'], 4),
                    'test': round(m['test_r2'], 4),
                    'mae': round(m['test_mae'], 4),
                })
    if not rows:
        print("  no model results recorded")
        return

    table = pd.DataFrame(rows)
    table['gap'] = (table['train'] - table['test']).round(4)
    print(table.to_string(index=False))

    rule("4. BEST PER POSITION (by test R2)")
    best = table.loc[table.groupby(['app', 'pos'])['test'].idxmax()]
    print(best.to_string(index=False))

    # A split recorded once is enough; they are identical across positions.
    for approach in ('direct', 'pca'):
        for res in metrics.get(approach, {}).values():
            split = res.get('split')
            if split:
                rule("5. SPLIT")
                print(f"  train {split['n_train']:>8,}  {split['train_seasons']}")
                print(f"  val   {split['n_val']:>8,}  {split['val_seasons']}")
                print(f"  test  {split['n_test']:>8,}  {split['test_seasons']}")
                return


def saved_section():
    rule("6. SAVED ARTIFACTS")
    base = 'saved_models'
    if not os.path.isdir(base):
        print(f"  MISSING {base}/")
        return
    for kind in ('direct', 'pca_models'):
        meta = os.path.join(base, kind, 'meta.json')
        if os.path.exists(meta):
            print(f"  {kind}/meta.json:")
            for pos, info in json.load(open(meta)).items():
                extra = info.get('features_count', info.get('n_pca_components'))
                print(f"    {pos:<4} best={info['best_model']:<12} "
                      f"r2={info['best_test_r2']:.4f}  n={extra}")
    for pos in ('GK', 'DEF', 'MID', 'FWD'):
        f = os.path.join(base, 'direct', pos, 'features.json')
        if os.path.exists(f):
            n = len(json.load(open(f)))
            flag = '  <-- SINGLE-FEATURE BUG IS BACK' if n < 10 else ''
            print(f"  direct/{pos}/features.json: {n} features{flag}")


def main():
    print("PIPELINE RUN SUMMARY")
    print(f"cwd: {os.getcwd()}")
    dataset_section()
    features_section()
    models_section()
    saved_section()
    print("\n" + "=" * 72)
    return 0


if __name__ == '__main__':
    sys.exit(main())
