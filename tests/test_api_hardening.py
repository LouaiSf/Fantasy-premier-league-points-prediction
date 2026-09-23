"""Refresh auth, CORS, market-price fail-closed behaviour and request validation."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import webapp.app as webapp_app
from webapp import contracts

client = webapp_app.app.test_client()
REMOTE = {"REMOTE_ADDR": "203.0.113.9"}


@pytest.fixture(autouse=True)
def _clean_guards(monkeypatch):
    monkeypatch.delenv("REFRESH_TOKEN", raising=False)
    webapp_app.reset_refresh_guards()
    yield
    webapp_app.reset_refresh_guards()


def fake_fetch(monkeypatch, returncode=0):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=returncode, stdout="", stderr="")

    monkeypatch.setattr(webapp_app.subprocess, "run", fake_run)
    return calls


def post_raw(path, data, **kwargs):
    return client.post(path, data=data, content_type="application/json", **kwargs)


# --- refresh auth -----------------------------------------------------------
REFRESH_ROUTES = [
    ("post", "/api/refresh"),
    ("post", "/api/refresh/predictions"),
    ("get", "/api/refresh/status"),
    ("post", "/api/reload"),
]


@pytest.mark.parametrize("method,path", REFRESH_ROUTES)
def test_without_a_token_only_direct_local_requests_are_accepted(monkeypatch, method, path):
    fake_fetch(monkeypatch)
    monkeypatch.setattr(webapp_app.pipeline, "run_pipeline",
                        lambda *a, **k: {"first_gw": 1, "last_gw": 2, "players": 1, "warnings": []})
    call = getattr(client, method)

    remote = call(path, environ_overrides=REMOTE)
    assert remote.status_code == 403
    assert remote.get_json()["code"] == "refresh_disabled"

    proxied = call(path, headers={"X-Forwarded-For": "203.0.113.9"})
    assert proxied.status_code == 403, "a proxy on localhost must not count as local"

    assert call(path).status_code in (200, 202)


@pytest.mark.parametrize("method,path", REFRESH_ROUTES)
def test_with_a_token_the_bearer_token_is_required(monkeypatch, method, path):
    monkeypatch.setenv("REFRESH_TOKEN", "s3cret-token")
    calls = fake_fetch(monkeypatch)
    monkeypatch.setattr(webapp_app.pipeline, "run_pipeline",
                        lambda *a, **k: {"first_gw": 1, "last_gw": 2, "players": 1, "warnings": []})
    call = getattr(client, method)

    missing = call(path)
    assert missing.status_code == 401
    assert missing.get_json()["code"] == "refresh_auth_required"
    assert missing.headers["WWW-Authenticate"] == "Bearer"

    for bad in ("Bearer nope", "Bearer ", "s3cret-token", "Basic s3cret-token", "Bearer s3cret-tokén"):
        assert call(path, headers={"Authorization": bad}).status_code == 401, bad
    assert calls == [], "an unauthorised call must never reach the subprocess"

    good = call(path, headers={"Authorization": "Bearer s3cret-token"}, environ_overrides=REMOTE)
    assert good.status_code in (200, 202), "a valid token works from a remote address"


def test_a_blank_token_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("REFRESH_TOKEN", "   ")
    assert client.post("/api/refresh/predictions", environ_overrides=REMOTE).status_code == 403


def test_forbidden_refresh_does_not_start_a_subprocess(monkeypatch):
    calls = fake_fetch(monkeypatch)
    assert client.post("/api/refresh", environ_overrides=REMOTE).status_code == 403
    assert calls == []
    assert webapp_app.fetch_cooldown.remaining() == 0


# --- rate limiting ----------------------------------------------------------
class Clock:
    now = 100.0

    def __call__(self):
        return self.now


def test_rate_limiter_is_a_sliding_window_per_key():
    clock = Clock()
    limiter = webapp_app.RateLimiter(2, window=60, clock=clock)
    assert limiter.check("a") == 0
    assert limiter.check("a") == 0
    assert limiter.check("a") == 60
    assert limiter.check("b") == 0, "another caller has its own budget"
    clock.now += 45
    assert limiter.check("a") == 15
    clock.now += 16
    assert limiter.check("a") == 0


def test_refresh_endpoints_are_rate_limited_including_bad_tokens(monkeypatch):
    monkeypatch.setenv("REFRESH_TOKEN", "s3cret-token")
    monkeypatch.setattr(webapp_app.refresh_limiter, "limit", 3)
    for _ in range(3):
        assert client.post("/api/refresh", headers={"Authorization": "Bearer guess"}).status_code == 401

    limited = client.post("/api/refresh", headers={"Authorization": "Bearer s3cret-token"})

    assert limited.status_code == 429
    assert limited.get_json()["code"] == "rate_limited"
    assert 0 < int(limited.headers["Retry-After"]) <= 60


def test_status_polling_has_its_own_larger_budget(monkeypatch):
    monkeypatch.setattr(webapp_app.refresh_limiter, "limit", 1)
    assert all(client.get("/api/refresh/status").status_code == 200 for _ in range(20))


# --- CORS -------------------------------------------------------------------
def test_origins_default_to_local_dev_and_fail_closed_in_production():
    resolve = webapp_app.resolve_allowed_origins
    assert resolve({}) == webapp_app.DEV_ORIGINS
    assert resolve({"APP_ENV": "production"}) == []
    assert resolve({"APP_ENV": "Production", "ALLOWED_ORIGINS": " "}) == []


def test_explicit_origins_are_normalised_and_wildcard_is_refused_in_production():
    resolve = webapp_app.resolve_allowed_origins
    assert resolve({"ALLOWED_ORIGINS": "https://a.example/, https://b.example"}) == [
        "https://a.example", "https://b.example"]
    assert resolve({"ALLOWED_ORIGINS": "*"}) == ["*"], "dev may opt in by name"
    with pytest.raises(RuntimeError, match="not allowed"):
        resolve({"APP_ENV": "production", "ALLOWED_ORIGINS": "https://a.example,*"})


def test_browsers_on_other_origins_get_no_cors_grant():
    foreign = client.get("/api/meta", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in foreign.headers

    local = client.get("/api/meta", headers={"Origin": "http://localhost:3000"})
    assert local.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


# --- market prices fail closed ---------------------------------------------
def export(elements=(11, 12)) -> pd.DataFrame:
    return pd.DataFrame([
        {"element": e, "name": f"P{e}", "team": "Club", "position": "MID", "value_m": 5.0,
         "GW": 1, "predicted_points": 2.0}
        for e in elements
    ])


@pytest.fixture
def season(tmp_path, monkeypatch):
    root = tmp_path / "data" / "2026-27"
    root.mkdir(parents=True)
    pd.DataFrame([{"id": 1, "name": "Club"}]).to_csv(root / "teams.csv", index=False)
    export().to_csv(tmp_path / "predictions.csv", index=False)
    monkeypatch.setattr(webapp_app, "ROOT", str(tmp_path))
    monkeypatch.setattr(webapp_app.opt, "PREDICTIONS", str(tmp_path / "predictions.csv"))
    monkeypatch.setattr(webapp_app.opt, "infer_next_gameweek", lambda _season, root=None: 1)
    webapp_app.reset_state()
    yield root
    webapp_app.reset_state()


def test_missing_market_file_raises_instead_of_using_export_prices(season):
    with pytest.raises(webapp_app.MarketDataUnavailable, match="not found"):
        webapp_app.join_market_prices(export(), "2026-27")


@pytest.mark.parametrize("content,expected", [
    ("id,other\n11,1\n", "lacks id/now_cost"),
    ("", "unreadable"),
    ("id,now_cost\n99,50\n", "prices only 0 of 2"),
    ("id,now_cost\n11,0\n12,\n", "prices only 0 of 2"),
])
def test_unusable_market_file_raises(season, content, expected):
    (season / "players_raw.csv").write_text(content, encoding="utf-8")
    with pytest.raises(webapp_app.MarketDataUnavailable, match=expected):
        webapp_app.join_market_prices(export(), "2026-27")


def test_market_prices_replace_export_prices_when_available(season):
    pd.DataFrame([{"id": 11, "now_cost": 61}, {"id": 12, "now_cost": 45}]).to_csv(
        season / "players_raw.csv", index=False)
    joined = webapp_app.join_market_prices(export(), "2026-27")
    assert joined.set_index("element")["value_m"].to_dict() == {11: 6.1, 12: 4.5}


PRICE_DEPENDENT = [
    ("get", "/api/players", None),
    ("post", "/api/squad", {"budget": 100}),
    ("post", "/api/lineup", {"elements": list(range(1, 16))}),
    ("post", "/api/transfers", {"elements": list(range(1, 16))}),
    ("post", "/api/chips", {"horizon": 2}),
    ("get", "/api/watchlist", None),
]


def test_without_market_data_price_dependent_routes_are_unavailable(season):
    state = webapp_app.state()

    assert state["error"] is None, "predictions themselves are fine"
    assert "not found" in state["market_error"]
    assert state["players"]["value_m"].isna().all(), "stale export prices must be blanked"

    for method, path, body in PRICE_DEPENDENT:
        response = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert response.status_code == 503, path
        payload = response.get_json()
        assert payload["code"] == "market_prices_unavailable", path
        assert "Market prices are unavailable" in payload["error"]

    meta = client.get("/api/meta").get_json()
    assert meta["predictions_available"] is True
    assert meta["market_prices_available"] is False
    assert "not found" in meta["market_prices_error"]


def test_market_data_recovers_when_the_file_appears(season):
    assert webapp_app.state()["market_error"]
    pd.DataFrame([{"id": 11, "now_cost": 50}, {"id": 12, "now_cost": 50}]).to_csv(
        season / "players_raw.csv", index=False)

    recovered = webapp_app.state()

    assert recovered["market_error"] is None
    assert recovered["players"]["value_m"].tolist() == [5.0, 5.0]
    assert client.get("/api/meta").get_json()["market_prices_available"] is True


def test_missing_predictions_are_a_distinct_unavailable_code(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp_app, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(webapp_app.opt, "PREDICTIONS", str(tmp_path / "nope.csv"))
    webapp_app.reset_state()
    try:
        response = client.post("/api/squad", json={})
        assert response.status_code == 503
        assert response.get_json()["code"] == "predictions_unavailable"
    finally:
        webapp_app.reset_state()


# --- request validation -----------------------------------------------------
def squad_elements() -> list[int]:
    squad = client.post("/api/squad", json={"budget": 100.0}).get_json()
    return [p["element"] for p in squad["xi"] + squad["bench"]]


BODY_ROUTES = ["/api/squad", "/api/lineup", "/api/transfers", "/api/chips"]


@pytest.mark.parametrize("path", BODY_ROUTES + ["/api/refresh/predictions"])
def test_malformed_json_is_a_400_not_a_500(path):
    for raw in ("{not json", "{'a': 1}", '{"budget": ', "\xff\xfe"):
        response = post_raw(path, raw)
        assert response.status_code == 400, (path, raw)
        assert response.get_json()["code"] == "invalid_json"


@pytest.mark.parametrize("path", BODY_ROUTES + ["/api/refresh/predictions"])
@pytest.mark.parametrize("raw", ["[]", '"text"', "5", "null", "true"])
def test_a_body_that_is_not_an_object_is_rejected(path, raw):
    response = post_raw(path, raw)
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_body"


@pytest.mark.parametrize("raw", ['{"budget": NaN}', '{"budget": Infinity}', '{"bank": -Infinity}'])
def test_nan_and_infinity_literals_are_not_json(raw):
    response = post_raw("/api/squad", raw)
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_json"


@pytest.mark.parametrize("path,field", [("/api/squad", "budget"), ("/api/transfers", "bank"),
                                        ("/api/chips", "horizon")])
def test_numbers_that_overflow_to_infinity_are_rejected(path, field):
    # 1e999 is valid JSON syntax but parses to a float infinity.
    payload = '{"elements": %s, "%s": 1e999}' % (squad_elements(), field)
    response = post_raw(path, payload)
    assert response.status_code == 400
    assert response.get_json()["field"] == field
    assert response.get_json()["code"] == "invalid_field"


def test_an_empty_body_means_defaults():
    assert post_raw("/api/squad", "").status_code == 200


@pytest.mark.parametrize("body,field", [
    ({"budget": "100"}, "budget"),
    ({"budget": True}, "budget"),
    ({"budget": 5}, "budget"),
    ({"budget": [100]}, "budget"),
    ({"lock": "Haaland"}, "lock"),
    ({"lock": [1, 2]}, "lock"),
    ({"ban": {"a": 1}}, "ban"),
    ({"lock": ["x" * 500]}, "lock"),
])
def test_squad_rejects_bad_fields_with_the_field_named(body, field):
    response = client.post("/api/squad", json=body)
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "invalid_field" and payload["field"] == field


def test_squad_reports_unknown_locked_players_with_a_code():
    response = client.post("/api/squad", json={"lock": ["Definitely Not A Player"]})
    assert response.status_code == 400
    assert response.get_json()["code"] == "unknown_player"


@pytest.mark.parametrize("body,field", [
    ({"free": 1.5}, "free"),
    ({"free": "1"}, "free"),
    ({"free": 6}, "free"),
    ({"free": True}, "free"),
    ({"bank": -1}, "bank"),
    ({"bank": "0"}, "bank"),
    ({"max": 2.5}, "max"),
    ({"max": None, "elements": "x"}, "elements"),
    ({"selling_prices_tenths": [1]}, "selling_prices_tenths"),
    ({"selling_prices_tenths": {"a": 5}}, "selling_prices_tenths"),
])
def test_transfers_reject_bad_fields(body, field):
    payload = {"elements": squad_elements(), **body}
    response = client.post("/api/transfers", json=payload)
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_field"
    assert response.get_json()["field"] == field


@pytest.mark.parametrize("elements", [[], None, [1.5] * 15, ["1"] * 15, [0] * 15, [-3] * 15,
                                      list(range(1, 200))])
def test_transfers_reject_bad_element_lists(elements):
    response = client.post("/api/transfers", json={"elements": elements})
    assert response.status_code == 400
    assert response.get_json()["code"] in {"invalid_field", "invalid_squad"}


def test_unknown_element_ids_have_their_own_code():
    elements = squad_elements()
    elements[0] = 99_999_999
    for path in ("/api/transfers", "/api/lineup"):
        response = client.post(path, json={"elements": elements})
        assert response.status_code == 400, path
        payload = response.get_json()
        assert payload["code"] == "unknown_player"
        assert "99999999" in payload["error"]


def test_duplicate_elements_are_an_invalid_squad():
    elements = squad_elements()
    elements[1] = elements[0]
    response = client.post("/api/transfers", json={"elements": elements})
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_squad"


@pytest.mark.parametrize("body", [
    {"elements": ["a"] * 15},
    {"elements": "1,2,3"},
    {"elements": [True] * 15},
    {"squad": "Haaland"},
    {"squad": [1] * 15},
])
def test_lineup_rejects_bad_identities(body):
    response = client.post("/api/lineup", json=body)
    assert response.status_code == 400
    assert response.get_json()["code"] in {"invalid_field", "invalid_squad"}


@pytest.mark.parametrize("body,field", [
    ({"horizon": "8"}, "horizon"),
    ({"horizon": 0}, "horizon"),
    ({"horizon": 39}, "horizon"),
    ({"horizon": 2.5}, "horizon"),
    ({"scheduled_gameweeks": "6"}, "scheduled_gameweeks"),
    ({"scheduled_gameweeks": [99]}, "scheduled_gameweeks"),
    ({"scheduled_gameweeks": [True]}, "scheduled_gameweeks"),
    ({"scheduled_gameweeks": [6.5]}, "scheduled_gameweeks"),
    ({"last_free_hit_gameweek": "x"}, "last_free_hit_gameweek"),
    ({"last_free_hit_gameweek": 0}, "last_free_hit_gameweek"),
    ({"bank": 101}, "bank"),
    ({"chip_inventory": [1, 2]}, "chip_inventory"),
    ({"chip_inventory": "used"}, "chip_inventory"),
])
def test_chips_reject_bad_fields(body, field):
    response = client.post("/api/chips", json=body)
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "invalid_field" and payload["field"] == field


def test_chips_unknown_squad_name_is_a_400_not_a_crash():
    names = ["Not A Real Player %d" % i for i in range(15)]
    response = client.post("/api/chips", json={"squad": names})
    assert response.status_code == 400
    assert response.get_json()["code"] == "unknown_player"


def test_chips_accepts_valid_optional_fields():
    response = client.post("/api/chips", json={
        "horizon": 4, "scheduled_gameweeks": [8], "last_free_hit_gameweek": 5,
        "chip_inventory": {"first_half": {"wildcard": "used"}}, "bank": None})
    assert response.status_code == 200


@pytest.mark.parametrize("query", ["max_ownership=nan", "max_ownership=inf", "max_ownership=abc",
                                   "max_ownership=101", "top=abc", "top=1.5", "top=0", "top=nan",
                                   "top=99999"])
def test_watchlist_rejects_bad_query_values(query):
    response = client.get(f"/api/watchlist?{query}")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_field"


def test_watchlist_accepts_defaults_and_valid_values():
    assert client.get("/api/watchlist").status_code == 200
    assert client.get("/api/watchlist?max_ownership=5&top=3").status_code == 200


# --- consistent errors and the contract -------------------------------------
def test_unknown_routes_and_methods_are_json_client_errors():
    missing = client.get("/api/definitely-not-a-route")
    assert missing.status_code == 404 and missing.get_json()["code"] == "not_found"

    wrong = client.get("/api/squad")
    assert wrong.status_code == 405 and wrong.get_json()["code"] == "method_not_allowed"


def test_oversized_bodies_are_rejected():
    response = post_raw("/api/squad", '{"lock": ["' + "x" * (contracts.MAX_BODY_BYTES + 10) + '"]}')
    assert response.status_code == 413
    assert response.get_json()["code"] == "payload_too_large"


def test_unexpected_errors_are_500_without_leaking_internals(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret path C:/internal/thing.csv")

    monkeypatch.setattr(webapp_app.opt, "compute_watchlist", explode)
    response = client.get("/api/watchlist")
    assert response.status_code == 500
    payload = response.get_json()
    assert payload["code"] == "internal_error"
    assert "secret" not in payload["error"]


def test_every_api_response_carries_the_contract_version():
    responses = [
        client.get("/api/meta"),
        client.post("/api/squad", json={}),
        client.post("/api/squad", json={"budget": "x"}),           # error
        client.get("/api/nope"),                                   # 404
        client.get("/api/watchlist"),
    ]
    for response in responses:
        assert response.headers["X-API-Contract-Version"] == str(contracts.API_CONTRACT_VERSION)
        assert response.get_json()["api_contract_version"] == contracts.API_CONTRACT_VERSION


def test_chips_keeps_its_own_contract_version_alongside():
    payload = client.post("/api/chips", json={"horizon": 2}).get_json()
    assert payload["contract_version"] == webapp_app.opt.CHIPS_CONTRACT_VERSION
    assert payload["api_contract_version"] == contracts.API_CONTRACT_VERSION


def test_all_error_bodies_share_one_shape():
    bodies = [
        client.post("/api/squad", json={"budget": "x"}).get_json(),
        client.post("/api/transfers", json={"elements": []}).get_json(),
        client.get("/api/watchlist?top=x").get_json(),
        post_raw("/api/squad", "{").get_json(),
        client.get("/api/nope").get_json(),
    ]
    for body in bodies:
        assert body["ok"] is False
        assert isinstance(body["error"], str) and body["error"]
        assert isinstance(body["code"], str) and body["code"]
