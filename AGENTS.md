# Project instructions

hobbyjogging is a Python monorepo: one canonical SQLite training database,
source importers, and source-independent reports.

## Session scope convention

- **Root sessions** (this directory) handle architecture, planning, schema or
  model changes, cross-package contracts, docs/roadmap, and real-DB strategy.
- **Package sessions** (`packages/<pkg>`) handle changes confined to that
  package: features, bug fixes, tests, and package docs.
- If a package change needs a core API or schema change, settle or implement
  the core part in a root session first, then consume it in the package.
- Package sessions may read the whole repo; only *changes* stay in their lane.
- Commit scope follows session scope. Never stage unrelated in-progress edits
  (check `git status` before committing).
- Do not push; the user pushes manually.
- The user runs interactive triage against the real database themselves. Test
  risky operations on a copy (e.g. `/tmp/opencode/`) first.

## Packages

- `packages/hobbyjogging-core` — canonical model, schema/migrations, sport
  vocabulary, `TrainingWriter`, `TrainingRepository`.
- `packages/hobbyjogging-import` — FIT, Intervals.icu, and Garmin Personal API
  importers, review queue and triage. Runalyze enrichment is planned.
- `packages/hobbyjogging-reports` — analysis, Markdown reports, charts, and the
  activities table over `DataSource` and the canonical model.

## Tests

Run each package's suite from its own tests directory (pytest is not
installed):

```bash
cd packages/<pkg>/tests && uv run python -m unittest discover -q
```

Cross-package changes must leave all three suites green.

## Data model rules

- Default DB `data/hobbyjogging.db` (`HOBBYJOGGING_DB` overrides); FIT files
  `data/fit` (`HOBBYJOGGING_FIT_DIR` overrides). Real DB lives at
  `~/projects/laufen_private/data/db/hobbyjogging.db`.
- Imports write; reports read only (`DataSource` + canonical model).
- "Delete" means durable soft delete via `excluded_at`, never a hard delete.
- Events are Intervals-authoritative: fields are replaced (including NULLs),
  removed events are soft-excluded, and manual/other-source events are left
  alone.
- Manual values outrank every import source and survive reimports.
- `duration_s` is recording/timer time, `moving_s` is moving time, and
  `elapsed_s` is elapsed time; all three are owner-tracked.
- There is no automatic per-source priority. The first owner keeps a field;
  meaningful cross-source disagreement becomes a `field_conflict` review item.
- A trusted source may force ownership only on an explicit human action
  (triage `(t)`); manual fields still win. Normal imports never force.
- VO2max has two owners: Garmin FIT → `vo2max_garmin`, Runalyze →
  `vo2max_runalyze`. Tags are per-source and manual tags are never replaced.
- Sports normalize through `hobbyjogging_core.sports`; never hard-code aliases.
- Reports use matplotlib only, never pandas.
