"""Project a prediction forward over several gameweeks.

The problem
-----------
Every feature in this project is a lag or a rolling mean of matches a player
has already played, so predicting GW+1 is easy and predicting GW+3 looks
impossible: the features for GW+3 want GW+2's result, which has not happened.
Chaining predictions into each other -- predict GW+1, pretend it is real,
predict GW+2 from it -- compounds error on every step and cannot fill in the
inputs a prediction does not produce at all, like bps or minutes.

What this does instead
----------------------
Freeze the player. His form, his availability, his price and his minutes
history stay exactly as they are today, and only the fixture moves forward.
A GW+3 prediction is then an honest statement: this is the player as he is
now, against the side he meets in three weeks, at that venue.

That is a real approximation and it does lose something -- a player in the
middle of a hot streak is treated as though the streak neither continues nor
ends. Measured on the 2024-25 and 2025-26 seasons, against the rank
correlation of an ordinary next-gameweek prediction, it holds up better than
the shape of the features suggests:

    gameweeks ahead   1      2      3      4      5
    signal retained   95.9%  92.8%  90.3%  88.5%  87.4%

Roughly 2.6% of the ranking decays per gameweek. Six weeks out is still worth
most of one week out, which is what makes planning a squad over a horizon
worth doing rather than a way of dressing up noise.

Why only the fixture features move
----------------------------------
Of the features the models use, exactly the fx_* family depends on which
match is being played -- 20 of MID's 74. They are built in
fpl_pipeline.ipynb's add_fixture_features from team-level rolling form joined
on (season, team, fixture), so a future fixture's values are each side's
current form arranged against the opponent it will actually face.
Nothing about the player enters them, which is why they can be recomputed for
a match that has not happened while the other 54 features stay put.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# The rolling team-form columns add_fixture_features builds, and the venue
# split it keeps separately because a side's away defence is its own statistic.
FORM_WINDOWS = (4, 8)
VENUE_WINDOW = 6


def _team_match_table(history: pd.DataFrame, season: str) -> pd.DataFrame:
    """One row per team-match: goals for and against, in order played.

    Mirrors the aggregation at the top of add_fixture_features so the numbers
    projected forward are the same quantity the models were trained on.
    """
    needed = {'my_team_score', 'opponent_team_score', 'team', 'fixture', 'GW', 'was_home'}
    missing = needed - set(history.columns)
    if missing:
        raise KeyError(f"history is missing {sorted(missing)}; cannot project fixtures")

    played = history[(history['season'] == season)].copy()
    if 'is_prediction_row' in played.columns:
        played = played[~played['is_prediction_row'].fillna(False).astype(bool)]
    if played.empty:
        return pd.DataFrame()

    table = (played.groupby(['team', 'fixture', 'GW', 'was_home'])
             .agg(scored=('my_team_score', 'max'),
                  conceded=('opponent_team_score', 'max'))
             .reset_index()
             .sort_values(['team', 'GW']))
    return table


def team_form_snapshot(history: pd.DataFrame, season: str) -> tuple[dict, dict]:
    """Each team's form as it stands going into its next match.

    add_fixture_features assigns a match the rolling mean of the matches
    *before* it, via .shift(1). The value that shift would give the next
    unplayed match is the unshifted rolling mean at the last played one, which
    is what this returns: (overall by team, venue-specific by team and venue).
    """
    table = _team_match_table(history, season)
    if table.empty:
        return {}, {}

    overall: dict = {}
    for team, block in table.groupby('team'):
        block = block.sort_values('GW')
        entry = {}
        for window in FORM_WINDOWS:
            entry[f'att_form_{window}'] = block['scored'].rolling(
                window, min_periods=1).mean().iloc[-1]
            entry[f'def_form_{window}'] = block['conceded'].rolling(
                window, min_periods=1).mean().iloc[-1]
            entry[f'cs_rate_{window}'] = block['conceded'].eq(0).rolling(
                window, min_periods=1).mean().iloc[-1]
        overall[team] = entry

    venue: dict = {}
    for (team, was_home), block in table.groupby(['team', 'was_home']):
        block = block.sort_values('GW')
        venue[(team, bool(was_home))] = {
            'att_form_venue': block['scored'].rolling(
                VENUE_WINDOW, min_periods=1).mean().iloc[-1],
            'def_form_venue': block['conceded'].rolling(
                VENUE_WINDOW, min_periods=1).mean().iloc[-1],
        }

    return overall, venue


def _side(overall: dict, venue: dict, team: str, at_home: bool) -> dict:
    """One side's full form vector for a match at the given venue."""
    out = dict(overall.get(team, {}))
    out.update(venue.get((team, at_home), {}))
    return out


def fixture_features(team: str, opponent: str, at_home: bool,
                     overall: dict, venue: dict) -> dict:
    """The fx_* block for a player of `team` facing `opponent`.

    own_* is this side's form at this venue; opp_* is the opponent's form at
    theirs, which is the venue flipped.
    """
    own = _side(overall, venue, team, at_home)
    # The opponent's venue form is for the venue they are at, which is the
    # opposite of ours: our home match is their away one.
    opp = _side(overall, venue, opponent, not at_home)

    values: dict = {}
    for key, value in own.items():
        values[f'fx_own_{key}'] = value
    for key, value in opp.items():
        values[f'fx_opp_{key}'] = value

    # The three summary edges, defined exactly as in add_fixture_features.
    if 'fx_own_att_form_8' in values and 'fx_opp_def_form_8' in values:
        values['fx_attack_edge'] = values['fx_own_att_form_8'] - values['fx_opp_def_form_8']
        values['fx_defence_edge'] = values['fx_opp_att_form_8'] - values['fx_own_def_form_8']
        values['fx_cs_chance'] = values['fx_own_cs_rate_8'] - values['fx_opp_att_form_8']

    values['fx_is_home'] = int(at_home)
    return values


def upcoming_fixtures(fixtures: pd.DataFrame, first_gw: int, horizon: int,
                      id_to_name: dict) -> dict:
    """{gameweek: {team_name: [(opponent_name, at_home), ...]}}.

    A list per team rather than a single opponent, because a double gameweek
    is two fixtures and a blank is an empty list -- the two cases this whole
    exercise exists to get right.
    """
    event_col = 'event' if 'event' in fixtures.columns else 'GW'
    window = range(first_gw, first_gw + horizon)
    schedule: dict = {gw: {} for gw in window}

    for _, row in fixtures.iterrows():
        gw = row.get(event_col)
        if pd.isna(gw) or int(gw) not in schedule:
            continue
        gw = int(gw)
        home = id_to_name.get(row.get('team_h'))
        away = id_to_name.get(row.get('team_a'))
        if not home or not away:
            continue
        schedule[gw].setdefault(home, []).append((away, True))
        schedule[gw].setdefault(away, []).append((home, False))

    return schedule


def project(base_rows: pd.DataFrame, feature_names: list, schedule: dict,
            overall: dict, venue: dict, gameweek: int) -> pd.DataFrame:
    """`base_rows` re-aimed at `gameweek`, one row per fixture that week.

    Players whose club is blank that gameweek drop out; players with a double
    come back twice, one row per fixture, for the caller to sum.
    """
    week = schedule.get(gameweek, {})
    fx_columns = [f for f in feature_names if f.startswith('fx_')]

    out = []
    for team, matches in week.items():
        squad = base_rows[base_rows['team'] == team]
        if squad.empty:
            continue
        for opponent, at_home in matches:
            values = fixture_features(team, opponent, at_home, overall, venue)
            block = squad.copy()
            for column in fx_columns:
                if column in values:
                    block[column] = values[column]
            block['GW'] = gameweek
            block['opponent_team'] = opponent
            block['was_home'] = at_home
            out.append(block)

    if not out:
        return base_rows.iloc[0:0].copy()
    return pd.concat(out, ignore_index=True)
