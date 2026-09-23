"""Shared-state safety, prediction artifacts, and operational monitoring."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

import webapp.app as webapp_app
import webapp.platform_data as platform_data
from scripts import artifacts, refresh_pipeline as pipeline
from webapp import observability as obs

client = webapp_app.app.test_client()
PROJECT = Path(__file__).resolve().parent.parent
SEASON = "2026-27"
REMOTE = {"REMOTE_ADDR": "203.0.113.9"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("REQUIRE_ARTIFACT_MANIFEST", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    webapp_app.reset_refresh_guards()
    obs.reset_alert_log()
    yield
    webapp_app.reset_refresh_guards()
    webapp_app.reset_state()


def export(points: float = 2.0, elements=(11, 12)) -> pd.DataFrame:
    return pd.DataFrame([
        {"element": e, "name": f"P{e}", "team": "Club", "position": "MID", "value_m": 5.0,
         "GW": 1, "predicted_points": points}
        for e in elements
    ])


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A complete throwaway project root: predictions, market prices, teams, fixtures."""
    season = tmp_path / "data" / SEASON
    season.mkdir(parents=True)
    pd.DataFrame([{"id": 1, "name": "Club", "short_name": "CLB"}]).to_csv(season / "teams.csv", index=False)
    pd.DataFrame([{"id": 11, "now_cost": 50}, {"id": 12, "now_cost": 50}]).to_csv(
        season / "players_raw.csv", index=False)
    pd.DataFrame([{"event": 1, "kickoff_time": "2026-08-21T19:00:00Z", "finished": False}]).to_csv(
        season / "fixtures.csv", index=False)
    export().to_csv(tmp_path / "predictions.csv", index=False)
    monkeypatch.setattr(webapp_app, "ROOT", str(tmp_path))
    monkeypatch.setattr(webapp_app.opt, "PREDICTIONS", "predictions.csv")
    monkeypatch.setattr(webapp_app.opt, "infer_next_gameweek", lambda _season, root=None: 1)
    webapp_app.reset_state()
    return tmp_path


def touch(path: Path, seconds: float = 5.0) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + int(seconds * 1e9)))


# --- immutable snapshots and locking ----------------------------------------
def test_the_snapshot_is_read_only(site):
    snapshot = webapp_app.state()
    with pytest.raises(TypeError):
        snapshot["players"] = None
    with pytest.raises(TypeError):
        del snapshot["error"]


def test_a_reload_replaces_the_snapshot_and_leaves_the_old_one_intact(site):
    old = webapp_app.state()
    export(points=9.0).to_csv(site / "predictions.csv", index=False)

    new = webapp_app.state()

    assert new is not old
    assert set(old["players"]["predicted_points"]) == {2.0}, "a held snapshot must not change"
    assert set(new["players"]["predicted_points"]) == {9.0}
    assert webapp_app.state() is new, "a fresh snapshot is reused, not rebuilt"


def test_a_changed_fixtures_file_now_triggers_a_reload(site):
    first = webapp_app.state()
    touch(site / "data" / SEASON / "fixtures.csv")
    assert webapp_app.state() is not first


def test_maintenance_serves_the_last_good_snapshot_while_files_change(site):
    before = webapp_app.state()
    with webapp_app.maintenance():
        export(points=9.0).to_csv(site / "predictions.csv", index=False)
        assert webapp_app.state() is before, "readers must not see a half-written refresh"
        with webapp_app.maintenance():
            assert webapp_app.state() is before, "maintenance nests"
        assert webapp_app.state() is before
    assert set(webapp_app.state()["players"]["predicted_points"]) == {9.0}


def test_concurrent_readers_and_a_rewriting_writer_never_see_mixed_data(site, monkeypatch):
    builds = {"running": 0, "peak": 0, "total": 0}
    real_build = webapp_app._build_snapshot

    def counted_build():
        builds["running"] += 1
        builds["peak"] = max(builds["peak"], builds["running"])
        builds["total"] += 1
        try:
            time.sleep(0.003)   # widen the window a race would need
            return real_build()
        finally:
            builds["running"] -= 1

    monkeypatch.setattr(webapp_app, "_build_snapshot", counted_build)
    webapp_app.state()      # something good must be loaded before the files start changing
    builds.update(running=0, peak=0, total=0)
    stop = threading.Event()
    problems: list[str] = []
    reads = []

    def reader():
        while not stop.is_set():
            try:
                snapshot = webapp_app.state()
                values = set(snapshot["players"]["predicted_points"])
                prices = set(snapshot["players"]["value_m"])
                if len(values) != 1 or len(prices) != 1:
                    problems.append(f"mixed snapshot: {values} {prices}")
                reads.append(1)
            except Exception as exc:   # noqa: BLE001 - any failure is a finding
                problems.append(repr(exc))

    def writer():
        for i in range(12):
            export(points=2.0 + (i % 2) * 5).to_csv(site / "predictions.csv", index=False)
            touch(site / "predictions.csv", seconds=i + 1)
            time.sleep(0.01)

    threads = [threading.Thread(target=reader) for _ in range(6)]
    for thread in threads:
        thread.start()
    writer()
    time.sleep(0.05)
    stop.set()
    for thread in threads:
        thread.join(5)

    assert problems == []
    assert builds["peak"] == 1, "snapshot rebuilds must be serialised"
    assert len(reads) > builds["total"], "readers must share builds, not each do their own"


def test_reset_state_forces_a_rebuild(site):
    first = webapp_app.state()
    webapp_app.reset_state()
    assert webapp_app.state() is not first


# --- no process-wide chdir ---------------------------------------------------
def test_importing_the_app_does_not_change_the_working_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", "import os, webapp.app; print(os.getcwd())"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(PROJECT)})
    assert result.returncode == 0, result.stderr[-500:]
    assert Path(result.stdout.strip().splitlines()[-1]).resolve() == tmp_path.resolve()


def test_the_api_works_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    webapp_app.reset_state()
    assert client.get("/api/meta").get_json()["predictions_available"] is True
    assert client.get("/api/platform").status_code == 200
    assert client.post("/api/squad", json={}).status_code == 200
    assert client.post("/api/chips", json={"horizon": 3}).status_code == 200


# --- caches keyed by file modification time ----------------------------------
def test_platform_payload_is_cached_until_a_source_file_changes(site, monkeypatch):
    builds = []

    def fake_build(root, season):
        builds.append(season)
        return {"players": [], "teams": [], "season": season}

    monkeypatch.setattr(webapp_app, "build_local_snapshot", fake_build)
    monkeypatch.setattr(webapp_app, "_platform_cache", None)

    assert client.get("/api/platform").status_code == 200
    assert client.get("/api/platform").status_code == 200
    assert len(builds) == 1, "the second request must be served from the cache"

    touch(site / "data" / SEASON / "teams.csv")
    client.get("/api/platform")
    assert len(builds) == 2, "a changed source file invalidates it"

    with webapp_app.maintenance():
        touch(site / "data" / SEASON / "teams.csv", seconds=9)
        client.get("/api/platform")
    assert len(builds) == 2, "during a refresh the last good payload is served"


def test_enriched_players_are_built_once_per_snapshot(site, monkeypatch):
    calls = []
    real = webapp_app._build_enriched
    monkeypatch.setattr(webapp_app, "_build_enriched", lambda s: calls.append(1) or real(s))
    monkeypatch.setattr(webapp_app, "_enriched_cache", None)
    snapshot = webapp_app.state()

    first = webapp_app.enriched_players(snapshot)
    second = webapp_app.enriched_players(snapshot)

    assert first is second and len(calls) == 1
    touch(site / "data" / SEASON / "players_raw.csv")
    webapp_app.enriched_players(webapp_app.state())
    assert len(calls) == 2


def test_player_history_rows_are_cached_by_modification_time(tmp_path, monkeypatch):
    path = tmp_path / "merged_gw.csv"
    path.write_text("element,GW\n1,1\n", encoding="utf-8")
    parses = []
    real = platform_data._read_rows
    monkeypatch.setattr(platform_data, "_read_rows", lambda p: parses.append(1) or real(p))
    monkeypatch.setattr(platform_data, "_ROW_CACHE", {})

    assert platform_data._read_rows_cached(path) is platform_data._read_rows_cached(path)
    assert len(parses) == 1

    path.write_text("element,GW\n1,1\n2,2\n", encoding="utf-8")
    assert len(platform_data._read_rows_cached(path)) == 2
    assert len(parses) == 2


# --- artifacts ---------------------------------------------------------------
def make_artifact(tmp_path) -> str:
    csv_path = tmp_path / "predictions.csv"
    export().to_csv(csv_path, index=False)
    return str(csv_path)


def write_manifest_for(tmp_path, csv_path: str, **overrides) -> dict:
    manifest = artifacts.build_manifest(
        csv_path, season=SEASON, horizon=1, first_gw=1, last_gw=1, players=2, rows=2,
        root=str(tmp_path))
    manifest.update(overrides)
    artifacts.write_manifest(csv_path, manifest)
    return manifest


def test_describe_verifies_a_matching_manifest(tmp_path):
    csv_path = make_artifact(tmp_path)
    manifest = write_manifest_for(tmp_path, csv_path)
    info = artifacts.describe(csv_path)
    assert info["manifest_status"] == "verified"
    assert info["sha256"] == manifest["sha256"] == artifacts.sha256_file(csv_path)
    assert info["first_gw"] == 1 and info["season"] == SEASON


def test_describe_detects_missing_mismatched_and_unreadable_manifests(tmp_path):
    csv_path = make_artifact(tmp_path)
    assert artifacts.describe(csv_path)["manifest_status"] == "missing"

    write_manifest_for(tmp_path, csv_path)
    export(points=99.0).to_csv(csv_path, index=False)   # hand-edited after the fact
    assert artifacts.describe(csv_path)["manifest_status"] == "mismatch"

    Path(artifacts.manifest_path(csv_path)).write_text("{not json", encoding="utf-8")
    assert artifacts.describe(csv_path)["manifest_status"] == "unreadable"
    Path(artifacts.manifest_path(csv_path)).write_text("[1]", encoding="utf-8")
    assert artifacts.describe(csv_path)["manifest_status"] == "unreadable"


def test_the_model_bundle_hash_follows_content_not_timestamps(tmp_path):
    models = tmp_path / "saved_models" / "direct"
    models.mkdir(parents=True)
    (models / "meta.json").write_text("{}", encoding="utf-8")
    (models / "GK.joblib").write_bytes(b"model-a")
    first = artifacts.model_bundle_info(str(tmp_path))
    assert first["files"] == 2

    touch(models / "GK.joblib", 100)
    assert artifacts.model_bundle_info(str(tmp_path))["sha256"] == first["sha256"]

    (models / "GK.joblib").write_bytes(b"model-b")
    assert artifacts.model_bundle_info(str(tmp_path))["sha256"] != first["sha256"]
    assert artifacts.model_bundle_info(str(tmp_path / "nowhere")) is None


def test_the_manifest_cli_round_trips(tmp_path):
    csv_path = make_artifact(tmp_path)
    frame = pd.read_csv(csv_path)
    manifest = artifacts.build_manifest(csv_path, season=SEASON, horizon=1, first_gw=1, last_gw=1,
                                        players=int(frame.element.nunique()), rows=len(frame),
                                        root=str(tmp_path))
    artifacts.write_manifest(csv_path, manifest)
    verify = [sys.executable, str(PROJECT / "scripts" / "artifacts.py"), "verify", "--csv", csv_path]
    assert subprocess.run(verify, capture_output=True, text=True).returncode == 0
    Path(csv_path).write_text("tampered", encoding="utf-8")
    assert subprocess.run(verify, capture_output=True, text=True).returncode == 1


def test_the_pipeline_writes_a_verified_manifest_with_the_replace(tmp_path, monkeypatch):
    season = tmp_path / "data" / SEASON
    season.mkdir(parents=True)
    pd.DataFrame({"name": ["Arsenal", "Chelsea"]}).to_csv(season / "teams.csv", index=False)
    monkeypatch.setattr(pipeline, "ROOT", str(tmp_path))
    monkeypatch.setattr(pipeline.opt, "infer_next_gameweek", lambda _season, root=None: 6)
    frame = pd.DataFrame([
        {"element": e, "name": f"P{e}", "team": ["Arsenal", "Chelsea"][e % 2], "position": "MID",
         "GW": gw, "value_m": 5.0, "predicted_points": 3.0}
        for e in range(1, 6) for gw in (6, 7)])

    def runner(command, **_kwargs):
        if any(part.endswith("predict_gameweek.py") for part in command):
            frame.to_csv(command[command.index("--out") + 1], index=False)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    report = pipeline.run_pipeline(SEASON, 2, out="predictions.csv", log=lambda _l: None,
                                   runner=runner)

    target = str(tmp_path / "predictions.csv")
    info = artifacts.describe(target)
    assert info["manifest_status"] == "verified"
    assert info["first_gw"] == 6 and info["last_gw"] == 7 and info["horizon"] == 2
    assert report["artifact_sha256"] == info["sha256"]


def test_a_failed_run_leaves_the_manifest_matching_the_kept_predictions(tmp_path, monkeypatch):
    season = tmp_path / "data" / SEASON
    season.mkdir(parents=True)
    pd.DataFrame({"name": ["Club"]}).to_csv(season / "teams.csv", index=False)
    monkeypatch.setattr(pipeline, "ROOT", str(tmp_path))
    csv_path = make_artifact(tmp_path)
    write_manifest_for(tmp_path, csv_path)
    before = Path(artifacts.manifest_path(csv_path)).read_bytes()

    def failing(command, **_kwargs):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "nope"})()

    with pytest.raises(pipeline.PipelineError):
        pipeline.run_pipeline(SEASON, 2, out="predictions.csv", log=lambda _l: None, runner=failing)
    assert Path(artifacts.manifest_path(csv_path)).read_bytes() == before
    assert artifacts.describe(csv_path)["manifest_status"] == "verified"


def test_meta_reports_the_served_artifact_and_its_models():
    artifact = client.get("/api/meta").get_json()["artifact"]
    assert artifact["sha256"] == artifacts.sha256_file(str(PROJECT / "predictions_next_gw.csv"))
    assert {"manifest_status", "generated_at", "model_bundle", "first_gw", "last_gw"} <= artifact.keys()


# --- readiness ---------------------------------------------------------------
def test_liveness_never_depends_on_data(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp_app, "ROOT", str(tmp_path))
    webapp_app.reset_state()
    assert client.get("/api/health/live").status_code == 200


def test_readiness_is_503_without_predictions(tmp_path, monkeypatch):
    (tmp_path / "data" / SEASON).mkdir(parents=True)
    monkeypatch.setattr(webapp_app, "ROOT", str(tmp_path))
    monkeypatch.setattr(webapp_app.opt, "PREDICTIONS", "predictions.csv")
    webapp_app.reset_state()

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    body = response.get_json()
    assert body["ok"] is False and body["blocking"] == ["predictions_unavailable"]
    assert body["checks"]["predictions_loaded"] is False


def test_readiness_is_503_without_market_prices(site):
    (site / "data" / SEASON / "players_raw.csv").unlink()
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert "market_prices_unavailable" in response.get_json()["blocking"]


def test_a_missing_manifest_blocks_readiness_only_when_required(site, monkeypatch):
    assert client.get("/api/health/ready").status_code == 200, "development tolerates it"
    alerts = {a["name"]: a for a in client.get("/api/health/ready").get_json()["alerts"]}
    assert alerts["artifact_manifest_invalid"]["severity"] == "warning"

    monkeypatch.setenv("REQUIRE_ARTIFACT_MANIFEST", "1")
    blocked = client.get("/api/health/ready")
    assert blocked.status_code == 503
    assert blocked.get_json()["blocking"] == ["artifact_manifest_invalid"]

    monkeypatch.delenv("REQUIRE_ARTIFACT_MANIFEST")
    monkeypatch.setenv("APP_ENV", "production")
    assert client.get("/api/health/ready").status_code == 503, "production requires it by default"

    write_manifest_for(site, str(site / "predictions.csv"))
    assert client.get("/api/health/ready").status_code == 200


def test_readiness_on_the_real_data_reports_freshness():
    body = client.get("/api/health/ready").get_json()
    assert body["ok"] is True and body["checks"]["artifact_verified"] is True
    fresh = body["freshness"]
    assert fresh["predictions"]["age_seconds"] >= 0 and fresh["market"]["age_seconds"] >= 0
    assert fresh["next_deadline"]["estimated"] is True
    assert not any(key.startswith("_") for key in fresh)


# --- alerts ------------------------------------------------------------------
NOW = 1_800_000_000.0
DEADLINE = NOW + 10 * 3600


def snapshot(**overrides) -> dict:
    base = {"error": None, "market_error": None, "gameweek": 6, "future_gameweeks": [6, 7],
            "mtime": NOW - 3600, "market_mtime": NOW - 7200, "loaded_at": NOW,
            "artifact": {"manifest_status": "verified", "generated_at": None}}
    return {**base, **overrides}


@pytest.fixture
def fixtures_file(tmp_path):
    kickoff = obs._iso(DEADLINE + 90 * 60).replace("+00:00", "Z")
    path = tmp_path / "fixtures.csv"
    pd.DataFrame([
        {"event": 6, "kickoff_time": kickoff},
        {"event": 6, "kickoff_time": obs._iso(DEADLINE + 90 * 60 + 86400).replace("+00:00", "Z")},
        {"event": 7, "kickoff_time": obs._iso(DEADLINE + 7 * 86400).replace("+00:00", "Z")},
    ]).to_csv(path, index=False)
    return str(path)


def alert_names(snap, fixtures, now=NOW, require=False, environ=None) -> set[str]:
    fresh = obs.freshness(snap, fixtures, now=now)
    return {a["name"] for a in obs.evaluate_alerts(snap, fresh, require_manifest=require,
                                                   environ=environ or {})}


def test_the_deadline_is_the_first_kickoff_minus_ninety_minutes(fixtures_file):
    assert obs.next_deadline(fixtures_file, 6) == DEADLINE
    assert obs.next_deadline(fixtures_file, 99) is None
    assert obs.next_deadline(fixtures_file, None) is None
    assert obs.next_deadline(fixtures_file + ".missing", 6) is None


def test_a_healthy_snapshot_raises_nothing(fixtures_file):
    assert alert_names(snapshot(), fixtures_file) == set()


def test_predictions_older_than_market_data(fixtures_file):
    assert "predictions_older_than_market" in alert_names(
        snapshot(mtime=NOW - 7200, market_mtime=NOW - 3600), fixtures_file)


def test_predictions_for_a_gameweek_that_is_no_longer_next(fixtures_file):
    assert "predictions_gameweek_mismatch" in alert_names(
        snapshot(future_gameweeks=[5, 6, 7]), fixtures_file)


def test_age_thresholds_default_and_override(fixtures_file):
    old = snapshot(mtime=NOW - 80 * 3600, market_mtime=NOW - 90 * 3600)
    names = alert_names(old, fixtures_file)
    assert {"predictions_too_old", "market_data_old"} <= names
    assert "predictions_too_old" not in alert_names(
        old, fixtures_file, environ={"MAX_PREDICTION_AGE_HOURS": "100"})


def test_predictions_going_stale_as_the_deadline_approaches(fixtures_file):
    approaching = NOW    # 10h to the deadline, inside the 24h window
    assert "predictions_stale_before_deadline" in alert_names(
        snapshot(mtime=NOW - 20 * 3600, market_mtime=NOW - 30 * 3600), fixtures_file, now=approaching)
    assert "predictions_stale_before_deadline" not in alert_names(
        snapshot(mtime=NOW - 2 * 3600), fixtures_file, now=approaching)
    far = DEADLINE - 3 * 86400
    assert "predictions_stale_before_deadline" not in alert_names(
        snapshot(mtime=far - 20 * 3600, market_mtime=far - 30 * 3600), fixtures_file, now=far)


def test_predictions_made_before_a_deadline_that_has_since_passed(fixtures_file):
    after = DEADLINE + 3600
    assert "predictions_predate_deadline" in alert_names(
        snapshot(mtime=DEADLINE - 3600, market_mtime=DEADLINE - 7200), fixtures_file, now=after)
    assert "predictions_predate_deadline" not in alert_names(
        snapshot(mtime=DEADLINE + 600, market_mtime=DEADLINE - 7200), fixtures_file, now=after)


def test_the_manifest_time_wins_over_the_file_time_when_dating_predictions(fixtures_file):
    # A checkout stamps every file with the deploy time; the manifest knows the truth.
    generated = obs._iso(NOW - 100 * 3600)
    snap = snapshot(mtime=NOW - 60, artifact={"manifest_status": "verified", "generated_at": generated})
    fresh = obs.freshness(snap, fixtures_file, now=NOW)
    assert fresh["predictions"]["source"] == "manifest"
    assert "predictions_too_old" in alert_names(snap, fixtures_file)


def test_unavailable_data_is_blocking_and_suppresses_dependent_alerts(fixtures_file):
    snap = snapshot(error="no predictions")
    alerts = obs.evaluate_alerts(snap, obs.freshness(snap, fixtures_file, now=NOW),
                                 require_manifest=False, environ={})
    assert [(a["name"], a["blocking"]) for a in alerts] == [("predictions_unavailable", True)]

    market = snapshot(market_error="gone")
    alerts = obs.evaluate_alerts(market, obs.freshness(market, fixtures_file, now=NOW),
                                 require_manifest=False, environ={})
    assert ("market_prices_unavailable", True) in [(a["name"], a["blocking"]) for a in alerts]


def test_manifest_alert_severity_follows_the_requirement(fixtures_file):
    snap = snapshot(artifact={"manifest_status": "mismatch", "generated_at": None})
    fresh = obs.freshness(snap, fixtures_file, now=NOW)
    lenient = obs.evaluate_alerts(snap, fresh, require_manifest=False, environ={})[0]
    strict = obs.evaluate_alerts(snap, fresh, require_manifest=True, environ={})[0]
    assert (lenient["severity"], lenient["blocking"]) == ("warning", False)
    assert (strict["severity"], strict["blocking"]) == ("critical", True)


def test_alert_transitions_are_logged_once_each_way(caplog):
    caplog.set_level(logging.INFO, logger="fpl")
    raised = [{"name": "market_data_old", "severity": "warning", "blocking": False, "message": "old"}]

    obs.log_alert_changes(raised)
    obs.log_alert_changes(raised)      # unchanged: silent
    obs.log_alert_changes([])

    events = [(r.event, r.fields.get("alert")) for r in caplog.records]
    assert events == [("alert_raised", "market_data_old"), ("alert_cleared", "market_data_old")]


# --- metrics endpoint --------------------------------------------------------
def test_prometheus_output_carries_freshness_alerts_artifact_and_requests(fixtures_file):
    snap = snapshot(artifact={"manifest_status": "verified", "generated_at": None, "sha256": "abc",
                              "model_bundle": {"sha256": "def"}}, market_error="x")
    fresh = obs.freshness(snap, fixtures_file, now=NOW)
    metrics = obs.RequestMetrics()
    metrics.observe("/api/squad", "POST", 200, 0.25)
    metrics.observe("/api/squad", "POST", 400, 0.05)

    text = obs.prometheus(snap, fresh, obs.evaluate_alerts(snap, fresh, require_manifest=False,
                                                           environ={}), False, metrics, True)

    assert "fpl_ready 0" in text and "fpl_refresh_running 1" in text
    assert "fpl_predictions_age_seconds 3600" in text
    assert "fpl_market_data_age_seconds 7200" in text
    assert "fpl_next_deadline_seconds 36000" in text
    assert 'fpl_alert_active{alert="market_prices_unavailable"} 1' in text
    assert 'fpl_alert_active{alert="predictions_too_old"} 0' in text, "cleared alerts are exported as 0"
    assert 'fpl_artifact_info{sha256="abc",model_bundle_sha256="def",manifest_status="verified"} 1' in text
    assert 'fpl_http_requests_total{route="/api/squad",method="POST",status="400"} 1' in text
    assert 'fpl_http_request_duration_seconds_count{route="/api/squad"} 2' in text


def test_the_metrics_endpoint_is_guarded_and_counts_requests():
    assert client.get("/api/metrics", environ_overrides=REMOTE).status_code == 403
    client.post("/api/squad", json={"budget": "x"})
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert 'fpl_http_requests_total{route="/api/squad",method="POST",status="400"}' in response.get_data(as_text=True)


# --- structured logs ---------------------------------------------------------
def records(caplog, event):
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def test_every_request_gets_an_id_and_one_structured_log_line(caplog):
    caplog.set_level(logging.INFO, logger="fpl")

    response = client.post("/api/squad", json={"budget": "x"}, headers={"X-Request-ID": "trace-42"})

    assert response.headers["X-Request-ID"] == "trace-42"
    (line,) = records(caplog, "request")
    fields = line.fields
    assert fields["request_id"] == "trace-42" and fields["method"] == "POST"
    assert fields["route"] == "/api/squad" and fields["status"] == 400
    assert fields["error_code"] == "invalid_field" and fields["duration_ms"] >= 0
    assert line.levelno == logging.WARNING


def test_unsafe_request_ids_are_replaced():
    for bad in ("has space", "x" * 200, "semi;colon", "<script>"):
        got = client.get("/api/health/live", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
        assert got != bad and len(got) == 32


def test_unhandled_errors_are_logged_with_a_traceback_but_not_returned(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="fpl")
    monkeypatch.setattr(webapp_app.opt, "compute_watchlist",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom internals")))

    response = client.get("/api/watchlist")

    assert response.status_code == 500 and "boom" not in response.get_data(as_text=True)
    (error,) = records(caplog, "unhandled_exception")
    assert error.fields["exc_type"] == "RuntimeError"
    assert "boom internals" in error.fields["traceback"]
    assert error.fields["request_id"] == response.headers["X-Request-ID"]
    assert [r.levelno for r in records(caplog, "request")] == [logging.ERROR]


def test_health_checks_do_not_flood_the_info_log(caplog):
    caplog.set_level(logging.INFO, logger="fpl")
    client.get("/api/health/live")
    client.get("/api/health/ready")
    assert records(caplog, "request") == []


def test_the_json_formatter_emits_one_parseable_object_per_line():
    record = logging.LogRecord("fpl", logging.INFO, __file__, 1, "request", None, None)
    record.event, record.fields = "request", {"status": 200, "path": "/api/x"}
    parsed = json.loads(obs.JsonFormatter().format(record))
    assert parsed["event"] == "request" and parsed["level"] == "info"
    assert parsed["status"] == 200 and parsed["ts"].endswith("+00:00")


# --- an unreadable source file must not take the site down --------------------
def test_a_torn_predictions_file_keeps_the_last_good_snapshot_and_alerts(site, caplog):
    caplog.set_level(logging.WARNING, logger="fpl")
    good = webapp_app.state()
    (site / "predictions.csv").write_text("", encoding="utf-8")     # truncated mid-write
    touch(site / "predictions.csv")

    assert webapp_app.state() is good, "the site keeps serving what it had"
    assert client.post("/api/squad", json={}).status_code in (200, 400)
    body = client.get("/api/health/ready").get_json()
    assert "predictions_rebuild_failing" in [a["name"] for a in body["alerts"]]
    assert [r.fields["error"].split(":")[0] for r in caplog.records
            if getattr(r, "event", "") == "snapshot_rebuild_failed"] == ["EmptyDataError"], \
        "the same failure is logged once, not per request"

    export(points=7.0).to_csv(site / "predictions.csv", index=False)
    touch(site / "predictions.csv", 9)
    recovered = webapp_app.state()
    assert set(recovered["players"]["predicted_points"]) == {7.0}
    alerts = client.get("/api/health/ready").get_json()["alerts"]
    assert "predictions_rebuild_failing" not in [a["name"] for a in alerts]


def test_an_unreadable_file_with_nothing_loaded_is_an_explained_error_not_a_500(site):
    (site / "predictions.csv").write_text("", encoding="utf-8")
    snapshot = webapp_app.state()
    assert "could not be read" in snapshot["error"]
    assert client.post("/api/squad", json={}).status_code == 503
    assert client.get("/api/health/ready").status_code == 503


def test_a_new_manifest_invalidates_the_snapshot(site):
    first = webapp_app.state()
    assert first["artifact"]["manifest_status"] == "missing"
    write_manifest_for(site, str(site / "predictions.csv"))
    second = webapp_app.state()
    assert second is not first and second["artifact"]["manifest_status"] == "verified"
