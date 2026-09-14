from app.migrations import MIGRATION_FILE, split_statements


def test_oracle_migration_contains_schema_and_seed_statements():
    migration = MIGRATION_FILE.read_text(encoding="utf-8")
    statements = split_statements(migration)
    assert len(statements) == 17
    assert sum(statement.startswith("BEGIN") for statement in statements) == 13
    assert sum(statement.startswith("MERGE INTO locations") for statement in statements) == 3
    assert "voltage_volts NUMBER" in migration
    assert "sensor_ok NUMBER(1)" in migration
    assert "enabled NUMBER(1)" in migration
    assert "UPDATE power_slots SET enabled = 0 WHERE status = 'disabled'" in migration
    assert "power_bank_id VARCHAR2(64)" in migration
    assert "cancel_requested_at TIMESTAMP WITH TIME ZONE" in migration
    assert "cancel_reason VARCHAR2(500)" in migration
    assert "claim_request_id VARCHAR2(36)" in migration
    assert "CREATE UNIQUE INDEX idx_tasks_claim_request" in migration
    assert "SELECT 'A1' code, '右樓梯口' name, '3F' floor, 7.7 x, -7.2 y, 0 yaw" in migration
    assert "SELECT 'E1' code, '左樓梯口' name, '3F' floor, 7 x, 5.5 y, 0 yaw" in migration
    assert "SELECT 'F1' code, '電機工程學系' name, '3F' floor, -2.6 x, 4.7 y, 0 yaw" in migration
    assert "UPDATE locations SET enabled = 0 WHERE code = 'S1'" in migration


def test_sqlplus_slashes_are_not_sent_to_driver():
    statements = split_statements("SELECT 1 FROM dual;\n/\nSELECT 2 FROM dual;\n/")
    assert statements == ["SELECT 1 FROM dual", "SELECT 2 FROM dual"]
