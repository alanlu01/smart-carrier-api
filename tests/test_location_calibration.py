from app import location_calibration, repository


def test_location_calibration_defaults_to_dry_run(monkeypatch, capsys):
    current = {
        "code": "A1",
        "name": "A1",
        "description": None,
        "floor": "1F",
        "x": 0.0,
        "y": 0.0,
        "yaw": 0.0,
    }
    monkeypatch.setattr(repository, "get_location", lambda _code: current)
    apply_calls = []
    monkeypatch.setattr(
        repository,
        "update_location_coordinates",
        lambda *args: apply_calls.append(args),
    )

    assert (
        location_calibration.main(
            ["a1", "1.2", "2.3", "0.5", "--name", "門口"]
        )
        == 0
    )
    assert not apply_calls
    output = capsys.readouterr().out
    assert '"name": "門口"' in output
    assert "Dry run only" in output


def test_location_calibration_applies_explicitly(monkeypatch, capsys):
    current = {"code": "A1", "x": 0.0, "y": 0.0, "yaw": 0.0}
    updated = {"code": "A1", "x": 1.2, "y": 2.3, "yaw": 0.5}
    monkeypatch.setattr(repository, "get_location", lambda _code: current)
    apply_calls = []

    def apply_update(*args, **kwargs):
        apply_calls.append((args, kwargs))
        return updated

    monkeypatch.setattr(repository, "update_location_coordinates", apply_update)

    assert (
        location_calibration.main(
            ["A1", "1.2", "2.3", "0.5", "--name", "門口", "--apply"]
        )
        == 0
    )
    assert apply_calls == [(("A1", 1.2, 2.3, 0.5), {"name": "門口"})]
    assert '"updated"' in capsys.readouterr().out
