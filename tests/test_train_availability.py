from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import calibrate  # noqa: E402
import train_availability as ta  # noqa: E402

SEASONS = ['2022-23', '2023-24', '2024-25', '2025-26', '2026-27']
ROWS_PER_SEASON = 120


def frame() -> pd.DataFrame:
    """MID rows over five seasons: two in TRAIN_SEASONS, both TEST_SEASONS, one newer."""
    rng = np.random.default_rng(0)
    n = ROWS_PER_SEASON * len(SEASONS)
    minutes_prev = rng.integers(0, 91, n)
    played = rng.random(n) < minutes_prev / 90
    return pd.DataFrame({
        'season': np.repeat(SEASONS, ROWS_PER_SEASON),
        'GW': np.tile(np.arange(ROWS_PER_SEASON) % 38 + 1, len(SEASONS)),
        'position': 'MID',
        'minutes_prev_1': minutes_prev,
        'value': rng.integers(40, 130, n),
        'minutes': np.where(played, 90, 0),
        'total_points': np.where(played, rng.integers(1, 10, n), 0),
    })


@pytest.fixture
def model_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, 'MODEL_DIR', str(tmp_path))
    monkeypatch.setattr(calibrate, 'MODEL_DIR', str(tmp_path))
    return tmp_path


def meta(directory: Path) -> dict:
    return json.loads((directory / 'availability_meta.json').read_text(encoding='utf-8'))


def test_saving_keeps_the_holdout_fit_and_refits_on_every_season(model_dir):
    metrics = ta.train_position('MID', frame(), save=True)

    holdout = meta(model_dir / 'MID' / 'holdout')
    assert holdout['trained_on'] == ['2022-23', '2023-24']
    assert holdout['tested_on'] == ['2024-25', '2025-26']
    assert meta(model_dir / 'MID')['trained_on'] == SEASONS
    assert metrics['train_rows'] == 2 * ROWS_PER_SEASON
    assert metrics['saved_model']['rows'] == len(SEASONS) * ROWS_PER_SEASON
    for name in ('availability.joblib', 'conditional.joblib', 'availability_scaler.joblib',
                 'availability_features.json'):
        assert (model_dir / 'MID' / name).exists()
        assert (model_dir / 'MID' / 'holdout' / name).exists()


def test_no_save_writes_nothing(model_dir):
    ta.train_position('MID', frame(), save=False)
    assert not os.listdir(model_dir)


def test_calibration_measures_the_holdout_copy(model_dir):
    ta.train_position('MID', frame(), save=True)
    assert calibrate.load_position('MID')['dir'] == str(model_dir / 'MID' / 'holdout')


def test_calibration_refuses_models_that_saw_its_seasons(model_dir):
    # Without the holdout copy only the refit is left, and it trained on
    # 2024-25 and 2025-26: fitting on its predictions would be in-sample.
    ta.train_position('MID', frame(), save=True)
    shutil.rmtree(model_dir / 'MID' / 'holdout')
    with pytest.raises(SystemExit, match='in-sample'):
        calibrate.load_position('MID')


def test_calibration_still_reads_a_checkout_from_before_the_refit(model_dir):
    ta.train_position('MID', frame(), save=True)
    shutil.rmtree(model_dir / 'MID' / 'holdout')
    (model_dir / 'MID' / 'availability_meta.json').unlink()
    assert calibrate.load_position('MID')['dir'] == str(model_dir / 'MID')


@pytest.mark.parametrize('argv, message', [
    (['--train-through', '2024-25', '--test', '2025-26'], 'add --no-save'),
    (['--no-save', '--train-through', '2025-26', '--test', '2025-26'], 'must come after'),
])
def test_backtest_folds_are_checked_before_anything_runs(monkeypatch, argv, message):
    monkeypatch.setattr(sys, 'argv', ['train_availability.py', *argv])
    with pytest.raises(SystemExit, match=message):
        ta.main()
