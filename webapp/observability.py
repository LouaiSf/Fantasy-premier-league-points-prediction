"""Structured logging, freshness metrics, alerts and readiness for the API.

Nothing here talks to the network or sends a message. It makes the state of the
service *observable*: JSON log lines for a log shipper, a readiness verdict for
the load balancer, and Prometheus-format gauges plus named alert conditions for
whatever does the alerting (Prometheus/Alertmanager, Grafana, UptimeRobot on
/api/health/ready, a cron that greps the logs). Delivery is that tool's job.

Alerts (name -> what it means). `blocking` ones fail /api/health/ready.

    predictions_unavailable          no usable prediction export             blocking
    market_prices_unavailable        no live prices (see /api/meta)          blocking
    artifact_manifest_invalid        manifest missing/unreadable/mismatched  blocking in production
    predictions_older_than_market    market data changed after the predictions were made
    predictions_gameweek_mismatch    predictions target a gameweek that is no longer next
    predictions_too_old              older than MAX_PREDICTION_AGE_HOURS (72)
    market_data_old                  older than MAX_MARKET_AGE_HOURS (48)
    predictions_stale_before_deadline  deadline within DEADLINE_WINDOW_HOURS (24) and the
                                     predictions are older than STALE_BEFORE_DEADLINE_HOURS (12)
    predictions_predate_deadline     the deadline has passed and the predictions were made before it
    predictions_rebuild_failing      a changed source file was unreadable; the previous data is being served

The deadline is estimated as the gameweek's first kick-off minus 90 minutes
(the local fixtures file does not carry FPL's official deadline).
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
import math
import os
import re
import sys
import threading
import time
import uuid
from typing import Mapping

UTC = datetime.timezone.utc
LOGGER_NAME = 'fpl'
REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
DEADLINE_LEAD = datetime.timedelta(minutes=90)


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, event, plus whatever the call attached."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'ts': datetime.datetime.fromtimestamp(record.created, UTC).isoformat(timespec='milliseconds'),
            'level': record.levelname.lower(),
            'event': getattr(record, 'event', record.getMessage()),
        }
        payload.update(getattr(record, 'fields', {}))
        return json.dumps(payload, default=str, separators=(',', ':'))


def configure_logging(environ: Mapping[str, str] | None = None) -> logging.Logger:
    environ = os.environ if environ is None else environ
    logger = logging.getLogger(LOGGER_NAME)
    level = getattr(logging, (environ.get('LOG_LEVEL') or 'INFO').upper(), logging.INFO)
    logger.setLevel(level)
    if not any(getattr(h, '_fpl_json', False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        handler._fpl_json = True   # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger


def log_event(level: int, event: str, **fields) -> None:
    logging.getLogger(LOGGER_NAME).log(level, event, extra={'event': event, 'fields': fields})


def request_id_from(header_value: str | None) -> str:
    """Honour a caller's X-Request-ID if it is safe to echo, else mint one."""
    if header_value and REQUEST_ID_PATTERN.match(header_value):
        return header_value
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Request metrics
# ---------------------------------------------------------------------------
class RequestMetrics:
    """In-process HTTP counters, safe to update from several threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: dict[tuple[str, str, int], int] = {}
        self.duration_sum: dict[str, float] = {}
        self.duration_count: dict[str, int] = {}

    def observe(self, route: str, method: str, status: int, seconds: float) -> None:
        with self._lock:
            key = (route, method, status)
            self.requests[key] = self.requests.get(key, 0) + 1
            self.duration_sum[route] = self.duration_sum.get(route, 0.0) + seconds
            self.duration_count[route] = self.duration_count.get(route, 0) + 1

    def snapshot(self) -> tuple[dict, dict, dict]:
        with self._lock:
            return dict(self.requests), dict(self.duration_sum), dict(self.duration_count)

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self.duration_sum.clear()
            self.duration_count.clear()


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------
def _iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.datetime.fromtimestamp(ts, UTC).isoformat()


def _parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


_DEADLINE_CACHE: dict[tuple[str, int, int], float | None] = {}


def next_deadline(fixtures_path: str, gameweek: int | None) -> float | None:
    """Estimated deadline (epoch seconds): the gameweek's first kick-off minus 90 minutes."""
    if gameweek is None or not os.path.exists(fixtures_path):
        return None
    stat = os.stat(fixtures_path)
    key = (fixtures_path, stat.st_mtime_ns, int(gameweek))
    if key in _DEADLINE_CACHE:
        return _DEADLINE_CACHE[key]
    earliest = None
    try:
        with open(fixtures_path, encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                if str(row.get('event', '')).strip() != str(int(gameweek)):
                    continue
                kickoff = _parse_iso(row.get('kickoff_time'))
                if kickoff is not None and (earliest is None or kickoff < earliest):
                    earliest = kickoff
    except (OSError, csv.Error):
        earliest = None
    deadline = None if earliest is None else earliest - DEADLINE_LEAD.total_seconds()
    if len(_DEADLINE_CACHE) > 64:
        _DEADLINE_CACHE.clear()
    _DEADLINE_CACHE[key] = deadline
    return deadline


def freshness(snapshot: Mapping, fixtures_path: str, now: float | None = None) -> dict:
    """How old the data behind a snapshot is, and how long until the next deadline."""
    now = time.time() if now is None else now
    artifact = snapshot.get('artifact') or {}
    manifest_time = _parse_iso(artifact.get('generated_at'))
    file_time = snapshot.get('mtime')
    generated = manifest_time if manifest_time is not None else file_time
    market = snapshot.get('market_mtime')
    fixtures = os.path.getmtime(fixtures_path) if os.path.exists(fixtures_path) else None
    deadline = next_deadline(fixtures_path, snapshot.get('gameweek'))

    def age(ts):
        return None if ts is None else max(0.0, now - ts)

    return {
        'now': _iso(now),
        'predictions': {
            'generated_at': _iso(generated),
            'source': 'manifest' if manifest_time is not None else ('file_mtime' if file_time else None),
            'age_seconds': age(generated),
            'loaded_at': _iso(snapshot.get('loaded_at')),
        },
        'market': {'updated_at': _iso(market), 'age_seconds': age(market)},
        'fixtures': {'updated_at': _iso(fixtures), 'age_seconds': age(fixtures)},
        'next_deadline': {
            'gameweek': snapshot.get('gameweek'),
            'deadline_at': _iso(deadline),
            'seconds_until': None if deadline is None else deadline - now,
            'estimated': True,
        },
        '_generated_ts': generated, '_market_ts': market, '_deadline_ts': deadline,
    }


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
ALERT_NAMES = (
    'predictions_unavailable',
    'market_prices_unavailable',
    'artifact_manifest_invalid',
    'predictions_older_than_market',
    'predictions_gameweek_mismatch',
    'predictions_too_old',
    'market_data_old',
    'predictions_stale_before_deadline',
    'predictions_predate_deadline',
    'predictions_rebuild_failing',
)


def _hours(environ: Mapping[str, str], name: str, default: float) -> float:
    try:
        return max(0.0, float(environ.get(name, default))) * 3600
    except ValueError:
        return default * 3600


def evaluate_alerts(snapshot: Mapping, fresh: dict, *, require_manifest: bool,
                    environ: Mapping[str, str] | None = None) -> list[dict]:
    """Every alert condition that currently holds."""
    environ = os.environ if environ is None else environ
    max_prediction_age = _hours(environ, 'MAX_PREDICTION_AGE_HOURS', 72)
    max_market_age = _hours(environ, 'MAX_MARKET_AGE_HOURS', 48)
    deadline_window = _hours(environ, 'DEADLINE_WINDOW_HOURS', 24)
    stale_before_deadline = _hours(environ, 'STALE_BEFORE_DEADLINE_HOURS', 12)
    alerts: list[dict] = []

    def raise_(name: str, severity: str, message: str, blocking: bool = False) -> None:
        alerts.append({'name': name, 'severity': severity, 'blocking': blocking, 'message': message})

    if snapshot.get('error'):
        raise_('predictions_unavailable', 'critical', 'No usable prediction export is loaded.', True)
    if snapshot.get('market_error'):
        raise_('market_prices_unavailable', 'critical',
               'Live market prices are unavailable; budgets, transfers and chips are refused.', True)

    artifact = snapshot.get('artifact')
    if artifact and artifact.get('manifest_status') != 'verified':
        status = artifact.get('manifest_status')
        raise_('artifact_manifest_invalid', 'critical' if require_manifest else 'warning',
               f'The prediction artifact has no verified manifest ({status}).', require_manifest)

    if snapshot.get('error'):
        return alerts     # the rest is about data that is not there

    now_ts = _parse_iso(fresh['now'])
    generated, market, deadline = fresh['_generated_ts'], fresh['_market_ts'], fresh['_deadline_ts']
    predictions_age = fresh['predictions']['age_seconds']

    if generated is not None and market is not None and generated < market:
        raise_('predictions_older_than_market', 'warning',
               'Market data changed after the predictions were generated; regenerate them.')

    first_predicted = min(snapshot.get('future_gameweeks') or [], default=None)
    if first_predicted is not None and snapshot.get('gameweek') is not None \
            and first_predicted != snapshot['gameweek']:
        raise_('predictions_gameweek_mismatch', 'warning',
               f'Predictions start at GW{first_predicted} but GW{snapshot["gameweek"]} is next.')

    if predictions_age is not None and predictions_age > max_prediction_age:
        raise_('predictions_too_old', 'warning',
               f'Predictions are {predictions_age / 3600:.0f}h old.')
    market_age = fresh['market']['age_seconds']
    if market_age is not None and market_age > max_market_age:
        raise_('market_data_old', 'warning', f'Market data is {market_age / 3600:.0f}h old.')

    if deadline is not None and generated is not None and now_ts is not None:
        until = deadline - now_ts
        if until <= 0:
            if generated < deadline:
                raise_('predictions_predate_deadline', 'warning',
                       'The deadline has passed and the predictions were generated before it.')
        elif until <= deadline_window and predictions_age is not None \
                and predictions_age > stale_before_deadline:
            raise_('predictions_stale_before_deadline', 'warning',
                   f'Deadline in {until / 3600:.1f}h and the predictions are '
                   f'{predictions_age / 3600:.0f}h old; refresh them.')
    return alerts


_last_alerts: frozenset[str] = frozenset()
_alerts_lock = threading.Lock()


def log_alert_changes(alerts: list[dict]) -> None:
    """Log each alert as it is raised and again when it clears."""
    global _last_alerts
    current = {a['name']: a for a in alerts}
    with _alerts_lock:
        previous, _last_alerts = _last_alerts, frozenset(current)
    for name in sorted(set(current) - previous):
        alert = current[name]
        log_event(logging.ERROR if alert['severity'] == 'critical' else logging.WARNING,
                  'alert_raised', alert=name, severity=alert['severity'], message=alert['message'])
    for name in sorted(previous - set(current)):
        log_event(logging.INFO, 'alert_cleared', alert=name)


def reset_alert_log() -> None:
    global _last_alerts
    with _alerts_lock:
        _last_alerts = frozenset()


# ---------------------------------------------------------------------------
# Readiness and Prometheus exposition
# ---------------------------------------------------------------------------
def readiness(snapshot: Mapping, fresh: dict, alerts: list[dict]) -> dict:
    blocking = [a['name'] for a in alerts if a['blocking']]
    return {
        'ok': not blocking,
        'status': 'ready' if not blocking else 'not_ready',
        'blocking': blocking,
        'checks': {
            'predictions_loaded': not snapshot.get('error'),
            'market_prices': not snapshot.get('error') and not snapshot.get('market_error'),
            'artifact_verified': (snapshot.get('artifact') or {}).get('manifest_status') == 'verified',
        },
        'alerts': [{k: a[k] for k in ('name', 'severity', 'message')} for a in alerts],
        'freshness': {k: v for k, v in fresh.items() if not k.startswith('_')},
    }


def _label(value) -> str:
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')


def prometheus(snapshot: Mapping, fresh: dict, alerts: list[dict], ready: bool,
               metrics: RequestMetrics, refresh_running: bool) -> str:
    lines: list[str] = []

    def gauge(name: str, help_: str, value, labels: str = '') -> None:
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            return
        lines.append(f'# HELP {name} {help_}')
        lines.append(f'# TYPE {name} gauge')
        lines.append(f'{name}{labels} {value}')

    gauge('fpl_ready', '1 when the service can serve predictions and prices.', 1 if ready else 0)
    gauge('fpl_predictions_age_seconds', 'Seconds since the predictions were generated.',
          fresh['predictions']['age_seconds'])
    gauge('fpl_predictions_generated_timestamp_seconds', 'When the predictions were generated.',
          fresh['_generated_ts'])
    gauge('fpl_market_data_age_seconds', 'Seconds since market prices were fetched.',
          fresh['market']['age_seconds'])
    gauge('fpl_fixtures_age_seconds', 'Seconds since fixtures were fetched.',
          fresh['fixtures']['age_seconds'])
    gauge('fpl_next_deadline_seconds', 'Seconds until the estimated next deadline (negative once passed).',
          fresh['next_deadline']['seconds_until'])
    gauge('fpl_snapshot_loaded_timestamp_seconds', 'When the in-memory snapshot was built.',
          snapshot.get('loaded_at'))
    gauge('fpl_refresh_running', '1 while a prediction refresh job is running.', 1 if refresh_running else 0)

    active = {a['name']: a['severity'] for a in alerts}
    lines.append('# HELP fpl_alert_active 1 while the named alert condition holds.')
    lines.append('# TYPE fpl_alert_active gauge')
    for name in ALERT_NAMES:
        lines.append(f'fpl_alert_active{{alert="{name}"}} {1 if name in active else 0}')

    artifact = snapshot.get('artifact')
    if artifact:
        bundle = (artifact.get('model_bundle') or {}).get('sha256') or ''
        lines.append('# HELP fpl_artifact_info Identity of the served prediction artifact.')
        lines.append('# TYPE fpl_artifact_info gauge')
        lines.append('fpl_artifact_info{sha256="%s",model_bundle_sha256="%s",manifest_status="%s"} 1' % (
            _label(artifact.get('sha256', '')), _label(bundle), _label(artifact.get('manifest_status'))))

    requests, duration_sum, duration_count = metrics.snapshot()
    lines.append('# HELP fpl_http_requests_total HTTP requests handled.')
    lines.append('# TYPE fpl_http_requests_total counter')
    for (route, method, status), count in sorted(requests.items()):
        lines.append(f'fpl_http_requests_total{{route="{_label(route)}",method="{method}",status="{status}"}} {count}')
    lines.append('# HELP fpl_http_request_duration_seconds Time spent handling requests.')
    lines.append('# TYPE fpl_http_request_duration_seconds summary')
    for route in sorted(duration_sum):
        lines.append(f'fpl_http_request_duration_seconds_sum{{route="{_label(route)}"}} {duration_sum[route]:.6f}')
        lines.append(f'fpl_http_request_duration_seconds_count{{route="{_label(route)}"}} {duration_count[route]}')
    return '\n'.join(lines) + '\n'
