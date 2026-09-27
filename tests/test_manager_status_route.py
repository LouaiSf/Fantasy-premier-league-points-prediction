from __future__ import annotations

import webapp.app as app_module
from webapp.app import app
from webapp.fpl_client import ChipPlayed, HistoryEntry, ManagerHistory, ManagerSummary


def test_status_route_reports_inventory_and_free_transfers(monkeypatch) -> None:
    summary = ManagerSummary(
        entry_id=1, manager_name="Test Manager", team_name="Test FC",
        overall_rank=100, total_points=300, current_event=6, bank=2.5, team_value=101.2,
    )
    history = ManagerHistory(
        chips=(ChipPlayed(name="wildcard", event=4),),
        current=(
            HistoryEntry(event=2, event_transfers=1, event_transfers_cost=0, bank=0.0, value=1000.0),
            HistoryEntry(event=3, event_transfers=1, event_transfers_cost=0, bank=0.0, value=1000.0),
            HistoryEntry(event=4, event_transfers=8, event_transfers_cost=0, bank=0.0, value=1000.0),
            HistoryEntry(event=5, event_transfers=0, event_transfers_cost=0, bank=0.0, value=1000.0),
            HistoryEntry(event=6, event_transfers=0, event_transfers_cost=0, bank=25.0, value=1012.0),
        ),
    )
    monkeypatch.setattr(app_module.manager_client, "get_entry", lambda entry_id: summary)
    monkeypatch.setattr(app_module.manager_client, "get_history", lambda entry_id: history)

    response = app.test_client().get("/api/managers/1/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["gameweek"] == 7
    assert payload["chip_inventory"]["first_half"]["wildcard"] == "used"
    assert payload["chip_inventory"]["first_half"]["bench_boost"] == "unused"
    assert payload["last_free_hit_gameweek"] is None
    assert payload["free_transfers"] == 4
    assert payload["bank"] == 2.5
    assert payload["source"] == "fpl_public"


def test_status_route_maps_manager_not_found(monkeypatch) -> None:
    from webapp.fpl_client import ManagerNotFound

    def raise_not_found(entry_id: int):
        raise ManagerNotFound("no such entry")

    monkeypatch.setattr(app_module.manager_client, "get_entry", raise_not_found)

    response = app.test_client().get("/api/managers/999999999/status")
    assert response.status_code == 404
    assert response.get_json()["code"] == "manager_not_found"
