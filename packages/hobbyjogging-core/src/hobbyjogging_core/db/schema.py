"""Initial SQLite schema.

Dates and timestamps are stored as ISO-8601 text. Durations are seconds,
distances are meters, and booleans are integers (0/1).
"""

INITIAL_SCHEMA_SQL = """
CREATE TABLE import_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_imported INTEGER NOT NULL DEFAULT 0,
    records_skipped INTEGER NOT NULL DEFAULT 0,
    parameters_json TEXT,
    error TEXT,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE source_records (
    id INTEGER PRIMARY KEY,
    import_run_id INTEGER REFERENCES import_runs(id) ON DELETE SET NULL,
    source TEXT NOT NULL,
    record_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    checksum TEXT NOT NULL,
    payload_json TEXT,
    raw_path TEXT,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, record_type, external_id)
);

CREATE TABLE zone_configs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    boundaries_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE activities (
    id TEXT PRIMARY KEY,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    started_at_utc TEXT,
    local_date TEXT NOT NULL,
    tz_offset_min INTEGER,
    sport TEXT NOT NULL,
    sub_sport TEXT,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    duration_s REAL NOT NULL DEFAULT 0,
    distance_m REAL NOT NULL DEFAULT 0,
    avg_hr REAL,
    training_load REAL,
    rpe REAL,
    feel INTEGER CHECK (feel IS NULL OR feel BETWEEN 1 AND 5),
    intensity REAL,
    pace_zone_config_id TEXT REFERENCES zone_configs(id) ON DELETE SET NULL,
    hr_zone_config_id TEXT REFERENCES zone_configs(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE activity_sources (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    source_record_id INTEGER NOT NULL REFERENCES source_records(id) ON DELETE CASCADE,
    match_method TEXT NOT NULL,
    confidence REAL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (activity_id, source_record_id)
);

CREATE UNIQUE INDEX idx_activity_sources_one_primary
    ON activity_sources(activity_id) WHERE is_primary = 1;

CREATE TABLE activity_field_sources (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    source TEXT NOT NULL,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    value_json TEXT,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, field_name)
);

CREATE TABLE activity_laps (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    lap_index INTEGER NOT NULL,
    start_time_utc TEXT,
    duration_s REAL NOT NULL DEFAULT 0,
    distance_m REAL NOT NULL DEFAULT 0,
    avg_hr REAL,
    max_hr REAL,
    elevation_gain_m REAL,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    UNIQUE (activity_id, lap_index)
);

CREATE TABLE activity_intervals (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    interval_index INTEGER NOT NULL,
    group_id TEXT,
    type TEXT NOT NULL DEFAULT '',
    start_time TEXT NOT NULL DEFAULT '',
    duration_s REAL NOT NULL DEFAULT 0,
    distance_m REAL NOT NULL DEFAULT 0,
    avg_hr REAL,
    max_hr REAL,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    UNIQUE (activity_id, interval_index)
);

CREATE TABLE activity_zone_times (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    zone_index INTEGER NOT NULL,
    seconds REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (activity_id, kind, zone_index)
);

CREATE TABLE wellness_days (
    local_date TEXT PRIMARY KEY,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    hrv REAL,
    resting_hr REAL,
    sleep_s REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    local_date TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    duration_s REAL,
    distance_m REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE equipment (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    brand TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    acquired_on TEXT,
    retired_on TEXT,
    target_distance_m REAL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE activity_equipment (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    equipment_id TEXT NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'primary',
    source TEXT NOT NULL DEFAULT 'manual',
    source_record_id INTEGER REFERENCES source_records(id) ON DELETE SET NULL,
    is_manual INTEGER NOT NULL DEFAULT 0 CHECK (is_manual IN (0, 1)),
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, equipment_id, role)
);

CREATE UNIQUE INDEX idx_activity_equipment_one_primary
    ON activity_equipment(activity_id) WHERE role = 'primary';

CREATE TABLE equipment_source_links (
    equipment_id TEXT NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    source_record_id INTEGER NOT NULL REFERENCES source_records(id) ON DELETE CASCADE,
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (equipment_id, source_record_id),
    UNIQUE (source_record_id)
);

CREATE INDEX idx_activities_local_date ON activities(local_date);
CREATE INDEX idx_activities_sport ON activities(sport);
CREATE INDEX idx_activities_started_at_utc ON activities(started_at_utc);
CREATE INDEX idx_source_records_checksum ON source_records(checksum);
CREATE INDEX idx_events_local_date ON events(local_date);
CREATE INDEX idx_equipment_type ON equipment(type);
CREATE INDEX idx_activity_equipment_equipment ON activity_equipment(equipment_id);

CREATE VIEW equipment_usage AS
SELECT
    e.id AS equipment_id,
    e.name AS equipment_name,
    e.type AS equipment_type,
    e.target_distance_m,
    e.retired_on,
    COUNT(a.id) AS activity_count,
    COALESCE(SUM(a.distance_m), 0.0) AS distance_m,
    COALESCE(SUM(a.duration_s), 0.0) AS duration_s,
    MIN(a.local_date) AS first_used_on,
    MAX(a.local_date) AS last_used_on
FROM equipment e
LEFT JOIN activity_equipment ae
    ON ae.equipment_id = e.id AND ae.role = 'primary'
LEFT JOIN activities a ON a.id = ae.activity_id
GROUP BY e.id;
"""
