# hobbyjogging-core

Canonical training model, SQLite schema, migrations, and shared helpers.

`hobbyjogging-core` is the shared contract used by `hobbyjogging-import` and
`hobbyjogging-reports`. It contains no network or report-rendering code.

## Model

Canonical types live in `hobbyjogging_core.model`:

- `Activity` (including both VO2max values and tags)
- `WellnessDay`
- `Event`
- `Interval`
- `Equipment`
- `ActivityEquipment`

`DataSource` lives in `hobbyjogging_core.datasource`. The shared sport
vocabulary lives in `hobbyjogging_core.sports` (canonical names, labels, sport
groups, and one alias table for FIT/Intervals/manual entry).

## Database

Open and migrate a database with:

```python
from hobbyjogging_core import open_database

conn = open_database()  # data/hobbyjogging.db
```

Set `HOBBYJOGGING_DB` to use a different path.

Migrations are ordered SQL scripts tracked with SQLite's `PRAGMA user_version`.
`SCHEMA_VERSION` is the current target version (6).

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

`upsert_activity` returns a list of `FieldConflict` objects for cross-source
disagreements; importers record them as review items. `force=True` is reserved
for an explicit human trust decision (triage `(t)`): it lets a source take
ownership of every non-manual field. Manual fields are always kept.

Tags are written per source:

```python
writer.replace_activity_tags(
    "activity-uuid",
    ["race", "morning"],
    source="runalyze",
    source_record_id=source_id,
)
```

### Field ownership

- Manual values (`is_manual = 1`) are never overwritten.
- The first source to write a field keeps it; re-importing from the same
  source refreshes its own fields.
- Agreement within tolerance is a no-op; a meaningful disagreement becomes a
  `field_conflict` review item and changes nothing.
- `force=True` overrides ownership for one explicit re-import, except for
  manual fields.
- `duration_s` (recording/timer), `moving_s` (moving time), and `elapsed_s`
  are distinct fields; all three are owner-tracked.
- VO2max has independent owners: Garmin FIT writes `vo2max_garmin`, Runalyze
  writes `vo2max_runalyze`, and Runalyze may fill an empty Garmin slot.

### Schema layers

- `source_records` — immutable raw imports, checksums, file references, and
  the Garmin fetch manifest (`source = "garmin"`, `record_type =
  "activity-file"`).
- `activities`, `wellness_days`, `events` — canonical merged data, including
  recording/elapsed/moving time, `vo2max_garmin`, `vo2max_runalyze`, and
  event `training_load`.
- `activity_sources` — links between canonical activities and raw records.
- `activity_field_sources` — per-field provenance; manual values are marked.
- `activity_tags` — per-source activity labels (`is_manual = 1` for manual).
- `review_items` — import conflicts and questionable activities, with a
  fingerprint for idempotent detection and an open/ignored/resolved status.
- `activity_laps`, `activity_intervals` — FIT laps and structured intervals.
- `activity_zone_times`, `zone_configs` — zone times and their definitions.
- `equipment`, `activity_equipment`, `equipment_source_links` — gear and
  activity assignments.
- `import_runs` — import history and counters.

Equipment mileage is derived through the `equipment_usage` view rather than
stored on the equipment row.
