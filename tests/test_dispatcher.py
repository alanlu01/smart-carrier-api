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


def test_selects_requested_bank_instead_of_substituting():
    slots = [
        {"id": "PB-01", "status": "full", "charge": 100},
        {"id": "PB-02", "status": "ready", "charge": 96},
        None,
    ]

    selected = select_power_bank(slots, required_charge=80, power_bank_id="PB-02")

    assert selected is not None
    assert selected[3]["id"] == "PB-02"
    assert select_power_bank(slots, required_charge=80, power_bank_id="PB-03") is None


def test_select_power_bank_accepts_null_charge_without_crashing():
    slots = [
        {"id": "PB-01", "status": "ready", "charge": None},
        {"id": "PB-02", "status": "full", "charge": None},
    ]

    selected = select_power_bank(slots, required_charge=80)

    assert selected is not None
    assert selected[3]["id"] == "PB-02"


def test_unknown_charge_ready_slot_cannot_satisfy_charge_requirement():
    slots = [{"id": "PB-01", "status": "ready", "charge": None}]

    assert select_power_bank(slots, required_charge=80) is None


def test_borrow_distance_gets_point_seven_weight():
    orders = [
        {"id": "return", "type": "return", "x": 5.0, "y": 0.0},
        {"id": "borrow", "type": "borrow", "x": 6.0, "y": 0.0},
    ]
    slots = [{"id": "PB-01", "status": "full", "charge": 100}, None, None]
    route, deferred = schedule_orders(orders, {"x": 0.0, "y": 0.0}, slots)
    assert not deferred
    assert route[0]["id"] == "borrow"
