import math
from typing import Any

BORROW_DISTANCE_WEIGHT = 0.7
BORROWABLE = {"full": 0, "ready": 1}


def select_power_bank(slots: list[dict[str, Any] | None], required_charge: float = 0):
    candidates = []
    for index, bank in enumerate(slots):
        if not bank or bank.get("status") not in BORROWABLE:
            continue
        charge = float(bank.get("charge", 101))
        if charge < required_charge:
            continue
        candidates.append((BORROWABLE[bank["status"]], charge, index, bank))
    return min(candidates, default=None, key=lambda item: item[:3])


def schedule_orders(
    orders: list[dict[str, Any]],
    current_position: dict[str, float],
    slots: list[dict[str, Any] | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending = [dict(order) for order in orders]
    inventory = [dict(slot) if slot else None for slot in slots]
    position = dict(current_position)
    route: list[dict[str, Any]] = []

    while pending:
        feasible = []
        for index, order in enumerate(pending):
            distance = math.hypot(order["x"] - position["x"], order["y"] - position["y"])
            if order["type"] == "borrow":
                bank = select_power_bank(inventory, order.get("required_charge", 0))
                if bank:
                    feasible.append((distance * BORROW_DISTANCE_WEIGHT, distance, index, bank))
            elif order["type"] == "return" and None in inventory:
                feasible.append((distance, distance, index, None))

        if not feasible:
            break

        _, distance, index, bank = min(feasible, key=lambda item: item[:3])
        order = pending.pop(index)
        scheduled = {**order, "distance": distance}
        if order["type"] == "borrow":
            _, _, slot_index, selected = bank
            inventory[slot_index] = None
            scheduled["selected_power_bank"] = dict(selected)
        else:
            slot_index = inventory.index(None)
            inventory[slot_index] = order.get("power_bank", {"status": "low"})
        route.append(scheduled)
        position = {"x": order["x"], "y": order["y"]}

    return route, pending
