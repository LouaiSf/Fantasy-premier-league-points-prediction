from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pandas as pd
import pytest

import webapp.app as webapp_app
from scripts import refresh_pipeline as pipeline

SEASON = "2026-27"
TEAMS = ["Arsenal", "Chelsea"]


@pytest.fixture(autouse=True)
def _no_refresh_cooldown():
    # Process-wide state: one test's refresh must not throttle the next.
    webapp_app.reset_refresh_guards()
    yield
    webapp_app.reset_refresh_guards()


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A throwaway project root with a season's teams, and GW6 as the next week."""
    season_dir = tmp_path / "data" / SEASON
    season_dir.mkdir(parents=True)
    pd.DataFrame({"name": TEAMS}).to_csv(season_dir / "teams.csv", index=False)
    monkeypatch.setattr(pipeline, "ROOT", str(tmp_path))
    monkeypatch.setattr(pipeline.opt, "infer_next_gameweek", lambda _season, root=None: 6)
    return tmp_path


def export(first_gw: int = 6, weeks: int = 4, players: int = 10, teams=TEAMS) -> pd.DataFrame:
    rows = [
        {"element": element, "name": f"P{element}", "team": teams[element % len(teams)],
         "position": "MID", "GW": gw, "value_m": 5.0, "predicted_points": 3.5}
        for element in range(1, players + 1)
        for gw in range(first_gw, first_gw + weeks)
    ]
    return pd.DataFrame(rows)


def write(path, frame: pd.DataFrame):
    frame.to_csv(path, index=False)
    return str(path)


# --- validate_predictions ---------------------------------------------------
def test_validate_accepts_a_complete_export(root):
    summary = pipeline.validate_predictions(write(root / "c.csv", export()), SEASON, 4)
    assert summary["first_gw"] == 6
    assert summary["gameweeks"] == [6, 7, 8, 9]
    assert summary["players"] == 10


def test_validate_rejects_a_horizon_that_is_too_short(root):
    with pytest.raises(pipeline.PipelineError, match="GW9"):
        pipeline.validate_predictions(write(root / "c.csv", export(weeks=3)), SEASON, 4)


def test_validate_rejects_a_stale_first_gameweek(root):
    # The predict step asks the live API; local fixtures say GW6. Disagreement
    # means one side is stale, and the old export must be kept.
    with pytest.raises(pipeline.PipelineError, match="GW5 but local fixtures say GW6"):
        pipeline.validate_predictions(write(root / "c.csv", export(first_gw=5)), SEASON, 4)


def test_validate_allows_a_horizon_cut_short_by_the_season_end(root, monkeypatch):
    monkeypatch.setattr(pipeline.opt, "infer_next_gameweek", lambda _season, root=None: 37)
    frame = export(first_gw=37, weeks=2)
    assert pipeline.validate_predictions(write(root / "c.csv", frame), SEASON, 8)["gameweeks"] == [37, 38]


def test_validate_rejects_blank_points(root):
    frame = export()
    frame.loc[0, "predicted_points"] = None
    with pytest.raises(pipeline.PipelineError, match="predicted_points"):
        pipeline.validate_predictions(write(root / "c.csv", frame), SEASON, 4)


def test_validate_rejects_missing_columns(root):
    with pytest.raises(pipeline.PipelineError, match="missing columns: GW"):
        pipeline.validate_predictions(write(root / "c.csv", export().drop(columns="GW")), SEASON, 4)


def test_validate_rejects_a_club_mismatch(root):
    frame = export(teams=["Arsenal", "Everton"])
    with pytest.raises(pipeline.PipelineError, match="teams.csv"):
        pipeline.validate_predictions(write(root / "c.csv", frame), SEASON, 4)


def test_validate_rejects_a_collapse_in_player_count(root):
    previous = write(root / "old.csv", export(players=20))
    with pytest.raises(pipeline.PipelineError, match="down from 20"):
        pipeline.validate_predictions(write(root / "c.csv", export(players=10)), SEASON, 4,
                                      previous_path=previous)


def test_validate_rejects_an_empty_file(root):
    (root / "c.csv").write_text("")
    with pytest.raises(pipeline.PipelineError, match="not readable"):
        pipeline.validate_predictions(str(root / "c.csv"), SEASON, 4)


# --- run_pipeline -----------------------------------------------------------
class FakeRunner:
    """Stands in for subprocess.run: records commands, writes the predict output."""

    def __init__(self, frame: pd.DataFrame | None = None, predict_returncode: int = 0,
                 fetch_returncode: int = 0):
        self.frame = export() if frame is None else frame
        self.predict_returncode = predict_returncode
        self.fetch_returncode = fetch_returncode
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        if any(part.endswith("predict_gameweek.py") for part in command):
            if self.predict_returncode == 0:
                self.frame.to_csv(command[command.index("--out") + 1], index=False)
            return SimpleNamespace(returncode=self.predict_returncode, stdout="", stderr="boom")
        if any(part.endswith("fetch_data.py") for part in command):
            return SimpleNamespace(returncode=self.fetch_returncode, stdout="partial output",
                                   stderr="HTTP 503 from upstream")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def run(root, runner, **kwargs):
    return pipeline.run_pipeline(SEASON, 4, out="predictions.csv", log=lambda _l: None,
                                 runner=runner, **kwargs)


def test_pipeline_fetches_predicts_and_replaces_atomically(root):
    target = root / "predictions.csv"
    write(target, export(players=10, weeks=1))
    runner = FakeRunner(export(players=10, weeks=4))

    report = run(root, runner)

    assert sorted(pd.read_csv(target)["GW"].unique()) == [6, 7, 8, 9]
    assert report["first_gw"] == 6 and report["last_gw"] == 9
    assert [c[1].rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for c in runner.commands] == [
        "fetch_data.py", "predict_gameweek.py"]
    fetch, predict = runner.commands
    assert "--force" in fetch and fetch[fetch.index("--source") + 1] == "olbauday"
    assert predict[predict.index("--horizon") + 1] == "4"
    assert not list(root.glob("*.tmp.csv")), "temp file must not be left behind"
    assert not (root / "data" / ".refresh_pipeline.lock").exists()


def test_pipeline_can_skip_the_fetch(root):
    runner = FakeRunner()
    run(root, runner, fetch=False)
    assert len(runner.commands) == 1


def test_failed_validation_leaves_the_previous_predictions_untouched(root):
    target = root / "predictions.csv"
    write(target, export(players=10, weeks=1))
    before = target.read_bytes()

    with pytest.raises(pipeline.PipelineError) as raised:
        run(root, FakeRunner(export(weeks=2)))   # 2 weeks of a 4-week horizon

    assert raised.value.step == "validate"
    assert target.read_bytes() == before
    assert not list(root.glob("*.tmp.csv"))
    assert not (root / "data" / ".refresh_pipeline.lock").exists()


def test_failed_predict_step_leaves_the_previous_predictions_untouched(root):
    target = root / "predictions.csv"
    write(target, export(players=10, weeks=1))
    before = target.read_bytes()

    with pytest.raises(pipeline.PipelineError) as raised:
        run(root, FakeRunner(predict_returncode=1))

    assert raised.value.step == "predict" and "boom" in raised.value.message
    assert target.read_bytes() == before


def test_concurrent_runs_are_refused(root):
    lock = root / "data" / ".refresh_pipeline.lock"
    lock.write_text("123")
    runner = FakeRunner()
    with pytest.raises(pipeline.PipelineBusy):
        run(root, runner)
    assert runner.commands == []
    assert lock.exists(), "someone else's lock must not be removed"


def test_a_stale_lock_does_not_block_forever(root, monkeypatch):
    lock = root / "data" / ".refresh_pipeline.lock"
    lock.write_text("123")
    monkeypatch.setattr(pipeline, "LOCK_STALE_AFTER_S", -1)
    run(root, FakeRunner())


def test_horizon_is_bounded(root):
    with pytest.raises(pipeline.PipelineError, match="horizon"):
        pipeline.run_pipeline(SEASON, 0, runner=FakeRunner())


# --- endpoints --------------------------------------------------------------
@pytest.fixture
def fresh_job(monkeypatch):
    monkeypatch.setattr(webapp_app, "_refresh_job", {"state": "idle"})


def wait_for(state: str, timeout: float = 5.0) -> dict:
    client = webapp_app.app.test_client()
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get("/api/refresh/status").get_json()["job"]
        if job["state"] == state:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job never reached {state}: {job}")


def test_refresh_predictions_runs_in_the_background(monkeypatch, fresh_job):
    release = threading.Event()
    seen = {}

    def fake_pipeline(season, horizon, fetch, rebuild, log, on_step):
        seen.update(season=season, horizon=horizon, fetch=fetch)
        on_step("predict")
        release.wait(5)
        return {"first_gw": 6, "last_gw": 17, "players": 487, "warnings": []}

    monkeypatch.setattr(webapp_app.pipeline, "run_pipeline", fake_pipeline)
    client = webapp_app.app.test_client()

    started = client.post("/api/refresh/predictions", json={"horizon": 8, "fetch": False})
    assert started.status_code == 202
    assert started.get_json()["job"]["state"] == "running"

    busy = client.post("/api/refresh/predictions", json={})
    assert busy.status_code == 409
    assert "already running" in busy.get_json()["error"]

    release.set()
    job = wait_for("succeeded")
    assert job["report"]["last_gw"] == 17
    assert seen["horizon"] == 8 and seen["fetch"] is False


def test_refresh_predictions_reports_a_failure_and_allows_a_retry(monkeypatch, fresh_job):
    def failing(*_args, **_kwargs):
        raise pipeline.PipelineError("validate", "predictions start at GW5")

    monkeypatch.setattr(webapp_app.pipeline, "run_pipeline", failing)
    client = webapp_app.app.test_client()

    assert client.post("/api/refresh/predictions", json={"fetch": False}).status_code == 202
    job = wait_for("failed")
    assert job["failed_step"] == "validate"
    assert "GW5" in job["error"]

    assert client.post("/api/refresh/predictions", json={"fetch": False}).status_code == 202


@pytest.mark.parametrize("body", [{"horizon": 0}, {"horizon": 99}, {"horizon": "x"}, {"fetch": "yes"}])
def test_refresh_predictions_validates_input(body, fresh_job):
    response = webapp_app.app.test_client().post("/api/refresh/predictions", json=body)
    assert response.status_code == 400


# --- failure handling -------------------------------------------------------
def command_names(runner) -> list[str]:
    return [c[1].replace("\\", "/").rsplit("/", 1)[-1] for c in runner.commands]


def test_a_failed_fetch_is_an_error_with_its_exit_status_and_stderr(root):
    target = root / "predictions.csv"
    write(target, export(weeks=1))
    before = target.read_bytes()
    runner = FakeRunner(fetch_returncode=3)

    with pytest.raises(pipeline.PipelineError) as raised:
        run(root, runner)

    error = raised.value
    assert error.step == "fetch"
    assert error.details["returncode"] == 3
    assert "HTTP 503" in error.details["stderr"]
    assert "status 3" in error.message
    assert len(runner.commands) == 1, "nothing may run after a failed fetch"
    assert target.read_bytes() == before


def test_a_timeout_is_reported_as_a_failure(root):
    import subprocess

    def hang(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    with pytest.raises(pipeline.PipelineError, match="timed out") as raised:
        run(root, hang)
    assert raised.value.step == "fetch"


def test_history_is_rebuilt_only_when_it_lags(root, monkeypatch):
    lags = iter([1, 0])   # behind before the rebuild, current after
    monkeypatch.setattr(pipeline, "history_gameweeks_behind", lambda _season: next(lags))
    runner = FakeRunner()

    report = run(root, runner)

    assert command_names(runner) == ["fetch_data.py", "build_dataset.py", "predict_gameweek.py"]
    assert "--write" in runner.commands[1]
    assert report["warnings"] == []


def test_history_is_left_alone_when_current_or_opted_out(root, monkeypatch):
    monkeypatch.setattr(pipeline, "history_gameweeks_behind", lambda _season: 0)
    current = FakeRunner()
    run(root, current)
    assert len(current.commands) == 2

    monkeypatch.setattr(pipeline, "history_gameweeks_behind", lambda _season: 2)
    opted_out = FakeRunner()
    report = run(root, opted_out, rebuild=False)
    assert len(opted_out.commands) == 2
    assert report["warnings"], "a lagging history must still be reported"


def test_a_failed_history_rebuild_stops_before_predicting(root, monkeypatch):
    monkeypatch.setattr(pipeline, "history_gameweeks_behind", lambda _season: 1)

    class Runner(FakeRunner):
        def __call__(self, command, **kwargs):
            if any(part.endswith("build_dataset.py") for part in command):
                self.commands.append(command)
                return SimpleNamespace(returncode=1, stdout="", stderr="content check failed")
            return super().__call__(command, **kwargs)

    runner = Runner()
    with pytest.raises(pipeline.PipelineError) as raised:
        run(root, runner)
    assert raised.value.step == "history"
    assert "predict_gameweek.py" not in command_names(runner)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_cooldown_counts_down_and_failures_cool_down_less():
    clock = Clock()
    cooldown = webapp_app.Cooldown(60, 10, clock=clock)
    assert cooldown.remaining() == 0
    cooldown.record(True)
    assert cooldown.remaining() == 60
    clock.now += 45.5
    assert cooldown.remaining() == 15
    clock.now += 20
    assert cooldown.remaining() == 0
    cooldown.record(False)
    assert cooldown.remaining() == 10


def fake_fetch(monkeypatch, returncode=0, stderr=""):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=returncode, stdout="out", stderr=stderr)

    monkeypatch.setattr(webapp_app.subprocess, "run", fake_run)
    return calls


def test_refresh_reports_a_failed_fetch_with_stderr(monkeypatch):
    fake_fetch(monkeypatch, returncode=2, stderr="Traceback ... ConnectionError")
    before = webapp_app.state().get("loaded_at")

    response = webapp_app.app.test_client().post("/api/refresh")

    assert response.status_code == 502
    body = response.get_json()
    assert body["ok"] is False
    assert body["step"] == "fetch" and body["code"] == "fetch_failed"
    assert body["returncode"] == 2
    assert "ConnectionError" in body["stderr"]
    assert "status 2" in body["error"]
    assert webapp_app.state().get("loaded_at") == before, "a failed fetch must not reload state"


def test_refresh_rate_limits_repeat_calls(monkeypatch):
    calls = fake_fetch(monkeypatch)
    client = webapp_app.app.test_client()

    assert client.post("/api/refresh").status_code == 200
    second = client.post("/api/refresh")

    assert second.status_code == 429
    body = second.get_json()
    assert body["code"] == "refresh_cooldown"
    assert 0 < body["retry_after_seconds"] <= 60
    assert second.headers["Retry-After"] == str(body["retry_after_seconds"])
    assert len(calls) == 1, "a throttled request must not fetch"


def test_refresh_failure_cools_down_briefly(monkeypatch):
    fake_fetch(monkeypatch, returncode=1, stderr="nope")
    client = webapp_app.app.test_client()
    assert client.post("/api/refresh").status_code == 502
    assert 0 < webapp_app.fetch_cooldown.remaining() <= 10
    assert client.post("/api/refresh").status_code == 429


def test_refresh_is_refused_while_another_refresh_holds_the_lock(monkeypatch):
    calls = fake_fetch(monkeypatch)
    with pipeline.exclusive_run():
        response = webapp_app.app.test_client().post("/api/refresh")
    assert response.status_code == 409
    assert response.get_json()["code"] == "refresh_in_progress"
    assert calls == []
    assert webapp_app.fetch_cooldown.remaining() == 0, "a busy lock is not an attempt"


def test_prediction_refresh_with_fetch_is_throttled_but_without_is_not(monkeypatch, fresh_job):
    monkeypatch.setattr(webapp_app.pipeline, "run_pipeline",
                        lambda *a, **k: {"first_gw": 6, "last_gw": 17, "players": 1, "warnings": []})
    client = webapp_app.app.test_client()
    webapp_app.fetch_cooldown.record(True)

    assert client.post("/api/refresh/predictions", json={"fetch": True}).status_code == 429

    assert client.post("/api/refresh/predictions", json={"fetch": False}).status_code == 202
    wait_for("succeeded")


def test_failed_prediction_job_exposes_stderr(monkeypatch, fresh_job):
    def failing(*_args, **_kwargs):
        raise pipeline.PipelineError("predict", "exited with status 1: boom",
                                     {"returncode": 1, "stderr": "Traceback: boom"})

    monkeypatch.setattr(webapp_app.pipeline, "run_pipeline", failing)
    client = webapp_app.app.test_client()
    assert client.post("/api/refresh/predictions", json={"fetch": False}).status_code == 202
    job = wait_for("failed")
    assert job["returncode"] == 1 and job["stderr"] == "Traceback: boom"
    assert job["failed_step"] == "predict"
