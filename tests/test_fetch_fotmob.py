from __future__ import annotations

import copy
import io
import json
import sys
import urllib.error
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_fotmob as fm  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'fotmob'


@pytest.fixture
def match() -> dict:
    """Arsenal 3-0 Coventry, 2026-27 GW1, trimmed to five players."""
    return json.loads((FIXTURES / 'match_5795363.json').read_text(encoding='utf-8'))


@pytest.fixture
def league() -> dict:
    return json.loads((FIXTURES / 'league_premier_league.json').read_text(encoding='utf-8'))


def by_name(rows: list[dict]) -> dict:
    return {r['player_name']: r for r in rows}


def shot(**kw) -> dict:
    base = {'playerId': 1, 'teamId': 9825, 'eventType': 'Miss', 'situation': 'RegularPlay',
            'isOnTarget': False, 'isBlocked': False, 'isFromInsideBox': True, 'isOwnGoal': False,
            'expectedGoals': 0.1, 'expectedGoalsOnTarget': 0.0, 'keeperId': None}
    return {**base, **kw}


# --------------------------------------------------------------------------
# League and match pages
# --------------------------------------------------------------------------

def test_only_finished_and_not_abandoned_matches_are_kept(league) -> None:
    ids = [m['id'] for m in fm.finished_matches(league)]
    # 5795491 is still to play; 4193691 (Bournemouth v Luton, 2023-24) was abandoned.
    assert ids == [5795363]


def test_match_pages_are_fetched_by_id_not_by_the_pairing_url(league) -> None:
    # The league pageUrl names the club pairing; it serves the wrong game for cup ties.
    assert fm.match_url(5795363) == 'https://www.fotmob.com/match/5795363'
    assert 'page_url' not in fm.finished_matches(league)[0]


def test_a_page_for_a_different_match_is_never_cached(match) -> None:
    with pytest.raises(fm.FotmobError, match='page is match 5795363'):
        fm.cached_slice(match, 6005647)
    assert fm.cached_slice(match, 5795363)['general']['matchId'] == '5795363'


def test_page_props_reads_next_data_and_rejects_other_pages() -> None:
    html = '<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"a":1}}}</script>'
    assert fm.page_props(html) == {'a': 1}
    with pytest.raises(fm.FotmobError, match='__NEXT_DATA__'):
        fm.page_props('<html></html>')


def test_season_format() -> None:
    assert fm.fotmob_season('2026-27') == '2026-2027'
    assert fm.league_url('2023-24').endswith('season=2023-2024')


# --------------------------------------------------------------------------
# Player stats
# --------------------------------------------------------------------------

def test_unused_substitutes_are_skipped(match) -> None:
    rows = by_name(fm.parse_player_stats(match['content']['playerStats']))
    assert 'Ben Wilson' not in rows
    assert {'David Raya', 'Matt Grimes', 'Carl Rushworth'} <= set(rows)


def test_labels_parse_to_columns_and_missing_labels_are_nan(match) -> None:
    rows = by_name(fm.parse_player_stats(match['content']['playerStats']))
    raya, grimes = rows['David Raya'], rows['Matt Grimes']
    assert raya['is_gk'] and raya['minutes'] == 90
    assert raya['xgot_faced'] == pytest.approx(0.04)
    assert raya['goals_prevented'] == pytest.approx(0.04)
    assert raya['fantasy_points'] == 6        # equals his FPL points that week
    assert np.isnan(raya['was_fouled'])       # label sent without a value
    assert np.isnan(grimes['saves'])          # label not sent for an outfielder
    assert grimes['blocks'] == 1 and grimes['clearances'] == 3 and grimes['recoveries'] == 3


def test_fraction_stats_keep_their_attempts(match) -> None:
    grimes = by_name(fm.parse_player_stats(match['content']['playerStats']))['Matt Grimes']
    assert (grimes['accurate_passes'], grimes['accurate_passes_att']) == (50, 56)
    assert (grimes['aerial_duels_won'], grimes['aerial_duels_won_att']) == (3, 4)


# --------------------------------------------------------------------------
# Shots
# --------------------------------------------------------------------------

def test_shot_totals_exclude_own_goals_and_penalties_from_npxg() -> None:
    shots = fm.parse_shots({'shots': [
        shot(eventType='Goal', isOnTarget=True, expectedGoals=0.4, expectedGoalsOnTarget=0.7),
        shot(situation='Penalty', eventType='Goal', isOnTarget=True, expectedGoals=0.79,
             expectedGoalsOnTarget=0.9),
        shot(isBlocked=True, isFromInsideBox=False, expectedGoals=0.05),
        shot(eventType='Goal', isOwnGoal=True, isOnTarget=True, expectedGoals=0.0,
             expectedGoalsOnTarget=0.5),
    ]})
    agg = fm.aggregate_shots(shots).iloc[0]
    assert agg['shots'] == 3 and agg['goals'] == 2
    assert agg['xg'] == pytest.approx(1.24)
    assert agg['npxg'] == pytest.approx(0.45)
    assert agg['xgot'] == pytest.approx(1.6)
    assert (agg['shots_on_target'], agg['shots_in_box'], agg['shots_blocked']) == (2, 2, 1)


def test_players_without_shots_get_zero_but_a_missing_shotmap_is_unknown(match) -> None:
    players, _, _ = fm.match_rows(match)
    grimes = players.set_index('player_name').loc['Matt Grimes']
    assert grimes['shots'] == 0 and grimes['xgot'] == 0

    no_map = copy.deepcopy(match)
    no_map['content']['shotmap'] = None
    players, _, _ = fm.match_rows(no_map)
    assert players[fm.SHOT_COLUMNS].isna().all().all()


def test_an_empty_shotmap_parses() -> None:
    players, shots, warnings = fm.match_rows({'content': {'shotmap': {'shots': []}, 'playerStats': {}}})
    assert players.empty and shots.empty and warnings == []


def test_keeper_xgot_faced_is_cross_checked_against_the_shots(match) -> None:
    assert fm.match_rows(match)[2] == []
    bad = copy.deepcopy(match)
    for p in bad['content']['playerStats'].values():
        if p['name'] == 'David Raya':
            p['stats'][0]['stats']['xGOT faced']['stat']['value'] = 1.5
    warnings = fm.match_rows(bad)[2]
    assert len(warnings) == 1 and warnings[0].startswith('David Raya')


# --------------------------------------------------------------------------
# FPL joins
# --------------------------------------------------------------------------

TEAMS = pd.DataFrame({'id': [1, 7, 12], 'name': ['Arsenal', 'Coventry City', 'Ipswich']})


def test_team_names_resolve_per_season() -> None:
    assert fm.team_lookup(TEAMS) == {9825: 1, 8669: 7, 9902: 12}


def test_matches_join_to_fpl_fixtures_and_unknown_clubs_fail_loudly() -> None:
    fixtures = pd.DataFrame({'id': [1], 'event': [1], 'team_h': [1], 'team_a': [7]})
    m = {'id': 5795363, 'home_id': 9825, 'home_name': 'Arsenal', 'away_id': 8669, 'away_name': 'Coventry City'}
    joined = fm.attach_fixtures([m], fixtures, fm.team_lookup(TEAMS))[0]
    assert (joined['gw'], joined['fpl_fixture'], joined['fpl_home'], joined['fpl_away']) == (1, 1, 1, 7)

    with pytest.raises(fm.FotmobError, match='999 Atlantis'):
        fm.attach_fixtures([{**m, 'away_id': 999, 'away_name': 'Atlantis'}], fixtures, fm.team_lookup(TEAMS))
    with pytest.raises(fm.FotmobError, match='no FPL fixture'):
        fm.attach_fixtures([{**m, 'home_id': 8669, 'away_id': 9825}], fixtures, fm.team_lookup(TEAMS))


@pytest.mark.parametrize('raw, expected', [
    ('Lukáš Horníček', 'lukas hornicek'),
    ('Pascal Groß', 'pascal gross'),
    ("Dara O'Shea", 'dara oshea'),
    ('Kalimuendo-Muinga', 'kalimuendo muinga'),
    ('Martin Ødegaard', 'martin odegaard'),
    ('Jakub Kiwior', 'jakub kiwior'),
    ('Michał Karbownik', 'michal karbownik'),
])
def test_name_normalisation(raw, expected) -> None:
    assert fm.normalise(raw) == expected


def test_name_scores() -> None:
    assert fm.name_score('David Raya', 'David', 'Raya Martín', 'Raya') == 0.95
    assert fm.name_score('Bukayo Saka', 'Bukayo', 'Saka', 'Saka') == 1.0
    assert fm.name_score('Gabriel Magalhães', 'Gabriel', 'dos Santos Magalhães', 'Gabriel') == 0.95
    assert fm.name_score('Igor Jesus', 'Igor Jesus', 'Maciel da Cruz', 'Igor Jesus') == 0.9
    assert fm.name_score('Bukayo Saka', 'Declan', 'Rice', 'Rice') < fm.NAME_MATCH_MIN


def fotmob_players(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=['fotmob_player_id', 'player_name', 'minutes', 'fantasy_points'])


def fpl_rows(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=['element', 'first_name', 'second_name', 'web_name',
                                       'minutes', 'total_points'])


def test_each_mapping_method() -> None:
    players = fotmob_players([
        (1, 'Bukayo Saka', 90, 6),         # name, minutes and points
        (2, 'Declan Rice', 88, 3),         # name and minutes; FPL points differ
        (3, 'Yéremi Pino', 70, 2),         # spelt differently; minutes and points unique
        (4, 'Nobody Known', 12, 1),        # nothing agrees
    ])
    fpl = fpl_rows([
        (10, 'Bukayo', 'Saka', 'Saka', 90, 6),
        (11, 'Declan', 'Rice', 'Rice', 89, 4),
        (12, 'Yéremy', 'Pino Santos', 'Yeremy', 70, 2),
        (13, 'Other', 'Player', 'Player', 45, 1),
    ])
    out = fm.map_match(players, fpl, {}).set_index('fotmob_player_id')
    assert out.loc[1, ['element', 'map_method']].tolist() == [10, 'name+minutes+points']
    assert out.loc[2, ['element', 'map_method']].tolist() == [11, 'name+minutes']
    assert out.loc[3, ['element', 'map_method']].tolist() == [12, 'minutes+points']
    assert pd.isna(out.loc[4, 'element'])


def test_minutes_and_points_alone_must_be_unambiguous() -> None:
    players = fotmob_players([(1, 'Aaa Bbb', 0.0, 0), (2, 'Ccc Ddd', 0.0, 0)])
    fpl = fpl_rows([(10, 'X', 'Y', 'Y', 0, 0), (11, 'Z', 'W', 'W', 0, 0)])
    assert fm.map_match(players, fpl, {})['element'].isna().all()


def test_overrides_win_over_the_matcher() -> None:
    players = fotmob_players([(1, 'Bukayo Saka', 90, 6)])
    fpl = fpl_rows([(10, 'Bukayo', 'Saka', 'Saka', 90, 6), (99, 'Someone', 'Else', 'Else', 0, 0)])
    out = fm.map_match(players, fpl, {1: 99}).iloc[0]
    assert (out['element'], out['map_method']) == (99, 'override')


def test_a_name_is_never_given_two_elements() -> None:
    # Two FotMob players share a surname; only one FPL row fits each on minutes.
    players = fotmob_players([(1, 'Ben White', 90, 2), (2, 'Joe White', 90, 2)])
    fpl = fpl_rows([(10, 'Ben', 'White', 'White', 90, 2)])
    assert fm.map_match(players, fpl, {})['element'].notna().sum() == 1


def test_overrides_are_read_per_season(tmp_path) -> None:
    path = tmp_path / 'overrides.csv'
    path.write_text('season,fotmob_player_id,element\n2026-27,1,10\n2025-26,1,77\n', encoding='utf-8')
    assert fm.load_overrides('2026-27', str(path)) == {1: 10}
    assert fm.load_overrides('2026-27', str(tmp_path / 'missing.csv')) == {}


def test_a_transferred_player_is_found_elsewhere_in_his_gameweek() -> None:
    # The live export files his GW1 under his new club's fixture.
    rows = pd.DataFrame({'gw': [1], 'player_name': ['Iliman Ndiaye'], 'minutes': [90.0],
                         'fantasy_points': [9.0], 'element': [np.nan], 'map_method': [None],
                         'map_confidence': [np.nan]})
    cands = pd.DataFrame({'GW': [1, 2], 'element': [237, 237], 'first_name': ['Iliman'] * 2,
                          'second_name': ['Ndiaye'] * 2, 'web_name': ['Ndiaye'] * 2,
                          'minutes': [90, 90], 'total_points': [9, 4]})
    out = fm.gameweek_fallback(rows, cands).iloc[0]
    assert (out['element'], out['map_method']) == (237, 'name+minutes+points (gw)')

    cands.loc[0, 'total_points'] = 2      # points disagree: leave it unmapped
    assert pd.isna(fm.gameweek_fallback(rows, cands).iloc[0]['element'])


def test_match_verification_share() -> None:
    rows = pd.DataFrame({'minutes': [90, 90, 0], 'element': [1, np.nan, np.nan]})
    assert fm.match_minutes_verified(rows) == 0.5


# --------------------------------------------------------------------------
# HTTP, robots and exit codes
# --------------------------------------------------------------------------

def test_fetcher_refuses_the_api() -> None:
    fetcher = fm.Fetcher(opener=lambda *a, **k: pytest.fail('must not fetch'))
    for url in ('https://www.fotmob.com/api/matchDetails?matchId=1', 'https://data.fotmob.com/stats/47.json'):
        with pytest.raises(fm.FotmobError, match='only public HTML'):
            fetcher.get(url)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetcher_spaces_requests_and_backs_off_on_429() -> None:
    sleeps, calls, now = [], [], [0.0]

    def opener(req, timeout):
        calls.append(req.get_header('User-agent'))
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, 'slow down', {}, None)
        return FakeResponse(b'ok')

    fetcher = fm.Fetcher(sleep=lambda s: sleeps.append(s), clock=lambda: now[0], opener=opener)
    assert fetcher.get('https://www.fotmob.com/match/1') == 'ok'
    assert calls == [fm.USER_AGENT, fm.USER_AGENT]
    assert sleeps[0] == fm.RETRY_BACKOFF_S[0]
    assert sleeps[1] == pytest.approx(fm.MIN_INTERVAL_S)   # the clock never moved


def test_robots_disallow_aborts() -> None:
    class Fetch:
        def get(self, url):
            return 'User-agent: *\nDisallow: /match/\n'

    with pytest.raises(fm.FotmobError, match='robots.txt does not allow'):
        fm.check_robots(Fetch(), [fm.match_url(1)])
    fm.check_robots(Fetch(), [fm.league_url('2026-27')])


def test_low_coverage_exits_2(monkeypatch) -> None:
    monkeypatch.setattr(fm, 'check_robots', lambda *a, **k: None)
    monkeypatch.setattr(fm, 'download', lambda *a, **k: [])
    report = {'mapped_minutes_share': 0.9, 'unmapped': ['GW1 Someone (1), 90 min']}
    monkeypatch.setattr(fm, 'build_season', lambda *a, **k: report)
    assert fm.main(['--season', '2026-27']) == 2
    report['mapped_minutes_share'] = 0.99
    assert fm.main(['--season', '2026-27']) == 0


def test_a_failed_fetch_exits_1(monkeypatch) -> None:
    def blocked(*a, **k):
        raise fm.FotmobError('robots.txt does not allow fetching x')
    monkeypatch.setattr(fm, 'check_robots', blocked)
    assert fm.main(['--season', '2026-27']) == 1
