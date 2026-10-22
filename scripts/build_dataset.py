"""Rebuild all_seasons_data.csv and all_seasons_data_final.csv.

Why this is not just "re-run fpl_pipeline.ipynb"
-----------------------------------------
The notebook builds all_seasons_data_final.csv in two halves:

  cells 3-34   merge every season's merged_gw.csv, map positions, teams and
               opponents, adjust 2016-17..2018-19 points  ->  all_seasons_data.csv
  cell  40     assign game_number (chronological match index per player-season)
  cells 35-80  merge FBref defensive stats, recompute defensive contribution
               and re-modify points                       ->  all_seasons_data_final.csv

game_number is assigned in the middle of the second half, so it is picked up
here separately: the feature-engineering stage sorts on it, and every
downstream model drops rows with game_number < 5.

The second half reads defensive_stats_raw.csv, which is gitignored and is not
in this checkout. Re-scraping it from FBref takes roughly 380 requests per
season under soccerdata's rate limiting.

It does not need re-scraping. The existing all_seasons_data_final.csv already
contains the *output* of that merge, so this script lifts the defensive
columns straight out of it and joins them onto the rebuilt frame on
(season, element, fixture) -- player id and match id, both stable and numeric,
rather than the fuzzy-matched name the notebook had to use.

Rows the lookup cannot cover are the 13,105 rows of 2024-25 GW22-38 recovered
by scripts/rebuild_merged_gw.py: they were never in the old file, so no FBref
stats were ever merged for them. They get zeros and are flagged with
has_fbref_defensive=0 rather than being silently mixed in, because otherwise a
model would read "0 tackles" as a real observation for half of a test season.

Usage
-----
    python scripts/build_dataset.py --write
    python scripts/build_dataset.py --write --skip-raw   # reuse all_seasons_data.csv
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import unicodedata

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range  # noqa: E402

NOTEBOOK = 'fpl_pipeline.ipynb'
RAW_OUT = 'all_seasons_data.csv'
FINAL_OUT = 'all_seasons_data_final.csv'

# Seasons whose defensive stats came from the FBref merge, and whose points
# therefore get the defensive-contribution adjustment in the notebook's step 5.
# 2016-17..2018-19 are adjusted earlier (cell 25) and carry native FPL
# defensive columns; 2025-26 ships defensive contribution from the FPL API.
MERGED_SEASONS = ['2019-20', '2020-21', '2021-22', '2022-23', '2023-24', '2024-25']

DEFENSIVE_COLS = ['tackles', 'recoveries', 'clearances_blocks_interceptions']
JOIN_KEYS = ['season', 'element', 'fixture']

# FotMob publishes Opta's own defensive counts: against FPL's native columns
# in 2025-26 its blocks+interceptions+clearances, tackles and recoveries
# correlate 0.999 and are identical on 98-99% of rows. The FBref values these
# seasons carried correlate only 0.34-0.62 with them, never had recoveries,
# and covered only 52% of 2024-25. So wherever FotMob has the row, it wins.
FOTMOB_DEFENSIVE = {'clearances_blocks_interceptions': ('blocks', 'interceptions', 'clearances'),
                    'tackles': ('tackles',), 'recoveries': ('recoveries',)}


# The two functions below are copied verbatim from fpl_pipeline.ipynb step 5 so that
# recovered rows are scored by exactly the same rules as every other row.
def calculate_defensive_contribution_row(row):
    """Calculate defensive contribution based on position"""
    position = row['position']
    cbi = row.get('clearances_blocks_interceptions', 0) or 0
    tackles = row.get('tackles', 0) or 0
    recoveries = row.get('recoveries', 0) or 0

    if position == 'DEF':
        return cbi + tackles
    elif position in ['MID', 'FWD']:
        return cbi + tackles + recoveries
    else:  # GK or unknown
        return 0


def calculate_modified_points(row):
    """Add 2 bonus points for defensive contribution threshold"""
    points = row['total_points']
    position = row['position']
    def_contrib = row.get('defensive_contribution', 0) or 0

    if position == 'DEF' and def_contrib >= 10:
        points += 2
    elif position in ['MID', 'FWD'] and def_contrib >= 12:
        points += 2
    return points


NOTEBOOK_SEASONS = ('2016-17', '2017-18', '2018-19', '2019-20', '2020-21',
                    '2021-22', '2022-23', '2023-24', '2024-25', '2025-26')


def discover_extra_seasons() -> list:
    """Season folders on disk that the notebook cells know nothing about.

    The merge cells name every season in hardcoded variables
    (data_merged_gw_2016_17 and so on), so a new season means editing eight
    cells. Seasons from 2020-21 onwards all share the modern merged_gw schema,
    so they can be appended generically instead -- which means next season
    needs a fetch and nothing else.
    """
    if not os.path.isdir('data'):
        return []
    found = []
    for name in sorted(os.listdir('data')):
        if name in NOTEBOOK_SEASONS or not name[:4].isdigit():
            continue
        if os.path.exists(os.path.join('data', name, 'gws', 'merged_gw.csv')):
            found.append(name)
    return found


def load_extra_season(season: str, template: pd.DataFrame) -> pd.DataFrame | None:
    """Bring one unknown season up to the merged frame's schema.

    Mirrors what cells 15/17/28/32 do for 2025-26: drop xP, map opponent ids to
    names, tag the season, and compute defensive_contribution. Any column the
    template has and this season lacks is filled with 0 rather than left
    missing, so the concat cannot silently widen the frame.
    """
    path = os.path.join('data', season, 'gws', 'merged_gw.csv')
    df = read_csv_tolerant(path)
    if df.empty:
        return None

    df = df.drop(columns=[c for c in ('xP',) if c in df.columns])
    df['season'] = season

    teams_path = os.path.join('data', season, 'teams.csv')
    if 'opponent_team' in df.columns and os.path.exists(teams_path):
        teams = read_csv_tolerant(teams_path)
        if {'id', 'name'} <= set(teams.columns):
            mapping = dict(zip(teams['id'], teams['name']))
            df['opponent_team'] = df['opponent_team'].map(mapping).fillna(df['opponent_team'])

    if 'position' in df.columns:
        df['position'] = df['position'].replace({
            'Goalkeeper': 'GK', 'Defender': 'DEF',
            'Midfielder': 'MID', 'Forward': 'FWD', 'GKP': 'GK',
        })

    for col in template.columns:
        if col not in df.columns:
            df[col] = 0
    df = df[[c for c in template.columns if c in df.columns]]

    df['defensive_contribution'] = df.apply(calculate_defensive_contribution_row, axis=1)
    print(f"  {season}: {len(df):,} rows, GW "
          f"{int(df['GW'].min())}-{int(df['GW'].max())}")
    return df


EXPECTED_COLS = ['expected_goals', 'expected_assists',
                 'expected_goal_involvements', 'expected_goals_conceded']


def add_expected_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Carry FPL's xG/xA through from the source gameweek files.

    These are the strongest public signal for whether a player is about to
    return, and the pipeline was dropping them: the merge cells keep only the
    columns every season shares, and xG first appears in 2022-23.

    Joined on (season, element, fixture) -- ids, not names. Seasons without the
    columns get zeros and has_xg=0, so a model can tell "no shot taken" from
    "this season predates the stat", which matters because those two mean
    completely different things and only one of them is information.
    """
    print("\n--- carrying over xG / xA from source ---")
    frames = []
    for season in sorted(df['season'].unique()):
        path = os.path.join('data', season, 'gws', 'merged_gw.csv')
        if not os.path.exists(path):
            continue
        head = read_csv_tolerant(path, nrows=0)
        available = [c for c in EXPECTED_COLS if c in head.columns]
        if not available:
            print(f"  {season}: no expected-goals columns in source")
            continue
        block = read_csv_tolerant(path, usecols=['element', 'fixture'] + available)
        block['season'] = season
        frames.append(block)
        print(f"  {season}: {len(block):,} rows, {len(available)} columns")

    for col in EXPECTED_COLS:
        df[col] = 0.0
    df['has_xg'] = 0

    if not frames:
        print("  nothing to join; has_xg = 0 everywhere")
        return df

    lookup = pd.concat(frames, ignore_index=True)
    lookup = lookup.drop_duplicates(subset=JOIN_KEYS, keep='first')

    before = len(df)
    merged = df.drop(columns=EXPECTED_COLS).merge(
        lookup, on=JOIN_KEYS, how='left', suffixes=('', '_src'))
    assert len(merged) == before, f"join changed row count: {before} -> {len(merged)}"

    for col in EXPECTED_COLS:
        if col not in merged.columns:
            merged[col] = np.nan
    merged['has_xg'] = merged[EXPECTED_COLS].notna().any(axis=1).astype(int)
    for col in EXPECTED_COLS:
        merged[col] = pd.to_numeric(merged[col], errors='coerce').fillna(0.0)

    covered = int(merged['has_xg'].sum())
    print(f"  rows with xG: {covered:,} / {len(merged):,} "
          f"({covered / len(merged) * 100:.0f}%)")
    return merged


def build_raw() -> pd.DataFrame:
    """Run the notebook's own season-merging cells (3..34), then cell 40."""
    print("=" * 78)
    print("STAGE 1  merge every season  (fpl_pipeline.ipynb cells 3..34)")
    print("=" * 78)
    ns = run_range(
        NOTEBOOK,
        first="# What differs between seasons",
        last="# save all seasons data to a csv file",
        namespace={'pd': pd, 'np': np},
    )
    df = ns['all_seasons_data']
    print(f"\nmerged seasons: {df.shape[0]:,} rows x {df.shape[1]} cols")

    extra = discover_extra_seasons()
    if extra:
        print(f"\nappending {len(extra)} season(s) the notebook does not know about:")
        frames = [df]
        for season in extra:
            loaded = load_extra_season(season, df)
            if loaded is not None and len(loaded):
                frames.append(loaded)
        if len(frames) > 1:
            df = pd.concat(frames, ignore_index=True)
            print(f"  total now: {df.shape[0]:,} rows")

    return add_game_number(df)


def add_game_number(df: pd.DataFrame) -> pd.DataFrame:
    """Run the notebook's own game_number cell (cell 40).

    That cell sits inside the FBref half of the notebook, which cannot run
    here, but it only needs all_seasons_df and kickoff_time. Without it the
    feature stage dies with KeyError: 'game_number'.
    """
    print("\n--- assigning game_number (fpl_pipeline.ipynb cell 40) ---")
    anchor = "# Assign game_number using kickoff_time for ALL seasons"
    ns = run_range(
        NOTEBOOK, first=anchor, last=anchor,
        namespace={'pd': pd, 'np': np, 'all_seasons_df': df,
                   'all_seasons_data': df},   # alias used in some notebook cells
        verbose=False,
    )
    out = ns['all_seasons_updated']
    assert 'game_number' in out.columns, 'cell 40 did not produce game_number'
    assert len(out) == len(df), f'row count changed: {len(df)} -> {len(out)}'
    assert out['game_number'].notna().all(), 'some rows have no game_number'
    print(f"  game_number range: {out.game_number.min()}..{out.game_number.max()}")
    return out


def read_csv_tolerant(path: str, **kwargs) -> pd.DataFrame:
    """Read a CSV whose encoding is not known up front.

    Outputs are written as utf-8, but the vaastav source files are a mix of
    utf-8 and latin-1, and files produced by earlier versions of this pipeline
    are latin-1. Reading those with pandas' utf-8 default dies on the first
    accented player name.
    """
    last_error = None
    for encoding in ('utf-8', 'latin-1'):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"could not decode {path} as utf-8 or latin-1") from last_error


def defensive_lookup(path: str) -> pd.DataFrame | None:
    """Defensive columns from the previous all_seasons_data_final.csv."""
    if not os.path.exists(path):
        print(f"\nWARNING: {path} not found -- no defensive stats to carry over.")
        print("Every row will be flagged has_fbref_defensive=0.")
        return None

    # If the source is itself a previous output of this script, it already
    # carries has_fbref_defensive. Take that flag rather than re-deriving it:
    # the unmatched rows were filled with 0 on the way out, so notna() would
    # now report them as real observations and the distinction would be lost
    # the first time anyone re-ran the rebuild.
    header = read_csv_tolerant(path, nrows=0)
    cols = JOIN_KEYS + DEFENSIVE_COLS
    carries_flag = 'has_fbref_defensive' in header.columns
    if carries_flag:
        cols = cols + ['has_fbref_defensive']
        print("  source already carries has_fbref_defensive; reusing it")

    old = read_csv_tolerant(path, usecols=cols)

    dupes = old.duplicated(subset=JOIN_KEYS).sum()
    if dupes:
        print(f"  note: {dupes} duplicate rows on {JOIN_KEYS} in the old file, keeping first")
        old = old.drop_duplicates(subset=JOIN_KEYS, keep='first')

    print(f"  defensive lookup: {len(old):,} player-matches")
    return old


def fotmob_defensive(season: str) -> pd.DataFrame | None:
    """(element, fixture) -> FPL-style defensive columns from FotMob, or None."""
    path = os.path.join('data', season, 'fotmob', 'player_match.csv')
    if not os.path.exists(path):
        return None
    needed = sorted({c for parts in FOTMOB_DEFENSIVE.values() for c in parts})
    fm = read_csv_tolerant(path, usecols=['element', 'fpl_fixture'] + needed)
    fm = fm.dropna(subset=['element', 'fpl_fixture'])
    out = pd.DataFrame({'element': fm['element'].astype(int),
                        'fixture': fm['fpl_fixture'].astype(int)})
    for col, parts in FOTMOB_DEFENSIVE.items():
        # Keepers have no blocks line at all; that is a zero, not a gap.
        out[col] = fm[list(parts)].fillna(0).sum(axis=1).to_numpy()
    out['season'] = season
    return out.drop_duplicates(subset=JOIN_KEYS, keep='first')


def overlay_fotmob_defensive(df: pd.DataFrame) -> pd.DataFrame:
    """Replace FBref-era defensive stats with FotMob's wherever it has the match."""
    frames = [f for s in MERGED_SEASONS if (f := fotmob_defensive(s)) is not None]
    if not frames:
        print("  no FotMob player_match.csv for the FBref seasons; keeping FBref")
        return df
    lookup = pd.concat(frames, ignore_index=True)
    before = len(df)
    merged = df.merge(lookup, on=JOIN_KEYS, how='left', suffixes=('', '_fotmob'),
                      indicator='_fm')
    assert len(merged) == before, f"FotMob join changed row count: {before} -> {len(merged)}"
    hit = merged['_fm'] == 'both'
    for col in DEFENSIVE_COLS:
        merged.loc[hit, col] = merged.loc[hit, f'{col}_fotmob']
    merged.loc[hit, 'defensive_source'] = 'fotmob'
    merged = merged.drop(columns=['_fm'] + [f'{c}_fotmob' for c in DEFENSIVE_COLS])
    print(f"  FotMob defensive stats on {int(hit.sum()):,} rows "
          f"({', '.join(sorted(lookup['season'].unique()))})")
    return merged


def derive_fixture_teams(df: pd.DataFrame) -> pd.DataFrame:
    """Set each row's club to the side it played for in that fixture.

    vaastav's 2016-17..2019-20 files give some players their end-of-season
    club for every gameweek: 1,080 rows (364 with minutes) name a club that
    was neither side of the match, which made the fixture features build
    team-match rows for games those clubs never played. Each fixture's two
    clubs are recoverable from the rows themselves -- the home side is the
    opponent of every away row and vice versa -- so this needs no fixtures.csv,
    which 2016-17 and 2017-18 do not have.
    """
    home = df['was_home'].astype(str).str.lower().isin(['true', '1'])
    sides = (df.assign(_home=home)
               .groupby(['season', 'fixture', '_home'])['opponent_team']
               .agg(lambda s: s.mode().iat[0] if not s.mode().empty else np.nan)
               .unstack()
               .reindex(columns=[False, True]))
    # The opponent of the away rows is the home club, and the reverse.
    sides = sides.rename(columns={False: '_home_team', True: '_away_team'})
    joined = df[['season', 'fixture']].join(sides, on=['season', 'fixture'])
    derived = joined['_home_team'].where(home.to_numpy(), joined['_away_team'])
    derived = pd.Series(derived.to_numpy(), index=df.index).fillna(df['team'])
    changed = derived != df['team']
    if changed.any():
        print(f"\n--- team taken from the fixture: {int(changed.sum()):,} rows corrected ---")
        print(df.loc[changed].groupby('season').size().to_string())
    df['team'] = derived
    return df


def _name_key(name) -> str:
    """'Petr_Cech_1' / 'Petr Čech' -> 'petr cech': the season-independent spelling."""
    text = re.sub(r'_\d+$', '', str(name)).replace('_', ' ')
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text)).strip()


def add_player_ids(df: pd.DataFrame) -> pd.DataFrame:
    """A player id that holds across seasons: FPL's own `code`.

    The feature stage followed a player from season to season by `name`, but
    the name's spelling changes with the source: 'David_Ospina' (2016-18),
    'Petr_Cech_1' (2018-20), 'Mesut Özil' (2020-). Only 0 of 625, 2 of 666 and
    0 of 712 players carried their history into 2018-19, 2019-20 and 2020-21,
    and two Ben Davies (Spurs, Liverpool) shared one history in 2020-23.
    `code` is FPL's permanent player id. Elements missing from a season's
    players_raw.csv (2025-26's is a 746-player snapshot; 95 later signings
    are absent) take the code of the same normalised name in another season
    when that name means one player; otherwise they get a season-local id.
    """
    codes = []
    for season in sorted(df['season'].unique()):
        path = os.path.join('data', season, 'players_raw.csv')
        if os.path.exists(path):
            raw = read_csv_tolerant(path, usecols=['id', 'code'])
            codes.append(raw.rename(columns={'id': 'element'}).assign(season=season))
    lookup = pd.concat(codes, ignore_index=True).drop_duplicates(['season', 'element'])
    df = df.drop(columns=[c for c in ('player_id',) if c in df.columns])
    df = df.merge(lookup.rename(columns={'code': 'player_id'}),
                  on=['season', 'element'], how='left')

    keys = df['name'].map(_name_key)
    known = pd.DataFrame({'key': keys, 'player_id': df['player_id']}).dropna()
    per_key = known.drop_duplicates().groupby('key')['player_id']
    unique = per_key.first()[per_key.nunique() == 1]
    missing = df['player_id'].isna()
    df.loc[missing, 'player_id'] = keys[missing].map(unique)
    # A borrowed code must not already belong to another element that season.
    owners = df.loc[~missing].groupby(['season', 'player_id'])['element'].first()
    borrowed = df.index[missing & df['player_id'].notna()]
    owner = pd.Series([owners.get((s, c)) for s, c in
                       zip(df.loc[borrowed, 'season'], df.loc[borrowed, 'player_id'])],
                      index=borrowed)
    taken = owner.notna() & (owner != df.loc[borrowed, 'element'])
    df.loc[taken[taken].index, 'player_id'] = np.nan
    by_name = int(missing.sum() - df['player_id'].isna().sum())

    # Never linked to anyone else: a negative id unique to the season-element.
    still = df['player_id'].isna()
    season_rank = {s: i for i, s in enumerate(sorted(df['season'].unique()))}
    df.loc[still, 'player_id'] = -(df.loc[still, 'season'].map(season_rank) * 100_000
                                   + df.loc[still, 'element'])
    df['player_id'] = df['player_id'].astype('int64')
    print(f"\n--- player_id: FPL code on {int((~missing).sum()):,} rows, "
          f"by name on {by_name:,}, season-local on {int(still.sum()):,} ---")
    clash = df.groupby(['season', 'player_id'])['element'].nunique()
    assert (clash == 1).all(), f"player_id shared by two elements: {clash[clash > 1].head()}"
    return df


def build_final(raw: pd.DataFrame, old_final: str) -> pd.DataFrame:
    print("\n" + "=" * 78)
    print("STAGE 2  carry over defensive stats and re-apply the point rules")
    print("=" * 78)

    lookup = defensive_lookup(old_final)

    # The index must be a clean RangeIndex before anything below runs.
    #
    # add_game_number sorts the frame without resetting, so raw arrives with a
    # scrambled index, while df.merge() returns a fresh RangeIndex. Mixing the
    # two means `df.loc[mask, col] = values` aligns on index labels and writes
    # into the wrong rows -- silently, since the shapes all still match. It
    # corrupted both the coverage flag (45% of 2024-25 GW22-38 marked as having
    # FBref data that does not exist for them) and the defensive values, which
    # feed the +2 defensive-contribution bonus and so moved total_points itself.
    df = raw.reset_index(drop=True)

    # One row per player per match. 2019-20 keeps a 0-minute GW29 row for
    # Man City v Arsenal, postponed by Covid and played in GW39 under the same
    # fixture id, so every squad member looked like he missed a match that was
    # never played; 2025-26 repeats one row outright. Keep the real kickoff.
    kickoff = pd.to_datetime(df['kickoff_time'], errors='coerce', utc=True)
    order = kickoff.sort_values(kind='stable').index
    repeated = df.loc[order].duplicated(subset=JOIN_KEYS, keep='last')
    if repeated.any():
        print(f"  dropping {int(repeated.sum())} repeated (season, element, fixture) rows")
        df = df.drop(index=repeated[repeated].index).reset_index(drop=True)

    if lookup is not None:
        # The FBref merge only ever applied to MERGED_SEASONS. Every other
        # season carries defensive stats natively: 2016-17..2018-19 from FPL's
        # own feed, and 2025-26 onwards from the defensive-contribution stats
        # FPL introduced with the new scoring rules.
        #
        # Overwriting all of them from the lookup destroys that. It is not
        # hypothetical: 2025-26 GW10-38 is absent from the old file, so those
        # rows would be zero-filled even though merged_gw.csv carries real
        # values for them (recoveries are non-zero on 31.7% of GW10+ rows).
        # That is 24,000 rows of a test season silently blanked.
        needs_fbref = df['season'].isin(MERGED_SEASONS)
        print(f"  FBref join applies to {int(needs_fbref.sum()):,} rows "
              f"({', '.join(MERGED_SEASONS)})")
        print(f"  native defensive stats kept for {int((~needs_fbref).sum()):,} rows")

        native = df.loc[~needs_fbref, DEFENSIVE_COLS].copy()
        df = df.drop(columns=[c for c in DEFENSIVE_COLS if c in df.columns])
        before = len(df)
        # indicator gives an unambiguous answer to "did this row match?".
        # Deriving it from notna() over the joined columns cannot tell a match
        # apart from a column that merely holds a value, and got it wrong.
        df = df.merge(lookup, on=JOIN_KEYS, how='left', indicator='_join')
        assert len(df) == before, f"join changed row count: {before} -> {len(df)}"
        assert df.index.equals(pd.RangeIndex(len(df))), 'merge did not return a RangeIndex'

        if 'has_fbref_defensive' in df.columns:
            # Carried over from a previous run of this script.
            df['has_fbref_defensive'] = df['has_fbref_defensive'].fillna(0).astype(int)
        else:
            df['has_fbref_defensive'] = (df['_join'] == 'both').astype(int)
        df = df.drop(columns='_join')

        # Put the native values back and mark them as real data. needs_fbref
        # was built from the pre-merge frame, so it is realigned first.
        needs_fbref = needs_fbref.reset_index(drop=True)
        native = native.reset_index(drop=True)
        keep_native = df.index[~needs_fbref]
        for col in DEFENSIVE_COLS:
            df.loc[keep_native, col] = native[col].to_numpy()
        df.loc[keep_native, 'has_fbref_defensive'] = 1

        for col in DEFENSIVE_COLS:
            df[col] = df[col].fillna(0)
    else:
        for col in DEFENSIVE_COLS:
            if col not in df.columns:
                df[col] = 0
        df['has_fbref_defensive'] = 0

    df['defensive_source'] = np.where(df['season'].isin(MERGED_SEASONS), 'fbref', 'fpl')
    df.loc[df['has_fbref_defensive'] == 0, 'defensive_source'] = 'none'
    df = overlay_fotmob_defensive(df)

    # Nobody makes a tackle without playing. The FBref merge gave 1,600-2,000
    # rows a season defensive actions on 0 minutes, and 1,054 of those were
    # then awarded the +2 defensive-contribution bonus they could never earn.
    idle = df['minutes'].fillna(0) <= 0
    stray = idle & (df[DEFENSIVE_COLS].fillna(0).sum(axis=1) > 0)
    print(f"  clearing defensive stats on {int(stray.sum()):,} rows with no minutes")
    df.loc[idle, DEFENSIVE_COLS] = 0
    # A player who did not play is known to have made none, so those zeros
    # are observations whatever source the rest of his season came from.
    # One label for every such row outside the native FPL seasons, so the
    # source never differs between a played and an unplayed row of a season
    # except through minutes themselves.
    df.loc[idle & (df['defensive_source'] != 'fpl'), 'defensive_source'] = 'no_minutes'
    # has_fbref_defensive keeps its name for the notebook's sake; it means
    # "these defensive columns are observed", whichever source they came from.
    df['has_fbref_defensive'] = (df['defensive_source'] != 'none').astype(int)
    print("  defensive source by season:")
    print(pd.crosstab(df['season'], df['defensive_source']).to_string())

    print(f"\n  rows with carried-over defensive stats: "
          f"{int(df.has_fbref_defensive.sum()):,} / {len(df):,}")
    uncovered = df[df.has_fbref_defensive == 0]
    if len(uncovered):
        by_season = uncovered.groupby('season').size()
        print("  rows without (flagged has_fbref_defensive=0):")
        for season, n in by_season.items():
            gws = uncovered[uncovered.season == season]['GW']
            print(f"    {season}: {n:,} rows, GW {int(gws.min())}-{int(gws.max())}")

    # Notebook step 5, applied to the same seasons the notebook applies it to.
    mask = df['season'].isin(MERGED_SEASONS)
    print(f"\n  recalculating defensive_contribution for {int(mask.sum()):,} rows...")
    df.loc[mask, 'defensive_contribution'] = (
        df.loc[mask].apply(calculate_defensive_contribution_row, axis=1)
    )
    print("  applying the defensive-contribution point bonus...")
    df.loc[mask, 'total_points'] = df.loc[mask].apply(calculate_modified_points, axis=1)

    return df


def report(df: pd.DataFrame, allow_empty_columns: bool = False) -> None:
    print("\n" + "=" * 78)
    print("RESULT")
    print("=" * 78)
    summary = df.groupby('season').agg(
        rows=('total_points', 'size'),
        max_gw=('GW', 'max'),
        players=('name', 'nunique'),
        mean_points=('total_points', 'mean'),
        pct_with_defensive=('has_fbref_defensive', 'mean'),
    )
    summary['mean_points'] = summary['mean_points'].round(3)
    summary['pct_with_defensive'] = (100 * summary['pct_with_defensive']).round(1)
    print(summary.to_string())
    print(f"\ntotal: {len(df):,} rows x {df.shape[1]} columns")

    # The feature stage sorts and filters on game_number; a silent absence
    # here surfaces much later as a confusing KeyError deep inside a cell.
    required = ['season', 'GW', 'game_number', 'position', 'name', 'player_id',
                'element', 'fixture', 'total_points', 'kickoff_time']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"output is missing required column(s): {missing}")
    print("column check: everything the feature stage needs is present")
    check_season_columns(df, allow_empty_columns)


# Columns that are genuinely all-zero for long stretches -- nobody is sent off
# most weeks -- so an empty column here says nothing about the source.
ALWAYS_SPARSE = {
    'own_goals', 'penalties_missed', 'penalties_saved', 'red_cards',
    'has_fbref_defensive', 'has_xg',
}


def check_season_columns(df: pd.DataFrame, allow_empty_columns: bool = False) -> None:
    """Fail when a season is entirely empty in a column other seasons fill.

    A source whose column names do not match gets zero-filled a few lines up,
    by design, so that one missing field cannot stop a build. The cost is that
    a source which names half its columns differently produces a season of
    zeroes and no error at all -- which is exactly what the olbauday switch
    did. Position, the ICT components and every defensive action came through
    as zero for the whole of 2026-27, and the first sign of it was a model
    recommending goalkeepers as captain.

    Comparing each season against the rest turns that into a failure at the
    point the data is built, where it is cheap to diagnose.
    """
    seasons = sorted(df['season'].dropna().unique())
    if len(seasons) < 2:
        return

    numeric = [c for c in df.columns
               if c not in ALWAYS_SPARSE
               and pd.api.types.is_numeric_dtype(df[c])]
    filled = df.groupby('season')[numeric].apply(
        lambda block: (block.fillna(0) != 0).mean()
    )
    # A column worth checking is one that other seasons do populate.
    elsewhere = filled.drop(index=seasons[-1]).max()
    suspect = [c for c in numeric
               if filled.loc[seasons[-1], c] == 0 and elsewhere[c] > 0.05]

    # position and team are strings, so they miss the numeric sweep above, and
    # they are the two that matter most: every model is trained per position.
    for col in ('position', 'team'):
        if col in df.columns:
            latest = df.loc[df['season'] == seasons[-1], col].astype(str)
            if latest.isin({'0', '0.0', '', 'nan', 'None'}).all():
                suspect.append(col)

    if not suspect:
        print(f"content check: {seasons[-1]} has data in every column other "
              f"seasons populate")
        return

    raise SystemExit(
        f"{seasons[-1]} is entirely empty in {len(suspect)} column(s) that "
        f"earlier seasons populate:\n"
        f"  {', '.join(sorted(suspect))}\n\n"
        f"These were filled with zero rather than fetched, which almost always "
        f"means the\nsource's column names do not match the ones the mapping "
        f"in scripts/fetch_data.py\nlooks for. Every lag and rolling mean built "
        f"on top of them will also be zero,\nso the models will score this "
        f"season on features that are blank rather than bad.\n\n"
        f"Fix the mapping and re-fetch with --force. To build anyway, pass "
        f"--allow-empty-columns."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='write the CSVs (default: dry run)')
    ap.add_argument('--skip-raw', action='store_true',
                    help=f'reuse an existing {RAW_OUT} instead of re-merging the seasons')
    ap.add_argument('--old-final', default=FINAL_OUT,
                    help='file to lift the defensive columns out of')
    ap.add_argument('--allow-empty-columns', action='store_true',
                    help='build even when the latest season is blank in columns '
                         'other seasons populate')
    ap.add_argument('--allow-missing-defensive', action='store_true',
                    help='build even with no defensive stats to carry over')
    args = ap.parse_args()

    # Preserve the original before this run overwrites it, since it is the only
    # source of the FBref defensive columns.
    #
    # This copies rather than moves. Moving meant a failure part-way through
    # left no all_seasons_data_final.csv at all, and the next attempt then
    # found nothing to look up and silently produced a dataset with every row
    # flagged has_fbref_defensive=0 -- a much worse outcome than the crash.
    # .prev, once written, is never overwritten: it is the pristine original.
    old_final_snapshot = args.old_final
    if args.write and args.old_final == FINAL_OUT:
        snapshot = FINAL_OUT + '.prev'
        if os.path.exists(snapshot):
            print(f"using existing snapshot {snapshot}")
            old_final_snapshot = snapshot
        elif os.path.exists(FINAL_OUT):
            print(f"snapshotting {FINAL_OUT} -> {snapshot}")
            shutil.copy2(FINAL_OUT, snapshot)
            old_final_snapshot = snapshot

    if not os.path.exists(old_final_snapshot):
        print(f"\n{'!' * 70}")
        print(f"WARNING: {old_final_snapshot} does not exist.")
        print("Without it there are no FBref defensive stats to carry over, and")
        print("every row will be flagged has_fbref_defensive=0. That is almost")
        print("certainly not what you want -- restore the file and re-run.")
        print(f"{'!' * 70}")
        if not args.allow_missing_defensive:
            raise SystemExit(
                "refusing to build a dataset with no defensive stats; "
                "pass --allow-missing-defensive to override"
            )

    if args.skip_raw:
        print(f"reading existing {RAW_OUT}")
        raw = read_csv_tolerant(RAW_OUT)
    else:
        raw = build_raw()
        if args.write:
            raw.to_csv(RAW_OUT, index=False, encoding='utf-8')
            print(f"wrote {RAW_OUT}")

    final = build_final(raw, old_final_snapshot)
    final = add_expected_stats(final)
    final = derive_fixture_teams(final)
    final = add_player_ids(final)
    # 2021-22 labels 101 keeper rows 'GKP'; every model filters on 'GK'.
    final['position'] = final['position'].replace({'GKP': 'GK'})
    report(final, allow_empty_columns=args.allow_empty_columns)

    if args.write:
        final.to_csv(FINAL_OUT, index=False, encoding='utf-8')
        print(f"\nwrote {FINAL_OUT}")
    else:
        print("\n(dry run -- pass --write to save)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
