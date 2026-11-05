"""Ordered schema migrations."""

import sqlite3

from .schema import INITIAL_SCHEMA_SQL

SCHEMA_VERSION = 5

MIGRATION_2_SQL = """
ALTER TABLE activities ADD COLUMN elapsed_s REAL NOT NULL DEFAULT 0;
"""

MIGRATION_3_SQL = """
CREATE TABLE review_items (
    id INTEGER PRIMARY KEY,
    activity_id TEXT REFERENCES activities(id) ON DELETE CASCADE,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE CASCADE,
    import_run_id INTEGER REFERENCES import_runs(id) ON DELETE SET NULL,
    category TEXT NOT NULL,
    detail TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'ignored', 'resolved')),
    severity TEXT NOT NULL DEFAULT 'warn'
        CHECK (severity IN ('info', 'warn', 'error')),
    reported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    resolved_note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_review_items_scope
ON review_items(category, fingerprint);
CREATE INDEX idx_review_items_status ON review_items(status);
CREATE INDEX idx_review_items_activity ON review_items(activity_id);
"""

MIGRATION_4_SQL = """
ALTER TABLE activities ADD COLUMN excluded_at TEXT;
ALTER TABLE source_records ADD COLUMN excluded_at TEXT;
"""

MIGRATION_5_SQL = """
ALTER TABLE activities ADD COLUMN vo2max_garmin REAL;
ALTER TABLE activities ADD COLUMN vo2max_runalyze REAL;

CREATE TABLE activity_tags (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, tag, source)
);

CREATE INDEX idx_activity_tags_tag ON activity_tags(tag);
"""

MIGRATIONS: dict[int, str] = {
    1: INITIAL_SCHEMA_SQL,
    2: MIGRATION_2_SQL,
    3: MIGRATION_3_SQL,
    4: MIGRATION_4_SQL,
    5: MIGRATION_5_SQL,
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
