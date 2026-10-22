from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_dataset as bd  # noqa: E402


def match_rows(fixture, home, away, players, season='2017-18'):
    """Rows for one fixture: players is [(element, team, was_home)]."""
    return [{'season': season, 'fixture': fixture, 'element': element, 'team': team,
             'was_home': was_home, 'opponent_team': away if was_home else home}
            for element, team, was_home in players]


def test_team_is_the_side_the_player_played_for() -> None:
    # Element 3 is filed under his end-of-season club, Everton, for a match
    # Swansea (away) played at West Ham.
    df = pd.DataFrame(match_rows(10, 'West Ham', 'Swansea',
                                 [(1, 'West Ham', True), (2, 'Swansea', False),
                                  (3, 'Everton', False)]))
    out = bd.derive_fixture_teams(df)
    assert out['team'].tolist() == ['West Ham', 'Swansea', 'Swansea']


def test_team_left_alone_when_a_fixture_has_one_side_only() -> None:
    df = pd.DataFrame(match_rows(11, 'Hull', 'Stoke', [(1, 'Hull', True)]))
    assert bd.derive_fixture_teams(df)['team'].tolist() == ['Hull']


def test_name_key_matches_every_season_spelling() -> None:
    assert bd._name_key('Petr_Cech_1') == bd._name_key('Petr Čech') == 'petr cech'
    assert bd._name_key('David_Ospina') == 'david ospina'
    assert bd._name_key("N'Golo Kanté") == 'n golo kante'


def write_raw(root: Path, season: str, rows: list) -> None:
    (root / 'data' / season).mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=['id', 'code']).to_csv(
        root / 'data' / season / 'players_raw.csv', index=False)


def test_player_id_follows_fpl_code_across_seasons_and_splits_namesakes(tmp_path, monkeypatch) -> None:
    write_raw(tmp_path, '2019-20', [(7, 111), (8, 222)])
    write_raw(tmp_path, '2020-21', [(70, 111), (80, 222), (90, 333)])
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame({
        'season': ['2019-20', '2019-20', '2020-21', '2020-21', '2020-21'],
        'element': [7, 8, 70, 80, 90],
        'name': ['Ben_Davies_7', 'Mesut_Ozil_8', 'Ben Davies', 'Mesut Özil', 'Ben Davies'],
    })
    out = bd.add_player_ids(df).set_index(['season', 'element'])['player_id']
    assert out[('2019-20', 7)] == out[('2020-21', 70)] == 111
    assert out[('2019-20', 8)] == out[('2020-21', 80)] == 222
    # A second Ben Davies in the same season is a different player.
    assert out[('2020-21', 90)] == 333


def test_player_without_a_code_borrows_it_by_name_or_stays_season_local(tmp_path, monkeypatch) -> None:
    write_raw(tmp_path, '2024-25', [(5, 555)])
    write_raw(tmp_path, '2025-26', [(1, 999)])   # snapshot without the late signings
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame({
        'season': ['2024-25', '2025-26', '2025-26'],
        'element': [5, 747, 748],
        'name': ['Josh Dasilva', 'Josh Dasilva', 'Ezra Mayers'],
    })
    out = bd.add_player_ids(df).set_index(['season', 'element'])['player_id']
    assert out[('2025-26', 747)] == 555
    assert out[('2025-26', 748)] < 0


def test_fotmob_defensive_counts_replace_fbref_where_present(tmp_path, monkeypatch) -> None:
    fm_dir = tmp_path / 'data' / '2024-25' / 'fotmob'
    fm_dir.mkdir(parents=True)
    pd.DataFrame({
        'element': [1, 2], 'fpl_fixture': [40, 40],
        'blocks': [1, None], 'interceptions': [2, 0], 'clearances': [4, 1],
        'tackles': [3, 0], 'recoveries': [5, 2],
    }).to_csv(fm_dir / 'player_match.csv', index=False)
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame({
        'season': ['2024-25'] * 3, 'element': [1, 2, 3], 'fixture': [40, 40, 40],
        'clearances_blocks_interceptions': [0, 9, 4], 'tackles': [0, 9, 1],
        'recoveries': [0, 0, 0], 'defensive_source': ['none', 'fbref', 'fbref'],
    })
    out = bd.overlay_fotmob_defensive(df).set_index('element')
    assert out.loc[1, ['clearances_blocks_interceptions', 'tackles', 'recoveries']].tolist() == [7, 3, 5]
    # A keeper's missing blocks line counts as none.
    assert out.loc[2, 'clearances_blocks_interceptions'] == 1
    assert out.loc[3, 'tackles'] == 1 and out.loc[3, 'defensive_source'] == 'fbref'
    assert out.loc[1, 'defensive_source'] == 'fotmob'


@pytest.mark.parametrize('position,contribution,bonus', [
    ('DEF', 10, 2), ('DEF', 9, 0), ('MID', 12, 2), ('FWD', 11, 0), ('GK', 30, 0)])
def test_defensive_contribution_bonus_thresholds(position, contribution, bonus) -> None:
    row = {'total_points': 1, 'position': position, 'defensive_contribution': contribution}
    assert bd.calculate_modified_points(row) == 1 + bonus
