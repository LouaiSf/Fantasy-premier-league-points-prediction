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
import traceback
import datetime
import subprocess
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)   # every path in optimise.py is relative to the project root

try:
    from scripts import optimise as opt  # noqa: E402
except ImportError:
    import optimise as opt  # noqa: E402
from webapp.platform_data import (  # noqa: E402
    build_local_snapshot,
    latest_local_season,
    player_history,
)

# optimise.py takes this as a CLI default rather than a module constant.
DEFAULT_BUDGET = 100.0

app = Flask(__name__)
# The Next.js frontend (webapp/frontend) runs on its own dev port and calls
# this API cross-origin; the Jinja/vanilla-JS pages it is replacing served
# same-origin and needed none of this.
CORS(app, resources={r'/api/*': {'origins': '*'}})

# Loaded once. The CSV is small (a few hundred rows) and rereading it per
# request would just add latency.
_state: dict = {}


def state() -> dict:
    path = opt.PREDICTIONS
    if not _state:
        return reload_predictions()
    # A cached error has no mtime to compare against, so the staleness check
    # below could never fire and the process stayed broken for its whole life
    # even once the file it was complaining about had been generated. Retry
    # whenever the file exists and the last attempt failed: the work is one
    # CSV read, and the alternative is telling someone to restart the server
    # after running the pipeline the error message just told them to run.
    if _state.get('error') and os.path.exists(path):
        return reload_predictions()
    if os.path.exists(path) and ('mtime' in _state and os.path.getmtime(path) != _state['mtime']):
        return reload_predictions()
    return _state


def reload_predictions() -> dict:
    path = opt.PREDICTIONS
    if not os.path.exists(path):
        _state['error'] = (
            f"{path} not found. Run scripts/predict_gameweek.py first -- "
            f"the site has nothing to show without it."
        )
        _state['players'] = pd.DataFrame()
        return _state

    players = opt.load_predictions(path, drop_unavailable=True)
    everyone = opt.load_predictions(path, drop_unavailable=False)

    season = sorted(
        d for d in os.listdir('data')
        if os.path.isdir(os.path.join('data', d)) and d[:4].isdigit()
    )[-1]
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
                'season': season,
                'gameweek': opt.infer_next_gameweek(season),
                'mtime': os.path.getmtime(path),
                'model': model_summary(),
            })
            return _state

    _state.update({
        'error': None,
        'players': players,
        'everyone': everyone,
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
    snapshot.update({
        'ok': True,
        'prediction_available': prediction_available,
        'prediction_error': s.get('error'),
        'prediction_timestamp': prediction_timestamp,
        'model': s.get('model') or model_summary(),
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
PROFILE_TEXT = ['news', 'birth_date', 'team_join_date', 'squad_number', 'photo']

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

    keep = ['id'] + [c for c in PROFILE_NUMERIC + PROFILE_TEXT if c in raw.columns]
    if 'region' in raw.columns:
        keep.append('region')
    if 'code' in raw.columns:
        keep.append('code')
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
        for key in ('news', 'birth_date', 'team_join_date'):
            value = row.get(key)
            record[key] = None if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)

        code = row.get('code')
        record['photo'] = (
            f'https://resources.premierleague.com/premierleague/photos/players/250x250/p{int(code)}.png'
            if code is not None and not pd.isna(code) else None
        )

        region = row.get('region')
        meta = regions.get(str(int(region))) if region is not None and not pd.isna(region) else None
        record['country'] = meta['name'] if meta else None
        record['flag'] = flag_for(meta.get('iso') if meta else None)
        out.append(record)
    return out


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

    # show_squad derives this for the terminal; the browser needs it too.
    shape = result['xi']['position'].value_counts()
    formation = (f"{int(shape.get('DEF', 0))}-{int(shape.get('MID', 0))}"
                 f"-{int(shape.get('FWD', 0))}")

    captain = None
    if result['captain'] is not None:
        captain = opt.squad_records(result['squad'][
            result['squad']['name'] == result['captain']['name']])[0]

    return jsonify({
        'ok': True,
        'budget': budget,
        'spend': round(float(result['squad']['value_m'].sum()), 1),
        'xi': opt.squad_records(result['xi']),
        'bench': opt.squad_records(result['bench']),
        'captain': captain,
        'xi_points': round(float(result['xi']['predicted_points'].sum()), 2),
        'formation': formation,
    })


@app.route('/api/transfers', methods=['POST'])
def api_transfers():
    s = state()
    if s.get('error'):
        return unavailable(s['error'])

    body = request.get_json(force=True) or {}
    names = [n for n in body.get('squad', []) if n]
    if len(names) != opt.SQUAD_SIZE:
        return fail(f'a squad is {opt.SQUAD_SIZE} players; you gave {len(names)}')

    try:
        current = squad_from_names(names)
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

    try:
        data = opt.compute_transfers(current, s['players'], free, bank, max_transfers)
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

    data = opt.compute_chips(squad, s['season'], s['gameweek'], horizon, s['players'])
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
        res = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'scripts', 'fetch_data.py'), '--season', season],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        _state.clear()
        new_state = state()
        if new_state.get('error'):
            return jsonify({'ok': False, 'error': new_state['error'], 'output': res.stdout}), 500
        return jsonify({
            'ok': True,
            'message': f'Season {season} data refreshed successfully.',
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
    print('\n  http://127.0.0.1:5000\n')
    app.run(debug=False, port=5000)
