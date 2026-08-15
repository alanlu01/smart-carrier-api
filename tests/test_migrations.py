from app.migrations import MIGRATION_FILE, split_statements


def test_oracle_migration_contains_schema_and_seed_statements():
    statements = split_statements(MIGRATION_FILE.read_text(encoding="utf-8"))
    assert len(statements) == 11
    assert sum(statement.startswith("BEGIN") for statement in statements) == 7
    assert sum(statement.startswith("MERGE INTO locations") for statement in statements) == 4


def test_sqlplus_slashes_are_not_sent_to_driver():
    statements = split_statements("SELECT 1 FROM dual;\n/\nSELECT 2 FROM dual;\n/")
    assert statements == ["SELECT 1 FROM dual", "SELECT 2 FROM dual"]
