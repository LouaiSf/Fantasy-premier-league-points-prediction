from __future__ import annotations

from dataclasses import dataclass, field


# Product policy constants for the chip plan (contract v4). Every chip now
# has a real gain (points vs the best no-chip alternative that same week), so
# these thresholds compare like with like across chips -- unlike the old
# single DECISION_MARGIN, which only ever applied to Triple Captain.
MIN_GAIN: dict[str, float] = {
    'triple_captain': 4.0,
    'bench_boost': 5.0,
    'free_hit': 6.0,
    'wildcard': 8.0,
}
CLOSE_CALL_MARGIN = 1.0
# Discount applied per gameweek of distance when comparing a future week's
# gain with playing now: a projection two gameweeks out is worth less than
# one for next week, because rotation, injuries and price changes erode it.
FUTURE_RELIABILITY = 0.95
WILDCARD_WINDOW = 6
# A half's chips expire at its last gameweek. Once a half has no more than
# this many spare weeks beyond one per unused chip, holding out for a week
# that clears MIN_GAIN risks losing the chip, so any positive week is allowed.
USE_OR_LOSE_BUFFER = 1
# The planner brute-forces every chip's week within a half; each chip keeps
# only its best few weeks by discounted gain, which never drops the optimum
# for four chips (a chip can be displaced from at most three weeks by the
# other three) as long as this is at least 4.
PLAN_TOP_WEEKS = 8


@dataclass(frozen=True)
class ChipPlanPolicy:
    """Maps a chip's computed per-week gains to a plan-wide status.

    Every number here is a conservative product default, not a calibrated
    threshold -- there is no per-chip historical holdout to justify a
    tighter one yet.
    """
    min_gain: dict[str, float] = field(default_factory=lambda: dict(MIN_GAIN))
    close_call_margin: float = CLOSE_CALL_MARGIN
    future_reliability: float = FUTURE_RELIABILITY
    wildcard_window: int = WILDCARD_WINDOW
    use_or_lose_buffer: int = USE_OR_LOSE_BUFFER
    plan_top_weeks: int = PLAN_TOP_WEEKS
    uncertainty_note: str = (
        'Player point projections have model error; the discount and gain '
        'thresholds are conservative product policy, not a learned metric.'
    )

    def as_dict(self) -> dict:
        return {
            'min_gain': dict(self.min_gain),
            'close_call_margin': self.close_call_margin,
            'future_reliability': self.future_reliability,
            'wildcard_window': self.wildcard_window,
            'use_or_lose_buffer': self.use_or_lose_buffer,
            'uncertainty_note': self.uncertainty_note,
            'basis': 'CHIP_PLAN_POLICY: a conservative product policy, not a learned metric',
            'calibration_version': None,
        }
