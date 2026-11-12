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
- **`event_race_method_v1`.** Re-derives the `race` method for every event
  linked to an Intervals record, adding it where the payload category is
  `RACE_A/B/C` and removing a stale non-manual row otherwise; manual rows win.
  Applied to the real DB: 2 events gained the method (Baden Stadtlauf, Linz
  Marathon 2026), 648 unchanged.

## Next

Nothing queued. New data work registers a task here instead of a script.

## Waiting on

Nothing. The package owns schema evolution, backfills, recomputes, and their
bookkeeping.
