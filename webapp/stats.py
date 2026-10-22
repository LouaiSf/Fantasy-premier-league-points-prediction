"""Stats Lab: per-player underlying numbers over a gameweek window.

FPL's own per-match file (data/<season>/gws/merged_gw.csv) supplies minutes,
goals, assists, xG/xA, the defensive actions and saves. FotMob's
(data/<season>/fotmob/player_match.csv, written by scripts/fetch_fotmob.py)
adds what FPL does not publish: xGOT, shots and touches in the box, chances
created, blocks / interceptions / clearances as separate counts, and for
keepers xGOT faced and goals prevented. It is joined on (element, FPL
fixture). FotMob files are not committed, so a deployment without them
returns every FotMob field as null rather than 0: "not measured" is not
"did nothing".
"""

from __future__ import annotations

import math
import os
from functools import lru_cache

import numpy as np
import pandas as pd

# 2026/27 scoring, unchanged from 2025/26: +2 for reaching it in a match.
# DEF count clearances, blocks, interceptions and tackles (CBIT); MID and FWD
# also count ball recoveries (CBIRT). Goalkeepers cannot earn it.
DEFCON_THRESHOLD = {'DEF': 10, 'MID': 12, 'FWD': 12}
DEFCON_POINTS = 2
LAST_FORM_GWS = 4
WINDOWS = {'last4': 4, 'last6': 6, 'season': None}

FPL_COLUMNS = ['element', 'name', 'GW', 'fixture', 'minutes', 'goals_scored', 'assists',
               'expected_goals', 'expected_assists', 'expected_goal_involvements',
               'expected_goals_conceded', 'clearances_blocks_interceptions', 'tackles',
               'recoveries', 'saves', 'goals_conceded', 'clean_sheets', 'total_points',
               'position', 'team', 'opponent_team', 'was_home']
FOTMOB_COLUMNS = ['xg', 'npxg', 'xgot', 'shots', 'shots_on_target', 'shots_in_box',
                  'touches_opp_box', 'chances_created', 'big_chances_created', 'xa',
                  'tackles', 'blocks', 'interceptions', 'clearances', 'recoveries',
                  'xgot_faced', 'goals_prevented', 'saves_inside_box', 'goals']

# Each preset: the metric it sorts on, the direction, an optional position
# filter and minimum, and the columns the page shows first.
PRESETS = {
    'unlucky_finishers': {
        'label': 'Unlucky finishers', 'sort': 'xg_minus_goals', 'desc': True,
        'positions': ('MID', 'FWD', 'DEF'), 'min': {'shots': 3},
        'columns': ['xg', 'goals', 'xg_minus_goals', 'xgot_minus_xg', 'shots_p90'],
        'scatter': {'x': 'xg', 'y': 'goals', 'diagonal': True}},
    'clinical_finishers': {
        'label': 'Clinical finishers', 'sort': 'xgot_minus_xg', 'desc': True,
        'positions': ('MID', 'FWD', 'DEF'), 'min': {'shots': 3},
        'columns': ['xg', 'xgot', 'xgot_minus_xg', 'goals', 'shots_in_box_p90'],
        'scatter': {'x': 'xg', 'y': 'xgot', 'diagonal': True}},
    'defcon_machines': {
        'label': 'DefCon machines', 'sort': 'defcon_hit_rate', 'desc': True,
        'positions': ('DEF', 'MID'), 'min': {},
        'columns': ['defcon_p90', 'defcon_hit_rate', 'defcon_prob_next', 'tackles_p90',
                    'recoveries_p90'],
        'scatter': {'x': 'defcon_p90', 'y': 'defcon_hit_rate', 'diagonal': False}},
    'shot_stoppers': {
        'label': 'Shot-stoppers', 'sort': 'goals_prevented_p90', 'desc': True,
        'positions': ('GK',), 'min': {},
        'columns': ['goals_prevented', 'goals_prevented_p90', 'save_pct', 'xgot_faced_p90',
                    'clean_sheet_pct'],
        'scatter': {'x': 'xgot_faced_p90', 'y': 'goals_prevented_p90', 'diagonal': False}},
    'busy_keepers': {
        'label': 'Busy keepers', 'sort': 'xgot_faced_p90', 'desc': True,
        'positions': ('GK',), 'min': {},
        'columns': ['xgot_faced_p90', 'saves_p90', 'save_pct', 'goals_prevented_p90',
                    'saves_inside_box_p90'],
        'scatter': {'x': 'xgot_faced_p90', 'y': 'saves_p90', 'diagonal': False}},
    'rising_threat': {
        'label': 'Rising threat', 'sort': 'xgi_p90_trend', 'desc': True,
        'positions': ('MID', 'FWD', 'DEF'), 'min': {},
        'columns': ['xgi_p90_last4', 'xgi_p90', 'xgi_p90_trend', 'touches_opp_box_p90',
                    'chances_created_p90'],
        'scatter': {'x': 'xgi_p90', 'y': 'xgi_p90_last4', 'diagonal': True}},
    'creators_without_returns': {
        'label': 'Creators without returns', 'sort': 'xa_minus_assists', 'desc': True,
        'positions': ('MID', 'FWD', 'DEF'), 'min': {},
        'columns': ['xa', 'assists', 'xa_minus_assists', 'chances_created_p90',
                    'big_chances_created_p90'],
        'scatter': {'x': 'xa', 'y': 'assists', 'diagonal': True}},
}

# Metrics that exist only with FotMob data; null without it.
FOTMOB_METRICS = {
    'xgot', 'xgot_p90', 'xgot_minus_xg', 'goals_minus_xgot', 'shots', 'shots_p90',
    'shots_in_box_p90', 'touches_opp_box_p90', 'chances_created_p90',
    'big_chances_created_p90', 'blocks_p90', 'interceptions_p90', 'clearances_p90',
    'xgot_faced_p90', 'goals_prevented', 'goals_prevented_p90', 'saves_inside_box_p90',
    'npxg_p90',
}


def defcon_probability(rate_p90: float | None, expected_minutes: float | None,
                       threshold: int | None) -> float | None:
    """P(Poisson(rate x minutes/90) >= threshold): the chance of the DefCon bonus next match."""
    if rate_p90 is None or expected_minutes is None or threshold is None:
        return None
    lam = max(0.0, rate_p90) * max(0.0, expected_minutes) / 90.0
    below = sum(math.exp(-lam) * lam ** k / math.factorial(k) for k in range(threshold))
    return max(0.0, min(1.0, 1.0 - below))


def _read(path: str, usecols=None) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    head = pd.read_csv(path, nrows=0)
    cols = [c for c in usecols if c in head.columns] if usecols else None
    return pd.read_csv(path, usecols=cols, low_memory=False)


def _mtime(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def paths(root: str, season: str) -> dict:
    base = os.path.join(root, 'data', season)
    return {'fpl': os.path.join(base, 'gws', 'merged_gw.csv'),
            'fotmob': os.path.join(base, 'fotmob', 'player_match.csv'),
            'players': os.path.join(base, 'players_raw.csv'),
            'teams': os.path.join(base, 'teams.csv')}


def signature(root: str, season: str) -> tuple:
    return tuple(_mtime(p) for p in paths(root, season).values())


@lru_cache(maxsize=4)
def load_matches(root: str, season: str, _signature: tuple) -> tuple[pd.DataFrame, bool]:
    """One row per player per match, FPL columns plus fm_* where FotMob has the match."""
    p = paths(root, season)
    fpl = _read(p['fpl'], FPL_COLUMNS)
    if fpl is None or fpl.empty:
        return pd.DataFrame(), False
    fpl = fpl.copy()
    position = fpl['position'].replace({'GKP': 'GK'})
    fpl['position'] = position
    cbi = fpl['clearances_blocks_interceptions'].fillna(0) + fpl['tackles'].fillna(0)
    fpl['defensive_contribution'] = np.where(
        position == 'DEF', cbi, np.where(position.isin(['MID', 'FWD']),
                                         cbi + fpl['recoveries'].fillna(0), np.nan))

    fotmob = _read(p['fotmob'], ['element', 'fpl_fixture'] + FOTMOB_COLUMNS)
    has_fotmob = fotmob is not None and not fotmob.empty
    if has_fotmob:
        fotmob = (fotmob.dropna(subset=['element', 'fpl_fixture'])
                  .astype({'element': int, 'fpl_fixture': int})
                  .drop_duplicates(['element', 'fpl_fixture'])
                  .rename(columns={'fpl_fixture': 'fixture',
                                   **{c: f'fm_{c}' for c in FOTMOB_COLUMNS}}))
        for col in (f'fm_{c}' for c in FOTMOB_COLUMNS):
            if col not in fotmob.columns:
                fotmob[col] = np.nan
        fpl = fpl.merge(fotmob, on=['element', 'fixture'], how='left', indicator='_fm')
        fpl['fm_mapped'] = fpl.pop('_fm').eq('both')
        # FotMob leaves out a stat that is zero; a mapped match means 0.
        for col in (f'fm_{c}' for c in FOTMOB_COLUMNS):
            fpl.loc[fpl['fm_mapped'], col] = fpl.loc[fpl['fm_mapped'], col].fillna(0)
    else:
        fpl['fm_mapped'] = False
    return fpl, has_fotmob


def _players(root: str, season: str) -> pd.DataFrame:
    raw = _read(paths(root, season)['players'],
                ['id', 'web_name', 'code', 'team', 'element_type', 'now_cost'])
    if raw is None:
        return pd.DataFrame(columns=['element'])
    return raw.rename(columns={'id': 'element'})


def _per90(total, minutes):
    return None if total is None or not minutes else total * 90.0 / minutes


def _clean(value):
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return round(float(value), 3)
    if isinstance(value, float):
        return round(value, 3)
    return value


def summarise(block: pd.DataFrame, position: str, has_fotmob: bool) -> dict:
    """Every Stats Lab metric for one player's matches in a window."""
    played = block[block['minutes'] > 0]
    minutes = float(played['minutes'].sum())
    apps = int(len(played))
    total = lambda col: float(played[col].fillna(0).sum()) if col in played else 0.0  # noqa: E731

    goals, assists = total('goals_scored'), total('assists')
    xg, xa, xgi = total('expected_goals'), total('expected_assists'), total('expected_goal_involvements')
    out = {
        'minutes': minutes, 'apps': apps, 'points': total('total_points'),
        'goals': goals, 'assists': assists, 'xg': xg, 'xa': xa, 'xgi': xgi,
        'xg_p90': _per90(xg, minutes), 'xa_p90': _per90(xa, minutes), 'xgi_p90': _per90(xgi, minutes),
        'goals_minus_xg': goals - xg, 'xg_minus_goals': xg - goals,
        'assists_minus_xa': assists - xa, 'xa_minus_assists': xa - assists,
        'tackles_p90': _per90(total('tackles'), minutes),
        'recoveries_p90': _per90(total('recoveries'), minutes),
        'cbi_p90': _per90(total('clearances_blocks_interceptions'), minutes),
        'saves_p90': _per90(total('saves'), minutes),
    }

    threshold = DEFCON_THRESHOLD.get(position)
    if threshold is not None:
        out['defcon_p90'] = _per90(total('defensive_contribution'), minutes)
        sixty = played[played['minutes'] >= 60]
        out['defcon_hit_rate'] = (float((sixty['defensive_contribution'] >= threshold).mean())
                                  if len(sixty) else None)
        recent = played.sort_values('GW').tail(LAST_FORM_GWS)
        expected = float(recent['minutes'].mean()) if len(recent) else None
        out['defcon_prob_next'] = defcon_probability(out['defcon_p90'], expected, threshold)
    else:
        out['defcon_p90'] = out['defcon_hit_rate'] = out['defcon_prob_next'] = None

    if position == 'GK':
        saves, conceded = total('saves'), total('goals_conceded')
        out['save_pct'] = saves / (saves + conceded) if saves + conceded else None
        sixty = played[played['minutes'] >= 60]
        out['clean_sheet_pct'] = float(sixty['clean_sheets'].mean()) if len(sixty) else None
    else:
        out['save_pct'] = out['clean_sheet_pct'] = None

    mapped = played[played['fm_mapped']] if has_fotmob else played.iloc[0:0]
    fm_minutes = float(mapped['minutes'].sum())
    if has_fotmob and fm_minutes > 0:
        fm = lambda col: float(mapped[f'fm_{col}'].sum())  # noqa: E731
        fm_xg, xgot, fm_goals = fm('xg'), fm('xgot'), fm('goals')
        out.update({
            'xgot': xgot, 'xgot_p90': _per90(xgot, fm_minutes),
            'npxg_p90': _per90(fm('npxg'), fm_minutes),
            'xgot_minus_xg': xgot - fm_xg, 'goals_minus_xgot': fm_goals - xgot,
            'shots': fm('shots'), 'shots_p90': _per90(fm('shots'), fm_minutes),
            'shots_in_box_p90': _per90(fm('shots_in_box'), fm_minutes),
            'touches_opp_box_p90': _per90(fm('touches_opp_box'), fm_minutes),
            'chances_created_p90': _per90(fm('chances_created'), fm_minutes),
            'big_chances_created_p90': _per90(fm('big_chances_created'), fm_minutes),
            'blocks_p90': _per90(fm('blocks'), fm_minutes),
            'interceptions_p90': _per90(fm('interceptions'), fm_minutes),
            'clearances_p90': _per90(fm('clearances'), fm_minutes),
        })
        if position == 'GK':
            out.update({
                'xgot_faced_p90': _per90(fm('xgot_faced'), fm_minutes),
                'goals_prevented': fm('goals_prevented'),
                'goals_prevented_p90': _per90(fm('goals_prevented'), fm_minutes),
                'saves_inside_box_p90': _per90(fm('saves_inside_box'), fm_minutes),
            })
    for metric in FOTMOB_METRICS:
        out.setdefault(metric, None)
    out['fotmob_minutes'] = fm_minutes if has_fotmob else None
    return out


def resolve_window(matches: pd.DataFrame, window: str | None,
                   gw_from: int | None, gw_to: int | None) -> tuple[int, int]:
    last = int(matches['GW'].max()) if not matches.empty else 1
    if gw_from is not None or gw_to is not None:
        lo = max(1, gw_from or 1)
        hi = min(last, gw_to or last)
        return (lo, max(lo, hi))
    span = WINDOWS.get(window or 'season')
    return (1 if span is None else max(1, last - span + 1), last)


def _xgi_p90_by_player(rows: pd.DataFrame) -> pd.Series:
    played = rows[rows['minutes'] > 0]
    sums = played.groupby('element')[['expected_goal_involvements', 'minutes']].sum()
    return (sums['expected_goal_involvements'] * 90.0 / sums['minutes']).where(sums['minutes'] > 0)


def player_stats(root: str, season: str, *, window: str | None = 'season',
                 gw_from: int | None = None, gw_to: int | None = None,
                 position: str | None = None, min_minutes: int = 0,
                 preset: str | None = None, sort: str | None = None,
                 limit: int | None = None) -> dict:
    return _player_stats(root, season, signature(root, season), window, gw_from, gw_to,
                         position, min_minutes, preset, sort, limit)


@lru_cache(maxsize=64)
def _player_stats(root: str, season: str, _signature: tuple, window, gw_from, gw_to,
                  position, min_minutes, preset, sort, limit) -> dict:
    matches, has_fotmob = load_matches(root, season, _signature)
    if matches.empty:
        return {'rows': [], 'window': None, 'has_fotmob': False, 'presets': _preset_list()}
    lo, hi = resolve_window(matches, window, gw_from, gw_to)
    in_window = matches[(matches['GW'] >= lo) & (matches['GW'] <= hi)]
    last = int(matches['GW'].max())
    recent_xgi = _xgi_p90_by_player(matches[matches['GW'] > last - LAST_FORM_GWS])
    season_xgi = _xgi_p90_by_player(matches)

    spec = PRESETS.get(preset) if preset else None
    players = _players(root, season).set_index('element')
    rows = []
    for element, block in in_window.groupby('element'):
        pos = block['position'].mode().iat[0] if not block['position'].mode().empty else None
        if position and pos != position:
            continue
        if spec and pos not in spec['positions']:
            continue
        metrics = summarise(block, pos, has_fotmob)
        if metrics['minutes'] < min_minutes:
            continue
        if spec and any((metrics.get(k) or 0) < v for k, v in spec['min'].items()):
            continue
        last4, whole = recent_xgi.get(element), season_xgi.get(element)
        last4 = None if last4 is None or pd.isna(last4) else float(last4)
        whole = None if whole is None or pd.isna(whole) else float(whole)
        metrics['xgi_p90_last4'] = last4
        metrics['xgi_p90_trend'] = None if last4 is None or whole is None else last4 - whole
        info = players.loc[element] if element in players.index else pd.Series(dtype=object)
        code, web_name = info.get('code'), info.get('web_name')
        rows.append({
            'id': int(element),
            'name': str(web_name) if pd.notna(web_name) else str(block['name'].iat[-1]),
            'team': str(block.sort_values('GW')['team'].iat[-1]),
            'position': pos,
            'code': None if code is None or pd.isna(code) else int(code),
            'sources': ['fpl', 'fotmob'] if metrics['fotmob_minutes'] else ['fpl'],
            'metrics': {k: _clean(v) for k, v in metrics.items()},
        })

    sort_key = sort or (spec['sort'] if spec else 'xgi_p90')
    descending = spec['desc'] if spec and not sort else True
    present = [r for r in rows if r['metrics'].get(sort_key) is not None]
    absent = [r for r in rows if r['metrics'].get(sort_key) is None]
    present.sort(key=lambda r: r['metrics'][sort_key], reverse=descending)
    ordered = present + absent
    return {
        'rows': ordered[:limit] if limit else ordered,
        'total': len(ordered),
        'window': {'gw_from': lo, 'gw_to': hi, 'last_gw': last, 'name': window},
        'sort': sort_key, 'preset': preset,
        'has_fotmob': has_fotmob,
        'fotmob_metrics': sorted(FOTMOB_METRICS),
        'defcon_threshold': DEFCON_THRESHOLD,
        'presets': _preset_list(),
        'teams': team_table(matches, has_fotmob),
    }


def _preset_list() -> list:
    return [{'id': key, **{k: v for k, v in spec.items() if k != 'min'},
             'positions': list(spec['positions']), 'min': spec['min']}
            for key, spec in PRESETS.items()]


def team_table(matches: pd.DataFrame, has_fotmob: bool) -> list:
    """Rolling team xG for/against (and FotMob xGOT against) over the last 4 and 6 matches."""
    per_match = (matches.groupby(['team', 'fixture', 'GW'])
                 .agg(xg_for=('expected_goals', 'sum'),
                      **({'xgot_for': ('fm_xgot', 'sum')} if has_fotmob else {}))
                 .reset_index())
    opponents = per_match.rename(columns={'team': 'opp', 'xg_for': 'xg_against',
                                          **({'xgot_for': 'xgot_against'} if has_fotmob else {})})
    joined = per_match.merge(opponents, on=['fixture', 'GW'])
    joined = joined[joined['team'] != joined['opp']].sort_values('GW')
    out = []
    for team, block in joined.groupby('team'):
        entry = {'team': team, 'matches': int(len(block))}
        for n in (4, 6):
            tail = block.tail(n)
            entry[f'xg_for_{n}'] = _clean(float(tail['xg_for'].mean()))
            entry[f'xg_against_{n}'] = _clean(float(tail['xg_against'].mean()))
            entry[f'xgot_against_{n}'] = (_clean(float(tail['xgot_against'].mean()))
                                          if has_fotmob else None)
        out.append(entry)
    return sorted(out, key=lambda e: e['team'])


def player_underlying(root: str, season: str, element: int) -> dict:
    """Per-gameweek xGI, xGOT and defensive actions (keepers: goals prevented) for sparklines."""
    matches, has_fotmob = load_matches(root, season, signature(root, season))
    block = matches[matches['element'] == element].sort_values('GW') if not matches.empty else matches
    if block.empty:
        return {'element': element, 'gameweeks': [], 'has_fotmob': has_fotmob}
    position = block['position'].mode().iat[0]
    weeks = []
    for gw, week in block.groupby('GW'):
        mapped = week[week['fm_mapped']] if has_fotmob else week.iloc[0:0]
        weeks.append({
            'gw': int(gw),
            'minutes': _clean(float(week['minutes'].sum())),
            'xgi': _clean(float(week['expected_goal_involvements'].fillna(0).sum())),
            'xgot': _clean(float(mapped['fm_xgot'].sum())) if len(mapped) else None,
            'defensive_contribution': (_clean(float(week['defensive_contribution'].sum()))
                                       if position != 'GK' else None),
            'goals_prevented': (_clean(float(mapped['fm_goals_prevented'].sum()))
                                if position == 'GK' and len(mapped) else None),
        })
    return {'element': element, 'position': position, 'gameweeks': weeks,
            'has_fotmob': has_fotmob}
