from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import optimise as optimise_module
from optimise import (  # noqa: E402
    annotate_marginals,
    choose_transfer_recommendation,
    chip_advice,
    compute_squad_alternatives,
    compute_transfers,
    expected_total,
    load_predictions,
    load_horizon,
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


def test_selling_prices_override_market_value_in_budget_and_bank_after() -> None:
    current = current_squad()
    # A riser (bought 8.0, now worth the fixture's 10.0, real sale nets 9.0)
    # and someone already priced at their floor after a fall (5.0, unchanged
    # by the half-rise rule since there's nothing to halve on the way down).
    # Neither equals a naive "market value" read, so this only passes if the
    # solver used the supplied selling prices rather than re-deriving or
    # ignoring them.
    selling_prices = {int(e): float(v) for e, v in zip(current['element'], current['value_m'])}
    selling_prices[20] = 9.0   # 'Useful premium': market 10.0, real sale 9.0
    expected_selling_value = sum(selling_prices.values())

    result = compute_transfers(current, current, free=0, bank=1.5, max_transfers=0,
                                selling_prices=selling_prices)

    hold = result['rows'][0]
    assert result['selling_value'] == round(expected_selling_value, 1)
    assert result['budget'] == round(expected_selling_value + 1.5, 1)
    assert hold['selling_value'] == round(expected_selling_value, 1)
    assert hold['market_value'] == round(float(current['value_m'].sum()), 1)
    assert hold['bank_after'] == 1.5


def test_two_transfer_downgrade_upgrade_uses_real_selling_proceeds() -> None:
    current = current_squad()
    market = pd.concat([
        current,
        pd.DataFrame([
            player(100, 'Cheap enabler', 'P', 'MID', 4.0, 7.0),
            player(101, 'Elite upgrade', 'Q', 'MID', 11.0, 14.0),
        ]),
    ], ignore_index=True)
    # Without a selling-price override this exact combination is feasible
    # with zero bank (dropped market value 10.0 + 5.0 == bought market value
    # 4.0 + 11.0). Pricing 'Useful premium' at half a million below his
    # market value must eat directly into that budget: the same combination
    # now needs the matching 0.5 of bank to still be legal.
    selling_prices = {int(e): float(v) for e, v in zip(current['element'], current['value_m'])}
    selling_prices[20] = 9.5  # 'Useful premium': market 10.0, real sale 9.5

    result = compute_transfers(current, market, free=2, bank=0.5, max_transfers=2,
                                selling_prices=selling_prices)
    two_moves = next(row for row in result['rows'] if row['transfers'] == 2)

    assert set(two_moves['out']) == {'Useful premium', 'Weak budget'}
    assert set(two_moves['in']) == {'Cheap enabler', 'Elite upgrade'}
    assert two_moves['bank_after'] == 0.0
    assert two_moves['bank_after'] >= 0


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


def test_load_predictions_uses_earliest_gw_and_sums_double_fixtures(tmp_path) -> None:
    path = tmp_path / 'horizon.csv'
    pd.DataFrame([
        {'element': 1, 'name': 'One', 'team': 'A', 'position': 'MID',
         'value_m': 5.0, 'GW': 5, 'predicted_points': 2.0},
        {'element': 1, 'name': 'One', 'team': 'A', 'position': 'MID',
         'value_m': 5.0, 'GW': 5, 'predicted_points': 2.5},
        {'element': 1, 'name': 'One', 'team': 'A', 'position': 'MID',
         'value_m': 5.0, 'GW': 6, 'predicted_points': 10.0},
        {'element': 2, 'name': 'Two', 'team': 'B', 'position': 'MID',
         'value_m': 5.0, 'GW': 5, 'predicted_points': 3.0},
        {'element': 2, 'name': 'Two', 'team': 'B', 'position': 'MID',
         'value_m': 5.0, 'GW': 6, 'predicted_points': 4.0},
    ]).to_csv(path, index=False)

    current = load_predictions(str(path))
    horizon_players, points, gameweeks = load_horizon(str(path))

    assert set(current['GW']) == {5}
    assert current.set_index('element')['predicted_points'].to_dict() == {1: 4.5, 2: 3.0}
    assert gameweeks == [5, 6]
    assert points.set_axis(horizon_players['element']).loc[1].to_dict() == {5: 4.5, 6: 10.0}



def test_cli_chip_advice_loads_and_aligns_horizon_matrix(tmp_path, monkeypatch, capsys):
    prediction_path = tmp_path / 'predictions.csv'
    pd.DataFrame([
        {'element': 11, 'name': 'One', 'team': 'Club', 'position': 'MID',
         'value_m': 5.0, 'GW': 1, 'predicted_points': 2.0},
        {'element': 11, 'name': 'One', 'team': 'Club', 'position': 'MID',
         'value_m': 5.0, 'GW': 2, 'predicted_points': 8.0},
        {'element': 12, 'name': 'Two', 'team': 'Club', 'position': 'MID',
         'value_m': 5.0, 'GW': 1, 'predicted_points': 3.0},
        {'element': 12, 'name': 'Two', 'team': 'Club', 'position': 'MID',
         'value_m': 5.0, 'GW': 2, 'predicted_points': 4.0},
    ]).to_csv(prediction_path, index=False)
    players = pd.DataFrame([
        {'element': 12, 'name': 'Two'},
        {'element': 11, 'name': 'One'},
    ])
    received = {}

    def capture_inputs(_squad, _season, _first_gw, _horizon, _players, **kwargs):
        received.update(kwargs)
        return {
            'first_gw': 1, 'last_gw': 2, 'any_dgw': False, 'any_bgw': False,
            'projection_mode': 'model_projection', 'projection_gameweeks': [1, 2],
            'coverage_warning': None, 'unmapped_teams': [], 'rows': [],
            'recommendations': [],
        }

    monkeypatch.setattr(optimise_module, 'PREDICTIONS', str(prediction_path))
    monkeypatch.setattr(optimise_module, 'compute_chips', capture_inputs)

    chip_advice(None, 'test-season', 1, 2, players)

    assert received['future_points'].to_numpy().tolist() == [[3.0, 4.0], [2.0, 8.0]]
    assert received['projection_generated_at'] is not None

def test_single_gameweek_matrix_cannot_become_future_player_gain(monkeypatch, tmp_path):
    from test_chip_advisor import market, synced_inventory, write_season
    from optimise import compute_chips

    write_season(tmp_path, double=True)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()
    only_current = pd.DataFrame(5.0, index=players.index, columns=[1])

    data = compute_chips(
        squad, 'test-season', 1, 4, players,
        inventory=synced_inventory(), future_points=only_current,
    )

    assert data['projection_mode'] == 'fixture_signal'
    assert data['evaluated_horizon'] == 1
    assert 'covers 1 of 4' in data['coverage_warning']
    assert all(rec['projected_gain'] is None for rec in data['recommendations'])
    assert all(rec['fixture_signal_index'] is not None for rec in data['recommendations'])
    assert all(rec['status'] != 'play' for rec in data['recommendations'])
    assert all(rec['evidence'] is None for rec in data['recommendations'])


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


def test_locked_transfer_pairs_stay_in_optimizer_rows_with_an_extra_move() -> None:
    current = current_squad()
    market = pd.concat([
        current,
        pd.DataFrame([
            player(100, 'Cheap enabler', 'P', 'MID', 4.0, 7.0),
            player(101, 'Elite upgrade', 'Q', 'MID', 11.0, 14.0),
            player(102, 'Extra upgrade', 'R', 'FWD', 6.0, 9.0),
        ]),
    ], ignore_index=True)

    result = compute_transfers(
        current, market, free=3, bank=6.0, max_transfers=3,
        locked_out_elements=[20, 21], locked_in_elements=[100, 101],
    )

    assert [failure['status'] for failure in result['failures'][:2]] == [
        'needs at least 2 staged moves', 'needs at least 2 staged moves',
    ]
    two_moves = next(row for row in result['rows'] if row['transfers'] == 2)
    three_moves = next(row for row in result['rows'] if row['transfers'] == 3)
    assert {20, 21}.issubset(set(two_moves['out_elements']))
    assert {100, 101}.issubset(set(two_moves['in_elements']))
    assert {20, 21}.issubset(set(three_moves['out_elements']))
    assert {100, 101}.issubset(set(three_moves['in_elements']))
    assert len(three_moves['out_elements']) == len(three_moves['in_elements']) == 3
    assert result['draft_constraints'] == {
        'locked_out_elements': [20, 21],
        'locked_in_elements': [100, 101],
    }


def test_locked_transfer_validation_rejects_bad_pairs_duplicates_and_overbudget() -> None:
    current = current_squad()
    market = pd.concat([
        current,
        pd.DataFrame([
            player(100, 'Midfield target', 'P', 'MID', 11.0, 14.0),
            player(101, 'Forward target', 'Q', 'FWD', 6.0, 9.0),
        ]),
    ], ignore_index=True)

    with pytest.raises(ValueError, match='same position'):
        compute_transfers(
            current, market, free=1, bank=20.0, max_transfers=1,
            locked_out_elements=[20], locked_in_elements=[101],
        )
    with pytest.raises(ValueError, match='unique'):
        compute_transfers(
            current, market, free=2, bank=20.0, max_transfers=2,
            locked_out_elements=[20, 20], locked_in_elements=[100, 100],
        )
    with pytest.raises(ValueError, match='exceed'):
        compute_transfers(
            current, market, free=1, bank=0.0, max_transfers=1,
            locked_out_elements=[21], locked_in_elements=[100],
        )


def test_staged_transfer_can_sell_an_unavailable_owned_player_at_real_price() -> None:
    current = current_squad()
    market = current[current['element'] != 1].reset_index(drop=True)
    market = pd.concat([
        market,
        pd.DataFrame([player(102, 'Replacement keeper', 'R', 'GK', 4.0, 5.0)]),
    ], ignore_index=True)
    selling_prices = {int(row.element): float(row.value_m) for row in current.itertuples()}
    selling_prices[1] = 3.8

    result = compute_transfers(
        current, market, free=1, bank=0.2, max_transfers=1,
        selling_prices=selling_prices,
        locked_out_elements=[1], locked_in_elements=[102],
    )

    row = result['rows'][0]
    assert row['out_elements'] == [1]
    assert row['in_elements'] == [102]
    assert row['bank_after'] == 0.0
    assert result['draft_constraints']['locked_out_elements'] == [1]


def test_goalkeepers_are_eligible_for_captain_and_vice() -> None:
    squad = current_squad()
    squad.loc[squad['element'] == 1, 'predicted_points'] = 20.0
    captain_result, _ = solve_squad(squad, float(squad['value_m'].sum()))
    assert captain_result['captain']['position'] == 'GK'

    squad.loc[squad['element'] == 1, 'predicted_points'] = 7.0
    vice_result, _ = solve_squad(squad, float(squad['value_m'].sum()))
    assert vice_result['captain']['position'] != 'GK'
    assert vice_result['vice_captain']['position'] == 'GK'
