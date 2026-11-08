# Package instructions: hobbyjogging-import

Source ingestion and the review queue for the hobbyjogging monorepo.

## Scope

- Work on this package. Read `hobbyjogging-core` and `hobbyjogging-reports` as
  reference, but keep changes here unless a core/schema change is required.
- If a change needs a core API or schema change, settle it in a root session
  first, then consume it here.
- Commit only files in this package; never push.

## Tests

```bash
cd packages/hobbyjogging-import/tests && uv run python -m unittest discover -q
```

- pytest is not installed; use `unittest`.
- Tests must never touch the real database. Use `connect(":memory:")` or a
  temporary file.
- Network access must be injectable/faked; no test may call Intervals.icu or
  Garmin.

## Data rules

- Importers write; they never render reports.
- No per-source priority except `moving_s` and `elapsed_s`, which Intervals
  owns: an Intervals value replaces another source's value silently, and
  another source never overrides it or opens a review item. For every other
  field, the first owner keeps it, same-source reimports refresh their own
  fields, and a meaningful cross-source disagreement becomes a
  `field_conflict` review item instead of overwriting.
- `upsert_activity(..., force=True)` is reserved for an explicit human trust
  decision (triage `(t)`); manual fields still win. Normal imports never force.
- Manual values (`activity_field_sources.is_manual = 1`) are never overwritten.
- "Delete" means durable exclusion (`excluded_at`), never a hard delete.
- Sports normalize through `hobbyjogging_core.sports`; never hard-code aliases
  here.
- VO2max has two owners: FIT writes `vo2max_garmin`, Runalyze writes
  `vo2max_runalyze`. Tags are per-source; manual tags are never replaced.
- Raw payloads go to `source_records`; review items are idempotent by
  `(category, fingerprint, activity_id)`.

## Conventions

- The real database lives at `HOBBYJOGGING_DB`; the user runs interactive
  triage themselves. Do not run imports or writes against it without being
  asked.
- Test risky operations on a copy (e.g. `/tmp/opencode/`).
- Keep CLI, importers, and review code consistent with the existing module
  layout (`fit_import.py`, `intervals.py`, `quality.py`, `triage.py`, ...).
