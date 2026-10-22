from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webapp import ownership  # noqa: E402
from webapp.fpl_client import (  # noqa: E402
    LeagueStandingsEntry, LeagueStandingsPage, LineupNotFound, ManagerPick, UpstreamRateLimited,
)


def pick(element, multiplier, position=1):
    return ManagerPick(element=element, position=position, multiplier=multiplier,
                       is_captain=multiplier >= 2, is_vice_captain=False,
                       purchase_price=None, selling_price=None)


class FakeClient:
    """Standings pages of 50 and a picks table, with optional failures."""

    def __init__(self, picks_by_entry, chips=None, missing=(), rate_limited_once=()):
        self.picks_by_entry = picks_by_entry
        self.chips = chips or {}
        self.missing = set(missing)
        self.rate_limited = set(rate_limited_once)
        self.pages_read = []

    def get_league_standings(self, league_id, page=1):
        self.pages_read.append(page)
        entries = sorted(self.picks_by_entry)[(page - 1) * 50: page * 50]
        return LeagueStandingsPage(league_id=league_id, league_name='Mini', page=page,
                                   has_next=page * 50 < len(self.picks_by_entry),
                                   entries=tuple(LeagueStandingsEntry(e, '', '', None, None)
                                                 for e in entries))

    def _get_picks(self, entry, gameweek):
        if entry in self.rate_limited:
            self.rate_limited.discard(entry)
            raise UpstreamRateLimited('slow down')
        if entry in self.missing:
            raise LineupNotFound('no picks')
        return {'active_chip': self.chips.get(entry)}, self.picks_by_entry[entry]


FAST = ownership.Throttle(0)


def test_eo_counts_bench_0_starter_1_captain_2_triple_captain_3() -> None:
    lineups = [
        ([pick(10, 2), pick(20, 1), pick(30, 0)], None),
        ([pick(10, 3), pick(20, 0)], '3xc'),
        ([pick(10, 1), pick(30, 1)], 'bboost'),   # a Bench Boost bench plays
        ([pick(20, 1)], None),
    ]
    out = ownership.aggregate(lineups)
    assert out['sample_size'] == 4
    haaland = out['players']['10']
    assert haaland['eo_pct'] == 150.0 and haaland['owned_pct'] == 75.0
    assert haaland['captain_pct'] == 50.0 and haaland['tc_pct'] == 25.0
    assert out['players']['30']['eo_pct'] == 25.0 and out['players']['30']['starting_pct'] == 25.0
    assert out['chips'] == {'none': 50.0, '3xc': 25.0, 'bboost': 25.0}


def test_basis_is_the_gameweek_whose_deadline_has_passed() -> None:
    events = [{'id': 7, 'is_current': True, 'finished': True}, {'id': 8, 'is_next': True}]
    assert ownership.basis_gameweek(events) == 7
    assert ownership.basis_gameweek([{'id': 1, 'is_next': True}]) is None


def test_failed_entries_shrink_the_sample_and_rate_limits_are_retried(monkeypatch) -> None:
    monkeypatch.setattr(ownership.time, 'sleep', lambda s: None)
    client = FakeClient({1: [pick(10, 2)], 2: [pick(10, 1)], 3: [pick(10, 1)]},
                        missing={3}, rate_limited_once={2})
    lineups, failed = ownership.fetch_lineups(client, [1, 2, 3], 7, FAST)
    assert failed == 1 and len(lineups) == 2
    assert ownership.aggregate(lineups)['players']['10']['eo_pct'] == 150.0


def test_tier_pages() -> None:
    rng = random.Random(0)
    assert ownership.sample_pages('top1k', None, rng) == list(range(1, 21))
    top10k = ownership.sample_pages('top10k', None, rng)
    assert len(top10k) == 20 and max(top10k) <= 200 and len(set(top10k)) == 20
    overall = ownership.sample_pages('overall', 11_000_000, rng)
    assert len(overall) == 20 and max(overall) <= 220_000 and overall[-1] > 200_000
    with pytest.raises(ValueError):
        ownership.sample_pages('top5', None, rng)


def test_league_report_and_estimate_for_the_next_gameweek() -> None:
    client = FakeClient({e: [pick(10, 2 if e % 2 else 1)] for e in range(1, 61)})
    report = ownership.build(client, league_id=99, gameweek=7, total_players=None,
                             selected_by={10: 40.0}, throttle=FAST)
    assert report['sample_size'] == 60 and client.pages_read == [1, 2]
    assert report['players']['10']['eo_pct'] == 150.0
    estimated = ownership.with_estimate(report, 8, {10: 50.0})
    assert estimated['is_estimate'] is True
    assert estimated['players']['10']['eo_estimate_pct'] == 187.5
    assert ownership.with_estimate(report, 7, {10: 50.0})['is_estimate'] is False


def test_saved_reports_round_trip_and_latest_wins(tmp_path) -> None:
    for gw in (6, 7):
        ownership.save(str(tmp_path), 'season', {'key': 'top10k', 'basis_gw': gw, 'players': {}})
    assert ownership.latest(str(tmp_path), 'season', 'top10k')['basis_gw'] == 7
    assert ownership.latest(str(tmp_path), 'season', 'top1k') is None


def test_ownership_route_reports_a_missing_sample_and_rejects_bad_tiers(monkeypatch, tmp_path) -> None:
    from webapp import app as app_module
    monkeypatch.setattr(app_module, 'ROOT', str(tmp_path))
    client = app_module.app.test_client()
    assert client.get('/api/ownership?tier=top5').status_code == 400
    missing = client.get('/api/ownership?tier=top10k')
    assert missing.status_code == 404 and missing.get_json()['code'] == 'ownership_not_built'
