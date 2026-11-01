"""Ordered schema migrations."""

import sqlite3

from .schema import INITIAL_SCHEMA_SQL

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, str] = {
    1: INITIAL_SCHEMA_SQL,
}


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations and return the resulting schema version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current} is newer than supported "
            f"version {SCHEMA_VERSION}"
        )

    for version in range(current + 1, SCHEMA_VERSION + 1):
        sql = MIGRATIONS.get(version)
        if sql is None:
            raise RuntimeError(f"Missing migration for schema version {version}")
        _apply(conn, version, sql)

    return conn.execute("PRAGMA user_version").fetchone()[0]


def _apply(conn: sqlite3.Connection, version: int, sql: str) -> None:
    script = f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;"
    try:
        conn.executescript(script)
    except Exception:
        conn.rollback()
        raise
