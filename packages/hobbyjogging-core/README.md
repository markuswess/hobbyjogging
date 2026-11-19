# hobbyjogging-core

Canonical training model, SQLite schema, migrations, and shared helpers.

`hobbyjogging-core` is the shared contract used by `hobbyjogging-import` and
`hobbyjogging-reports`. It contains no network or report-rendering code.

## Model

Canonical types live in `hobbyjogging_core.model`:

- `Activity` (including both VO2max values, tags and the device id)
- `WellnessDay`
- `Event` and `EventZoneTime`
- `Interval` and `Lap`
- `Equipment`, `ActivityEquipment`, `EquipmentSourceLink`
- `Route`, `ActivityRoute`
- `ActivitySocial` (per-source social text)
- `Device`
- `ReviewItem`

`DataSource` lives in `hobbyjogging_core.datasource`. The shared sport
vocabulary lives in `hobbyjogging_core.sports` (canonical names, labels, sport
groups, and one alias table for FIT/Intervals/manual entry). The import policy
(`sources.toml`) is parsed in `hobbyjogging_core.sources_config`.

## Database

Open and migrate a database with:

```python
from hobbyjogging_core import open_database

conn = open_database()  # data/hobbyjogging.db
```

Set `HOBBYJOGGING_DB` to use a different path.

Migrations are ordered SQL scripts tracked with SQLite's `PRAGMA user_version`.
`SCHEMA_VERSION` is the current target version (24).

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
- A manual value or a manual owner decision is stored as an **input** in
  `activity_manual_fields`: one row per `(activity, field)` with either a value
  or an owner patch. The canonical column is a projection that
  `recompute_canonical` rebuilds and `verify_canonical` checks; ownership is a
  recorded decision, never re-derived.
- The first source to write a field keeps it; re-importing from the same
  source refreshes its own fields. The exception is a ranked authority:
  `moving_s` and `elapsed_s` prefer Intervals, then FIT; `device_id` and
  `vo2max_garmin` prefer FIT. The ranked value
  replaces another source's value silently, and an unranked value never
  overrides it or opens a conflict.
- Agreement within tolerance is a no-op; a meaningful disagreement on any
  other field becomes a `field_conflict` review item and changes nothing.
  Average HR uses a wider 5 bpm floor because device and stream averages
  legitimately drift by a few bpm.
- A blank `name`/`description` counts as unfilled: a later source may supply
  the text, while an empty incoming value never clears it.
- `force=True` overrides ownership for one explicit re-import, except for
  manual fields.
- `duration_s` (recording/timer) is owner-tracked; `moving_s` (moving time)
  and `elapsed_s` use a ranked authority (Intervals, then FIT).
- VO2max has independent owners: Garmin FIT writes `vo2max_garmin`, Runalyze
  writes `vo2max_runalyze`, and Runalyze may fill an empty Garmin slot.

Planned events follow a different rule: `upsert_event` treats the source as
authoritative and replaces every field (including NULLs), and revives an
excluded event. `exclude_event` / `restore_event` manage the soft exclusion
used by the event sync. `set_event_zone_times(event_id, kind, rows)` replaces
an event's planned zone distribution.

### Schema layers

- `source_records` — immutable raw imports, checksums, file references, and
  the Garmin fetch manifest (`source = "garmin"`, `record_type =
  "activity-file"`).
- `activities`, `wellness_days`, `events` — canonical merged data, including
  recording/elapsed/moving time, elevation and max HR (v12), `vo2max_garmin`,
  `vo2max_runalyze`, `device_id` (v17), and event `training_load`. Events carry
  `excluded_at`; the repository hides excluded events.
- `activity_manual_fields` (v23) — the manual input layer: manual values and
  owner patches, the inputs a rebuild replays.
- `activity_social` (v22) — social text per source (`source` is data), with a
  manual row that survives imports.
- `activity_weather` (v13) — one row per activity: temperature, feels-like,
  humidity, wind, pressure, UV, clouds, condition, night flag.
- `devices` (v17, `excluded_at` in v24) — recording devices by serial; one
  recorder per activity. A retired provider row is soft-excluded, never
  deleted.
- `routes` (v20) + `activity_routes` — named loops/courses and the activities
  that covered them; the sheet keys by `Streckennummer`, Runalyze's
  `recurring_route` is a different identity.
- `race_results` (v16) — official race distance/time, placement, participants,
  priority and status, kept apart from the measured GPS values.
- `event_activity_links` (v21) — a planned race and the activity that ran it.
- `training_periods` (v18) — dated seasons, plans, illness, travel and
  recovery ranges; manual rows survive the recompute.
- `athlete_thresholds` (v14/v15) — dated, per-sport max HR, LTHR and threshold
  pace snapshots; `zone_configs` holds the zone boundaries and each activity
  points at the config of its era.
- `event_zone_times` — planned event zone distribution (`zone_label`,
  `zone_index`, `seconds`); `events.zone_kind` names the zone system
  (`pace`, `hr`, `power`, or `unknown`).
- `activity_sources` — links between canonical activities and raw records.
- `activity_field_sources` — per-field provenance; manual values are marked.
- `activity_tags` — per-source activity labels (`is_manual = 1` for manual).
- `activity_workout_methods`, `activity_workout_targets`,
  `event_workout_methods`, `event_workout_targets` — set-based workout
  classification (`hobbyjogging_core.workouts`).
- `review_items` — import conflicts and questionable activities, with a
  fingerprint for idempotent detection and an open/ignored/resolved status.
- `activity_laps`, `activity_intervals` — FIT laps and structured intervals.
- `activity_zone_times`, `zone_configs` — zone times and their definitions.
- `equipment`, `activity_equipment`, `equipment_source_links` — gear and
  activity assignments.
- `fit_scan_files` (v11) — the FIT archive scan manifest.
- `data_migrations`, `maintenance_runs` (v10) — registered data work.
- `import_runs` — import history and counters.

Equipment mileage is derived through the `equipment_usage` view rather than
stored on the equipment row.
