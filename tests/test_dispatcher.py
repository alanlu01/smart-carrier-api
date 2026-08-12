from app.services.dispatcher import schedule_orders, select_power_bank


def test_selects_full_bank_before_ready_bank():
    slots = [
        {"id": "PB-01", "status": "ready", "charge": 90},
        {"id": "PB-02", "status": "full", "charge": 100},
        None,
    ]
    selected = select_power_bank(slots, required_charge=80)
    assert selected is not None
    assert selected[3]["id"] == "PB-02"


def test_borrow_distance_gets_point_seven_weight():
    orders = [
        {"id": "return", "type": "return", "x": 5.0, "y": 0.0},
        {"id": "borrow", "type": "borrow", "x": 6.0, "y": 0.0},
    ]
    slots = [{"id": "PB-01", "status": "full", "charge": 100}, None, None]
    route, deferred = schedule_orders(orders, {"x": 0.0, "y": 0.0}, slots)
    assert not deferred
    assert route[0]["id"] == "borrow"
