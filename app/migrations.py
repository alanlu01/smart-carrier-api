import re
from pathlib import Path

from app.database import get_connection

MIGRATION_FILE = Path(__file__).resolve().parent.parent / "migrations" / "001_oracle_schema.sql"


def split_statements(sql: str) -> list[str]:
    statements = []
    for block in re.split(r"(?m)^\s*/\s*$", sql):
        lines = [line for line in block.splitlines() if not line.lstrip().startswith("--")]
        statement = "\n".join(lines).strip()
        if not statement:
            continue
        if not statement.upper().startswith(("BEGIN", "DECLARE")):
            statement = statement.removesuffix(";").rstrip()
        statements.append(statement)
    return statements


def migrate() -> None:
    statements = split_statements(MIGRATION_FILE.read_text(encoding="utf-8"))
    with get_connection() as connection, connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    print(f"Applied {len(statements)} Oracle schema statements.")


if __name__ == "__main__":
    migrate()
