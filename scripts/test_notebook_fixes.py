"""Regression tests for the training-pipeline fixes.

Nothing is mocked: the helper cells are pulled straight out of the notebooks
and exec'd, so these fail if the notebook code does not actually run.

Covers
  - temporal_masks / season_split partition on season boundaries and never
    put a later season into an earlier fold
  - chronological_order leaves the training fold as one contiguous block, which
    is what makes TimeSeriesSplit meaningful
  - prepare_position_data raises instead of silently training on whatever
    features happen to exist -- including the exact case that produced the
    single-feature 'direct' models

Run:  python scripts/test_notebook_fixes.py
"""
import json
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

def code_cells(path):
    nb = json.load(open(path, encoding='utf-8'))
    return [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']


cells = code_cells('final.ipynb')


def cell_with(needle, source=None):
    pool = cells if source is None else source
    hits = [s for s in pool if needle in s]
    assert len(hits) == 1, f"{needle!r}: {len(hits)} hits"
    return hits[0]


print("=" * 70)
print("final.ipynb")
print("=" * 70)


ns = {'pd': pd, 'np': np, 'StandardScaler': StandardScaler}
exec(cell_with('SEASON_ORDER = ['), ns)
exec(cell_with('def prepare_position_data(df, position, features'), ns)

temporal_masks = ns['temporal_masks']
chronological_order = ns['chronological_order']
describe_split = ns['describe_split']
prepare_position_data = ns['prepare_position_data']
SEASON_ORDER = ns['SEASON_ORDER']

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as e:
        failures.append(name)
        print(f"  FAIL  {name}: {type(e).__name__}: {e}")


# A small panel frame: 4 players x every season x 3 gameweeks.
rows = []
for s in SEASON_ORDER:
    for gw in (3, 1, 2):                      # deliberately out of order
        for pos in ('GK', 'DEF', 'MID', 'FWD'):
            rows.append({'season': s, 'GW': gw, 'position': pos,
                         'total_points': float(gw), 'value': 50.0,
                         'bps_prev_1': 1.0, 'minutes_rolling_3': 60.0})
frame = pd.DataFrame(rows)
frame.index = frame.index * 7 + 3             # non-trivial index

print(f"\ntest frame: {frame.shape}, seasons {frame.season.nunique()}\n")
print("temporal_masks")


def t_partition():
    tr, va, te = temporal_masks(frame)
    assert (tr | va | te).all(), "some rows fell outside every fold"
    assert not (tr & va).any() and not (va & te).any() and not (tr & te).any()
    assert set(frame[tr].season.unique()) == set(ns['TRAIN_SEASONS'])
    assert set(frame[va].season.unique()) == set(ns['VAL_SEASONS'])
    assert set(frame[te].season.unique()) == set(ns['TEST_SEASONS'])


def t_index_aligned():
    tr, _, _ = temporal_masks(frame)
    assert tr.index.equals(frame.index), "masks must share the frame's index"
    assert frame.loc[tr].shape[0] == int(tr.sum())


def t_no_future_in_train():
    tr, va, te = temporal_masks(frame)
    rank = {s: i for i, s in enumerate(SEASON_ORDER)}
    assert frame[tr].season.map(rank).max() < frame[va].season.map(rank).min()
    assert frame[va].season.map(rank).max() < frame[te].season.map(rank).min()


def t_unknown_season():
    bad = frame.copy()
    bad.loc[bad.index[0], 'season'] = '2099-00'
    try:
        temporal_masks(bad)
    except ValueError as e:
        assert '2099-00' in str(e)
        return
    raise AssertionError("expected ValueError for an unrecognised season")


def t_missing_season_col():
    try:
        temporal_masks(frame.drop(columns=['season']))
    except ValueError as e:
        assert 'season' in str(e)
        return
    raise AssertionError("expected ValueError when 'season' is absent")


check('partitions on season boundaries', t_partition)
check('masks align to frame index', t_index_aligned)
check('train strictly precedes val precedes test', t_no_future_in_train)
check('rejects unknown season', t_unknown_season)
check('rejects frame without season column', t_missing_season_col)

print("\nchronological_order")


def t_order():
    order = chronological_order(frame)
    ordered = frame.loc[order]
    rank = ordered.season.map({s: i for i, s in enumerate(SEASON_ORDER)})
    key = list(zip(rank, ordered.GW))
    assert key == sorted(key), "rows are not in (season, gameweek) order"


def t_order_preserves_rows():
    order = chronological_order(frame)
    assert sorted(order) == sorted(frame.index)


def t_masks_reorder():
    order = chronological_order(frame)
    tr, va, te = (m.loc[order] for m in temporal_masks(frame))
    # After reordering, each fold must be one contiguous block -- that is what
    # makes TimeSeriesSplit on the training fold meaningful.
    pos = np.flatnonzero(tr.to_numpy())
    assert (np.diff(pos) == 1).all(), "training rows are not contiguous in time order"
    assert pos[0] == 0, "training block does not start at the beginning"


check('sorts by season then gameweek', t_order)
check('reorders without losing rows', t_order_preserves_rows)
check('training fold is a contiguous leading block', t_masks_reorder)

print("\nprepare_position_data coverage guard")


def t_guard_raises():
    wanted = ['value', 'bps_prev_1', 'minutes_rolling_3'] + [f'absent_{i}' for i in range(20)]
    try:
        prepare_position_data(frame, 'MID', wanted)
    except ValueError as e:
        msg = str(e)
        assert '3/23' in msg, msg
        assert 'all_seasons_data' in msg, "error should name the likely cause"
        return
    raise AssertionError("expected ValueError when most features are missing")


def t_guard_allows_full():
    wanted = ['value', 'bps_prev_1', 'minutes_rolling_3']
    X, y, avail, pos_df = prepare_position_data(frame, 'MID', wanted)
    assert avail == wanted
    assert len(X) == len(y) == len(pos_df)
    assert (pos_df.position == 'MID').all()
    assert X.index.equals(pos_df.index), "X must stay aligned with pos_df"


def t_guard_tolerates_one_missing():
    # 9/10 present is above the 90% threshold and must not raise.
    for i in range(7):
        frame[f'extra_{i}'] = 1.0
    wanted = ['value', 'bps_prev_1', 'minutes_rolling_3'] + [f'extra_{i}' for i in range(7)]
    X, _, avail, _ = prepare_position_data(frame, 'DEF', wanted + ['absent_1'])
    assert len(avail) == 10, avail


def t_reproduces_the_original_bug():
    # The exact failure mode from the buggy run: POSITION_FEATURES against the
    # un-engineered frame, where only 'value' survives.
    raw = frame[['season', 'GW', 'position', 'total_points', 'value']]
    wanted = ['value', 'bps_prev_1', 'minutes_rolling_3', 'bonus_rolling_5']
    try:
        prepare_position_data(raw, 'GK', wanted)
    except ValueError as e:
        assert '1/4' in str(e), str(e)
        return
    raise AssertionError("the single-feature bug would still pass silently")


check('raises when coverage is below threshold', t_guard_raises)
check('accepts a fully-covered feature list', t_guard_allows_full)
check('tolerates one missing feature out of ten', t_guard_tolerates_one_missing)
check('catches the original single-feature bug', t_reproduces_the_original_bug)

print("\ndescribe_split")


def t_describe_empty_fold():
    only_train = frame[frame.season.isin(ns['TRAIN_SEASONS'])]
    tr, va, te = temporal_masks(only_train)
    try:
        describe_split(tr, va, te, label='x: ')
    except ValueError as e:
        assert 'empty' in str(e)
        return
    raise AssertionError("expected ValueError when a fold is empty")


def t_describe_ok():
    tr, va, te = temporal_masks(frame)
    describe_split(tr, va, te, label='full frame: ')


check('raises when a fold is empty', t_describe_empty_fold)
check('prints a full split without complaint', t_describe_ok)

# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("advanced_fpl_models.ipynb")
print("=" * 70)

adv = code_cells('advanced_fpl_models.ipynb')
ans = {'pd': pd, 'np': np}
exec(cell_with('SEASON_ORDER = [', adv), ans)
exec(cell_with('def prepare_position_data(df, position, features', adv), ans)

# Mirrors data/predictive_features_data.csv: a season_x column, and only six
# of the ten seasons present.
REAL = ['2016-17', '2017-18', '2020-21', '2021-22', '2022-23', '2023-24']
adv_frame = pd.DataFrame([
    {'season_x': s, 'GW': gw, 'position': p, 'total_points': float(gw), 'value': 50.0}
    for s in REAL for gw in (2, 1) for p in ('GK', 'DEF', 'MID', 'FWD')
])
adv_frame.index = adv_frame.index * 3 + 11

print("\nadaptive season_split")


def t_detect_col():
    assert ans['season_column'](adv_frame) == 'season_x'


def t_seasons_present():
    assert ans['seasons_present'](adv_frame) == REAL


def t_adv_folds():
    tr, va, te = ans['season_split'](adv_frame)
    assert set(adv_frame[te].season_x.unique()) == {'2023-24'}
    assert set(adv_frame[va].season_x.unique()) == {'2022-23'}
    assert set(adv_frame[tr].season_x.unique()) == set(REAL[:4])
    assert (tr | va | te).all()


def t_adv_contiguous():
    order = ans['chronological_order'](adv_frame)
    tr, _, _ = (m.loc[order] for m in ans['season_split'](adv_frame))
    pos = np.flatnonzero(tr.to_numpy())
    assert pos[0] == 0 and (np.diff(pos) == 1).all()


def t_adv_too_few_seasons():
    try:
        ans['season_split'](adv_frame[adv_frame.season_x == '2016-17'])
    except ValueError as e:
        assert 'at least 3 seasons' in str(e)
        return
    raise AssertionError("expected ValueError with only one season")


def t_adv_guard():
    # The real failure: GK asked for 18 features and got 2.
    try:
        ans['prepare_position_data'](adv_frame, 'GK',
                                     ['value'] + [f'rolling_{i}' for i in range(17)])
    except ValueError as e:
        assert '1/18' in str(e), str(e)
        assert 'all_seasons_data_featured' in str(e), "error should name the fix"
        return
    raise AssertionError("expected ValueError for the 2-of-18 feature case")


check('detects the season_x column', t_detect_col)
check('lists present seasons chronologically', t_seasons_present)
check('holds out the latest season, validates on the previous', t_adv_folds)
check('training fold is contiguous after ordering', t_adv_contiguous)
check('rejects a frame with too few seasons', t_adv_too_few_seasons)
check('coverage guard fires on the GK 2-of-18 case', t_adv_guard)

print()
if failures:
    raise SystemExit(f"{len(failures)} test(s) failed: {failures}")
print(f"all tests passed")
