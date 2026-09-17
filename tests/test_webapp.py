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

    # When predictions are loaded through the real application boundary.
    result = app_module.reload_predictions()

    # Then the optimizer is disabled instead of joining season-scoped player ids.
    assert "does not match local season 2026-27" in result["error"]
    assert result["players"].empty
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
