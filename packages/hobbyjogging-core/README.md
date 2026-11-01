# hobbyjogging-core

Canonical training model, SQLite schema, migrations, and shared helpers.

`hobbyjogging-core` is the shared contract used by `hobbyjogging-import` and
`hobbyjogging-reports`. It contains no network or report-rendering code.

## Model

Canonical types live in `hobbyjogging_core.model`:

- `Activity`
- `WellnessDay`
- `Event`
- `Interval`
- `Equipment`
- `ActivityEquipment`

`DataSource` lives in `hobbyjogging_core.datasource`.

## Database

Open and migrate a database with:

```python
from hobbyjogging_core import open_database

conn = open_database()  # ~/projects/laufen_private/data/db/hobbyjogging.db
```

Set `HOBBYJOGGING_DB` to use a different path.

Migrations are ordered SQL scripts tracked with SQLite's `PRAGMA user_version`.
`SCHEMA_VERSION` is the current target version.

Read canonical data through the repository:

```python
from hobbyjogging_core import TrainingRepository, open_database

conn = open_database()
repository = TrainingRepository(conn)
activities = repository.activities(start, end)
wellness = repository.wellness(start, end)
events = repository.events(start, end)
equipment = repository.equipment()
```

Write imports through `TrainingWriter`:

```python
from hobbyjogging_core import TrainingWriter

writer = TrainingWriter(conn)
run_id = writer.start_import_run("intervals", {"days": 90})
source_id = writer.upsert_source_record(
    source="intervals",
    record_type="activity",
    external_id="i123",
    checksum="...",
    payload_json="{}",
    import_run_id=run_id,
)
writer.upsert_activity(
    "activity-uuid",
    {"local_date": "2026-10-01", "sport": "run", "name": "Easy run"},
    source="intervals",
    source_record_id=source_id,
)
writer.finish_import_run(run_id, "success", records_seen=1, records_imported=1)
```

### Schema layers

- `source_records` — immutable raw imports, checksums, and file references.
- `activities`, `wellness_days`, `events` — canonical merged data.
- `activity_sources` — links between canonical activities and raw records.
- `activity_field_sources` — per-field provenance; manual values are marked.
- `activity_laps`, `activity_intervals` — FIT laps and structured intervals.
- `activity_zone_times`, `zone_configs` — zone times and their definitions.
- `equipment`, `activity_equipment`, `equipment_source_links` — gear and
  activity assignments.
- `import_runs` — import history and counters.

Equipment mileage is derived through the `equipment_usage` view rather than
stored on the equipment row.
