from __future__ import annotations

from pathlib import Path

from src.historical.writer import _execute_sql_script


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def test_sql_semicolon_inside_line_comment_is_not_a_statement_boundary() -> None:
    cursor = RecordingCursor()

    _execute_sql_script(
        cursor,
        "-- something; with semicolon\n"
        "SELECT 'value; still a string';\n"
        "SELECT 2;",
    )

    assert cursor.statements == [
        "-- something; with semicolon\nSELECT 'value; still a string'",
        "SELECT 2",
    ]


def test_sql_semicolon_inside_block_comment_is_not_a_statement_boundary() -> None:
    cursor = RecordingCursor()

    _execute_sql_script(cursor, "SELECT 1 /* block; comment */; SELECT 2;")

    assert cursor.statements == [
        "SELECT 1 /* block; comment */",
        "SELECT 2",
    ]


def test_sql_quoted_identifiers_and_literals_remain_single_statements() -> None:
    cursor = RecordingCursor()

    _execute_sql_script(
        cursor,
        'SELECT "column;name", \'it\'\'s;quoted\';\n'
        "SELECT 2;",
    )

    assert len(cursor.statements) == 2
    assert cursor.statements[0] == 'SELECT "column;name", \'it\'\'s;quoted\''


def test_all_historical_migrations_split_into_expected_statements() -> None:
    expected_statement_counts = {
        "001_initial_historical.sql": 10,
        "002_fix_historical_constraints.sql": 8,
        "003_fix_observation_conflict_target.sql": 1,
        "004_harden_historical_schema.sql": 8,
    }

    for filename, expected_count in expected_statement_counts.items():
        cursor = RecordingCursor()
        _execute_sql_script(cursor, (MIGRATIONS_DIR / filename).read_text(encoding="utf-8"))
        assert len(cursor.statements) == expected_count, filename
        assert all(statement.strip() for statement in cursor.statements)


def test_historical_migrations_keep_required_schema_semantics() -> None:
    migration_001 = (MIGRATIONS_DIR / "001_initial_historical.sql").read_text(encoding="utf-8")
    migration_002 = (MIGRATIONS_DIR / "002_fix_historical_constraints.sql").read_text(encoding="utf-8")
    migration_003 = (MIGRATIONS_DIR / "003_fix_observation_conflict_target.sql").read_text(encoding="utf-8")
    migration_004 = (MIGRATIONS_DIR / "004_harden_historical_schema.sql").read_text(encoding="utf-8")

    assert "payload_hash TEXT NOT NULL UNIQUE" in migration_001
    assert "ais_timestamp_second SMALLINT NULL CHECK (ais_timestamp_second BETWEEN 0 AND 63)" in migration_001
    assert "SET ais_timestamp_second = NULL" in migration_002
    assert "CHECK (ais_timestamp_second BETWEEN 0 AND 59)" in migration_002
    assert "UNIQUE (session_id, payload_hash)" in migration_002
    assert "ON ais_observations (session_id, payload_hash)" in migration_003
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_ais_observations_session_payload_hash" in migration_004
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in migration_004

    # The known problematic comment must not contain a statement delimiter.
    assert "ordinary seconds; they are" not in migration_002
