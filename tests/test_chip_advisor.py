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
    assert all(rec['projected_gain'] is None for rec in data['recommendations'])
    assert all(rec['fixture_signal_index'] is not None for rec in data['recommendations'])
    assert all(row['projected_gain'] == {chip: None for chip in CHIPS} for row in data['rows'])
    assert all(rec['status'] == 'watch' for rec in data['recommendations'])
    assert all('fixture signal' in rec['reasons'][0] for rec in data['recommendations'])
    assert all(rec['evidence'] is None for rec in data['recommendations'])
    assert all('expected_gain' not in rec and 'score_breakdown' not in rec
               for rec in data['recommendations'])


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
    assert by_chip['triple_captain']['projected_gain'] > 0
    assert by_chip['bench_boost']['evidence']['bench_total'] == round(sum(
        player['points'] for player in by_chip['bench_boost']['evidence']['ordered_bench']), 2)
    assert len(by_chip['bench_boost']['evidence']['ordered_bench']) == 4
    assert by_chip['triple_captain']['evidence']['incremental_gain'] == by_chip['triple_captain']['projected_gain']
    assert by_chip['triple_captain']['evidence']['captain']['fixtures'] == 2
    assert by_chip['triple_captain']['evidence']['triple_captain_total'] == round(
        by_chip['triple_captain']['evidence']['normal_captain_total']
        + 2 * by_chip['triple_captain']['evidence']['captain']['projected_points'], 2)
    assert by_chip['triple_captain']['evidence']['captain']['name'] == 'MID 0'
    assert by_chip['triple_captain']['evidence']['captain']['team'] == 'Club 8'
    assert by_chip['triple_captain']['evidence']['captain']['position'] == 'MID'
    assert by_chip['triple_captain']['evidence']['captain']['projected_points'] == by_chip['triple_captain']['evidence']['incremental_gain']
    assert by_chip['triple_captain']['evidence']['captain']['fixtures'] == 2
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
    assert free_hit['evidence']['current_xi_total'] >= 0
    assert free_hit['evidence']['optimized_xi_total'] >= 0
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

    assert triple_captain['projected_gain'] > 15.0


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
    breakdown = free_hit['evidence']

    assert breakdown['optimized_captain_points'] > breakdown['current_captain_points']
    assert free_hit['projected_gain'] == round(
        breakdown['optimized_xi_captain_total'] - breakdown['current_xi_captain_total'], 2)
    assert 'avoided_transfer_hits' not in breakdown


def test_future_chip_candidates_are_ranked_and_never_marked_play(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()
    points = horizon_points(players, [5, 6, 7, 8])
    points.loc[:, 7] = 1.0
    points.loc[11, 7] = 25.0

    data = compute_chips(squad, 'test-season', 5, 4, players,
                         inventory=synced_inventory(), future_points=points)
    triple_captain = next(rec for rec in data['recommendations']
                          if rec['chip'] == 'triple_captain')

    assert triple_captain['candidate_gw'] == 7
    assert triple_captain['status'] == 'watch'
    assert triple_captain['projected_gain'] == 25.0
    assert len(triple_captain['alternatives']) == 3
    assert triple_captain['alternatives'][0]['evidence']['captain']['element'] == 24
    assert triple_captain['alternatives'][0]['evidence']['incremental_gain'] == 25.0
    assert triple_captain['runner_up_gameweek'] == triple_captain['alternatives'][1]['gw']
    assert triple_captain['gap_to_runner_up'] > 0


def test_current_complete_candidate_uses_named_margin_policy(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()

    data = compute_chips(squad, 'test-season', 1, 2, players,
                         inventory=synced_inventory(),
                         future_points=horizon_points(players, [1, 2]))
    triple_captain = next(rec for rec in data['recommendations']
                          if rec['chip'] == 'triple_captain')

    assert triple_captain['status'] == 'play'
    assert triple_captain['decision_policy']['minimum_projected_gain'] == data['decision_policy']['minimum_projected_gain']
    assert triple_captain['decision_policy']['minimum_projected_gain'] > 0
    assert data['projection_mode'] == 'model_projection'
    assert data['projection_gameweeks'] == [1, 2]
    assert data['data_quality'] == 'complete_horizon'
    assert data['coverage_warning'] is None


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

    assert injured_bb['projected_gain'] < healthy_bb['projected_gain']


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



def test_complete_projection_without_synced_inventory_cannot_play(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()

    data = compute_chips(squad, 'test-season', 1, 2, players,
                         future_points=horizon_points(players, [1, 2]))

    triple_captain = next(rec for rec in data['recommendations']
                          if rec['chip'] == 'triple_captain')
    assert triple_captain['projected_gain'] is not None
    assert triple_captain['status'] == 'watch'
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

    assert wildcard['evidence']['horizon_length'] == 8
    assert 'current_cumulative_total' in wildcard['evidence']
    assert 'optimized_cumulative_total' in wildcard['evidence']
    assert all(data['rows'][index]['projected_gain']['wildcard'] is not None
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
    assert wildcard['evidence']['horizon_length'] == 2
    assert wildcard['projected_gain'] > 8.0


def _priced_market_with_reach_candidate():
    """A squad where one owned player has risen in price, plus one very
    high-scoring, moderately-priced market candidate that's only affordable
    if the risen player's real selling price (not his market value) funds it.

    The market's own 'Alt' candidates (7pts each) are neutralised to 1pt so
    the only reason the solver would touch the squad at all is 'Reach'
    -- otherwise their own attractiveness muddies the comparison.
    """
    players = market()
    players.loc[players['name'].str.startswith('Alt'), 'predicted_points'] = 1.0
    # 'MID 4' (element 24) was bought at 5.0 and is now worth 8.0; the real
    # 2026/27 selling-price rule banks 6.5 (5.0 + half the 3.0 rise), not the
    # full 8.0 market value.
    players.loc[players['element'] == 24, 'value_m'] = 8.0
    squad = players.iloc[:15].copy()
    with_target = pd.concat([
        players,
        pd.DataFrame([player(200, 'Reach', 'Club 20', 'MID', 50.0)]),
    ], ignore_index=True)
    with_target.loc[with_target['element'] == 200, 'value_m'] = 7.0
    return squad, with_target


def test_free_hit_budget_uses_real_selling_price_not_market_value(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    squad, players = _priced_market_with_reach_candidate()
    # Free Hit is never eligible in GW1, so this needs first_gw >= 2.
    points = horizon_points(players, [2])

    # No ownership-price basis: budget defaults to market value, under which
    # dropping the 8.0-priced 'MID 4' comfortably affords the 7.0 'Reach',
    # whose 50 points dominate the resulting XI total.
    no_finance = compute_chips(squad, 'test-season', 2, 1, players,
                               inventory=synced_inventory(), future_points=points)
    free_hit_no_finance = next(
        rec for rec in no_finance['recommendations'] if rec['chip'] == 'free_hit')
    assert free_hit_no_finance['evidence']['optimized_xi_total'] >= 90

    # Real ownership prices: selling 'MID 4' only raises 6.5, £0.5m short of
    # 'Reach' -- the same swap is not affordable and 'Reach' is left out.
    with_finance = compute_chips(squad, 'test-season', 2, 1, players,
                                 inventory=synced_inventory(), future_points=points,
                                 bank=0.0, selling_prices={24: 6.5})
    free_hit_with_finance = next(
        rec for rec in with_finance['recommendations'] if rec['chip'] == 'free_hit')
    assert free_hit_with_finance['evidence']['optimized_xi_total'] < 90
    assert free_hit_with_finance['warnings'] == []

    assert any('Budget estimated from current market value' in warning
               for warning in free_hit_no_finance['warnings'])


def test_wildcard_budget_uses_real_selling_price_not_market_value(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    squad, players = _priced_market_with_reach_candidate()
    points = horizon_points(players, [2])

    no_finance = compute_chips(squad, 'test-season', 2, 1, players,
                               inventory=synced_inventory(), future_points=points)
    wildcard_no_finance = next(
        rec for rec in no_finance['recommendations'] if rec['chip'] == 'wildcard')
    # Reach at 50 points, captained (doubled), dwarfs the rest of the squad.
    assert wildcard_no_finance['evidence']['optimized_cumulative_total'] >= 90

    with_finance = compute_chips(squad, 'test-season', 2, 1, players,
                                 inventory=synced_inventory(), future_points=points,
                                 bank=0.0, selling_prices={24: 6.5})
    wildcard_with_finance = next(
        rec for rec in with_finance['recommendations'] if rec['chip'] == 'wildcard')
    assert wildcard_with_finance['evidence']['optimized_cumulative_total'] < 90


def test_simultaneous_play_verdicts_warn_about_the_one_chip_per_gw_rule(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market()
    squad = players.iloc[:15].copy()
    points = horizon_points(players, [1])

    data = compute_chips(squad, 'test-season', 1, 1, players,
                         inventory=synced_inventory(), future_points=points)
    by_chip = {rec['chip']: rec for rec in data['recommendations']}

    playing = [chip for chip, rec in by_chip.items() if rec['status'] == 'play' and rec['gw'] == 1]
    assert len(playing) >= 2, 'fixture must actually exercise the conflict'
    chip_labels = {
        'triple_captain': 'Triple Captain', 'bench_boost': 'Bench Boost',
        'free_hit': 'Free Hit', 'wildcard': 'Wildcard',
    }
    for chip in playing:
        others = [c for c in playing if c != chip]
        warning_text = ' '.join(by_chip[chip]['warnings'])
        assert 'Only one chip can be played per gameweek' in warning_text
        for other in others:
            assert chip_labels[other] in warning_text


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
