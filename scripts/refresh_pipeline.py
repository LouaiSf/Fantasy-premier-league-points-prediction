"""Refresh the data and regenerate predictions_next_gw.csv, safely.

/api/refresh pulls raw FPL data and stops there, which left the backend serving
predictions built on last week's fixtures and prices -- and, when the export was
a single gameweek, no way to run a multi-week chip plan at all. This runs the
whole chain, and only ever swaps the result in once it has proved itself:

    1. fetch    current season data (fetch_data.py, olbauday, forced)
    2. history  rebuild all_seasons_data_final.csv if it lags the fetched data
    3. predict  predict_gameweek.py --horizon N, written to a temp file
    4. validate the temp file against the data that was just fetched
    5. replace  os.replace() onto predictions_next_gw.csv

Every command's exit status is checked and its stderr kept. A failure at any
step leaves the previous export exactly where it was. The web app reloads on
the file's mtime, so the swap needs no restart or reload call.

Usage
-----
    python scripts/refresh_pipeline.py                  # fetch + predict, horizon 12
    python scripts/refresh_pipeline.py --no-fetch       # data already fresh
    python scripts/refresh_pipeline.py --horizon 8 --season 2026-27
    python scripts/refresh_pipeline.py --no-rebuild-history

Exit status is 0 on success and 1 on failure, so it can be scheduled (cron,
Windows Task Scheduler) and alert on the exit code.

It never retrains models. The history rebuild is build_dataset.py --write: about
30 seconds, and it keeps a .prev copy of the file it replaces. Predictions are
built from that history rather than from the raw files, so without the rebuild
last week's form is silently missing.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import math
import os
import subprocess
import sys
import time
from typing import Callable

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import artifacts  # noqa: E402
import optimise as opt  # noqa: E402

DEFAULT_HORIZON = 12
LAST_GAMEWEEK = 38
FETCH_TIMEOUT_S = 180
HISTORY_TIMEOUT_S = 10 * 60
PREDICT_TIMEOUT_S = 30 * 60
# A run that died without releasing the lock must not block refreshes forever.
LOCK_STALE_AFTER_S = PREDICT_TIMEOUT_S + FETCH_TIMEOUT_S + HISTORY_TIMEOUT_S + 60
# A new export losing more than this share of the players the old one had
# almost certainly means something upstream broke, not that they all retired.
MAX_PLAYER_LOSS = 0.20

REQUIRED_COLUMNS = ('element', 'name', 'team', 'position', 'GW', 'value_m', 'predicted_points')

Log = Callable[[str], None]


class PipelineError(RuntimeError):
    """A step failed; the previous predictions were left untouched."""

    def __init__(self, step: str, message: str, details: dict | None = None):
        super().__init__(f'{step}: {message}')
        self.step = step
        self.message = message
        # returncode / stderr / stdout of the command that failed, when there was one
        self.details = details or {}


class PipelineBusy(PipelineError):
    def __init__(self) -> None:
        super().__init__('lock', 'another refresh is already running')


def _lock_path() -> str:
    return os.path.join(ROOT, 'data', '.refresh_pipeline.lock')


@contextlib.contextmanager
def exclusive_run():
    """One refresh at a time, across processes (a cron job and the web app)."""
    path = _lock_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if time.time() - os.path.getmtime(path) > LOCK_STALE_AFTER_S:
            os.remove(path)
    except OSError:
        pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise PipelineBusy() from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


def latest_season() -> str:
    data_dir = os.path.join(ROOT, 'data')
    seasons = sorted(d for d in os.listdir(data_dir)
                     if os.path.isdir(os.path.join(data_dir, d)) and d[:4].isdigit())
    if not seasons:
        raise PipelineError('setup', f'no season directory under {data_dir}')
    return seasons[-1]


def expected_gameweeks(first_gw: int, horizon: int) -> list[int]:
    """The weeks a horizon should cover, cut off where the season ends."""
    return list(range(first_gw, min(first_gw + horizon - 1, LAST_GAMEWEEK) + 1))


def validate_predictions(path: str, season: str, horizon: int,
                         previous_path: str | None = None) -> dict:
    """Prove a candidate export is safe to serve. Raises PipelineError if not.

    Checked against the data on disk, which the fetch step has just refreshed:
    the first gameweek must be the one local fixtures call next (the predict
    step asks the live API, so a disagreement means one side is stale), every
    week of the horizon must be present, and the numbers must be usable.
    """
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # unreadable or empty file
        raise PipelineError('validate', f'predictions are not readable CSV: {exc}') from exc
    if df.empty:
        raise PipelineError('validate', 'predictions file has no rows')
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise PipelineError('validate', f'predictions are missing columns: {", ".join(missing)}')

    points = pd.to_numeric(df['predicted_points'], errors='coerce')
    if points.isna().any() or not points.map(math.isfinite).all():
        raise PipelineError('validate', 'predicted_points has blank or non-finite values')
    if pd.to_numeric(df['value_m'], errors='coerce').isna().any():
        raise PipelineError('validate', 'value_m has blank values')
    if df['element'].isna().any():
        raise PipelineError('validate', 'element has blank values')

    first_gw = opt.infer_next_gameweek(season, root=ROOT)
    have = sorted(int(g) for g in df['GW'].dropna().unique())
    want = expected_gameweeks(first_gw, horizon)
    if have and have[0] != first_gw:
        raise PipelineError(
            'validate',
            f'predictions start at GW{have[0]} but local fixtures say GW{first_gw} is next; '
            'the fetched data and the live API disagree, so nothing was replaced')
    absent = [gw for gw in want if gw not in have]
    if absent:
        raise PipelineError(
            'validate',
            f'predictions cover GW{have[0]}-GW{have[-1]} but the {horizon}-week horizon '
            f'needs {", ".join(f"GW{gw}" for gw in absent)}')

    teams_path = os.path.join(ROOT, 'data', season, 'teams.csv')
    if os.path.exists(teams_path):
        local = set(pd.read_csv(teams_path)['name'].dropna())
        seen = set(df['team'].dropna())
        if local != seen:
            raise PipelineError(
                'validate',
                f'clubs do not match data/{season}/teams.csv '
                f'(only in predictions: {sorted(seen - local) or "none"}; '
                f'only local: {sorted(local - seen) or "none"})')

    players = int(df['element'].nunique())
    if previous_path and os.path.exists(previous_path):
        try:
            before = int(pd.read_csv(previous_path, usecols=['element'])['element'].nunique())
        except Exception:
            before = 0
        if before and players < before * (1 - MAX_PLAYER_LOSS):
            raise PipelineError(
                'validate',
                f'only {players} players, down from {before} in the current export')

    return {'first_gw': first_gw, 'gameweeks': have, 'players': players, 'rows': int(len(df))}


def history_gameweeks_behind(season: str) -> int | None:
    """How many fetched gameweeks the model's history has not seen yet."""
    history_path = os.path.join(ROOT, 'all_seasons_data_final.csv')
    merged_path = os.path.join(ROOT, 'data', season, 'gws', 'merged_gw.csv')
    if not (os.path.exists(history_path) and os.path.exists(merged_path)):
        return None
    try:
        history = pd.read_csv(history_path, usecols=['season', 'GW'], low_memory=False)
        fetched = pd.read_csv(merged_path, usecols=['GW'], low_memory=False)
    except Exception:
        return None
    seen = history.loc[history['season'] == season, 'GW']
    if fetched['GW'].dropna().empty:
        return None
    return max(0, int(fetched['GW'].max()) - (int(seen.max()) if not seen.empty else 0))


MAX_OUTPUT_CHARS = 4000


def _tail(text: str | None) -> str:
    text = (text or '').strip()
    return text[-MAX_OUTPUT_CHARS:]


def _run(step: str, command: list[str], timeout: int, log: Log, runner) -> None:
    log(f'  $ {" ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(command))}')
    try:
        result = runner(command, cwd=ROOT, capture_output=True, text=True,
                        timeout=timeout, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(step, f'timed out after {timeout // 60} minutes',
                            {'returncode': None, 'stderr': _tail(exc.stderr if isinstance(exc.stderr, str) else None),
                             'stdout': _tail(exc.stdout if isinstance(exc.stdout, str) else None)}) from None
    returncode = getattr(result, 'returncode', 0)
    if returncode != 0:
        stderr, stdout = _tail(getattr(result, 'stderr', '')), _tail(getattr(result, 'stdout', ''))
        last = (stderr or stdout).splitlines()[-1:] or ['no output']
        raise PipelineError(step, f'exited with status {returncode}: {last[0]}',
                            {'returncode': returncode, 'stderr': stderr, 'stdout': stdout})


def fetch_season(season: str, log: Log = print, runner=subprocess.run) -> None:
    """Pull one season from olbauday, forced. Raises PipelineError if it fails.

    olbauday, and forced: vaastav is the archive of finished seasons and has
    nothing to say about one in progress, and without --force every existing
    file is skipped, so a season already on disk would refresh nothing. The
    exit status is checked -- a failed fetch must not be reported as fresh data.
    """
    _run('fetch', [sys.executable, os.path.join(ROOT, 'scripts', 'fetch_data.py'),
                   '--season', season, '--source', 'olbauday', '--force'],
         FETCH_TIMEOUT_S, log, runner)


def rebuild_history(log: Log = print, runner=subprocess.run) -> None:
    _run('history', [sys.executable, os.path.join(ROOT, 'scripts', 'build_dataset.py'), '--write'],
         HISTORY_TIMEOUT_S, log, runner)


def _write_manifest(target: str, season: str, horizon: int, summary: dict, log: Log) -> str | None:
    """Record what the artifact is. Returns a warning if that could not be done."""
    try:
        manifest = artifacts.build_manifest(
            target, season=season, horizon=horizon, first_gw=summary['first_gw'],
            last_gw=summary['gameweeks'][-1], players=summary['players'],
            rows=summary['rows'], root=ROOT)
        artifacts.write_manifest(target, manifest)
    except OSError as exc:
        log(f'  could not write the manifest: {exc}')
        return (f'Predictions were replaced but the manifest could not be written ({exc}); '
                'run scripts/artifacts.py write.')
    return None


def run_pipeline(season: str | None = None, horizon: int = DEFAULT_HORIZON,
                 fetch: bool = True, rebuild: bool = True, out: str | None = None,
                 log: Log = print, on_step: Callable[[str], None] | None = None,
                 runner=subprocess.run) -> dict:
    """Run the whole chain. Returns a report; raises PipelineError on failure."""
    if not 1 <= horizon <= LAST_GAMEWEEK:
        raise PipelineError('setup', f'horizon must be between 1 and {LAST_GAMEWEEK}')
    season = season or latest_season()
    target = os.path.join(ROOT, out or opt.PREDICTIONS)
    started = time.time()
    step = on_step or (lambda _name: None)

    with exclusive_run():
        if fetch:
            step('fetch')
            log(f'[1/5] fetching {season} data')
            fetch_season(season, log, runner)
        else:
            log('[1/5] fetch skipped')

        # The predictions are built from this history, not from the raw files
        # just fetched, so a lagging history means last week's form is missing.
        lag = history_gameweeks_behind(season) if rebuild else None
        if lag:
            step('history')
            log(f'[2/5] model history is {lag} gameweek(s) behind; rebuilding it')
            rebuild_history(log, runner)
        else:
            log('[2/5] model history is current' if rebuild else '[2/5] history rebuild skipped')

        stem, ext = os.path.splitext(target)
        candidate = f'{stem}.{os.getpid()}.tmp{ext}'
        try:
            step('predict')
            log(f'[3/5] predicting, horizon {horizon}')
            _run('predict', [sys.executable, os.path.join(ROOT, 'scripts', 'predict_gameweek.py'),
                             '--season', season, '--horizon', str(horizon), '--out', candidate],
                 PREDICT_TIMEOUT_S, log, runner)

            step('validate')
            log('[4/5] validating')
            summary = validate_predictions(candidate, season, horizon, previous_path=target)

            step('replace')
            log('[5/5] replacing predictions')
            os.replace(candidate, target)
            manifest_warning = _write_manifest(target, season, horizon, summary, log)
        finally:
            with contextlib.suppress(OSError):
                os.remove(candidate)

    behind = history_gameweeks_behind(season)
    warnings = [manifest_warning] if manifest_warning else []
    if behind:
        warnings.append(
            f'The model history is {behind} gameweek(s) behind the fetched data, so '
            'form from those weeks is not in these predictions. Refresh it with '
            'scripts/build_dataset.py --write.')
    return {
        'season': season,
        'horizon': horizon,
        'first_gw': summary['first_gw'],
        'last_gw': summary['gameweeks'][-1],
        'players': summary['players'],
        'rows': summary['rows'],
        'artifact_sha256': artifacts.sha256_file(target),
        'history_gameweeks_behind': behind,
        'warnings': warnings,
        'fetched': fetch,
        'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'seconds': round(time.time() - started, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--season', default=None, help='defaults to the latest in data/')
    ap.add_argument('--horizon', type=int, default=DEFAULT_HORIZON)
    ap.add_argument('--no-fetch', action='store_true', help='skip the data fetch')
    ap.add_argument('--no-rebuild-history', action='store_true',
                    help='do not rebuild all_seasons_data_final.csv when it lags the fetched data')
    ap.add_argument('--out', default=None, help=f'defaults to {opt.PREDICTIONS}')
    args = ap.parse_args()
    os.chdir(ROOT)
    try:
        report = run_pipeline(args.season, args.horizon, fetch=not args.no_fetch,
                              rebuild=not args.no_rebuild_history, out=args.out)
    except PipelineError as exc:
        print(f'FAILED at {exc.step}: {exc.message}\nThe previous predictions were not changed.',
              file=sys.stderr)
        return 1
    print(f"\nOK: GW{report['first_gw']}-GW{report['last_gw']}, {report['players']} players, "
          f"{report['seconds']}s")
    for warning in report['warnings']:
        print(f'WARNING: {warning}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
