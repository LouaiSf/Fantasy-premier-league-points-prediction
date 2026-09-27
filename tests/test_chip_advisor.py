import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from optimise import compute_chips  # noqa: E402
from chip_engine import (  # noqa: E402
    _candidate_window, _expected_autosub_points, _no_chip_total, _optimise,
    build_point_matrix, ChipPlanPolicy,
)


CHIPS = ('triple_captain', 'bench_boost', 'free_hit', 'wildcard')


def player(element, name, team, position, points, status='a'):
    return {
        'element': element,
        'name': name,
        'team': team,
        'position': position,
        'value_m': 5.0,
        'predicted_points': points,
        'status': status,
        'p_plays': 1.0 if status == 'a' else 0.0,
    }


def market():
    rows = [
        player(1, 'GK 1', 'Club 1', 'GK', 4.0),
        player(2, 'GK 2', 'Club 2', 'GK', 3.0),
    ]
    rows += [player(10 + i, f'DEF {i}', f'Club {3 + i}', 'DEF', 5.0)
             for i in range(5)]
    rows += [player(20 + i, f'MID {i}', f'Club {8 + i}', 'MID',
                    10.0 if i == 0 else 4.0) for i in range(5)]
    rows += [player(30 + i, f'FWD {i}', f'Club {13 + i}', 'FWD', 5.0)
             for i in range(3)]
    rows += [player(100 + i, f'Alt {i}', f'Club {16 + i}', 'MID', 7.0)
             for i in range(5)]
    return pd.DataFrame(rows)


def horizon_points(players, gameweeks):
    return pd.DataFrame(
        {gameweek: players['predicted_points'].to_numpy() for gameweek in gameweeks},
        index=players.index,
    )


def write_season(tmp_path, double=False, blank=False, weeks=38):
    """A 20-team season with a fixture every gameweek 1..weeks.

    Defaults to a full 38-gameweek season, since compute_chips now always
    plans through GW38 regardless of the requested horizon. Pass a smaller
    `weeks` to deliberately test what happens once fixtures run out (a
    genuinely blank tail, not just an uncovered-but-fixtured week).
    """
    data = tmp_path / 'data' / 'test-season'
    data.mkdir(parents=True)
    pd.DataFrame({
        'id': range(1, 21),
        'name': [f'Club {i}' for i in range(1, 21)],
    }).to_csv(data / 'teams.csv', index=False)
    fixtures = []
    fixture_id = 1
    for gw in range(1, weeks + 1):
        team_ids = list(range(1, 21))
        if blank and gw == 3:
            team_ids = list(range(1, 19))
        pairs = list(zip(team_ids[::2], team_ids[1::2]))
        if double and gw == 2:
            pairs += [(1, 3), (8, 10)]
        for home, away in pairs:
            fixtures.append({
                'id': fixture_id,
                'event': gw,
                'team_h': home,
                'team_a': away,
                'team_h_difficulty': 2,
                'team_a_difficulty': 4,
            })
            fixture_id += 1
    pd.DataFrame(fixtures).to_csv(data / 'fixtures.csv', index=False)
    return data


def synced_inventory(state='unused'):
    return {
        'first_half': {chip: state for chip in CHIPS},
        'second_half': {chip: 'unused' for chip in CHIPS},
    }


# ---------------------------------------------------------------------------
# _candidate_window (chip eligibility, per gameweek, across the half boundary)
# ---------------------------------------------------------------------------
def test_candidate_window_spans_half_boundary(monkeypatch, tmp_path):
    inventory = {'first_half': {chip: 'unused' for chip in CHIPS},
                 'second_half': {chip: 'unused' for chip in CHIPS}}

    eligible, halves = _candidate_window(18, 21, 'wildcard', inventory, [], None)
    assert eligible == [18, 19, 20, 21]
    assert set(halves) == {'first_half', 'second_half'}
    assert halves['first_half']['expires_after_gameweek'] == 19
    assert halves['second_half']['expires_after_gameweek'] == 38

    inventory['first_half']['wildcard'] = 'used'
    eligible, _ = _candidate_window(18, 21, 'wildcard', inventory, [], None)
    assert eligible == [20, 21]


def test_gameweek_one_has_no_wildcard_or_free_hit_but_keeps_captain_and_bench():
    inventory = {'first_half': {chip: 'unused' for chip in CHIPS}, 'second_half': {}}

    windows = {chip: _candidate_window(1, 3, chip, inventory, [], None)[0] for chip in CHIPS}

    assert windows['wildcard'] == [2, 3]
    assert windows['free_hit'] == [2, 3]
    assert windows['triple_captain'] == [1, 2, 3]
    assert windows['bench_boost'] == [1, 2, 3]


def test_free_hit_in_gw19_blocks_free_hit_in_gw20_only():
    inventory = {'first_half': {'free_hit': 'used'}, 'second_half': {'free_hit': 'unused'}}

    blocked, _ = _candidate_window(19, 21, 'free_hit', inventory, [], 19)
    allowed, _ = _candidate_window(19, 21, 'free_hit', inventory, [], 5)

    assert blocked == [21]
    assert allowed == [20, 21]


def test_scheduled_gameweeks_are_excluded_from_every_chip():
    inventory = {'first_half': {chip: 'unused' for chip in CHIPS}, 'second_half': {}}

    windows = {chip: _candidate_window(5, 8, chip, inventory, [6], None)[0] for chip in CHIPS}

    assert all(6 not in window for window in windows.values())


# ---------------------------------------------------------------------------
# A2: build_point_matrix -- covered weeks as-is, uncovered weeks extrapolated
# ---------------------------------------------------------------------------
def _fixture_frame(index, gw_to_count, gw_to_difficulty):
    columns = {}
    for gw, count in gw_to_count.items():
        columns[(gw, 'fixtures')] = pd.Series(count, index=index, dtype=float)
        columns[(gw, 'difficulty')] = pd.Series(gw_to_difficulty[gw], index=index, dtype=float)
    frame = pd.DataFrame(columns, index=index)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


def test_build_point_matrix_keeps_covered_weeks_as_is():
    players = pd.DataFrame({'value_m': [5.0], 'status': ['a']})
    future_points = pd.DataFrame({6: [8.0], 7: [4.0]}, index=players.index)
    fixtures = _fixture_frame(players.index, {6: 1, 7: 1, 8: 1}, {6: 3, 7: 3, 8: 3})

    matrix, week_state = build_point_matrix(players, future_points, fixtures, 6, 8)

    assert matrix.loc[0, 6] == 8.0
    assert matrix.loc[0, 7] == 4.0
    assert week_state[6] == 'projected'
    assert week_state[7] == 'projected'


def test_build_point_matrix_extrapolates_uncovered_weeks_by_fdr():
    players = pd.DataFrame({'value_m': [5.0], 'status': ['a']})
    # 6 pts across 1 fixture at neutral FDR (3) each of two covered weeks ->
    # per_fixture_xp = 6.0. GW8 has a single easier fixture (FDR 1): a
    # +2-below-neutral difficulty bumps the rate by 2 * FDR_SLOPE (12%).
    future_points = pd.DataFrame({6: [6.0], 7: [6.0]}, index=players.index)
    fixtures = _fixture_frame(players.index, {6: 1, 7: 1, 8: 1}, {6: 3, 7: 3, 8: 1})

    matrix, week_state = build_point_matrix(players, future_points, fixtures, 6, 8)

    assert week_state[8] == 'extrapolated'
    assert matrix.loc[0, 8] == pytest.approx(6.0 * 1.12, rel=1e-6)


def test_build_point_matrix_blank_gameweek_prices_at_zero():
    players = pd.DataFrame({'value_m': [5.0], 'status': ['a']})
    future_points = pd.DataFrame({6: [6.0]}, index=players.index)
    fixtures = _fixture_frame(players.index, {6: 1, 7: 0}, {6: 3, 7: 3})

    matrix, week_state = build_point_matrix(players, future_points, fixtures, 6, 7)

    assert matrix.loc[0, 7] == 0.0
    assert week_state[7] == 'no_fixtures'


def test_build_point_matrix_zeroes_hard_unavailable_only_for_current_gw():
    players = pd.DataFrame({'value_m': [5.0], 'status': ['i']})
    future_points = pd.DataFrame({6: [8.0], 7: [8.0]}, index=players.index)
    fixtures = _fixture_frame(players.index, {6: 1, 7: 1}, {6: 3, 7: 3})

    matrix, _ = build_point_matrix(players, future_points, fixtures, 6, 7)

    assert matrix.loc[0, 6] == 0.0
    # GW7's export already reflects whatever chance he returns; not re-zeroed.
    assert matrix.loc[0, 7] == 8.0


# ---------------------------------------------------------------------------
# A3: bench boost autosub netting (direct formula tests)
# ---------------------------------------------------------------------------
def _current_result(xi_rows, bench_rows):
    return {'xi': pd.DataFrame(xi_rows), 'bench': pd.DataFrame(bench_rows)}


def test_bench_boost_full_gain_when_every_starter_certain_to_play():
    xi = [{'position': 'GK', 'predicted_points': 5.0}] + [
        {'position': 'MID', 'predicted_points': 4.0} for _ in range(10)]
    bench = [
        {'position': 'MID', 'predicted_points': 6.0},
        {'position': 'DEF', 'predicted_points': 3.0},
        {'position': 'FWD', 'predicted_points': 1.0},
        {'position': 'GK', 'predicted_points': 0.0},
    ]
    result = _current_result(xi, bench)
    p_plays = pd.DataFrame(1.0, index=range(15), columns=[6])

    autosub = _expected_autosub_points(result, p_plays, 6)

    assert autosub == 0.0
    bench_total = sum(row['predicted_points'] for row in bench)
    assert bench_total - autosub == 10.0


def test_bench_boost_gain_shrinks_when_starters_are_uncertain():
    xi = [{'position': 'GK', 'predicted_points': 5.0}] + [
        {'position': 'MID', 'predicted_points': 4.0} for _ in range(10)]
    bench = [
        {'position': 'MID', 'predicted_points': 6.0},
        {'position': 'DEF', 'predicted_points': 3.0},
        {'position': 'FWD', 'predicted_points': 1.0},
        {'position': 'GK', 'predicted_points': 0.0},
    ]
    result = _current_result(xi, bench)
    # Two outfield starters are 50/50 to play: m = 1.0 expected gap, so the
    # first bench slot (6.0 pts) is fully "used up" by the expected autosub.
    p_plays = pd.DataFrame(1.0, index=range(15), columns=[6])
    p_plays.loc[[1, 2], 6] = 0.5

    autosub = _expected_autosub_points(result, p_plays, 6)
    bench_total = sum(row['predicted_points'] for row in bench)

    assert autosub == pytest.approx(6.0)
    assert bench_total - autosub < 10.0


# ---------------------------------------------------------------------------
# A3: Free Hit's no-chip baseline depends on free transfers
# ---------------------------------------------------------------------------
def test_free_hit_baseline_improves_with_more_free_transfers(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15]
    point_matrix = horizon_points(players, [6])
    cost_overrides = {i: float(row['value_m']) for i, row in squad.iterrows()}
    opt = _optimise()

    one_transfer = _no_chip_total(
        opt, players, point_matrix, 6, squad.index, 100.0, cost_overrides, free_transfers=1)
    two_transfers = _no_chip_total(
        opt, players, point_matrix, 6, squad.index, 100.0, cost_overrides, free_transfers=2)

    # Two of the squad's 4.0-point MIDs can each be swapped for a 7.0-point
    # 'Alt' MID sitting outside the squad; one free transfer can only afford
    # one of those swaps, two free transfers capture both.
    assert two_transfers > one_transfer


# ---------------------------------------------------------------------------
# A4: horizon-independence, discounting, close calls and the joint plan
# ---------------------------------------------------------------------------
def _captain_scenario(tmp_path, monkeypatch, points_by_gw: dict, first_gw=6):
    """A squad where the highest-points player each week is an unambiguous
    captain choice, with per-gameweek control over exactly how much he
    scores -- everyone else stays low and flat so no other week or chip
    competes for "current-week candidate"."""
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()
    gameweeks = list(range(first_gw, 20))
    points = pd.DataFrame(1.0, index=players.index, columns=gameweeks)
    captain_row = players.index[players['element'] == 20][0]  # 'MID 0'
    for gw, value in points_by_gw.items():
        points.loc[captain_row, gw] = value
    data = compute_chips(squad, 'test-season', first_gw, 8, players,
                         inventory=synced_inventory(), future_points=points)
    return data


def test_triple_captain_planned_now_when_a_later_week_does_not_clear_the_discount(monkeypatch, tmp_path):
    # The plan's own worked example: 7.05 now vs 7.17 ten weeks later, which
    # discounts to ~4.3 (0.95**10 ~ 0.599) -- well short of 7.05.
    data = _captain_scenario(tmp_path, monkeypatch, {6: 7.05, 16: 7.17})
    tc = next(rec for rec in data['recommendations'] if rec['chip'] == 'triple_captain')

    assert tc['gw'] == 6
    assert tc['status'] == 'play_now'
    assert tc['gain'] == pytest.approx(7.05, abs=0.01)
    assert tc['close_call'] is False


def test_triple_captain_close_call_when_next_week_barely_beats_now(monkeypatch, tmp_path):
    data = _captain_scenario(tmp_path, monkeypatch, {6: 7.05, 7: 7.6})
    tc = next(rec for rec in data['recommendations'] if rec['chip'] == 'triple_captain')

    # GW7's discounted gain (7.6 * 0.95 ~= 7.22) edges out GW6's 7.05, but by
    # less than the 1.0-point close-call margin.
    assert tc['gw'] == 7
    assert tc['close_call'] is True


def test_same_squad_gives_same_plan_at_every_ui_horizon(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()
    points = horizon_points(players, range(6, 20))

    plans = [
        compute_chips(squad, 'test-season', 6, horizon, players,
                      inventory=synced_inventory(), future_points=points)['chip_plan']
        for horizon in (4, 8, 12, 16)
    ]

    assert all(plan == plans[0] for plan in plans[1:])


def test_wildcard_gain_is_horizon_independent(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()
    points = horizon_points(players, range(6, 20))

    short = compute_chips(squad, 'test-season', 6, 4, players,
                          inventory=synced_inventory(), future_points=points)
    long = compute_chips(squad, 'test-season', 6, 16, players,
                         inventory=synced_inventory(), future_points=points)
    wc_short = next(rec for rec in short['recommendations'] if rec['chip'] == 'wildcard')
    wc_long = next(rec for rec in long['recommendations'] if rec['chip'] == 'wildcard')

    assert wc_short['gains_by_week'] == wc_long['gains_by_week']


def test_joint_plan_never_assigns_two_chips_to_the_same_gameweek(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()
    points = horizon_points(players, range(6, 20))

    data = compute_chips(squad, 'test-season', 6, 8, players,
                         inventory=synced_inventory(), future_points=points)

    assigned_weeks = [entry['gw'] for entry in data['chip_plan']]
    assert len(assigned_weeks) == len(set(assigned_weeks))


def test_joint_plan_honours_a_chip_already_planned_for_a_specific_week(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()
    points = horizon_points(players, range(6, 20))

    # Wildcard already planned for GW9: every other chip's candidate window
    # must exclude GW9, so the joint plan can never double-book it.
    data = compute_chips(squad, 'test-season', 6, 8, players,
                         inventory=synced_inventory(), future_points=points,
                         scheduled_gameweeks=[9])

    for rec in data['recommendations']:
        assert 9 not in rec['candidate_gameweeks']


# ---------------------------------------------------------------------------
# Fixture-only mode (no complete squad)
# ---------------------------------------------------------------------------
def test_no_squad_is_explicit_fixture_only_mode(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)

    data = compute_chips(None, 'test-season', 2, 4, market())

    assert data['inventory_source'] == 'unknown'
    assert data['projection_mode'] == 'fixture_signal'
    assert data['has_squad'] is False
    assert all(rec['gain'] is None for rec in data['recommendations'])
    assert all(rec['status'] == 'no_squad' for rec in data['recommendations'])
    assert all(row['fixture_signal'] is not None for row in data['rows'])
    assert data['chip_plan'] == []


def test_incomplete_squad_falls_back_to_fixture_signal(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:14].copy()  # one short of a legal 15

    data = compute_chips(squad, 'test-season', 2, 4, players,
                         inventory=synced_inventory(), future_points=horizon_points(players, [2, 3]))

    assert data['has_squad'] is False
    assert data['projection_mode'] == 'fixture_signal'


def _fully_spent_inventory(state='used'):
    # Both halves gone, not just the current one: compute_chips always plans
    # through GW38, so a chip merely used in the *current* half still has a
    # next-half copy to look forward to and isn't "unavailable" overall.
    return {
        'first_half': {chip: state for chip in CHIPS},
        'second_half': {chip: state for chip in CHIPS},
    }


def test_used_chip_is_unavailable(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)

    data = compute_chips(None, 'test-season', 2, 4, market(),
                         inventory=_fully_spent_inventory('used'))

    assert all(rec['status'] == 'unavailable' for rec in data['recommendations'])


def test_expired_first_half_chip_is_unavailable(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)

    data = compute_chips(None, 'test-season', 25, 4, market(),
                         inventory=_fully_spent_inventory('expired'))

    assert all(rec['status'] == 'unavailable' for rec in data['recommendations'])


def test_chip_used_only_in_the_current_half_stays_available_for_the_other(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)

    data = compute_chips(None, 'test-season', 2, 4, market(),
                         inventory=synced_inventory('used'))

    # 'used' only in first_half (synced_inventory's default): second_half is
    # still unused, so every chip still has a real (later) candidate window.
    assert all(rec['status'] == 'no_squad' for rec in data['recommendations'])
    assert all(rec['candidate_gameweeks'] for rec in data['recommendations'])


# ---------------------------------------------------------------------------
# Squad-specific evidence and identity
# ---------------------------------------------------------------------------
def test_dgw_scores_actual_captain_and_bench(monkeypatch, tmp_path):
    write_season(tmp_path, double=True)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()

    points = horizon_points(players, range(1, 20))
    points.loc[:, 2] *= 2  # GW2's double gameweek
    data = compute_chips(squad, 'test-season', 1, 3, players,
                         inventory=synced_inventory(), future_points=points)
    by_chip = {rec['chip']: rec for rec in data['recommendations']}

    assert data['rows'][1]['dgw_teams'] == 4
    tc = by_chip['triple_captain']
    assert tc['gains_by_week'].get('2') is None or tc['gains_by_week'].get(2) is not None
    assert max(tc['gains_by_week'].values()) > 0
    bb_evidence = by_chip['bench_boost']['evidence']
    assert len(bb_evidence['ordered_bench']) == 4
    assert bb_evidence['bench_total'] == round(
        sum(player['points'] for player in bb_evidence['ordered_bench']), 2)


def test_blank_gameweek_gives_free_hit_a_real_comparison(monkeypatch, tmp_path):
    write_season(tmp_path, blank=True)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()

    data = compute_chips(squad, 'test-season', 2, 3, players,
                         inventory=synced_inventory(),
                         future_points=horizon_points(players, range(2, 20)))
    free_hit = next(rec for rec in data['recommendations'] if rec['chip'] == 'free_hit')

    assert data['rows'][1]['blank_teams'] == 2
    assert free_hit['evidence'] is not None
    assert 'free_hit_total' in free_hit['evidence']
    assert 'no_chip_total' in free_hit['evidence']


def test_owned_unavailable_player_is_kept_by_identity(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    players.loc[players['element'] == 30, ['status', 'p_plays']] = ['i', 0.0]
    squad = players.iloc[:15].copy()
    buyable = players[players['element'] != 30].reset_index(drop=True)
    owned_row = players[players['element'] == 30]
    combined = pd.concat([buyable, owned_row], ignore_index=True)
    future = horizon_points(combined, range(2, 20))

    data = compute_chips(squad, 'test-season', 2, 2, combined,
                         inventory=synced_inventory(), future_points=future)

    assert data['has_squad'] is True
    assert data['projection_mode'] == 'model_projection'


def test_selling_price_changes_free_hit_and_wildcard_budget(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    players.loc[players['name'].str.startswith('Alt'), 'predicted_points'] = 1.0
    players.loc[players['element'] == 24, 'value_m'] = 8.0
    squad = players.iloc[:15].copy()
    with_target = pd.concat([
        players,
        pd.DataFrame([player(200, 'Reach', 'Club 20', 'MID', 50.0)]),
    ], ignore_index=True)
    with_target.loc[with_target['element'] == 200, 'value_m'] = 7.0
    points = horizon_points(with_target, range(2, 20))

    no_finance = compute_chips(squad, 'test-season', 2, 1, with_target,
                               inventory=synced_inventory(), future_points=points)
    free_hit_no_finance = next(
        rec for rec in no_finance['recommendations'] if rec['chip'] == 'free_hit')
    assert free_hit_no_finance['evidence']['free_hit_total'] >= 90

    with_finance = compute_chips(squad, 'test-season', 2, 1, with_target,
                                 inventory=synced_inventory(), future_points=points,
                                 bank=0.0, selling_prices={24: 6.5})
    free_hit_with_finance = next(
        rec for rec in with_finance['recommendations'] if rec['chip'] == 'free_hit')
    assert free_hit_with_finance['evidence']['free_hit_total'] < 90
    assert any('Budget estimated from current market value' in warning
              for warning in free_hit_no_finance['warnings'])


# ---------------------------------------------------------------------------
# A2: extrapolation beyond the export's coverage
# ---------------------------------------------------------------------------
def test_export_shorter_than_the_half_still_has_a_squad_plan_with_extrapolated_weeks(monkeypatch, tmp_path):
    write_season(tmp_path)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)
    squad = players.iloc[:15].copy()
    # Covers only GW6-9, well short of the GW6-19 first half.
    points = horizon_points(players, range(6, 10))

    data = compute_chips(squad, 'test-season', 6, 4, players,
                         inventory=synced_inventory(), future_points=points)

    assert data['has_squad'] is True
    assert data['projection_mode'] == 'model_projection'
    assert data['week_states'][6] == 'projected'
    assert data['week_states'][12] == 'extrapolated'


def test_fixture_only_mode_marks_weeks_with_no_confirmed_fixtures_unknown(monkeypatch, tmp_path):
    # Fixture-only mode (no squad) never runs build_point_matrix, so its
    # week labelling is coarser: 'complete' where teams have fixtures,
    # 'unknown' once the fixture file itself has run out.
    write_season(tmp_path, weeks=14)
    monkeypatch.chdir(tmp_path)
    players = market().reset_index(drop=True)

    data = compute_chips(None, 'test-season', 13, 4, players)

    assert data['week_states'][13] == 'complete'
    assert data['week_states'][15] == 'unknown'
