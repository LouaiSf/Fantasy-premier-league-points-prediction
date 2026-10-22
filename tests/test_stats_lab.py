from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webapp import stats  # noqa: E402

SEASON = 'test-season'


def match(element, gw, minutes, position='MID', team='Club A', **values):
    row = {'element': element, 'name': f'Player {element}', 'GW': gw, 'fixture': gw * 10 + (element % 2),
           'minutes': minutes, 'goals_scored': 0, 'assists': 0, 'expected_goals': 0.0,
           'expected_assists': 0.0, 'expected_goal_involvements': 0.0,
           'expected_goals_conceded': 0.0, 'clearances_blocks_interceptions': 0,
           'tackles': 0, 'recoveries': 0, 'saves': 0, 'goals_conceded': 0,
           'clean_sheets': 0, 'total_points': 2, 'position': position, 'team': team,
           'opponent_team': 'Club B', 'was_home': True}
    row.update(values)
    return row


def write(tmp_path, fpl_rows, fotmob_rows=None, players=None):
    base = tmp_path / 'data' / SEASON
    (base / 'gws').mkdir(parents=True)
    pd.DataFrame(fpl_rows).to_csv(base / 'gws' / 'merged_gw.csv', index=False)
    if fotmob_rows is not None:
        (base / 'fotmob').mkdir()
        pd.DataFrame(fotmob_rows).to_csv(base / 'fotmob' / 'player_match.csv', index=False)
    pd.DataFrame(players or [{'id': 1, 'web_name': 'One', 'code': 11, 'team': 1,
                              'element_type': 3, 'now_cost': 60}]).to_csv(
        base / 'players_raw.csv', index=False)
    stats.load_matches.cache_clear()
    return str(tmp_path)


def by_id(result):
    return {row['id']: row for row in result['rows']}


def test_per_90_and_finishing_gaps(tmp_path) -> None:
    root = write(tmp_path, [match(1, 1, 90, goals_scored=1, expected_goals=0.4, expected_assists=0.2,
                                  expected_goal_involvements=0.6),
                            match(1, 2, 45, expected_goals=0.2, expected_goal_involvements=0.2)])
    row = by_id(stats.player_stats(root, SEASON))[1]['metrics']
    assert row['minutes'] == 135 and row['apps'] == 2
    assert row['xg_p90'] == pytest.approx(0.6 * 90 / 135, abs=1e-3)
    assert row['goals_minus_xg'] == pytest.approx(0.4)
    assert row['xa_minus_assists'] == pytest.approx(0.2)


def test_window_and_minimum_minutes(tmp_path) -> None:
    rows = [match(1, gw, 90, expected_goals=0.1 * gw, expected_goal_involvements=0.1 * gw)
            for gw in range(1, 9)] + [match(2, 8, 30)]
    root = write(tmp_path, rows)
    last4 = stats.player_stats(root, SEASON, window='last4')
    assert last4['window']['gw_from'] == 5 and last4['window']['gw_to'] == 8
    assert by_id(last4)[1]['metrics']['xg'] == pytest.approx(0.5 + 0.6 + 0.7 + 0.8)
    assert 2 not in by_id(stats.player_stats(root, SEASON, min_minutes=90))
    custom = stats.player_stats(root, SEASON, gw_from=2, gw_to=3)
    assert by_id(custom)[1]['metrics']['minutes'] == 180


def test_fotmob_fields_are_null_without_fotmob_and_for_unmapped_players(tmp_path) -> None:
    rows = [match(1, 1, 90), match(2, 1, 90)]
    root = write(tmp_path, rows)
    alone = by_id(stats.player_stats(root, SEASON))[1]
    assert alone['metrics']['xgot'] is None and alone['sources'] == ['fpl']

    stats.load_matches.cache_clear()
    root = write(tmp_path / 'with', rows, fotmob_rows=[
        {'element': 1, 'fpl_fixture': 11, 'xg': 0.5, 'xgot': 0.9, 'shots': 3, 'goals': 1}])
    result = by_id(stats.player_stats(root, SEASON))
    assert result[1]['metrics']['xgot'] == pytest.approx(0.9)
    assert result[1]['metrics']['xgot_minus_xg'] == pytest.approx(0.4)
    # Omitted FotMob stats on a mapped match are zeros, not gaps.
    assert result[1]['metrics']['touches_opp_box_p90'] == 0
    assert result[2]['metrics']['xgot'] is None and result[2]['sources'] == ['fpl']


def test_defcon_hit_rate_uses_position_thresholds_and_60_minute_apps(tmp_path) -> None:
    rows = [match(1, 1, 90, position='DEF', clearances_blocks_interceptions=6, tackles=4),
            match(1, 2, 90, position='DEF', clearances_blocks_interceptions=5, tackles=4),
            match(1, 3, 20, position='DEF', clearances_blocks_interceptions=12),
            match(3, 1, 90, position='MID', clearances_blocks_interceptions=4, tackles=4, recoveries=4)]
    root = write(tmp_path, rows)
    result = by_id(stats.player_stats(root, SEASON))
    assert result[1]['metrics']['defcon_hit_rate'] == 0.5
    assert result[3]['metrics']['defcon_hit_rate'] == 1.0


def test_defcon_probability_is_a_poisson_tail() -> None:
    lam = 11.0 * 90 / 90
    expected = 1 - sum(math.exp(-lam) * lam ** k / math.factorial(k) for k in range(10))
    assert stats.defcon_probability(11.0, 90, 10) == pytest.approx(expected)
    assert stats.defcon_probability(0.0, 90, 10) == 0.0
    assert stats.defcon_probability(None, 90, 10) is None


def test_keeper_preset_filters_and_sorts(tmp_path) -> None:
    rows = [match(1, 1, 90, position='GK', saves=4, goals_conceded=1),
            match(2, 1, 90, position='GK', saves=1, goals_conceded=3),
            match(3, 1, 90, position='MID')]
    fotmob = [{'element': 1, 'fpl_fixture': 11, 'xgot_faced': 2.0, 'goals_prevented': 1.0},
              {'element': 2, 'fpl_fixture': 10, 'xgot_faced': 1.5, 'goals_prevented': -1.5}]
    root = write(tmp_path, rows, fotmob_rows=fotmob)
    result = stats.player_stats(root, SEASON, preset='shot_stoppers')
    assert [row['id'] for row in result['rows']] == [1, 2]
    assert result['rows'][0]['metrics']['save_pct'] == pytest.approx(0.8)
    assert result['sort'] == 'goals_prevented_p90'


def test_stats_routes_answer_and_reject_bad_input() -> None:
    from webapp.app import app
    client = app.test_client()
    ok = client.get('/api/stats/players?window=last4&position=MID&limit=5')
    assert ok.status_code == 200
    body = ok.get_json()
    assert body['ok'] and len(body['rows']) <= 5 and 'fotmob_updated_at' in body
    assert client.get('/api/stats/players?window=fortnight').status_code == 400
    assert client.get('/api/stats/players?preset=nope').status_code == 400
    first = body['rows'][0]['id'] if body['rows'] else 1
    under = client.get(f'/api/player/{first}/underlying').get_json()
    assert under['ok'] and 'gameweeks' in under
