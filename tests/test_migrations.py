from app.migrations import MIGRATION_FILE, split_statements


def test_oracle_migration_contains_schema_and_seed_statements():
    migration = MIGRATION_FILE.read_text(encoding="utf-8")
    statements = split_statements(migration)
    assert len(statements) == 14
    assert sum(statement.startswith("BEGIN") for statement in statements) == 10
    assert sum(statement.startswith("MERGE INTO locations") for statement in statements) == 4
    assert "voltage_volts NUMBER" in migration
    assert "sensor_ok NUMBER(1)" in migration
    assert "power_bank_id VARCHAR2(64)" in migration
    assert "SELECT 'A1' code, '門口' name, '1F' floor, -0.45 x, -0.35 y, 0 yaw" in migration
    assert "SELECT 'E1' code, '廚房' name, '1F' floor, -1.5 x, 5 y, 0 yaw" in migration
    assert "SELECT 'F1' code, '廁所' name, '1F' floor, -4 x, 1.5 y, 3.14 yaw" in migration
    assert "SELECT 'S1' code, '客廳TV' name, '1F' floor, 0.4 x, 0 y, 0 yaw" in migration


def test_sqlplus_slashes_are_not_sent_to_driver():
    statements = split_statements("SELECT 1 FROM dual;\n/\nSELECT 2 FROM dual;\n/")
    assert statements == ["SELECT 1 FROM dual", "SELECT 2 FROM dual"]
