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

- **`drop_empty_intervals_v1`** (backfill). Once the import filter lands,
  rewrite the stored interval set for activities that still carry the empty
  artifacts. Read the rows per activity, drop those where `duration_s <= 1`
  and `distance_m < 1` (reuse `hobbyjogging_import.intervals.is_empty_interval`
  once it exists), and write the rest back with
  `replace_activity_intervals(activity_id, kept, source_record_id=...)` using
  the activity's existing interval source record. Expected: ~239 rows across
  ~235 activities; 220 of those then match their lap count.
  - Idempotent; `--dry-run`; scope by `--from`/`--to`/`--entity`/`--limit`.
  - Tests: the trailing recovery is removed, a genuine 2 s / 5 m segment
    survives, an activity whose only interval is empty ends with no rows, a
    rerun is a no-op, dry-run writes nothing.
  - Docs: package README table, root `NEXT_UP.md` when it lands.

Nothing else queued. New data work registers a task here instead of a script.

## Waiting on

Nothing. The package owns schema evolution, backfills, recomputes, and their
bookkeeping.
