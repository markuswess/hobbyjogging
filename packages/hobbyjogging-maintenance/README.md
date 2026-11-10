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

`run --all` runs every backfill that is not applied yet. `sync.sh` does not
run maintenance tasks; they stay deliberate.

## Shipped tasks

| id | kind | what |
|---|---|---|
| `event_zones_v1` | backfill | Re-derive planned-event zone kinds/times from the saved Intervals payloads. |
| `workout_classification_v1` | backfill | Classify activities from the reports classifier and the sheet `Trainigstyp` code; disagreements are left unclassified and listed. |
| `workout_classification_queue` | recompute | Turn those disagreements into `workout_classification` review items and close the ones that no longer apply. Resolve them with `hobbyjogging-import review triage` (`k`). |

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
