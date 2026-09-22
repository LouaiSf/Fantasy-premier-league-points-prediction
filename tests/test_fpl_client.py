from __future__ import annotations

import json

import pytest

from webapp.fpl_client import (
    FplClient,
    InvalidUpstreamResponse,
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
