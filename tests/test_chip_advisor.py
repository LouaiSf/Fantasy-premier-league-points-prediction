import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from optimise import compute_chips  # noqa: E402


CHIPS = ('triple_captain', 'bench_boost', 'free_hit', 'wildcard')


def player(element, name, team, position, points, status='a'):
    return {
        'element': element,
        'name': name,
        'team': team,
        'position': position,
        'value_m': 5.0,
        'predicted_points': points,
        'status': status,
        'p_plays': 1.0 if status == 'a' else 0.0,
    }


def market():
    rows = [
        player(1, 'GK 1', 'Club 1', 'GK', 4.0),
        player(2, 'GK 2', 'Club 2', 'GK', 3.0),
    ]
    rows += [player(10 + i, f'DEF {i}', f'Club {3 + i}', 'DEF', 5.0)
             for i in range(5)]
    rows += [player(20 + i, f'MID {i}', f'Club {8 + i}', 'MID',
                    10.0 if i == 0 else 4.0) for i in range(5)]
    rows += [player(30 + i, f'FWD {i}', f'Club {13 + i}', 'FWD', 5.0)
             for i in range(3)]
    rows += [player(100 + i, f'Alt {i}', f'Club {16 + i}', 'MID', 7.0)
             for i in range(5)]
    return pd.DataFrame(rows)


def horizon_points(players, gameweeks):
    return pd.DataFrame(
        {gameweek: players['predicted_points'].to_numpy() for gameweek in gameweeks},
        index=players.index,
    )


def write_season(tmp_path, double=False, blank=False):
    data = tmp_path / 'data' / 'test-season'
    data.mkdir(parents=True)
    pd.DataFrame({
        'id': range(1, 21),
        'name': [f'Club {i}' for i in range(1, 21)],
    }).to_csv(data / 'teams.csv', index=False)
    fixtures = []
    fixture_id = 1
    for gw in range(1, 15):
        team_ids = list(range(1, 21))
        if blank and gw == 3:
            team_ids = list(range(1, 19))
        pairs = list(zip(team_ids[::2], team_ids[1::2]))
        if double and gw == 2:
            pairs += [(1, 3), (8, 10)]
        for home, away in pairs:
            fixtures.append({
                'id': fixture_id,
                'event': gw,
                'team_h': home,
                'team_a': away,
                'team_h_difficulty': 2,
                'team_a_difficulty': 4,
            })
            fixture_id += 1
    pd.DataFrame(fixtures).to_csv(data / 'fixtures.csv', index=False)
    return data


def synced_inventory(state='unused'):
    return {
        'first_half': {chip: state for chip in CHIPS},
        'second_half': {chip: 'unused' for chip in CHIPS},
    }


def test_no_squad_is_explicit_fixture_signal(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)

    data = compute_chips(None, 'test-season', 2, 4, market())

    assert data['inventory_status'] == 'not_synced'
    assert data['projection_mode'] == 'fixture_signal'
    assert all(rec['expected_gain'] is None for rec in data['recommendations'])
    assert all(rec['status'] == 'watch' for rec in data['recommendations'])
    assert all('fixture signal' in rec['reasons'][0] for rec in data['recommendations'])
    assert all('captain_evidence' not in rec for rec in data['recommendations'])


def test_dgw_scores_actual_captain_and_bench(monkeypatch, tmp_path):
    write_season(tmp_path, double=True)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()

    points = horizon_points(players, [1, 2, 3])
    points[2] *= 2
    data = compute_chips(squad, 'test-season', 1, 3, players,
                         inventory=synced_inventory(), future_points=points)
    by_chip = {rec['chip']: rec for rec in data['recommendations']}

    assert data['rows'][1]['dgw_teams'] == 4
    assert by_chip['triple_captain']['expected_gain'] > 0
    assert by_chip['bench_boost']['score_breakdown']['bench_points'] >= 0
    assert by_chip['bench_boost']['bench_players'] and len(by_chip['bench_boost']['bench_players']) == 4
    assert by_chip['triple_captain']['score_breakdown']['incremental_gain'] == by_chip['triple_captain']['expected_gain']
    assert by_chip['triple_captain']['score_breakdown']['captain_fixture_count'] == 2
    assert by_chip['triple_captain']['score_breakdown']['triple_captain_points'] == round(
        by_chip['triple_captain']['score_breakdown']['normal_captain_points'] * 3, 2)
    assert by_chip['triple_captain']['captain_evidence']['player'] == 'MID 0'
    assert by_chip['triple_captain']['captain_evidence']['team'] == 'Club 8'
    assert by_chip['triple_captain']['captain_evidence']['position'] == 'MID'
    assert by_chip['triple_captain']['captain_evidence']['points'] == by_chip['triple_captain']['score_breakdown']['incremental_gain']
    assert by_chip['triple_captain']['captain_evidence']['fixtures'] == 2
    assert by_chip['triple_captain']['candidate_gw'] == 2


def test_blank_gameweek_gives_free_hit_a_squad_comparison(monkeypatch, tmp_path):
    write_season(tmp_path, blank=True)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()

    data = compute_chips(squad, 'test-season', 2, 3, players,
                         inventory=synced_inventory(),
                         future_points=horizon_points(players, [2, 3, 4]))
    free_hit = next(rec for rec in data['recommendations'] if rec['chip'] == 'free_hit')

    assert data['rows'][1]['blank_teams'] == 2
    assert free_hit['score_breakdown']['current_xi'] >= 0
    assert free_hit['score_breakdown']['optimized_xi'] >= 0
    assert free_hit['candidate_gameweeks'] == [2, 3, 4]


def test_non_prefix_squad_keeps_projection_identity(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    players.loc[15, 'predicted_points'] = 20.0
    squad = players.iloc[[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15]]

    data = compute_chips(squad, 'test-season', 1, 1, players,
                         inventory=synced_inventory(),
                         future_points=horizon_points(players, [1]))
    triple_captain = next(rec for rec in data['recommendations']
                          if rec['chip'] == 'triple_captain')

    assert triple_captain['expected_gain'] > 15.0


def test_free_hit_includes_new_captain_delta(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    players.loc[15, 'predicted_points'] = 20.0
    squad = players.iloc[:15]

    data = compute_chips(squad, 'test-season', 1, 2, players,
                         inventory=synced_inventory(),
                         future_points=horizon_points(players, [1, 2]))
    free_hit = next(rec for rec in data['recommendations']
                    if rec['chip'] == 'free_hit')
    breakdown = free_hit['score_breakdown']

    assert breakdown['captain_delta'] > 0
    assert round(breakdown['captain_delta'], 2) == 10.0
    assert free_hit['expected_gain'] == round(
        breakdown['xi_gain'] + breakdown['captain_delta']
        + breakdown['avoided_transfer_hits'], 2)
    assert free_hit['expected_gain'] == round(
        breakdown['optimized_total'] - breakdown['current_total']
        + breakdown['avoided_transfer_hits'], 2)


def test_injured_bench_reduces_bench_boost_value(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    healthy = market()
    injured = healthy.copy()
    injured.loc[injured.index[14], 'status'] = 'i'
    injured.loc[injured.index[14], 'p_plays'] = 0.0

    healthy_result = compute_chips(healthy.iloc[:15], 'test-season', 1, 1, healthy,
                                   inventory=synced_inventory(),
                                   future_points=horizon_points(healthy, [1]))
    injured_result = compute_chips(injured.iloc[:15], 'test-season', 1, 1, injured,
                                   inventory=synced_inventory(),
                                   future_points=horizon_points(injured, [1]))
    healthy_bb = next(rec for rec in healthy_result['recommendations'] if rec['chip'] == 'bench_boost')
    injured_bb = next(rec for rec in injured_result['recommendations'] if rec['chip'] == 'bench_boost')

    assert injured_bb['expected_gain'] < healthy_bb['expected_gain']


def test_inventory_expiry_and_scheduled_week_conflict(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)

    expired = compute_chips(None, 'test-season', 5, 2, market(),
                            inventory=synced_inventory('expired'))
    assert all(rec['status'] == 'unavailable' for rec in expired['recommendations'])

    scheduled = compute_chips(None, 'test-season', 5, 2, market(),
                              inventory=synced_inventory(), scheduled_gameweeks=[5, 6])
    assert all(rec['candidate_gameweeks'] == [] for rec in scheduled['recommendations'])
    assert all(rec['status'] == 'hold' for rec in scheduled['recommendations'])


def test_used_chip_and_one_chip_gameweek_are_unavailable_or_excluded(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)

    used = compute_chips(None, 'test-season', 2, 4, market(),
                         inventory=synced_inventory('used'))
    assert all(rec['status'] == 'unavailable' for rec in used['recommendations'])

    available = compute_chips(None, 'test-season', 2, 4, market(),
                              inventory=synced_inventory(), scheduled_gameweeks=[2])
    assert all(2 not in rec['candidate_gameweeks'] for rec in available['recommendations'])


def test_unsynced_inventory_never_promotes_fixture_signal_to_play(monkeypatch, tmp_path):
    write_season(tmp_path, double=True)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()

    data = compute_chips(squad, 'test-season', 1, 3, players)

    assert data['inventory_sync_state'] == 'not_synced'
    assert data['projection_mode'] == 'fixture_signal'
    assert all(rec['status'] != 'play' for rec in data['recommendations'])


def test_wildcard_uses_cumulative_multi_gameweek_gain(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()

    data = compute_chips(squad, 'test-season', 2, 8, players,
                         inventory=synced_inventory(),
                         future_points=horizon_points(players, range(2, 10)))
    wildcard = next(rec for rec in data['recommendations'] if rec['chip'] == 'wildcard')

    assert wildcard['score_breakdown']['horizon_weeks'] == 8
    assert 'current_cumulative' in wildcard['score_breakdown']
    assert 'optimized_cumulative' in wildcard['score_breakdown']
    assert all(data['rows'][index]['opportunity']['wildcard'] is not None
               for index in range(len(data['rows'])))


def test_wildcard_reoptimizes_for_each_remaining_horizon(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()
    future_points = pd.DataFrame(1.0, index=players.index, columns=[2, 3, 4])
    future_points.loc[7:11, 2] = 50.0
    future_points.loc[7:11, [3, 4]] = 0.0
    future_points.loc[15:19, 2] = 0.0
    future_points.loc[15:19, [3, 4]] = 20.0

    data = compute_chips(squad, 'test-season', 2, 3, players,
                         inventory=synced_inventory(), future_points=future_points)
    wildcard = next(rec for rec in data['recommendations'] if rec['chip'] == 'wildcard')

    assert wildcard['candidate_gw'] == 3
    assert wildcard['score_breakdown']['horizon_weeks'] == 2
    assert wildcard['expected_gain'] > 8.0


def test_horizon_changes_candidate_matrix(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()

    four = compute_chips(None, 'test-season', 2, 4, players)
    eight = compute_chips(None, 'test-season', 2, 8, players)
    twelve = compute_chips(None, 'test-season', 2, 12, players)

    assert len(four['rows']) == 4
    assert len(eight['rows']) == 8
    assert len(twelve['rows']) == 12
    assert four['last_gw'] < eight['last_gw'] < twelve['last_gw']
