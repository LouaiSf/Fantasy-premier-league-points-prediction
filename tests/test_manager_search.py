from __future__ import annotations

from types import SimpleNamespace

import pytest

import webapp.app as app_module
from webapp.app import app
from webapp.fpl_client import LeagueNotFound, UpstreamRateLimited


def standings_page(page: int, entries=(), has_next: bool = True):
    return SimpleNamespace(
        league_id=314,
        league_name="Test league",
        page=page,
        has_next=has_next,
        entries=tuple(entries),
    )


def league_entry(entry_id: int, manager_name: str, team_name: str):
    return SimpleNamespace(
        entry_id=entry_id,
        manager_name=manager_name,
        team_name=team_name,
        rank=entry_id,
        total_points=500,
    )


def test_league_search_scans_five_pages_and_normalizes_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned: list[int] = []

    def fetch(_league_id: int, page: int):
        scanned.append(page)
        entries = (
            [league_entry(404, "José Rivera", "City Rovers")]
            if page == 4
            else []
        )
        return standings_page(page, entries)

    monkeypatch.setattr(app_module.manager_client, "get_league_standings", fetch)
    response = app.test_client().get(
        "/api/managers/leagues/314/search?q=Jose%20Rovers&cursor=1&limit=5"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert scanned == [1, 2, 3, 4, 5]
    assert [row["entry_id"] for row in payload["results"]] == [404]
    assert payload["scanned_from_page"] == 1
    assert payload["scanned_through_page"] == 5
    assert payload["scanned_entries"] == 1
    assert payload["next_cursor"] == 6
    assert payload["scope"] == "league_pages"


def test_league_search_continue_cursor_covers_page_seven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned: list[int] = []

    def fetch(_league_id: int, page: int):
        scanned.append(page)
        entries = [league_entry(707, "Rina Example", "The Seventh Team")] if page == 7 else []
        return standings_page(page, entries)

    monkeypatch.setattr(app_module.manager_client, "get_league_standings", fetch)
    response = app.test_client().get(
        "/api/managers/leagues/314/search?q=Rina&cursor=6&limit=5"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert scanned == [6, 7, 8, 9, 10]
    assert [row["entry_id"] for row in payload["results"]] == [707]
    assert payload["scanned_from_page"] == 6
    assert payload["scanned_through_page"] == 10
    assert payload["next_cursor"] == 11


def test_league_search_keeps_partial_results_after_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch(_league_id: int, page: int):
        if page == 2:
            raise UpstreamRateLimited("limited")
        return standings_page(page, [league_entry(101, "A Manager", "A Team")])

    monkeypatch.setattr(app_module.manager_client, "get_league_standings", fetch)
    response = app.test_client().get(
        "/api/managers/leagues/314/search?q=Manager&cursor=1&limit=5"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["interrupted"] is True
    assert payload["interrupted_code"] == "upstream_rate_limited"
    assert payload["scanned_through_page"] == 1
    assert payload["next_cursor"] == 2
    assert [row["entry_id"] for row in payload["results"]] == [101]


def test_league_search_maps_initial_not_found_and_rejects_invalid_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_league_id: int, _page: int):
        raise LeagueNotFound("missing")

    monkeypatch.setattr(app_module.manager_client, "get_league_standings", missing)
    client = app.test_client()
    missing_response = client.get(
        "/api/managers/leagues/314/search?q=Example&cursor=1"
    )
    short_query = client.get("/api/managers/leagues/314/search?q=A")
    bad_cursor = client.get(
        "/api/managers/leagues/314/search?q=Example&cursor=0"
    )
    bad_limit = client.get(
        "/api/managers/leagues/314/search?q=Example&limit=6"
    )

    assert missing_response.status_code == 404
    assert missing_response.get_json()["code"] == "league_not_found"
    assert short_query.status_code == 400
    assert bad_cursor.status_code == 400
    assert bad_limit.status_code == 400
