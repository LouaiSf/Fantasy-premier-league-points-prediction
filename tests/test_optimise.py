from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from optimise import (  # noqa: E402
    annotate_marginals,
    choose_transfer_recommendation,
    compute_transfers,
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
