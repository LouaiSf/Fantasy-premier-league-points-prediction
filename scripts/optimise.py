"""Turn predicted points into FPL decisions.

predict_gameweek.py answers "how many points is each player worth". This
answers the questions an actual manager has: which fifteen to own, which
eleven to start, who to captain, which transfers to make, and when to play
each chip.

Everything is a single integer program per question, so the answers are
genuinely optimal under the stated constraints rather than greedy picks.

Subcommands
-----------
    squad       the best legal 15 under a budget, with XI, bench and captain
    transfers   the best N transfers out of a squad you already own
    chips       when to play Triple Captain, Bench Boost, Free Hit, Wildcard
    watchlist   differentials, value picks, and who to avoid

Usage
-----
    python scripts/optimise.py squad --budget 100
    python scripts/optimise.py squad --budget 83 --formation-only-xi
    python scripts/optimise.py transfers --squad my_squad.txt --free 1 --bank 0.5
    python scripts/optimise.py chips --squad my_squad.txt --horizon 8
    python scripts/optimise.py watchlist --max-ownership 10

A squad file is one player name per line; blank lines and #comments ignored.
Names are matched case-insensitively against the prediction output, so a
surname is usually enough.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

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
    if drop_unavailable and 'status' in df.columns:
        df = df[~df['status'].isin({'i', 'u', 's', 'n'})]

    # One row per player. A double gameweek would otherwise let the optimiser
    # buy the same player twice.
    df = df.sort_values('predicted_points', ascending=False).drop_duplicates('name')
    return df.reset_index(drop=True)


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
def solve_squad(players: pd.DataFrame, budget: float, *, squad_size: int = SQUAD_SIZE,
                locked=None, banned=None, must_transfer_out=None,
                bench_weight: float = BENCH_WEIGHT, captain: bool = True):
    """Best legal squad, the XI inside it, and who to captain -- one program.

    Picking fifteen and then picking eleven separately gives a worse answer
    than deciding both together: the value of a player depends on whether he
    starts, and the value of a cheap bench depends on what it frees up for the
    XI. Both sets of binaries live in the same problem, tied by xi <= squad.
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
    problem += objective

    for i in idx:
        problem += in_xi[i] <= in_squad[i]
        problem += is_cap[i] <= in_xi[i]

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

    problem.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[problem.status]
    if status != 'Optimal':
        return None, status

    chosen = [i for i in idx if in_squad[i].value() > 0.5]
    starters = [i for i in idx if in_xi[i].value() > 0.5]
    skipper = [i for i in idx if is_cap[i].value() > 0.5]
    return {
        'squad': players.loc[chosen],
        'xi': players.loc[starters],
        'bench': players.loc[[i for i in chosen if i not in starters]],
        'captain': players.loc[skipper[0]] if skipper else None,
    }, status


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
        print(f"  expected total   {xi_points + cap_bonus:>6.2f}")
    if len(bench):
        print(f"  bench            {bench['predicted_points'].sum():>6.2f} "
              f"(only scores on Bench Boost)")


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------
def compute_transfers(current: pd.DataFrame, players: pd.DataFrame,
                      free: int, bank: float, max_transfers: int) -> dict:
    """Best move for each transfer count, net of the points hit.

    More transfers always buy at least as many raw points, so comparing them
    only means something after the -4 per extra transfer is charged. Every
    count is returned so a marginal second or third transfer is visible rather
    than assumed.

    Returns data only. suggest_transfers() prints it; the web layer renders the
    same structure, so the two can never drift.
    """
    budget = current['value_m'].sum() + bank
    keep_idx = [i for i in current.index]

    baseline = None
    rows = []
    failures = []
    for count in range(0, max_transfers + 1):
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
        if baseline is None:
            baseline = gross

        out = current[~current['name'].isin(result['squad']['name'])]
        into = result['squad'][~result['squad']['name'].isin(current['name'])]
        rows.append({
            'transfers': count,
            'gross': round(float(gross), 2),
            'hit': int(hit),
            'net': round(float(gross - hit), 2),
            'gain': round(float(gross - hit - baseline), 2),
            'out': list(out['name']),
            'in': list(into['name']),
            'squad': squad_records(result['squad']),
            'xi': squad_records(result['xi']),
        })

    best = max(rows, key=lambda r: r['net']) if rows else None
    return {
        'squad_value': round(float(current['value_m'].sum()), 1),
        'bank': round(float(bank), 1),
        'budget': round(float(budget), 1),
        'free': int(free),
        'hit_cost': HIT_COST,
        'rows': rows,
        'failures': failures,
        'best': best,
    }


def squad_records(frame: pd.DataFrame) -> list:
    """Rows as plain dicts, for JSON and for templates."""
    cols = [c for c in ('name', 'team', 'position', 'opponent_team', 'was_home',
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


def suggest_transfers(current: pd.DataFrame, players: pd.DataFrame,
                      free: int, bank: float, max_transfers: int) -> None:
    data = compute_transfers(current, players, free, bank, max_transfers)

    print(f"\n  squad value {data['squad_value']:.1f}m + bank {data['bank']:.1f}m "
          f"= {data['budget']:.1f}m to spend")
    print(f"  {data['free']} free transfer(s); each extra costs "
          f"{data['hit_cost']} points\n")

    for failure in data['failures']:
        print(f"  {failure['transfers']} transfers: no legal squad "
              f"({failure['status']})")

    if not data['rows']:
        raise SystemExit("no legal squad found at any transfer count")

    print(f"  {'moves':<7}{'gross':>8}{'hit':>6}{'net':>8}{'vs 0':>8}")
    print("  " + "-" * 40)
    for row in data['rows']:
        print(f"  {row['transfers']:<7}{row['gross']:>8.2f}{row['hit']:>6}"
              f"{row['net']:>8.2f}{row['gain']:>+8.2f}")

    best = max(rows, key=lambda r: r['net'])
    print(f"\n  best: {best['transfers']} transfer(s), "
          f"net {best['net']:.2f} ({best['gain']:+.2f} vs standing pat)")
    if best['transfers']:
        print(f"    OUT  {best['out']}")
        print(f"    IN   {best['in']}")
    if best['gain'] < 1.0 and best['transfers']:
        print("\n  A gain under a point is inside this model's error "
              "(test MAE ~1.0/player).")
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


def compute_chips(squad, season: str, first_gw: int, horizon: int,
                  players: pd.DataFrame) -> dict:
    """Fixture-driven chip timing over a window of gameweeks.

    Returns data only, so the CLI and the web layer render the same numbers.

    One honest caveat travels with this: the model's per-player prediction does
    not vary by gameweek. Its features are current form, and the opponent
    features were measured and dropped for adding nothing. So the variation
    below comes from fixture count and difficulty, not from the model -- this
    is a fixture ticker with a form weighting, not a per-gameweek projection.
    """
    teams = pd.read_csv(os.path.join('data', season, 'teams.csv'))
    name_to_id = dict(zip(teams['name'], teams['id']))

    calendar = fixture_calendar(season, first_gw, horizon)
    counts = calendar.pivot_table(index='event', columns='team',
                                  values='fixtures', fill_value=0)

    doubles = {int(gw): [int(t) for t in row.index if row[t] >= 2]
               for gw, row in counts.iterrows()}
    blanks = {int(gw): [int(t) for t in row.index if row[t] == 0]
              for gw, row in counts.iterrows()}
    any_dgw = any(doubles.values())
    any_bgw = any(v for v in blanks.values())

    squad_teams = None
    unmapped = []
    if squad is not None and len(squad):
        squad_teams = squad['team'].map(name_to_id)
        if squad_teams.isna().any():
            unmapped = sorted(squad.loc[squad_teams.isna(), 'team'].unique())
            squad_teams = squad_teams.dropna()

    rows = []
    for gw in sorted(counts.index):
        gw_counts = counts.loc[gw]
        gw_diff = calendar[calendar['event'] == gw].set_index('team')['difficulty']
        # gw_counts is fixtures per team, so each match is counted twice.
        entry = {
            'gw': int(gw),
            'matches': int(gw_counts.sum() // 2),
            'dgw_teams': len(doubles[int(gw)]),
            'blank_teams': len(blanks[int(gw)]),
        }
        if squad_teams is not None and len(squad_teams):
            played = squad_teams.map(gw_counts).fillna(0)
            entry['squad_playing'] = int((played > 0).sum())
            entry['squad_blanks'] = int((played == 0).sum())
            entry['avg_fdr'] = round(float(squad_teams.map(gw_diff).mean()), 2)
        else:
            entry['avg_fdr'] = round(float(gw_diff.mean()), 2)
        rows.append(entry)

    recommendations = []
    if any_dgw:
        best = max(rows, key=lambda r: r['dgw_teams'])
        recommendations.append({
            'chip': 'Bench Boost / Triple Captain', 'gw': best['gw'],
            'reason': f"{best['dgw_teams']} teams play twice",
            'confidence': 'high',
        })
    else:
        if squad_teams is not None and len(squad_teams):
            best = sorted(rows, key=lambda r: (-r['squad_playing'], r['avg_fdr']))[0]
            recommendations.append({
                'chip': 'Bench Boost', 'gw': best['gw'],
                'reason': (f"{best['squad_playing']}/{len(squad)} of your squad play, "
                           f"avg FDR {best['avg_fdr']}"),
                'confidence': 'low',
            })
        easiest = min(rows, key=lambda r: r['avg_fdr'])
        recommendations.append({
            'chip': 'Triple Captain', 'gw': easiest['gw'],
            'reason': f"easiest fixtures, avg FDR {easiest['avg_fdr']}",
            'confidence': 'low',
            'note': 'no double gameweek scheduled -- a fixture call, not a projection',
        })

    if any_bgw:
        worst = max(rows, key=lambda r: r.get('squad_blanks', r['blank_teams']))
        recommendations.append({
            'chip': 'Free Hit', 'gw': worst['gw'],
            'reason': (f"{worst.get('squad_blanks', worst['blank_teams'])} "
                       f"of your squad blank"),
            'confidence': 'high',
        })
    else:
        recommendations.append({
            'chip': 'Free Hit', 'gw': None,
            'reason': 'hold -- its value is covering a blank gameweek, and none '
                      'is scheduled in this window',
            'confidence': 'high',
        })

    hardest = max(rows, key=lambda r: r['avg_fdr'])
    wildcard = {
        'chip': 'Wildcard', 'gw': hardest['gw'],
        'reason': f"hardest run, avg FDR {hardest['avg_fdr']}",
        'confidence': 'low',
    }

    if squad is not None and len(squad):
        optimal, _ = solve_squad(players, squad['value_m'].sum() + 0.5)
        current_xi = best_legal_xi_points(squad)
        if optimal and current_xi is not None:
            gap = float(optimal['xi']['predicted_points'].sum() - current_xi)
            wildcard['squad_gap'] = round(gap, 2)
            wildcard['reason'] += (f"; your squad is {gap:.2f} points off an "
                                   f"optimal one at the same value")
            if gap > 8:
                wildcard['note'] = 'that is a wide gap -- a wildcard would pay for itself'
    recommendations.append(wildcard)

    return {
        'first_gw': first_gw,
        'last_gw': first_gw + horizon - 1,
        'any_dgw': any_dgw,
        'any_bgw': any_bgw,
        'rows': rows,
        'recommendations': recommendations,
        'unmapped_teams': unmapped,
        'has_squad': squad is not None and len(squad) > 0,
    }


def chip_advice(squad: pd.DataFrame | None, season: str, first_gw: int,
                horizon: int, players: pd.DataFrame) -> None:
    data = compute_chips(squad, season, first_gw, horizon, players)

    print(f"\n{'=' * 78}")
    print(f"CHIP TIMING   GW{data['first_gw']}-{data['last_gw']}")
    print("=" * 78)

    if not data['any_dgw'] and not data['any_bgw']:
        print("\n  No double or blank gameweeks are scheduled in this window.")
        print("  They appear only once cup runs force postponements, usually from")
        print("  around GW18. Until then Bench Boost and Free Hit have no fixture")
        print("  edge to aim at, and the ranking below reflects fixture difficulty")
        print("  and your squad's form alone.")

    print("\n  Note: the model's per-player number does not vary by gameweek --")
    print("  its features are current form, and opponent strength was measured")
    print("  and dropped. Ranking below combines that form with fixture count")
    print("  and FDR, which is where the gameweek-to-gameweek signal comes from.")

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
        print(f"    {rec['reason']}")
        if rec.get('note'):
            print(f"    {rec['note']}")


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
    p_squad.add_argument('--formation-only-xi', action='store_true',
                         help='pick 11 rather than a 15-man squad')

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
    players = load_predictions(args.predictions)
    print(f"{len(players):,} available players from {args.predictions}")

    season = args.season
    if season is None:
        seasons = sorted(d for d in os.listdir('data') if d[0].isdigit())
        season = seasons[-1]

    if args.command == 'squad':
        lock = read_squad_file_names(args.lock, players) if args.lock else []
        ban = read_squad_file_names(args.ban, players) if args.ban else []
        size = XI_SIZE if args.formation_only_xi else SQUAD_SIZE
        result, status = solve_squad(players, args.budget, squad_size=size,
                                     locked=lock, banned=ban)
        if result is None:
            raise SystemExit(f"no legal squad at {args.budget}m ({status})")
        show_squad(result, args.budget)

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
