"""Chip inventory and free-transfer accounting derived from FPL's public history.

Pure functions only: no network access and no Flask. `manager_routes.py` calls
these from the `/api/managers/<id>/status` route; tests call them directly
against hand-built histories.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

# Mirrors scripts.optimise.CHIP_IDS / FIRST_HALF_LAST_GW. Duplicated rather
# than imported so this module stays a light, pandas-free import for the
# manager-lookup routes.
CHIP_IDS: tuple[str, ...] = ('triple_captain', 'bench_boost', 'free_hit', 'wildcard')
FIRST_HALF_LAST_GW = 19
MAX_FREE_TRANSFERS = 5

# FPL's history endpoint names chips differently from the rest of this app.
FPL_CHIP_NAME_TO_ID: dict[str, str] = {
    'wildcard': 'wildcard',
    'freehit': 'free_hit',
    'bboost': 'bench_boost',
    '3xc': 'triple_captain',
}
# Chips that let a gameweek's transfers bypass the free-transfer count.
UNLIMITED_TRANSFER_CHIP_IDS = frozenset({'wildcard', 'free_hit'})


class _ChipLike(Protocol):
    name: str
    event: int


class _HistoryEntryLike(Protocol):
    event: int
    event_transfers: int
    event_transfers_cost: int


def derive_chip_inventory(chips: Sequence[_ChipLike], current_gw: int) -> dict:
    """Chip usage split by half-season, plus the last Free Hit gameweek.

    Each played chip is marked `used` in the half its event falls in (GW1-19
    is the first half, GW20-38 the second). An unplayed chip in a half that
    has already finished is `expired`; everything else unplayed is `unused`.
    """
    inventory = {
        'first_half': {chip_id: 'unused' for chip_id in CHIP_IDS},
        'second_half': {chip_id: 'unused' for chip_id in CHIP_IDS},
    }
    last_free_hit_gameweek: int | None = None
    for chip in chips:
        chip_id = FPL_CHIP_NAME_TO_ID.get(chip.name)
        if chip_id is None:
            continue
        half = 'first_half' if chip.event <= FIRST_HALF_LAST_GW else 'second_half'
        inventory[half][chip_id] = 'used'
        if chip_id == 'free_hit' and (
            last_free_hit_gameweek is None or chip.event > last_free_hit_gameweek
        ):
            last_free_hit_gameweek = chip.event

    if current_gw > FIRST_HALF_LAST_GW:
        for chip_id in CHIP_IDS:
            if inventory['first_half'][chip_id] == 'unused':
                inventory['first_half'][chip_id] = 'expired'

    return {'chip_inventory': inventory, 'last_free_hit_gameweek': last_free_hit_gameweek}


def derive_free_transfers(
    current: Sequence[_HistoryEntryLike], chips: Sequence[_ChipLike], next_gw: int,
) -> int:
    """Free transfers available entering `next_gw`, replayed from history.

    2026/27 rules: GW1 is unlimited and never banks a free transfer. From GW2
    a manager gains +1 free transfer per gameweek, capped at 5. A gameweek's
    `event_transfers_cost` is 4 points per paid transfer, so the free
    transfers it spent are `event_transfers - event_transfers_cost / 4`. In a
    Wildcard or Free Hit gameweek transfers cost nothing and spend no free
    transfers, and the saved balance carries forward untouched.
    """
    chip_events = {
        chip.event for chip in chips
        if FPL_CHIP_NAME_TO_ID.get(chip.name) in UNLIMITED_TRANSFER_CHIP_IDS
    }
    by_event = {entry.event: entry for entry in current}

    free_transfers = 1  # the balance entering GW2, once GW1's unlimited window closes
    for event in range(2, next_gw):
        entry = by_event.get(event)
        if entry is not None and event not in chip_events:
            paid = entry.event_transfers_cost // 4
            free_used = entry.event_transfers - paid
            free_transfers = max(0, free_transfers - free_used)
        free_transfers = min(MAX_FREE_TRANSFERS, free_transfers + 1)
    return free_transfers
