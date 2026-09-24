from __future__ import annotations

import json

import pytest

from webapp.fpl_client import (
    FplClient,
    InvalidUpstreamResponse,
    LeagueNotFound,
    ManagerNotFound,
    SearchNotConfigured,
    UpstreamUnavailable,
)
from webapp import fpl_client


@pytest.fixture(autouse=True)
def clear_client_cache() -> None:
    fpl_client._CACHE.clear()


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_numeric_entry_normalizes_manager_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_open(request, timeout):
        calls.append(request.full_url)
        return FakeResponse({
            "id": 123,
            "player_first_name": "First",
            "player_last_name": "Last",
            "name": "Example XI",
            "summary_overall_rank": 42,
            "summary_overall_points": 231,
            "current_event": 7,
            "bank": 12,
            "value": 1000,
        })

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)

    summary = FplClient().get_entry(123)

    assert summary.entry_id == 123
    assert summary.manager_name == "First Last"
    assert summary.team_name == "Example XI"
    assert summary.overall_rank == 42
    assert summary.total_points == 231
    assert summary.current_event == 7
    assert calls == ["https://fantasy.premierleague.com/api/entry/123/"]


def test_lineup_normalizes_prices_and_keeps_fpl_position_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = {
        "/entry/123/": {
            "id": 123,
            "player_first_name": "First",
            "player_last_name": "Last",
            "name": "Example XI",
            "summary_overall_rank": 42,
            "summary_overall_points": 231,
            "current_event": 7,
            "bank": 12,
            "value": 1000,
        },
        "/entry/123/event/7/picks/": {
            "entry": 123,
            "event": 7,
            "picks": [
                {"element": 9, "position": 2, "multiplier": 1, "is_captain": False,
                 "is_vice_captain": True, "purchase_price": 55, "selling_price": 56},
                {"element": 8, "position": 1, "multiplier": 2, "is_captain": True,
                 "is_vice_captain": False, "purchase_price": 45, "selling_price": 46},
            ],
        },
    }

    def fake_open(request, timeout):
        path = request.full_url.removeprefix("https://fantasy.premierleague.com/api")
        return FakeResponse(payloads[path])

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)

    lineup = FplClient().get_lineup(123, requested_gameweek=7)

    assert lineup.lineup_gameweek == 7
    assert [pick.element for pick in lineup.picks] == [8, 9]
    assert lineup.picks[0].purchase_price == 4.5
    assert lineup.picks[1].selling_price == 5.6


def test_lineup_keeps_missing_account_prices_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request, timeout):
        path = request.full_url.removeprefix("https://fantasy.premierleague.com/api")
        if path == "/entry/123/":
            return FakeResponse({"id": 123, "current_event": 7, "bank": 0})
        return FakeResponse({"event": 7, "picks": [{
            "element": 8, "position": 1, "multiplier": 1,
            "is_captain": False, "is_vice_captain": False,
        }]})

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)
    lineup = FplClient().get_lineup(123, requested_gameweek=7)

    assert lineup.picks[0].purchase_price is None
    assert lineup.picks[0].selling_price is None


def test_lineup_falls_back_to_previous_public_event(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request, timeout):
        path = request.full_url.removeprefix("https://fantasy.premierleague.com/api")
        if path == "/entry/123/":
            return FakeResponse({"id": 123, "current_event": 7})
        if path.endswith("/event/7/picks/"):
            return FakeResponse({}, status=404)
        return FakeResponse({"entry": 123, "event": 6, "picks": []})

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)

    lineup = FplClient().get_lineup(123)

    assert lineup.requested_gameweek is None
    assert lineup.lineup_gameweek == 6


def test_invalid_json_and_timeout_are_typed_upstream_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_open(request, timeout):
        return FakeResponse({})

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", invalid_open)
    with pytest.raises(InvalidUpstreamResponse):
        FplClient().get_entry(123)

    def timeout_open(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", timeout_open)
    with pytest.raises(UpstreamUnavailable):
        FplClient().get_entry(123)


def test_missing_entry_is_typed_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request, timeout):
        return FakeResponse({}, status=404)

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)

    with pytest.raises(ManagerNotFound):
        FplClient().get_entry(123)


def test_text_search_requires_a_configured_contract() -> None:
    with pytest.raises(SearchNotConfigured):
        FplClient().search_text("First Last")


def test_league_standings_normalizes_entries_and_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_open(request, timeout):
        calls.append(request.full_url)
        return FakeResponse({
            "league": {"id": 314, "name": "Overall"},
            "standings": {
                "has_next": True,
                "page": 2,
                "results": [
                    {"entry": 895045, "player_name": "Jasper Selvaraj",
                     "entry_name": "Jake Crow Sliced Jam", "rank": 1, "total": 468},
                    {"entry": 5151567, "player_name": "Chris Greenwood",
                     "entry_name": "I Want It Stach Way", "rank": 2, "total": 456},
                ],
            },
        })

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)

    page = FplClient().get_league_standings(314, page=2)

    assert page.league_id == 314
    assert page.league_name == "Overall"
    assert page.has_next is True
    assert [entry.entry_id for entry in page.entries] == [895045, 5151567]
    assert page.entries[0].manager_name == "Jasper Selvaraj"
    assert page.entries[0].team_name == "Jake Crow Sliced Jam"
    assert calls == ["https://fantasy.premierleague.com/api/leagues-classic/314/standings/?page_standings=2"]


def test_league_standings_typed_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(request, timeout):
        return FakeResponse({}, status=404)

    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)

    with pytest.raises(LeagueNotFound):
        FplClient().get_league_standings(999999999)


def test_league_standings_cache_lasts_sixty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100.0]
    calls: list[str] = []

    def fake_open(request, timeout):
        calls.append(request.full_url)
        return FakeResponse({
            "league": {"name": "Overall"},
            "standings": {"has_next": True, "results": []},
        })

    monkeypatch.setattr(fpl_client.time, "monotonic", lambda: now[0])
    monkeypatch.setattr("webapp.fpl_client.request.urlopen", fake_open)
    client = FplClient()

    client.get_league_standings(314, page=1)
    now[0] = 159.0
    client.get_league_standings(314, page=1)
    now[0] = 161.0
    client.get_league_standings(314, page=1)

    assert len(calls) == 2
