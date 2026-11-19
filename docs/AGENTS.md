# Project instructions

hobbyjogging is a Python monorepo: one canonical SQLite training database,
source importers, and source-independent reports.

## Session scope convention

The project runs four kinds of sessions:

- **Root** (this directory) — general planning and cross-package coding:
  architecture, schema or model changes, cross-package contracts, docs and
  roadmap, and real-DB strategy.
- **Planning** (this directory, before the root coding session) — a docs-only
  root session: it owns `docs/NEXT_UP.md`, `docs/ARCHITECTURE.md` and
  `docs/METRICS.md`, writes no code, does not edit `packages/*/NEXT_UP.md`, and
  runs sequentially with the root coding session on the shared tree.
- **Package** (`packages/<pkg>`) — work confined to one package: features, bug
  fixes, tests, and package docs. One session per package; `hobbyjogging-core`
  has no session of its own and is handled by the root session.
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
- **Small features never wait for a phase.** A bug fix, a dashboard fix, a
  report or column over data already stored, a lab metric that passed the gate,
  or a doc change may be done in its owning package at any time. Not small, so
  it follows the phase queue: a schema migration or backfill, a new source, a
  new write surface, a cross-package contract, or a real-DB write beyond
  triage. A bug fix may still ship an additive, expand-only migration in its
  own session; **bugs first** outranks the queue.
- **Start from your own list.** A package session works from its
  `NEXT_UP.md`; root items are dependencies, not work. Reference a root item by
  number (`root item 4`) and run `uv run python tools/check_todos.py` after any
  renumbering, so the pointer cannot rot.
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
- `packages/hobbyjogging-import` — FIT, Intervals.icu, Garmin Personal API,
  Runalyze and Strava CSV importers, review queue and triage. Runalyze phases
  1–5 and the Strava social/gear import have landed; the per-source create
  policy lives in `sources.toml`.
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
- Manual values outrank every import source and survive reimports; they are
  stored as inputs in `activity_manual_fields`, so a rebuild reproduces them.
  The same table holds an owner patch (triage `(t)`), which keeps the chosen
  source owning the field.
- `duration_s` is recording/timer time, `moving_s` is moving time, and
  `elapsed_s` is elapsed time. `duration_s` is owner-tracked; `moving_s` and
  `elapsed_s` have a ranked authority (Intervals, then FIT) and never produce
  a review item.
- There is no automatic per-source priority. Field rules live in
  `hobbyjogging_core.import_rules`; the writer applies them. The default is
  owner-based: the first source keeps a field, a later source fills only an
  empty value, and a meaningful cross-source disagreement becomes a
  `field_conflict` review item (average HR: beyond 5 bpm). A field may declare
  a ranked authority where one source is a better measurement:
  `moving_s`/`elapsed_s` → Intervals, then FIT; `device_id` and
  `vo2max_garmin` → FIT. Manual values always win.
- Social text is per source in `activity_social`: a source refreshes its own
  row and a manual row survives imports. A per-source target may promote it to
  `activities.name`/`description` (default: social only), because a promoted
  title feeds `classify()`; a description does not.
- Every source that yields activity rows may create. The per-source
  `create | review | ignore` policy in `sources.toml` decides what an unmatched
  row does; FIT, Intervals and the sheet always create and use `enabled`.
  Creation happens only when there is nothing to review.
- Inputs are never rebuilt, projections are: payloads, pointers, manual edits,
  links, exclusions and review answers are inputs; canonical activity fields
  are a cache rebuilt by `recompute_canonical` and checked by
  `verify_canonical`. Ownership stays a recorded decision, not a derivation.
- Add a source as a `SourceProfile` plus an adapter, not as a new branch in
  matching or quality. The profile declares what it can fill, how it matches
  and whether absence means deletion.
- A blank text field counts as unfilled: a later source may fill an empty
  `name`/`description`, while an empty incoming value never clears text.
- A trusted source may force ownership only on an explicit human action
  (triage `(t)`), recorded as a manual owner patch; manual fields still win.
  Normal imports never force.
- VO2max has two owners: Garmin FIT → `vo2max_garmin`, Runalyze →
  `vo2max_runalyze`. Tags are per-source and manual tags are never replaced.
- Route identity is source-scoped: the sheet keys by `Streckennummer` (or the
  name when there is no single number), and Runalyze's `recurring_route` id is
  a different identity — the two never merge automatically.
- A linked race event gives its activity the `race` method under `race_link`;
  a non-excluded official `race_results` row is evidence too, and the method is
  dropped when neither remains. A manual link or a manual method set wins, and
  an ambiguous match becomes an `ambiguous_race` review item rather than a
  guess.
- A gear record that matches an existing equipment item only adds a source
  link; it never overwrites that item's name, brand, model or dates. A name
  tie is broken by the acquisition date (Runalyze's `date_start` against
  `acquired_on`) when exactly one row matches; otherwise an ambiguous match
  opens a non-hiding `ambiguous_equipment` review item.
- Sports normalize through `hobbyjogging_core.sports`; never hard-code aliases.
- Workout methods/targets are set-based (`activity_workout_*`,
  `event_workout_*`). Quality is derived: base/recovery only is non-quality;
  intervals, fartlek, long_run, progression, race, and the quality targets
  are quality; strides never make a session quality by itself. A tempo run is
  `continuous` with a `threshold` target (there is no `tempo` method).
- Reports use plotly for charts and never pandas.

## Metrics

- New metrics start in the lab (`./lab.sh`, `experiments/`) and are promoted
  only through the gate in `docs/METRICS.md`.
- Every promoted metric keeps a card there; definition, baseline and caveats
  stay in sync with the code.
- The dashboard is the last place a metric lands, never the first.
