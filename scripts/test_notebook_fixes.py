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
import sys
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
# Availability features: the whole point is that they only see the past.
# ---------------------------------------------------------------------------
avail_ns = {'pd': pd, 'np': np}
exec(cell_with('def add_availability_features(df):'), avail_ns)


def _avail_frame():
    """One player, known minutes, so every value can be checked by hand."""
    minutes = [90, 90, 0, 0, 45, 90, 90, 90, 0, 90]
    return pd.DataFrame({
        'name': ['P'] * len(minutes),
        'season': ['2023-24'] * len(minutes),
        'game_number': range(1, len(minutes) + 1),
        'minutes': minutes,
        'kickoff_time': pd.date_range('2023-08-12', periods=len(minutes), freq='7D')
                          .strftime('%Y-%m-%dT%H:%M:%SZ'),
    })


def t_avail_first_row_blank():
    out = avail_ns['add_availability_features'](_avail_frame())
    first = out.iloc[0]
    for col in ('avail_played_rate_3', 'avail_started_rate_5',
                'avail_season_played_rate', 'avail_days_since_last'):
        assert pd.isna(first[col]), f"{col} has a value on the first match: {first[col]}"


def t_avail_matches_hand_calculation():
    out = avail_ns['add_availability_features'](_avail_frame())
    # minutes: 90 90 0 0 45 90 90 90 0 90  -> appeared: 1 1 0 0 1 1 1 1 0 1
    # row 4 (0-indexed) sees the previous three: 1, 0, 0 -> 1/3
    assert abs(out['avail_played_rate_3'].iloc[4] - 1 / 3) < 1e-9, \
        out['avail_played_rate_3'].iloc[4]
    # row 3 sees 1, 1, 0 -> 2/3
    assert abs(out['avail_played_rate_3'].iloc[3] - 2 / 3) < 1e-9, \
        out['avail_played_rate_3'].iloc[3]


def t_avail_no_current_match_leak():
    """Changing only THIS match's minutes must not change this row's features."""
    base = _avail_frame()
    out_a = avail_ns['add_availability_features'](base.copy())

    tampered = base.copy()
    tampered.loc[5, 'minutes'] = 0          # row 5 played 90; pretend it did not
    out_b = avail_ns['add_availability_features'](tampered)

    cols = [c for c in out_a.columns if c.startswith('avail_')]
    row_a = out_a.loc[5, cols]
    row_b = out_b.loc[5, cols]
    for col in cols:
        a, b = row_a[col], row_b[col]
        if pd.isna(a) and pd.isna(b):
            continue
        assert a == b, (
            f"{col} changed when only the current match changed "
            f"({a} -> {b}) -- the feature is reading the present"
        )


def t_avail_streaks():
    out = avail_ns['add_availability_features'](_avail_frame())
    # appeared: 1 1 0 0 1 1 1 1 0 1 -> at row 4 the previous run of blanks is 2
    assert out['avail_zero_streak'].iloc[4] == 2, out['avail_zero_streak'].iloc[4]
    # by row 8 there have been three straight full matches before it
    assert out['avail_start_streak'].iloc[8] == 3, out['avail_start_streak'].iloc[8]


check('availability: first match has no lookback', t_avail_first_row_blank)
check('availability: rates match a hand calculation', t_avail_matches_hand_calculation)
check('availability: current match cannot change its own features', t_avail_no_current_match_leak)
check('availability: blank and start streaks count correctly', t_avail_streaks)


# ---------------------------------------------------------------------------
# Seasons with native FPL defensive stats must not be overwritten by the
# FBref lookup, which only ever covered 2019-20..2024-25.
# ---------------------------------------------------------------------------
def t_native_defensive_preserved():
    sys.path.insert(0, 'scripts')
    import build_dataset

    raw = pd.DataFrame({
        'season': ['2021-22', '2025-26'],
        'element': [1, 1],
        'fixture': [10, 20],
        'GW': [1, 1],
        'position': ['DEF', 'DEF'],
        'total_points': [2, 2],
        'tackles': [0, 7],                              # 2025-26 value is real
        'recoveries': [0, 5],
        'clearances_blocks_interceptions': [0, 3],
        'defensive_contribution': [0, 0],
    })
    # A lookup that covers only the FBref season.
    lookup = pd.DataFrame({
        'season': ['2021-22'], 'element': [1], 'fixture': [10],
        'tackles': [4], 'recoveries': [2], 'clearances_blocks_interceptions': [1],
    })
    orig = build_dataset.defensive_lookup
    build_dataset.defensive_lookup = lambda _path: lookup
    try:
        out = build_dataset.build_final(raw, 'ignored')
    finally:
        build_dataset.defensive_lookup = orig

    fbref = out[out.season == '2021-22'].iloc[0]
    native = out[out.season == '2025-26'].iloc[0]
    assert fbref['tackles'] == 4, f"FBref season not joined: {fbref['tackles']}"
    assert native['tackles'] == 7, (
        f"native 2025-26 tackles overwritten with {native['tackles']} -- "
        f"the FBref join must not touch seasons it never covered"
    )
    assert native['has_fbref_defensive'] == 1


check('native defensive stats survive the FBref join', t_native_defensive_preserved)


def t_scrambled_index_does_not_misroute():
    """add_game_number sorts without resetting, so raw arrives shuffled.

    df.merge() returns a clean RangeIndex, so `df.loc[mask, col] = values`
    aligned on labels and wrote into the wrong rows -- corrupting both the
    coverage flag and the defensive values, which feed the +2 bonus and so
    moved total_points itself. Shapes matched throughout, so nothing complained.
    """
    sys.path.insert(0, 'scripts')
    import build_dataset

    raw = pd.DataFrame({
        'season': ['2021-22', '2021-22', '2025-26', '2025-26'],
        'element': [1, 2, 1, 2], 'fixture': [10, 11, 20, 21], 'GW': [1, 1, 1, 1],
        'position': ['DEF'] * 4, 'total_points': [2, 2, 2, 2],
        'tackles': [0, 0, 9, 9], 'recoveries': [0, 0, 9, 9],
        'clearances_blocks_interceptions': [0, 0, 9, 9],
        'defensive_contribution': [0, 0, 0, 0],
    }, index=[3, 1, 0, 2])          # not a RangeIndex, as in the real pipeline

    lookup = pd.DataFrame({
        'season': ['2021-22'], 'element': [1], 'fixture': [10],
        'tackles': [4], 'recoveries': [2], 'clearances_blocks_interceptions': [1]})

    orig = build_dataset.defensive_lookup
    build_dataset.defensive_lookup = lambda _p: lookup
    try:
        out = build_dataset.build_final(raw, 'ignored').set_index(['season', 'element'])
    finally:
        build_dataset.defensive_lookup = orig

    assert out.loc[('2021-22', 1), 'tackles'] == 4, 'joined row lost its value'
    assert out.loc[('2021-22', 2), 'tackles'] == 0, 'unmatched row invented a value'
    assert out.loc[('2025-26', 1), 'tackles'] == 9, 'native value overwritten'
    assert out.loc[('2025-26', 2), 'tackles'] == 9, 'native value overwritten'
    assert out.loc[('2021-22', 2), 'has_fbref_defensive'] == 0,         'row with no lookup entry flagged as covered'


check('scrambled index does not misroute defensive values',
      t_scrambled_index_does_not_misroute)

print()
if failures:
    raise SystemExit(f"{len(failures)} test(s) failed: {failures}")
print(f"all tests passed")
