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
        return {**snapshot, 'error': (
            f"{opt.PREDICTIONS} not found. Run scripts/predict_gameweek.py first -- "
            f"the site has nothing to show without it.")}

    market_path = market_prices_path(season)
    snapshot['mtime'] = os.path.getmtime(path)
    snapshot['market_mtime'] = os.path.getmtime(market_path) if os.path.exists(market_path) else None
    snapshot['artifact'] = artifacts.describe(path)
    try:
        snapshot['gameweek'] = opt.infer_next_gameweek(season, root=ROOT)
    except (OSError, ValueError, KeyError):
        return {**snapshot, 'error': f'Fixture data for {season} is missing or unreadable.'}

    try:
        players = opt.load_predictions(path, drop_unavailable=True)
        everyone = opt.load_predictions(path, drop_unavailable=False)
    except SystemExit as exc:
        return {**snapshot, 'error': f'{opt.PREDICTIONS} is unusable: {exc.code}'}

    market_error = None
    try:
        players = join_market_prices(players, season)
        everyone = join_market_prices(everyone, season)
    except MarketDataUnavailable as exc:
        market_error = str(exc)
        players = without_prices(players)
        everyone = without_prices(everyone)
    snapshot['market_error'] = market_error

    teams_path = project_path('data', season, 'teams.csv')
    if os.path.exists(teams_path):
        local_teams = set(pd.read_csv(teams_path)['name'].dropna())
        prediction_teams = set(everyone['team'].dropna())
        if local_teams != prediction_teams:
            only_predictions = ', '.join(sorted(prediction_teams - local_teams))
            only_local = ', '.join(sorted(local_teams - prediction_teams))
            return {**snapshot, 'error': (
                f'{opt.PREDICTIONS} does not match local season {season}. '
                f'Only in predictions: {only_predictions or "none"}. '
                f'Only in local data: {only_local or "none"}. '
                'Refresh the local season data or regenerate predictions.')}

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

    return {**snapshot, 'players': players, 'everyone': everyone,
            'future_points': future_points, 'future_gameweeks': future_gameweeks}


def model_summary() -> dict:
    """What actually produced these numbers, surfaced rather than assumed."""
    import json
    meta_path = project_path('saved_models', 'direct', 'meta.json')
    if not os.path.exists(meta_path):
        meta_path = project_path('fpl_results', 'saved_models', 'direct', 'meta.json')
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


def squad_from_names(names: list, snapshot: Mapping | None = None) -> pd.DataFrame:
    """Resolve submitted names to squad rows.

    Exact match first. optimise.read_squad_file_names does substring matching,
    which is right for a CLI where someone types "salah", but wrong here: the
    browser sends names picked from a list, and a substring can resolve to a
    different player whose name contains it ("Rodrigo" inside "Rodrigo Gomes").
    Falls back to the CLI resolver only for names that do not match exactly.
    """
    everyone = (snapshot if snapshot is not None else state())['everyone']
    by_name = {n: i for i, n in zip(everyone.index, everyone['name'])}

    indices, fuzzy = [], []
    for name in names:
        if name in by_name:
            indices.append(by_name[name])
        else:
            fuzzy.append(name)
    if fuzzy:
        try:
            indices += opt.read_squad_file_names(fuzzy, everyone)
        except SystemExit as exc:
            # The CLI resolver exits the process on a miss; here it is a bad request.
            raise RequestError(str(exc.code), 'unknown_player', 'squad') from None

    if len(set(indices)) != len(indices):
        raise RequestError('the same player appears twice in that squad', 'invalid_squad')
    return everyone.loc[indices]


def squad_from_elements(elements: list[int], snapshot: Mapping | None = None) -> pd.DataFrame:
    everyone = (snapshot if snapshot is not None else state())['everyone']
    if len(elements) != opt.SQUAD_SIZE or len(set(elements)) != opt.SQUAD_SIZE:
        raise RequestError(
            f'a squad is {opt.SQUAD_SIZE} distinct players; you gave {len(set(elements))}',
            'invalid_squad', 'elements')
    current = everyone[everyone['element'].isin(elements)].copy()
    found = set(current['element'])
    missing = [str(element) for element in elements if element not in found]
    if missing:
        raise RequestError(f"unknown player element(s): {', '.join(missing)}",
                           'unknown_player', 'elements')
    order = {element: position for position, element in enumerate(elements)}
    current['_order'] = current['element'].map(order)
    return current.sort_values('_order').drop(columns='_order').reset_index(drop=True)


def fail(message: str, status: int = 400, code: str = 'invalid_request', **extra):
    return jsonify({'ok': False, 'error': message, 'code': code, **extra}), status


def unavailable(message: str, code: str = 'predictions_unavailable'):
    """503 for anything that needs data the server does not have.

    Distinct from fail()'s 400: the request was fine, the server just has no
    model output (or market prices) to answer it with, and the fix is to run
    the pipeline rather than to send something different. A caching layer or a
    client retry should treat the two completely differently.
    """
    return fail(message, 503, code)


def data_gate(s: dict):
    """The 503 to return when the data behind a price-dependent route is unusable."""
    if s.get('error'):
        return unavailable(s['error'])
    if s.get('market_error'):
        return unavailable(s['market_error'], 'market_prices_unavailable')
    return None


@app.errorhandler(RequestError)
def on_request_error(exc: RequestError):
    g.error_code = exc.code
    return jsonify(exc.body()), exc.status


_HTTP_CODES = {404: 'not_found', 405: 'method_not_allowed', 413: 'payload_too_large'}


@app.errorhandler(HTTPException)
def on_http_error(exc: HTTPException):
    # Werkzeug's own 404/405/413 are the client's mistake, not a server fault.
    status = exc.code or 500
    return jsonify({'ok': False, 'error': exc.description or exc.name,
                    'code': _HTTP_CODES.get(status, 'http_error')}), status


@app.errorhandler(Exception)
def on_error(exc):
    # The stack trace goes to the log; the caller gets no internals.
    g.error_code = 'internal_error'
    obs.log_event(logging.ERROR, 'unhandled_exception', request_id=g.get('request_id'),
                  method=request.method, path=request.path, exc_type=type(exc).__name__,
                  error=str(exc), traceback=traceback.format_exc())
    return jsonify({'ok': False, 'error': 'Internal server error.',
                    'code': 'internal_error'}), 500


@app.before_request
def start_request():
    g.request_id = obs.request_id_from(request.headers.get('X-Request-ID'))
    g.started = time.perf_counter()


def _quiet_route() -> bool:
    return request.path.startswith('/api/health/') or request.path == '/api/metrics'


@app.after_request
def log_request(response):
    started = g.get('started')
    if started is not None:
        seconds = time.perf_counter() - started
        route = request.url_rule.rule if request.url_rule else 'unmatched'
        request_metrics.observe(route, request.method, response.status_code, seconds)
        response.headers['X-Request-ID'] = g.request_id
        level = logging.DEBUG if _quiet_route() else (
            logging.ERROR if response.status_code >= 500 else
            logging.WARNING if response.status_code >= 400 else logging.INFO)
        fields = {
            'request_id': g.request_id, 'method': request.method, 'path': request.path,
            'route': route, 'status': response.status_code,
            'duration_ms': round(seconds * 1000, 2), 'remote_addr': request.remote_addr,
            'bytes': response.calculate_content_length(),
        }
        if g.get('error_code'):
            fields['error_code'] = g.error_code
        obs.log_event(level, 'request', **fields)
    return response


@app.after_request
def stamp_contract(response):
    """Version every /api response, in a header and, for JSON objects, the body."""
    if not request.path.startswith('/api/'):
        return response
    response.headers['X-API-Contract-Version'] = str(API_CONTRACT_VERSION)
    if response.mimetype == 'application/json' and not response.direct_passthrough:
        try:
            payload = json.loads(response.get_data(as_text=True))
        except ValueError:
            return response
        if isinstance(payload, dict) and 'api_contract_version' not in payload:
            payload['api_contract_version'] = API_CONTRACT_VERSION
            response.set_data(json.dumps(payload) + '\n')
    return response


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def public_artifact(artifact) -> dict | None:
    """Which prediction artifact is being served, and which models made it."""
    if not artifact:
        return None
    return {key: artifact.get(key) for key in (
        'artifact', 'sha256', 'manifest_status', 'generated_at', 'season', 'horizon',
        'first_gw', 'last_gw', 'model_bundle', 'code_commit')}


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
        'market_prices_available': not s.get('market_error'),
        'market_prices_error': s.get('market_error'),
        'artifact': public_artifact(s.get('artifact')),
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


_platform_cache: tuple | None = None    # (key, payload)


@app.route('/api/platform')
def api_platform():
    global _platform_cache
    s = state()
    season = s.get('season') or latest_local_season(Path(ROOT))
    if season is None:
        return fail('no local FPL season data is available', 503, 'no_season')

    # Assembling this reads three CSVs and joins ~800 players, and every page
    # asks for it. The result only changes when a source file or the loaded
    # predictions do, so it is keyed on their modification times. While a
    # refresh is rewriting files the last good payload is served as-is.
    key = (season, s.get('loaded_at'),
           _mtime_ns(project_path('data', season, 'teams.csv')),
           _mtime_ns(project_path('data', season, 'fixtures.csv')),
           _mtime_ns(market_prices_path(season)),
           _mtime_ns(project_path('data', 'fpl_regions.json')))
    cached = _platform_cache
    if cached is not None and (cached[0] == key or _maintenance):
        return jsonify(cached[1])

    snapshot = build_local_snapshot(Path(ROOT), season)
    prediction_available = not bool(s.get('error'))
    if prediction_available:
        predictions = {
            player['element']: player
            for player in enriched_players(s)
            if player.get('element') is not None
        }
        for player in snapshot['players']:
            prediction = predictions.get(player.get('element'))
            if prediction is None:
                continue
            for key_name in ('predicted_points', 'points_per_million', 'opponent_team',
                             'was_home', 'has_prior_history'):
                if key_name in prediction:
                    player[key_name] = prediction[key_name]

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
    market_mtime = s.get('market_mtime')
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
        'market_prices_available': not s.get('market_error') and market_mtime is not None,
        'market_prices_error': s.get('market_error'),
        'market_prices_updated_at': market_prices_updated_at,
        'predictions_older_than_market': predictions_older_than_market,
    })
    _platform_cache = (key, snapshot)
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
    path = project_path('data', 'fpl_regions.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


_enriched_cache: tuple | None = None    # (snapshot, file signature, records)


def enriched_players(snapshot: Mapping | None = None) -> list:
    """enriched records for a snapshot, computed once per snapshot and data files.

    Building them reads players_raw.csv and joins ~800 rows, and one request can
    ask several times (XI, bench, captain, vice). The list is shared: read only.
    """
    global _enriched_cache
    s = snapshot if snapshot is not None else state()
    signature = (_mtime_ns(project_path('data', s['season'], 'players_raw.csv')) if s.get('season') else None,
                 _mtime_ns(project_path('data', s['season'], 'teams.csv')) if s.get('season') else None,
                 _mtime_ns(project_path('data', 'fpl_regions.json')))
    cached = _enriched_cache
    if cached is not None and cached[0] is s and cached[1] == signature:
        return cached[2]
    records = _build_enriched(s)
    _enriched_cache = (s, signature, records)
    return records


def _build_enriched(s: Mapping) -> list:
    """Predictions joined to FPL's own player metadata.

    Joins on `element`, the FPL player id, rather than on the display name.
    Names are not unique or stable across the season -- two players can share a
    web_name and FPL renames them when that happens -- and a mis-joined row
    would attach the wrong photo and the wrong stats to a prediction.
    """
    base = opt.squad_records(s['everyone'])

    raw_path = project_path('data', s['season'], 'players_raw.csv')
    if not os.path.exists(raw_path):
        return base

    raw = pd.read_csv(raw_path, low_memory=False)
    regions = load_regions()
    team_rows = {
        int(row['id']): row['short_name']
        for row in pd.read_csv(project_path('data', s['season'], 'teams.csv')).to_dict('records')
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


def enriched_squad_records(frame: pd.DataFrame, snapshot: Mapping | None = None) -> list:
    records = opt.squad_records(frame)
    by_element = {
        player['element']: player
        for player in enriched_players(snapshot)
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
    if gate := data_gate(s):
        return gate
    return jsonify({'ok': True, 'players': enriched_players(s)})


@app.route('/api/squad', methods=['POST'])
def api_squad():
    s = state()
    if gate := data_gate(s):
        return gate

    body = contracts.read_json_object(request)
    budget = contracts.number(body, 'budget', DEFAULT_BUDGET, lo=20, hi=200,
                              range_message='budget must be between 20.0m and 200.0m')

    players = s['players']
    lock = contracts.name_list(body, 'lock')
    ban = contracts.name_list(body, 'ban')

    # solve_squad takes row indices, so names are resolved here rather than
    # filtering the frame -- dropping banned rows would renumber the index the
    # locked list refers to.
    lock_idx, ban_idx = [], []
    if lock:
        matched = players[players['name'].isin(lock)]
        missing = sorted(set(lock) - set(matched['name']))
        if missing:
            return fail(f"could not lock (not in the prediction set, or "
                        f"unavailable): {', '.join(missing)}", code='unknown_player')
        if len(matched) > opt.SQUAD_SIZE:
            return fail(f'cannot lock more than {opt.SQUAD_SIZE} players', code='invalid_squad')
        lock_idx = list(matched.index)
    if ban:
        ban_idx = list(players[players['name'].isin(ban)].index)
        if set(lock) & set(ban):
            return fail(f"cannot both lock and exclude: "
                        f"{', '.join(sorted(set(lock) & set(ban)))}", code='invalid_squad')

    result, status = opt.solve_squad(players, budget,
                                     locked=lock_idx or None,
                                     banned=ban_idx or None)
    if result is None:
        return fail(f'no legal squad at £{budget:.1f}m ({status}). '
                    f'Try raising the budget or removing some locks.', code='invalid_squad')

    return jsonify(lineup_response(result, budget, s))


def lineup_response(result: dict, budget: float, snapshot: Mapping | None = None) -> dict:
    """Serialize a solved squad with its complete matchday lineup."""
    payload = opt.lineup_payload(result, budget)
    payload['xi'] = enriched_squad_records(result['xi'], snapshot)
    payload['bench'] = enriched_squad_records(result['bench'], snapshot)
    for key in ('captain', 'vice_captain'):
        selected = result.get(key)
        payload[key] = (None if selected is None else
                        enriched_squad_records(pd.DataFrame([selected]), snapshot)[0])
    return payload


@app.route('/api/lineup', methods=['POST'])
def api_lineup():
    """Choose XI, bench order, captain and vice from an owned 15."""
    s = state()
    if gate := data_gate(s):
        return gate

    body = contracts.read_json_object(request)
    elements = contracts.int_list(
        body, 'elements', message='elements must be a list of numeric FPL element IDs')
    names = contracts.name_list(body, 'squad')
    if elements:
        current = squad_from_elements(elements, s)
    else:
        if len(names) != opt.SQUAD_SIZE:
            return fail(f'a squad is {opt.SQUAD_SIZE} players; you gave {len(names)}',
                        code='invalid_squad')
        try:
            current = squad_from_names(names, s).reset_index(drop=True)
        except (ValueError, KeyError) as exc:
            return fail(str(exc), code='invalid_squad')

    budget = float(current['value_m'].sum())
    result, status = opt.solve_squad(current, budget)
    if result is None:
        return fail(f'the supplied 15 is not a legal FPL squad ({status})', code='invalid_squad')
    return jsonify(lineup_response(result, budget, s))


@app.route('/api/transfers', methods=['POST'])
def api_transfers():
    s = state()
    if gate := data_gate(s):
        return gate

    body = contracts.read_json_object(request)
    raw_elements = contracts.int_list(
        body, 'elements', required=True,
        message='elements must be a list of numeric FPL element IDs')
    if len(raw_elements) != opt.SQUAD_SIZE or len(set(raw_elements)) != opt.SQUAD_SIZE:
        return fail('elements must contain 15 distinct numeric FPL element IDs',
                    code='invalid_squad', field='elements')
    current = squad_from_elements(raw_elements, s)

    free = contracts.number(body, 'free', 1, lo=0, hi=5, integer=True,
                            range_message='free transfers must be between 0 and 5')
    bank = contracts.number(body, 'bank', 0.0, lo=0, hi=100,
                            range_message='bank must be between 0.0m and 100.0m')
    max_transfers = contracts.number(body, 'max', 3, lo=0, hi=5, integer=True,
                                     range_message='max transfers must be between 0 and 5')

    # Optional, but when present must price every owned element -- a partial
    # map would silently fall back to market value for whichever players it
    # left out, understating what selling them actually returns.
    selling_prices = contracts.selling_prices(body, set(raw_elements))

    try:
        data = opt.compute_transfers(
            current, s['players'], free, bank, max_transfers,
            selling_prices=selling_prices)
    except ValueError as exc:
        return fail(str(exc), code='invalid_squad')
    data['ok'] = True
    return jsonify(data)


@app.route('/api/chips', methods=['POST'])
def api_chips():
    s = state()
    if gate := data_gate(s):
        return gate

    body = contracts.read_json_object(request)
    names = contracts.name_list(body, 'squad')
    squad = None
    if names:
        if len(names) != opt.SQUAD_SIZE:
            return fail(f'a squad is {opt.SQUAD_SIZE} players; you gave {len(names)}',
                        code='invalid_squad')
        try:
            squad = squad_from_names(names, s)
        except (ValueError, KeyError) as exc:
            return fail(str(exc), code='invalid_squad')

    horizon = contracts.number(body, 'horizon', 8, lo=1, hi=38, integer=True,
                               range_message='horizon must be between 1 and 38 gameweeks')
    inventory = contracts.chip_inventory(body)
    scheduled = contracts.int_list(
        body, 'scheduled_gameweeks', maximum=38,
        message='scheduled_gameweeks must be a list of gameweek numbers (1-38)') or []
    last_free_hit = contracts.number(body, 'last_free_hit_gameweek', None,
                                     lo=1, hi=38, integer=True)
    bank = contracts.number(body, 'bank', None, lo=0, hi=100,
                            range_message='bank must be between 0.0m and 100.0m')

    # Free Hit / Wildcard candidate squads are priced from real ownership
    # cost when it's available, same as /api/transfers; a squad request has
    # no elements to key this against, so it's only accepted alongside one.
    owned = (None if squad is None or 'element' not in squad.columns
             else {int(element) for element in squad['element']})
    selling_prices = contracts.selling_prices(body, owned)

    data = opt.compute_chips(
        squad, s['season'], s['gameweek'], horizon, s['players'],
        inventory=inventory,
        scheduled_gameweeks=scheduled,
        last_free_hit_gameweek=last_free_hit,
        future_points=s.get('future_points'),
        projection_generated_at=(
            datetime.datetime.fromtimestamp(s['mtime'], tz=datetime.timezone.utc).isoformat()
            if s.get('mtime') else None
        ),
        bank=bank,
        selling_prices=selling_prices,
        root=ROOT,
    )
    data['ok'] = True
    return jsonify(data)


@app.route('/api/watchlist')
def api_watchlist():
    s = state()
    if gate := data_gate(s):
        return gate
    max_ownership = contracts.query_number(request.args, 'max_ownership', 10, lo=0, hi=100)
    top = contracts.query_number(request.args, 'top', 12, lo=1, hi=200, integer=True)

    data = opt.compute_watchlist(s['players'], max_ownership, top)
    data['ok'] = True
    return jsonify(data)


class Cooldown:
    """Minimum gap between attempts to hit the upstream data sources.

    Every refresh is a forced pull of ~40 files from a public repository, so a
    stuck client or an impatient double-click must not be able to hammer it.
    A failed attempt cools down for less time than a successful one: the person
    should be able to retry a transient error, just not in a tight loop.
    """

    def __init__(self, after_success: float, after_failure: float, clock=time.monotonic):
        self.after_success = after_success
        self.after_failure = after_failure
        self._clock = clock
        self._until = 0.0

    def remaining(self) -> int:
        return max(0, math.ceil(self._until - self._clock()))

    def record(self, ok: bool) -> None:
        self._until = self._clock() + (self.after_success if ok else self.after_failure)

    def reset(self) -> None:
        self._until = 0.0


def _seconds_from_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return default


# Shared by /api/refresh and any prediction refresh that fetches, since both
# pull the same files. A prediction refresh with fetch=false only reads local
# data, so it is not throttled.
fetch_cooldown = Cooldown(
    after_success=_seconds_from_env('REFRESH_COOLDOWN_SECONDS', 60),
    after_failure=_seconds_from_env('REFRESH_FAILURE_COOLDOWN_SECONDS', 10),
)


# ---------------------------------------------------------------------------
# Refresh guard: token, rate limit
# ---------------------------------------------------------------------------
class RateLimiter:
    """At most `limit` calls per `window` seconds for each key (sliding window)."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> int:
        """0 if the call is allowed (and counted), else seconds until it would be."""
        now = self._clock()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return max(1, math.ceil(self.window - (now - hits[0])))
            hits.append(now)
            self._hits[key] = hits
            # Keys that have gone quiet would otherwise accumulate forever.
            if len(self._hits) > 1024:
                self._hits = {k: v for k, v in self._hits.items()
                              if v and now - v[-1] < self.window}
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Sized for one person clicking Refresh; polling a running job is much chattier.
refresh_limiter = RateLimiter(int(_seconds_from_env('REFRESH_RATE_LIMIT_PER_MINUTE', 12)))
status_limiter = RateLimiter(int(_seconds_from_env('REFRESH_STATUS_RATE_LIMIT_PER_MINUTE', 120)))
FORWARDING_HEADERS = ('X-Forwarded-For', 'Forwarded', 'X-Real-IP')


def refresh_token() -> str:
    return os.environ.get('REFRESH_TOKEN', '').strip()


def is_direct_loopback() -> bool:
    """A request straight from this machine, not relayed by a proxy.

    A reverse proxy on the same host also arrives from 127.0.0.1, so any
    forwarding header means "not direct" and is treated as remote.
    """
    return (request.remote_addr in ('127.0.0.1', '::1')
            and not any(header in request.headers for header in FORWARDING_HEADERS))


def refresh_guard(limiter: RateLimiter):
    """Protect an endpoint that fetches, rewrites data or reveals job output.

    Rate limited first, so wrong guesses at the token are throttled too. Then:
    with REFRESH_TOKEN set, the caller must send `Authorization: Bearer <token>`;
    with it unset, only a direct local request is accepted, so a deployment that
    forgot to configure a token has the endpoint switched off rather than open.
    """
    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            wait = limiter.check(request.remote_addr or 'unknown')
            if wait:
                response = fail(f'Too many requests; try again in {wait}s.', 429, 'rate_limited',
                                retry_after_seconds=wait)
                response[0].headers['Retry-After'] = str(wait)
                return response
            token = refresh_token()
            if token:
                header = request.headers.get('Authorization', '')
                supplied = header[7:].strip() if header[:7].lower() == 'bearer ' else ''
                if not supplied or not hmac.compare_digest(supplied.encode(), token.encode()):
                    response = fail('A valid refresh token is required.', 401,
                                    'refresh_auth_required')
                    response[0].headers['WWW-Authenticate'] = 'Bearer'
                    return response
            elif not is_direct_loopback():
                return fail('Refresh is disabled for remote callers: set REFRESH_TOKEN on the '
                            'server and send it as a bearer token.', 403, 'refresh_disabled')
            return view(*args, **kwargs)
        return wrapper
    return decorator


def reset_refresh_guards() -> None:
    """Clear rate-limit and cooldown state (tests, and an operator-facing reset)."""
    refresh_limiter.reset()
    status_limiter.reset()
    fetch_cooldown.reset()


@app.route('/api/reload', methods=['POST'])
@refresh_guard(refresh_limiter)
def api_reload():
    reset_state()
    s = state()
    if s.get('error'):
        return unavailable(s['error'])
    return jsonify({'ok': True, 'players': len(s['players']),
                    'gameweek': s['gameweek'], 'market_prices_available': not s.get('market_error')})


def require_manifest() -> bool:
    """Production must serve only verified artifacts; development may serve any."""
    flag = os.environ.get('REQUIRE_ARTIFACT_MANIFEST', '').strip().lower()
    return flag in ('1', 'true', 'yes') if flag else is_production()


def health_report():
    s = state()
    fresh = obs.freshness(s, project_path('data', s['season'], 'fixtures.csv') if s.get('season')
                          else project_path('data', 'none', 'fixtures.csv'))
    alerts = obs.evaluate_alerts(s, fresh, require_manifest=require_manifest())
    if _rebuild_failure:
        alerts.append({'name': 'predictions_rebuild_failing', 'severity': 'warning', 'blocking': False,
                       'message': 'A changed source file could not be read; the previous data is being served.'})
    obs.log_alert_changes(alerts)
    return s, fresh, alerts


@app.route('/api/health/live')
def api_health_live():
    # Liveness must not touch data: a bad export should fail readiness, not restart the process.
    return jsonify({'ok': True, 'status': 'live'})


@app.route('/api/health/ready')
def api_health_ready():
    s, fresh, alerts = health_report()
    report = obs.readiness(s, fresh, alerts)
    report['artifact'] = public_artifact(s.get('artifact'))
    return jsonify(report), (200 if report['ok'] else 503)


@app.route('/api/metrics')
@refresh_guard(status_limiter)
def api_metrics():
    s, fresh, alerts = health_report()
    ready = not any(a['blocking'] for a in alerts)
    body = obs.prometheus(s, fresh, alerts, ready, request_metrics,
                          refresh_running=_refresh_job.get('state') == 'running')
    return Response(body, mimetype='text/plain; version=0.0.4')


def too_soon(remaining: int):
    response = jsonify({
        'ok': False,
        'code': 'refresh_cooldown',
        'error': f'Data was refreshed moments ago; try again in {remaining}s.',
        'retry_after_seconds': remaining,
    })
    response.status_code = 429
    response.headers['Retry-After'] = str(remaining)
    return response


def step_failure(exc, status: int = 502):
    """A failed subprocess step, with its exit status and stderr for the caller."""
    body = {'ok': False, 'code': f'{exc.step}_failed', 'step': exc.step, 'error': str(exc)}
    for key in ('returncode', 'stderr', 'stdout'):
        if key in exc.details:
            body[key] = exc.details[key]
    return jsonify(body), status


@app.route('/api/refresh', methods=['POST'])
@refresh_guard(refresh_limiter)
def api_refresh():
    s = state()
    season = s.get('season') or latest_local_season(Path(ROOT))
    if not season:
        return fail('No local season configured.', 503, 'no_season')

    remaining = fetch_cooldown.remaining()
    if remaining:
        return too_soon(remaining)

    try:
        # One refresh at a time, across processes and across this endpoint and
        # the prediction pipeline, which fetches too. A busy lock is not an
        # attempt, so it does not start a cooldown.
        with pipeline.exclusive_run():
            try:
                with maintenance():
                    pipeline.fetch_season(season, log=lambda _line: None, runner=subprocess.run)
            except pipeline.PipelineError as exc:
                fetch_cooldown.record(False)
                return step_failure(exc)
            fetch_cooldown.record(True)

            new_state = reload_predictions()
            if new_state.get('error'):
                return jsonify({'ok': False, 'error': new_state['error']}), 500
            # A refresh moves the data and leaves the predictions where they
            # were. Running the model is minutes of work and does not belong in
            # a request, so say so rather than serving numbers built on last
            # week's squad prices and availability as though they were current.
            players_raw = market_prices_path(season)
            predictions_stale = (
                os.path.exists(players_raw) and new_state.get('mtime') is not None
                and os.path.getmtime(players_raw) > new_state['mtime'])
            message = f'Season {season} data refreshed successfully.'
            if predictions_stale:
                message += (' The predictions are now older than the data -- '
                            'regenerate them with POST /api/refresh/predictions '
                            'or scripts/refresh_pipeline.py.')
            return jsonify({
                'ok': True,
                'message': message,
                'predictions_stale': predictions_stale,
                'season': new_state['season'],
                'gameweek': new_state['gameweek'],
                'players': len(new_state['players']),
            })
    except pipeline.PipelineBusy:
        return jsonify({'ok': False, 'code': 'refresh_in_progress',
                        'error': 'Another refresh is already running.'}), 409
    except Exception as exc:
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(exc)}), 500


# Regenerating predictions is minutes of model work, so it runs as a background
# job: POST starts it, GET reports on it. The pipeline itself validates the new
# export and swaps it in atomically; state() then reloads on the file's mtime.
_refresh_job: dict = {'state': 'idle'}
_refresh_job_lock = threading.Lock()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _run_refresh_job(season: str, horizon: int, fetch: bool, rebuild: bool) -> None:
    def on_step(step: str) -> None:
        _refresh_job['step'] = step

    try:
        with maintenance():
            report = pipeline.run_pipeline(
                season, horizon, fetch=fetch, rebuild=rebuild,
                log=lambda _line: None, on_step=on_step)
        outcome = {'state': 'succeeded', 'report': report, 'error': None}
    except pipeline.PipelineError as exc:
        outcome = {'state': 'failed', 'failed_step': exc.step, 'error': str(exc), **exc.details}
    except Exception as exc:
        traceback.print_exc()
        outcome = {'state': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
    if fetch and outcome.get('failed_step') not in ('lock', 'setup'):
        fetch_cooldown.record(outcome['state'] == 'succeeded' or outcome.get('failed_step') != 'fetch')
    with _refresh_job_lock:
        _refresh_job.update(outcome, finished_at=_now(), step=None)


@app.route('/api/refresh/predictions', methods=['POST'])
@refresh_guard(refresh_limiter)
def api_refresh_predictions():
    body = contracts.read_json_object(request)
    horizon = contracts.number(
        body, 'horizon', pipeline.DEFAULT_HORIZON, lo=1, hi=pipeline.LAST_GAMEWEEK, integer=True,
        range_message=f'horizon must be between 1 and {pipeline.LAST_GAMEWEEK} gameweeks')
    fetch = contracts.boolean(body, 'fetch', True)
    rebuild = contracts.boolean(body, 'rebuild_history', True)
    season = latest_local_season(Path(ROOT))
    if not season:
        return fail('No local season configured.', 503, 'no_season')

    with _refresh_job_lock:
        if _refresh_job.get('state') == 'running':
            return jsonify({'ok': False, 'code': 'refresh_in_progress',
                            'error': 'A prediction refresh is already running.',
                            'job': dict(_refresh_job)}), 409
        if fetch and fetch_cooldown.remaining():
            return too_soon(fetch_cooldown.remaining())
        _refresh_job.clear()
        _refresh_job.update({'state': 'running', 'step': 'starting', 'season': season,
                             'horizon': horizon, 'fetch': fetch, 'started_at': _now()})
        threading.Thread(target=_run_refresh_job, args=(season, horizon, fetch, rebuild),
                         daemon=True).start()
        return jsonify({'ok': True, 'job': dict(_refresh_job)}), 202


@app.route('/api/refresh/status')
@refresh_guard(status_limiter)
def api_refresh_status():
    # Guarded like the POSTs: a failed job carries stderr, which can name paths.
    with _refresh_job_lock:
        return jsonify({'ok': True, 'job': dict(_refresh_job)})


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
