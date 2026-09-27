from __future__ import annotations

from webapp.fpl_client import ChipPlayed, HistoryEntry
from webapp.manager_status import derive_chip_inventory, derive_free_transfers


def entry(event: int, transfers: int = 0, cost: int = 0) -> HistoryEntry:
    return HistoryEntry(
        event=event, event_transfers=transfers, event_transfers_cost=cost,
        bank=0.0, value=1000.0,
    )


# ---------------------------------------------------------------------------
# derive_chip_inventory
# ---------------------------------------------------------------------------
def test_chip_inventory_all_unused_in_first_half() -> None:
    result = derive_chip_inventory([], current_gw=6)
    assert result["chip_inventory"]["first_half"] == {
        "triple_captain": "unused", "bench_boost": "unused",
        "free_hit": "unused", "wildcard": "unused",
    }
    assert result["chip_inventory"]["second_half"]["wildcard"] == "unused"
    assert result["last_free_hit_gameweek"] is None


def test_chip_inventory_marks_played_chip_used_and_tracks_last_free_hit() -> None:
    chips = [ChipPlayed(name="wildcard", event=7), ChipPlayed(name="freehit", event=12)]
    result = derive_chip_inventory(chips, current_gw=14)
    assert result["chip_inventory"]["first_half"]["wildcard"] == "used"
    assert result["chip_inventory"]["first_half"]["free_hit"] == "used"
    assert result["chip_inventory"]["first_half"]["bench_boost"] == "unused"
    assert result["last_free_hit_gameweek"] == 12


def test_chip_inventory_expires_unused_first_half_chips_after_gw19() -> None:
    chips = [ChipPlayed(name="3xc", event=5)]
    result = derive_chip_inventory(chips, current_gw=25)
    inventory = result["chip_inventory"]
    assert inventory["first_half"]["triple_captain"] == "used"
    assert inventory["first_half"]["bench_boost"] == "expired"
    assert inventory["first_half"]["free_hit"] == "expired"
    assert inventory["first_half"]["wildcard"] == "expired"
    # The second half hasn't started/finished, so it stays unused.
    assert inventory["second_half"]["bench_boost"] == "unused"


def test_chip_inventory_second_half_chip_used() -> None:
    chips = [ChipPlayed(name="bboost", event=24)]
    result = derive_chip_inventory(chips, current_gw=25)
    assert result["chip_inventory"]["second_half"]["bench_boost"] == "used"
    assert result["chip_inventory"]["first_half"]["bench_boost"] == "expired"


# ---------------------------------------------------------------------------
# derive_free_transfers
# ---------------------------------------------------------------------------
def test_free_transfers_bank_up_with_no_transfers_made() -> None:
    current = [entry(2, transfers=0, cost=0)]
    assert derive_free_transfers(current, chips=[], next_gw=3) == 2


def test_free_transfers_steady_state_when_one_transfer_used_each_week() -> None:
    current = [entry(2, transfers=1, cost=0), entry(3, transfers=1, cost=0)]
    assert derive_free_transfers(current, chips=[], next_gw=4) == 1


def test_free_transfers_paid_transfer_still_resets_to_one() -> None:
    current = [entry(2, transfers=2, cost=4)]
    assert derive_free_transfers(current, chips=[], next_gw=3) == 1


def test_free_transfers_chip_week_preserves_balance_and_banks_next() -> None:
    current = [entry(2, transfers=10, cost=0)]
    chips = [ChipPlayed(name="wildcard", event=2)]
    assert derive_free_transfers(current, chips, next_gw=3) == 2


def test_free_transfers_caps_at_five() -> None:
    current = [entry(gw) for gw in range(2, 10)]
    assert derive_free_transfers(current, chips=[], next_gw=10) == 5


def test_free_transfers_entering_gw2_is_one() -> None:
    assert derive_free_transfers([], chips=[], next_gw=2) == 1
