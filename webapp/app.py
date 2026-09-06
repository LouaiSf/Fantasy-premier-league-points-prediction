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

import pandas as pd
from flask import Flask, jsonify, render_template, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)   # every path in optimise.py is relative to the project root

import optimise as opt  # noqa: E402

# optimise.py takes this as a CLI default rather than a module constant.
DEFAULT_BUDGET = 100.0

app = Flask(__name__)

# Loaded once. The CSV is small (a few hundred rows) and rereading it per
# request would just add latency.
_state: dict = {}


def state() -> dict:
    if not _state:
        reload_predictions()
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
        return {}
    meta = json.load(open(meta_path, encoding='utf-8'))
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
        raise SystemExit('the same player appears twice in that squad')
    return everyone.loc[indices]


def fail(message: str, code: int = 400):
    return jsonify({'ok': False, 'error': message}), code


@app.errorhandler(Exception)
def on_error(exc):
    # A stack trace in the terminal, a readable sentence in the browser.
    traceback.print_exc()
    return jsonify({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}), 500


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    s = state()
    return render_template('index.html',
                           error=s.get('error'),
                           season=s.get('season'),
                           gameweek=s.get('gameweek'),
                           model=s.get('model', {}),
                           player_count=len(s.get('players', [])))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.route('/api/meta')
def api_meta():
    s = state()
    if s.get('error'):
        return fail(s['error'])
    return jsonify({
        'ok': True,
        'season': s['season'],
        'gameweek': s['gameweek'],
        'players': len(s['players']),
        'model': s['model'],
        'budget_default': DEFAULT_BUDGET,
        'squad_size': opt.SQUAD_SIZE,
        'xi_size': opt.XI_SIZE,
        'hit_cost': opt.HIT_COST,
    })


@app.route('/api/players')
def api_players():
    """Everyone, for the pickers. Includes the unavailable, flagged as such."""
    s = state()
    if s.get('error'):
        return fail(s['error'])
    return jsonify({'ok': True, 'players': opt.squad_records(s['everyone'])})


@app.route('/api/squad', methods=['POST'])
def api_squad():
    s = state()
    if s.get('error'):
        return fail(s['error'])

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
        return fail(s['error'])

    body = request.get_json(force=True) or {}
    names = [n for n in body.get('squad', []) if n]
    if len(names) != opt.SQUAD_SIZE:
        return fail(f'a squad is {opt.SQUAD_SIZE} players; you gave {len(names)}')

    try:
        current = squad_from_names(names)
    except SystemExit as exc:
        return fail(str(exc))

    try:
        free = int(body.get('free', 1))
        bank = float(body.get('bank', 0.0))
        max_transfers = int(body.get('max', 3))
    except (TypeError, ValueError):
        return fail('free, bank and max must be numbers')
    if not 0 <= max_transfers <= 5:
        return fail('max transfers must be between 0 and 5')

    data = opt.compute_transfers(current, s['players'], free, bank, max_transfers)
    data['ok'] = True
    return jsonify(data)


@app.route('/api/chips', methods=['POST'])
def api_chips():
    s = state()
    if s.get('error'):
        return fail(s['error'])

    body = request.get_json(force=True) or {}
    names = [n for n in body.get('squad', []) if n]
    squad = None
    if names:
        if len(names) != opt.SQUAD_SIZE:
            return fail(f'a squad is {opt.SQUAD_SIZE} players; you gave {len(names)}')
        try:
            squad = squad_from_names(names)
        except SystemExit as exc:
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
        return fail(s['error'])
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
        return fail(s['error'])
    return jsonify({'ok': True, 'players': len(s['players']),
                    'gameweek': s['gameweek']})


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
