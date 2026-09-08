"""Fetch season data from the vaastav/Fantasy-Premier-League mirror.

The checked-in 2025-26 snapshot stops at GW9 and is missing GW7 entirely;
upstream now has all 38. 2026-27 is not in this checkout at all.

What it downloads, per season:

    gws/merged_gw.csv     the one file the pipeline actually reads
    gws/gw<N>.csv         per-gameweek files, so scripts/rebuild_merged_gw.py
                          can still audit merged_gw.csv against its parts
    teams.csv             opponent id -> name for seasons after the master list
    players_raw.csv       element_type -> position
    fixtures.csv          used by the FDR features in advanced_fpl_models.ipynb

Existing files are left alone unless --force, so an interrupted run resumes
where it stopped rather than starting over.

Every download is verified as parseable CSV before it replaces anything, and
the summary at the end reports rows per gameweek so a truncated upstream file
is visible immediately rather than three stages later.

Usage
-----
    python scripts/fetch_data.py --season 2025-26 --season 2026-27
    python scripts/fetch_data.py --season 2026-27 --force
    python scripts/fetch_data.py --list 2026-27      # what exists upstream
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

RAW = 'https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data'
API = 'https://api.github.com/repos/vaastav/Fantasy-Premier-League/contents/data'
ROOT_FILES = ('teams.csv', 'players_raw.csv', 'fixtures.csv',
              'cleaned_players.csv', 'player_idlist.csv')
HEADERS = {'User-Agent': 'Mozilla/5.0 (fpl-pipeline)'}


def http_get(url: str, tries: int = 4, timeout: int = 45) -> bytes:
    """GET with backoff. GitHub rate-limits and times out under load."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise
            last = exc
        except Exception as exc:
            last = exc
        if attempt < tries - 1:
            wait = 2 ** attempt
            print(f"      retry {attempt + 1}/{tries - 1} in {wait}s ({type(last).__name__})")
            time.sleep(wait)
    raise RuntimeError(f"failed after {tries} tries: {url} ({last})")


def list_upstream(season: str) -> dict:
    """What the mirror has for this season."""
    out = {'gws': [], 'root': [], 'has_merged': False}
    try:
        entries = json.loads(http_get(f"{API}/{season}/gws"))
        names = [e['name'] for e in entries]
        out['gws'] = sorted(int(n[2:-4]) for n in names
                            if n.startswith('gw') and n.endswith('.csv') and n[2:-4].isdigit())
        out['has_merged'] = 'merged_gw.csv' in names
    except Exception as exc:
        print(f"  could not list {season}/gws: {exc}")
    try:
        entries = json.loads(http_get(f"{API}/{season}"))
        out['root'] = [e['name'] for e in entries if e['name'].endswith('.csv')]
    except Exception as exc:
        print(f"  could not list {season}: {exc}")
    return out


def save_verified(data: bytes, path: str) -> int:
    """Write only if it parses as CSV. Returns row count."""
    for encoding in ('utf-8', 'latin-1'):
        try:
            df = pd.read_csv(io.BytesIO(data), encoding=encoding, low_memory=False)
            break
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            raise RuntimeError(f"downloaded bytes are not valid CSV: {exc}")
    else:
        raise RuntimeError("could not decode downloaded CSV")

    if df.empty:
        raise RuntimeError("downloaded CSV has no rows")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with open(tmp, 'wb') as fh:
        fh.write(data)
    os.replace(tmp, path)
    return len(df)


def fetch_season(season: str, force: bool, gw_files: bool = True) -> dict:
    print(f"\n{'=' * 72}\n{season}\n{'=' * 72}")
    upstream = list_upstream(season)
    if not upstream['gws'] and not upstream['root']:
        print("  nothing found upstream -- season may not exist yet")
        return {'season': season, 'downloaded': 0, 'skipped': 0, 'gws': []}

    print(f"  upstream: {len(upstream['gws'])} gw files "
          f"(GW {min(upstream['gws'])}-{max(upstream['gws'])})"
          if upstream['gws'] else "  upstream: no gw files")

    downloaded = skipped = 0
    got = []

    targets = [(f"{season}/gws/merged_gw.csv", os.path.join('data', season, 'gws', 'merged_gw.csv'))]
    if gw_files:
        targets += [(f"{season}/gws/gw{n}.csv", os.path.join('data', season, 'gws', f'gw{n}.csv'))
                    for n in upstream['gws']]
    targets += [(f"{season}/{f}", os.path.join('data', season, f))
                for f in ROOT_FILES if not upstream['root'] or f in upstream['root']]

    for remote, local in targets:
        if os.path.exists(local) and not force:
            skipped += 1
            continue
        try:
            data = http_get(f"{RAW}/{remote}")
            rows = save_verified(data, local)
            downloaded += 1
            got.append((os.path.basename(local), rows))
            print(f"    {os.path.basename(local):<20} {rows:>7,} rows")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"    {os.path.basename(local):<20} not published upstream")
            else:
                print(f"    {os.path.basename(local):<20} HTTP {exc.code}")
        except Exception as exc:
            print(f"    {os.path.basename(local):<20} FAILED: {exc}")

    print(f"\n  downloaded {downloaded}, left alone {skipped}"
          f"{' (use --force to refresh)' if skipped else ''}")
    return {'season': season, 'downloaded': downloaded, 'skipped': skipped, 'gws': got}


def report(season: str) -> None:
    """What the pipeline will actually see for this season."""
    path = os.path.join('data', season, 'gws', 'merged_gw.csv')
    if not os.path.exists(path):
        print(f"  {season}: no merged_gw.csv")
        return
    for encoding in ('utf-8', 'latin-1'):
        try:
            df = pd.read_csv(path, encoding=encoding, low_memory=False)
            break
        except UnicodeDecodeError:
            continue
    gw_col = 'GW' if 'GW' in df.columns else 'round'
    if gw_col not in df.columns:
        print(f"  {season}: {len(df):,} rows (no GW column)")
        return
    gws = sorted(df[gw_col].dropna().unique())
    gaps = [g for g in range(int(min(gws)), int(max(gws)) + 1) if g not in gws]
    print(f"  {season}: {len(df):>7,} rows | GW {int(min(gws))}-{int(max(gws))} "
          f"({len(gws)} present){' | GAPS: ' + str(gaps) if gaps else ''}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--season', action='append', dest='seasons',
                    help='season to fetch, repeatable (default: 2025-26 and 2026-27)')
    ap.add_argument('--force', action='store_true', help='re-download files that already exist')
    ap.add_argument('--no-gw-files', action='store_true',
                    help='fetch only merged_gw.csv, not the per-gameweek files')
    ap.add_argument('--list', dest='list_season',
                    help='just report what exists upstream for this season')
    args = ap.parse_args()

    if args.list_season:
        info = list_upstream(args.list_season)
        print(json.dumps(info, indent=2))
        return 0

    seasons = args.seasons or ['2025-26', '2026-27']
    for season in seasons:
        fetch_season(season, force=args.force, gw_files=not args.no_gw_files)

    print(f"\n{'=' * 72}\nWHAT THE PIPELINE WILL SEE\n{'=' * 72}")
    for season in seasons:
        report(season)
    print("\nNext: python scripts/build_dataset.py --write")
    return 0


if __name__ == '__main__':
    sys.exit(main())
