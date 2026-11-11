# Next up: maintenance package

This file records what the package is still waiting on.

## Done

- **Recurring workout-set derivation.** `workout_sets_current` is a
  `recompute` task that derives methods/targets for activities that have none,
  using the same classifier/sheet helpers as the backfill. It fills gaps only:
  any activity with sets from any source (manual, backfill, classifier) is
  skipped, so triage decisions and the one-time backfill are never fought.
  Disagreements stay empty and are left to `workout_classification_queue`.
  `sync.sh` runs both after a successful sync (`--no-classify` skips them);
  the full-DB run takes about half a second.

## Next

- **`event_race_method_v1`** (backfill). The Intervals importer maps
  `RACE_A`/`RACE_B`/`RACE_C` to the `race` workout method on event upsert
  (`hobbyjogging_import.intervals.RACE_CATEGORIES`), but only for events a
  sync window touches. The calendar has 3 race events in its payloads (2
  `RACE_A`, 1 `RACE_B`) and only 1 carries the method.
  - For every event linked to an Intervals event record, re-derive the method
    set from `payload_json.category` with the same helper and write it via
    `replace_event_workout_methods(..., source="backfill")`.
  - Leave manual event methods alone (the writer already protects
    `is_manual` rows); a changed mapping means a new id (`_v2`).
  - Idempotent; `--dry-run`; scope by `--from`/`--to`/`--entity`/`--limit`.
  - Tests: `RACE_A` → `race`; `WORKOUT` → no methods; a manual `race` row
    survives; a rerun is a no-op; dry-run writes nothing.
  - Docs: package README table, root `NEXT_UP.md` when it lands.

## Waiting on

Nothing. The package owns schema evolution, backfills, recomputes, and their
bookkeeping; new data work should register a task here instead of a script.
