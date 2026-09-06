"""Judge the model by the team it picks, not by R2.

Every other number in this project is a regression metric. But FPL is a
selection problem: nobody cares whether a player's score was predicted to
within a point, they care whether the eleven you picked outscored the eleven
you would have picked otherwise. Those two things come apart -- a model can
have the better R2 and still pick worse teams, because R2 rewards being close
on the 60% of players who score two points and selection only rewards being
right at the top of the ranking.

So this picks a real XI under real constraints and adds up what it actually
scored.

Method
------
For every gameweek in the test seasons, solve the same integer program twice,
changing only what it maximises:

    model       the saved per-position models' predicted points
    rolling_5   the player's mean over their previous five matches
    perfect     what they actually went on to score  (the ceiling)

Constraints are identical in all three cases -- budget, formation, and at most
three players from one club -- so the difference in points scored is
attributable to the ranking and nothing else.

`perfect` is not a competitor. It is there because a gap of a few points
between model and rolling_5 means something quite different depending on
whether the ceiling is 90 or 130.

Usage
-----
    python scripts/validate_selection.py
    python scripts/validate_selection.py --budget 83 --seasons 2025-26
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range, stub_boosters_if_absent  # noqa: E402

NOTEBOOK = 'final.ipynb'
IN_FILE = 'all_seasons_data_featured.csv'
MODEL_DIR = os.path.join('saved_models', 'direct')
POSITIONS = ('GK', 'DEF', 'MID', 'FWD')

# A legal FPL XI: one keeper, at least three at the back, at least one up top.
FORMATION = {'GK': (1, 1), 'DEF': (3, 5), 'MID': (2, 5), 'FWD': (1, 3)}
SQUAD_SIZE = 11
MAX_PER_CLUB = 3


def load_models() -> dict:
    import joblib

    meta_path = os.path.join(MODEL_DIR, 'meta.json')
    if not os.path.exists(meta_path):
        raise SystemExit(f"{meta_path} not found -- train first.")
    meta = json.load(open(meta_path, encoding='utf-8'))

    models = {}
    for position in POSITIONS:
        pos_dir = os.path.join(MODEL_DIR, position)
        best = meta.get(position, {}).get('best_model')
        paths = {
            'model': os.path.join(pos_dir, f'{best}.joblib'),
            'scaler': os.path.join(pos_dir, 'scaler.joblib'),
        }
        if not all(os.path.exists(p) for p in paths.values()):
            raise SystemExit(f"{position}: .joblib files missing under {pos_dir}")
        models[position] = {
            'model': joblib.load(paths['model']),
            'scaler': joblib.load(paths['scaler']),
            'features': json.load(open(os.path.join(pos_dir, 'features.json'),
                                       encoding='utf-8')),
            'name': best,
        }
    return models


def score_test_rows(ns: dict, models: dict) -> pd.DataFrame:
    """Model predictions for every test-fold row, with what actually happened."""
    df = ns['df']
    frames = []
    for position in POSITIONS:
        X, y, _f, pos_df = ns['prepare_position_data'](
            df, position, ns['POSITION_FEATURES'][position])
        order = ns['chronological_order'](pos_df)
        X, y, pos_df = X.loc[order], y.loc[order], pos_df.loc[order]
        _tr, _v, test = (m.loc[order] for m in ns['temporal_masks'](pos_df))

        spec = models[position]
        Xt = X.loc[test, spec['features']].replace([np.inf, -np.inf], np.nan).fillna(0)
        block = pos_df[test].copy()
        block['predicted'] = spec['model'].predict(spec['scaler'].transform(Xt))
        block['actual'] = y[test].to_numpy()
        block['position'] = position
        frames.append(block)

    out = pd.concat(frames, ignore_index=True)
    # rolling_5 is the heuristic the model has to beat, and it is already a
    # column: a strictly-past mean, same as every other feature.
    out['rolling_5'] = out.get('total_points_rolling_5', pd.Series(0, index=out.index))
    out['rolling_5'] = out['rolling_5'].fillna(0)
    return out


def pick_xi(pool: pd.DataFrame, objective: str, budget_tenths: int):
    """Best legal XI under `objective`. Returns (indices, None) or (None, reason)."""
    import pulp

    pool = pool[pool['value'] > 0]
    if len(pool) < SQUAD_SIZE:
        return None, 'not enough priced players'

    problem = pulp.LpProblem('xi', pulp.LpMaximize)
    pick = {i: pulp.LpVariable(f'p{i}', cat='Binary') for i in pool.index}

    problem += pulp.lpSum(pool.loc[i, objective] * pick[i] for i in pool.index)
    problem += pulp.lpSum(pick.values()) == SQUAD_SIZE
    problem += pulp.lpSum(pool.loc[i, 'value'] * pick[i] for i in pool.index) <= budget_tenths

    for position, (low, high) in FORMATION.items():
        members = [i for i in pool.index if pool.loc[i, 'position'] == position]
        if len(members) < low:
            return None, f'only {len(members)} {position} available'
        problem += pulp.lpSum(pick[i] for i in members) >= low
        problem += pulp.lpSum(pick[i] for i in members) <= high

    for club in pool['team'].unique():
        members = [i for i in pool.index if pool.loc[i, 'team'] == club]
        problem += pulp.lpSum(pick[i] for i in members) <= MAX_PER_CLUB

    problem.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[problem.status] != 'Optimal':
        return None, f'solver: {pulp.LpStatus[problem.status]}'
    return [i for i in pool.index if pick[i].value() > 0.5], None


def run(scored: pd.DataFrame, budget: float, seasons, verbose: bool) -> pd.DataFrame:
    budget_tenths = int(round(budget * 10))
    strategies = ['predicted', 'rolling_5', 'actual']
    rows = []

    weeks = (scored[scored['season'].isin(seasons)]
             .groupby(['season', 'GW']).size().reset_index()[['season', 'GW']])
    print(f"\nsolving {len(weeks)} gameweeks x 3 objectives "
          f"(budget {budget:.1f}m, max {MAX_PER_CLUB}/club)")

    for _, week in weeks.iterrows():
        pool = scored[(scored['season'] == week['season']) &
                      (scored['GW'] == week['GW'])].copy()
        # One row per player: double gameweeks would otherwise let the same
        # player be picked twice.
        pool = pool.sort_values('actual', ascending=False).drop_duplicates('name')
        pool = pool.reset_index(drop=True)

        entry = {'season': week['season'], 'GW': int(week['GW']), 'pool': len(pool)}
        ok = True
        for strategy in strategies:
            picks, reason = pick_xi(pool, strategy, budget_tenths)
            if picks is None:
                if verbose:
                    print(f"  {week['season']} GW{week['GW']}: skipped ({reason})")
                ok = False
                break
            entry[strategy] = float(pool.loc[picks, 'actual'].sum())
            entry[f'{strategy}_cost'] = float(pool.loc[picks, 'value'].sum()) / 10
        if ok:
            rows.append(entry)

    return pd.DataFrame(rows)


def report(results: pd.DataFrame, budget: float) -> None:
    if results.empty:
        raise SystemExit("no gameweeks solved")

    print("\n" + "=" * 78)
    print("POINTS ACTUALLY SCORED BY THE PICKED XI")
    print("=" * 78)

    n = len(results)
    model, rolling, perfect = (results['predicted'].sum(),
                               results['rolling_5'].sum(),
                               results['actual'].sum())

    print(f"\n{n} gameweeks, budget {budget:.1f}m\n")
    print(f"  {'strategy':<24}{'total':>9}{'per GW':>9}{'vs rolling_5':>15}")
    print("  " + "-" * 55)
    print(f"  {'model predictions':<24}{model:>9.0f}{model / n:>9.1f}"
          f"{model - rolling:>+15.0f}")
    print(f"  {'rolling_5 average':<24}{rolling:>9.0f}{rolling / n:>9.1f}{'':>15}")
    print(f"  {'perfect foresight':<24}{perfect:>9.0f}{perfect / n:>9.1f}"
          f"{perfect - rolling:>+15.0f}")

    beat = (results['predicted'] > results['rolling_5']).sum()
    tied = (results['predicted'] == results['rolling_5']).sum()
    print(f"\n  model beat rolling_5 in {beat}/{n} gameweeks "
          f"({beat / n:.0%}), tied {tied}")

    gap = perfect - rolling
    captured = (model - rolling) / gap if gap else 0
    print(f"  of the {gap:.0f} points between rolling_5 and perfect foresight, "
          f"the model captured {captured:.1%}")

    diff = results['predicted'] - results['rolling_5']
    print(f"\n  per-gameweek difference: mean {diff.mean():+.2f}, "
          f"median {diff.median():+.1f}, "
          f"best {diff.max():+.0f}, worst {diff.min():+.0f}")

    # A difference this noisy needs a sense of whether it is real.
    if diff.std() > 0:
        t = diff.mean() / (diff.std() / np.sqrt(n))
        print(f"  paired t over gameweeks: t={t:.2f} "
              f"({'unlikely to be chance' if abs(t) > 2 else 'within noise'})")

    print("\nby season:")
    for season, block in results.groupby('season'):
        m, r, p = block['predicted'].mean(), block['rolling_5'].mean(), block['actual'].mean()
        print(f"  {season}  {len(block):>2} GWs   model {m:>5.1f}   "
              f"rolling_5 {r:>5.1f}   perfect {p:>5.1f}   diff {m - r:>+5.1f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--budget', type=float, default=83.0,
                    help='XI budget in millions (default 83, a realistic starting XI '
                         'once a bench is paid for out of the 100m squad limit)')
    ap.add_argument('--seasons', nargs='+', default=None,
                    help='defaults to every test season')
    ap.add_argument('--out', default='selection_metrics.json')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(IN_FILE):
        raise SystemExit(f"{IN_FILE} not found. Run scripts/build_features.py first.")

    print("=" * 78)
    print("SELECTION VALIDATION")
    print("=" * 78)

    # The preprocessing range passes through the notebook's booster imports,
    # even though nothing is trained here.
    stub_boosters_if_absent()

    models = load_models()
    print("models: " + ", ".join(f"{p}={models[p]['name']}" for p in POSITIONS))

    ns = run_range(
        NOTEBOOK,
        first=f"all_seasons_data_featured = pd.read_csv('{IN_FILE}')",
        last="# Prepare data for modeling",
        namespace={'pd': pd, 'np': np},
        verbose=False,
    )

    scored = score_test_rows(ns, models)
    seasons = args.seasons or sorted(scored['season'].unique())
    print(f"test rows: {len(scored):,} across {seasons}")

    results = run(scored, args.budget, seasons, args.verbose)
    report(results, args.budget)

    results.to_json(args.out, orient='records', indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
