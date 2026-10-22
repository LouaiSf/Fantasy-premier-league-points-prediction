"""Effective ownership (EO) from a sample of real FPL teams.

EO of a player = sum of the sample's multipliers for him / sample size x 100:
bench 0, starter 1, captain 2, Triple Captain 3 (a Bench Boost bench counts
1, which FPL's `multiplier` already says). Against the field a manager's
points move by (his multiplier - EO/100) x the player's points, so a 160% EO
Haaland not captained is a bet *against* the field, and a 5% EO differential
is the upside play.

Samples come from the Overall league (314) standings, which FPL publishes 50
managers a page:

    top1k    pages 1-20, every member
    top10k   20 random pages from 1-200            (1,000 managers)
    overall  20 random pages across the whole game (1,000 managers)
    league   every member of one classic league, up to 500

Picks for a gameweek are public only once its deadline has passed, so the
basis is the last gameweek that has started; ownership for the next one is
estimated by scaling each player's sampled EO with how his overall selection
has moved since the sample was taken.
"""

from __future__ import annotations

import datetime
import json
import os
import random
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from webapp.fpl_client import (
    FplClientError, LineupNotFound, ManagerNotFound, UpstreamRateLimited,
)

OVERALL_LEAGUE = 314
PAGE_SIZE = 50
TIER_PAGES = {'top1k': 20, 'top10k': 20, 'overall': 20}
TOP10K_LAST_PAGE = 200
LEAGUE_MAX_MEMBERS = 500
WORKERS = 4
REQUESTS_PER_SECOND = 8.0
RETRIES = 3
# An estimate scales EO by ownership drift; past this it is a guess, not a scale.
ESTIMATE_CLAMP = (0.0, 300.0)
TIERS = tuple(TIER_PAGES)


class Throttle:
    """At most `rate` calls a second across every worker thread."""

    def __init__(self, rate: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.interval = 1.0 / rate if rate > 0 else 0.0
        self._clock, self._sleep = clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            self._sleep(start - now)


def sample_pages(tier: str, total_players: int | None, rng: random.Random) -> list[int]:
    """Which Overall-league standings pages a tier reads."""
    if tier == 'top1k':
        return list(range(1, TIER_PAGES['top1k'] + 1))
    if tier == 'top10k':
        return sorted(rng.sample(range(1, TOP10K_LAST_PAGE + 1), TIER_PAGES['top10k']))
    if tier == 'overall':
        last = max(TIER_PAGES['overall'], (total_players or 10_000_000) // PAGE_SIZE)
        # Spread evenly with a random offset, so every part of the game is in.
        step = last / TIER_PAGES['overall']
        return [min(last, int(step * i + rng.uniform(0, step)) + 1)
                for i in range(TIER_PAGES['overall'])]
    raise ValueError(f'unknown tier {tier!r}')


def basis_gameweek(events: Iterable[dict]) -> int | None:
    """The latest gameweek whose deadline has passed (FPL's is_current)."""
    events = list(events)
    current = [e['id'] for e in events if e.get('is_current')]
    if current:
        return int(current[0])
    started = [e['id'] for e in events if e.get('finished') or e.get('data_checked')]
    return int(max(started)) if started else None


def aggregate(lineups: list[tuple[list, str | None]]) -> dict:
    """Per-element ownership shares from (picks, active_chip) per sampled manager."""
    n = len(lineups)
    owned, started, captained, tripled, multiplier = Counter(), Counter(), Counter(), Counter(), Counter()
    chips = Counter()
    for picks, chip in lineups:
        chips[chip or 'none'] += 1
        for pick in picks:
            owned[pick.element] += 1
            multiplier[pick.element] += pick.multiplier
            if pick.multiplier >= 1:
                started[pick.element] += 1
            if pick.multiplier >= 2:
                captained[pick.element] += 1
            if pick.multiplier >= 3:
                tripled[pick.element] += 1
    pct = (lambda count: round(100.0 * count / n, 2)) if n else (lambda count: 0.0)
    players = {
        str(element): {
            'owned_pct': pct(owned[element]),
            'starting_pct': pct(started[element]),
            'captain_pct': pct(captained[element]),
            'tc_pct': pct(tripled[element]),
            'eo_pct': pct(multiplier[element]),
        }
        for element in owned
    }
    return {'sample_size': n, 'players': players,
            'chips': {name: pct(count) for name, count in chips.most_common()}}


def _with_retry(call: Callable, throttle: Throttle, sleep: Callable[[float], None] = time.sleep):
    for attempt in range(RETRIES):
        throttle.wait()
        try:
            return call()
        except UpstreamRateLimited:
            if attempt == RETRIES - 1:
                raise
            sleep(2.0 * (attempt + 1))
    return None


def fetch_lineups(client, entries: list[int], gameweek: int, throttle: Throttle,
                  workers: int = WORKERS) -> tuple[list, int]:
    """(picks, active_chip) for every entry that answers, and how many failed."""
    def one(entry: int):
        try:
            data, picks = _with_retry(lambda: client._get_picks(entry, gameweek), throttle)
        except (LineupNotFound, ManagerNotFound, FplClientError):
            return None
        return picks, data.get('active_chip')

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, entries))
    lineups = [r for r in results if r is not None]
    return lineups, len(entries) - len(lineups)


def tier_entries(client, tier: str, total_players: int | None, throttle: Throttle,
                 rng: random.Random | None = None) -> list[int]:
    rng = rng or random.Random()
    entries: list[int] = []
    for page in sample_pages(tier, total_players, rng):
        standings = _with_retry(lambda: client.get_league_standings(OVERALL_LEAGUE, page), throttle)
        entries.extend(row.entry_id for row in standings.entries)
    return entries


def league_entries(client, league_id: int, throttle: Throttle) -> tuple[list[int], str]:
    entries, name, page = [], '', 1
    while len(entries) < LEAGUE_MAX_MEMBERS:
        standings = _with_retry(lambda: client.get_league_standings(league_id, page), throttle)
        name = standings.league_name
        entries.extend(row.entry_id for row in standings.entries)
        if not standings.has_next:
            break
        page += 1
    return entries[:LEAGUE_MAX_MEMBERS], name


def build(client, *, tier: str | None = None, league_id: int | None = None,
          gameweek: int, total_players: int | None, selected_by: dict[int, float],
          throttle: Throttle | None = None, rng: random.Random | None = None) -> dict:
    """One ownership report: a tier sample or one league, for `gameweek`'s teams."""
    throttle = throttle or Throttle(REQUESTS_PER_SECOND)
    if league_id is not None:
        entries, label = league_entries(client, league_id, throttle)
        key = f'league:{league_id}'
    else:
        entries, label = tier_entries(client, tier, total_players, throttle, rng), tier
        key = tier
    lineups, failed = fetch_lineups(client, entries, gameweek, throttle)
    report = aggregate(lineups)
    report.update({
        'key': key, 'label': label, 'basis_gw': gameweek,
        'sample_requested': len(entries), 'sample_failed': failed,
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        # Overall selection at sampling time, for estimating later gameweeks.
        'selected_by_at_sample': {str(k): v for k, v in selected_by.items()},
    })
    return report


def with_estimate(report: dict, target_gw: int, selected_by_now: dict[int, float]) -> dict:
    """The report plus, when its basis is an earlier gameweek, an estimated EO for target_gw."""
    out = dict(report)
    out['target_gw'] = target_gw
    out['is_estimate'] = report['basis_gw'] < target_gw
    if not out['is_estimate']:
        return out
    then = report.get('selected_by_at_sample', {})
    lo, hi = ESTIMATE_CLAMP
    players = {}
    for element, row in report['players'].items():
        before, now = then.get(element), selected_by_now.get(int(element))
        factor = (now / before) if before and now is not None else 1.0
        players[element] = {**row, 'eo_estimate_pct': round(min(hi, max(lo, row['eo_pct'] * factor)), 2)}
    out['players'] = players
    return out


def path_for(root: str, season: str, gameweek: int, tier: str) -> str:
    return os.path.join(root, 'data', season, 'ownership', f'gw{gameweek}_{tier}.json')


def save(root: str, season: str, report: dict) -> str:
    path = path_for(root, season, report['basis_gw'], report['key'])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, separators=(',', ':'))
    os.replace(tmp, path)
    return path


def latest(root: str, season: str, tier: str) -> dict | None:
    """The newest saved report for a tier, or None."""
    folder = os.path.join(root, 'data', season, 'ownership')
    if not os.path.isdir(folder):
        return None
    found = []
    for name in os.listdir(folder):
        if name.endswith(f'_{tier}.json') and name.startswith('gw'):
            try:
                found.append((int(name[2:name.index('_')]), name))
            except ValueError:
                continue
    if not found:
        return None
    with open(os.path.join(folder, max(found)[1]), encoding='utf-8') as fh:
        return json.load(fh)
