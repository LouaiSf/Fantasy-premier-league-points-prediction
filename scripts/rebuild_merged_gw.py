"""Rebuild data/<season>/gws/merged_gw.csv from the per-gameweek gw*.csv files.

Why this exists
---------------
data/2024-25/gws/merged_gw.csv was concatenated without aligning columns by
name. FPL added seven `mng_*` (Assistant Manager) columns in GW22 of 2024-25,
so rows from GW22 onward carry 49 fields while GW1-21 rows carry 42. Every
reader in this project opens merged_gw.csv with `on_bad_lines='skip'`, which
silently dropped all 13,427 rows from GW22-38 -- 49% of the season.

The per-gameweek gw*.csv files are intact, so the merged file is rebuilt from
them with a name-aligned concat. The `mng_*` columns are dropped by default:
no other season has them, nothing downstream reads them, and dropping them
makes the output a drop-in replacement with the exact schema GW1-21 already
had.

The same GW22 change introduced 322 rows with position "AM" (Assistant
Manager). That is a manager entity, not a player: it scores by a different
rule set, exists in no other season, and would distort the team-level rolling
aggregates built downstream. Those rows are dropped by default too.

Usage
-----
    python scripts/rebuild_merged_gw.py                 # audit every season
    python scripts/rebuild_merged_gw.py --season 2024-25 --write
    python scripts/rebuild_merged_gw.py --all --write   # rebuild everything
"""

from __future__ import annotations

import argparse
import csv
import collections
import glob
import os
import re
import shutil
import sys

import pandas as pd

DATA_DIR = "data"
GW_RE = re.compile(r"gw(\d+)\.csv$", re.IGNORECASE)

# The four positions the models are built for. "AM" (Assistant Manager) shows
# up only in 2024-25 GW22+ and is not a player.
PLAYER_POSITIONS = {"GK", "DEF", "MID", "FWD"}


def gw_files(season: str) -> list[tuple[int, str]]:
    """Return [(gameweek, path), ...] sorted by gameweek."""
    out = []
    for path in glob.glob(os.path.join(DATA_DIR, season, "gws", "gw*.csv")):
        m = GW_RE.search(os.path.basename(path))
        if m:
            out.append((int(m.group(1)), path))
    return sorted(out)


def read_csv_tolerant(path: str, **kwargs) -> pd.DataFrame:
    """Read a vaastav CSV, trying utf-8 first then latin-1.

    Seasons in this dump are not consistently encoded: 2024-25 and 2025-26 are
    utf-8, several older seasons are latin-1.

    Deliberately does NOT default to on_bad_lines='skip' -- silently dropping
    rows is the bug this script exists to undo.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"could not decode {path} as utf-8 or latin-1")


def field_widths(path: str) -> dict[int, int]:
    """Count how many rows have each field count. >1 key means a broken file."""
    counts: collections.Counter = collections.Counter()
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.reader(fh):
            counts[len(row)] += 1
    return dict(sorted(counts.items()))


def audit(season: str) -> dict:
    parts = gw_files(season)
    merged_path = os.path.join(DATA_DIR, season, "gws", "merged_gw.csv")

    expected_rows = 0
    for _, path in parts:
        with open(path, encoding="utf-8", errors="replace") as fh:
            expected_rows += sum(1 for _ in fh) - 1

    present = {gw for gw, _ in parts}
    missing = sorted(set(range(1, max(present) + 1)) - present) if present else []

    info = {
        "season": season,
        "gw_files": len(parts),
        "missing_gw_files": missing,
        "expected_rows": expected_rows,
        "merged_exists": os.path.exists(merged_path),
        "widths": field_widths(merged_path) if os.path.exists(merged_path) else {},
    }

    if info["merged_exists"]:
        # on_bad_lines="skip" here reproduces exactly what the notebooks do,
        # so "readable_rows" is what the pipeline actually sees today.
        df = read_csv_tolerant(merged_path, on_bad_lines="skip")
        info["readable_rows"] = len(df)
        info["lost_rows"] = expected_rows - len(df)
        info["gw_range"] = (
            f"{int(df['GW'].min())}-{int(df['GW'].max())}" if "GW" in df else "no GW col"
        )
    return info


def rebuild(
    season: str,
    keep_mng: bool = False,
    keep_non_players: bool = False,
    write: bool = False,
) -> pd.DataFrame:
    parts = gw_files(season)
    if not parts:
        raise SystemExit(f"no gw*.csv files found for season {season}")

    frames = []
    for gw, path in parts:
        df = read_csv_tolerant(path)
        df["GW"] = gw
        frames.append(df)

    # Name-aligned concat. This is the actual fix: pandas unions the columns by
    # name, so the seven mng_* columns that appear from GW22 line up correctly
    # instead of shifting every field to its right.
    merged = pd.concat(frames, ignore_index=True, sort=False)

    if not keep_mng:
        mng_cols = [c for c in merged.columns if c.startswith("mng_")]
        if mng_cols:
            merged = merged.drop(columns=mng_cols)
            print(f"  dropped {len(mng_cols)} mng_* columns: {mng_cols}")

    dropped_rows = 0
    if not keep_non_players and "position" in merged.columns:
        non_player = ~merged["position"].isin(PLAYER_POSITIONS)
        if non_player.any():
            counts = merged.loc[non_player, "position"].value_counts().to_dict()
            dropped_rows = int(non_player.sum())
            merged = merged[~non_player].reset_index(drop=True)
            print(f"  dropped {dropped_rows} non-player rows: {counts}")

    # Put GW last, matching the layout the existing readers expect.
    cols = [c for c in merged.columns if c != "GW"] + ["GW"]
    merged = merged[cols]

    expected = sum(len(f) for f in frames) - dropped_rows
    assert len(merged) == expected, f"row count changed: {len(merged)} != {expected}"

    out_path = os.path.join(DATA_DIR, season, "gws", "merged_gw.csv")
    print(f"  rebuilt: {len(merged)} rows x {len(merged.columns)} cols, "
          f"GW {int(merged['GW'].min())}-{int(merged['GW'].max())}")

    if write:
        if os.path.exists(out_path):
            backup = out_path + ".broken.bak"
            if not os.path.exists(backup):
                shutil.copy2(out_path, backup)
                print(f"  backed up original -> {backup}")
        merged.to_csv(out_path, index=False, encoding="utf-8")
        print(f"  wrote {out_path}")

        widths = field_widths(out_path)
        assert len(widths) == 1, f"output still has mixed widths: {widths}"
        print(f"  verified: uniform field width {widths}")

    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", help="e.g. 2024-25")
    ap.add_argument("--all", action="store_true", help="every season under data/")
    ap.add_argument("--write", action="store_true", help="write the file (default: dry run)")
    ap.add_argument("--keep-mng", action="store_true", help="keep the mng_* columns")
    ap.add_argument("--keep-non-players", action="store_true",
                    help="keep rows whose position is not GK/DEF/MID/FWD (e.g. AM)")
    args = ap.parse_args()

    seasons = sorted(
        d for d in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, d, "gws"))
    )

    if args.season:
        targets = [args.season]
    elif args.all:
        targets = seasons
    else:
        print("AUDIT (no --season/--all given, nothing will be written)\n")
        broken = []
        for s in seasons:
            info = audit(s)
            flag = ""
            if len(info["widths"]) > 1:
                flag = f"  <-- BROKEN, {info['lost_rows']} rows unreadable"
                broken.append(s)
            print(f"{info['season']}: {info['gw_files']} gw files, "
                  f"{info['expected_rows']} rows expected, "
                  f"{info.get('readable_rows', '?')} readable, "
                  f"GW {info.get('gw_range', '?')}, widths {info['widths']}{flag}")
            if info["missing_gw_files"]:
                print(f"    note: no gw file for gameweek(s) {info['missing_gw_files']}")
        print(f"\n{len(broken)} season(s) need rebuilding: {broken or 'none'}")
        return 0

    for s in targets:
        print(f"\n{s}:")
        rebuild(s, keep_mng=args.keep_mng,
                keep_non_players=args.keep_non_players, write=args.write)
    if not args.write:
        print("\n(dry run -- pass --write to actually replace merged_gw.csv)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
