# Next up: maintenance package

This file records what the package is still waiting on.

## Next task: recurring workout-set derivation

### Problem

Workout methods/targets are a *derived* value, but today they are only written
by the one-time `workout_classification_v1` backfill. Activities imported after
that backfill never get sets:

- `workout_classification_v1` is `kind="backfill"` and is recorded in
  `data_migrations`, so it is skipped forever after its first run.
- `workout_classification_queue` is a recompute, but it only opens/closes
  review items for classifier-vs-sheet disagreements. It derives nothing and
  does nothing for an activity with no sheet source.
- Example: the 2026-11-10 "Easy" run
  (`8569237b-0379-5b93-9601-899c301e6b28`) has no sets although the
  classifier proposes `continuous`/`recovery`. It was imported after the
  backfill ran and has only `intervals` + `fit` sources.

The placement rule behind this: importers write received facts; maintenance
derives stored values (backfill = one-time, recompute = ongoing); reports
compute cheap metrics on read. Classification is a stored derived value, so the
recurring derive step belongs here, not in the importer.

### Task

Add a `recompute` task (working name `workout_sets_current`) that derives sets
for activities that have none, using the same helpers as the backfill
(`classifier_proposal`, `sheet_proposal`, `disagrees` in `workouts.py`):

- classifier only → classifier methods/targets
- sheet only → sheet methods/targets
- both agree → union
- both disagree → leave the activity empty (the queue records the decision)
- neither → leave empty

Write with a non-manual source (e.g. `classifier`) through
`replace_activity_workout_methods` / `replace_activity_workout_targets`.

### Rules to settle in the root session

- **Ownership.** Skip activities that already have sets from any source
  (manual, backfill, classifier, sheet) so triage decisions are never fought.
  Or, alternatively, re-derive only rows whose source is the recompute's own
  source; decide explicitly.
- **Scope.** Full database by default; `--activity`/`--entity`, `--from`/`--to`
  and `--limit` come from the shared task context for free.
- **Automation.** `sync.sh` deliberately does not run maintenance tasks. Either
  run the recompute after each sync deliberately, or change sync policy to
  invoke it (root decision).
- **Algorithm moves.** The classifier still lives in
  `hobbyjogging_report.classify`, which maintenance already imports. The
  "classifier into core" hygiene item is separate; this task can land first.

### Tests

- A new activity with no sheet row gets the classifier's sets.
- A new activity with a sheet row and no classifier gets the sheet's sets.
- An existing manual set is untouched.
- A classifier/sheet disagreement stays empty and the queue still opens an
  item.
- A second run is a no-op; `--dry-run` writes nothing.

### Docs

- Add the task to the package README table.
- Update `docs/NEXT_UP.md` when it lands.
