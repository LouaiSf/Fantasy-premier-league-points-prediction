from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import predict_gameweek as pg  # noqa: E402

NOW = pd.Timestamp('2026-10-22T12:00:00Z')


def test_between_deadlines_the_next_round_flag_is_the_one_predicted() -> None:
    # GW7 finished, GW8 next: this_round is GW7's stale value.
    fit_again = {'chance_of_playing_this_round': 0, 'chance_of_playing_next_round': 100}
    new_doubt = {'chance_of_playing_this_round': 100, 'chance_of_playing_next_round': 75}
    assert pg.playing_chance(fit_again, predicting_current=False) == 100
    assert pg.playing_chance(new_doubt, predicting_current=False) == 75


def test_during_a_live_gameweek_this_round_is_the_one_predicted() -> None:
    row = {'chance_of_playing_this_round': 25, 'chance_of_playing_next_round': 75}
    assert pg.playing_chance(row, predicting_current=True) == 25
    assert pg.playing_chance({'chance_of_playing_next_round': 50}, predicting_current=True) == 50


def test_expected_back_reads_fpl_news_and_rolls_the_year() -> None:
    assert pg.expected_back('Knee injury - Expected back 7 Nov', NOW) == pd.Timestamp('2026-11-07', tz='UTC')
    assert pg.expected_back('Suspended until 31 Oct', NOW) == pd.Timestamp('2026-10-31', tz='UTC')
    assert pg.expected_back('Ankle - Expected back 3 Jan', NOW) == pd.Timestamp('2027-01-03', tz='UTC')
    assert pg.expected_back('Thigh injury - Unknown return date', NOW) is None


def rows(**columns) -> pd.DataFrame:
    return pd.DataFrame(columns)


def test_a_doubt_decays_each_week_instead_of_lasting_the_whole_horizon() -> None:
    frame = rows(chance=[75.0, np.nan], status=['d', 'a'], news=['Calf - 75% chance', ''])
    one = pg.horizon_chance(frame, 1, pd.Timestamp('2026-10-31', tz='UTC'), NOW)
    two = pg.horizon_chance(frame, 2, pd.Timestamp('2026-11-07', tz='UTC'), NOW)
    assert one.iloc[0] == 87.5 and two.iloc[0] == 93.75
    # No flag stays no flag.
    assert np.isnan(one.iloc[1])


def test_a_return_date_holds_the_cap_at_zero_until_then() -> None:
    frame = rows(chance=[0.0], status=['i'], news=['Hamstring - Expected back 7 Nov'])
    before = pg.horizon_chance(frame, 1, pd.Timestamp('2026-10-31T15:00Z'), NOW)
    after = pg.horizon_chance(frame, 3, pd.Timestamp('2026-11-21T15:00Z'), NOW)
    assert before.iloc[0] == 0.0
    assert np.isnan(after.iloc[0])


def test_a_player_who_has_left_stays_unavailable() -> None:
    frame = rows(chance=[0.0], status=['u'], news=['Has joined Getafe on loan'])
    assert pg.horizon_chance(frame, 5, pd.Timestamp('2026-12-01', tz='UTC'), NOW).iloc[0] == 0.0


def test_the_published_following_week_flag_starts_the_decay() -> None:
    frame = rows(chance=[25.0], chance_following=[50.0], status=['d'], news=[''])
    assert pg.horizon_chance(frame, 1, None, NOW).iloc[0] == 50.0
    assert pg.horizon_chance(frame, 2, None, NOW).iloc[0] == 75.0
