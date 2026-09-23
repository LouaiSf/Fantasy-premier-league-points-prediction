"""Web UI for the FPL tools.

Wraps scripts/optimise.py rather than reimplementing it. Every number shown in
the browser comes from the same functions the CLI calls, so the two cannot
disagree -- which matters in a project where silent divergence between two code
paths has been the recurring bug.

Run:
    python webapp/app.py
    open http://127.0.0.1:5000

Needs predictions_next_gw.csv, produced by scripts/predict_gameweek.py.
"""

from __future__ import annotations

import os
import sys
import json
import logging
import math
import hmac
import contextlib
import functools
import traceback
import datetime
import subprocess
import threading
import time
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import pandas as pd
from flask import Flask, Response, g, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
# No os.chdir(ROOT): the working directory is process-wide state that every
# thread shares. Paths here are built from ROOT, and optimise.py is handed it
# explicitly (its `root=` arguments) rather than relying on being run from it.

try:
    from scripts import artifacts  # noqa: E402
    from scripts import optimise as opt  # noqa: E402
    from scripts import refresh_pipeline as pipeline  # noqa: E402
except ImportError:
    import artifacts  # noqa: E402
    import optimise as opt  # noqa: E402
    import refresh_pipeline as pipeline  # noqa: E402
from webapp.platform_data import (  # noqa: E402
    build_local_snapshot,
    latest_local_season,
    photo_url,
    player_history,
)
from webapp import contracts  # noqa: E402
from webapp import observability as obs  # noqa: E402
from webapp.contracts import API_CONTRACT_VERSION, MAX_BODY_BYTES, RequestError  # noqa: E402
from webapp.fpl_client import FplClient  # noqa: E402
from webapp.manager_routes import create_manager_blueprint  # noqa: E402

# optimise.py takes this as a CLI default rather than a module constant.
DEFAULT_BUDGET = 100.0

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_BODY_BYTES
obs.configure_logging()
request_metrics = obs.RequestMetrics()

# The Next.js frontend (webapp/frontend) runs on its own port and calls this
# API cross-origin. Fail closed: with ALLOWED_ORIGINS unset, development gets
# the local Next.js origins and production (APP_ENV=production) gets none, so
# browsers on other sites cannot call the API. '*' has to be asked for by name,
# and is refused in production. CORS is a browser-side control only; it does
# not stop curl, which is what the refresh token is for.
DEV_ORIGINS = ['http://localhost:3000', 'http://127.0.0.1:3000']


def is_production(environ=None) -> bool:
    return (environ or os.environ).get('APP_ENV', '').strip().lower() == 'production'


def resolve_allowed_origins(environ=None) -> list[str]:
    environ = os.environ if environ is None else environ
    raw = (environ.get('ALLOWED_ORIGINS') or '').strip()
    if not raw:
        return [] if is_production(environ) else list(DEV_ORIGINS)
    origins = [o.strip().rstrip('/') for o in raw.split(',') if o.strip()]
    if '*' in origins and is_production(environ):
        raise RuntimeError(
            "ALLOWED_ORIGINS='*' is not allowed when APP_ENV=production; "
            'list the frontend origin(s) explicitly.')
    return origins


_origins = resolve_allowed_origins()
if _origins:
    CORS(app, resources={r'/api/*': {'origins': _origins}},
         allow_headers=['Content-Type', 'Authorization'])

# The loaded predictions are an immutable snapshot: a read-only mapping that is
# replaced wholesale and never edited. A request grabs one snapshot and uses it
# start to finish, so a reload or refresh on another thread can never hand it
# half-old, half-new data (gunicorn runs several threads). Rebuilds are
# serialised by an RLock; the common path -- a fresh snapshot -- takes no lock.
# DataFrames inside a snapshot are shared between threads: treat them as
# read-only.
_snapshot: Mapping = MappingProxyType({})
_state_lock = threading.RLock()
_maintenance = 0    # > 0 while a refresh is rewriting the data files
manager_client = FplClient()


def project_path(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


def predictions_path() -> str:
    return os.path.join(ROOT, opt.PREDICTIONS)   # an absolute PREDICTIONS wins


def market_prices_path(season: str) -> str:
    return project_path('data', season, 'players_raw.csv')


def latest_season() -> str | None:
    data_dir = project_path('data')
    if not os.path.isdir(data_dir):
        return None
    seasons = sorted(d for d in os.listdir(data_dir)
                     if os.path.isdir(os.path.join(data_dir, d)) and d[:4].isdigit())
    return seasons[-1] if seasons else None


def _mtime_ns(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def source_signature(season: str | None) -> tuple:
    """Modification times of every file a snapshot is built from.

    A snapshot is stale when any of them differs from what it was built with --
    including appearing or disappearing (None). Taken *before* the files are
    read, so a change landing mid-build makes the next request rebuild instead
    of being silently absorbed.
    """
    manifest = _mtime_ns(artifacts.manifest_path(predictions_path()))
    if season is None:
        return (_mtime_ns(predictions_path()), manifest, None, None, None)
    return (
        _mtime_ns(predictions_path()),
        manifest,
        _mtime_ns(market_prices_path(season)),
        _mtime_ns(project_path('data', season, 'teams.csv')),
        _mtime_ns(project_path('data', season, 'fixtures.csv')),
    )


def _is_stale(snapshot: Mapping) -> bool:
    season = snapshot.get('season') or latest_season()
    return source_signature(season) != snapshot.get('signature')


def state() -> Mapping:
    """The current snapshot, rebuilt first if any source file has changed."""
    snapshot = _snapshot
    if snapshot and (_maintenance or not _is_stale(snapshot)):
        return snapshot
    with _state_lock:
        snapshot = _snapshot
        if snapshot and (_maintenance or not _is_stale(snapshot)):
            return snapshot
        return reload_predictions()


_rebuild_failure: str | None = None    # why the last rebuild failed, until one succeeds


def reload_predictions() -> Mapping:
    """Build a new snapshot and install it.

    A file that cannot be read -- half-written, truncated, corrupt -- must not
    take the site down if there is good data already loaded: the previous
    snapshot keeps being served, the failure is logged and raised as the
    `predictions_rebuild_failing` alert, and the next request tries again. With
    nothing loaded yet there is nothing to fall back to, so the snapshot says why.
    """
    global _snapshot, _rebuild_failure
    with _state_lock:
        previous = _snapshot
        try:
            built = _build_snapshot()
        except (OSError, ValueError, KeyError) as exc:   # pandas' parse errors are ValueErrors
            reason = f'{type(exc).__name__}: {exc}'
            if _rebuild_failure != reason:
                obs.log_event(logging.WARNING, 'snapshot_rebuild_failed', error=reason,
                              serving_previous=bool(previous and not previous.get('error')))
            _rebuild_failure = reason
            if previous and not previous.get('error'):
                return previous
            built = {**_empty_snapshot(latest_season()),
                     'error': f'{opt.PREDICTIONS} could not be read ({type(exc).__name__}).'}
        else:
            _rebuild_failure = None
        _snapshot = MappingProxyType(built)
        return _snapshot


def reset_state() -> None:
    global _snapshot
    with _state_lock:
        _snapshot = MappingProxyType({})


@contextlib.contextmanager
def maintenance():
    """Hold readers on the last good snapshot while data files are rewritten.

    fetch_data.py rewrites files in place, so a rebuild that started halfway
    through would read a torn file. While this is active state() keeps serving
    the current snapshot; the first request after it ends sees the new
    signature and rebuilds.
    """
    global _maintenance
    with _state_lock:
        _maintenance += 1
    try:
        yield
    finally:
        with _state_lock:
            _maintenance -= 1


class MarketDataUnavailable(Exception):
    """Live market prices cannot be established, so no price may be shown or used."""


# A market file that prices under half the export is not this season's market.
MIN_MARKET_COVERAGE = 0.5


def join_market_prices(df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Overwrite `value_m` with players_raw.csv's `now_cost` -- the live price.

    predictions_next_gw.csv is a point-in-time export; players_raw.csv is
    refreshed independently and routinely moves after that export was
    written. /api/platform, /api/transfers and chip optimisation all need
    the price a manager would actually pay today, not the price the model
    saw at export time. A player missing from the current market file
    cannot be legally bought at any price, so he is dropped here rather
    than silently priced from the stale export.

    Fails closed: when the market file is missing, unreadable, lacks the
    columns, or covers too little of the export, this raises rather than
    handing back the export's own (possibly weeks-old) prices.
    """
    if df.empty:
        return df
    raw_path = market_prices_path(season)
    shown = os.path.join('data', season, 'players_raw.csv')
    if 'element' not in df.columns:
        raise MarketDataUnavailable(
            'The prediction export has no element IDs, so it cannot be matched to market prices.')
    if not os.path.exists(raw_path):
        raise MarketDataUnavailable(
            f'Market prices are unavailable: {shown} not found. Refresh the season data '
            'before using budgets, transfers or chips.')
    try:
        raw = pd.read_csv(raw_path, usecols=['id', 'now_cost'], low_memory=False)
    except (ValueError, OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise MarketDataUnavailable(
            f'Market prices are unavailable: {shown} is unreadable or lacks id/now_cost '
            f'({type(exc).__name__}).') from exc
    market_price = pd.to_numeric(raw.set_index('id')['now_cost'], errors='coerce') / 10.0
    market_price = market_price[market_price.notna() & (market_price > 0)]
    priced = df['element'].map(market_price)
    if priced.notna().mean() < MIN_MARKET_COVERAGE:
        raise MarketDataUnavailable(
            f'Market prices are unavailable: {shown} prices only '
            f'{int(priced.notna().sum())} of {len(df)} predicted players.')
    df = df.copy()
    df['value_m'] = priced
    return df.dropna(subset=['value_m']).reset_index(drop=True)


def without_prices(df: pd.DataFrame) -> pd.DataFrame:
    """The export with its stale prices blanked, for when there is no market data.

    Every price-dependent route is gated on `market_error`; blanking value_m
    means a route that forgot the gate gets NaN, not last week's number.
    """
    if df.empty or 'value_m' not in df.columns:
        return df
    df = df.copy()
    df['value_m'] = float('nan')
    return df


def local_element_ids() -> set[int]:
    current = state().get('everyone')
    if current is None or 'element' not in current.columns:
        return set()
    return {int(element) for element in current['element'].dropna()}


app.register_blueprint(create_manager_blueprint(manager_client, local_element_ids))


def _empty_snapshot(season: str | None) -> dict:
    return {
        'loaded_at': time.time(),
        'signature': source_signature(season),   # before reading, see source_signature
        'season': season,
        'gameweek': None,
        'error': None,
        'market_error': None,
        'players': pd.DataFrame(),
        'everyone': pd.DataFrame(),
        'future_points': None,
        'future_gameweeks': [],
        'mtime': None,
        'market_mtime': None,
        'artifact': None,
        'model': model_summary(),
    }


def _build_snapshot() -> dict:
    """Read every source file and return a complete snapshot. Touches no globals."""
    path = predictions_path()
    season = latest_season()
    snapshot = _empty_snapshot(season)
    if season is None:
        return {**snapshot, 'error': 'No season directory found under data/.'}
    if not os.path.exists(path):
        _state['error'] = (
            f"{path} not found. Run scripts/predict_gameweek.py first -- "
            f"the site has nothing to show without it."
        )
        _state['players'] = pd.DataFrame()
        _state['everyone'] = pd.DataFrame()
        _state['future_points'] = None
        _state['future_gameweeks'] = []
        return _state

    players = opt.load_predictions(path, drop_unavailable=True)
    everyone = opt.load_predictions(path, drop_unavailable=False)

    season = sorted(
        d for d in os.listdir('data')
        if os.path.isdir(os.path.join('data', d)) and d[:4].isdigit()
    )[-1]
    market_path = market_prices_path(season)
    market_mtime = os.path.getmtime(market_path) if os.path.exists(market_path) else None
    players = join_market_prices(players, season)
    everyone = join_market_prices(everyone, season)

    future_points = None
    future_gameweeks = []
    try:
        horizon_players, horizon_points, future_gameweeks = opt.load_horizon(
            path, drop_unavailable=True)
        identity = 'element' if 'element' in players.columns and 'element' in horizon_players.columns else 'name'
        horizon_points.index = horizon_players[identity].to_list()
        future_points = horizon_points.reindex(players[identity].to_list())
        future_points.index = players.index
    except SystemExit:
        future_gameweeks = []

    teams_path = os.path.join('data', season, 'teams.csv')
    if os.path.exists(teams_path):
        local_teams = set(pd.read_csv(teams_path)['name'].dropna())
        prediction_teams = set(everyone['team'].dropna())
        if local_teams != prediction_teams:
            only_predictions = ', '.join(sorted(prediction_teams - local_teams))
            only_local = ', '.join(sorted(local_teams - prediction_teams))
            _state.update({
                'error': (
                    f'{path} does not match local season {season}. '
                    f'Only in predictions: {only_predictions or "none"}. '
                    f'Only in local data: {only_local or "none"}. '
                    'Refresh the local season data or regenerate predictions.'
                ),
                'players': pd.DataFrame(),
                'everyone': pd.DataFrame(),
                'future_points': None,
                'future_gameweeks': [],
                'season': season,
                'gameweek': opt.infer_next_gameweek(season),
                'mtime': os.path.getmtime(path),
                'market_mtime': market_mtime,
                'model': model_summary(),
            })
            return _state

    _state.update({
        'error': None,
        'players': players,
        'everyone': everyone,
        'future_points': future_points,
        'future_gameweeks': future_gameweeks,
        'market_mtime': market_mtime,
        'season': season,
        'gameweek': opt.infer_next_gameweek(season),
        'mtime': os.path.getmtime(path),
        'model': model_summary(),
    })
    return _state


def model_summary() -> dict:
    """What actually produced these numbers, surfaced rather than assumed."""
    import json
    meta_path = os.path.join('saved_models', 'direct', 'meta.json')
    if not os.path.exists(meta_path):
        meta_path = os.path.join('fpl_results', 'saved_models', 'direct', 'meta.json')
    if not os.path.exists(meta_path):
        return {}
    with open(meta_path, encoding='utf-8') as f:
        meta = json.load(f)
    return {
        pos: {
            'model': v.get('best_model'),
            'features': v.get('features_count'),
            'test_r2': round(v.get('best_test_r2', 0), 4),
        }
        for pos, v in meta.items()
    }


def squad_from_names(names: list) -> pd.DataFrame:
    """Resolve submitted names to squad rows.

    Exact match first. optimise.read_squad_file_names does substring matching,
    which is right for a CLI where someone types "salah", but wrong here: the
    browser sends names picked from a list, and a substring can resolve to a
    different player whose name contains it ("Rodrigo" inside "Rodrigo Gomes").
    Falls back to the CLI resolver only for names that do not match exactly.
    """
    everyone = state()['everyone']
    by_name = {n: i for i, n in zip(everyone.index, everyone['name'])}

    indices, fuzzy = [], []
    for name in names:
        if name in by_name:
            indices.append(by_name[name])
        else:
            fuzzy.append(name)
    if fuzzy:
        indices += opt.read_squad_file_names(fuzzy, everyone)

    if len(set(indices)) != len(indices):
        raise ValueError('the same player appears twice in that squad')
    return everyone.loc[indices]


def squad_from_elements(elements: list[int]) -> pd.DataFrame:
    everyone = state()['everyone']
    if len(elements) != opt.SQUAD_SIZE or len(set(elements)) != opt.SQUAD_SIZE:
        raise ValueError(f'a squad is {opt.SQUAD_SIZE} distinct players; you gave {len(set(elements))}')
    current = everyone[everyone['element'].isin(elements)].copy()
    found = set(current['element'])
    missing = [str(element) for element in elements if element not in found]
    if missing:
        raise ValueError(f"unknown player element(s): {', '.join(missing)}")
    order = {element: position for position, element in enumerate(elements)}
    current['_order'] = current['element'].map(order)
    return current.sort_values('_order').drop(columns='_order').reset_index(drop=True)


def fail(message: str, code: int = 400):
    return jsonify({'ok': False, 'error': message}), code


def unavailable(message: str):
    """503 for anything that needs predictions that have not been generated.

    Distinct from fail()'s 400: the request was fine, the server just has no
    model output to answer it with yet, and the fix is to run the prediction
    pipeline rather than to send something different. A caching layer or a
    client retry should treat the two completely differently.
    """
    return fail(message, 503)


@app.errorhandler(Exception)
def on_error(exc):
    # A stack trace in the terminal, a readable sentence in the browser.
    traceback.print_exc()
    return jsonify({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}), 500


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.route('/api/meta')
def api_meta():
    s = state()
    # Deliberately not gated on predictions. This endpoint describes the models
    # and the season, which are on disk whether or not an export has been
    # generated, and the frontend reads it for the model footnote. Failing here
    # when predictions are missing took down that footnote on every page for a
    # reason that has nothing to do with it.
    mtime = s.get('mtime')
    updated_at = None
    if mtime:
        updated_at = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
    return jsonify({
        'ok': True,
        'predictions_available': not s.get('error'),
        'predictions_error': s.get('error'),
        'season': s.get('season'),
        'gameweek': s.get('gameweek'),
        # players is a DataFrame, so it cannot be truth-tested with `or`.
        'players': 0 if s.get('players') is None else len(s['players']),
        'model': s.get('model') if s.get('model') else model_summary(),
        'budget_default': DEFAULT_BUDGET,
        'squad_size': opt.SQUAD_SIZE,
        'xi_size': opt.XI_SIZE,
        'hit_cost': opt.HIT_COST,
        'predictions_updated_at': updated_at,
    })


@app.route('/api/platform')
def api_platform():
    s = state()
    season = s.get('season') or latest_local_season(Path(ROOT))
    if season is None:
        return fail('no local FPL season data is available')

    snapshot = build_local_snapshot(Path(ROOT), season)
    prediction_available = not bool(s.get('error'))
    if prediction_available:
        predictions = {
            player['element']: player
            for player in enriched_players()
            if player.get('element') is not None
        }
        for player in snapshot['players']:
            prediction = predictions.get(player.get('element'))
            if prediction is None:
                continue
            for key in ('predicted_points', 'points_per_million', 'opponent_team',
                        'was_home', 'has_prior_history'):
                if key in prediction:
                    player[key] = prediction[key]

    mtime = s.get('mtime')
    prediction_timestamp = (
        datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
        if mtime else None
    )

    # players_raw.csv (current market prices, joined into `snapshot['players']`
    # above) and the prediction export are two independent files that can be
    # refreshed at different times. My Team and Transfer Studio need to know
    # when the price they're showing was last observed, and whether the point
    # projections predate a since-changed market.
    raw_path = os.path.join('data', season, 'players_raw.csv')
    market_mtime = os.path.getmtime(raw_path) if os.path.exists(raw_path) else None
    market_prices_updated_at = (
        datetime.datetime.fromtimestamp(market_mtime, tz=datetime.timezone.utc).isoformat()
        if market_mtime else None
    )
    predictions_older_than_market = bool(
        prediction_available and mtime and market_mtime and mtime < market_mtime
    )

    snapshot.update({
        'ok': True,
        'prediction_available': prediction_available,
        'prediction_error': s.get('error'),
        'prediction_timestamp': prediction_timestamp,
        'model': s.get('model') or model_summary(),
        'market_prices_updated_at': market_prices_updated_at,
        'predictions_older_than_market': predictions_older_than_market,
    })
    return jsonify(snapshot)


# Fields worth showing next to a prediction. Everything here comes from
# players_raw.csv, which is FPL's own bootstrap payload as scraped.
PROFILE_NUMERIC = [
    'form', 'points_per_game', 'total_points', 'minutes', 'starts',
    'goals_scored', 'assists', 'clean_sheets', 'bonus', 'bps', 'ict_index',
    'expected_goals', 'expected_assists', 'expected_goal_involvements',
    'expected_goals_per_90', 'expected_assists_per_90', 'starts_per_90',
    'saves', 'goals_conceded', 'yellow_cards', 'red_cards',
    'chance_of_playing_next_round', 'transfers_in_event', 'transfers_out_event',
]
PROFILE_TEXT = [
    'news', 'birth_date', 'team_join_date', 'squad_number', 'photo',
    'first_name', 'second_name', 'web_name',
]

# England, Scotland and Wales are ISO subdivisions, not countries, so their
# flags are the tag sequences rather than regional-indicator pairs.
SUBDIVISION_FLAGS = {
    'EN': '\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F',
    'SC': '\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F',
    'WA': '\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F',
}


def flag_for(iso: str | None) -> str:
    """ISO 3166-1 alpha-2 to a flag emoji."""
    if not iso or len(iso) != 2 or not iso.isalpha():
        return ''
    iso = iso.upper()
    if iso in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[iso]
    return chr(0x1F1E6 + ord(iso[0]) - 65) + chr(0x1F1E6 + ord(iso[1]) - 65)


def load_regions() -> dict:
    import json
    path = os.path.join('data', 'fpl_regions.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def enriched_players() -> list:
    """Predictions joined to FPL's own player metadata.

    Joins on `element`, the FPL player id, rather than on the display name.
    Names are not unique or stable across the season -- two players can share a
    web_name and FPL renames them when that happens -- and a mis-joined row
    would attach the wrong photo and the wrong stats to a prediction.
    """
    s = state()
    base = opt.squad_records(s['everyone'])

    raw_path = os.path.join('data', s['season'], 'players_raw.csv')
    if not os.path.exists(raw_path):
        return base

    raw = pd.read_csv(raw_path, low_memory=False)
    regions = load_regions()
    team_rows = {
        int(row['id']): row['short_name']
        for row in pd.read_csv(os.path.join('data', s['season'], 'teams.csv')).to_dict('records')
    }

    keep = ['id'] + [c for c in PROFILE_NUMERIC + PROFILE_TEXT if c in raw.columns]
    if 'region' in raw.columns:
        keep.append('region')
    if 'code' in raw.columns:
        keep.append('code')
    for column in ('team', 'team_code'):
        if column in raw.columns:
            keep.append(column)
    profile = raw[keep].set_index('id')

    has_element = bool(base) and 'element' in base[0]
    if not has_element:
        # Predictions written before element was carried through. Fall back to
        # the name join and say so rather than silently showing no stats.
        by_name = {}
        if {'first_name', 'second_name'} <= set(raw.columns):
            full = (raw['first_name'].astype(str) + ' ' + raw['second_name'].astype(str))
            by_name = dict(zip(full, raw['id']))

    out = []
    for record in base:
        pid = record.get('element')
        if pid is None and not has_element:
            pid = by_name.get(record.get('name'))
        row = profile.loc[pid].to_dict() if pid in profile.index else {}

        for key in PROFILE_NUMERIC:
            value = row.get(key)
            record[key] = None if value is None or pd.isna(value) else float(value)
        for key in ('news', 'birth_date', 'team_join_date', 'first_name',
                    'second_name', 'web_name'):
            value = row.get(key)
            record[key] = None if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)

        code = row.get('code')
        code = None if code is None or pd.isna(code) else int(code)
        record['photo'] = photo_url(code)
        record['photo_large'] = photo_url(code, '500x500')

        team_id = row.get('team')
        record['team_id'] = None if team_id is None or pd.isna(team_id) else int(team_id)
        team_code = row.get('team_code')
        record['team_code'] = None if team_code is None or pd.isna(team_code) else int(team_code)
        record['team_short'] = team_rows.get(record['team_id'])

        region = row.get('region')
        meta = regions.get(str(int(region))) if region is not None and not pd.isna(region) else None
        record['country'] = meta['name'] if meta else None
        record['flag'] = flag_for(meta.get('iso') if meta else None)
        out.append(record)
    return out


def enriched_squad_records(frame: pd.DataFrame) -> list:
    records = opt.squad_records(frame)
    by_element = {
        player['element']: player
        for player in enriched_players()
        if player.get('element') is not None
    }
    return [
        {**record, **by_element.get(record.get('element'), {})}
        for record in records
    ]


@app.route('/api/players')
def api_players():
    """Everyone, for the pickers. Includes the unavailable, flagged as such."""
    s = state()
    if s.get('error'):
        return unavailable(s['error'])
    return jsonify({'ok': True, 'players': enriched_players()})


@app.route('/api/squad', methods=['POST'])
def api_squad():
    s = state()
    if s.get('error'):
        return unavailable(s['error'])

    body = request.get_json(force=True) or {}
    try:
        budget = float(body.get('budget', DEFAULT_BUDGET))
    except (TypeError, ValueError):
        return fail('budget must be a number')
    if not 20 <= budget <= 200:
        return fail('budget must be between 20.0m and 200.0m')

    players = s['players']
    lock = [n for n in body.get('lock', []) if n]
    ban = [n for n in body.get('ban', []) if n]

    # solve_squad takes row indices, so names are resolved here rather than
    # filtering the frame -- dropping banned rows would renumber the index the
    # locked list refers to.
    lock_idx, ban_idx = [], []
    if lock:
        matched = players[players['name'].isin(lock)]
        missing = sorted(set(lock) - set(matched['name']))
        if missing:
            return fail(f"could not lock (not in the prediction set, or "
                        f"unavailable): {', '.join(missing)}")
        if len(matched) > opt.SQUAD_SIZE:
            return fail(f'cannot lock more than {opt.SQUAD_SIZE} players')
        lock_idx = list(matched.index)
    if ban:
        ban_idx = list(players[players['name'].isin(ban)].index)
        if set(lock) & set(ban):
            return fail(f"cannot both lock and exclude: "
                        f"{', '.join(sorted(set(lock) & set(ban)))}")

    result, status = opt.solve_squad(players, budget,
                                     locked=lock_idx or None,
                                     banned=ban_idx or None)
    if result is None:
        return fail(f'no legal squad at £{budget:.1f}m ({status}). '
                    f'Try raising the budget or removing some locks.')

    return jsonify(lineup_response(result, budget))


def lineup_response(result: dict, budget: float) -> dict:
    """Serialize a solved squad with its complete matchday lineup."""
    payload = opt.lineup_payload(result, budget)
    payload['xi'] = enriched_squad_records(result['xi'])
    payload['bench'] = enriched_squad_records(result['bench'])
    for key in ('captain', 'vice_captain'):
        selected = result.get(key)
        payload[key] = (None if selected is None else
                        enriched_squad_records(pd.DataFrame([selected]))[0])
    return payload


@app.route('/api/lineup', methods=['POST'])
def api_lineup():
    """Choose XI, bench order, captain and vice from an owned 15."""
    s = state()
    if s.get('error'):
        return unavailable(s['error'])

    body = request.get_json(force=True) or {}
    elements = [element for element in body.get('elements', []) if element is not None]
    names = [name for name in body.get('squad', []) if name]
    if elements:
        if len(elements) != opt.SQUAD_SIZE or len(set(elements)) != opt.SQUAD_SIZE:
            return fail(f'a squad is {opt.SQUAD_SIZE} distinct players; you gave {len(set(elements))}')
        everyone = s['everyone']
        current = everyone[everyone['element'].isin(elements)].copy()
        if len(current) != opt.SQUAD_SIZE:
            found = set(current['element'])
            missing = [str(element) for element in elements if element not in found]
            return fail(f"unknown player element(s): {', '.join(missing)}")
        order = {element: position for position, element in enumerate(elements)}
        current['_order'] = current['element'].map(order)
        current = current.sort_values('_order').drop(columns='_order').reset_index(drop=True)
    else:
        if len(names) != opt.SQUAD_SIZE:
            return fail(f'a squad is {opt.SQUAD_SIZE} players; you gave {len(names)}')
        try:
            current = squad_from_names(names).reset_index(drop=True)
        except (ValueError, KeyError) as exc:
            return fail(str(exc))

    budget = float(current['value_m'].sum())
    result, status = opt.solve_squad(current, budget)
    if result is None:
        return fail(f'the supplied 15 is not a legal FPL squad ({status})')
    return jsonify(lineup_response(result, budget))


@app.route('/api/transfers', methods=['POST'])
def api_transfers():
    s = state()
    if s.get('error'):
        return unavailable(s['error'])

    body = request.get_json(force=True) or {}
    raw_elements = body.get('elements')
    if not isinstance(raw_elements, list) or any(
            isinstance(element, bool) or not isinstance(element, int)
            for element in raw_elements):
        return fail('elements must be a list of numeric FPL element IDs')
    try:
        if len(raw_elements) != opt.SQUAD_SIZE or len(set(raw_elements)) != opt.SQUAD_SIZE:
            return fail('elements must contain 15 distinct numeric FPL element IDs')
        current = squad_from_elements(raw_elements)
    except (ValueError, KeyError) as exc:
        return fail(str(exc))

    try:
        free = int(body.get('free', 1))
        bank = float(body.get('bank', 0.0))
        max_transfers = int(body.get('max', 3))
    except (TypeError, ValueError):
        return fail('free, bank and max must be numbers')
    if not 0 <= max_transfers <= 5:
        return fail('max transfers must be between 0 and 5')
    if not 0 <= free <= 5:
        return fail('free transfers must be between 0 and 5')
    if not 0 <= bank <= 100:
        return fail('bank must be between 0.0m and 100.0m')

    # Optional, but when present must price every owned element -- a partial
    # map would silently fall back to market value for whichever players it
    # left out, understating what selling them actually returns.
    raw_selling_prices = body.get('selling_prices_tenths')
    selling_prices = None
    if raw_selling_prices is not None:
        if not isinstance(raw_selling_prices, dict):
            return fail('selling_prices_tenths must be an object of element ID to tenths of a million')
        try:
            parsed = {int(key): value for key, value in raw_selling_prices.items()}
        except (TypeError, ValueError):
            return fail('selling_prices_tenths keys must be numeric FPL element IDs')
        if any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0
                for value in parsed.values()):
            return fail('selling_prices_tenths values must be finite nonnegative numbers')
        if set(parsed.keys()) != set(raw_elements):
            return fail('selling_prices_tenths must have exactly one entry per owned element')
        selling_prices = {element: tenths / 10.0 for element, tenths in parsed.items()}

    try:
        data = opt.compute_transfers(
            current, s['players'], free, bank, max_transfers,
            selling_prices=selling_prices)
    except ValueError as exc:
        return fail(str(exc))
    data['ok'] = True
    return jsonify(data)


@app.route('/api/chips', methods=['POST'])
def api_chips():
    s = state()
    if s.get('error'):
        return unavailable(s['error'])

    body = request.get_json(force=True) or {}
    names = [n for n in body.get('squad', []) if n]
    squad = None
    if names:
        if len(names) != opt.SQUAD_SIZE:
            return fail(f'a squad is {opt.SQUAD_SIZE} players; you gave {len(names)}')
        try:
            squad = squad_from_names(names)
        except (ValueError, KeyError) as exc:
            return fail(str(exc))

    try:
        horizon = int(body.get('horizon', 8))
    except (TypeError, ValueError):
        return fail('horizon must be a number')
    if not 1 <= horizon <= 38:
        return fail('horizon must be between 1 and 38 gameweeks')

    inventory = body.get('chip_inventory')
    scheduled = body.get('scheduled_gameweeks', [])
    if scheduled is None:
        scheduled = []
    if not isinstance(scheduled, list) or any(
            not isinstance(gameweek, (int, float)) for gameweek in scheduled):
        return fail('scheduled_gameweeks must be a list of numbers')
    try:
        last_free_hit = body.get('last_free_hit_gameweek')
        if last_free_hit is not None:
            last_free_hit = int(last_free_hit)
    except (TypeError, ValueError):
        return fail('last_free_hit_gameweek must be a number')

    try:
        raw_bank = body.get('bank')
        bank = None if raw_bank is None else float(raw_bank)
    except (TypeError, ValueError):
        return fail('bank must be a number')
    if bank is not None and not 0 <= bank <= 100:
        return fail('bank must be between 0.0m and 100.0m')

    # Free Hit / Wildcard candidate squads are priced from real ownership
    # cost when it's available, same as /api/transfers; a squad request has
    # no elements to key this against, so it's only accepted alongside one.
    raw_selling_prices = body.get('selling_prices_tenths')
    selling_prices = None
    if raw_selling_prices is not None:
        if not isinstance(raw_selling_prices, dict):
            return fail('selling_prices_tenths must be an object of element ID to tenths of a million')
        try:
            parsed = {int(key): value for key, value in raw_selling_prices.items()}
        except (TypeError, ValueError):
            return fail('selling_prices_tenths keys must be numeric FPL element IDs')
        if any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0
                for value in parsed.values()):
            return fail('selling_prices_tenths values must be finite nonnegative numbers')
        if squad is None or 'element' not in squad.columns:
            return fail('selling_prices_tenths requires a 15-player squad in this request')
        if set(parsed.keys()) != {int(element) for element in squad['element']}:
            return fail('selling_prices_tenths must have exactly one entry per owned element')
        selling_prices = {element: tenths / 10.0 for element, tenths in parsed.items()}

    data = opt.compute_chips(
        squad, s['season'], s['gameweek'], horizon, s['players'],
        inventory=inventory,
        scheduled_gameweeks=[int(gameweek) for gameweek in scheduled],
        last_free_hit_gameweek=last_free_hit,
        future_points=s.get('future_points'),
        projection_generated_at=(
            datetime.datetime.fromtimestamp(s['mtime'], tz=datetime.timezone.utc).isoformat()
            if s.get('mtime') else None
        ),
        bank=bank,
        selling_prices=selling_prices,
    )
    data['ok'] = True
    return jsonify(data)


@app.route('/api/watchlist')
def api_watchlist():
    s = state()
    if s.get('error'):
        return unavailable(s['error'])
    try:
        max_ownership = float(request.args.get('max_ownership', 10))
        top = int(request.args.get('top', 12))
    except (TypeError, ValueError):
        return fail('max_ownership and top must be numbers')

    data = opt.compute_watchlist(s['players'], max_ownership, top)
    data['ok'] = True
    return jsonify(data)


@app.route('/api/reload', methods=['POST'])
def api_reload():
    _state.clear()
    s = state()
    if s.get('error'):
        return unavailable(s['error'])
    return jsonify({'ok': True, 'players': len(s['players']),
                    'gameweek': s['gameweek']})


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    s = state()
    season = s.get('season') or latest_local_season(Path(ROOT))
    if not season:
        return fail('No local season configured.')

    try:
        # olbauday, and forced. vaastav is the archive of finished seasons and
        # does not carry one in progress, so the default source refreshed a
        # live season from a repository that has nothing to say about it. And
        # without --force every file that already exists is skipped, which for
        # a season already on disk is every file: the button refreshed nothing
        # and reported success. A forced olbauday pull takes about 26 seconds.
        res = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'scripts', 'fetch_data.py'),
             '--season', season, '--source', 'olbauday', '--force'],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        _state.clear()
        new_state = state()
        if new_state.get('error'):
            return jsonify({'ok': False, 'error': new_state['error'], 'output': res.stdout}), 500
        # A refresh moves the data and leaves the predictions where they
        # were. Running the model is minutes of work and does not belong in a
        # request, so say so rather than serving numbers built on last week's
        # squad prices and availability as though they were current.
        players_raw = os.path.join(ROOT, 'data', season, 'players_raw.csv')
        predictions_stale = (
            os.path.exists(players_raw) and new_state.get('mtime') is not None
            and os.path.getmtime(players_raw) > new_state['mtime'])
        message = f'Season {season} data refreshed successfully.'
        if predictions_stale:
            message += (' The predictions are now older than the data -- '
                        'rerun scripts/predict_gameweek.py to match them.')
        return jsonify({
            'ok': True,
            'message': message,
            'predictions_stale': predictions_stale,
            'season': new_state['season'],
            'gameweek': new_state['gameweek'],
            'players': len(new_state['players']),
        })
    except Exception as exc:
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/api/player/<int:element_id>/history')
def api_player_history(element_id: int):
    s = state()
    season = s.get('season') or latest_local_season(Path(ROOT)) or '2026-27'
    history = player_history(Path(ROOT), season, element_id)
    return jsonify({'ok': True, 'history': history})



if __name__ == '__main__':
    s = state()
    print('=' * 70)
    print('FPL Assistant')
    print('=' * 70)
    if s.get('error'):
        print(f'\n  WARNING: {s["error"]}\n')
    else:
        print(f'  season {s["season"]}, GW{s["gameweek"]}, '
              f'{len(s["players"]):,} available players')
        for pos, info in (s.get('model') or {}).items():
            print(f'    {pos:<4} {info["model"]:<12} {info["features"]:>3} features'
                  f'   test R2 {info["test_r2"]}')
    port = int(os.environ.get('PORT', 5000))
    print(f'\n  http://127.0.0.1:{port}\n')
    app.run(debug=False, port=port)
