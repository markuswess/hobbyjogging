"""Ordered schema migrations."""

import sqlite3

from .schema import INITIAL_SCHEMA_SQL

SCHEMA_VERSION = 10

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

MIGRATION_6_SQL = """
ALTER TABLE activities ADD COLUMN moving_s REAL;
ALTER TABLE events ADD COLUMN training_load REAL;

-- Backfill moving time for activities imported from Intervals. FIT moving
-- time comes from total_moving_time on the next FIT import.
UPDATE activities
SET moving_s = (
    SELECT json_extract(sr.payload_json, '$.moving_time')
    FROM activity_sources als
    JOIN source_records sr ON sr.id = als.source_record_id
    WHERE als.activity_id = activities.id
      AND sr.source = 'intervals'
      AND sr.record_type = 'activity'
      AND sr.payload_json IS NOT NULL
    LIMIT 1
)
WHERE moving_s IS NULL;

-- Events only expose moving_time; older rows stored NULL because the
-- importer read the nonexistent `duration` field.
UPDATE events
SET duration_s = COALESCE(
        duration_s,
        (
            SELECT json_extract(sr.payload_json, '$.moving_time')
            FROM source_records sr
            WHERE sr.id = events.source_record_id
        )
    ),
    training_load = COALESCE(
        training_load,
        (
            SELECT json_extract(sr.payload_json, '$.icu_training_load')
            FROM source_records sr
            WHERE sr.id = events.source_record_id
        )
    );
"""

MIGRATION_7_SQL = """
ALTER TABLE events ADD COLUMN excluded_at TEXT;
CREATE INDEX idx_events_excluded ON events(excluded_at);
"""

MIGRATION_8_SQL = """
ALTER TABLE events ADD COLUMN zone_kind TEXT NOT NULL DEFAULT '';

CREATE TABLE event_zone_times (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    zone_index INTEGER,
    zone_label TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, zone_label)
);

CREATE INDEX idx_event_zone_times_event ON event_zone_times(event_id);
"""

MIGRATION_9_SQL = """
CREATE TABLE activity_workout_methods (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, method)
);

CREATE TABLE activity_workout_targets (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, target)
);

CREATE TABLE event_workout_methods (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, method)
);

CREATE TABLE event_workout_targets (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, target)
);

CREATE INDEX idx_activity_workout_methods_method
ON activity_workout_methods(method);
CREATE INDEX idx_activity_workout_targets_target
ON activity_workout_targets(target);
CREATE INDEX idx_event_workout_methods_method
ON event_workout_methods(method);
CREATE INDEX idx_event_workout_targets_target
ON event_workout_targets(target);
"""

MIGRATION_10_SQL = """
-- Bookkeeping for hobbyjogging-maintenance. ``data_migrations`` records
-- one-time backfills that have been applied; ``maintenance_runs`` logs every
-- run (including dry runs and repeatable recomputes).
CREATE TABLE data_migrations (
    id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE maintenance_runs (
    id INTEGER PRIMARY KEY,
    task TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('backfill', 'recompute')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    dry_run INTEGER NOT NULL DEFAULT 0 CHECK (dry_run IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'ok', 'failed')),
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_maintenance_runs_task
ON maintenance_runs(task, started_at);
"""

MIGRATIONS: dict[int, str] = {
    1: INITIAL_SCHEMA_SQL,
    2: MIGRATION_2_SQL,
    3: MIGRATION_3_SQL,
    4: MIGRATION_4_SQL,
    5: MIGRATION_5_SQL,
    6: MIGRATION_6_SQL,
    7: MIGRATION_7_SQL,
    8: MIGRATION_8_SQL,
    9: MIGRATION_9_SQL,
    10: MIGRATION_10_SQL,
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
