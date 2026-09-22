from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChipDecisionPolicy:
    minimum_projected_gain: float
    uncertainty_note: str

    def status(self, gain: float | None, *, current_gameweek: bool,
               inventory_synced: bool, model_projection: bool,
               has_complete_squad: bool) -> str:
        if not has_complete_squad or not model_projection:
            return 'watch'
        if not current_gameweek:
            return 'watch'
        if not inventory_synced:
            return 'watch'
        if gain is None or gain < self.minimum_projected_gain:
            return 'hold'
        return 'play'

    def as_dict(self) -> dict:
        return {
            'minimum_projected_gain': self.minimum_projected_gain,
            'uncertainty_note': self.uncertainty_note,
            'basis': 'DECISION_MARGIN: a conservative product policy, not a learned metric',
        }
