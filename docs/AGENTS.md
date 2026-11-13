# Project instructions

hobbyjogging is a Python monorepo: one canonical SQLite training database,
source importers, and source-independent reports.

## Session scope convention

The project runs three kinds of sessions:

- **Root** (this directory) — general planning and cross-package coding:
  architecture, schema or model changes, cross-package contracts, docs and
  roadmap, and real-DB strategy.
- **Package** (`packages/<pkg>`) — work confined to one package: features, bug
  fixes, tests, and package docs. One session per package.
- **Lab** — exploring metrics and analysis before they enter a package:
  `./lab.sh` sessions, `experiments/` scripts, and the candidate list in
  `experiments/README.md`. The lab may read the whole repo and write
  experiments and lab docs, but it does not change package code; promotion
  happens in the package session once an idea passes the gate in
  `docs/METRICS.md` (see `docs/ARCHITECTURE.md`). The root session writes and
  commits the promoted/rejected cards in `docs/METRICS.md`.

Rules:

- If a package change needs a core API or schema change, settle or implement
  the core part in a root session first, then consume it in the package.
- Sessions may read the whole repo; only *changes* stay in their lane.
- `experiments/` belongs to the lab; package sessions consume what the lab
  promoted rather than writing new experiments.
- Commit scope follows session scope. Never stage unrelated in-progress edits
  (check `git status` before committing).
- Do not push; the user pushes manually.
- The user runs interactive triage against the real database themselves. Test
  risky operations on a copy (e.g. `/tmp/opencode/`) first.

## Working the todo lists

- **Bugs first.** A reported bug outranks new work: fix it before starting a
  feature, and a bug that blocks other items jumps the queue regardless of
  size. What already exists must be correct before more is added to it.
- Pick by **impact per unit of effort**, not by list order: the highest-impact,
  lowest-workload item first. The numbering is not a schedule.
- **Stay inside the package as long as possible.** If an item can be solved
  within the package, do that before asking for a core, schema or cross-package
  change; escalate only when the package genuinely cannot express the fix.
- When an item needs both, do the smallest core or cross-package piece that
  unblocks it, then return to the package and finish it there.
- If an item turns out much larger than expected, stop and leave it for the
  root session to re-scope instead of half-implementing it across packages.
- Record a deferral with its reason in that package's `NEXT_UP.md` (for example
  "needs elevation data"), so the next session does not re-discover it.

## Keeping it readable

Neither the code nor the docs may become an unreadable monster. A periodic
cleanup pass is part of the todo list, not a rewrite project.

- **Delete rather than comment out.** Dead code, unused helpers, unused
  exports and stale flags go in the same change that notices them.
- **No speculative abstraction.** Add an indirection when a second caller
  exists, not before.
- **One fact, one place.** `NEXT_UP.md` owns the work queue, `METRICS.md` the
  metric cards, `ARCHITECTURE.md` the structure and rules, `AGENTS.md` the
  conventions. Do not restate another document's content; point at it.
- **Keep the Done lists short.** Git history is the changelog; a long `## Done`
  section is duplication that rots.
- **Split or trim in the same change.** If a file outgrows its purpose while
  you are working in it, fix that there — do not leave it for later.
- **Leave it no worse.** A touch-up is welcome, a drive-by rewrite that mixes
  concerns with a fix is not.

## Packages

- `packages/hobbyjogging-core` — canonical model, schema/migrations, sport
  vocabulary, `TrainingWriter`, `TrainingRepository`.
- `packages/hobbyjogging-import` — FIT, Intervals.icu, and Garmin Personal API
  importers, review queue and triage. Runalyze enrichment is planned.
- `packages/hobbyjogging-maintenance` — schema-evolution runner and registered
  backfills/recomputes.
- `packages/hobbyjogging-reports` — analysis, Markdown reports, charts, and the
  activities table over `DataSource` and the canonical model.

## Schema and data changes

- Schema changes are ordered, immutable SQL migrations in
  `hobbyjogging_core/db/migrations.py`; bump `SCHEMA_VERSION`.
- Changes to existing rows go through a registered task in
  `hobbyjogging-maintenance`: `backfill` for a one-time transformation
  (recorded as applied), `recompute` for re-deriving stored values (runs every
  time). Never add another ad-hoc script.
- Never edit an applied migration or task; add a new version instead.
- Dry-run first (`--dry-run`), then apply; back up the real DB first.
- Tasks write through `TrainingWriter` and must not commit; the runner owns
  the transaction and rolls it back for a dry run.

## Tests

Run each package's suite from its own tests directory (pytest is not
installed):

```bash
cd packages/<pkg>/tests && uv run python -m unittest discover -q
```

Cross-package changes must leave all four suites green.

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
  `elapsed_s` is elapsed time. `duration_s` is owner-tracked; `moving_s` and
  `elapsed_s` are Intervals-authoritative and never produce a review item.
- There is no automatic per-source priority, except the fixed `moving_s` /
  `elapsed_s` authority above. The first owner keeps every other field;
  meaningful cross-source disagreement becomes a `field_conflict` review item.
  For average HR, a disagreement is only meaningful beyond 5 bpm.
- A blank text field counts as unfilled: a later source may fill an empty
  `name`/`description`, while an empty incoming value never clears text.
- A trusted source may force ownership only on an explicit human action
  (triage `(t)`); manual fields still win. Normal imports never force.
- VO2max has two owners: Garmin FIT → `vo2max_garmin`, Runalyze →
  `vo2max_runalyze`. Tags are per-source and manual tags are never replaced.
- Sports normalize through `hobbyjogging_core.sports`; never hard-code aliases.
- Workout methods/targets are set-based (`activity_workout_*`,
  `event_workout_*`). Quality is derived: base/recovery only is non-quality;
  intervals, long_run, progression, race, and the quality targets are
  quality; strides never make a session quality by itself. A tempo run is
  `continuous` with a `threshold` target (there is no `tempo` method).
- Reports use plotly for charts and never pandas.

## Metrics

- New metrics start in the lab (`./lab.sh`, `experiments/`) and are promoted
  only through the gate in `docs/METRICS.md`.
- Every promoted metric keeps a card there; definition, baseline and caveats
  stay in sync with the code.
- The dashboard is the last place a metric lands, never the first.
