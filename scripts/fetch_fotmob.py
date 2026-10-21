"""Scrape per-player, per-match advanced stats from FotMob match pages.

FPL's own data stops at xG, xA, CBI, tackles and recoveries. FotMob (Opta
derived) also has xGOT, goals prevented, xGOT faced, blocks, interceptions and
clearances as separate numbers, chances created, big chances, touches in the
opposition box, duels and more -- per player, per match, back to 2023-24.
FBref lost its Opta data in January 2026 and Understat has no xGOT or
defensive actions, so FotMob is the source.

Compliance
----------
fotmob.com/robots.txt disallows /api/* for ordinary crawlers and allows normal
pages. Those pages embed their full data in <script id="__NEXT_DATA__">, so
this reads only HTML pages and never calls /api/* or data.fotmob.com. robots.txt
is checked at start, every request carries an honest User-Agent, requests are
at least MIN_INTERVAL_S apart, and finished matches are cached locally and
never fetched twice. Personal, non-commercial use; credit "Match data: FotMob".
Nothing under data/<season>/fotmob/ is committed.

What it writes, per season (data/<season>/fotmob/)
--------------------------------------------------
    raw/match_<id>.json.gz  the slice of each match page this reads (cache)
    player_match.csv        one row per player per match, keyed to FPL
                            (element, gw, fpl_fixture); stats FotMob did not
                            report are blank, never 0
    shots.csv               one row per shot, with xG and xGOT
    player_map.csv          FotMob player id -> FPL element, with how it was matched
    sync.json               when this last ran and how much of it mapped

Each FotMob player is matched to the FPL element in the same fixture and team
by name, then verified on minutes and FPL points (FotMob reports the FPL points
too). data/fotmob_overrides.csv (season,fotmob_player_id,element) wins over the
matcher. If under MIN_MAPPED_MINUTES of FotMob minutes map, the files are still
written but the exit status is 2 and the unmapped players are listed.

Usage
-----
    python scripts/fetch_fotmob.py --season 2026-27
    python scripts/fetch_fotmob.py --season 2026-27 --backfill 2023-24,2024-25,2025-26
    python scripts/fetch_fotmob.py --season 2026-27 --max-matches 5
    python scripts/fetch_fotmob.py --season 2026-27 --dry-run   # list what would be fetched

A full season is about 380 x 3 s = 19 minutes; a weekly run is about 30 seconds.
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import gzip
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEAGUE_ID = 47
BASE = 'https://www.fotmob.com'
USER_AGENT = ('FPL-Assistant-research/1.0 (personal non-commercial project; '
              'github.com/LouaiSf/Fantasy-premier-league-points-prediction)')
MIN_INTERVAL_S = 3.0
TIMEOUT_S = 30
RETRY_BACKOFF_S = (10, 30, 90)      # on 429 and 5xx
MAX_CONSECUTIVE_FAILURES = 3
MIN_MAPPED_MINUTES = 0.98
# Below this share of a match's minutes verifying against FPL, the two sources
# are taken to describe different games and the match is left unmapped.
MIN_MATCH_VERIFIED = 0.5
NAME_MATCH_MIN = 0.85
OVERRIDES = os.path.join(ROOT, 'data', 'fotmob_overrides.csv')

# FotMob team id -> the names FPL has used for that club (teams.csv changes
# them between seasons: "Ipswich" in 2024-25, "Ipswich Town" in 2026-27).
FOTMOB_TEAM_TO_FPL = {
    8678: ('Bournemouth',), 9825: ('Arsenal',), 10252: ('Aston Villa',), 9937: ('Brentford',),
    10204: ('Brighton',), 8191: ('Burnley',), 8455: ('Chelsea',), 8669: ('Coventry City', 'Coventry'),
    9826: ('Crystal Palace',), 8668: ('Everton',), 9879: ('Fulham',), 8667: ('Hull City', 'Hull'),
    9902: ('Ipswich Town', 'Ipswich'), 8463: ('Leeds',), 8197: ('Leicester',), 8650: ('Liverpool',),
    8346: ('Luton',), 8456: ('Man City',), 10260: ('Man Utd',), 10261: ('Newcastle',),
    10203: ("Nott'm Forest",), 8657: ('Sheffield Utd',), 8466: ('Southampton',),
    8472: ('Sunderland',), 8586: ('Spurs',), 8654: ('West Ham',), 8602: ('Wolves',),
}

# FotMob's English stat label -> column. A label FotMob did not send for a
# player is NaN in the output, never 0.
LABELS = {
    'Minutes played': 'minutes',
    'FotMob rating': 'fotmob_rating',
    'Expected assists (xA)': 'xa',
    'Chances created': 'chances_created',
    'Big chances created': 'big_chances_created',
    'Big chances missed': 'big_chances_missed',
    'Hit woodwork': 'hit_woodwork',
    'Touches': 'touches',
    'Touches in opposition box': 'touches_opp_box',
    'Passes into final third': 'passes_final_third',
    'Accurate passes': 'accurate_passes',
    'Accurate crosses': 'accurate_crosses',
    'Accurate long balls': 'accurate_long_balls',
    'Successful dribbles': 'successful_dribbles',
    'Dispossessed': 'dispossessed',
    'Was fouled': 'was_fouled',
    'Fouls committed': 'fouls_committed',
    'Offsides': 'offsides',
    'Tackles': 'tackles',
    'Blocks': 'blocks',
    'Clearances': 'clearances',
    'Headed clearance': 'headed_clearances',
    'Interceptions': 'interceptions',
    'Recoveries': 'recoveries',
    'Defensive actions': 'defensive_actions',
    'Dribbled past': 'dribbled_past',
    'Clearance off the line': 'clearances_off_line',
    'Last man tackle': 'last_man_tackles',
    'Error led to goal': 'errors_led_to_goal',
    'Duels won': 'duels_won',
    'Duels lost': 'duels_lost',
    'Ground duels won': 'ground_duels_won',
    'Aerial duels won': 'aerial_duels_won',
    'Saves': 'saves',
    'Goals conceded': 'goals_conceded',
    'xGOT faced': 'xgot_faced',
    'Goals prevented': 'goals_prevented',
    'Saves inside box': 'saves_inside_box',
    'Diving save': 'diving_saves',
    'High claim': 'high_claims',
    'Punches': 'punches',
    'Acted as sweeper': 'sweeper_actions',
    'Distance covered': 'distance_m',
    'Top speed': 'top_speed_kmh',
    'Number of sprints': 'sprints',
    'Fantasy points': 'fantasy_points',
}
# "14/18 accurate passes" arrives as value 14, total 18: total is kept as <col>_att.
FRACTION_COLUMNS = ('accurate_passes', 'accurate_crosses', 'accurate_long_balls',
                    'successful_dribbles', 'ground_duels_won', 'aerial_duels_won')
LABEL_COLUMNS = list(LABELS.values()) + [f'{c}_att' for c in FRACTION_COLUMNS]
SHOT_COLUMNS = ['xg', 'npxg', 'xgot', 'shots', 'shots_on_target', 'shots_in_box',
                'shots_blocked', 'goals']
KEY_COLUMNS = ['season', 'gw', 'fpl_fixture', 'fotmob_match_id', 'fpl_team_id',
               'fotmob_player_id', 'opta_id', 'player_name', 'element', 'map_method',
               'map_confidence', 'is_gk']

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)


class FotmobError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Fetcher:
    """Polite GET for HTML pages: one request per MIN_INTERVAL_S, backoff on 429/5xx."""

    def __init__(self, interval: float = MIN_INTERVAL_S, sleep=time.sleep, clock=time.monotonic,
                 opener=urllib.request.urlopen):
        self.interval, self.sleep, self.clock, self.opener = interval, sleep, clock, opener
        self._last = None

    def _wait(self) -> None:
        if self._last is not None:
            gap = self.interval - (self.clock() - self._last)
            if gap > 0:
                self.sleep(gap)
        self._last = self.clock()

    def get(self, url: str) -> str:
        path = urllib.parse.urlparse(url).path
        if path.startswith('/api/') or 'data.fotmob.com' in url:
            raise FotmobError(f'refusing to fetch {url}: only public HTML pages are read')
        for attempt in range(len(RETRY_BACKOFF_S) + 1):
            self._wait()
            try:
                req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
                                                           'Accept': 'text/html'})
                with self.opener(req, timeout=TIMEOUT_S) as resp:
                    return resp.read().decode('utf-8', errors='replace')
            except urllib.error.HTTPError as exc:
                if (exc.code == 429 or exc.code >= 500) and attempt < len(RETRY_BACKOFF_S):
                    self.sleep(RETRY_BACKOFF_S[attempt])
                    continue
                raise FotmobError(f'HTTP {exc.code} for {url}') from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < len(RETRY_BACKOFF_S):
                    self.sleep(RETRY_BACKOFF_S[attempt])
                    continue
                raise FotmobError(f'{type(exc).__name__} for {url}: {exc}') from None
        raise FotmobError(f'gave up on {url}')


def check_robots(fetcher: Fetcher, urls: list[str], parser_cls=urllib.robotparser.RobotFileParser) -> None:
    """Abort unless robots.txt lets USER_AGENT fetch every one of urls."""
    rp = parser_cls()
    rp.parse(fetcher.get(f'{BASE}/robots.txt').splitlines())
    blocked = [u for u in urls if not rp.can_fetch(USER_AGENT, u)]
    if blocked:
        raise FotmobError('robots.txt does not allow fetching ' + ', '.join(blocked)
                          + '; not scraping.')


def page_props(html: str) -> dict:
    match = NEXT_DATA.search(html)
    if not match:
        raise FotmobError('page has no __NEXT_DATA__ block; FotMob may have changed its layout')
    return json.loads(match.group(1))['props']['pageProps']


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def fotmob_season(season: str) -> str:
    """'2026-27' -> '2026-2027'."""
    start = int(season[:4])
    return f'{start}-{start + 1}'


def league_url(season: str) -> str:
    return f'{BASE}/leagues/{LEAGUE_ID}/fixtures/premier-league?season={fotmob_season(season)}'


def match_url(match_id: int) -> str:
    """The page for exactly this match.

    The league page's pageUrl is /matches/<slug>/<code>#<id>, but <code>
    names the pairing of the two clubs and the #<id> fragment never reaches
    the server, so that URL serves whichever meeting FotMob picks -- a cup
    tie, or next month's fixture. /match/<id> serves the one asked for.
    """
    return f'{BASE}/match/{match_id}'


def finished_matches(league_props: dict) -> list[dict]:
    """Finished, not cancelled or abandoned, league matches from a league page."""
    out = []
    for m in league_props['fixtures']['allMatches']:
        status = m.get('status') or {}
        if not status.get('finished') or status.get('cancelled'):
            continue
        out.append({'id': int(m['id']), 'round': m.get('round'),
                    'home_id': int(m['home']['id']), 'home_name': m['home']['name'],
                    'away_id': int(m['away']['id']), 'away_name': m['away']['name'],
                    'utc_time': status.get('utcTime')})
    return out


def has_player_stats(props: dict) -> bool:
    players = ((props.get('content') or {}).get('playerStats')) or {}
    return any(p.get('stats') for p in players.values())


def cached_slice(props: dict, match_id: int) -> dict:
    """The part of a match page this script reads; everything else is dropped.

    Raises if the page is for a different match, so a wrong page is never cached.
    """
    served = str((props.get('general') or {}).get('matchId'))
    if served != str(match_id):
        raise FotmobError(f'asked for match {match_id}, page is match {served}')
    content = props.get('content') or {}
    return {'general': props.get('general') or {},
            'content': {'shotmap': content.get('shotmap'),
                        'playerStats': content.get('playerStats')}}


def _stat_value(entry: dict):
    stat = (entry or {}).get('stat') or {}
    value = stat.get('value')
    if isinstance(value, bool) or value is None:
        return np.nan, None
    total = stat.get('total') if str(stat.get('type', '')).startswith('fraction') else None
    return float(value), (None if total is None else float(total))


def parse_player_stats(player_stats: dict) -> list[dict]:
    """One row per player who has stats; unused substitutes have none and are skipped."""
    rows = []
    for p in (player_stats or {}).values():
        sections = p.get('stats') or []
        if not sections:
            continue
        row = {'fotmob_player_id': int(p['id']), 'opta_id': p.get('optaId'),
               'player_name': p.get('name'), 'fotmob_team_id': int(p['teamId']),
               'is_gk': bool(p.get('isGoalkeeper'))}
        for col in LABEL_COLUMNS:
            row[col] = np.nan
        for section in sections:
            for label, entry in (section.get('stats') or {}).items():
                col = LABELS.get(label)
                if col is None or not np.isnan(row[col]):
                    continue    # some labels repeat across sections; the first wins
                value, total = _stat_value(entry)
                row[col] = value
                if col in FRACTION_COLUMNS and total is not None:
                    row[f'{col}_att'] = total
        rows.append(row)
    return rows


def parse_shots(shotmap: dict | None) -> pd.DataFrame:
    shots = (shotmap or {}).get('shots') or []
    rows = [{'fotmob_player_id': s.get('playerId'), 'fotmob_team_id': s.get('teamId'),
             'minute': s.get('min'), 'minute_added': s.get('minAdded'),
             'situation': s.get('situation'), 'shot_type': s.get('shotType'),
             'x': s.get('x'), 'y': s.get('y'),
             'is_on_target': bool(s.get('isOnTarget')), 'is_blocked': bool(s.get('isBlocked')),
             'is_from_inside_box': bool(s.get('isFromInsideBox')),
             'is_goal': s.get('eventType') == 'Goal', 'is_own_goal': bool(s.get('isOwnGoal')),
             'xg': float(s.get('expectedGoals') or 0.0),
             'xgot': float(s.get('expectedGoalsOnTarget') or 0.0),
             'keeper_id': s.get('keeperId')}
            for s in shots]
    return pd.DataFrame(rows, columns=['fotmob_player_id', 'fotmob_team_id', 'minute', 'minute_added',
                                       'situation', 'shot_type', 'x', 'y', 'is_on_target', 'is_blocked',
                                       'is_from_inside_box', 'is_goal', 'is_own_goal', 'xg', 'xgot',
                                       'keeper_id'])


def aggregate_shots(shots: pd.DataFrame) -> pd.DataFrame:
    """Per-player shot totals. Own goals are not the scorer's shots and are left out."""
    s = shots[~shots['is_own_goal'].astype(bool)].copy()
    s['npxg'] = np.where(s['situation'] == 'Penalty', 0.0, s['xg'])
    g = s.groupby('fotmob_player_id')
    out = pd.DataFrame({
        'xg': g['xg'].sum(), 'npxg': g['npxg'].sum(), 'xgot': g['xgot'].sum(),
        'shots': g.size(), 'shots_on_target': g['is_on_target'].sum(),
        'shots_in_box': g['is_from_inside_box'].sum(), 'shots_blocked': g['is_blocked'].sum(),
        'goals': g['is_goal'].sum(),
    })
    return out.reset_index()


def keeper_xgot_mismatches(rows: list[dict], shots: pd.DataFrame, tol: float = 0.05) -> list[str]:
    """GKs whose reported xGOT faced disagrees with the shots they faced."""
    out = []
    faced = shots[~shots['is_own_goal'].astype(bool)].groupby('keeper_id')['xgot'].sum()
    for r in rows:
        if not r['is_gk'] or np.isnan(r['xgot_faced']):
            continue
        from_shots = float(faced.get(r['fotmob_player_id'], 0.0))
        if abs(from_shots - r['xgot_faced']) > tol:
            out.append(f"{r['player_name']}: xGOT faced {r['xgot_faced']:.2f}, shots say {from_shots:.2f}")
    return out


def match_rows(cached: dict) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """(player rows with shot totals, shot rows, warnings) for one cached match."""
    content = cached['content']
    rows = parse_player_stats(content.get('playerStats'))
    shotmap = content.get('shotmap')
    shots = parse_shots(shotmap)
    warnings = keeper_xgot_mismatches(rows, shots)
    players = pd.DataFrame(rows, columns=['fotmob_player_id', 'opta_id', 'player_name',
                                          'fotmob_team_id', 'is_gk'] + LABEL_COLUMNS)
    if shotmap is None or 'shots' not in shotmap:
        for col in SHOT_COLUMNS:
            players[col] = np.nan      # no shotmap at all: unknown, not zero
    else:
        players = players.merge(aggregate_shots(shots), on='fotmob_player_id', how='left')
        players[SHOT_COLUMNS] = players[SHOT_COLUMNS].fillna(0.0)
    return players, shots, warnings


# --------------------------------------------------------------------------
# FPL joins
# --------------------------------------------------------------------------

def team_lookup(teams: pd.DataFrame) -> dict[int, int]:
    """FotMob team id -> FPL team id for one season's teams.csv."""
    by_name = {str(n): int(i) for i, n in zip(teams['id'], teams['name'])}
    out = {}
    for fm_id, names in FOTMOB_TEAM_TO_FPL.items():
        for name in names:
            if name in by_name:
                out[fm_id] = by_name[name]
                break
    return out


def attach_fixtures(matches: list[dict], fixtures: pd.DataFrame, teams: dict[int, int]) -> list[dict]:
    """Add gw, fpl_fixture and FPL team ids. Unknown clubs or fixtures are hard errors."""
    unknown = sorted({(m[f'{side}_id'], m[f'{side}_name']) for m in matches
                      for side in ('home', 'away') if m[f'{side}_id'] not in teams})
    if unknown:
        raise FotmobError('FotMob teams with no FPL mapping (add them to FOTMOB_TEAM_TO_FPL): '
                          + ', '.join(f'{i} {n}' for i, n in unknown))
    by_pair = {(int(h), int(a)): (e, int(i)) for h, a, e, i in
               zip(fixtures['team_h'], fixtures['team_a'], fixtures['event'], fixtures['id'])}
    out, missing = [], []
    for m in matches:
        h, a = teams[m['home_id']], teams[m['away_id']]
        hit = by_pair.get((h, a))
        if hit is None or pd.isna(hit[0]):
            missing.append(f"{m['home_name']} v {m['away_name']} ({m['id']})")
            continue
        out.append({**m, 'fpl_home': h, 'fpl_away': a, 'gw': int(hit[0]), 'fpl_fixture': hit[1]})
    if missing:
        raise FotmobError('finished FotMob matches with no FPL fixture: ' + '; '.join(missing))
    return out


# Letters NFKD does not split into a base letter plus an accent.
_UNDECOMPOSED = str.maketrans({'ø': 'o', 'ł': 'l', 'đ': 'd', 'æ': 'ae', 'œ': 'oe', 'ı': 'i', 'þ': 'th'})


def normalise(name) -> str:
    text = unicodedata.normalize('NFKD', str(name or '').casefold()).translate(_UNDECOMPOSED)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", ' ', text.replace("'", ''))
    return ' '.join(text.split())


def name_score(fotmob_name: str, first: str, second: str, web: str) -> float:
    full = normalise(fotmob_name)
    fpl_full = normalise(f'{first} {second}')
    if not full:
        return 0.0
    if full == fpl_full:
        return 1.0
    tokens = full.split()
    second_n, web_n = normalise(second), normalise(web)
    if tokens[-1] in (web_n, second_n) or (second_n and tokens[-1] == second_n.split()[-1]):
        return 0.95
    fpl_tokens = set(fpl_full.split()) | set(web_n.split())
    if set(tokens) <= fpl_tokens or (web_n and set(web_n.split()) <= set(tokens) and len(web_n) > 3):
        return 0.9
    return max(difflib.SequenceMatcher(None, full, c).ratio() for c in (fpl_full, web_n) if c) \
        if (fpl_full or web_n) else 0.0


def fpl_candidates(merged: pd.DataFrame, raw: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    """merged_gw rows with the FPL team the player played for in that fixture and his names.

    merged_gw's own team column is the player's club at export time in older
    seasons, so the team comes from was_home and the fixture instead.
    """
    fx = fixtures[['id', 'team_h', 'team_a']].rename(columns={'id': 'fixture'})
    m = merged[['element', 'GW', 'fixture', 'minutes', 'total_points', 'was_home']].copy()
    m['was_home'] = m['was_home'].astype(str).str.lower().isin(('true', '1'))
    # A handful of seasons repeat a row; the totals are the same either way.
    m = m.drop_duplicates(['element', 'fixture'])
    m = m.merge(fx, on='fixture', how='left')
    m['fpl_team_id'] = np.where(m['was_home'], m['team_h'], m['team_a'])
    names = raw[['id', 'first_name', 'second_name', 'web_name']].rename(columns={'id': 'element'})
    return m.merge(names, on='element', how='left')


def map_match(players: pd.DataFrame, candidates: pd.DataFrame, overrides: dict[int, int]) -> pd.DataFrame:
    """Give each FotMob player in one team-fixture an FPL element, one to one.

    candidates holds that team-fixture's merged_gw rows. Methods, best first:
    override, name+minutes+points (1.0), name+minutes (0.9), and minutes+points
    (0.8) when that pair is unique among the remaining candidates.
    """
    players = players.copy()
    players['element'], players['map_method'], players['map_confidence'] = np.nan, None, np.nan
    taken: set[int] = set()
    proposals = []
    for idx, p in players.iterrows():
        pid = int(p['fotmob_player_id'])
        if pid in overrides:
            players.loc[idx, ['element', 'map_method', 'map_confidence']] = [overrides[pid], 'override', 1.0]
            taken.add(overrides[pid])
            continue
        for _, c in candidates.iterrows():
            minutes_ok = not np.isnan(p['minutes']) and abs(p['minutes'] - c['minutes']) <= 1
            points_ok = not np.isnan(p['fantasy_points']) and p['fantasy_points'] == c['total_points']
            score = name_score(p['player_name'], c['first_name'], c['second_name'], c['web_name'])
            if score >= NAME_MATCH_MIN and minutes_ok:
                conf, method = (1.0, 'name+minutes+points') if points_ok else (0.9, 'name+minutes')
                proposals.append((conf, score, idx, int(c['element']), method))
    for conf, _score, idx, element, method in sorted(proposals, key=lambda t: (-t[0], -t[1])):
        if element in taken or not pd.isna(players.loc[idx, 'element']):
            continue
        players.loc[idx, ['element', 'map_method', 'map_confidence']] = [element, method, conf]
        taken.add(element)
    # Names that did not match: fall back on minutes and FPL points, if unambiguous.
    free = candidates[~candidates['element'].isin(taken)]
    for idx, p in players[players['element'].isna()].iterrows():
        if np.isnan(p['minutes']) or np.isnan(p['fantasy_points']):
            continue
        hit = free[((free['minutes'] - p['minutes']).abs() <= 1) & (free['total_points'] == p['fantasy_points'])]
        rivals = players[players['element'].isna()
                         & ((players['minutes'] - p['minutes']).abs() <= 1)
                         & (players['fantasy_points'] == p['fantasy_points'])]
        if len(hit) == 1 and len(rivals) == 1:
            element = int(hit['element'].iloc[0])
            players.loc[idx, ['element', 'map_method', 'map_confidence']] = [element, 'minutes+points', 0.8]
            free = free[free['element'] != element]
    return players


def gameweek_fallback(rows: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """Map players the fixture search missed by looking across their whole gameweek.

    The live-season FPL export files a transferred player's earlier gameweeks
    under his current club's fixture, so his row is in the right gameweek with
    the right minutes and points but the wrong fixture. Name, minutes and
    points must all agree, and the element must be unclaimed in that gameweek.
    """
    rows = rows.copy()
    open_rows = rows['element'].isna() & rows['map_method'].isna() & (rows['minutes'].fillna(0) > 0)
    for idx in rows.index[open_rows]:
        p = rows.loc[idx]
        taken = set(rows.loc[(rows['gw'] == p['gw']), 'element'].dropna().astype(int))
        pool = candidates[(candidates['GW'] == p['gw']) & ~candidates['element'].isin(taken)
                          & ((candidates['minutes'] - p['minutes']).abs() <= 1)
                          & (candidates['total_points'] == p['fantasy_points'])]
        hits = [int(c.element) for c in pool.itertuples()
                if name_score(p['player_name'], c.first_name, c.second_name, c.web_name) >= NAME_MATCH_MIN]
        if len(set(hits)) == 1:
            rows.loc[idx, ['element', 'map_method', 'map_confidence']] = [hits[0], 'name+minutes+points (gw)', 0.85]
    return rows


def match_minutes_verified(rows: pd.DataFrame) -> float:
    """Share of a match's FotMob minutes that were matched to FPL with minutes agreeing."""
    minutes = rows['minutes'].fillna(0)
    if not minutes.sum():
        return 1.0
    return float(minutes[rows['element'].notna()].sum() / minutes.sum())


def season_consolidate(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Per FotMob player, the element chosen most often; fill gaps where that element played."""
    mapped = rows.dropna(subset=['element'])
    mode = (mapped.groupby(['fotmob_player_id', 'element']).size().rename('matches').reset_index()
            .sort_values(['fotmob_player_id', 'matches'], ascending=[True, False]))
    conflicts = []
    for pid, grp in mode.groupby('fotmob_player_id'):
        if len(grp) > 1:
            name = rows.loc[rows['fotmob_player_id'] == pid, 'player_name'].iloc[0]
            conflicts.append(f'{name} ({pid}) -> elements '
                             + ', '.join(f'{int(e)} x{n}' for e, n in zip(grp['element'], grp['matches'])))
    best = mode.drop_duplicates('fotmob_player_id').set_index('fotmob_player_id')['element']
    rows = rows.copy()
    gap = rows['element'].isna() & rows['fotmob_player_id'].isin(best.index)
    for idx in rows.index[gap]:
        element = best[rows.at[idx, 'fotmob_player_id']]
        played = rows.at[idx, '_fixture_elements']
        if element in played and element not in set(
                rows.loc[(rows['fpl_fixture'] == rows.at[idx, 'fpl_fixture']), 'element'].dropna()):
            rows.loc[idx, ['element', 'map_method', 'map_confidence']] = [element, 'season', 0.7]
    names = rows.drop_duplicates('fotmob_player_id').set_index('fotmob_player_id')['player_name']
    pmap = pd.DataFrame({'fotmob_player_id': best.index, 'element': best.values.astype(int),
                         'player_name': names.reindex(best.index).values})
    pmap['matches'] = mode.drop_duplicates('fotmob_player_id')['matches'].values
    return rows, pmap, conflicts


def load_overrides(season: str, path: str = OVERRIDES) -> dict[int, int]:
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, comment='#')
    df = df[df['season'].astype(str) == season]
    return {int(p): int(e) for p, e in zip(df['fotmob_player_id'], df['element'])}


# --------------------------------------------------------------------------
# Season run
# --------------------------------------------------------------------------

def season_dir(season: str) -> str:
    return os.path.join(ROOT, 'data', season, 'fotmob')


def raw_path(season: str, match_id: int) -> str:
    return os.path.join(season_dir(season), 'raw', f'match_{match_id}.json.gz')


def read_cached(path: str) -> dict:
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        return json.load(fh)


def write_cached(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.tmp'
    with gzip.open(tmp, 'wt', encoding='utf-8') as fh:
        json.dump(payload, fh, separators=(',', ':'))
    os.replace(tmp, path)


def download(season: str, fetcher: Fetcher, max_matches: int | None, dry_run: bool,
             log=print) -> list[dict]:
    """Fetch the league page, then every finished match not cached yet."""
    props = page_props(fetcher.get(league_url(season)))
    matches = finished_matches(props)
    todo = [m for m in matches if not os.path.exists(raw_path(season, m['id']))]
    cached = len(matches) - len(todo)
    if max_matches is not None:
        todo = todo[:max_matches]
    log(f'{season}: {len(matches)} finished matches, {cached} cached, {len(todo)} to fetch'
        + (f' (~{len(todo) * MIN_INTERVAL_S / 60:.0f} min)' if todo else ''))
    if dry_run:
        for m in todo:
            log(f"  would fetch {m['home_name']} v {m['away_name']} ({match_url(m['id'])})")
        return matches
    failures = 0
    for n, m in enumerate(todo, 1):
        try:
            props = page_props(fetcher.get(match_url(m['id'])))
            payload = cached_slice(props, m['id'])
            failures = 0
            # Finished, but player stats are not out yet: try again next run
            # rather than caching an empty match that would never be refetched.
            if not has_player_stats(props):
                log(f"  no player stats yet for {m['home_name']} v {m['away_name']}; will retry next run")
                continue
            write_cached(raw_path(season, m['id']), payload)
        except (FotmobError, KeyError, ValueError) as exc:
            failures += 1
            log(f"  FAILED {m['home_name']} v {m['away_name']}: {exc}")
            if failures >= MAX_CONSECUTIVE_FAILURES:
                raise FotmobError(f'{failures} matches in a row failed; stopping') from None
        if n % 20 == 0 or n == len(todo):
            log(f'  fetched {n}/{len(todo)}')
    return matches


def build_season(season: str, matches: list[dict], log=print) -> dict:
    """Parse every cached match, map players to FPL and write the season's CSVs."""
    base = os.path.join(ROOT, 'data', season)
    fixtures = pd.read_csv(os.path.join(base, 'fixtures.csv'))
    teams = team_lookup(pd.read_csv(os.path.join(base, 'teams.csv')))
    merged = pd.read_csv(os.path.join(base, 'gws', 'merged_gw.csv'), low_memory=False)
    raw = pd.read_csv(os.path.join(base, 'players_raw.csv'))
    cands = fpl_candidates(merged, raw, fixtures)
    overrides = load_overrides(season)
    cached = [m for m in attach_fixtures(matches, fixtures, teams) if os.path.exists(raw_path(season, m['id']))]

    all_rows, all_shots, warnings, mismatched, awaiting = [], [], [], [], []
    for m in cached:
        payload = read_cached(raw_path(season, m['id']))
        if str(payload['general'].get('matchId')) != str(m['id']):
            log(f"  skipping {raw_path(season, m['id'])}: it holds match {payload['general'].get('matchId')}")
            continue
        players, shots, warn = match_rows(payload)
        if players.empty:
            continue
        warnings += [f"{m['home_name']} v {m['away_name']}: {w}" for w in warn]
        players['fpl_team_id'] = players['fotmob_team_id'].map(teams)
        fixture_cands = cands[cands['fixture'] == m['fpl_fixture']]
        played = set(fixture_cands['element'].astype(int))
        match_frames = []
        for team_id, grp in players.groupby('fpl_team_id'):
            mapped = map_match(grp, fixture_cands[fixture_cands['fpl_team_id'] == team_id], overrides)
            mapped['_fixture_elements'] = [played] * len(mapped)
            match_frames.append(mapped)
        match_df = pd.concat(match_frames, ignore_index=True)
        # Names match but minutes do not, for most of the match: FotMob and FPL
        # are describing different games (a replay, or one side's data is
        # wrong). Joining them would pin one game's stats on the other's points.
        verified = match_minutes_verified(match_df)
        if fixture_cands.empty:
            # FotMob has the result before the local FPL data does; the next
            # run after scripts/fetch_data.py maps it.
            awaiting.append(f"GW{m['gw']} {m['home_name']} v {m['away_name']}")
            match_df['map_method'] = 'awaiting_fpl'
        elif verified < MIN_MATCH_VERIFIED:
            mismatched.append({'fotmob_match_id': m['id'], 'fpl_fixture': m['fpl_fixture'], 'gw': m['gw'],
                               'match': f"{m['home_name']} v {m['away_name']}",
                               'fotmob_utc_time': m.get('utc_time'), 'verified_minutes_share': round(verified, 3)})
            match_df[['element', 'map_confidence']] = np.nan
            match_df['map_method'] = 'source_mismatch'
            match_df['_fixture_elements'] = [set()] * len(match_df)
        all_rows.append(match_df.assign(season=season, gw=m['gw'], fpl_fixture=m['fpl_fixture'],
                                        fotmob_match_id=m['id']))
        all_shots.append(shots.assign(season=season, gw=m['gw'], fpl_fixture=m['fpl_fixture'],
                                      fotmob_match_id=m['id'],
                                      fpl_team_id=shots['fotmob_team_id'].map(teams)))
    if not all_rows:
        raise FotmobError(f'{season}: no cached matches to build from')

    rows = pd.concat(all_rows, ignore_index=True)
    rows = gameweek_fallback(rows, cands)
    rows, pmap, conflicts = season_consolidate(rows)
    rows = rows.drop(columns=['_fixture_elements', 'fotmob_team_id'])
    rows['element'] = rows['element'].astype('Int64')
    rows = rows[KEY_COLUMNS + LABEL_COLUMNS + SHOT_COLUMNS].sort_values(['gw', 'fpl_fixture', 'fpl_team_id'])
    shots = pd.concat(all_shots, ignore_index=True)
    shots['element'] = shots.merge(
        rows[['fotmob_match_id', 'fotmob_player_id', 'element']],
        on=['fotmob_match_id', 'fotmob_player_id'], how='left')['element'].values

    # Matches the two sources disagree on are reported, not counted against coverage.
    comparable = ~rows['map_method'].isin(('source_mismatch', 'awaiting_fpl'))
    minutes = rows['minutes'].fillna(0).where(comparable, 0)
    coverage = float(minutes[rows['element'].notna()].sum() / minutes.sum()) if minutes.sum() else 0.0
    unmapped = rows[rows['element'].isna() & (minutes > 0)]

    out = season_dir(season)
    os.makedirs(out, exist_ok=True)
    rows.to_csv(os.path.join(out, 'player_match.csv'), index=False)
    shots.to_csv(os.path.join(out, 'shots.csv'), index=False)
    pmap.to_csv(os.path.join(out, 'player_map.csv'), index=False)
    report = {
        'season': season, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'matches': len(cached), 'last_gw': int(rows['gw'].max()), 'player_rows': len(rows),
        'shots': len(shots), 'mapped_minutes_share': round(coverage, 4),
        'map_methods': rows['map_method'].fillna('unmapped').value_counts().to_dict(),
        'unmapped_players': len(unmapped), 'conflicts': len(conflicts), 'keeper_warnings': len(warnings),
        'source_mismatches': mismatched, 'awaiting_fpl': awaiting,
    }
    with open(os.path.join(out, 'sync.json'), 'w', encoding='utf-8') as fh:
        json.dump(report, fh, indent=2)

    if awaiting:
        log(f'  {len(awaiting)} match(es) not in the local FPL data yet, left unmapped: ' + '; '.join(awaiting))
    for mm in mismatched:
        log(f"  source mismatch, left unmapped: GW{mm['gw']} {mm['match']} (FotMob {mm['fotmob_utc_time']}, "
            f"{mm['verified_minutes_share']:.0%} of minutes agree with FPL)")
    for w in warnings[:10]:
        log(f'  warning: {w}')
    for c in conflicts[:20]:
        log(f'  conflict: {c}')
    log(f'{season}: {len(cached)} matches, {len(rows)} player rows, '
        f'{coverage:.1%} of FotMob minutes mapped to FPL ({report["map_methods"]})')
    report['unmapped'] = [f"GW{r.gw} {r.player_name} ({r.fotmob_player_id}), {r.minutes:.0f} min"
                          for r in unmapped.itertuples()]
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--season', required=True, help='e.g. 2026-27')
    ap.add_argument('--backfill', default='', help='more seasons, comma separated: 2023-24,2024-25')
    ap.add_argument('--max-matches', type=int, default=None, help='fetch at most N new matches per season')
    ap.add_argument('--dry-run', action='store_true', help='list what would be fetched, fetch nothing else')
    args = ap.parse_args(argv)
    seasons = [s.strip() for s in args.backfill.split(',') if s.strip()] + [args.season]

    fetcher = Fetcher()
    status = 0
    try:
        check_robots(fetcher, [league_url(args.season), match_url(5795363)])
        for season in seasons:
            matches = download(season, fetcher, args.max_matches, args.dry_run)
            if args.dry_run:
                continue
            report = build_season(season, matches)
            if report['mapped_minutes_share'] < MIN_MAPPED_MINUTES:
                print(f"{season}: only {report['mapped_minutes_share']:.1%} of minutes mapped "
                      f'(need {MIN_MAPPED_MINUTES:.0%}). Unmapped:', file=sys.stderr)
                for line in report['unmapped']:
                    print(f'  {line}', file=sys.stderr)
                print(f'Add them to {os.path.relpath(OVERRIDES, ROOT)} (season,fotmob_player_id,element).',
                      file=sys.stderr)
                status = 2
    except FotmobError as exc:
        print(f'FotMob fetch failed: {exc}', file=sys.stderr)
        return 1
    return status


if __name__ == '__main__':
    sys.exit(main())
