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

conn = open_database()  # data/hobbyjogging.db
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
