from app.migrations import MIGRATION_FILE, split_statements


def test_oracle_migration_contains_schema_and_seed_statements():
    migration = MIGRATION_FILE.read_text(encoding="utf-8")
    statements = split_statements(migration)
    assert len(statements) == 20
    assert sum(statement.startswith("BEGIN") for statement in statements) == 13
    assert sum(statement.startswith("MERGE INTO locations") for statement in statements) == 6
    assert "voltage_volts NUMBER" in migration
    assert "sensor_ok NUMBER(1)" in migration
    assert "enabled NUMBER(1)" in migration
    assert "UPDATE power_slots SET enabled = 0 WHERE status = 'disabled'" in migration
    assert "power_bank_id VARCHAR2(64)" in migration
    assert "cancel_requested_at TIMESTAMP WITH TIME ZONE" in migration
    assert "cancel_reason VARCHAR2(500)" in migration
    assert "claim_request_id VARCHAR2(36)" in migration
    assert "CREATE UNIQUE INDEX idx_tasks_claim_request" in migration
    assert "SELECT 'A1' code, '右樓梯口' name, '3F' floor, 7.8 x, -6.6 y, 0 yaw" in migration
    assert "SELECT 'E1' code, '左樓梯口' name, '3F' floor, 7.2 x, 5.7 y, 0 yaw" in migration
    assert "SELECT 'F1' code, '電機工程學系' name, '3F' floor, -3 x, 5 y, 0 yaw" in migration
    assert "SELECT 'C1' code, 'CYCU EE' name, '3F' floor, 2.0 x, 5.18 y, 0 yaw" in migration
    assert "SELECT 'L1' code, '座位燈' name, '3F' floor, 1.4 x, -5.3 y, 0 yaw" in migration
    assert "SELECT 'B1' code, '座位' name, '3F' floor, 6.6 x, -0.3 y, 0 yaw" in migration
    assert "UPDATE locations SET enabled = 0 WHERE code = 'S1'" in migration


def test_sqlplus_slashes_are_not_sent_to_driver():
    statements = split_statements("SELECT 1 FROM dual;\n/\nSELECT 2 FROM dual;\n/")
    assert statements == ["SELECT 1 FROM dual", "SELECT 2 FROM dual"]
