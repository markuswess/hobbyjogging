# hobbyjogging-maintenance

Schema evolution and registered data work for the training database.

This is the composition root: the only package allowed to depend on core,
import, and reports at the same time.

## Two kinds of task

- **backfill** — a one-time transformation after a schema or logic change.
  Recorded in `data_migrations` and skipped once applied. Changing the
  transformation means a new id (`..._v2`), never an edit.
- **recompute** — an idempotent re-derivation of stored values from their
  authoritative inputs (raw payloads or other canonical fields). It runs every
  time and is only logged.

Schema changes themselves are not tasks: they are ordered, immutable SQL
migrations in `hobbyjogging_core.db.migrations`, applied by `open_database()`.

## Commands

```bash
uv run --env-file .env hobbyjogging-maintenance list
uv run --env-file .env hobbyjogging-maintenance status
uv run --env-file .env hobbyjogging-maintenance run <task> --dry-run
uv run --env-file .env hobbyjogging-maintenance run <task>
uv run --env-file .env hobbyjogging-maintenance run --all
```

`run` options:

| Option | Meaning |
|---|---|
| `--dry-run` | run the real code path, then roll the transaction back |
| `--force` | run a backfill that is already applied |
| `--from` / `--to` | limit to a local-date range |
| `--entity ID` | limit to one activity or event |
| `--limit N` | first N entities |
| `--output PATH` | write the task's findings (e.g. conflicts) to a file |
| `--database PATH` | use a database other than `HOBBYJOGGING_DB` |

`run --all` runs every backfill that is not applied yet. `sync.sh` runs the six
idempotent recomputes after a successful sync — `workout_sets_current`,
`workout_classification_queue`, `athlete_thresholds_current`,
`activity_zone_configs_current`, `training_periods_current` and
`race_links_current` — and skips them with `--no-classify`; backfills stay
deliberate.

## Shipped tasks

Backfills (one-time, recorded, skipped once applied):

| id | what |
|---|---|
| `activity_device_v1` | Create the devices from FIT and fill `activities.device_id`. |
| `activity_elevation_v1` | Fill elevation gain/loss from the stored payloads. |
| `activity_max_hr_v1` | Fill `max_hr` from the stored payloads. |
| `activity_routes_v1` | Resolve the sheet's `Strecke`/`Streckennummer` into routes and link the activity. |
| `activity_weather_v1` | Create `activity_weather` rows from the stored payloads. |
| `device_identity_v1` | Re-point activities on a provider fallback device at the FIT device they claim, or clear an app-name fallback. |
| `device_identity_orphans_v1` | Soft-exclude the provider device rows left unused after the FIT claim (never delete). |
| `drop_classification_tags_v1` | Remove the sheet's `Trainigstyp` codes from `activity_tags`, keeping area labels and manual tags. |
| `drop_empty_intervals_v1` | Drop the empty 1 s / 0 m Intervals artifact from stored interval sets. |
| `event_race_method_v1` | Re-derive the `race` method for existing Intervals events from their payload category. |
| `event_zones_v1` | Re-derive planned-event zone kinds/times from the saved Intervals payloads. |
| `fartlek_from_fs_v1` | Convert sheet `fs` activities from `intervals` to `fartlek`. |
| `remove_tempo_method_v1` | Convert the retired `tempo` method to `continuous` (targets unchanged). |
| `wellness_extras_v1` | Fill weight, sleep score/quality, SpO2, steps, floors and CTL/ATL. |
| `workout_classification_v1` | Classify activities from the reports classifier and the sheet code; disagreements are left unclassified and listed. |

Recomputes (idempotent, run every time):

| id | what |
|---|---|
| `athlete_thresholds_current` | Derive the dated, per-sport max HR/LTHR/threshold-pace snapshots from the Intervals payloads. |
| `activity_zone_configs_current` | Derive the zone configs and point each activity at the config of its era. |
| `training_periods_current` | Derive seasons, illness ranges and notes from the Intervals event notes. |
| `race_links_current` | Match race events (and official results) to activities and derive the `race` method. |
| `workout_sets_current` | Derive methods/targets for activities that have none (classifier + sheet, disagreements left to the queue). |
| `workout_classification_queue` | Turn those disagreements into `workout_classification` review items and close the ones that no longer apply (`k` in triage). |
| `verify_canonical` | Diff every owned canonical field against its manual value, owner patch or pointer without writing. |
| `recompute_canonical` | Re-project every owned canonical field from its inputs; never re-decides ownership. |

## Adding a task

```python
from ..context import TaskContext
from ..registry import task


@task("my_change_v1", kind="backfill", description="One line.")
def my_change(context: TaskContext) -> None:
    for activity in context.repository.activities(start, end):
        context.count("seen")
        context.writer.replace_activity_workout_methods(
            activity.id, ["continuous"], source="backfill"
        )
```

Register the module in `backfills/__init__.py` and add a test. Rules:

- Write through `context.writer`; manual values and ownership rules then keep
  holding.
- Do not commit. The runner owns the transaction and rolls it back for a dry
  run.
- Respect `context.scope` and count what you did with `context.count`.
- Put long findings in `context.output_lines` and call `context.write_output()`;
  put one-line hints in `context.note()`.
- Raise on real problems: the runner rolls back and records the failure.

## Guarantees

- One transaction per run; a dry run executes the real code path and rolls it
  back, so it cannot drift from a real run.
- An applied backfill is skipped unless `--force` is given.
- Every run, dry or not, is recorded in `maintenance_runs` with counts and
  status; applied backfills are recorded in `data_migrations`.
- A failing task rolls back completely and is recorded as `failed` with the
  error message.
