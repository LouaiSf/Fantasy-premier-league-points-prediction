from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChipDecisionPolicy:
    """Maps evidence to an action label.

    The vocabulary is deliberately weaker than a "play now" verdict. A one-point
    margin is a product default, not a calibrated threshold, so the strongest
    label issued is `consider`. A `play` verdict needs a per-chip historical
    holdout to justify its threshold, and none exists yet.
    """
    minimum_projected_gain: float
    uncertainty_note: str

    def status(self, gain: float | None, *, current_gameweek: bool,
               inventory_known: bool, model_projection: bool,
               has_complete_squad: bool, gain_is_comparable: bool) -> str:
        if not has_complete_squad or not model_projection:
            return 'watch'
        # Only a gain measured against the right no-chip alternative can be
        # compared with the margin; raw evidence never becomes an action label.
        if not gain_is_comparable or gain is None:
            return 'watch'
        if not current_gameweek or not inventory_known:
            return 'watch'
        if gain < self.minimum_projected_gain:
            return 'hold'
        return 'consider'

    def as_dict(self) -> dict:
        return {
            'minimum_projected_gain': self.minimum_projected_gain,
            'uncertainty_note': self.uncertainty_note,
            'basis': 'DECISION_MARGIN: a conservative product policy, not a learned metric',
            'strongest_status': 'consider',
            'calibration_version': None,
        }
