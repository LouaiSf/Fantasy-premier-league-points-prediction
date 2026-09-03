"""Rebuild all_seasons_data.csv and all_seasons_data_final.csv.

Why this is not just "re-run final.ipynb"
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
import shutil
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbrun import run_range  # noqa: E402

NOTEBOOK = 'final.ipynb'
RAW_OUT = 'all_seasons_data.csv'
FINAL_OUT = 'all_seasons_data_final.csv'

# Seasons whose defensive stats came from the FBref merge, and whose points
# therefore get the defensive-contribution adjustment in the notebook's step 5.
# 2016-17..2018-19 are adjusted earlier (cell 25) and carry native FPL
# defensive columns; 2025-26 ships defensive contribution from the FPL API.
MERGED_SEASONS = ['2019-20', '2020-21', '2021-22', '2022-23', '2023-24', '2024-25']

DEFENSIVE_COLS = ['tackles', 'recoveries', 'clearances_blocks_interceptions']
JOIN_KEYS = ['season', 'element', 'fixture']


# The two functions below are copied verbatim from final.ipynb step 5 so that
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


def build_raw() -> pd.DataFrame:
    """Run the notebook's own season-merging cells (3..34), then cell 40."""
    print("=" * 78)
    print("STAGE 1  merge every season  (final.ipynb cells 3..34)")
    print("=" * 78)
    ns = run_range(
        NOTEBOOK,
        first="data_merged_gw_2016_17 = pd.read_csv",
        last="# save all seasons data to a csv file",
        namespace={'pd': pd, 'np': np},
    )
    df = ns['all_seasons_data']
    print(f"\nmerged seasons: {df.shape[0]:,} rows x {df.shape[1]} cols")
    return add_game_number(df)


def add_game_number(df: pd.DataFrame) -> pd.DataFrame:
    """Run the notebook's own game_number cell (cell 40).

    That cell sits inside the FBref half of the notebook, which cannot run
    here, but it only needs all_seasons_df and kickoff_time. Without it the
    feature stage dies with KeyError: 'game_number'.
    """
    print("\n--- assigning game_number (final.ipynb cell 40) ---")
    anchor = "# Assign game_number using kickoff_time for ALL seasons"
    ns = run_range(
        NOTEBOOK, first=anchor, last=anchor,
        namespace={'pd': pd, 'np': np, 'all_seasons_df': df},
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

    This pipeline writes its CSVs with encoding='latin-1' (the notebook's
    choice, kept for compatibility), but the vaastav source files are a mix of
    utf-8 and latin-1. Letting pandas default to utf-8 means a file this very
    script wrote fails to read back, on the first accented player name.
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


def build_final(raw: pd.DataFrame, old_final: str) -> pd.DataFrame:
    print("\n" + "=" * 78)
    print("STAGE 2  carry over defensive stats and re-apply the point rules")
    print("=" * 78)

    lookup = defensive_lookup(old_final)
    df = raw.copy()

    if lookup is not None:
        # Drop the placeholder defensive columns the merge cells created, so
        # the joined values are the only ones present.
        df = df.drop(columns=[c for c in DEFENSIVE_COLS if c in df.columns])
        before = len(df)
        df = df.merge(lookup, on=JOIN_KEYS, how='left')
        assert len(df) == before, f"join changed row count: {before} -> {len(df)}"

        if 'has_fbref_defensive' in df.columns:
            # Carried over from a previous run of this script.
            df['has_fbref_defensive'] = df['has_fbref_defensive'].fillna(0).astype(int)
        else:
            matched = df[DEFENSIVE_COLS].notna().any(axis=1)
            df['has_fbref_defensive'] = matched.astype(int)
        for col in DEFENSIVE_COLS:
            df[col] = df[col].fillna(0)
    else:
        for col in DEFENSIVE_COLS:
            if col not in df.columns:
                df[col] = 0
        df['has_fbref_defensive'] = 0

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


def report(df: pd.DataFrame) -> None:
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
    required = ['season', 'GW', 'game_number', 'position', 'name',
                'element', 'fixture', 'total_points', 'kickoff_time']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"output is missing required column(s): {missing}")
    print("column check: everything the feature stage needs is present")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='write the CSVs (default: dry run)')
    ap.add_argument('--skip-raw', action='store_true',
                    help=f'reuse an existing {RAW_OUT} instead of re-merging the seasons')
    ap.add_argument('--old-final', default=FINAL_OUT,
                    help='file to lift the defensive columns out of')
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
            raw.to_csv(RAW_OUT, index=False, encoding='latin-1')
            print(f"wrote {RAW_OUT}")

    final = build_final(raw, old_final_snapshot)
    report(final)

    if args.write:
        final.to_csv(FINAL_OUT, index=False, encoding='latin-1')
        print(f"\nwrote {FINAL_OUT}")
    else:
        print("\n(dry run -- pass --write to save)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
