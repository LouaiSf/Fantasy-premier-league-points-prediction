from __future__ import annotations

import pandas as pd
import pytest

import webapp.app as app_module
from webapp.app import app


def test_platform_api_meta_and_platform() -> None:
    # Given the production Flask API application.
    client = app.test_client()

    # When meta and platform endpoints are requested.
    meta_res = client.get("/api/meta")
    assert meta_res.status_code == 200
    meta = meta_res.get_json()
    assert meta["ok"] is True
    assert meta["season"] == "2026-27"
    assert "model" in meta

    plat_res = client.get("/api/platform")
    assert plat_res.status_code == 200
    plat = plat_res.get_json()
    assert plat["ok"] is True
    assert len(plat["teams"]) == 20
    assert len(plat["players"]) > 0


def test_reload_predictions_rejects_a_different_league_roster(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given local season clubs that differ from the prediction export.
    season = tmp_path / "data" / "2026-27"
    season.mkdir(parents=True)
    (season / "teams.csv").write_text("id,name\n1,Burnley\n", encoding="utf-8")
    (tmp_path / "predictions_next_gw.csv").write_text("placeholder", encoding="utf-8")
    predictions = pd.DataFrame([{"team": "Hull City"}])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_module.opt, "PREDICTIONS", "predictions_next_gw.csv")
    monkeypatch.setattr(app_module.opt, "load_predictions", lambda *_args, **_kwargs: predictions)
    monkeypatch.setattr(app_module.opt, "infer_next_gameweek", lambda _season: 1)
    app_module._state.clear()

    result = app_module.reload_predictions()

    assert "does not match local season 2026-27" in result["error"]
    assert result["players"].empty
    app_module._state.clear()


def test_reload_predictions_keeps_current_table_and_stable_horizon_matrix(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    season = tmp_path / "data" / "2026-27"
    season.mkdir(parents=True)
    pd.DataFrame([{"id": 1, "name": "Club"}]).to_csv(season / "teams.csv", index=False)
    prediction_path = tmp_path / "predictions.csv"
    pd.DataFrame([
        {"element": 11, "name": "One", "team": "Club", "position": "MID", "value_m": 5.0, "GW": 1, "predicted_points": 2.0},
        {"element": 11, "name": "One", "team": "Club", "position": "MID", "value_m": 5.0, "GW": 2, "predicted_points": 8.0},
        {"element": 12, "name": "Two", "team": "Club", "position": "MID", "value_m": 5.0, "GW": 1, "predicted_points": 3.0},
        {"element": 12, "name": "Two", "team": "Club", "position": "MID", "value_m": 5.0, "GW": 2, "predicted_points": 4.0},
    ]).to_csv(prediction_path, index=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_module.opt, "PREDICTIONS", str(prediction_path))
    monkeypatch.setattr(app_module.opt, "infer_next_gameweek", lambda _season: 1)
    app_module._state.clear()

    state = app_module.reload_predictions()

    assert state["players"].set_index("element")["predicted_points"].to_dict() == {11: 2.0, 12: 3.0}
    assert state["future_gameweeks"] == [1, 2]
    by_element = state["future_points"].set_axis(state["players"]["element"])
    assert by_element.loc[11].to_dict() == {1: 2.0, 2: 8.0}
    assert by_element.loc[12].to_dict() == {1: 3.0, 2: 4.0}

    received = {}

    def capture_chip_inputs(*_args, **kwargs):
        received.update(kwargs)
        return {"recommendations": [], "projection_gameweeks": [1, 2]}

    monkeypatch.setattr(app_module.opt, "compute_chips", capture_chip_inputs)
    response = app.test_client().post("/api/chips", json={"horizon": 2})
    assert response.status_code == 200
    assert received["future_points"].to_numpy().tolist() == [[3.0, 4.0], [2.0, 8.0]]
    assert response.get_json()["projection_gameweeks"] == [1, 2]
    app_module._state.clear()


def test_player_history_endpoint() -> None:
    client = app.test_client()
    res = client.get("/api/player/42/history")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert isinstance(data["history"], list)


def test_watchlist_endpoint() -> None:
    client = app.test_client()
    res = client.get("/api/watchlist")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "value" in data
    assert "differentials" in data


def test_lineup_endpoint_optimises_a_supplied_team() -> None:
    client = app.test_client()
    squad_res = client.post('/api/squad', json={'budget': 100.0})
    assert squad_res.status_code == 200
    squad = squad_res.get_json()
    elements = [player['element'] for player in squad['xi'] + squad['bench']]

    response = client.post('/api/lineup', json={'elements': elements})

    assert response.status_code == 200
    lineup = response.get_json()
    assert len(lineup['xi']) == 11
    assert len(lineup['bench']) == 4
    assert lineup['bench'][-1]['position'] == 'GK'
    assert lineup['captain']['element'] != lineup['vice_captain']['element']
    assert {lineup['captain']['element'], lineup['vice_captain']['element']} <= {
        player['element'] for player in lineup['xi']
    }


def test_auto_pick_serializes_identity_and_portrait_contract() -> None:
    client = app.test_client()

    response = client.post('/api/squad', json={'budget': 100.0})

    assert response.status_code == 200
    squad = response.get_json()
    for player in squad['xi'] + squad['bench']:
        assert player['element'] is not None
        assert player['web_name']
        assert player['first_name']
        assert player['second_name']
        assert 'photo' in player
        assert 'photo_large' in player
        assert 'team_id' in player
    assert squad['captain']['photo'] is not None
    assert squad['vice_captain']['photo'] is not None


def test_refresh_pulls_the_live_source_and_forces_it(monkeypatch) -> None:
    # vaastav archives finished seasons; only olbauday carries one in
    # progress. And without --force every existing file is skipped, so the
    # button reported success while refreshing nothing.
    import webapp.app as webapp_app

    seen = {}

    class Result:
        stdout = ""

    def fake_run(command, **kwargs):
        seen["command"] = command
        return Result()

    monkeypatch.setattr(webapp_app.subprocess, "run", fake_run)
    response = webapp_app.app.test_client().post("/api/refresh")

    assert response.status_code == 200
    assert "--force" in seen["command"]
    assert "olbauday" in seen["command"]
    assert seen["command"][seen["command"].index("--source") + 1] == "olbauday"


def test_manager_search_numeric_and_text_contract(monkeypatch) -> None:
    client = app.test_client()

    class Summary:
        entry_id = 123
        manager_name = "First Last"
        team_name = "Example XI"
        overall_rank = 42
        total_points = 231

    monkeypatch.setattr(app_module.manager_client, "get_entry", lambda _entry_id: Summary())

    numeric = client.get("/api/managers/search?q=123")
    assert numeric.status_code == 200
    assert numeric.get_json()["results"][0]["entry_id"] == 123

    text = client.get("/api/managers/search?q=First%20Last")
    assert text.status_code == 503
    assert text.get_json()["code"] == "search_not_configured"


def test_manager_lineup_returns_missing_local_elements(monkeypatch) -> None:
    client = app.test_client()

    class Summary:
        entry_id = 123
        manager_name = "First Last"
        team_name = "Example XI"
        overall_rank = 42
        total_points = 231
        current_event = 7
        bank = 1.2
        team_value = 100.0
        event_points = 55
        event_rank = 10
        active_chip = None

    class Pick:
        element = 999999
        position = 1
        multiplier = 2
        is_captain = True
        is_vice_captain = False
        purchase_price = 4.5
        selling_price = 4.6

    class Lineup:
        summary = Summary()
        requested_gameweek = None
        lineup_gameweek = 7
        picks = (Pick(),)

    monkeypatch.setattr(app_module.manager_client, "get_lineup", lambda _entry_id, **_kwargs: Lineup())

    response = client.get("/api/managers/123/lineup")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["missing_elements"] == [999999]
    assert payload["manager"]["entry_id"] == 123


def test_transfers_accept_element_ids_and_return_current_lineup() -> None:
    client = app.test_client()
    squad = client.post("/api/squad", json={"budget": 100.0}).get_json()
    elements = [player["element"] for player in squad["xi"] + squad["bench"]]

    response = client.post(
        "/api/transfers",
        json={"elements": elements, "free": 0, "bank": 0.0, "max": 0},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["current_lineup"]["bench"]) == 4
    assert payload["rows"][0]["captained_total"] == payload["rows"][0]["gross"]
    assert set(payload["current_lineup"]) == {
        "ok", "budget", "spend", "xi", "bench", "captain",
        "vice_captain", "xi_points", "formation",
    }


def test_transfers_reject_legacy_name_identity() -> None:
    client = app.test_client()
    squad = client.post("/api/squad", json={"budget": 100.0}).get_json()
    names = [player["name"] for player in squad["xi"] + squad["bench"]]

    response = client.post("/api/transfers", json={"squad": names, "free": 0, "max": 0})

    assert response.status_code == 400
    assert response.get_json()["error"] == "elements must be a list of numeric FPL element IDs"


def test_transfers_reject_boolean_element_ids() -> None:
    client = app.test_client()
    response = client.post(
        "/api/transfers",
        json={"elements": [True] * 15, "free": 0, "max": 0},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "elements must be a list of numeric FPL element IDs"


def test_chips_response_matches_the_frontend_contract() -> None:
    # Given the generic (no-squad) fixture-signal mode the chip advisor falls back to.
    client = app.test_client()

    response = client.post("/api/chips", json={"horizon": 4})

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["contract_version"] == app_module.opt.CHIPS_CONTRACT_VERSION
    required_top_level = {
        "first_gw", "last_gw", "any_dgw", "any_bgw", "has_squad", "rows",
        "recommendations", "current_gameweek", "projection_mode",
        "inventory_status", "inventory_sync_state", "scheduled_gameweeks",
        "projection_source", "projection_generated_at", "projection_gameweeks",
        "requested_horizon", "evaluated_horizon", "coverage_warning",
        "data_quality", "methodology_version", "decision_policy",
    }
    assert required_top_level <= data.keys()
    assert isinstance(data["projection_gameweeks"], list)

    for row in data["rows"]:
        assert {"gw", "matches", "dgw_teams", "blank_teams", "avg_fdr",
                "projected_gain", "fixture_signal_index"} <= row.keys()

    for rec in data["recommendations"]:
        assert {"chip", "label", "status", "candidate_gameweeks", "gw",
                "candidate_gw", "projected_gain", "fixture_signal_index",
                "alternatives", "decision_policy", "reasons", "warnings",
                "confidence"} <= rec.keys()
        assert {"minimum_projected_gain", "uncertainty_note", "basis"} <= rec["decision_policy"].keys()
