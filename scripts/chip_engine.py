"""The Chip Advisor engine (contract v4): squad-specific, horizon-independent.

Moved out of optimise.py so the chip machinery -- which has grown into its
own model of projection, gain and planning -- has its own file. optimise.py
re-exports `compute_chips` (and the other names tests/webapp import) at the
bottom of its module, once its own solver functions exist, so `opt.compute_chips`
keeps working unchanged.

This module never imports `optimise` at the top level: every function that
needs `solve_squad`, `solve_squad_horizon`, `fixture_calendar` and friends
fetches them lazily through `_optimise()`. That is what lets optimise.py
import *this* module at its own bottom without a circular-import failure,
regardless of which of the two modules a caller happens to import first.
"""
from __future__ import annotations

import dataclasses
import itertools
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from chip_policy import FIXTURE_DEPENDENT_CHIPS, ChipPlanPolicy


def _optimise():
    # Prefer whichever module identity (bare `optimise` or `scripts.optimise`)
    # is already loaded, rather than importing fresh: this file's callers use
    # both spellings (tests and the CLI import bare; webapp/app.py imports
    # `scripts.optimise`), and a fresh import under the spelling nobody asked
    # for would create a second, independent copy of optimise.py's module
    # state -- invisible to a caller that monkeypatches the one it imported.
    import sys
    for name in ('optimise', 'scripts.optimise'):
        if name in sys.modules:
            return sys.modules[name]
    try:
        from scripts import optimise as opt
    except ImportError:
        import optimise as opt
    return opt


CHIP_IDS = ('triple_captain', 'bench_boost', 'free_hit', 'wildcard')
CHIP_LABELS = {
    'triple_captain': 'Triple Captain',
    'bench_boost': 'Bench Boost',
    'free_hit': 'Free Hit',
    'wildcard': 'Wildcard',
}
CHIP_METHOD_VERSION = '3.0'
CHIPS_CONTRACT_VERSION = 4
FIRST_HALF_LAST_GW = 19
SECOND_HALF_LAST_GW = 38
# The exported future points are already p(plays) * points-if-plays, so a
# second appearance discount would count the same uncertainty twice.
PROJECTION_SEMANTICS = 'expected_points_including_appearance'
HARD_UNAVAILABLE_STATUSES = frozenset({'i', 'u', 's', 'n'})
# How much an extrapolated (uncovered) week's per-fixture rate is nudged by
# its average FDR: +/-1 difficulty point moves the rate 6%, clipped at 0.
FDR_SLOPE = 0.06
DEFAULT_FREE_TRANSFERS = 1
SOLVER_TIME_LIMIT_SECONDS = 10.0
SOLVER_GAP_REL = 0.005
# Free Hit and Wildcard each solve a full-market MILP once or twice per
# candidate week -- up to ~19 weeks in a GW1 half. The full ~500-player
# market makes that too slow for an interactive request (a full-season cold
# run measured ~55s). Restricting the pool to each position's best prospects
# by total predicted points over the window, plus its cheapest few (budget
# enablers) and every owned player, cuts the market to well under half its
# size without changing the optimum in practice: a genuinely optimal transfer
# target is essentially never outside a position's top tier or its cheapest
# fillers. Measured on real GW6 data: identical wildcard/free-hit gains at
# every tested cut down to 15+4, so 25+6 keeps a wide safety margin.
MARKET_REDUCTION_PER_POSITION = 25
MARKET_REDUCTION_CHEAPEST = 6


# ---------------------------------------------------------------------------
# Shared player/squad helpers (unchanged behaviour from the pre-v4 engine)
# ---------------------------------------------------------------------------
def _player_key(row: pd.Series) -> str | int:
    if 'element' in row.index and pd.notna(row['element']):
        return int(row['element'])
    return str(row.get('name', ''))


def _align_squad_to_players(players: pd.DataFrame, squad: pd.DataFrame) -> pd.DataFrame:
    player_indexes = {}
    for index, row in players.iterrows():
        key = _player_key(row)
        if key in player_indexes:
            raise ValueError(f'duplicate player identity: {key}')
        player_indexes[key] = index

    aligned = squad.copy()
    aligned_indexes = []
    for _, row in aligned.iterrows():
        key = _player_key(row)
        if key not in player_indexes:
            raise ValueError(f'squad player is not in the market: {key}')
        aligned_indexes.append(player_indexes[key])
    if len(set(aligned_indexes)) != len(aligned_indexes):
        raise ValueError('the same player appears twice in that squad')
    aligned.index = aligned_indexes
    return aligned


def _result_total(result: dict) -> float:
    total = float(result['xi']['predicted_points'].sum())
    if result.get('captain') is not None:
        total += float(result['captain']['predicted_points'])
    return total


def _horizon_week_total(week: dict, point_matrix: pd.DataFrame, gameweek: int) -> float:
    total = float(point_matrix.loc[week['xi'].index, gameweek].sum())
    if week.get('captain') is not None:
        total += float(point_matrix.loc[week['captain'].name, gameweek])
    return total


def _half_of(gameweek: int) -> str:
    return 'first_half' if gameweek <= FIRST_HALF_LAST_GW else 'second_half'


def _half_last_gw(gameweek: int) -> int:
    return FIRST_HALF_LAST_GW if gameweek <= FIRST_HALF_LAST_GW else SECOND_HALF_LAST_GW


def _candidate_window(first_gw: int, last_gw: int, chip: str,
                      inventory: dict, scheduled: list,
                      last_free_hit: int | None) -> tuple[list, dict]:
    """Eligible gameweeks for one chip, decided one gameweek at a time.

    2026/27 gives two chip sets: GW1-19 and GW20-38. Each gameweek is checked
    against the inventory of the set it belongs to, so a span that crosses
    GW19/20 offers candidates from both. One chip per gameweek; Wildcard and
    Free Hit are unavailable in GW1; a GW19 Free Hit blocks one in GW20.
    """
    halves: dict[str, dict] = {}
    eligible = []
    for gw in range(first_gw, last_gw + 1):
        half = _half_of(gw)
        window = halves.setdefault(half, {
            'half': half,
            'state': inventory.get(half, {}).get(chip, 'unknown'),
            'expires_after_gameweek': FIRST_HALF_LAST_GW if half == 'first_half' else SECOND_HALF_LAST_GW,
            'gameweeks': [],
        })
        window['gameweeks'].append(gw)
        if window['state'] in {'used', 'expired'} or gw in scheduled:
            continue
        if chip in {'wildcard', 'free_hit'} and gw == 1:
            continue
        if chip == 'free_hit' and last_free_hit == FIRST_HALF_LAST_GW and gw == FIRST_HALF_LAST_GW + 1:
            continue
        eligible.append(gw)
    return eligible, halves


# ---------------------------------------------------------------------------
# A2: the per-week projection matrix that never discards the squad
# ---------------------------------------------------------------------------
def _player_fixture_frame(players: pd.DataFrame, calendar: pd.DataFrame,
                          name_to_id: dict, gameweeks: list) -> pd.DataFrame:
    """Per player per gameweek fixture count and average difficulty.

    A DataFrame indexed like `players`, with a two-level column
    (gameweek, 'fixtures' | 'difficulty') -- the shape `build_point_matrix`
    needs to extrapolate blanks, doubles and hard fixture runs per player.
    """
    team_ids = players['team'].map(name_to_id)
    known_teams = sorted({t for t in name_to_id.values()})
    counts = calendar.pivot_table(index='event', columns='team', values='fixtures', fill_value=0)
    diffs = calendar.pivot_table(index='event', columns='team', values='difficulty')
    counts = counts.reindex(index=gameweeks, columns=known_teams, fill_value=0)
    diffs = diffs.reindex(index=gameweeks, columns=known_teams)

    columns = {}
    for gw in gameweeks:
        columns[(gw, 'fixtures')] = team_ids.map(counts.loc[gw]).fillna(0.0)
        columns[(gw, 'difficulty')] = team_ids.map(diffs.loc[gw])
    frame = pd.DataFrame(columns, index=players.index)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=['gw', 'metric'])
    return frame


def build_point_matrix(players: pd.DataFrame, future_points: pd.DataFrame | None,
                       fixtures: pd.DataFrame, first_gw: int, last_gw: int,
                       ) -> tuple[pd.DataFrame, dict]:
    """A player-by-gameweek points matrix that always covers [first_gw, last_gw].

    Covered weeks (columns present in `future_points`) use the export as-is,
    since it already folds in the chance of playing; only a *hard* official
    absence (injured/suspended/loan/not-in-squad) zeroes a player, and only
    for the current gameweek -- a player ruled out today may return next week,
    and the export for later weeks already reflects that.

    Every other week in the range is extrapolated per player: this player's
    own mean points-per-fixture over the covered weeks (skipping blanks),
    times how many fixtures he has that week, nudged by that week's average
    fixture difficulty (`FDR_SLOPE` per point away from a neutral FDR of 3).
    A team with no fixture that week prices at zero either way.

    Returns (matrix, week_state), where week_state[gw] is 'projected' (a
    covered week), 'extrapolated' (uncovered, but somebody has a fixture) or
    'no_fixtures' (an uncovered week where nobody in the squad/market has one
    -- a genuine blank gameweek).
    """
    gameweeks = list(range(first_gw, last_gw + 1))
    matrix = pd.DataFrame(0.0, index=players.index, columns=gameweeks)
    week_state: dict[int, str] = {}

    covered = []
    if future_points is not None:
        covered = [gw for gw in gameweeks if gw in future_points.columns]
        for gw in covered:
            matrix[gw] = (
                pd.to_numeric(future_points[gw], errors='coerce')
                .reindex(players.index).fillna(0.0)
            )

    if first_gw in covered and 'status' in players.columns:
        hard_out = players.index[players['status'].isin(HARD_UNAVAILABLE_STATUSES)]
        matrix.loc[hard_out, first_gw] = 0.0

    def fixtures_for(gw: int) -> pd.Series:
        return fixtures[(gw, 'fixtures')].reindex(players.index).fillna(0.0)

    def difficulty_for(gw: int) -> pd.Series:
        return fixtures[(gw, 'difficulty')].reindex(players.index)

    per_fixture_terms = []
    for gw in covered:
        count = fixtures_for(gw)
        has_fixture = count > 0
        rate = (matrix[gw] / count.replace(0.0, pd.NA)).where(has_fixture)
        per_fixture_terms.append(rate)
    per_fixture_xp = (
        pd.concat(per_fixture_terms, axis=1).astype(float).mean(axis=1, skipna=True)
        if per_fixture_terms else pd.Series(0.0, index=players.index)
    ).fillna(0.0)

    for gw in gameweeks:
        if gw in covered:
            week_state[gw] = 'projected'
            continue
        count = fixtures_for(gw)
        difficulty = difficulty_for(gw).fillna(3.0)
        factor = (1.0 + FDR_SLOPE * (3.0 - difficulty)).clip(lower=0.0)
        estimate = (per_fixture_xp * count * factor).clip(lower=0.0)
        matrix[gw] = estimate.where(count > 0, 0.0)
        week_state[gw] = 'no_fixtures' if float(count.sum()) == 0.0 else 'extrapolated'

    return matrix, week_state


def _reduced_market(players: pd.DataFrame, point_matrix: pd.DataFrame, squad_index,
                    per_position: int = MARKET_REDUCTION_PER_POSITION,
                    cheapest: int = MARKET_REDUCTION_CHEAPEST) -> pd.DataFrame:
    """A smaller candidate pool for Free Hit/Wildcard's full-market solves.

    See MARKET_REDUCTION_PER_POSITION for why this is safe: every owned
    player is always kept (so the squad stays a legal starting point), and
    each position keeps its best prospects by total projected points over the
    evaluated window plus its very cheapest options, so the budget-filler
    role a sub-4.5m player plays is never lost.
    """
    total_points = point_matrix.sum(axis=1)
    keep = set(squad_index)
    for position in players['position'].unique():
        pos_index = players.index[players['position'] == position]
        ranked = total_points.loc[pos_index].sort_values(ascending=False)
        keep.update(ranked.index[:per_position])
        cheapest_index = players.loc[pos_index].sort_values('value_m').index[:cheapest]
        keep.update(cheapest_index)
    return players.loc[sorted(keep)]


def _p_plays_matrix(players: pd.DataFrame, future_p_plays: pd.DataFrame | None,
                    gameweeks: list) -> pd.DataFrame:
    """Per player per gameweek chance of playing, defaulting to 1.0.

    Only covered weeks carry real information; an uncovered week is treated
    as "expected to play" rather than extrapolated, since the export doesn't
    give a fixture-difficulty-shaped signal for availability the way it does
    for points.
    """
    if future_p_plays is None:
        return pd.DataFrame(1.0, index=players.index, columns=gameweeks)
    matrix = future_p_plays.reindex(index=players.index, columns=gameweeks)
    matrix = matrix.apply(pd.to_numeric, errors='coerce')
    return matrix.fillna(1.0).clip(lower=0.0, upper=1.0)


# ---------------------------------------------------------------------------
# A3: comparable per-week gains, one per chip
# ---------------------------------------------------------------------------
def _current_week_result(opt, squad: pd.DataFrame, point_matrix: pd.DataFrame, gw: int):
    adjusted = squad.copy()
    adjusted['predicted_points'] = point_matrix.loc[squad.index, gw].to_numpy()
    budget = float(squad['value_m'].sum())
    result, _status = opt.solve_squad(
        adjusted, budget + 0.01, squad_size=len(squad), bench_weight=0.0, captain=True)
    return result


def _expected_autosub_points(current_result: dict, p_plays: pd.DataFrame, gw: int) -> float:
    """Points the bench is expected to score anyway, through normal autosubs.

    GK: the bench keeper only comes on if the starter doesn't play. Outfield:
    `m` is the expected number of starting-XI gaps this week; bench slot k
    (ordered by projected points, as FPL's own autosub priority is) covers a
    gap with probability `clip(m - (k-1), 0, 1)` -- the first sub is used
    whenever there's at least one gap, the second only when there are two-plus.
    """
    def p_of(index) -> float:
        return float(p_plays.loc[index, gw]) if index in p_plays.index else 1.0

    xi = current_result['xi']
    bench = current_result['bench']
    starting_gk = xi[xi['position'] == 'GK']
    p_start_gk = p_of(starting_gk.index[0]) if len(starting_gk) else 1.0
    bench_gk = bench[bench['position'] == 'GK']
    gk_xp = float(bench_gk['predicted_points'].iloc[0]) if len(bench_gk) else 0.0
    gk_component = (1.0 - p_start_gk) * gk_xp

    outfield_starters = xi[xi['position'] != 'GK']
    gaps = float(sum(1.0 - p_of(i) for i in outfield_starters.index))
    bench_outfield = bench[bench['position'] != 'GK']

    outfield_component = 0.0
    for k, (index, row) in enumerate(bench_outfield.iterrows(), start=1):
        weight = min(1.0, max(0.0, gaps - (k - 1)))
        outfield_component += weight * float(row['predicted_points'])

    return gk_component + outfield_component


def _no_chip_total(opt, players: pd.DataFrame, point_matrix: pd.DataFrame, gw: int,
                   squad_index, budget: float, cost_overrides: dict,
                   free_transfers: int) -> float | None:
    """The best a manager could do this week with a normal (chip-free) transfer."""
    candidate = players.assign(predicted_points=point_matrix[gw])
    result, _status = opt.solve_squad(
        candidate, budget + 0.01, squad_size=opt.SQUAD_SIZE, bench_weight=0.0, captain=True,
        cost_overrides=cost_overrides, owned_indices=list(squad_index),
        max_changes=max(0, free_transfers),
        time_limit_seconds=SOLVER_TIME_LIMIT_SECONDS, gap_rel=SOLVER_GAP_REL)
    if result is None:
        return None
    return _result_total(result)


def _free_hit_total(opt, players: pd.DataFrame, point_matrix: pd.DataFrame, gw: int,
                    budget: float, cost_overrides: dict) -> tuple[float | None, dict | None]:
    result, _status = opt.solve_squad(
        players.assign(predicted_points=point_matrix[gw]), budget + 0.01,
        squad_size=opt.SQUAD_SIZE, bench_weight=0.0, captain=True,
        cost_overrides=cost_overrides,
        time_limit_seconds=SOLVER_TIME_LIMIT_SECONDS, gap_rel=SOLVER_GAP_REL)
    if result is None:
        return None, None
    return _result_total(result), result


def _wildcard_totals(opt, players: pd.DataFrame, point_matrix: pd.DataFrame,
                     window_gws: list, budget: float, cost_overrides: dict,
                     squad_index, free_transfers: int, policy: ChipPlanPolicy,
                     ) -> tuple[float | None, float | None, dict | None]:
    weights = opt.horizon_weights(window_gws, 1.0)
    wc_result, _status = opt.solve_squad_horizon(
        players, point_matrix.loc[:, window_gws], budget + 0.01, weights, bench_weight=0.0,
        cost_overrides=cost_overrides,
        time_limit_seconds=SOLVER_TIME_LIMIT_SECONDS, gap_rel=SOLVER_GAP_REL)
    if wc_result is None:
        return None, None, None
    wc_total = sum(
        _horizon_week_total(wc_result['weeks'][gw], point_matrix, gw) for gw in window_gws)

    baseline_changes = min(opt.SQUAD_SIZE, free_transfers + policy.wildcard_window - 1)
    baseline_result, _status = opt.solve_squad_horizon(
        players, point_matrix.loc[:, window_gws], budget + 0.01, weights, bench_weight=0.0,
        cost_overrides=cost_overrides, owned_indices=list(squad_index),
        max_changes=baseline_changes,
        time_limit_seconds=SOLVER_TIME_LIMIT_SECONDS, gap_rel=SOLVER_GAP_REL)
    if baseline_result is None:
        return None, None, None
    baseline_total = sum(
        _horizon_week_total(baseline_result['weeks'][gw], point_matrix, gw) for gw in window_gws)

    return float(wc_total - baseline_total), float(wc_total), wc_result


# ---------------------------------------------------------------------------
# A4: one joint, horizon-independent chip plan
# ---------------------------------------------------------------------------
def _discount(gain: float | None, week: int, current_gw: int, policy: ChipPlanPolicy) -> float | None:
    if gain is None:
        return None
    factor = policy.future_reliability ** (week - current_gw)
    if week in policy.extrapolated_weeks:
        factor *= policy.extrapolated_reliability
    return gain * factor


def _plan_tokens(candidate_windows: dict) -> list[tuple[str, str, list]]:
    """One (chip, half, eligible weeks) per chip copy still available.

    2026/27 has a full chip set per half, so an unused first-half Triple
    Captain and an unused second-half one are two separate chips to place.
    Planning one week per chip across both halves would let the first-half
    copy expire unplayed whenever the best week fell after GW19.
    """
    tokens = []
    for chip in CHIP_IDS:
        eligible = candidate_windows[chip][0]
        for half in ('first_half', 'second_half'):
            weeks = [gw for gw in eligible if _half_of(gw) == half]
            if weeks:
                tokens.append((chip, half, weeks))
    return tokens


def _gain_in_plan(chip: str, gw: int, placed: dict, gains: dict, after_wildcard: dict):
    """(gain, Wildcard week it depends on) for chip at gw, given the plan's other chips.

    Triple Captain and Bench Boost in the weeks after a planned Wildcard are
    played with the Wildcard's squad, not today's.
    """
    wc_gw = placed.get('wildcard')
    if chip in ('triple_captain', 'bench_boost') and wc_gw is not None and wc_gw < gw:
        later = after_wildcard.get(wc_gw, {}).get(gw, {})
        if chip in later:
            return later[chip][0], wc_gw
    return gains[chip].get(gw), None


def _awaiting_fixtures(tokens: list, doubles: dict, blanks: dict,
                       policy: ChipPlanPolicy) -> set:
    """(chip, half) copies to hold until their half's doubles or blanks are scheduled.

    Without a double or blank on the calendar, a Bench Boost's or Triple
    Captain's weeks differ only by fixture difficulty and the discount, so the
    planner put the second-half copies in GW20-21 -- the opposite of how they
    are best played. Held instead, unless the half is too short to wait.
    """
    held = set()
    for chip, half, weeks in tokens:
        # Only the second half: its doubles and blanks come from the cup
        # rounds, while the first half seldom has any and its chips expire
        # at GW19 regardless.
        if (half != 'second_half' or chip not in FIXTURE_DEPENDENT_CHIPS
                or len(weeks) <= policy.await_fixtures_min_weeks):
            continue
        half_weeks = range(min(weeks), SECOND_HALF_LAST_GW + 1)
        if not any(doubles.get(gw) or blanks.get(gw) for gw in half_weeks):
            held.add((chip, half))
    return held


def _joint_plan(gains: dict, tokens: list, current_gw: int, policy: ChipPlanPolicy,
                after_wildcard: dict | None = None) -> dict:
    """Place every available chip copy, one half at a time.

    Within a half: at most one chip per gameweek, every placed chip must clear
    its MIN_GAIN (or merely be positive once the half is short of weeks --
    an expiring chip is worth any positive week), and the placement maximises
    total discounted gain, with TC/BB re-valued after a Wildcard. Halves are
    independent: their weeks never overlap and each has its own chips.

    Returns {(chip, half): {'gw', 'gain', 'after_wildcard', 'use_or_lose',
    'runner_up_gw', 'runner_up_gain', 'best_unplaced'}}.
    """
    after_wildcard = after_wildcard or {}
    plan = {}
    for half in ('first_half', 'second_half'):
        half_tokens = [t for t in tokens if t[1] == half]
        if not half_tokens:
            continue
        half_weeks = {gw for _, _, weeks in half_tokens for gw in weeks}
        use_or_lose = len(half_weeks) <= len(half_tokens) + policy.use_or_lose_buffer

        def floor(chip: str) -> float:
            return 0.0 if use_or_lose else policy.min_gain[chip]

        def best_possible(chip: str, gw: int):
            values = [gains[chip].get(gw)]
            if chip in ('triple_captain', 'bench_boost'):
                values += [later[gw][chip][0] for later in after_wildcard.values()
                           if chip in later.get(gw, {})]
            values = [v for v in values if v is not None]
            return max(values) if values else None

        options, ranked_by_chip = [], {}
        for chip, _half, weeks in half_tokens:
            ranked = [(gw, best_possible(chip, gw)) for gw in weeks]
            ranked = [(gw, g) for gw, g in ranked if g is not None and g > 0 and g >= floor(chip)]
            ranked.sort(key=lambda t: -_discount(t[1], t[0], current_gw, policy))
            ranked_by_chip[chip] = ranked
            options.append([(chip, gw) for gw, _ in ranked[:policy.plan_top_weeks]] + [(chip, None)])

        best_placed, best_score = {}, 0.0
        for combo in itertools.product(*options):
            placed = {chip: gw for chip, gw in combo if gw is not None}
            if len(set(placed.values())) != len(placed):
                continue
            score = 0.0
            for chip, gw in placed.items():
                gain, _wc = _gain_in_plan(chip, gw, placed, gains, after_wildcard)
                if gain is None or gain <= 0 or gain < floor(chip):
                    break
                score += _discount(gain, gw, current_gw, policy)
            else:
                if score > best_score + 1e-9:
                    best_placed, best_score = placed, score

        for chip, _half, weeks in half_tokens:
            gw = best_placed.get(chip)
            gain, wc_gw = (_gain_in_plan(chip, gw, best_placed, gains, after_wildcard)
                           if gw is not None else (None, None))
            # The runner-up week: this chip's best other week that no other
            # placed chip occupies, valued under the same plan.
            taken = {w for c, w in best_placed.items() if c != chip}
            runner_up_gw, runner_up_gain = None, None
            for other in weeks:
                if other == gw or other in taken:
                    continue
                other_gain, _ = _gain_in_plan(chip, other, {**best_placed, chip: other}, gains, after_wildcard)
                if other_gain is None or other_gain <= 0:
                    continue
                if runner_up_gw is None or (_discount(other_gain, other, current_gw, policy)
                                            > _discount(runner_up_gain, runner_up_gw, current_gw, policy)):
                    runner_up_gw, runner_up_gain = other, other_gain
            best_unplaced = max(((w, g) for w in weeks if (g := gains[chip].get(w)) is not None),
                                key=lambda t: t[1], default=(None, None))
            plan[(chip, half)] = {
                'gw': gw, 'gain': gain, 'after_wildcard': wc_gw, 'use_or_lose': use_or_lose,
                'runner_up_gw': runner_up_gw, 'runner_up_gain': runner_up_gain,
                'best_unplaced': best_unplaced,
            }
    return plan


def _token_status(entry: dict, current_gw: int, policy: ChipPlanPolicy) -> dict:
    gw = entry['gw']
    status = 'hold' if gw is None else ('play_now' if gw == current_gw else 'planned')
    close_call = False
    if gw is not None and entry['runner_up_gw'] is not None:
        close_call = abs(_discount(entry['gain'], gw, current_gw, policy)
                         - _discount(entry['runner_up_gain'], entry['runner_up_gw'], current_gw, policy)
                         ) < policy.close_call_margin
    return {'status': status, 'close_call': close_call,
            'use_or_lose': entry['use_or_lose'] and gw is not None}


# ---------------------------------------------------------------------------
# Fixture-only mode (no complete 15-man squad to evaluate against)
# ---------------------------------------------------------------------------
def _fixture_signal(row: dict) -> dict:
    signal = row['dgw_teams'] * 1.5 + row['blank_teams'] * 1.25
    signal += max(0.0, 3.0 - row['avg_fdr'])
    return {
        'triple_captain': round(signal + row['dgw_teams'], 2),
        'bench_boost': round(signal + row['dgw_teams'] * 2, 2),
        'free_hit': round(signal + row['blank_teams'] * 2, 2),
        'wildcard': round(signal + max(0.0, row['avg_fdr'] - 3.0), 2),
    }


def _captain_and_bench(result: dict, p_plays: pd.DataFrame, gw: int) -> dict:
    """Triple Captain and Bench Boost gains (and evidence) for one squad's week.

    TC adds the captain's points once more; BB adds the bench, less what the
    bench would have scored anyway through autosubs.
    """
    out = {}
    captain = result.get('captain')
    if captain is not None:
        captain_points = float(captain['predicted_points'])
        out['triple_captain'] = (captain_points, {
            'chip': 'triple_captain',
            'captain': {
                'element': _player_key(captain), 'name': str(captain.get('name', '')),
                'team': str(captain.get('team', '')), 'position': str(captain.get('position', '')),
                'projected_points': round(captain_points, 2),
            },
        })
    bench_total = float(result['bench']['predicted_points'].sum())
    autosub = _expected_autosub_points(result, p_plays, gw)
    out['bench_boost'] = (bench_total - autosub, {
        'chip': 'bench_boost',
        'ordered_bench': [
            {'player': str(r.get('name', '')), 'element': _player_key(r),
             'points': round(float(r['predicted_points']), 2)}
            for _, r in result['bench'].iterrows()
        ],
        'bench_total': round(bench_total, 2),
        'expected_autosub_points': round(autosub, 2),
    })
    return out


def _evaluate_candidate_week(opt, gw: int, squad: pd.DataFrame, point_matrix: pd.DataFrame,
                             p_plays: pd.DataFrame, reduced_players: pd.DataFrame,
                             chip_budget: float, cost_overrides: dict, current_ft: int,
                             first_gw: int, last_gw: int, policy: ChipPlanPolicy,
                             candidate_windows: dict) -> tuple[int, dict, dict]:
    """Every chip's gain (and evidence) at one candidate gameweek.

    Runs inside a worker thread in `compute_chips`; takes only read-only
    inputs and returns plain data, so the caller can merge results back
    without any locking.
    """
    week_gains: dict[str, float] = {}
    week_evidence: dict[str, dict] = {}
    current_elements = {_player_key(r) for _, r in squad.iterrows()}

    current_result = _current_week_result(opt, squad, point_matrix, gw)
    if current_result is not None:
        for chip, (gain, chip_evidence) in _captain_and_bench(current_result, p_plays, gw).items():
            if gw in candidate_windows[chip][0]:
                week_gains[chip] = gain
                week_evidence[chip] = chip_evidence

    if gw in candidate_windows['free_hit'][0]:
        fh_total, fh_result = _free_hit_total(opt, reduced_players, point_matrix, gw, chip_budget, cost_overrides)
        ft_this_week = current_ft if gw == first_gw else 1
        baseline_total = _no_chip_total(
            opt, reduced_players, point_matrix, gw, squad.index, chip_budget, cost_overrides, ft_this_week)
        if fh_total is not None and baseline_total is not None:
            week_gains['free_hit'] = fh_total - baseline_total
            changed = 0
            if fh_result is not None:
                fh_elements = {_player_key(r) for _, r in fh_result['squad'].iterrows()}
                changed = len(current_elements - fh_elements)
            week_evidence['free_hit'] = {
                'chip': 'free_hit',
                'free_hit_total': round(fh_total, 2),
                'no_chip_total': round(baseline_total, 2),
                'no_chip_free_transfers': ft_this_week,
                'changed_player_count': changed,
                'xi': [] if fh_result is None else [
                    {'player': str(r.get('name', '')), 'element': _player_key(r)}
                    for _, r in fh_result['xi'].iterrows()
                ],
            }

    if gw in candidate_windows['wildcard'][0]:
        window_gws = [w for w in range(gw, gw + policy.wildcard_window) if w <= last_gw]
        wc_gain, wc_total, wc_result = _wildcard_totals(
            opt, reduced_players, point_matrix, window_gws, chip_budget, cost_overrides,
            squad.index, current_ft, policy)
        if wc_gain is not None:
            week_gains['wildcard'] = wc_gain
            changed = 0
            if wc_result is not None:
                wc_elements = {_player_key(r) for _, r in wc_result['squad'].iterrows()}
                changed = len(current_elements - wc_elements)
            week_evidence['wildcard'] = {
                'chip': 'wildcard',
                'window_gameweeks': window_gws,
                'truncated': len(window_gws) < policy.wildcard_window,
                'wildcard_total': round(wc_total, 2) if wc_total is not None else None,
                'changed_player_count': changed,
            }
            # The squad a Wildcard builds is the one Triple Captain and Bench
            # Boost would be played with in the weeks after it, so their gains
            # there are re-valued on it. That is what lets the planner find a
            # Wildcard-then-Bench-Boost pairing at all.
            after = {}
            if wc_result is not None:
                wc_squad = wc_result['squad']
                for later in window_gws[1:]:
                    if not any(later in candidate_windows[c][0] for c in ('triple_captain', 'bench_boost')):
                        continue
                    later_result = _current_week_result(opt, wc_squad, point_matrix, later)
                    if later_result is not None:
                        after[later] = _captain_and_bench(later_result, p_plays, later)
            week_evidence['wildcard']['_after'] = after

    return gw, week_gains, week_evidence


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------
def compute_chips(squad, season: str, first_gw: int, horizon: int,
                  players: pd.DataFrame, inventory: dict | None = None,
                  scheduled_gameweeks: list | None = None,
                  last_free_hit_gameweek: int | None = None,
                  future_points: pd.DataFrame | None = None,
                  future_p_plays: pd.DataFrame | None = None,
                  projection_generated_at: str | None = None,
                  bank: float | None = None,
                  selling_prices: dict | None = None,
                  root: str | None = None,
                  free_transfers: int | None = None) -> dict:
    opt = _optimise()
    players = players.copy()
    if not players.index.is_unique:
        players = players.reset_index(drop=True)
    if squad is not None:
        squad = _align_squad_to_players(players, squad)
    teams = pd.read_csv(os.path.join(opt.season_dir(season, root), 'teams.csv'))
    name_to_id = dict(zip(teams['name'], teams['id']))

    # The display/plan always runs from now through the end of the season --
    # "horizon" is accepted for API compatibility but no longer bends the
    # engine's answer (that was finding #2: a horizon dropdown that changed
    # the verdict). `requested_horizon`/`evaluated_horizon` below are for
    # display continuity only.
    last_gw = SECOND_HALF_LAST_GW
    gameweeks = list(range(first_gw, last_gw + 1))
    calendar = opt.fixture_calendar(season, first_gw, last_gw - first_gw + 1, root)
    counts = calendar.pivot_table(index='event', columns='team', values='fixtures', fill_value=0)
    counts = counts.reindex(index=gameweeks, columns=teams['id'].tolist(), fill_value=0).fillna(0)
    doubles = {gw: [int(team) for team in counts.loc[gw].index if counts.loc[gw, team] >= 2]
               for gw in gameweeks}
    blanks = {gw: [int(team) for team in counts.loc[gw].index if counts.loc[gw, team] == 0]
              for gw in gameweeks}
    any_dgw = any(doubles.values())
    any_bgw = any(blanks.values())

    has_squad = squad is not None and len(squad) == opt.SQUAD_SIZE
    squad_teams = squad['team'].map(name_to_id) if has_squad else None
    unmapped = (sorted(squad.loc[squad_teams.isna(), 'team'].unique())
                if has_squad and squad_teams.isna().any() else [])

    rows = []
    for gw in gameweeks:
        gw_counts = counts.loc[gw]
        gw_fixtures = calendar[calendar['event'] == gw]
        gw_diff = gw_fixtures.set_index('team')['difficulty']
        entry = {
            'gw': int(gw), 'matches': int(gw_counts.sum() // 2),
            'dgw_teams': len(doubles[gw]), 'blank_teams': len(blanks[gw]),
        }
        if squad_teams is not None:
            played = squad_teams.map(gw_counts).fillna(0)
            entry['squad_playing'] = int((played > 0).sum())
            entry['squad_blanks'] = int((played == 0).sum())
            squad_diffs = squad_teams.map(gw_diff).dropna()
            entry['avg_fdr'] = round(float(squad_diffs.mean()) if len(squad_diffs) else 3.0, 2)
        else:
            entry['avg_fdr'] = round(float(gw_diff.mean()) if len(gw_diff) else 3.0, 2)
        rows.append(entry)

    # A real prediction basis only exists once there's a squad to project and
    # at least one gameweek of exported model output to extrapolate from.
    has_projection_basis = future_points is not None and any(
        gw in future_points.columns for gw in gameweeks)
    mode = 'model_projection' if has_squad and has_projection_basis else 'fixture_signal'

    projection_gameweeks = [] if future_points is None else sorted(
        int(gw) for gw in future_points.columns if pd.notna(gw))
    policy = ChipPlanPolicy()

    supplied_inventory = inventory if isinstance(inventory, dict) else {}
    inventory_known = bool(inventory)
    normalized_inventory = {'first_half': {}, 'second_half': {}}
    for half in ('first_half', 'second_half'):
        source = supplied_inventory.get(half, {})
        for chip in CHIP_IDS:
            value = source.get(chip, 'unknown') if isinstance(source, dict) else 'unknown'
            if value is True:
                value = 'used'
            elif value is False:
                value = 'unused'
            normalized_inventory[half][chip] = value if value in {'unused', 'used', 'expired'} else 'unknown'

    scheduled = sorted({int(gw) for gw in (scheduled_gameweeks or [])})
    candidate_windows = {
        chip: _candidate_window(first_gw, last_gw, chip, normalized_inventory, scheduled,
                               last_free_hit_gameweek)
        for chip in CHIP_IDS
    }

    for row in rows:
        row['fixture_signal'] = _fixture_signal(row)

    if mode == 'fixture_signal':
        for row in rows:
            row['projection_state'] = 'complete' if row['matches'] > 0 else 'unknown'
        recommendations = []
        for chip in CHIP_IDS:
            candidates, halves = candidate_windows[chip]
            state = halves.get(_half_of(first_gw), {}).get('state', 'unknown')
            if not candidates and state in {'used', 'expired'}:
                status = 'unavailable'
            else:
                status = 'no_squad'
            recommendations.append({
                'chip': chip, 'label': CHIP_LABELS[chip], 'status': status,
                'gw': None, 'gain': None, 'discounted_gain': None,
                'close_call': False, 'use_or_lose': False,
                'candidate_gameweeks': candidates,
                'gains_by_week': {}, 'evidence': None,
                'reasons': ['A complete 15-player squad is needed for player-point '
                           'evidence; showing DGW/BGW fixture context only.'],
                'warnings': [] if inventory_known else [
                    'Chip inventory has not been entered; confirm this chip is still available.'],
                'inventory_windows': [dict(window) for window in halves.values()],
            })
        chip_plan = []
        primary_decision = None
    else:
        point_matrix, week_state = build_point_matrix(
            players, future_points, _player_fixture_frame(players, calendar, name_to_id, gameweeks),
            first_gw, last_gw)
        p_plays = _p_plays_matrix(players, future_p_plays, gameweeks)
        for row in rows:
            row['projection_state'] = week_state.get(row['gw'], 'no_fixtures')

        cost_overrides = {}
        for idx, player_row in squad.iterrows():
            key = _player_key(player_row)
            price = (
                float(selling_prices[key])
                if selling_prices is not None and key in selling_prices
                else float(player_row['value_m'])
            )
            cost_overrides[idx] = price
        total_selling_value = sum(cost_overrides.values())
        finance_available = bank is not None and selling_prices is not None
        chip_budget = float(bank) + total_selling_value if finance_available else float(squad['value_m'].sum())
        finance_warning = None if finance_available else (
            'Budget estimated from current market value, not real sale proceeds; '
            'import or price your squad to get an exact figure.')

        current_ft = free_transfers if free_transfers is not None else DEFAULT_FREE_TRANSFERS
        reduced_players = _reduced_market(players, point_matrix, squad.index)

        gains: dict[str, dict[int, float]] = {chip: {} for chip in CHIP_IDS}
        evidence: dict[str, dict[int, dict]] = {chip: {} for chip in CHIP_IDS}

        # Every candidate week across every chip, evaluated once each. Weeks
        # are independent (each is its own set of solver calls against the
        # same read-only inputs), and CBC runs as a subprocess that releases
        # the GIL while it waits -- so a thread pool gives a real speed-up
        # without touching the solver's own correctness.
        all_candidate_weeks = sorted({
            gw for chip in CHIP_IDS for gw in candidate_windows[chip][0]
        })
        worker_count = min(16, max(1, os.cpu_count() or 4), len(all_candidate_weeks) or 1)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            per_week = executor.map(
                lambda gw: _evaluate_candidate_week(
                    opt, gw, squad, point_matrix, p_plays, reduced_players, chip_budget,
                    cost_overrides, current_ft, first_gw, last_gw, policy, candidate_windows),
                all_candidate_weeks,
            )
            for gw, week_gains, week_evidence in per_week:
                for chip in CHIP_IDS:
                    if chip in week_gains:
                        gains[chip][gw] = week_gains[chip]
                        evidence[chip][gw] = week_evidence[chip]

        # {wildcard gw: {later gw: {chip: (gain, evidence)}}}, kept out of the response.
        after_wildcard = {gw: ev.pop('_after', {}) for gw, ev in evidence['wildcard'].items()}
        policy = dataclasses.replace(policy, extrapolated_weeks=frozenset(
            gw for gw, state in week_state.items() if state == 'extrapolated'))
        tokens = _plan_tokens(candidate_windows)
        awaiting = _awaiting_fixtures(tokens, doubles, blanks, policy)
        plan = _joint_plan(gains, [t for t in tokens if (t[0], t[1]) not in awaiting],
                           first_gw, policy, after_wildcard)
        for chip, half, weeks in tokens:
            if (chip, half) in awaiting:
                best = max(((w, g) for w in weeks if (g := gains[chip].get(w)) is not None),
                           key=lambda t: t[1], default=(None, None))
                plan[(chip, half)] = {
                    'gw': None, 'gain': None, 'after_wildcard': None, 'use_or_lose': False,
                    'runner_up_gw': None, 'runner_up_gain': None, 'best_unplaced': best,
                    'awaiting_fixtures': True}
        current_half = _half_of(first_gw)

        def token_view(chip: str, half: str) -> dict:
            entry = plan[(chip, half)]
            info = _token_status(entry, first_gw, policy)
            gw, gain, wc_gw = entry['gw'], entry['gain'], entry['after_wildcard']
            if gw is None:
                # Held: show the best week it was weighed against, so "hold" can be checked.
                best_gw = entry['best_unplaced'][0]
                chip_evidence = None if best_gw is None else evidence[chip].get(best_gw)
            elif wc_gw is not None:
                chip_evidence = {**after_wildcard[wc_gw][gw][chip][1], 'after_wildcard_gameweek': wc_gw}
            else:
                chip_evidence = evidence[chip].get(gw)
            return {**info, 'half': half, 'gw': gw,
                    'gain': None if gain is None else round(gain, 2),
                    'discounted_gain': None if gain is None else round(_discount(gain, gw, first_gw, policy), 2),
                    'after_wildcard_gameweek': wc_gw, 'evidence': chip_evidence,
                    'best_unplaced': entry['best_unplaced'],
                    'awaiting_fixtures': bool(entry.get('awaiting_fixtures'))}

        def reason_for(chip: str, view: dict) -> str:
            label, margin = CHIP_LABELS[chip], policy.min_gain[chip]
            half_end = FIRST_HALF_LAST_GW if view['half'] == 'first_half' else SECOND_HALF_LAST_GW
            if view['gw'] is None:
                best_gw, best_gain = view['best_unplaced']
                if best_gw is None:
                    return f'No eligible {label} week remains this half.'
                if view.get('awaiting_fixtures'):
                    return ('No double or blank gameweeks are scheduled from GW20 to '
                            f'GW{half_end} yet. {label} gains most in one, so hold it until FPL '
                            f"confirms them (on today's fixtures its best week is GW{best_gw}, "
                            f'+{best_gain:.1f}).')
                return (f'No week clears the {margin:.0f}-point margin yet (best is +{best_gain:.1f} in '
                        f'GW{best_gw}); hold it. It is planned automatically once GW{half_end} is close '
                        'enough that it would otherwise expire.')
            gain = view['gain']
            after = (f" with the squad your GW{view['after_wildcard_gameweek']} Wildcard builds"
                     if view['after_wildcard_gameweek'] is not None else '')
            if view['status'] == 'play_now':
                text = f'{label} is worth playing now: +{gain:.1f} points{after}'
                text += (f', above its {margin:.0f}-point margin.' if gain >= margin else
                         f". That is under its {margin:.0f}-point margin, but this half's chips expire "
                         f'after GW{half_end} and no better week is left.')
            else:
                text = f"Planned for GW{view['gw']}: +{gain:.1f} points{after}."
            # Say why a week with a bigger raw gain was passed over, or the
            # card reads "now 6.8 vs best 6.6" with no explanation.
            holders = {e['gw']: c for (c, h), e in plan.items()
                       if h == view['half'] and c != chip and e['gw'] is not None}
            half_gains = {w: g for w, g in gains[chip].items()
                          if _half_of(w) == view['half'] and w != view['gw'] and g is not None}
            planned_value = _discount(gain, view['gw'], first_gw, policy)
            better = [w for w, g in half_gains.items()
                      if _discount(g, w, first_gw, policy) > planned_value + 0.05]
            if better:
                taken_gw = max(better, key=lambda w: _discount(half_gains[w], w, first_gw, policy))
                if taken_gw in holders:
                    text += (f' GW{taken_gw} (+{half_gains[taken_gw]:.1f}) goes to '
                             f'{CHIP_LABELS[holders[taken_gw]]}: one chip per week, and the plan '
                             'scores more that way.')
            top_gw, top_gain = view['best_unplaced']
            if (top_gw is not None and top_gw > view['gw'] and top_gain > gain + 0.05
                    and top_gw not in better):
                text += f' GW{top_gw} is higher (+{top_gain:.1f}) but further out, so less certain.'
            if view['close_call']:
                text += ' Close call: another week is within a point of it.'
            if view['use_or_lose'] and view['status'] != 'play_now':
                text += f' Few weeks remain before GW{half_end}, so it is planned rather than held.'
            return text

        recommendations = []
        chip_plan = []
        for chip in CHIP_IDS:
            candidates, halves = candidate_windows[chip]
            state = halves.get(current_half, {}).get('state', 'unknown')
            chip_halves = [half for c, half, _w in tokens if c == chip]
            if not chip_halves:
                recommendations.append({
                    'chip': chip, 'label': CHIP_LABELS[chip], 'status': 'unavailable',
                    'gw': None, 'gain': None, 'discounted_gain': None,
                    'close_call': False, 'use_or_lose': False,
                    'candidate_gameweeks': [], 'gains_by_week': {}, 'evidence': None,
                    'reasons': [f'{CHIP_LABELS[chip]} is marked {state}.'], 'warnings': [],
                    'inventory_windows': [dict(window) for window in halves.values()],
                    'half': None, 'after_wildcard_gameweek': None, 'plan_by_half': [],
                })
                continue

            views = {half: token_view(chip, half) for half in chip_halves}
            # The card shows the copy that matters now: this half's if it is
            # still unused, otherwise the next half's.
            active = views.get(current_half) or views[chip_halves[0]]

            warnings = []
            if not inventory_known:
                warnings.append('Chip inventory has not been entered; confirm this chip is still available.')
            if chip in ('free_hit', 'wildcard') and finance_warning:
                warnings.append(finance_warning)
            reasons = [reason_for(chip, active)]
            for half, view in views.items():
                if view is active:
                    continue
                which = 'Second' if half == 'second_half' else 'First'
                if view['gw'] is not None:
                    reasons.append(f"{which}-half {CHIP_LABELS[chip]}: GW{view['gw']} (+{view['gain']:.1f}).")
                elif view['awaiting_fixtures']:
                    reasons.append(f"{which}-half {CHIP_LABELS[chip]}: held for the double "
                                   'gameweeks, which are not scheduled yet.')

            recommendations.append({
                'chip': chip, 'label': CHIP_LABELS[chip], 'status': active['status'],
                'gw': active['gw'], 'gain': active['gain'], 'discounted_gain': active['discounted_gain'],
                'close_call': active['close_call'], 'use_or_lose': active['use_or_lose'],
                'candidate_gameweeks': candidates,
                'gains_by_week': {int(gw): round(g, 2) for gw, g in gains[chip].items()},
                'evidence': active['evidence'],
                'reasons': reasons, 'warnings': warnings,
                'inventory_windows': [dict(window) for window in halves.values()],
                'half': active['half'], 'after_wildcard_gameweek': active['after_wildcard_gameweek'],
                'plan_by_half': [
                    {'half': half, 'gw': view['gw'], 'gain': view['gain'], 'status': view['status'],
                     'after_wildcard_gameweek': view['after_wildcard_gameweek']}
                    for half, view in views.items()],
            })
            for half, view in views.items():
                if view['gw'] is not None:
                    chip_plan.append({
                        'chip': chip, 'gw': view['gw'], 'half': half,
                        'gain': view['gain'], 'discounted_gain': view['discounted_gain'],
                        'status': view['status'],
                        'after_wildcard_gameweek': view['after_wildcard_gameweek'],
                    })
        chip_plan.sort(key=lambda entry: entry['gw'])

        play_now = [rec for rec in recommendations if rec['status'] == 'play_now']
        primary_decision = None
        if play_now:
            primary = max(play_now, key=lambda rec: rec['gain'])
            primary_decision = {
                'chip': primary['chip'], 'label': primary['label'], 'gw': primary['gw'],
                'gain': primary['gain'], 'reason': primary['reasons'][0],
            }

    evaluated_horizon = sum(gw in projection_gameweeks for gw in gameweeks)
    coverage_warning = None
    if mode != 'model_projection':
        coverage_warning = (
            'No player-based projection is available for this squad; player point '
            'gains are withheld and only fixture context is shown.'
        )

    return {
        'contract_version': CHIPS_CONTRACT_VERSION,
        'first_gw': first_gw, 'last_gw': last_gw,
        'current_gameweek': first_gw, 'any_dgw': any_dgw, 'any_bgw': any_bgw,
        'rows': rows,
        'week_states': {row['gw']: row['projection_state'] for row in rows},
        'recommendations': recommendations,
        'chip_plan': chip_plan,
        'unmapped_teams': unmapped, 'has_squad': has_squad,
        'projection_mode': mode,
        'projection_source': 'prediction export' if projection_gameweeks else 'unavailable',
        'projection_generated_at': projection_generated_at,
        'projection_gameweeks': projection_gameweeks,
        'projection_semantics': PROJECTION_SEMANTICS,
        'projection_note': (
            f'Weeks after GW{first_gw} use current form, price and availability, so they are '
            'scenario estimates rather than forecasts.'),
        'primary_decision': primary_decision,
        'requested_horizon': horizon,
        'evaluated_horizon': evaluated_horizon,
        'coverage_warning': coverage_warning,
        'data_quality': 'complete_horizon' if mode == 'model_projection' else 'fixture_signal_only',
        'methodology_version': CHIP_METHOD_VERSION,
        'decision_policy': policy.as_dict(),
        'inventory_source': 'local_user_reported' if inventory_known else 'unknown',
        'scheduled_gameweeks': scheduled,
        'free_transfers_used': free_transfers if free_transfers is not None else DEFAULT_FREE_TRANSFERS,
    }


def chip_advice(squad: pd.DataFrame | None, season: str, first_gw: int,
                horizon: int, players: pd.DataFrame) -> None:
    """CLI pretty-printer, kept for `python scripts/optimise.py chips`."""
    opt = _optimise()
    future_points = None
    future_p_plays = None
    try:
        horizon_players, horizon_matrix, horizon_p_plays, _gameweeks = opt.load_horizon(opt.PREDICTIONS)
        identity = 'element' if 'element' in players.columns and 'element' in horizon_players.columns else 'name'
        horizon_matrix.index = horizon_players[identity].to_list()
        horizon_p_plays.index = horizon_players[identity].to_list()
        future_points = horizon_matrix.reindex(players[identity].to_list())
        future_points.index = players.index
        future_p_plays = horizon_p_plays.reindex(players[identity].to_list())
        future_p_plays.index = players.index
    except SystemExit:
        pass

    generated_at = None
    if os.path.exists(opt.PREDICTIONS):
        import datetime
        generated_at = datetime.datetime.fromtimestamp(
            os.path.getmtime(opt.PREDICTIONS), tz=datetime.timezone.utc).isoformat()

    data = compute_chips(
        squad, season, first_gw, horizon, players,
        future_points=future_points, future_p_plays=future_p_plays,
        projection_generated_at=generated_at,
    )

    print(f"\n{'=' * 78}")
    print(f"CHIP PLAN   GW{data['first_gw']}-{data['last_gw']}")
    print("=" * 78)
    print('Projection mode: ' + data['projection_mode'])
    if data['coverage_warning']:
        print(data['coverage_warning'])
    print()
    if data['chip_plan']:
        for entry in data['chip_plan']:
            print(f"  {CHIP_LABELS[entry['chip']]} -> GW{entry['gw']} "
                 f"({entry['status']}, +{entry['gain']:.1f} pts)" if entry['gain'] is not None
                 else f"  {CHIP_LABELS[entry['chip']]} -> GW{entry['gw']} ({entry['status']})")
    else:
        print('  No chip plan available (no eligible chips or no squad).')
    print(f"\n{'-' * 78}")
    for rec in data['recommendations']:
        print(f"\n  {CHIP_LABELS[rec['chip']]}: {rec['status']}")
        print(f"    {rec['reasons'][0]}")
