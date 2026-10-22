"""Which feature families earn a place in the served two-stage model.

The predictions the app serves are P(plays) x E[points | plays] from
train_availability.py, so that is the model a new family has to improve.
Each family is added on top of the current per-position feature list and
scored on two later-season folds:

    validation  train 2016-17..2022-23, score 2023-24
    test        train 2016-17..2023-24, score 2024-25 + 2025-26

the same seasons fpl_pipeline.ipynb validates and tests on. FotMob reaches
back to 2019-20, so the validation fold trains fm_* on four seasons of data.
With FotMob starting in 2023-24 instead, the families were present in one
training season out of eight, "has the feature" came to mean "is 2023-24",
and every family scored worse (ablation run of 2026-10-22). A family is kept
for a position only when it improves R2 *and* MAE on *both* folds; anything
less is noise at this sample size.

Usage
-----
    python scripts/ablate_two_stage.py
    python scripts/ablate_two_stage.py --families fm_ def_ "fm_ def_"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

FOLDS = {
    'validation': ('2022-23', ['2023-24']),
    'test': ('2023-24', ['2024-25', '2025-26']),
}
FAMILIES = ['', 'xg_', 'def_', 'fm_', 'fm_ def_', 'fm_ def_ xg_']
POSITIONS = ('GK', 'DEF', 'MID', 'FWD')
OUT = 'ablation_two_stage.json'


def run(fold: str, family: str, train_from: str | None = None) -> dict:
    through, test = FOLDS[fold]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'metrics.json')
        cmd = [sys.executable, os.path.join('scripts', 'train_availability.py'), '--no-save',
               '--train-through', through, '--test', *test, '--metrics-out', path]
        if family:
            cmd += ['--extra', *family.split()]
        if train_from:
            cmd += ['--train-from', train_from]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--families', nargs='+', default=FAMILIES[1:])
    ap.add_argument('--train-from', default=None,
                    help='train every variant only on seasons from this one (e.g. 2019-20, '
                         'where FotMob starts), so presence of a family cannot stand in for era')
    ap.add_argument('--out', default=OUT)
    args = ap.parse_args()

    results = {}
    for family in [''] + args.families:
        label = family or 'baseline'
        results[label] = {}
        for fold in FOLDS:
            print(f"  {label:<14} {fold:<10}", flush=True)
            metrics = run(fold, family, args.train_from)
            results[label][fold] = {
                pos: {'r2': m['combined_test_r2'], 'mae': m['combined_test_mae'],
                      'n_features': m['n_features']}
                for pos, m in metrics.items()}

    base = results['baseline']
    verdict = {}
    print(f"\n{'family':<14} {'pos':<4} " + ' '.join(f'{f + " dR2":>15} {f + " dMAE":>16}' for f in FOLDS) + '  keep')
    for label, by_fold in results.items():
        if label == 'baseline':
            continue
        verdict[label] = {}
        for pos in POSITIONS:
            deltas = {fold: (by_fold[fold][pos]['r2'] - base[fold][pos]['r2'],
                             by_fold[fold][pos]['mae'] - base[fold][pos]['mae'])
                      for fold in FOLDS}
            keep = all(d_r2 > 0 and d_mae < 0 for d_r2, d_mae in deltas.values())
            verdict[label][pos] = {'keep': keep, **{
                fold: {'delta_r2': round(d[0], 5), 'delta_mae': round(d[1], 5)}
                for fold, d in deltas.items()}}
            cells = ' '.join(f'{d[0]:>+15.4f} {d[1]:>+16.4f}' for d in deltas.values())
            print(f"{label:<14} {pos:<4} {cells}  {'KEEP' if keep else '-'}")

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump({'folds': {k: {'train_through': v[0], 'test': v[1]} for k, v in FOLDS.items()},
                   'train_from': args.train_from,
                   'rule': 'keep only if R2 rises and MAE falls on both folds',
                   'results': results, 'verdict': verdict}, fh, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
