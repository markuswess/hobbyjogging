"""Ordered schema migrations."""

from __future__ import annotations

import sqlite3

from .schema import INITIAL_SCHEMA_SQL

SCHEMA_VERSION = 25

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

MIGRATION_11_SQL = """
-- Scan manifest for the FIT archive. Every file the importer has classified
-- gets a row, whether or not it became an activity, so a routine scan only
-- reads new or changed files. ``kind`` is the scan's verdict (``activity``,
-- ``other``, ``error``); the importer owns the values.
CREATE TABLE fit_scan_files (
    path TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fit_scan_files_seen ON fit_scan_files(seen_at);
"""


MIGRATION_12_SQL = """
-- Per-activity elevation and maximum heart rate. Elevation is owner-based
-- with a wide tolerance (the sources are estimates); max HR is owner-based
-- with a 2 bpm tolerance (a bigger gap means a different sensor or effort).
ALTER TABLE activities ADD COLUMN elevation_gain_m REAL;
ALTER TABLE activities ADD COLUMN elevation_loss_m REAL;
ALTER TABLE activities ADD COLUMN max_hr REAL;
"""


MIGRATION_13_SQL = """
-- Per-activity weather. One row per activity: the first source to record it
-- owns the row, a later source only fills the fields it left empty. Values
-- are metric: temperature in °C, wind in m/s, pressure in hPa.
CREATE TABLE activity_weather (
    activity_id TEXT PRIMARY KEY
        REFERENCES activities(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT '',
    source_record_id INTEGER
        REFERENCES source_records(id) ON DELETE SET NULL,
    temp_c REAL,
    feels_like_c REAL,
    humidity_pct REAL,
    wind_speed_ms REAL,
    wind_degree REAL,
    wind_gust_ms REAL,
    wind_chill_c REAL,
    heat_index_c REAL,
    pressure_hpa REAL,
    uv_index REAL,
    clouds_pct REAL,
    condition TEXT,
    is_night INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


MIGRATION_14_SQL = """
-- Dated athlete-threshold snapshots. Intervals stamps the athlete's settings
-- on every activity, so this is the deduplicated series of those settings;
-- Runalyze has no such history. A missing value carries forward.
CREATE TABLE athlete_thresholds (
    id INTEGER PRIMARY KEY,
    effective_from TEXT NOT NULL,
    max_hr REAL,
    lthr REAL,
    threshold_pace_mps REAL,
    source TEXT NOT NULL DEFAULT 'intervals',
    source_record_id INTEGER
        REFERENCES source_records(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, effective_from)
);
"""


MIGRATION_15_SQL = """
-- Thresholds are per sport: Intervals stamps the settings of the activity's
-- own sport, so the running series and the cycling one are different. The
-- v14 table was created empty in the same change, so it is recreated with the
-- sport column and the wider unique key.
DROP TABLE athlete_thresholds;
CREATE TABLE athlete_thresholds (
    id INTEGER PRIMARY KEY,
    effective_from TEXT NOT NULL,
    sport TEXT NOT NULL DEFAULT '',
    max_hr REAL,
    lthr REAL,
    threshold_pace_mps REAL,
    source TEXT NOT NULL DEFAULT 'intervals',
    source_record_id INTEGER
        REFERENCES source_records(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, sport, effective_from)
);
"""


MIGRATION_16_SQL = """
-- Official race results, separate from the measured GPS values. One row per
-- activity; the official distance and time are nullable so a partial result
-- can be entered and completed later. A PB counts only completed results.
CREATE TABLE race_results (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL UNIQUE
        REFERENCES activities(id) ON DELETE CASCADE,
    event_id TEXT REFERENCES events(id) ON DELETE SET NULL,
    name TEXT NOT NULL DEFAULT '',
    official_distance_m REAL,
    official_time_s REAL,
    officially_measured INTEGER,
    place_total INTEGER,
    place_gender INTEGER,
    place_ageclass INTEGER,
    participants_total INTEGER,
    participants_gender INTEGER,
    participants_ageclass INTEGER,
    priority_level TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    source_record_id INTEGER
        REFERENCES source_records(id) ON DELETE SET NULL,
    excluded_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_race_results_activity ON race_results(activity_id);
"""


MIGRATION_17_SQL = """
-- Recording devices. One recorder per activity, so the activity carries a
-- single foreign key instead of a link table; the serial distinguishes two
-- units of the same product.
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    manufacturer TEXT NOT NULL DEFAULT '',
    product TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    acquired_on TEXT,
    retired_on TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE activities ADD COLUMN device_id TEXT
    REFERENCES devices(id) ON DELETE SET NULL;
"""


MIGRATION_18_SQL = """
-- Training periods: seasons, plans, illness, travel and recovery. A period is
-- a date range, which an event is not; ranges may overlap (an illness inside a
-- season). Intervals supplies the season starts and the sickness notes; a
-- manual row is never removed by the recompute.
CREATE TABLE training_periods (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL,
    end_date TEXT,
    source TEXT NOT NULL DEFAULT 'intervals',
    source_record_id INTEGER
        REFERENCES source_records(id) ON DELETE SET NULL,
    notes TEXT NOT NULL DEFAULT '',
    excluded_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_training_periods_dates
ON training_periods(start_date, end_date);
"""


MIGRATION_19_SQL = """
-- Wellness extras. The Intervals payloads carry sleep score and quality,
-- SpO2, weight, steps, floors climbed and their own CTL/ATL; readiness,
-- stress, respiration, mood, soreness and fatigue are present as keys but
-- never populated, so they get no column yet.
ALTER TABLE wellness_days ADD COLUMN weight_kg REAL;
ALTER TABLE wellness_days ADD COLUMN sleep_score REAL;
ALTER TABLE wellness_days ADD COLUMN sleep_quality REAL;
ALTER TABLE wellness_days ADD COLUMN spo2 REAL;
ALTER TABLE wellness_days ADD COLUMN steps INTEGER;
ALTER TABLE wellness_days ADD COLUMN floors_climbed INTEGER;
ALTER TABLE wellness_days ADD COLUMN ctl REAL;
ALTER TABLE wellness_days ADD COLUMN atl REAL;
"""


MIGRATION_20_SQL = """
-- Routes: a named loop or course, kept apart from the activity that ran it.
-- The sheet's Streckennummer is the stable key; a name-only row gets a
-- name-scoped key. Runalyze's recurring_route id is a different identity, so
-- the two never merge automatically.
CREATE TABLE routes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    external_ref TEXT,
    distance_m REAL,
    source TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    excluded_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_routes_source_ref
ON routes(source, external_ref)
WHERE external_ref IS NOT NULL AND excluded_at IS NULL;

-- A run can cover several routes, so the link is a table, not a column.
CREATE TABLE activity_routes (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    route_id TEXT NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, route_id, source)
);

CREATE INDEX idx_activity_routes_route ON activity_routes(route_id);
"""


MIGRATION_21_SQL = """
-- A planned race and the activity that ran it. A race day can also have
-- warmup and cooldown activities, so this is a link table: one event may
-- point at several activities and one activity at several events.
CREATE TABLE event_activity_links (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    match_method TEXT NOT NULL DEFAULT 'auto',
    confidence REAL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, activity_id)
);

CREATE INDEX idx_event_activity_links_activity
ON event_activity_links(activity_id);
"""


MIGRATION_22_SQL = """
-- Social text that belongs to a source, not to the canonical training
-- fields: a Strava title is a pun, a description is a social note, and
-- neither may compete with the workout name or the training notes.
-- Keyed by source so a manual row and a source row can coexist; a source
-- reimport refreshes only its own row.
CREATE TABLE activity_social (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    external_id TEXT,
    url TEXT,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, source)
);

CREATE INDEX idx_activity_social_source
ON activity_social(source, external_id);
"""


MIGRATION_23_SQL = """
-- Manual edits are inputs, not just the materialized value: a rebuild has to
-- reproduce them. One row per activity and field holds either a manual value
-- or a manual owner decision (a forced source), never both. The legacy copy
-- keeps only the value; the pre-manual source was not recorded.
CREATE TABLE activity_manual_fields (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    value_json TEXT,
    owner_source TEXT,
    note TEXT NOT NULL DEFAULT '',
    edited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, field_name),
    CHECK ((value_json IS NULL) <> (owner_source IS NULL))
);

INSERT INTO activity_manual_fields (activity_id, field_name, value_json)
SELECT activity_id, field_name, value_json
FROM activity_field_sources
WHERE is_manual = 1 AND value_json IS NOT NULL;
"""


MIGRATION_24_SQL = """
-- A device row can be retired as an identity without deleting it: a provider
-- alias that no activity uses after the FIT claim, or a device the athlete
-- replaced. The repository lists only the active rows.
ALTER TABLE devices ADD COLUMN excluded_at TEXT;
"""


MIGRATION_25_SQL = """
-- An interval set carries its provenance: Intervals.icu's typed reps, or a
-- derived set from device laps. A derived write never replaces a measured
-- set, and the reports can label the difference.
ALTER TABLE activity_intervals ADD COLUMN source TEXT NOT NULL DEFAULT '';
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
    11: MIGRATION_11_SQL,
    12: MIGRATION_12_SQL,
    13: MIGRATION_13_SQL,
    14: MIGRATION_14_SQL,
    15: MIGRATION_15_SQL,
    16: MIGRATION_16_SQL,
    17: MIGRATION_17_SQL,
    18: MIGRATION_18_SQL,
    19: MIGRATION_19_SQL,
    20: MIGRATION_20_SQL,
    21: MIGRATION_21_SQL,
    22: MIGRATION_22_SQL,
    23: MIGRATION_23_SQL,
    24: MIGRATION_24_SQL,
    25: MIGRATION_25_SQL,
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
