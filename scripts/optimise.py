"""Turn predicted points into FPL decisions.

predict_gameweek.py answers "how many points is each player worth". This
answers the questions an actual manager has: which fifteen to own, which
eleven to start, who to captain, which transfers to make, and when to play
each chip.

Everything is a single integer program per question, so the answers are
genuinely optimal under the stated constraints rather than greedy picks.

Optimal is also deterministic: one budget has one answer, and every manager
running this gets the same fifteen. The optimum is a plateau rather than a
peak -- seven of the fifteen can change for about half a point, against a
per-player error near a full one -- so `squad` takes --alternatives to show
the squads the model cannot tell apart, --differential to tilt away from the
template, and --seed to break ties per manager. Each reports what it cost.

Subcommands
-----------
    squad       the best legal 15 with XI, bench, captain and vice-captain
    transfers   the best N transfers out of a squad you already own
    chips       when to play Triple Captain, Bench Boost, Free Hit, Wildcard
    watchlist   differentials, value picks, and who to avoid

Usage
-----
    python scripts/optimise.py squad --budget 100
    python scripts/optimise.py squad --budget 83 --formation-only-xi
    python scripts/optimise.py squad --alternatives 5
    python scripts/optimise.py squad --differential 0.02 --seed <user id>
    python scripts/optimise.py transfers --squad my_squad.txt --free 1 --bank 0.5
    python scripts/optimise.py chips --squad my_squad.txt --horizon 8
    python scripts/optimise.py watchlist --max-ownership 10

A squad file is one player name per line; blank lines and #comments ignored.
Names are matched case-insensitively against the prediction output, so a
surname is usually enough.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from console import force_utf8  # noqa: E402
from chip_policy import ChipDecisionPolicy  # noqa: E402

force_utf8()

PREDICTIONS = 'predictions_next_gw.csv'

# An FPL squad is exactly this shape, and the XI drawn from it must satisfy
# the second. The bench is whatever the XI leaves over.
SQUAD_SHAPE = {'GK': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}
XI_MIN = {'GK': 1, 'DEF': 3, 'MID': 2, 'FWD': 1}
XI_MAX = {'GK': 1, 'DEF': 5, 'MID': 5, 'FWD': 3}
SQUAD_SIZE = 15
XI_SIZE = 11
MAX_PER_CLUB = 3
HIT_COST = 4          # points docked per transfer beyond the free ones
# Do not recommend extra transfers for an edge smaller than the model's
# measured per-player error. The raw mathematical optimum is still returned.
DECISION_MARGIN = 1.0

# How far a --seed is allowed to move a pick, in predicted points per player.
# The optimum is a plateau, not a peak: forcing seven of the fifteen to change
# costs about half a point, so ties in any sense that matters are decided by
# differences far smaller than the model can resolve. This is the budget for
# breaking them. The points actually given up are measured and reported, so
# the cost of a seed is never hidden.
#
# Over five managers on a 100.0m budget, distinct starting elevens against the
# worst any of them gave up:
#
#     0.05   4 of 5   -0.23        0.20   5 of 5   -0.58
#     0.10   4 of 5   -0.52        0.50   5 of 5   -3.60
#
# 0.05 already separates almost everyone for a quarter of a point, and 0.50
# buys the last pair at more than the model can defend. Raise it with
# --seed-scale if a deployment would rather have the variety.
TIEBREAK_SCALE = 0.05

# Two squads count as different answers only if this many players differ.
MIN_ALTERNATIVE_CHANGES = 3

# Bench points only matter if you play Bench Boost, or a starter does not
# feature. Weighting them low keeps the optimiser from buying an expensive
# bench at the XI's expense, without letting it field four goalkeepers either.
BENCH_WEIGHT = 0.1


def load_predictions(path: str, drop_unavailable: bool = True) -> pd.DataFrame:
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} not found.\n"
            f"Run: python scripts/predict_gameweek.py")

    df = pd.read_csv(path)
    for required in ('name', 'team', 'position', 'value_m', 'predicted_points'):
        if required not in df.columns:
            raise SystemExit(f"{path} has no '{required}' column")

    df = df[df['value_m'] > 0].copy()
    current_points = None
    if 'GW' in df.columns:
        weeks = pd.to_numeric(df['GW'], errors='coerce')
        if weeks.notna().any():
            df = df.loc[weeks == weeks.min()].copy()
            identity = 'element' if 'element' in df.columns else 'name'
            current_points = df.groupby(identity)['predicted_points'].sum()
    if drop_unavailable and 'status' in df.columns:
        df = df[~df['status'].isin({'i', 'u', 's', 'n'})]

    # One row per player. A double gameweek would otherwise let the optimiser
    # buy the same player twice -- but that is the same element twice, so the
    # key has to be the element. Keying on the name deleted whole players from
    # the market whenever two of them shared a surname: eleven in the GW5
    # export, including one of the two Palacios.
    key = 'element' if 'element' in df.columns else 'name'
    df = df.sort_values('predicted_points', ascending=False).drop_duplicates(key)
    if current_points is not None:
        df['predicted_points'] = df[key].map(current_points)
    return df.reset_index(drop=True)


def load_horizon(path: str, drop_unavailable: bool = True) -> tuple:
    """A predictions file with a GW column, as (one row per player, points by GW).

    predict_gameweek.py --horizon writes one row per player per gameweek. This
    collapses it to the shape the optimiser wants: a player table to buy from,
    and a matrix of what each player is worth in each week. A double gameweek
    is two rows for one player and sums; a blank is no row at all and becomes
    a zero, which is exactly how a blank should price.
    """
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found.\n"
                         f"Run: python scripts/predict_gameweek.py --horizon 6")

    df = pd.read_csv(path)
    if 'GW' not in df.columns:
        raise SystemExit(
            f"{path} has no GW column, so it covers a single gameweek.\n"
            f"Regenerate it with: python scripts/predict_gameweek.py --horizon 6")
    for required in ('name', 'team', 'position', 'value_m', 'predicted_points'):
        if required not in df.columns:
            raise SystemExit(f"{path} has no '{required}' column")

    df = df[df['value_m'] > 0].copy()
    if drop_unavailable and 'status' in df.columns:
        df = df[~df['status'].isin({'i', 'u', 's', 'n'})]
    if df.empty:
        raise SystemExit(f"{path} has no available players")

    key = 'element' if 'element' in df.columns else 'name'
    gameweeks = sorted(int(g) for g in df['GW'].dropna().unique())

    points = (df.groupby([key, 'GW'])['predicted_points'].sum()
              .unstack('GW').reindex(columns=gameweeks).fillna(0.0))

    # One descriptive row per player. Price and club are properties of the
    # player, not of a gameweek, so the first row will do.
    players = (df.sort_values('GW').groupby(key, as_index=False).first())
    players = players.set_index(key).loc[points.index].reset_index()
    points = points.reset_index(drop=True)

    return players, points, gameweeks


def horizon_weights(gameweeks: list, decay: float) -> dict:
    """How much each gameweek counts, relative to the first.

    Discounting the far end looks obviously right and measures out wrong. A
    frozen-form prediction does lose about 2.6% of its ranking per gameweek
    (scripts/horizon.py), so the instinct is to weight later weeks down. But
    the squad is being held through all of those weeks and every one of them
    pays the same points, so a discount buys nothing and costs the far
    fixtures their say. Over 28 six-gameweek windows of 2024-25 and 2025-26,
    against picking on the next gameweek alone:

        decay 1.0   +17.8 points      decay 0.90   +12.5
        decay 0.97  +15.5             decay 0.80   +10.8

    Monotonic, so the default is 1.0. The argument is kept because a manager
    planning around a wildcard or a known return may genuinely want the near
    fixtures weighted more heavily than the far ones.
    """
    first = gameweeks[0]
    return {gw: decay ** (gw - first) for gw in gameweeks}


def read_squad_file(path: str, players: pd.DataFrame) -> pd.DataFrame:
    """Match a list of names against the prediction rows."""
    if not os.path.exists(path):
        raise SystemExit(f"squad file {path} not found")

    wanted = [line.strip() for line in open(path, encoding='utf-8')
              if line.strip() and not line.startswith('#')]
    if not wanted:
        raise SystemExit(f"{path} is empty")

    rows, missing, ambiguous = [], [], []
    lowered = players['name'].str.lower()
    for entry in wanted:
        hits = players[lowered.str.contains(entry.lower(), regex=False)]
        if hits.empty:
            missing.append(entry)
        elif len(hits) > 1:
            exact = hits[hits['name'].str.lower() == entry.lower()]
            if len(exact) == 1:
                rows.append(exact.index[0])
            else:
                ambiguous.append((entry, hits['name'].tolist()[:4]))
        else:
            rows.append(hits.index[0])

    if missing:
        print(f"\n  not found in the predictions: {', '.join(missing)}")
        print("  (injured and suspended players are dropped by default; "
              "check spelling, or pass --include-unavailable to predict_gameweek)")
    for entry, options in ambiguous:
        print(f"  {entry!r} matches several players: {', '.join(options)}")
    if missing or ambiguous:
        raise SystemExit("could not resolve every name in the squad file")

    return players.loc[rows]


# ---------------------------------------------------------------------------
# The optimiser
# ---------------------------------------------------------------------------
def expected_total(result: dict) -> float:
    """What the XI is worth with the armband on, in real predicted points.

    Read off the chosen players rather than the LP objective, which also
    carries the bench weighting, any ownership penalty and any seed jitter.
    Those steer the pick; they are not points anyone scores.
    """
    total = float(result['xi']['predicted_points'].sum())
    if result['captain'] is not None:
        total += float(result['captain']['predicted_points'])
    return total


def seed_jitter(players: pd.DataFrame, seed, scale: float = TIEBREAK_SCALE) -> dict:
    """A tiny per-player nudge, fixed by the seed.

    Deterministic across processes and machines: Python's hash() is salted per
    run, so the digest is taken explicitly. Keyed on the element where there is
    one, so the same seed keeps picking the same way when a player is renamed.
    """
    key = 'element' if 'element' in players.columns else 'name'
    jitter = {}
    for i, ident in players[key].items():
        digest = hashlib.sha256(f'{seed}:{ident}'.encode('utf-8')).digest()
        unit = int.from_bytes(digest[:8], 'big') / float(1 << 64)
        jitter[i] = (unit * 2.0 - 1.0) * scale
    return jitter


def solve_squad(players: pd.DataFrame, budget: float, *, squad_size: int = SQUAD_SIZE,
                locked=None, banned=None, must_transfer_out=None,
                bench_weight: float = BENCH_WEIGHT, captain: bool = True,
                apart_from=None, ownership_penalty: float = 0.0, seed=None,
                seed_scale: float = TIEBREAK_SCALE):
    """Best legal squad, XI, bench order and armband picks -- one program.

    Picking fifteen and then picking eleven separately gives a worse answer
    than deciding both together: the value of a player depends on whether he
    starts, and the value of a cheap bench depends on what it frees up for the
    XI. Both sets of binaries live in the same problem, tied by xi <= squad.

    Three optional terms steer which of several near-equal squads comes back,
    without changing what any of them is projected to score:

    `apart_from` is a list of (squad indices, minimum changes) that the answer
    must respect, which is how compute_squad_alternatives() walks the plateau.
    `ownership_penalty` docks a squad that many points per percent of ownership
    per player owned. `seed` breaks ties reproducibly per user.
    """
    import pulp

    idx = list(players.index)
    problem = pulp.LpProblem('fpl_squad', pulp.LpMaximize)

    in_squad = {i: pulp.LpVariable(f's{i}', cat='Binary') for i in idx}
    in_xi = {i: pulp.LpVariable(f'x{i}', cat='Binary') for i in idx}
    is_cap = {i: pulp.LpVariable(f'c{i}', cat='Binary') for i in idx}

    points = players['predicted_points'].to_dict()
    cost = players['value_m'].to_dict()
    position = players['position'].to_dict()
    club = players['team'].to_dict()

    # The XI carries full weight, the bench a fraction, the captain scores
    # twice (so the captaincy adds one more copy of his points).
    objective = pulp.lpSum(points[i] * in_xi[i] for i in idx)
    objective += bench_weight * pulp.lpSum(
        points[i] * (in_squad[i] - in_xi[i]) for i in idx)
    if captain:
        objective += pulp.lpSum(points[i] * is_cap[i] for i in idx)
    if ownership_penalty and 'selected_by' in players.columns:
        # Owning a widely-owned player is not worth fewer points, it is worth
        # less rank. Charging it here lets the same solver trade the two off,
        # rather than filtering the market and hoping what is left is legal.
        owned = pd.to_numeric(players['selected_by'], errors='coerce').fillna(0.0)
        objective -= pulp.lpSum(
            ownership_penalty * float(owned[i]) * in_squad[i] for i in idx)
    if seed is not None:
        # On both terms. Nudging only squad membership left the best eleven
        # to be chosen on points alone, so every manager fielded near enough
        # the same team and the differences all landed on the bench: two
        # distinct elevens in five rather than four, at identical cost.
        jitter = seed_jitter(players, seed, seed_scale)
        objective += pulp.lpSum(jitter[i] * in_squad[i] for i in idx)
        objective += pulp.lpSum(jitter[i] * in_xi[i] for i in idx)
    problem += objective

    for i in idx:
        problem += in_xi[i] <= in_squad[i]
        problem += is_cap[i] <= in_xi[i]
        # Never the goalkeeper. A keeper's ceiling is a clean sheet, a few
        # saves and three bonus, so doubling one is the wrong bet against any
        # starting outfielder even in a week where the projection likes him.
        # The armband was the one place this could go wrong unchecked: the
        # squad itself still needs two keepers and they are picked on merit.
        if position[i] == 'GK':
            problem += is_cap[i] == 0

    problem += pulp.lpSum(in_squad.values()) == squad_size
    problem += pulp.lpSum(in_xi.values()) == XI_SIZE
    problem += pulp.lpSum(is_cap.values()) == (1 if captain else 0)
    problem += pulp.lpSum(cost[i] * in_squad[i] for i in idx) <= budget

    full_squad = squad_size == SQUAD_SIZE
    for pos, need in SQUAD_SHAPE.items():
        members = [i for i in idx if position[i] == pos]
        if full_squad:
            problem += pulp.lpSum(in_squad[i] for i in members) == need
        problem += pulp.lpSum(in_xi[i] for i in members) >= XI_MIN[pos]
        problem += pulp.lpSum(in_xi[i] for i in members) <= XI_MAX[pos]

    for name in players['team'].unique():
        members = [i for i in idx if club[i] == name]
        problem += pulp.lpSum(in_squad[i] for i in members) <= MAX_PER_CLUB

    for i in (locked or []):
        problem += in_squad[i] == 1
    for i in (banned or []):
        problem += in_squad[i] == 0
    if must_transfer_out is not None:
        keep, count = must_transfer_out
        problem += pulp.lpSum(in_squad[i] for i in keep) == count
    for previous, min_changes in (apart_from or []):
        problem += pulp.lpSum(
            in_squad[i] for i in previous) <= squad_size - min_changes

    problem.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[problem.status]
    if status != 'Optimal':
        return None, status

    chosen = [i for i in idx if in_squad[i].value() > 0.5]
    starters = [i for i in idx if in_xi[i].value() > 0.5]
    skipper = [i for i in idx if is_cap[i].value() > 0.5]
    captain_idx = skipper[0] if skipper else None
    vice_candidates = [
        i for i in starters
        if i != captain_idx and position[i] != 'GK'
    ]
    # The vice-captain only scores if the captain does not play. With no
    # no-show probability in this single-GW solver, the sound deterministic
    # choice is the strongest projected starting outfielder after the captain.
    vice_idx = max(vice_candidates, key=lambda i: points[i]) if vice_candidates else None
    bench_idx = [i for i in chosen if i not in starters]
    bench_outfield = sorted(
        (i for i in bench_idx if position[i] != 'GK'),
        key=lambda i: points[i], reverse=True)
    bench_goalkeepers = sorted(
        (i for i in bench_idx if position[i] == 'GK'),
        key=lambda i: points[i], reverse=True)
    return {
        'squad': players.loc[chosen],
        'xi': players.loc[starters],
        # FPL displays three ordered outfield substitutes and the reserve
        # goalkeeper in a separate final slot.
        'bench': players.loc[bench_outfield + bench_goalkeepers],
        'captain': players.loc[captain_idx] if captain_idx is not None else None,
        'vice_captain': players.loc[vice_idx] if vice_idx is not None else None,
        # What the program maximised: points, plus the bench weighting and any
        # ownership penalty or seed jitter. Not points anyone scores, but the
        # only quantity two solutions can be ranked against each other on.
        'score': float(pulp.value(problem.objective)),
    }, status


def solve_squad_horizon(players: pd.DataFrame, points: pd.DataFrame, budget: float,
                        weights: dict, *, bench_weight: float = BENCH_WEIGHT,
                        locked=None, banned=None):
    """The best fifteen to own across several gameweeks, not just the next one.

    One squad is bought once and kept for the whole horizon; the XI and the
    armband are chosen again every week, which is what a manager actually does.
    That is the difference from running the single-gameweek solver six times
    and hoping the answers agree -- here the fifteen are picked knowing they
    have to cover all six weeks, so a player with one glamour fixture and five
    poor ones loses to one who is useful throughout.

    Transfers are deliberately not modelled. The horizon says which squad is
    worth holding; scripts/optimise.py transfers answers how to get there from
    the squad you own.
    """
    import pulp

    idx = list(players.index)
    gameweeks = list(points.columns)
    cost = players['value_m'].to_dict()
    position = players['position'].to_dict()
    club = players['team'].to_dict()

    problem = pulp.LpProblem('fpl_squad_horizon', pulp.LpMaximize)
    in_squad = pulp.LpVariable.dicts('own', idx, cat='Binary')
    in_xi = pulp.LpVariable.dicts('start', (idx, gameweeks), cat='Binary')
    is_cap = pulp.LpVariable.dicts('cap', (idx, gameweeks), cat='Binary')

    objective = []
    for gw in gameweeks:
        weight = weights[gw]
        column = points[gw]
        for i in idx:
            value = float(column.loc[i])
            # Starting is worth the points; the armband is worth them again;
            # the bench only pays off on a Bench Boost or an auto-sub.
            objective.append(weight * value * in_xi[i][gw])
            objective.append(weight * value * is_cap[i][gw])
            objective.append(weight * bench_weight * value
                             * (in_squad[i] - in_xi[i][gw]))
    problem += pulp.lpSum(objective)

    problem += pulp.lpSum(in_squad.values()) == SQUAD_SIZE
    problem += pulp.lpSum(cost[i] * in_squad[i] for i in idx) <= budget

    for pos, need in SQUAD_SHAPE.items():
        members = [i for i in idx if position[i] == pos]
        problem += pulp.lpSum(in_squad[i] for i in members) == need

    for name in players['team'].unique():
        members = [i for i in idx if club[i] == name]
        problem += pulp.lpSum(in_squad[i] for i in members) <= MAX_PER_CLUB

    for gw in gameweeks:
        problem += pulp.lpSum(in_xi[i][gw] for i in idx) == XI_SIZE
        problem += pulp.lpSum(is_cap[i][gw] for i in idx) == 1
        for pos in SQUAD_SHAPE:
            members = [i for i in idx if position[i] == pos]
            problem += pulp.lpSum(in_xi[i][gw] for i in members) >= XI_MIN[pos]
            problem += pulp.lpSum(in_xi[i][gw] for i in members) <= XI_MAX[pos]
        for i in idx:
            problem += in_xi[i][gw] <= in_squad[i]
            problem += is_cap[i][gw] <= in_xi[i][gw]
            if position[i] == 'GK':
                problem += is_cap[i][gw] == 0

    for i in (locked or []):
        problem += in_squad[i] == 1
    for i in (banned or []):
        problem += in_squad[i] == 0

    problem.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[problem.status]
    if status != 'Optimal':
        return None, status

    chosen = [i for i in idx if in_squad[i].value() > 0.5]
    weeks = {}
    for gw in gameweeks:
        starters = [i for i in chosen if in_xi[i][gw].value() > 0.5]
        skipper = [i for i in chosen if is_cap[i][gw].value() > 0.5]
        weeks[gw] = {
            'xi': players.loc[starters],
            'bench': players.loc[[i for i in chosen if i not in starters]],
            'captain': players.loc[skipper[0]] if skipper else None,
            'points': points[gw],
        }
    return {'squad': players.loc[chosen], 'weeks': weeks, 'points': points}, status


def show_squad_horizon(result: dict, budget: float, weights: dict) -> None:
    squad, weeks = result['squad'], result['weeks']
    points = result['points']
    gameweeks = list(weeks)
    spend = squad['value_m'].sum()

    order = {'GK': 0, 'DEF': 1, 'MID': 2, 'FWD': 3}
    totals = points.loc[squad.index].sum(axis=1)
    listing = squad.assign(_o=squad['position'].map(order), total=totals)
    listing = listing.sort_values(['_o', 'total'], ascending=[True, False])

    print(f"\n{'=' * 78}")
    print(f"SQUAD FOR GW{gameweeks[0]}..GW{gameweeks[-1]}")
    print("=" * 78)
    head = f"  {'':<4} {'player':<24}{'club':<15}{'£':>6}  " + "".join(
        f"GW{gw:<4}" for gw in gameweeks) + f"{'total':>7}"
    print(head)
    print("  " + "-" * (len(head) - 2))
    for i, row in listing.iterrows():
        cells = "".join(f"{points.loc[i, gw]:>5.1f} " for gw in gameweeks)
        starts = sum(1 for gw in gameweeks if i in weeks[gw]['xi'].index)
        flag = ' ' if starts == len(gameweeks) else '~'
        print(f"  {row['position']:<4} {row['name'][:22]:<24}{row['team'][:13]:<15}"
              f"{row['value_m']:>5.1f} {flag}{cells}{row['total']:>6.1f}")

    print(f"\n  '~' marks a player who is not in the XI every week.")

    print(f"\n{'=' * 78}\nWEEK BY WEEK\n{'=' * 78}")
    print(f"  {'gw':<5}{'formation':<12}{'captain':<24}{'XI':>7}{'+ armband':>11}{'weight':>8}")
    print("  " + "-" * 65)
    running = 0.0
    for gw in gameweeks:
        week = weeks[gw]
        xi = week['xi']
        shape = xi['position'].value_counts()
        formation = f"{shape.get('DEF', 0)}-{shape.get('MID', 0)}-{shape.get('FWD', 0)}"
        xi_points = points.loc[xi.index, gw].sum()
        cap = week['captain']
        bonus = points.loc[cap.name, gw] if cap is not None else 0.0
        running += xi_points + bonus
        print(f"  {gw:<5}{formation:<12}{(cap['name'][:22] if cap is not None else '-'):<24}"
              f"{xi_points:>7.2f}{xi_points + bonus:>11.2f}{weights[gw]:>8.2f}")

    print(f"\n  spend             {spend:>6.1f}m of {budget:.1f}m (bank {budget - spend:.1f}m)")
    print(f"  expected total    {running:>6.2f} across {len(gameweeks)} gameweeks "
          f"({running / len(gameweeks):.2f} per gameweek)")
    print(f"\n  The squad is bought once and held; the XI and armband are rechosen")
    print(f"  each week. Transfers are not modelled -- use the transfers subcommand")
    print(f"  to plan the route from the squad you already own.")


def show_squad(result: dict, budget: float) -> None:
    squad, xi, bench, cap = (result['squad'], result['xi'],
                             result['bench'], result['captain'])
    spend = squad['value_m'].sum()

    order = {'GK': 0, 'DEF': 1, 'MID': 2, 'FWD': 3}
    xi = xi.assign(_o=xi['position'].map(order)).sort_values(
        ['_o', 'predicted_points'], ascending=[True, False])
    # FPL asks for a bench *order*, and the reserve keeper sits in his own slot,
    # so the outfield three are ranked by predicted points -- the order they
    # would be auto-subbed in if a starter does not play.
    bench_gk = bench[bench['position'] == 'GK']
    bench_out = bench[bench['position'] != 'GK'].sort_values(
        'predicted_points', ascending=False)

    shape = xi['position'].value_counts()
    formation = f"{shape.get('DEF', 0)}-{shape.get('MID', 0)}-{shape.get('FWD', 0)}"

    print(f"\n{'=' * 78}")
    print(f"STARTING XI   ({formation})")
    print("=" * 78)
    for _, row in xi.iterrows():
        mark = ' (C)' if cap is not None and row['name'] == cap['name'] else ''
        print(f"  {row['position']:<4} {row['name'][:26]:<28} {row['team'][:14]:<16}"
              f"{row['value_m']:>5.1f}m {row['predicted_points']:>6.2f}{mark}")

    if len(bench):
        print("\nBENCH  (outfield in auto-sub order)")
        print("-" * 78)
        for slot, (_, row) in enumerate(bench_out.iterrows(), start=1):
            print(f"  {slot}. {row['position']:<4} {row['name'][:24]:<26}"
                  f"{row['team'][:14]:<16}{row['value_m']:>5.1f}m "
                  f"{row['predicted_points']:>6.2f}")
        for _, row in bench_gk.iterrows():
            print(f"  GK {row['position']:<4} {row['name'][:24]:<26}"
                  f"{row['team'][:14]:<16}{row['value_m']:>5.1f}m "
                  f"{row['predicted_points']:>6.2f}")

    xi_points = xi['predicted_points'].sum()
    cap_bonus = cap['predicted_points'] if cap is not None else 0
    print(f"\n  spend            {spend:>6.1f}m of {budget:.1f}m "
          f"(bank {budget - spend:.1f}m)")
    print(f"  XI points        {xi_points:>6.2f}")
    if cap is not None:
        print(f"  captain          {cap['name']} (+{cap_bonus:.2f})")
        vice = result.get('vice_captain')
        if vice is not None:
            print(f"  vice-captain     {vice['name']}")
        print(f"  expected total   {xi_points + cap_bonus:>6.2f}")
    if len(bench):
        print(f"  bench            {bench['predicted_points'].sum():>6.2f} "
              f"(only scores on Bench Boost)")


def squad_ownership(squad: pd.DataFrame) -> float | None:
    """Mean ownership of the fifteen, or None if the export has no column."""
    if 'selected_by' not in squad.columns:
        return None
    owned = pd.to_numeric(squad['selected_by'], errors='coerce')
    return None if owned.isna().all() else round(float(owned.mean()), 1)


def compute_squad_alternatives(players: pd.DataFrame, budget: float, *,
                               count: int = 5,
                               min_changes: int = MIN_ALTERNATIVE_CHANGES,
                               margin: float = DECISION_MARGIN,
                               **solve_kwargs) -> dict:
    """Every squad the model cannot tell apart from the best one.

    The optimiser is a deterministic integer program, so one budget has one
    answer and every manager running it gets the same fifteen. That is correct
    and useless: a template squad matches the field it is trying to beat.

    It is also a plateau rather than a peak. Forcing three of the fifteen to
    change costs about a quarter of a point, and seven about half, against a
    per-player error near a full point. So this re-solves under the constraint
    that each answer differs from all the previous ones, and stops once the
    next one would fall more than `margin` below the best -- which is to say,
    once the difference is one the model can actually defend.

    Returns data only, so the CLI and the web layer show the same squads.
    """
    found, apart, failures = [], [], []
    best = None
    while len(found) < count:
        result, status = solve_squad(players, budget, apart_from=apart,
                                     **solve_kwargs)
        if result is None:
            failures.append(status)
            break
        total = expected_total(result)
        score = result['score']
        if best is None:
            best = score
        elif best - score > margin:
            # Past the point where the model can justify the difference.
            break
        found.append({
            'rank': len(found) + 1,
            'total': round(total, 2),
            # Measured on the objective, not on the points, so it cannot come
            # out negative when a penalty or a seed is steering the pick.
            'behind_best': round(best - score, 2),
            # Signed, and in real points: what this squad is projected to
            # score against the first one. Steering can make it positive.
            'points_vs_best': round(total - found[0]['total'], 2) if found else 0.0,
            'spend': round(float(result['squad']['value_m'].sum()), 1),
            'ownership': squad_ownership(result['squad']),
            'captain': None if result['captain'] is None
                       else result['captain']['name'],
            'changes': (None if not found else sorted(
                set(result['squad']['name']) - set(found[0]['names']))),
            'names': list(result['squad']['name']),
            'squad': squad_records(result['squad']),
            'xi': squad_records(result['xi']),
        })
        apart.append((list(result['squad'].index), min_changes))

    return {
        'budget': round(float(budget), 1),
        'requested': count,
        'min_changes': min_changes,
        'margin': margin,
        'alternatives': found,
        'exhausted': len(found) < count,
        'failures': failures,
    }


def show_squad_alternatives(data: dict) -> None:
    found = data['alternatives']
    if not found:
        raise SystemExit("no legal squad found")

    print()
    print('=' * 78)
    print(f"NEAR-OPTIMAL SQUADS   (at least {data['min_changes']} players apart, "
          f"within {data['margin']:.1f} points)")
    print('=' * 78)
    print()
    print("  The model's error is about a point per player, so these are the")
    print("  same answer as far as it can tell. Choosing between them is yours.")
    print()

    owned = found[0]['ownership'] is not None
    header = f"  {'#':<3}{'expected':>10}{'vs #1':>8}{'spend':>8}"
    if owned:
        header += f"{'owned%':>9}"
    print(header + "  captain / players it brings in")
    print("  " + "-" * 74)
    for entry in found:
        line = (f"  {entry['rank']:<3}{entry['total']:>10.2f}"
                f"{entry['points_vs_best']:>+8.2f}{entry['spend']:>8.1f}")
        if owned:
            line += f"{entry['ownership']:>9.1f}"
        detail = entry['captain'] or '--'
        if entry['changes']:
            detail += f"; in: {', '.join(entry['changes'])}"
        print(line + f"  {detail}")

    if data['exhausted']:
        print()
        print(f"  Only {len(found)} squad(s) stay within "
              f"{data['margin']:.1f} points while differing by "
              f"{data['min_changes']} players.")
        print("  Lower --min-changes for more, or accept a wider margin.")

def report_steering_cost(players: pd.DataFrame, budget: float, result: dict,
                         steer: dict) -> None:
    """Price whatever --seed and --differential bought.

    A tilt nobody can price is a tilt nobody can judge. Both of these move
    the pick off the optimum on purpose, so the points given up are measured
    against the unsteered answer and printed next to it.
    """
    if not steer.get('seed') and not steer.get('ownership_penalty'):
        return
    plain_steer = dict(steer)
    plain_steer['seed'] = None
    plain_steer['ownership_penalty'] = 0.0
    plain, _status = solve_squad(players, budget, **plain_steer)
    if plain is None:
        return

    steered_total = expected_total(result)
    plain_total = expected_total(plain)
    cost = plain_total - steered_total
    verdict = 'inside' if cost < DECISION_MARGIN else 'outside'
    print()
    print('-' * 78)
    print('STEERING COST')
    print('-' * 78)
    print(f"  this squad         {steered_total:>6.2f} expected points")
    print(f"  unsteered optimum  {plain_total:>6.2f}")
    print(f"  given up           {cost:>6.2f}  ({verdict} the "
          f"{DECISION_MARGIN:.1f}-point decision margin)")

    here = squad_ownership(result['squad'])
    there = squad_ownership(plain['squad'])
    if here is not None and there is not None:
        print(f"  mean ownership     {here:>6.1f}% against {there:.1f}% unsteered")
    changed = sorted(set(result['squad']['name']) - set(plain['squad']['name']))
    if changed:
        print(f"  differs by {len(changed)}: {', '.join(changed)}")
    else:
        print("  same fifteen as the unsteered optimum")

# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------
def choose_transfer_recommendation(rows: list, margin: float = DECISION_MARGIN):
    """Return (raw optimum, conservative recommendation).

    The solver can distinguish 58.16 from 58.09, but the prediction model
    cannot do so reliably. Keep the mathematical optimum for transparency,
    then step down to the fewest transfers whose net score is within `margin`
    of it.

    The step down only applies where it actually saves a points hit. A move
    covered by a free transfer costs nothing, so a small edge is still worth
    taking rather than withholding; a recommendation that thin is flagged
    instead, via `marginal_recommendation` in compute_transfers().
    """
    if not rows:
        return None, None
    best = max(rows, key=lambda row: (row['net'], -row['transfers']))
    defensible = [
        row for row in rows
        if row['transfers'] < best['transfers']
        and row['hit'] < best['hit']
        and best['net'] - row['net'] < margin
    ]
    if not defensible:
        return best, best
    return best, min(defensible, key=lambda row: row['transfers'])


def annotate_marginals(rows: list) -> None:
    """Attach each count's net gain over the count directly below it.

    Counts can be missing -- an unavailable player forces a minimum number of
    moves -- so this indexes by transfer count rather than list position, and
    leaves `marginal` at None when the preceding count has no row.
    """
    nets = {row['transfers']: row['net'] for row in rows}
    for row in rows:
        previous = nets.get(row['transfers'] - 1)
        row['marginal'] = (
            None if previous is None else round(row['net'] - previous, 2))


def compute_transfers(current: pd.DataFrame, players: pd.DataFrame,
                      free: int, bank: float, max_transfers: int) -> dict:
    """Jointly optimise every transfer count, net of the points hit.

    Each count is one integer program over the complete squad. This is
    intentionally not a greedy sequence: the solver may downgrade a useful
    player and spend the released money on a larger upgrade elsewhere. More
    transfers always buy at least as many raw points, so comparing them only
    means something after the -4 per extra transfer is charged. Every count is
    returned so a marginal second or third transfer is visible rather than
    assumed.

    Returns data only. suggest_transfers() prints it; the web layer renders the
    same structure, so the two can never drift.
    """
    budget = current['value_m'].sum() + bank

    # The available market has a fresh RangeIndex, while the current squad can
    # include unavailable players and therefore have different row numbers.
    # Transfer constraints must use stable identity, never DataFrame indices.
    identity = ('element' if 'element' in players.columns and
                'element' in current.columns else 'name')
    current_ids = set(current[identity])
    keep_idx = list(players.index[players[identity].isin(current_ids)])
    available_current_ids = set(players.loc[keep_idx, identity])
    forced_out = len(current_ids - available_current_ids)

    # Score standing pat independently. Count zero may be infeasible when an
    # owned player is unavailable, but gains still need the actual current
    # squad as their reference rather than the first feasible transfer plan.
    baseline_result, _ = solve_squad(
        current.reset_index(drop=True), float(current['value_m'].sum()))
    if baseline_result is None:
        raise ValueError('current squad is not a legal FPL squad')
    baseline_xi = float(baseline_result['xi']['predicted_points'].sum())
    baseline_cap = baseline_result['captain']
    baseline = baseline_xi + (
        float(baseline_cap['predicted_points']) if baseline_cap is not None else 0.0)

    rows = []
    failures = []
    for count in range(0, max_transfers + 1):
        if count < forced_out:
            failures.append({
                'transfers': count,
                'status': f'at least {forced_out} unavailable player(s) must be transferred out',
            })
            continue
        result, status = solve_squad(
            players, budget,
            must_transfer_out=(keep_idx, SQUAD_SIZE - count))
        if result is None:
            failures.append({'transfers': count, 'status': status})
            continue

        xi_points = result['xi']['predicted_points'].sum()
        cap = result['captain']['predicted_points'] if result['captain'] is not None else 0
        gross = xi_points + cap
        hit = max(0, count - free) * HIT_COST

        result_ids = set(result['squad'][identity])
        out = current[~current[identity].isin(result_ids)]
        into = result['squad'][~result['squad'][identity].isin(current_ids)]
        rows.append({
            'transfers': count,
            'gross': round(float(gross), 2),
            'hit': int(hit),
            'net': round(float(gross - hit), 2),
            'gain': round(float(gross - hit - baseline), 2),
            'out': list(out['name']),
            'in': list(into['name']),
            'squad': squad_records(result['squad']),
            **lineup_payload(result, budget),
            'bank_after': round(float(budget - result['squad']['value_m'].sum()), 1),
            'captained_total': round(float(gross), 2),
        })

    annotate_marginals(rows)

    best, recommended = choose_transfer_recommendation(rows)
    return {
        'squad_value': round(float(current['value_m'].sum()), 1),
        'bank': round(float(bank), 1),
        'budget': round(float(budget), 1),
        'free': int(free),
        'hit_cost': HIT_COST,
        'decision_margin': DECISION_MARGIN,
        'rows': rows,
        'failures': failures,
        'best': best,
        'recommended': recommended,
        'recommendation_edge': (
            None if best is None or recommended is None
            else round(best['net'] - recommended['net'], 2)),
        # The recommended move is worth making but sits inside the model's
        # error, so rolling it instead is defensible. Advisory, not a veto.
        'marginal_recommendation': bool(
            recommended is not None and recommended['transfers']
            and recommended['gain'] < DECISION_MARGIN),
        'current_lineup': lineup_payload(
            baseline_result, float(current['value_m'].sum())),
    }


def squad_records(frame: pd.DataFrame) -> list:
    """Rows as plain dicts, for JSON and for templates.

    Includes `element` when present so API rows have stable identity within a
    prediction export. FPL element ids are season-scoped, so callers must
    verify the season roster before joining them to another dataset.
    """
    cols = [c for c in ('element', 'name', 'team', 'position', 'opponent_team', 'was_home',
                        'value_m', 'predicted_points', 'points_per_million',
                        'selected_by', 'status', 'has_prior_history')
            if c in frame.columns]
    out = []
    for record in frame[cols].to_dict('records'):
        clean = {}
        for key, value in record.items():
            if isinstance(value, (np.integer,)):
                clean[key] = int(value)
            elif isinstance(value, (np.floating,)):
                clean[key] = round(float(value), 3)
            elif isinstance(value, (np.bool_,)):
                clean[key] = bool(value)
            else:
                clean[key] = value
        out.append(clean)
    return out


def lineup_payload(result: dict, budget: float) -> dict:
    shape = result['xi']['position'].value_counts()
    xi = result['xi']
    captain = result.get('captain')
    vice_captain = result.get('vice_captain')
    xi_points = float(xi['predicted_points'].sum())
    return {
        'ok': True,
        'budget': float(budget),
        'spend': round(float(result['squad']['value_m'].sum()), 1),
        'xi': squad_records(xi),
        'bench': squad_records(result['bench']),
        'captain': None if captain is None else squad_records(pd.DataFrame([captain]))[0],
        'vice_captain': None if vice_captain is None else squad_records(pd.DataFrame([vice_captain]))[0],
        'xi_points': round(xi_points, 2),
        'formation': (f"{int(shape.get('DEF', 0))}-{int(shape.get('MID', 0))}-"
                      f"{int(shape.get('FWD', 0))}"),
    }


def suggest_transfers(current: pd.DataFrame, players: pd.DataFrame,
                      free: int, bank: float, max_transfers: int) -> None:
    try:
        data = compute_transfers(current, players, free, bank, max_transfers)
    except ValueError as exc:
        raise SystemExit(str(exc))

    print(f"\n  squad value {data['squad_value']:.1f}m + bank {data['bank']:.1f}m "
          f"= {data['budget']:.1f}m to spend")
    print(f"  {data['free']} free transfer(s); each extra costs "
          f"{data['hit_cost']} points\n")

    for failure in data['failures']:
        print(f"  {failure['transfers']} transfers: no legal squad "
              f"({failure['status']})")

    if not data['rows']:
        raise SystemExit("no legal squad found at any transfer count")

    print(f"  {'moves':<7}{'gross':>8}{'hit':>6}{'net':>8}{'vs 0':>8}{'marginal':>11}")
    print("  " + "-" * 51)
    for row in data['rows']:
        marginal = '--' if row['marginal'] is None else f"{row['marginal']:+.2f}"
        print(f"  {row['transfers']:<7}{row['gross']:>8.2f}{row['hit']:>6}"
              f"{row['net']:>8.2f}{row['gain']:>+8.2f}{marginal:>11}")

    best = data['best']
    recommended = data['recommended']
    print(f"\n  raw optimum: {best['transfers']} transfer(s), "
          f"net {best['net']:.2f} ({best['gain']:+.2f} vs standing pat)")
    print(f"  recommendation: {recommended['transfers']} transfer(s), "
          f"net {recommended['net']:.2f}")
    if recommended['transfers']:
        print(f"    OUT  {recommended['out']}")
        print(f"    IN   {recommended['in']}")
    if recommended['transfers'] != best['transfers']:
        print(f"\n  The extra {best['transfers'] - recommended['transfers']} move(s) cost a hit "
              f"and add only {data['recommendation_edge']:.2f} net points, inside the "
              f"model's {data['decision_margin']:.1f}-point decision margin.")
    if data['marginal_recommendation']:
        print(f"\n  This gain is itself under {data['decision_margin']:.1f} points, "
              "inside the model's error (test MAE ~1.0/player).")
        print("  Rolling the transfer is defensible.")


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------
def fixture_calendar(season: str, first_gw: int, horizon: int) -> pd.DataFrame:
    """Fixtures per team per gameweek, with average difficulty."""
    path = os.path.join('data', season, 'fixtures.csv')
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found")

    fixtures = pd.read_csv(path)
    window = fixtures[(fixtures['event'] >= first_gw) &
                      (fixtures['event'] < first_gw + horizon)]
    if window.empty:
        raise SystemExit(f"no fixtures between GW{first_gw} and "
                         f"GW{first_gw + horizon - 1}")

    rows = []
    for _, fix in window.iterrows():
        rows.append({'event': int(fix['event']), 'team': int(fix['team_h']),
                     'difficulty': fix.get('team_h_difficulty', 3), 'home': True})
        rows.append({'event': int(fix['event']), 'team': int(fix['team_a']),
                     'difficulty': fix.get('team_a_difficulty', 3), 'home': False})
    per_team = pd.DataFrame(rows)
    return (per_team.groupby(['event', 'team'])
            .agg(fixtures=('difficulty', 'size'),
                 difficulty=('difficulty', 'mean'))
            .reset_index())


def best_legal_xi_points(squad: pd.DataFrame) -> float | None:
    """Points from the best XI this squad can legally field.

    Not the same as the top eleven by predicted points, which is what this used
    to compare against: that ignores formation, so it happily fields no
    goalkeeper and five forwards. The number came out above what a legal XI can
    reach, and the wildcard gap then printed as negative -- "your squad is
    -0.48 points off optimal", which reads as nonsense because it is.

    Solving with squad_size = len(squad) forces every player in, leaving the LP
    to choose only the XI, under the same formation rules as everywhere else.
    """
    if squad is None or len(squad) < XI_SIZE:
        return None
    result, _status = solve_squad(
        squad, budget=float(squad['value_m'].sum()) + 1.0,
        squad_size=len(squad), captain=False)
    if result is None:
        # An illegal 15 (wrong shape, or four from one club) cannot field a
        # legal XI either. Better to say nothing than to invent a number.
        return None
    return float(result['xi']['predicted_points'].sum())


CHIP_IDS = ('triple_captain', 'bench_boost', 'free_hit', 'wildcard')
CHIP_LABELS = {
    'triple_captain': 'Triple Captain',
    'bench_boost': 'Bench Boost',
    'free_hit': 'Free Hit',
    'wildcard': 'Wildcard',
}
CHIP_METHOD_VERSION = '1.0'


def _availability_factor(players: pd.DataFrame) -> pd.Series:
    factor = pd.Series(1.0, index=players.index)
    if 'status' in players.columns:
        factor = factor.where(~players['status'].isin({'i', 'u', 's', 'n'}), 0.0)
    for column in ('p_plays', 'chance', 'chance_of_playing_next_round'):
        if column in players.columns:
            values = pd.to_numeric(players[column], errors='coerce')
            if column.startswith('chance'):
                values = values / 100.0
            factor = values.fillna(factor).clip(lower=0.0, upper=1.0)
            break
    return factor


def _player_key(row: pd.Series) -> str | int:
    if 'element' in row.index and pd.notna(row['element']):
        return int(row['element'])
    return str(row.get('name', ''))


def _align_squad_to_players(players: pd.DataFrame, squad: pd.DataFrame) -> pd.DataFrame:
    player_indexes = {}
    for index, row in players.iterrows():
        key = _player_key(row)
        if key in player_indexes:
            raise ValueError(f'duplicate player identity: {key}')
        player_indexes[key] = index

    aligned = squad.copy()
    aligned_indexes = []
    for _, row in aligned.iterrows():
        key = _player_key(row)
        if key not in player_indexes:
            raise ValueError(f'squad player is not in the market: {key}')
        aligned_indexes.append(player_indexes[key])
    if len(set(aligned_indexes)) != len(aligned_indexes):
        raise ValueError('the same player appears twice in that squad')
    aligned.index = aligned_indexes
    return aligned


def _bench_evidence(bench: pd.DataFrame) -> list[dict]:
    evidence = []
    availability = _availability_factor(bench)
    for index, row in bench.iterrows():
        points = float(pd.to_numeric(row.get('predicted_points', 0), errors='coerce') or 0)
        is_available = bool(availability.loc[index] > 0)
        evidence.append({
            'player': str(row.get('name', '')),
            'element': _player_key(row),
            'points': round(points, 2),
            'available': is_available,
        })
    return evidence


def _result_total(result: dict) -> float:
    total = float(result['xi']['predicted_points'].sum())
    if result.get('captain') is not None:
        total += float(result['captain']['predicted_points'])
    return total


def _horizon_week_total(week: dict, point_matrix: pd.DataFrame, gameweek: int) -> float:
    total = float(point_matrix.loc[week['xi'].index, gameweek].sum())
    if week.get('captain') is not None:
        total += float(point_matrix.loc[week['captain'].name, gameweek])
    return total


def _projection_matrix(players: pd.DataFrame, calendar: pd.DataFrame,
                       gameweeks: list[int], name_to_id: dict,
                       future_points: pd.DataFrame | None = None) -> tuple[pd.DataFrame, str]:
    if future_points is not None:
        candidate = future_points.reindex(index=players.index, columns=gameweeks)
        numeric = candidate.apply(pd.to_numeric, errors='coerce')
        if not numeric.empty and numeric.notna().all().all():
            matrix = numeric.fillna(0.0).mul(_availability_factor(players), axis=0)
            return matrix, 'model_projection'
    return pd.DataFrame(index=players.index, columns=gameweeks, dtype=float), 'fixture_signal'


def _candidate_window(first_gw: int, horizon: int, chip: str,
                      inventory: dict, scheduled: list,
                      last_free_hit: int | None) -> tuple[list, str, str]:
    gameweeks = list(range(first_gw, first_gw + horizon))
    half = 'first_half' if first_gw <= 19 else 'second_half'
    expires = '19' if half == 'first_half' else '38'
    state = inventory.get(half, {}).get(chip, 'unknown')
    if state in {'used', 'expired'}:
        return [], half, expires
    eligible = [gw for gw in gameweeks if (gw <= 19 if half == 'first_half' else gw >= 20)]
    eligible = [gw for gw in eligible if gw not in scheduled]
    if chip == 'free_hit':
        eligible = [gw for gw in eligible if gw > 1]
        if last_free_hit is not None:
            eligible = [gw for gw in eligible if gw != last_free_hit + 1]
    return eligible, half, expires


def _recommendation(chip: str, scores: dict, breakdowns: dict,
                    fixture_indexes: dict, candidate_gameweeks: list,
                    inventory: dict, has_squad: bool, half: str,
                    expires: str, projection_mode: str, current_gameweek: int,
                    policy: ChipDecisionPolicy) -> dict:
    label = CHIP_LABELS[chip]
    state = inventory.get(half, {}).get(chip, 'unknown')
    warnings = []
    inventory_synced = inventory.get('_synced') is True
    if not inventory_synced:
        warnings.append('Chip history is not synced; confirm this chip is still available.')

    base = {
        'chip': chip, 'label': label, 'projection_mode': projection_mode,
        'candidate_gameweeks': [],
        'gw': None, 'candidate_gw': None, 'projected_gain': None,
        'fixture_signal_index': None,
        'alternatives': [], 'runner_up_gameweek': None,
        'gap_to_runner_up': None, 'evidence': None,
        'decision_policy': policy.as_dict(), 'confidence': 'low',
        'reasons': [], 'warnings': warnings,
        'inventory_set': half, 'expires_after_gameweek': int(expires),
    }
    if state in {'used', 'expired'}:
        base.update(status='unavailable', reasons=[f'{label} is marked {state}.'])
        return base
    if not candidate_gameweeks:
        warnings.append(f'No eligible {label} gameweek remains in this horizon.')
        base.update(status='hold', reasons=[f'No eligible {label} window in this horizon.'])
        return base

    fixture_only = projection_mode == 'fixture_signal' or not has_squad
    values = fixture_indexes if fixture_only else scores
    ranked = sorted(
        candidate_gameweeks,
        key=lambda gw: (values.get(gw) is not None,
                        values.get(gw) if values.get(gw) is not None else float('-inf'),
                        -gw),
        reverse=True,
    )
    alternatives = []
    for gw in ranked[:3]:
        gain = scores.get(gw) if projection_mode == 'model_projection' else None
        alternatives.append({
            'chip': chip,
            'gw': int(gw),
            'projected_gain': None if gain is None else round(float(gain), 2),
            'fixture_signal_index': (
                round(float(fixture_indexes[gw]), 2)
                if projection_mode == 'fixture_signal' and fixture_indexes.get(gw) is not None
                else None
            ),
            'evidence': None if fixture_only else {'chip': chip, **breakdowns.get(gw, {})},
        })

    best_gw = ranked[0]
    gain = scores.get(best_gw) if not fixture_only else None
    status = policy.status(
        gain, current_gameweek=best_gw == current_gameweek,
        inventory_synced=inventory_synced,
        model_projection=projection_mode == 'model_projection' and has_squad,
        has_complete_squad=has_squad,
    )
    second = alternatives[1] if len(alternatives) > 1 else None
    gap = None
    if second is not None:
        best_value = values.get(best_gw)
        second_value = values.get(second['gw'])
        if best_value is not None and second_value is not None:
            gap = round(float(best_value - second_value), 2)

    evidence = None if fixture_only else {'chip': chip, **breakdowns.get(best_gw, {})}
    if fixture_only:
        formula = None
    elif chip == 'triple_captain':
        formula = 'One additional copy of the selected captain projection.'
    elif chip == 'bench_boost':
        formula = 'The sum of the four ordered bench player projections.'
    elif chip == 'free_hit':
        formula = 'Optimized legal XI and captain total minus the current XI and captain total.'
    else:
        formula = 'Optimized persistent squad total minus the current squad total over the remaining horizon.'

    if fixture_only:
        reason = f'GW{best_gw} has the strongest fixture signal; complete squad projections are needed to quantify gain.'
    elif status == 'play':
        reason = f'{label} clears the {policy.minimum_projected_gain:.1f}-point policy margin in the current gameweek.'
    elif status == 'hold':
        reason = f'Projected gain is below the {policy.minimum_projected_gain:.1f}-point policy margin.'
    elif best_gw != current_gameweek:
        reason = f'GW{best_gw} is a future candidate; chip decisions are held until that gameweek.'
    elif not inventory_synced:
        reason = 'Current-week gain is provisional until chip inventory is synced.'
    else:
        reason = 'A complete squad and current-week decision are needed for a play recommendation.'

    base.update({
        'status': status,
        'candidate_gameweeks': [candidate['gw'] for candidate in alternatives],
        'gw': best_gw if status == 'play' else None,
        'candidate_gw': best_gw,
        'projected_gain': None if gain is None else round(float(gain), 2),
        'fixture_signal_index': (
            round(float(fixture_indexes[best_gw]), 2)
            if fixture_only and fixture_indexes.get(best_gw) is not None
            else None
        ),
        'alternatives': alternatives,
        'runner_up_gameweek': None if second is None else second['gw'],
        'gap_to_runner_up': gap,
        'evidence': evidence,
        'formula': formula,
        'reasons': [reason],
        'confidence': 'medium' if status == 'play' else 'low',
    })
    return base


def compute_chips(squad, season: str, first_gw: int, horizon: int,
                  players: pd.DataFrame, inventory: dict | None = None,
                  scheduled_gameweeks: list | None = None,
                  last_free_hit_gameweek: int | None = None,
                  future_points: pd.DataFrame | None = None,
                  projection_generated_at: str | None = None) -> dict:
    players = players.copy()
    if not players.index.is_unique:
        players = players.reset_index(drop=True)
    if squad is not None:
        squad = _align_squad_to_players(players, squad)
    teams = pd.read_csv(os.path.join('data', season, 'teams.csv'))
    name_to_id = dict(zip(teams['name'], teams['id']))
    calendar = fixture_calendar(season, first_gw, horizon)
    gameweeks = list(range(first_gw, first_gw + horizon))
    counts = calendar.pivot_table(index='event', columns='team', values='fixtures', fill_value=0)
    counts = counts.reindex(index=gameweeks, columns=teams['id'].tolist(), fill_value=0)
    counts = counts.fillna(0)
    doubles = {gw: [int(team) for team in counts.loc[gw].index if counts.loc[gw, team] >= 2]
               for gw in gameweeks}
    blanks = {gw: [int(team) for team in counts.loc[gw].index if counts.loc[gw, team] == 0]
              for gw in gameweeks}
    any_dgw = any(doubles.values())
    any_bgw = any(blanks.values())

    squad_teams = None
    unmapped = []
    has_squad = squad is not None and len(squad) == SQUAD_SIZE
    if has_squad:
        squad_teams = squad['team'].map(name_to_id)
        if squad_teams.isna().any():
            unmapped = sorted(squad.loc[squad_teams.isna(), 'team'].unique())

    rows = []
    for gw in gameweeks:
        gw_counts = counts.loc[gw]
        gw_fixtures = calendar[calendar['event'] == gw]
        gw_diff = gw_fixtures.set_index('team')['difficulty']
        entry = {
            'gw': int(gw), 'matches': int(gw_counts.sum() // 2),
            'dgw_teams': len(doubles[gw]), 'blank_teams': len(blanks[gw]),
        }
        if squad_teams is not None:
            played = squad_teams.map(gw_counts).fillna(0)
            entry['squad_playing'] = int((played > 0).sum())
            entry['squad_blanks'] = int((played == 0).sum())
            squad_diffs = squad_teams.map(gw_diff).dropna()
            entry['avg_fdr'] = round(float(squad_diffs.mean()) if len(squad_diffs) else 3.0, 2)
        else:
            entry['avg_fdr'] = round(float(gw_diff.mean()) if len(gw_diff) else 3.0, 2)
        rows.append(entry)

    supplied_inventory = inventory if isinstance(inventory, dict) else {}
    normalized_inventory = {'first_half': {}, 'second_half': {}, '_synced': bool(inventory)}
    for half in ('first_half', 'second_half'):
        source = supplied_inventory.get(half, {})
        for chip in CHIP_IDS:
            value = source.get(chip, 'unknown') if isinstance(source, dict) else 'unknown'
            if value is True:
                value = 'used'
            elif value is False:
                value = 'unused'
            normalized_inventory[half][chip] = value if value in {'unused', 'used', 'expired'} else 'unknown'

    scheduled = sorted({int(gw) for gw in (scheduled_gameweeks or [])})
    candidate_windows = {}
    for chip in CHIP_IDS:
        candidate_windows[chip] = _candidate_window(
            first_gw, horizon, chip, normalized_inventory, scheduled,
            last_free_hit_gameweek)

    point_matrix, projection_mode = _projection_matrix(
        players, calendar, gameweeks, name_to_id, future_points)
    scores = {chip: {} for chip in CHIP_IDS}
    breakdowns = {chip: {} for chip in CHIP_IDS}
    fixture_indexes = {chip: {} for chip in CHIP_IDS}
    current_totals = {}
    squad_budget = float(squad['value_m'].sum()) if has_squad else None
    policy = ChipDecisionPolicy(
        minimum_projected_gain=DECISION_MARGIN,
        uncertainty_note='Player point projections have model error; the decision margin is a conservative product policy.',
    )

    for gw in gameweeks:
        if projection_mode == 'fixture_signal' or not has_squad:
            row = rows[gw - first_gw]
            signal = row['dgw_teams'] * 1.5 + row['blank_teams'] * 1.25
            signal += max(0.0, 3.0 - row['avg_fdr'])
            fixture_indexes['triple_captain'][gw] = round(signal + row['dgw_teams'], 2)
            fixture_indexes['bench_boost'][gw] = round(signal + row['dgw_teams'] * 2, 2)
            fixture_indexes['free_hit'][gw] = round(signal + row['blank_teams'] * 2, 2)
            fixture_indexes['wildcard'][gw] = round(signal + max(0.0, row['avg_fdr'] - 3.0), 2)
            for chip in CHIP_IDS:
                breakdowns[chip][gw] = {'chip': chip, 'fixture_signal_index': fixture_indexes[chip][gw]}
            continue

        adjusted_squad = squad.copy()
        adjusted_squad['predicted_points'] = point_matrix.loc[squad.index, gw].to_numpy()
        current_budget = float(squad['value_m'].sum())
        current_result, _status = solve_squad(
            adjusted_squad, current_budget + 0.01, squad_size=len(squad),
            bench_weight=0.0, captain=True)
        if current_result is None:
            continue
        current_xi = float(current_result['xi']['predicted_points'].sum())
        captain = current_result.get('captain')
        captain_points = None if captain is None else float(captain['predicted_points'])
        captain_team_id = None if captain is None else name_to_id.get(captain['team'])
        captain_fixture_rows = calendar[(calendar['event'] == gw) &
                                        (calendar['team'] == captain_team_id)]
        captain_fixtures = 0 if captain_fixture_rows.empty else int(
            captain_fixture_rows['fixtures'].sum())
        bench = current_result['bench']
        current_total = _result_total(current_result)
        current_totals[gw] = current_total

        triple_total = None if captain_points is None else current_xi + captain_points * 3
        scores['triple_captain'][gw] = captain_points
        breakdowns['triple_captain'][gw] = {
            'chip': 'triple_captain',
            'captain': None if captain is None else {
                'element': _player_key(captain),
                'name': str(captain.get('name', '')),
                'team': str(captain.get('team', '')),
                'position': str(captain.get('position', '')),
                'projected_points': round(captain_points, 2),
                'fixtures': captain_fixtures,
                'available': bool(captain_points and captain_points > 0),
            },
            'normal_captain_total': round(current_total, 2),
            'triple_captain_total': None if triple_total is None else round(triple_total, 2),
            'incremental_gain': None if captain_points is None else round(captain_points, 2),
        }

        bench_players = _bench_evidence(bench)
        bench_total = float(bench['predicted_points'].sum())
        scores['bench_boost'][gw] = bench_total
        breakdowns['bench_boost'][gw] = {
            'chip': 'bench_boost',
            'ordered_bench': bench_players,
            'bench_total': round(bench_total, 2),
        }

        optimized = solve_squad(
            players.assign(predicted_points=point_matrix[gw]),
            current_budget + 0.01, squad_size=SQUAD_SIZE,
            bench_weight=0.0, captain=True)[0]
        optimized_xi = None if optimized is None else float(
            optimized['xi']['predicted_points'].sum())
        optimized_total = None if optimized is None else _result_total(optimized)
        optimized_captain = (
            None if optimized is None or optimized.get('captain') is None
            else float(optimized['captain']['predicted_points']))
        current_captain = (
            None if current_result.get('captain') is None
            else float(current_result['captain']['predicted_points']))
        current_elements = {_player_key(row) for _, row in squad.iterrows()}
        optimized_elements = set() if optimized is None else {
            _player_key(row) for _, row in optimized['squad'].iterrows()}
        changed_count = len(current_elements - optimized_elements)
        free_hit_gain = None if optimized_total is None else optimized_total - current_total
        scores['free_hit'][gw] = free_hit_gain
        breakdowns['free_hit'][gw] = {
            'chip': 'free_hit',
            'current_xi_captain_total': round(current_total, 2),
            'optimized_xi_captain_total': None if optimized_total is None else round(optimized_total, 2),
            'raw_delta': None if free_hit_gain is None else round(free_hit_gain, 2),
            'current_xi_total': round(current_xi, 2),
            'optimized_xi_total': None if optimized_xi is None else round(optimized_xi, 2),
            'current_captain_points': current_captain,
            'optimized_captain_points': optimized_captain,
            'changed_player_count': changed_count,
        }

    if has_squad and squad_budget is not None and projection_mode == 'model_projection':
        for gw in gameweeks:
            remaining = [future_gw for future_gw in gameweeks if future_gw >= gw]
            current_cumulative = sum(current_totals.get(future_gw, 0.0) for future_gw in remaining)
            wildcard_result, _status = solve_squad_horizon(
                players, point_matrix.loc[:, remaining], squad_budget,
                horizon_weights(remaining, 1.0), bench_weight=0.0)
            if wildcard_result is None:
                continue
            optimized_cumulative = sum(
                _horizon_week_total(wildcard_result['weeks'][future_gw], point_matrix, future_gw)
                for future_gw in remaining)
            weekly_deltas = {
                int(future_gw): round(
                    _horizon_week_total(wildcard_result['weeks'][future_gw], point_matrix, future_gw)
                    - current_totals.get(future_gw, 0.0), 2)
                for future_gw in remaining
            }
            current_elements = {_player_key(row) for _, row in squad.iterrows()}
            optimized_elements = {
                _player_key(row) for _, row in wildcard_result['squad'].iterrows()}
            scores['wildcard'][gw] = optimized_cumulative - current_cumulative
            breakdowns['wildcard'][gw] = {
                'chip': 'wildcard',
                'current_cumulative_total': round(current_cumulative, 2),
                'optimized_cumulative_total': round(optimized_cumulative, 2),
                'weekly_deltas': weekly_deltas,
                'horizon_length': len(remaining),
                'changed_player_count': len(current_elements - optimized_elements),
            }

    recommendations = []
    for chip in CHIP_IDS:
        eligible, half, expires = candidate_windows[chip]
        recommendation = _recommendation(
            chip, scores[chip], breakdowns[chip], fixture_indexes[chip],
            eligible, normalized_inventory, has_squad, half, expires,
            projection_mode, first_gw, policy)
        recommendations.append(recommendation)

    for row in rows:
        gw = row['gw']
        row['projected_gain'] = {
            chip: None if scores[chip].get(gw) is None else round(scores[chip][gw], 2)
            for chip in CHIP_IDS
        }
        row['fixture_signal_index'] = {
            chip: fixture_indexes[chip].get(gw)
            for chip in CHIP_IDS
        }

    projection_gameweeks = [] if future_points is None else sorted(
        int(gw) for gw in future_points.columns if pd.notna(gw))
    evaluated_horizon = sum(gw in projection_gameweeks for gw in gameweeks)
    coverage_warning = None
    if projection_mode != 'model_projection':
        if projection_gameweeks:
            coverage_warning = (
                f'Projection export covers {evaluated_horizon} of {horizon} requested weeks; '
                'player point gains are withheld.')
        else:
            coverage_warning = 'No multi-gameweek projection matrix is available; player point gains are withheld.'
    return {
        'first_gw': first_gw, 'last_gw': first_gw + horizon - 1,
        'current_gameweek': first_gw, 'any_dgw': any_dgw, 'any_bgw': any_bgw,
        'rows': rows, 'recommendations': recommendations,
        'unmapped_teams': unmapped, 'has_squad': has_squad,
        'projection_mode': projection_mode,
        'projection_source': 'prediction export' if projection_gameweeks else 'unavailable',
        'projection_generated_at': projection_generated_at,
        'projection_gameweeks': projection_gameweeks,
        'requested_horizon': horizon,
        'evaluated_horizon': evaluated_horizon,
        'coverage_warning': coverage_warning,
        'data_quality': 'complete_horizon' if projection_mode == 'model_projection' else 'fixture_signal_only',
        'methodology_version': CHIP_METHOD_VERSION,
        'decision_policy': policy.as_dict(),
        'inventory_status': 'synced' if normalized_inventory['_synced'] else 'not_synced',
        'inventory_sync_state': 'synced' if normalized_inventory['_synced'] else 'not_synced',
        'scheduled_gameweeks': scheduled,
    }


def chip_advice(squad: pd.DataFrame | None, season: str, first_gw: int,
                horizon: int, players: pd.DataFrame) -> None:
    future_points = None
    try:
        horizon_players, horizon_matrix, _gameweeks = load_horizon(PREDICTIONS)
        identity = 'element' if 'element' in players.columns and 'element' in horizon_players.columns else 'name'
        horizon_matrix.index = horizon_players[identity].to_list()
        future_points = horizon_matrix.reindex(players[identity].to_list())
        future_points.index = players.index
    except SystemExit:
        pass

    data = compute_chips(
        squad, season, first_gw, horizon, players,
        future_points=future_points,
        projection_generated_at=datetime.datetime.fromtimestamp(
            os.path.getmtime(PREDICTIONS), tz=datetime.timezone.utc).isoformat()
            if os.path.exists(PREDICTIONS) else None,
    )

    print(f"\n{'=' * 78}")
    print(f"CHIP TIMING   GW{data['first_gw']}-{data['last_gw']}")
    print("=" * 78)

    if not data['any_dgw'] and not data['any_bgw']:
        print('No double or blank gameweeks are scheduled in this window.')

    print('Projection mode: ' + data['projection_mode'])
    print('Coverage: ' + str(data['projection_gameweeks']))
    if data['coverage_warning']:
        print(data['coverage_warning'])

    if data['unmapped_teams']:
        print(f"\n  could not map teams to ids: {data['unmapped_teams']}")

    print()
    print(pd.DataFrame(data['rows']).to_string(index=False))

    print(f"\n{'-' * 78}")
    print("RECOMMENDATIONS")
    print("-" * 78)
    for rec in data['recommendations']:
        target = f"GW{rec['gw']}" if rec['gw'] else "hold"
        print(f"\n  {rec['chip']} -> {target}")
        print(f"    {rec['reasons'][0]}")


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------
def compute_watchlist(players: pd.DataFrame, max_ownership: float,
                      top: int) -> dict:
    show = ['name', 'team', 'position', 'value_m', 'predicted_points',
            'points_per_million']
    show = [c for c in show if c in players.columns]

    out = {
        'value': squad_records(
            players[players['predicted_points'] > 1].nlargest(top, 'points_per_million')),
        'overpriced': squad_records(
            players[players['value_m'] >= 8].nsmallest(top, 'points_per_million')),
        'differentials': [],
        'no_history': [],
        'has_ownership': 'selected_by' in players.columns,
        'max_ownership': max_ownership,
    }

    if out['has_ownership']:
        owned = pd.to_numeric(players['selected_by'], errors='coerce').fillna(100)
        cheap = players[owned <= max_ownership]
        if len(cheap):
            out['differentials'] = squad_records(cheap.nlargest(top, 'predicted_points'))

    if 'has_prior_history' in players.columns:
        unknown = players[~players['has_prior_history'].astype(bool)]
        if len(unknown):
            out['no_history'] = squad_records(
                unknown.nlargest(min(5, len(unknown)), 'predicted_points'))
            out['no_history_total'] = int(len(unknown))

    return out


def watchlist(players: pd.DataFrame, max_ownership: float, top: int) -> None:
    data = compute_watchlist(players, max_ownership, top)

    print(f"\n{'=' * 78}")
    print("WATCHLIST")
    print("=" * 78)

    def table(records):
        return pd.DataFrame(records).to_string(index=False) if records else '  (none)'

    print("\nBest value (points per million):")
    print(table(data['value']))

    if data['has_ownership']:
        if data['differentials']:
            print(f"\nDifferentials (owned by {data['max_ownership']}% or fewer):")
            print(table(data['differentials']))
    else:
        print(f"\n(ownership not in {PREDICTIONS}; differentials need "
              f"selected_by -- re-run predict_gameweek.py)")

    if data['no_history']:
        print(f"\n{data['no_history_total']} players have no prior data; their "
              f"numbers come from no evidence:")
        print(table(data['no_history']))

    print("\nPriciest players not worth their cost:")
    print(table(data['overpriced']))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--predictions', default=PREDICTIONS)
    ap.add_argument('--season', default=None, help='defaults to the newest in data/')
    sub = ap.add_subparsers(dest='command', required=True)

    p_squad = sub.add_parser('squad', help='best legal 15 under a budget')
    p_squad.add_argument('--budget', type=float, default=100.0)
    p_squad.add_argument('--lock', nargs='+', default=[], help='names to force in')
    p_squad.add_argument('--ban', nargs='+', default=[], help='names to exclude')
    p_squad.add_argument('--horizon', action='store_true',
                         help='pick a squad to hold across every gameweek in the '
                              'predictions file, rather than for the next one '
                              'only. Needs a file written by predict_gameweek.py '
                              '--horizon N.')
    p_squad.add_argument('--decay', type=float, default=1.0, metavar='D',
                         help='how much each further gameweek counts, as D**k. '
                              'Default 1.0 -- every week in the horizon counts '
                              'the same, which backtested better than any '
                              'discount. Below 1.0 favours the near fixtures.')
    p_squad.add_argument('--formation-only-xi', action='store_true',
                         help='pick 11 rather than a 15-man squad')
    p_squad.add_argument('--alternatives', type=int, default=0, metavar='N',
                         help='show N squads the model cannot tell apart, '
                              'instead of the single optimum')
    p_squad.add_argument('--min-changes', type=int,
                         default=MIN_ALTERNATIVE_CHANGES, metavar='K',
                         help=f'how many players must differ before two squads '
                              f'count as different answers '
                              f'(default {MIN_ALTERNATIVE_CHANGES})')
    p_squad.add_argument('--differential', type=float, default=0.0, metavar='P',
                         help='points to dock per percent of ownership per '
                              'player owned, to tilt away from the template. '
                              '0.01 charges a 50%%-owned player half a point')
    p_squad.add_argument('--seed-scale', type=float, default=TIEBREAK_SCALE,
                         metavar='J',
                         help=f'how far a seed may move a pick, in points per '
                              f'player (default {TIEBREAK_SCALE}). Higher means '
                              f'more variety between managers and a larger '
                              f'measured cost')
    p_squad.add_argument('--seed', default=None, metavar='S',
                         help='break ties reproducibly, so two managers on the '
                              'same budget get different squads from the same '
                              'plateau. The points it costs are reported')

    p_tr = sub.add_parser('transfers', help='best transfers from a squad you own')
    p_tr.add_argument('--squad', required=True, help='file of 15 player names')
    p_tr.add_argument('--free', type=int, default=1)
    p_tr.add_argument('--bank', type=float, default=0.0)
    p_tr.add_argument('--max-transfers', type=int, default=3)

    p_chips = sub.add_parser('chips', help='when to play each chip')
    p_chips.add_argument('--squad', default=None)
    p_chips.add_argument('--from-gw', type=int, default=None)
    p_chips.add_argument('--horizon', type=int, default=8)

    p_watch = sub.add_parser('watchlist', help='differentials and value picks')
    p_watch.add_argument('--max-ownership', type=float, default=10.0)
    p_watch.add_argument('--top', type=int, default=10)

    args = ap.parse_args()

    horizon_mode = args.command == 'squad' and getattr(args, 'horizon', False)
    if horizon_mode:
        players, points, gameweeks = load_horizon(args.predictions)
        print(f"{len(players):,} available players from {args.predictions}, "
              f"GW{gameweeks[0]}..GW{gameweeks[-1]}")
    else:
        players = load_predictions(args.predictions)
        print(f"{len(players):,} available players from {args.predictions}")

    season = args.season
    if season is None:
        seasons = sorted(d for d in os.listdir('data') if d[0].isdigit())
        season = seasons[-1]

    if args.command == 'squad':
        lock = read_squad_file_names(args.lock, players) if args.lock else []
        ban = read_squad_file_names(args.ban, players) if args.ban else []
        if horizon_mode:
            weights = horizon_weights(gameweeks, args.decay)
            result, status = solve_squad_horizon(players, points, args.budget,
                                                 weights, locked=lock, banned=ban)
            if result is None:
                raise SystemExit(f"no legal squad at {args.budget}m ({status})")
            show_squad_horizon(result, args.budget, weights)
        else:
            size = XI_SIZE if args.formation_only_xi else SQUAD_SIZE
            steer = dict(squad_size=size, locked=lock, banned=ban,
                         ownership_penalty=args.differential, seed=args.seed,
                         seed_scale=args.seed_scale)
            if args.alternatives:
                data = compute_squad_alternatives(
                    players, args.budget, count=args.alternatives,
                    min_changes=args.min_changes, **steer)
                show_squad_alternatives(data)
            else:
                result, status = solve_squad(players, args.budget, **steer)
                if result is None:
                    raise SystemExit(f"no legal squad at {args.budget}m ({status})")
                show_squad(result, args.budget)
                report_steering_cost(players, args.budget, result, steer)

    elif args.command == 'transfers':
        current = read_squad_file(args.squad, players)
        if len(current) != SQUAD_SIZE:
            print(f"\n  note: squad file resolved {len(current)} players, "
                  f"not {SQUAD_SIZE}")
        suggest_transfers(current, players, args.free, args.bank,
                          args.max_transfers)

    elif args.command == 'chips':
        squad = read_squad_file(args.squad, players) if args.squad else None
        first = args.from_gw
        if first is None:
            first = infer_next_gameweek(season)
        chip_advice(squad, season, first, args.horizon, players)

    elif args.command == 'watchlist':
        watchlist(players, args.max_ownership, args.top)

    return 0


def read_squad_file_names(names, players: pd.DataFrame):
    """Resolve --lock/--ban names to row indices."""
    lowered = players['name'].str.lower()
    out = []
    for entry in names:
        hits = players[lowered.str.contains(entry.lower(), regex=False)]
        if hits.empty:
            raise SystemExit(f"no player matching {entry!r}")
        out.append(hits.index[0])
    return out


def infer_next_gameweek(season: str) -> int:
    """First gameweek with no result yet."""
    path = os.path.join('data', season, 'fixtures.csv')
    fixtures = pd.read_csv(path)
    unplayed = fixtures[~fixtures['finished'].astype(bool)]
    if unplayed.empty:
        return int(fixtures['event'].max())
    return int(unplayed['event'].min())


if __name__ == '__main__':
    sys.exit(main())
