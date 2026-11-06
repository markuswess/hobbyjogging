# Architecture

How hobbyjogging is put together and where it is heading. For the staged plan
see [ROADMAP.md](ROADMAP.md); for working conventions see
[../AGENTS.md](../AGENTS.md).

## Goals

- One canonical training database that is the single ground truth, independent
  of any one device or service.
- Data from several sources merged into one activity, with provenance kept and
  conflicts surfaced instead of silently resolved.
- Human decisions (manual values, exclusions) that survive reimports.
- Reports and dashboards that read the canonical data only and are cheap to
  render anywhere: terminal, laptop browser, phone, wall screen.
- A deterministic data bundle for LLM coaching conversations.

## Principles

1. **Imports write, reports read.** The report layer never mutates the
   database; the import layer never formats output.
2. **No silent overwrites.** Manual values outrank every source. Cross-source
   disagreement becomes a review item, not a priority-rule outcome.
3. **Delete is exclusion.** Rows are retained for audit; nothing is hard
   deleted, so a reimport cannot resurrect deleted data.
4. **Compute → render.** Metrics live in analysis code and return typed data.
   Markdown, HTML, charts, and JSON are renderers over the same values.
5. **Source-independent reads.** Reports consume the canonical model through a
   `DataSource`, never a specific API or file format.
6. **Reproducible output.** Same database and date range produce the same
   report; generation timestamps are explicit, not hidden.

## Topology

Development happens on a laptop; the durable deployment target is an
always-on homelab host. The database lives on exactly one machine and clients
never hold a copy.

```text
   FIT archive      Garmin Personal API     Intervals.icu API     Runalyze API
        |                   |                     |                   |
        |            garmin fetch (FITs)          |          runalyze enrichment
        |                   |                     |                   |
        +-------------------+---------------------+-------------------+
                            |
                     import / sync job
                            |
                  canonical SQLite DB  (source of truth)
                           |
                 analysis + view models
                     /           \
              markdown/CLI     static HTML + SVG
                (terminal)     (generated dashboard)
                                      |
                                Caddy / nginx
                                      |
                    laptop browser · phone · wall screens
```

- **Homelab host**: database on local disk (never NFS/SMB), importers, review
  CLI, dashboard generator, static web server.
- **FIT archive**: synced from the laptop to the homelab (Syncthing or rsync).
  New activities are also fetched directly from the Garmin Personal API.
- **Runalyze**: enrichment only (comments, tags, gear, VO2max), never timing
  or distance.
- **Clients**: browsers only. No database credentials, no JavaScript
  framework, no write access.
- **Access**: private network (Tailscale/WireGuard) or basic auth at the
  reverse proxy. Health data is not exposed publicly.

## Packages

The repo is a uv workspace with three packages.

### `hobbyjogging-core`

Canonical model, schema, and read/write access.

- `model.py` — `Activity`, `Lap`, `Interval`, `WellnessDay`, `Event`,
  `Equipment`, zone models; activities carry both VO2max values and tags.
- `sports.py` — canonical sport names, labels, groups, and the shared alias
  table for FIT/Intervals/manual entry.
- `db/schema.py`, `db/migrations.py` — SQL schema and forward-only migrations
  (`SCHEMA_VERSION`, currently 5).
- `db/writer.py` — `TrainingWriter`: import runs, source records, activity
  upserts, field provenance, manual edits, exclusions, review items, laps,
  intervals, zone times, tags.
- `db/repository.py` — `TrainingRepository`: read queries over the canonical
  model.
- `datasource.py` — the `DataSource` protocol every report consumer depends
  on.
- `db/connection.py` — database path resolution and connection setup.

Core owns the rules that must not drift between packages: field ownership,
conflict detection, sport normalization, exclusion semantics, review-item
fingerprints.

### `hobbyjogging-import`

Source ingestion and the review queue.

- `fit.py` — FIT parsing and normalization (the only module that knows raw FIT
  field names).
- `fit_import.py` — file discovery, matching, activity/lap persistence.
- `garmin.py` — Garmin Personal API client: key → bearer token, activity list,
  original FIT download into the archive, fetch manifest.
- `client.py`, `intervals.py` — Intervals.icu API access and import, including
  the planned-event horizon.
- `links.py` — Intervals/Garmin activity URL resolution for triage and
  `review show`.
- `runalyze.py` — planned Runalyze enrichment import (comments, tags, gear,
  VO2max); never writes timing or distance.
- `matching.py` — temporal activity matching across sources.
- `quality.py` — canonical quality rules, field-conflict recording, review
  fingerprints, quality refresh after edits.
- `values.py` — parsers/formatters for manual entry (`46:20`, `8.2km`).
- `editing.py` — shared manual-edit application used by the CLI and triage.
- `triage.py` — interactive review walk.
- `review_cli.py`, `cli.py` — `hobbyjogging-import` entry point.

### `hobbyjogging-reports`

Analysis, views, and rendering.

- `sources/` — `DataSource` implementations: canonical database (default) and
  direct Intervals.icu API.
- `analysis.py`, `series.py` — pure functions over canonical activities,
  intervals, and wellness; derived metrics such as load, zone distribution,
  pace/HR trends, recovery.
- `model.py` — typed view models and analysis result types.
- `classify.py` — workout taxonomy.
- `daily.py`, `period_report.py`, `subt_report.py` — one Markdown report per
  file; `report_commands.py` dispatches them.
- `sessions.py`, `recent.py`, `debug.py` — session detail, shared lookback
  search, and raw payload dump.
- `activity_list.py` — the activities table (selection, columns, rendering).
- `summary.py` — period totals, quality-session lists, recovery averages.
- `charts.py`, `chart_commands.py` — matplotlib figures over prepared series.
- `format.py`, `mdpretty.py` — human formatting for the terminal.
- `commands.py`, `cli.py`, `command_support.py`, `__main__.py` — command
  registry, shared CLI helpers, and entry point.

The long-term dashboard is a new renderer in this package, not a new analytics
implementation.

## Canonical data model

SQLite, forward-only migrations. Schema version 5.

- `activities` — canonical values: dates, sport, name, description, duration,
  elapsed, distance, heart rate, training load, subjective fields, both VO2max
  values (`vo2max_garmin`, `vo2max_runalyze`), exclusion timestamp.
- `source_records` — raw imported payloads with checksums and provenance
  (`source`, `record_type`, `external_id`, `raw_path`, `payload_json`,
  exclusion timestamp).
- `activity_sources` — links between canonical activities and source records,
  including match method, confidence, and primary flag.
- `activity_field_sources` — per-field provenance: which source wrote a value,
  the value it wrote, and whether it is a manual override.
- `activity_laps`, `activity_intervals`, `activity_zone_times` — detail data
  attached to activities, tagged by source record.
- `activity_tags` (v5) — activity labels with their source; used for dashboard
  filters and later analysis.
- `wellness_days`, `events`, `equipment`, `activity_equipment`,
  `equipment_source_links`, `zone_configs` — supporting canonical data.
- `import_runs` — one row per import with parameters and outcome.
- `review_items` — the review queue: category, severity, detail, context,
  fingerprint, status, resolution note, activity/source links.

Two invariants are enforced by the writer:

- A manual field (`is_manual = 1`) is never overwritten by an import.
- An excluded activity cannot be written to or linked to.

The only exception to owner-based precedence is an explicit human decision:
`upsert_activity(..., force=True)` lets one trusted source take ownership of
every non-manual field. Triage `(t)` uses it to re-import a single Intervals
activity; normal imports never force.

VO2max has two independent owners: Garmin FIT writes `vo2max_garmin` and
Runalyze writes `vo2max_runalyze`. Runalyze may fill an empty
`vo2max_garmin` with its estimate as a fallback, but a later FIT value
replaces that fallback. Tags are replaced per source on reimport; manual tags
(`is_manual = 1`) are never touched.

Sports are normalized through `hobbyjogging_core.sports`: one alias table maps
FIT sport/sub-sport pairs, Intervals type names, and manual entry to the same
canonical names, and reports/quality rules share the same sport groups. The
writer treats placeholder sports (`generic`, `other`, `unknown`) as unknown, not
as competing claims: a specific sport fills a placeholder and never conflicts
with it. Two different specific sports still become a `field_conflict`.

## Import pipeline

1. **Ingest.** FIT files are parsed from the archive; Intervals.icu activities,
   wellness, and events are fetched from the API. Raw payloads are stored in
   `source_records` keyed by `(source, record_type, external_id)`.
2. **Match.** A FIT session is matched to a canonical activity by temporal
   overlap; ambiguous one-to-many matches are queued, not guessed. Intervals
   matches by external id, then temporally.
3. **Write with owner-based precedence.** There is no per-source priority:
   - manual field → never written;
   - same source reimporting → refreshes its own field;
   - first owner keeps a field while other sources agree within tolerance
     (about 1%, with 2 s / 2 bpm / 10 m floors; 15 s for start times);
   - a meaningful cross-source disagreement changes nothing and is recorded as
     a `field_conflict` review item;
   - an explicit trusted re-import (`force=True`, triage `(t)`) takes
     ownership of non-manual fields.
   Conflict-tracked fields are durations, distance, average HR, start
   time/date, timezone offset, sport, and training load. Subjective fields
   keep their owner silently.
4. **Quality rules.** Canonical values are checked for zero duration, missing
   distance for pace sports, and implausible implied pace; findings are queued.
5. **Record.** Every run is an `import_runs` row; review items are idempotent
   by fingerprint and supersede older items when the underlying conflict
   changes.

### Garmin Personal API fetch

The official Personal API is the automated source for original FIT files; it
is implemented in `hobbyjogging-import` as `garmin fetch`.

- The API key lives in `.env` (`GARMIN_PERSONAL_API_KEY`, with `GARMIN_API_KEY`
  as fallback), valid for 30/90/180/365 days. Each run exchanges it for a 24 h
  bearer token (cached at
  `~/.config/garmin/connect-personal-api-bearer-token.json`); there are no
  refresh tokens, so a 401 re-obtains the token.
- `garmin fetch [--since DATE] [--to DATE] [--days N] [--limit N] [--force]
  [--fit-dir PATH] [--dry-run]` lists activities (paged) and downloads the
  original file via `/download-service/files/activity/{id}` (a ZIP containing
  the FIT), extracts it atomically into the FIT archive, and records a
  `source_records` manifest (`source = "garmin"`, `record_type =
  "activity-file"`). The existing FIT importer then ingests the files; there is
  no separate write path.
- API-downloaded FITs are byte-identical to the GDPR archive export (verified
  on four activities in November 2026). Garmin VO2max is still in the FIT as
  undocumented message 140, field 7 (`raw * 3.5 / 65536`), so the FIT is the
  VO2max source; the JSON summary's `vO2MaxValue` is null.

### Runalyze enrichment

Runalyze is an enrichment source, not an activity source. The API provides
comments, tags, gear, and the Runalyze VO2max estimate; it is never used for
timing or distance.

- Rows are matched to existing activities temporally (Runalyze exposes no
  Garmin activity id) and stored as `source_records` with
  `external_id = runalyze:<id>`; unmatched rows create a canonical activity
  (decision: keep the history complete).
- Comments merge into `activities.description` (empty → other; contains →
  longer; otherwise join in a stable order), idempotently and without taking
  ownership of the field.
- Tags land in `activity_tags`; gear is upserted into `equipment` and linked via
  `activity_equipment` (first shoe/bike item primary, rest secondary), with
  canonical types derived from Runalyze's equipment-categories endpoint.
- `activities.vo2max_runalyze` stores the effective estimate; `0` /
  `use_vo2max=false` means missing. Runalyze may also fill an empty
  `vo2max_garmin`; the raw payload keeps the variants.

## Review workflow

Review categories: `ambiguous_match`, `field_conflict`, `quality`,
`duplicate`, `manual_flag`.

- `review list`, `show`, `resolve`, `ignore`, `flag`, `scan` — non-interactive
  queue management and backfill.
- `review edit` — manual values (`duration`, `distance`, `sport`), written as
  manual overrides and followed by a quality re-check.
- `review exclude` / `review restore` — durable soft delete of an activity and
  its source records, or undo.
- `review triage` — interactive walk with per-item decisions committed
  immediately: inspect, open every linked activity (`o`), copy the Intervals
  or Garmin Connect URL (`ci`/`cg`), edit, pick a conflicted value (`v`),
  force re-import one Intervals activity (`t`), exclude, resolve, ignore,
  note, link an ambiguous candidate, skip, quit. `review show` prints the same
  links.
- Review items dedupe by `(category, fingerprint, activity_id)`; the source
  record stays on the item for provenance but is not part of the fingerprint.

Reports hide activities with open review items by default (`--include-review`
shows them); excluded activities never appear. The queue is the quality gate:
an unresolved conflict or finding means the displayed numbers are not yet
trusted.

## Report and view layer

The rule is **compute → render**:

1. `sources/` fetches canonical data for a date range through `DataSource`.
2. `analysis.py` / `series.py` compute derived metrics and return typed
   results (`model.py`), with no formatting and no I/O.
3. Renderers turn those results into output:
   - Markdown reports for the terminal (`daily.py`, `period_report.py`,
     `subt_report.py`, `activity_list.py`, `mdpretty.py`);
   - matplotlib figures (`charts.py`, saved as files);
   - static HTML dashboard pages (planned);
   - JSON for LLM bundles or future clients (planned).

Charts consume prepared series and return figures; they never read the
database or parse report text. Adding a report means adding analysis plus a
renderer, not a new data path.

### Dashboard (planned)

Static-first, generated on the homelab:

- Self-contained HTML with embedded SVG charts and plain tables; no SPA, no
  client-side data fetching.
- Initial views: weekly overview (load, volume/time, zone mix, plan vs actual,
  last 14 days), activity list, activity detail, data-health summary.
- Every page carries a generation timestamp and a data-health banner (open
  review items, exclusions, missing data).
- Generation writes to a temporary directory and atomically swaps, so a
  partially written dashboard is never served.
- Interactivity (filters, drill-down) is deferred until the static views are
  proven; server-rendered HTML over the same view models is the upgrade path.

### LLM coaching export (planned, lower priority)

A deterministic, diffable bundle generated from the same view models:

- athlete goals and constraints, planned events, recent load and recovery
  trends, weekly volume/time by zone, key sessions;
- explicit caveats: open conflicts, exclusions, missing HR/GPS;
- compact JSON facts plus a short markdown digest, bounded in size and
  reproducible for a given date range.

Coaching is an ongoing conversation, so the bundle will also include a small
append-only decision log (recommendation, decision, followed or not) to give
continuity across sessions. Export is intentionally deferred behind the
dashboard: the view models make it cheap to add later.

## Status (November 2026)

- Canonical pipeline, review workflow, manual editing, and exclusion: done.
- Sources: FIT archive, Intervals.icu, and the Garmin Personal API fetch are
  implemented; schema v5 adds the two VO2max owners and activity tags.
- Reports: Markdown reports, charts, and the activities table; the report code
  is split per report. The static dashboard is the next build.
- The review queue still contains warnings the user chose to leave. Reports
  hide flagged activities by default (`--include-review` shows them).
- Remaining: Runalyze enrichment (API details), homelab cutover.

## Deployment

- **Sync job** on the homelab: Garmin fetch, Intervals incremental import,
  FIT archive scan, Runalyze enrichment, review scan, then dashboard
  regeneration. One command, idempotent, prints a diff summary (new activities,
  changed fields, new conflicts, new findings).
- **Static serving** via Caddy or nginx; regeneration triggered by the sync
  job, not per request.
- **Refresh**: wall screens use meta-refresh; phones reload manually.
- **Backups**: periodic `sqlite3 .backup` or Litestream; the database is the
  only irreplaceable artifact.
- **Database placement**: local disk on the homelab. Do not share SQLite over
  NFS/SMB.
- **Roles**: read-only connections for the app/report layer; writes only from
  the import and review CLI.

## Non-goals and deferred work

- No pandas; matplotlib only.
- No SPA or client-side analytics framework.
- No phone interactivity for now.
- No direct remote database access; clients read rendered pages.
- Generic CSV import remains optional/deferred. Runalyze is covered by its API,
  not by CSV.
- The Runalyze Garmin-id gap means matching stays temporal; exact linking can
  be added if Runalyze ever exposes the external activity id.

## Working conventions

- Package-scoped changes happen in package sessions; cross-package contracts,
  schema, and architecture happen at the repo root. Details in `AGENTS.md`.
- Tests are `unittest` (pytest is not installed) and run per package from its
  tests directory. All three suites must stay green for cross-package changes.
- Commits follow session scope; the user pushes manually.
