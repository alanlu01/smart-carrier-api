import pytest
from pydantic import ValidationError

from app.repository import first_compatible_task_id, task_is_compatible
from app.schemas import TaskClaim, TaskClaimSlot


def three_slots(*statuses: tuple[str, int | None]) -> list[TaskClaimSlot]:
    return [
        TaskClaimSlot(
            slot=index,
            bank_id=None if status == "empty" else f"PB-{index:02d}",
            status=status,
            charge=charge,
        )
        for index, (status, charge) in enumerate(statuses, start=1)
    ]


def test_two_banks_and_one_empty_slot_support_borrow_and_return():
    slots = three_slots(("ready", 96), ("low", 45), ("empty", 0))

    assert task_is_compatible("borrow", 80, 1, slots)
    assert task_is_compatible("return", None, 1, slots)


def test_incompatible_inventory_does_not_block_navigation():
    slots = three_slots(("low", 45), ("low", 30), ("empty", 0))

    assert not task_is_compatible("borrow", 80, 1, slots)
    assert task_is_compatible("navigation", None, 1, slots)


def test_return_requires_an_empty_slot_and_borrow_respects_minimum_charge():
    full_slots = three_slots(("ready", 70), ("low", 40), ("full", 100))
    no_high_charge_slots = three_slots(("ready", 70), ("low", 40), ("ready", 80))

    assert not task_is_compatible("return", None, 1, full_slots)
    assert not task_is_compatible("borrow", 90, 1, no_high_charge_slots)
    assert task_is_compatible("borrow", 90, 1, full_slots)


def test_borrow_requires_the_selected_power_bank_when_one_is_requested():
    slots = three_slots(("full", 100), ("ready", 96), ("empty", 0))

    assert task_is_compatible("borrow", 80, 1, slots, "PB-02")
    assert not task_is_compatible("borrow", 80, 1, slots, "PB-03")


def test_claim_slot_normalizes_power_bank_id():
    slot = TaskClaimSlot(slot=2, bank_id=" pb-02 ", status="full", charge=100)

    assert slot.bank_id == "PB-02"


def test_oldest_incompatible_task_is_skipped_for_next_compatible_task():
    slots = three_slots(("low", 45), ("low", 30), ("empty", 0))
    candidates = [
        ("borrow-oldest", "borrow", "PB-01", 80, 1),
        ("navigation-next", "navigation", None, None, 1),
        ("return-later", "return", None, None, 1),
    ]

    assert first_compatible_task_id(candidates, slots) == "navigation-next"


def test_robot_currently_skips_quantities_greater_than_one():
    slots = three_slots(("full", 100), ("ready", 90), ("empty", 0))

    assert not task_is_compatible("borrow", 80, 2, slots)


def test_claim_snapshot_requires_each_of_the_three_slots_once():
    with pytest.raises(ValidationError, match="slot numbers 1, 2, and 3"):
        TaskClaim(
            slots=[
                {"slot": 1, "status": "ready", "charge": 90},
                {"slot": 1, "status": "low", "charge": 40},
                {"slot": 3, "status": "empty", "charge": 0},
            ]
        )
