"""Fetch season data from vaastav/Fantasy-Premier-League or olbauday/FPL-Core-Insights.

vaastav (default source)
------------------------
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

olbauday source (--source olbauday)
------------------------------------
olbauday/FPL-Core-Insights updates twice daily and tracks the current season
in real time. Its file layout differs from vaastav; this script translates it
to the vaastav format our pipeline expects.

    files fetched from olbauday:
        data/{SEASON}/players.csv            player codes and positions
        data/{SEASON}/playerstats.csv        current cumulative player stats
        data/{SEASON}/teams.csv              team list
        data/{SEASON}/By Gameweek/GW{N}/player_gameweek_stats.csv
        data/{SEASON}/By Gameweek/GW{N}/fixtures.csv

    files written locally (vaastav format):
        data/{season}/players_raw.csv
        data/{season}/teams.csv
        data/{season}/fixtures.csv
        data/{season}/gws/gw{N}.csv
        data/{season}/gws/merged_gw.csv

Usage
-----
    python scripts/fetch_data.py --season 2025-26 --season 2026-27
    python scripts/fetch_data.py --season 2026-27 --force
    python scripts/fetch_data.py --list 2026-27      # what exists upstream
    python scripts/fetch_data.py --season 2026-27 --source olbauday --force
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


OLBAUDAY_RAW = ('https://raw.githubusercontent.com/olbauday/'
                'FPL-Core-Insights/main/data')

# Maps olbauday position strings → FPL element_type integers
_POS_MAP = {'Goalkeeper': 1, 'GK': 1, 'Defender': 2, 'DEF': 2,
            'Midfielder': 3, 'MID': 3, 'Forward': 4, 'FWD': 4}


def _local_to_olbauday_season(local: str) -> str:
    """'2026-27' → '2026-2027'."""
    y1, y2s = local.split('-')
    return f"{y1}-{y1[:2]}{y2s}"


def _ob_url(ob_season: str, path: str) -> str:
    return f"{OLBAUDAY_RAW}/{ob_season}/{path.replace(' ', '%20')}"


def _col(df: pd.DataFrame, col: str, default=0) -> pd.Series:
    """Return df[col] if it exists, else a Series of *default* with matching index."""
    return df[col] if col in df.columns else pd.Series(default, index=df.index)


def fetch_season_olbauday(local_season: str, force: bool) -> dict:
    """Download from olbauday/FPL-Core-Insights and write vaastav-format files."""
    print(f"\n{'=' * 72}\n{local_season} (source: olbauday)\n{'=' * 72}")

    ob_season = _local_to_olbauday_season(local_season)
    local_dir = os.path.join('data', local_season)
    os.makedirs(os.path.join(local_dir, 'gws'), exist_ok=True)

    downloaded = skipped = 0

    def fetch_ob(path: str) -> bytes:
        return http_get(_ob_url(ob_season, path))

    def save_df(df: pd.DataFrame, path: str) -> None:
        nonlocal downloaded
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.part'
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
        downloaded += 1
        print(f"    {os.path.basename(path):<30} {len(df):>7,} rows")

    # ------------------------------------------------------------------ teams
    teams_path = os.path.join(local_dir, 'teams.csv')
    if not os.path.exists(teams_path) or force:
        print("  Fetching teams …")
        raw = pd.read_csv(io.BytesIO(fetch_ob('teams.csv')))
        teams_out = pd.DataFrame({
            'id': raw['id'].astype(int),
            'code': raw['code'].astype(int),
            'name': raw['name'],
            'short_name': _col(raw, 'short_name',
                               raw['name'].str[:3].str.upper()),
            'strength': _col(raw, 'strength', 3).fillna(3).astype(int),
        })
        save_df(teams_out, teams_path)
    else:
        teams_out = pd.read_csv(teams_path)
        skipped += 1
        print(f"    teams.csv                        (skipped)")

    team_code_to_id: dict = dict(zip(teams_out['code'], teams_out['id']))
    team_id_to_name: dict = dict(zip(teams_out['id'], teams_out['name']))

    # --------------------------------------------------------------- players
    players_path = os.path.join(local_dir, 'players_raw.csv')
    if not os.path.exists(players_path) or force:
        print("  Fetching players.csv + playerstats.csv …")
        players_df = pd.read_csv(io.BytesIO(fetch_ob('players.csv')))
        stats_df = pd.read_csv(io.BytesIO(fetch_ob('playerstats.csv')),
                               low_memory=False)

        # playerstats.csv has one row per player per GW (cumulative snapshot).
        # Keep only the latest row per player so players_raw.csv has one row.
        if 'gw' in stats_df.columns:
            stats_df = (stats_df
                        .sort_values('gw')
                        .groupby('id', as_index=False)
                        .last())

        # olbauday players.csv: player_code, player_id, first_name,
        #   second_name, web_name, team_code, position
        # olbauday playerstats.csv: id (=player_id), + all the stats
        merged = stats_df.merge(
            players_df[['player_id', 'player_code', 'team_code', 'position']],
            left_on='id', right_on='player_id', how='left',
        )
        merged['element_type'] = (merged['position']
                                  .map(_POS_MAP).fillna(0).astype(int))
        merged['team'] = (merged['team_code']
                          .map(team_code_to_id).fillna(0).astype(int))
        merged.rename(columns={'player_code': 'code'}, inplace=True)

        # Resolve first_name / second_name: stats file has them already,
        # but if missing fall back to players.csv columns.
        if 'first_name' not in merged.columns and 'first_name_x' in merged.columns:
            merged.rename(columns={'first_name_x': 'first_name',
                                   'second_name_x': 'second_name',
                                   'web_name_x': 'web_name'}, inplace=True)

        save_df(merged, players_path)
        players_out = merged
    else:
        players_out = pd.read_csv(players_path, low_memory=False)
        skipped += 1
        print(f"    players_raw.csv                  (skipped)")

    player_id_to_team: dict = dict(zip(players_out['id'],
                                       players_out['team']))

    # --------------------------------------------------------------- fixtures
    fixtures_path = os.path.join(local_dir, 'fixtures.csv')
    if not os.path.exists(fixtures_path) or force:
        print("  Fetching fixtures from GW folders …")
        all_fix: list[pd.DataFrame] = []
        for gw in range(1, 39):
            try:
                data = fetch_ob(f"By Gameweek/GW{gw}/fixtures.csv")
                gw_fix = pd.read_csv(io.BytesIO(data))
                # Keep Premier League fixtures only.
                if 'tournament' in gw_fix.columns:
                    # olbauday uses 'prem' for Premier League fixtures;
                    # the regex catches 'prem', 'premier-league', etc.
                    gw_fix = gw_fix[
                        gw_fix['tournament'].str.match(
                            r'^prem', case=False, na=False)
                    ]
                # Require both team IDs to be present.
                gw_fix = gw_fix[
                    gw_fix['home_team'].notna() & gw_fix['away_team'].notna()
                ]
                if not gw_fix.empty:
                    all_fix.append(gw_fix)
                    print(f"    GW{gw}: {len(gw_fix)} PL fixtures")
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    break
                print(f"    GW{gw}: HTTP {exc.code} — skipped")
            except Exception as exc:
                print(f"    GW{gw}: {exc!r} — skipped")

        if all_fix:
            fix_df = pd.concat(all_fix, ignore_index=True)
            kt = _col(fix_df, 'kickoff_time', '').astype(str)
            # Normalise to RFC-3339 / ISO 8601 with UTC timezone that pandas
            # can parse with %z: append 'Z' when no offset is present.
            kt = kt.apply(
                lambda s: s if (s.endswith('Z') or '+' in s[-6:]) else s + 'Z'
                if s else ''
            )
            # olbauday's home_team / away_team are team CODES (e.g. 3 for
            # Arsenal), not IDs (1 for Arsenal). Convert using team_code_to_id
            # so the fixture lookup keys match what player_id_to_team returns.
            h_codes = fix_df['home_team'].astype(float).astype(int)
            a_codes = fix_df['away_team'].astype(float).astype(int)
            fix_out = pd.DataFrame({
                'id': range(1, len(fix_df) + 1),   # synthetic fixture ID
                'event': fix_df['gameweek'].astype(int),
                'team_h': h_codes.map(team_code_to_id),
                'team_a': a_codes.map(team_code_to_id),
                'kickoff_time': kt,
                'finished': _col(fix_df, 'finished', False),
                'team_h_difficulty': 3,
                'team_a_difficulty': 3,
            })
            # Drop rows where team mapping failed (non-PL teams that slipped
            # through the tournament filter).
            fix_out = fix_out.dropna(subset=['team_h', 'team_a'])
            fix_out[['team_h', 'team_a']] = (
                fix_out[['team_h', 'team_a']].astype(int)
            )
            save_df(fix_out, fixtures_path)
            fixtures_out = fix_out
        else:
            print("    WARNING: no PL fixtures found — fixtures.csv not written")
            fixtures_out = pd.DataFrame()
    else:
        fixtures_out = pd.read_csv(fixtures_path)
        skipped += 1
        print(f"    fixtures.csv                     (skipped)")

    # Build fixture lookup {(gw, team_id): (opponent_id, was_home, kickoff_time, fixture_id)}
    fixture_lookup: dict = {}
    if not fixtures_out.empty:
        for _, row in fixtures_out.iterrows():
            gw_n = int(row['event'])
            h = int(row['team_h'])
            a = int(row['team_a'])
            kt = str(row.get('kickoff_time', '') or '')
            fid = int(row.get('id', 0))
            fixture_lookup[(gw_n, h)] = (a, True, kt, fid)
            fixture_lookup[(gw_n, a)] = (h, False, kt, fid)

    # ---------------------------------------------------------- per-GW stats
    print("  Fetching per-GW player stats …")
    all_gw_frames: list[pd.DataFrame] = []
    available_gws: list[int] = []

    for gw in range(1, 39):
        gw_path = os.path.join(local_dir, 'gws', f'gw{gw}.csv')
        if os.path.exists(gw_path) and not force:
            df = pd.read_csv(gw_path, low_memory=False)
            all_gw_frames.append(df)
            available_gws.append(gw)
            skipped += 1
            continue

        try:
            data = fetch_ob(f"By Gameweek/GW{gw}/player_gameweek_stats.csv")
            src = pd.read_csv(io.BytesIO(data), low_memory=False)

            gw_out = pd.DataFrame({
                'element': src['id'],
                'name': _col(src, 'web_name', ''),
                'GW': gw,
                'total_points': _col(src, 'total_points', 0),
                'minutes': _col(src, 'minutes', 0),
                'goals_scored': _col(src, 'goals_scored', 0),
                'assists': _col(src, 'assists', 0),
                'clean_sheets': _col(src, 'clean_sheets', 0),
                'goals_conceded': _col(src, 'goals_conceded', 0),
                'own_goals': _col(src, 'own_goals', 0),
                'penalties_saved': _col(src, 'penalties_saved', 0),
                'penalties_missed': _col(src, 'penalties_missed', 0),
                'yellow_cards': _col(src, 'yellow_cards', 0),
                'red_cards': _col(src, 'red_cards', 0),
                'saves': _col(src, 'saves', 0),
                'bonus': _col(src, 'bonus', 0),
                'bps': _col(src, 'bps', 0),
                'ict_index': _col(src, 'ict_index', 0),
                'expected_goals': _col(src, 'expected_goals', 0),
                'expected_assists': _col(src, 'expected_assists', 0),
                'expected_goal_involvements':
                    _col(src, 'expected_goal_involvements', 0),
                'expected_goals_conceded':
                    _col(src, 'expected_goals_conceded', 0),
                'starts': _col(src, 'starts', 0),
                'transfers_balance':
                    _col(src, 'transfers_in', 0).astype(float)
                    - _col(src, 'transfers_out', 0).astype(float),
                'selected': _col(src, 'selected_by_percent', 0),
                'value': _col(src, 'now_cost', 0),
            })

            # Derive opponent_team and was_home from the fixture lookup.
            team_ids = gw_out['element'].map(player_id_to_team)

            _none4 = (None, None, None, None)

            def _lookup(tid, idx):
                if pd.isna(tid):
                    return None
                return fixture_lookup.get((gw, int(tid)), _none4)[idx]

            opponent_ids = team_ids.apply(lambda t: _lookup(t, 0))
            gw_out['opponent_team'] = (opponent_ids
                                       .map(team_id_to_name).fillna(''))
            gw_out['was_home'] = team_ids.apply(lambda t: _lookup(t, 1))
            # kickoff_time — needed by build_dataset's game_number assignment.
            gw_out['kickoff_time'] = team_ids.apply(lambda t: _lookup(t, 2))
            # fixture — join key used by add_expected_stats in build_dataset.
            gw_out['fixture'] = team_ids.apply(lambda t: _lookup(t, 3))

            save_df(gw_out, gw_path)
            all_gw_frames.append(gw_out)
            available_gws.append(gw)

        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                break
            print(f"    GW{gw}: HTTP {exc.code} — skipped")
        except Exception as exc:
            print(f"    GW{gw}: {exc!r} — skipped")

    # --------------------------------------------------------- merged_gw.csv
    merged_path = os.path.join(local_dir, 'gws', 'merged_gw.csv')
    if all_gw_frames and (not os.path.exists(merged_path) or force):
        merged_df = pd.concat(all_gw_frames, ignore_index=True)
        save_df(merged_df, merged_path)

    print(f"\n  downloaded {downloaded}, left alone {skipped}"
          f"{' (use --force to refresh)' if skipped else ''}")
    return {
        'season': local_season,
        'downloaded': downloaded,
        'skipped': skipped,
        'gws': available_gws,
    }


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
    ap.add_argument('--force', action='store_true',
                    help='re-download files that already exist')
    ap.add_argument('--no-gw-files', action='store_true',
                    help='fetch only merged_gw.csv, not the per-gameweek files '
                         '(vaastav source only)')
    ap.add_argument('--list', dest='list_season',
                    help='just report what exists upstream for this season '
                         '(vaastav source only)')
    ap.add_argument('--source', choices=['vaastav', 'olbauday'],
                    default='vaastav',
                    help='data source: vaastav (default) or olbauday '
                         '(olbauday/FPL-Core-Insights, updates twice daily)')
    args = ap.parse_args()

    if args.list_season:
        info = list_upstream(args.list_season)
        print(json.dumps(info, indent=2))
        return 0

    seasons = args.seasons or ['2025-26', '2026-27']

    if args.source == 'olbauday':
        for season in seasons:
            fetch_season_olbauday(season, force=args.force)
    else:
        for season in seasons:
            fetch_season(season, force=args.force, gw_files=not args.no_gw_files)

    print(f"\n{'=' * 72}\nWHAT THE PIPELINE WILL SEE\n{'=' * 72}")
    for season in seasons:
        report(season)
    print("\nNext: python scripts/build_dataset.py --write")
    return 0


if __name__ == '__main__':
    sys.exit(main())
