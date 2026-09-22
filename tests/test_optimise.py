from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from optimise import (  # noqa: E402
    annotate_marginals,
    choose_transfer_recommendation,
    compute_squad_alternatives,
    compute_transfers,
    expected_total,
    load_predictions,
    seed_jitter,
    solve_squad,
    squad_ownership,
)


def player(element: int, name: str, team: str, position: str,
           value: float, points: float) -> dict:
    return {
        'element': element,
        'name': name,
        'team': team,
        'position': position,
        'value_m': value,
        'predicted_points': points,
    }


def current_squad() -> pd.DataFrame:
    rows = [
        player(1, 'GK 1', 'A', 'GK', 4.0, 4.0),
        player(2, 'GK 2', 'B', 'GK', 4.0, 3.0),
    ]
    rows += [player(10 + i, f'DEF {i}', chr(67 + i), 'DEF', 5.0, 5.0)
             for i in range(5)]
    rows += [
        player(20, 'Useful premium', 'H', 'MID', 10.0, 8.0),
        player(21, 'Weak budget', 'I', 'MID', 5.0, 2.0),
        player(22, 'MID 2', 'J', 'MID', 5.0, 6.0),
        player(23, 'MID 3', 'K', 'MID', 5.0, 6.0),
        player(24, 'MID 4', 'L', 'MID', 5.0, 6.0),
    ]
    rows += [player(30 + i, f'FWD {i}', chr(77 + i), 'FWD', 5.0, 5.0)
             for i in range(3)]
    return pd.DataFrame(rows)


def test_joint_transfers_can_downgrade_to_fund_a_larger_upgrade() -> None:
    current = current_squad()
    market = pd.concat([
        current,
        pd.DataFrame([
            player(100, 'Cheap enabler', 'P', 'MID', 4.0, 7.0),
            player(101, 'Elite upgrade', 'Q', 'MID', 11.0, 14.0),
        ]),
    ], ignore_index=True)

    result = compute_transfers(current, market, free=2, bank=0.0, max_transfers=2)
    two_moves = next(row for row in result['rows'] if row['transfers'] == 2)

    assert set(two_moves['out']) == {'Useful premium', 'Weak budget'}
    assert set(two_moves['in']) == {'Cheap enabler', 'Elite upgrade'}
    assert result['best']['transfers'] == 2


def test_transfer_rows_include_the_solver_lineup_and_current_lineup() -> None:
    current = current_squad()

    result = compute_transfers(current, current, free=0, bank=0.0, max_transfers=0)
    row = result['rows'][0]

    assert len(row['bench']) == 4
    assert row['captain']['element'] in {player['element'] for player in row['xi']}
    assert row['vice_captain']['element'] in {player['element'] for player in row['xi']}
    assert row['formation'] == result['current_lineup']['formation']
    assert row['spend'] == round(float(current['value_m'].sum()), 1)
    assert row['bank_after'] == 0.0
    assert row['xi_points'] > 0
    assert row['captained_total'] == row['gross']
    assert result['current_lineup']['captain']['element'] == row['captain']['element']
    assert set(result['current_lineup']) == {
        'ok', 'budget', 'spend', 'xi', 'bench', 'captain',
        'vice_captain', 'xi_points', 'formation',
    }
    assert result['current_lineup']['ok'] is True


def test_transfer_constraints_match_players_by_element_not_dataframe_index() -> None:
    current = current_squad()
    # Simulate available-player filtering: one squad player disappears and the
    # remaining market receives a fresh index.
    market = current[current['element'] != 1].reset_index(drop=True)
    market = pd.concat([
        market,
        pd.DataFrame([player(102, 'Replacement GK', 'R', 'GK', 4.0, 5.0)]),
    ], ignore_index=True)

    result = compute_transfers(current, market, free=1, bank=0.0, max_transfers=1)

    assert result['failures'][0]['transfers'] == 0
    assert result['best']['out'] == ['GK 1']
    assert result['best']['in'] == ['Replacement GK']


def test_transfer_plan_counts_zero_one_and_two_are_returned_without_extra_hits() -> None:
    current = current_squad()
    market = pd.concat([
        current,
        pd.DataFrame([
            player(100, 'Cheap enabler', 'P', 'MID', 4.0, 7.0),
            player(101, 'Elite upgrade', 'Q', 'MID', 11.0, 14.0),
        ]),
    ], ignore_index=True)

    result = compute_transfers(current, market, free=2, bank=0.0, max_transfers=2)

    assert [row['transfers'] for row in result['rows']] == [0, 1, 2]
    assert all(row['hit'] == 0 for row in result['rows'])
    assert all(len(row['xi']) == 11 and len(row['bench']) == 4 for row in result['rows'])


def test_recommendation_rejects_a_tiny_edge_for_an_extra_hit() -> None:
    rows = [
        {'transfers': 0, 'net': 55.15, 'hit': 0},
        {'transfers': 1, 'net': 58.09, 'hit': 0},
        {'transfers': 2, 'net': 58.16, 'hit': 4},
        {'transfers': 3, 'net': 57.13, 'hit': 8},
    ]

    best, recommended = choose_transfer_recommendation(rows)

    assert best['transfers'] == 2
    assert recommended['transfers'] == 1


def test_recommendation_keeps_a_tiny_edge_that_costs_no_hit() -> None:
    # Same thin margin, but every move is covered by a free transfer. Nothing
    # is saved by withholding it, so the optimum stands.
    rows = [
        {'transfers': 0, 'net': 55.15, 'hit': 0},
        {'transfers': 1, 'net': 58.09, 'hit': 0},
        {'transfers': 2, 'net': 58.16, 'hit': 0},
    ]

    best, recommended = choose_transfer_recommendation(rows)

    assert best['transfers'] == 2
    assert recommended is best


def test_marginal_is_none_when_the_preceding_count_has_no_row() -> None:
    # Two unavailable players force at least two moves, and three is infeasible
    # here, so the marginal for four moves has nothing directly below it.
    rows = [
        {'transfers': 2, 'net': 58.00},
        {'transfers': 4, 'net': 59.50},
        {'transfers': 5, 'net': 60.25},
    ]

    annotate_marginals(rows)

    assert [row['marginal'] for row in rows] == [None, None, 0.75]


def test_guard_withholds_a_hit_costing_move_end_to_end() -> None:
    current = current_squad()
    market = pd.concat([
        current,
        pd.DataFrame([
            # Worth a free transfer on its own.
            player(200, 'Elite mid', 'P', 'MID', 5.0, 12.0),
            # Worth 4.07 gross, so 0.07 net once the hit is charged.
            player(201, 'Marginal def', 'Q', 'DEF', 5.0, 9.07),
        ]),
    ], ignore_index=True)

    hit = compute_transfers(current, market, free=1, bank=0.0, max_transfers=2)

    assert hit['best']['transfers'] == 2
    assert hit['recommended']['transfers'] == 1
    assert hit['recommendation_edge'] == 0.07
    assert hit['rows'][2]['hit'] == 4

    # The identical squad with a second free transfer keeps both moves: there
    # is no hit to save, so the margin has nothing to protect against.
    free = compute_transfers(current, market, free=2, bank=0.0, max_transfers=2)

    assert free['best']['transfers'] == 2
    assert free['recommended']['transfers'] == 2
    assert free['recommendation_edge'] == 0.0


def test_load_predictions_keeps_two_players_who_share_a_surname(tmp_path) -> None:
    # A double gameweek is one element twice; two Palacios are two players.
    # Keying the de-duplication on the name deleted the lower-scoring one from
    # the market entirely, so a squad holding him could not be resolved.
    path = tmp_path / 'predictions.csv'
    pd.DataFrame([
        {'element': 619, 'name': 'Palacios', 'team': 'Ipswich Town',
         'position': 'MID', 'value_m': 5.0, 'predicted_points': 1.45,
         'status': 'a'},
        {'element': 570, 'name': 'Palacios', 'team': 'Fulham',
         'position': 'MID', 'value_m': 5.4, 'predicted_points': 1.42,
         'status': 'a'},
        # The same element twice, as a double gameweek writes it. Only the
        # higher-scoring row should survive.
        {'element': 411, 'name': 'Haaland', 'team': 'Man City',
         'position': 'FWD', 'value_m': 15.6, 'predicted_points': 8.59,
         'status': 'a'},
        {'element': 411, 'name': 'Haaland', 'team': 'Man City',
         'position': 'FWD', 'value_m': 15.6, 'predicted_points': 7.10,
         'status': 'a'},
    ]).to_csv(path, index=False)

    loaded = load_predictions(str(path))

    assert sorted(loaded['element']) == [411, 570, 619]
    assert set(loaded.loc[loaded['name'] == 'Palacios', 'team']) == {
        'Ipswich Town', 'Fulham'}
    haaland = loaded.loc[loaded['element'] == 411, 'predicted_points']
    assert float(haaland.iloc[0]) == 8.59


def test_fixed_squad_gets_xi_ordered_bench_and_two_armbands() -> None:
    squad = current_squad().reset_index(drop=True)

    result, status = solve_squad(squad, float(squad['value_m'].sum()))

    assert status == 'Optimal'
    assert len(result['xi']) == 11
    assert len(result['bench']) == 4
    assert result['bench'].iloc[-1]['position'] == 'GK'
    outfield_points = list(result['bench'].iloc[:-1]['predicted_points'])
    assert outfield_points == sorted(outfield_points, reverse=True)
    assert result['captain']['name'] == 'Useful premium'
    assert result['vice_captain']['name'] != result['captain']['name']
    assert result['vice_captain']['position'] != 'GK'


def market(owned_top: bool = False) -> pd.DataFrame:
    """A deep enough market that several legal squads are near-equal.

    Every player has his own club, so the three-per-club rule never binds, and
    prices are flat so the budget does not either. Points step down by 0.01,
    which puts a lot of squads within a hundredth of each other.
    """
    rows, element = [], 1000
    for position, depth, top in (('GK', 5, 3.0), ('DEF', 10, 4.0),
                                 ('MID', 10, 5.0), ('FWD', 6, 4.5)):
        for i in range(depth):
            row = player(element, f'{position} {i}', f'T{element}', position,
                         5.0, top - i * 0.01)
            if owned_top:
                # The best players are also the most owned, which is what an
                # ownership penalty is there to push against.
                row['selected_by'] = 60.0 - i * 5.0
            rows.append(row)
            element += 1
    return pd.DataFrame(rows)


def test_alternatives_are_distinct_and_stay_inside_the_margin() -> None:
    data = compute_squad_alternatives(market(), 80.0, count=4, min_changes=3)
    found = data['alternatives']

    assert len(found) == 4
    assert [entry['rank'] for entry in found] == [1, 2, 3, 4]
    assert all(entry['behind_best'] <= data['margin'] for entry in found)
    # Monotonic: each answer is at best as good as the one before it, and
    # the gap is measured on what the solver maximised, so never negative.
    assert all(e['behind_best'] >= 0 for e in found)
    assert found == sorted(found, key=lambda e: e['behind_best'])
    # The displayed column is the real points difference, signed, and zero
    # for the squad everything else is compared against.
    assert found[0]['points_vs_best'] == 0.0
    assert all(e['points_vs_best'] == round(e['total'] - found[0]['total'], 2)
               for e in found)

    squads = [set(entry['names']) for entry in found]
    for i, one in enumerate(squads):
        assert len(one) == 15
        for other in squads[i + 1:]:
            assert len(one - other) >= 3


def thin_market() -> pd.DataFrame:
    """Fifteen good players, and only poor ones to replace them with."""
    rows, element = [], 2000
    for position, depth, top in (('GK', 2, 3.0), ('DEF', 5, 4.0),
                                 ('MID', 5, 5.0), ('FWD', 3, 4.5)):
        for i in range(depth):
            rows.append(player(element, f'{position} {i}', f'T{element}',
                               position, 5.0, top - i * 0.01))
            element += 1
    for position in ('GK', 'DEF', 'DEF', 'MID', 'MID', 'FWD'):
        rows.append(player(element, f'Spare {element}', f'T{element}',
                           position, 5.0, 0.1))
        element += 1
    return pd.DataFrame(rows)


def test_alternatives_stop_rather_than_return_a_worse_squad() -> None:
    # Five changes cannot all hide on the bench, so at least one lands in the
    # XI and costs real points. A margin this tight must refuse them rather
    # than pad the list out.
    data = compute_squad_alternatives(thin_market(), 80.0, count=5,
                                      min_changes=5, margin=0.001)

    assert len(data['alternatives']) == 1
    assert data['exhausted'] is True


def test_alternatives_admit_the_worse_squad_when_the_margin_allows_it() -> None:
    data = compute_squad_alternatives(thin_market(), 80.0, count=5,
                                      min_changes=5, margin=100.0)

    assert len(data['alternatives']) > 1
    assert data['alternatives'][1]['behind_best'] > 1.0


def test_seed_jitter_is_reproducible_and_seed_specific() -> None:
    players = market()

    assert seed_jitter(players, 'alice') == seed_jitter(players, 'alice')
    assert seed_jitter(players, 'alice') != seed_jitter(players, 'bob')
    assert all(abs(v) <= 0.05 for v in seed_jitter(players, 'alice').values())


def test_a_seed_moves_the_pick_without_leaving_the_plateau() -> None:
    players = market()
    plain, _ = solve_squad(players, 80.0)
    seeded, _ = solve_squad(players, 80.0, seed='alice')
    again, _ = solve_squad(players, 80.0, seed='alice')

    assert list(again['squad']['name']) == list(seeded['squad']['name'])
    assert set(seeded['squad']['name']) != set(plain['squad']['name'])
    # Whatever it changed, it cannot have cost more than the model can resolve.
    assert expected_total(plain) - expected_total(seeded) < 1.0


def test_ownership_penalty_buys_a_less_owned_squad() -> None:
    players = market(owned_top=True)
    plain, _ = solve_squad(players, 80.0)
    tilted, _ = solve_squad(players, 80.0, ownership_penalty=0.05)

    assert squad_ownership(tilted['squad']) < squad_ownership(plain['squad'])
    # The penalty steers the pick; it is not counted as points anyone scores.
    assert expected_total(tilted) <= expected_total(plain)


def test_seed_scale_controls_how_far_a_seed_may_move_the_pick() -> None:
    players = market()
    timid, _ = solve_squad(players, 80.0, seed="alice", seed_scale=0.0)
    plain, _ = solve_squad(players, 80.0)
    bold, _ = solve_squad(players, 80.0, seed="alice", seed_scale=0.5)

    # A zero budget for tie-breaking cannot move anything.
    assert set(timid['squad']['name']) == set(plain['squad']['name'])
    # A wider one can, and what it costs stays measurable against the optimum.
    assert set(bold['squad']['name']) != set(plain['squad']['name'])
    assert expected_total(plain) >= expected_total(bold)


def test_a_seed_moves_the_eleven_not_only_the_bench() -> None:
    # Nudging squad membership alone left every manager fielding the same XI.
    players = market()
    elevens = {
        frozenset(solve_squad(players, 80.0, seed=who, seed_scale=0.2)[0]
                  ["xi"]["name"])
        for who in ('alice', 'bob', 'carol', 'dave')
    }

    assert len(elevens) > 1
