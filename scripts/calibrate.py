"""Per-position calibration for the conditional half of the points model.

Why this step exists
--------------------
train_availability.py fits E[points | plays] separately for each position, and
each of those four models is asked to explain a different amount of noise. A
goalkeeper's return is nearly deterministic once he starts -- a clean sheet and
a handful of saves -- while a forward's turns on whether a rare event happens.
A squared-error fit answers an unpredictable target by shrinking toward the
mean, so the four models do not shrink by the same amount.

That does not show up in a per-position R2 or MAE, because each is scored only
against its own position. It shows up the moment the optimiser compares a
goalkeeper with a forward for the same slot, which is exactly what picking an
XI and an armband is.

Measured on the two seasons no model trained on, over the five players each
position ranks highest in a gameweek -- the pool the optimiser actually buys
from -- predicted minus actual:

                  2024-25          2025-26
    GK            +0.96            +1.08
    DEF           +0.49            +0.61
    MID           +0.40            -0.04
    FWD           +0.51            +0.41

Every position is over-predicted at the top, which is expected: picking the
highest of fifteen noisy estimates picks the luckiest errors along with the
best players. What matters is that the four are not over-predicted equally.

The correction is an affine map per position applied to E[points | plays]:

    E[points | plays]' = intercept + slope * E[points | plays]

A multiplier alone was tried first and is not enough. It moves a position's
average but not its spread, and the spread is the other half of the problem:
the top of the goalkeeper ranking is over-predicted by a full point even after
its mean is corrected, because the model's confidence in *which* keeper will
return is largely noise. The fitted goalkeeper slope is about 0.14, which says
roughly six sevenths of the apparent gap between keepers is not real.

It is applied to the conditional term rather than to the finished prediction
so that P(plays) still scales it. Applied to the product, a fringe player
predicted near zero would be lifted to the intercept -- a third-choice keeper
worth 2.5 points.

That does reorder players within a position, and deliberately so. The map is
monotone in the conditional term, but the finished prediction multiplies it by
P(plays), so flattening a position's conditional spread hands the ranking over
to who is going to be on the pitch. For goalkeepers, whose fitted slope says
the model can barely tell one starter's return from another's, that is the
right answer: the top keeper by this measure becomes the nailed one rather
than the one the model has quietly guessed will keep a clean sheet.

It is fitted on 2024-25 and 2025-26 because those are the seasons no model
saw -- 2023-24 is inside train_availability.py's TRAIN_SEASONS and would report
a model flattering itself. Fitting and shipping on the same two seasons means
the shipped numbers are in-sample; --validate reports the honest version, fit
on one season and scored on the other, and is what decides whether a position
is corrected at all.

Usage
-----
    python scripts/calibrate.py               # fit, report, and save
    python scripts/calibrate.py --validate    # fit on one season, score the other
    python scripts/calibrate.py --no-save
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd

IN_FILE = 'all_seasons_data_featured.csv'
MODEL_DIR = os.path.join('saved_models', 'direct')
METRICS_OUT = 'calibration_metrics.json'
POSITIONS = ('GK', 'DEF', 'MID', 'FWD')

# The seasons no model in saved_models/ has trained on. Keep in step with
# train_availability.py's TRAIN_SEASONS.
HOLDOUT_SEASONS = ('2024-25', '2025-26')

# A correction is only fitted where the optimiser actually chooses. Fringe
# players are dominated by P(plays), which is already well calibrated.
NAILED = 0.8

# How many players per position per gameweek count as "the top of the ranking".
# The optimiser fields one keeper, three to five defenders and so on, so no
# single depth is the right one and a rule tuned to one of them is a rule
# tuned to noise. Every depth is scored and the verdict is their average.
TOP_N = 5
TOP_DEPTHS = (1, 3, 5, 10)

# Guard rails. A slope outside this band means something is wrong upstream
# rather than that the model needs that much correcting; a negative one would
# also invert the ranking within the position.
MIN_SLOPE, MAX_SLOPE = 0.05, 1.50


def load_position(position: str):
    """The availability-half artifacts for one position."""
    directory = os.path.join(MODEL_DIR, position)
    feat_path = os.path.join(directory, 'availability_features.json')
    if not os.path.exists(feat_path):
        return None
    features = json.load(open(feat_path, encoding='utf-8'))
    if not isinstance(features, list):
        features = features.get('features', features)
    return {
        'dir': directory,
        'features': features,
        'scaler': joblib.load(os.path.join(directory, 'availability_scaler.joblib')),
        'availability': joblib.load(os.path.join(directory, 'availability.joblib')),
        'conditional': joblib.load(os.path.join(directory, 'conditional.joblib')),
    }


def score(frame: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """P(plays), E[points | plays] and their product for every row."""
    scaled = spec['scaler'].transform(frame[spec['features']].fillna(0))
    out = frame[['season', 'GW', 'total_points']].copy()
    out['p_plays'] = spec['availability'].predict_proba(scaled)[:, 1]
    out['conditional'] = spec['conditional'].predict(scaled)
    out['predicted'] = out['p_plays'] * out['conditional']
    return out


def fit_affine(scored: pd.DataFrame):
    """Least squares from E[points | plays] to what actually happened.

    Fitted on nailed players only. For them P(plays) is close to one, so the
    conditional term is compared against the outcome it is meant to predict
    rather than against one P(plays) has already discounted.
    """
    nailed = scored[scored['p_plays'] >= NAILED]
    if len(nailed) < 100:
        return None
    slope, intercept = np.polyfit(nailed['conditional'], nailed['total_points'], 1)
    return float(intercept), float(slope)


def top_bias(scored: pd.DataFrame, column: str = 'predicted',
             depth: int = TOP_N) -> float:
    """Mean predicted minus mean actual over each gameweek's highest ranked."""
    top = scored.groupby(['season', 'GW'], group_keys=False).apply(
        lambda group: group.nlargest(depth, column))
    return float(top[column].mean() - top['total_points'].mean())


def apply_affine(scored: pd.DataFrame, intercept: float, slope: float) -> pd.Series:
    """The calibrated prediction: P(plays) still scales the corrected term."""
    return scored['p_plays'] * (intercept + slope * scored['conditional'])


def transfers_out_of_sample(by_season: dict):
    """Does a calibration fitted on one holdout season help on the other?

    A bias worth correcting is one the model repeats. A fit that merely tracks
    one season's scoring rate will be the wrong fit next season, and applying
    it does more harm than leaving the prediction alone. Each holdout season
    takes a turn as the fit, and the correction is kept only when it shrinks
    the error on the season it did not see -- in both directions, so a single
    lucky pairing cannot carry it.
    """
    rounds = []
    for fit_season in HOLDOUT_SEASONS:
        other = [s for s in HOLDOUT_SEASONS if s != fit_season][0]
        fitted = fit_affine(by_season[fit_season])
        if fitted is None:
            continue
        intercept, slope = fitted
        unseen = by_season[other].copy()
        unseen['calibrated'] = apply_affine(unseen, intercept, slope)
        before = [abs(top_bias(unseen, 'predicted', n)) for n in TOP_DEPTHS]
        after = [abs(top_bias(unseen, 'calibrated', n)) for n in TOP_DEPTHS]
        rounds.append({
            'fit_on': fit_season,
            'scored_on': other,
            'intercept': intercept,
            'slope': slope,
            'bias_before': top_bias(unseen, 'predicted'),
            'bias_after': top_bias(unseen, 'calibrated'),
            'mean_abs_before': float(np.mean(before)),
            'mean_abs_after': float(np.mean(after)),
        })
    if not rounds:
        return False, rounds
    keeps = all(r['mean_abs_after'] < r['mean_abs_before'] for r in rounds)
    return keeps, rounds


def report_validation(by_position: dict) -> None:
    """Fit on one holdout season, score on the other -- the honest number."""
    print("\nHonest check: fit on one season, score on the other.\n")
    print(f"  {'pos':<5}{'fit on':>9}{'intercept':>11}{'slope':>8}"
          f"{'|bias| before':>15}{'after':>9}{'verdict':>9}")
    print("  " + "-" * 66)
    for position in POSITIONS:
        keeps, rounds = transfers_out_of_sample(by_position[position])
        for entry in rounds:
            print(f"  {position:<5}{entry['fit_on']:>9}{entry['intercept']:>11.3f}"
                  f"{entry['slope']:>8.3f}{entry['mean_abs_before']:>15.3f}"
                  f"{entry['mean_abs_after']:>9.3f}"
                  f"{('keep' if keeps else 'drop'):>9}")
    depths = '/'.join(str(d) for d in TOP_DEPTHS)
    print(f"\n  '|bias|' is |mean predicted - mean actual| over the top {depths}")
    print("  players a position ranks highest each gameweek, averaged over those")
    print("  depths, on the season that was NOT used to fit. A position is")
    print("  corrected only when the fit helps on both unseen seasons.\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', default=IN_FILE)
    parser.add_argument('--no-save', action='store_true')
    parser.add_argument('--validate', action='store_true',
                        help='fit on one holdout season, score on the other')
    args = parser.parse_args()

    if not os.path.exists(args.data):
        raise SystemExit(
            f"{args.data} not found.\n"
            f"Run: python scripts/build_features.py")

    frame = pd.read_csv(args.data, low_memory=False)
    frame = frame.dropna(subset=['total_points', 'minutes'])

    specs = {p: load_position(p) for p in POSITIONS}
    missing = [p for p, spec in specs.items() if spec is None]
    if missing:
        raise SystemExit(
            f"no availability model for {', '.join(missing)}.\n"
            f"Run: python scripts/train_availability.py")

    # Score once per position per season; every report below reuses it.
    by_position = {
        position: {
            season: score(frame[(frame['season'] == season)
                                & (frame['position'] == position)], specs[position])
            for season in HOLDOUT_SEASONS
        }
        for position in POSITIONS
    }

    if args.validate:
        report_validation(by_position)
        return 0

    print(f"\nFitting on {' + '.join(HOLDOUT_SEASONS)}, "
          f"nailed players only (p_plays >= {NAILED})\n")
    print(f"  {'pos':<5}{'n':>7}{'intercept':>11}{'slope':>8}"
          f"{'top bias':>11}{'after':>9}  note")
    print("  " + "-" * 64)

    metrics = {}
    for position in POSITIONS:
        both = pd.concat(by_position[position].values(), ignore_index=True)
        fitted = fit_affine(both)
        count = int((both['p_plays'] >= NAILED).sum())
        identity = {'intercept': 0.0, 'slope': 1.0, 'applied': False, 'n': count}

        if fitted is None:
            print(f"  {position:<5}{count:>7}{'':>39}  too few nailed players")
            metrics[position] = dict(identity, reason='insufficient data')
            continue

        intercept, slope = fitted
        if not MIN_SLOPE <= slope <= MAX_SLOPE:
            note = f'slope {slope:.3f} out of range, left uncorrected'
            print(f"  {position:<5}{count:>7}{'':>39}  {note}")
            metrics[position] = dict(identity, reason=note,
                                     raw_intercept=intercept, raw_slope=slope)
            continue

        keeps, rounds = transfers_out_of_sample(by_position[position])
        before = top_bias(both, 'predicted')
        calibrated = both.copy()
        calibrated['calibrated'] = apply_affine(both, intercept, slope)
        after = top_bias(calibrated, 'calibrated')
        note = ''
        if not keeps:
            note = 'left uncorrected, does not transfer'
            intercept, slope, after = 0.0, 1.0, before

        print(f"  {position:<5}{count:>7}{intercept:>11.3f}{slope:>8.3f}"
              f"{before:>+11.3f}{after:>+9.3f}  {note}")
        metrics[position] = {
            'intercept': intercept,
            'slope': slope,
            'applied': bool(keeps),
            'raw_intercept': float(fitted[0]),
            'raw_slope': float(fitted[1]),
            'n': count,
            'top_bias_before': before,
            'top_bias_after': after,
            'fitted_on': list(HOLDOUT_SEASONS),
            'nailed_threshold': NAILED,
            'top_n': TOP_N,
            'validation': rounds,
        }

    if args.no_save:
        print("\n  --no-save: nothing written\n")
        return 0

    for position in POSITIONS:
        out_path = os.path.join(MODEL_DIR, position, 'calibration.json')
        with open(out_path, 'w', encoding='utf-8') as handle:
            json.dump(metrics[position], handle, indent=2)
    with open(METRICS_OUT, 'w', encoding='utf-8') as handle:
        json.dump(metrics, handle, indent=2)
    print(f"\n  wrote calibration.json to each position directory under {MODEL_DIR}")
    print(f"  wrote {METRICS_OUT}\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
