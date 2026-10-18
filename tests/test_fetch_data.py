from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fetch_data import unfinished_clubs  # noqa: E402


def fixtures(rows: list) -> pd.DataFrame:
    """(event, team_h, team_a, finished), as fetch_season_olbauday writes fixtures.csv."""
    return pd.DataFrame(rows, columns=['event', 'team_h', 'team_a', 'finished'])


def test_a_finished_gameweek_holds_nothing_back() -> None:
    assert unfinished_clubs(fixtures([(7, 1, 2, True), (7, 3, 4, True)]), 7) == set()


def test_both_clubs_in_a_match_still_to_play_are_held_back() -> None:
    week = fixtures([(7, 1, 2, True), (7, 3, 4, False)])
    assert unfinished_clubs(week, 7) == {3, 4}


def test_a_double_gameweek_waits_for_the_second_match() -> None:
    # Club 1's per-gameweek row covers both matches, so it is not a result
    # until both are over.
    week = fixtures([(7, 1, 2, True), (7, 3, 1, False)])
    assert unfinished_clubs(week, 7) == {1, 3}


def test_other_gameweeks_and_blank_clubs_are_not_held_back() -> None:
    # Club 5 has no match in GW7; GW8 has not started.
    week = fixtures([(7, 1, 2, True), (8, 1, 5, False)])
    assert unfinished_clubs(week, 7) == set()


def test_finished_read_back_as_text_or_blank() -> None:
    week = fixtures([(7, 1, 2, 'True'), (7, 3, 4, 'False'), (7, 5, 6, np.nan)])
    assert unfinished_clubs(week, 7) == {3, 4, 5, 6}


def test_float_club_ids_from_a_player_map_still_match() -> None:
    # The player -> club map yields floats once any player is unmapped.
    team_ids = pd.Series([1.0, 3.0, np.nan])
    held = team_ids.isin(unfinished_clubs(fixtures([(7, 1, 2, True), (7, 3, 4, False)]), 7))
    assert held.tolist() == [False, True, False]


def test_no_fixtures_holds_nothing_back() -> None:
    assert unfinished_clubs(pd.DataFrame(), 7) == set()
