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
uv run --env-file .env hobbyjogging-maintenance init
uv run --env-file .env hobbyjogging-maintenance doctor --no-network
uv run --env-file .env hobbyjogging-maintenance list
uv run --env-file .env hobbyjogging-maintenance status
uv run --env-file .env hobbyjogging-maintenance run <task> --dry-run
uv run --env-file .env hobbyjogging-maintenance run <task>
uv run --env-file .env hobbyjogging-maintenance run --all
uv run --env-file .env hobbyjogging-maintenance export-manual --output overlay.jsonl
uv run --env-file .env hobbyjogging-maintenance import-manual overlay.jsonl
uv run --env-file .env hobbyjogging-maintenance rebuild --source live.db
uv run --env-file .env hobbyjogging-maintenance audit --output audit.md
```

`init` creates and migrates the database and the FIT directory; a second run
only checks the schema. `doctor` checks `uv`, the DB path and writability, the
schema version, the FIT directory, each configured credential, bounded API
liveness probes, pending backfills, source freshness, `sources.toml` and
whether the enabled sources can supply the visible dashboard areas (wellness,
load, zones, social, reps, races), then prints the next command. The root
wrappers are `./init.sh` and `./doctor.sh`.

## Manual overlay and rebuild

`export-manual` writes the decisions that cannot be recomputed from a payload:
manual activity fields and owner patches, manual workout sets, manual tags,
manual equipment links, activity exclusions and the ignored/resolved review
answers. It is JSONL, one record per line, with a version header; the default
output is stdout, `--output PATH` writes a file. `import-manual` re-applies it
to a database that already has the raw/structural layer (activities, source
records, links, pointers, equipment).

The overlay lives in the private repository next to the database and is
exported at each release tag. It is not a backup and not a canonical dump: the
raw payloads and the SQLite file remain the data of record.

`rebuild` is the proof. It copies the raw source records, activity identities,
links, ownership pointers, devices and equipment into a fresh schema, applies
the overlay, projects `local_date`/`sport`, runs `recompute_canonical`, and
diffs every canonical activity value and the exclusion set against the live
database. It does not re-import from the network, re-match activities or
re-decide ownership; an empty diff proves the projection from the stored
inputs, while the pointers stay the recorded decisions. `--target PATH` keeps
the rebuilt database for inspection; without it the target is temporary. Exit
status is 1 on any drift, missing/extra activity or exclusion mismatch.

## Historical audit

`audit` is read-only. It writes a Markdown report of the evidence already in
the database: canonical field coverage per year, raw payload keys without a
canonical home, tag meanings, interval-like descriptions, elevation/trail
candidates, race evidence, classification coverage, illness/season periods and
the review queue. It also reports session-average metric coverage and
cross-source disagreements; `--fit-sample N` controls how many raw FIT files
are parsed for that table (default 100, `0` disables the sample). It opens no
review items and changes nothing. Re-run it as imports land; `--output PATH`
writes the report, otherwise it goes to stdout.

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
| `activity_metrics_v1` | Create `activity_metrics` rows from the stored payloads and the FIT archive. |
| `device_identity_v1` | Re-point activities on a provider fallback device at the FIT device they claim, or clear an app-name fallback. |
| `device_identity_orphans_v1` | Soft-exclude the provider device rows left unused after the FIT claim (never delete). |
| `interval_source_v1` | Stamp the interval rows that predate schema v25 with `source='intervals'`. |
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
| `derived_zone_configs_current` | Build local HR/pace zone configs and lap zone times from manual threshold snapshots; Intervals wins. |
| `training_periods_current` | Derive seasons, illness ranges and notes from the Intervals event notes. |
| `race_links_current` | Match race events (and official results) to activities and derive the `race` method. |
| `workout_sets_current` | Re-derive classifier-sourced methods/targets from the current name/RPE/intensity/reps and fill unclassified gaps; manual, sheet, Runalyze-type and imported sets are left alone (`sheet`-only proposals carry `source='sheet'`). |
| `derived_intervals_current` | Infer WORK/RECOVERY reps from device laps when no measured set exists; `source='derived'`, never overwriting a measured set. |
| `workout_classification_queue` | Turn those disagreements into `workout_classification` review items and close the ones that no longer apply (`k` in triage). |
| `verify_canonical` | Diff every owned canonical field against its manual value, owner patch or pointer without writing. |
| `recompute_canonical` | Re-project every owned canonical field from its inputs; never re-decides ownership. |
| `runalyze_load_current` | Fill an empty `training_load` from Runalyze's `fit_trimp`/`trimp`; Intervals always wins in a mixed database. |

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
