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
        FIT archive                Intervals.icu API
             |                            |
             +-------------+--------------+
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
- **Clients**: browsers only. No database credentials, no JavaScript
  framework, no write access.
- **Access**: private network (Tailscale/WireGuard) or basic auth at the
  reverse proxy. Health data is not exposed publicly.

## Packages

The repo is a uv workspace with three packages.

### `hobbyjogging-core`

Canonical model, schema, and read/write access.

- `model.py` — `Activity`, `Lap`, `Interval`, `WellnessDay`, `Event`,
  `Equipment`, zone models.
- `db/schema.py`, `db/migrations.py` — SQL schema and forward-only migrations
  (`SCHEMA_VERSION`).
- `db/writer.py` — `TrainingWriter`: import runs, source records, activity
  upserts, field provenance, manual edits, exclusions, review items, laps,
  intervals, zone times.
- `db/repository.py` — `TrainingRepository`: read queries over the canonical
  model.
- `datasource.py` — the `DataSource` protocol every report consumer depends
  on.
- `db/connection.py` — database path resolution and connection setup.

Core owns the rules that must not drift between packages: field ownership,
conflict detection, exclusion semantics, review-item fingerprints.

### `hobbyjogging-import`

Source ingestion and the review queue.

- `fit.py` — FIT parsing and normalization (the only module that knows raw FIT
  field names).
- `fit_import.py` — file discovery, matching, activity/lap persistence.
- `client.py`, `intervals.py` — Intervals.icu API access and import.
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
- `reports.py`, `summary.py`, `report_commands.py` — markdown report builders.
- `charts.py`, `chart_commands.py` — matplotlib figures over prepared series.
- `format.py`, `mdpretty.py` — human formatting for the terminal.
- `commands.py`, `cli.py`, `__main__.py` — command registry and entry point.

The long-term dashboard is a new renderer in this package, not a new analytics
implementation.

## Canonical data model

SQLite, forward-only migrations. Schema version 4 at the time of writing.

- `activities` — canonical values: dates, sport, name, description, duration,
  elapsed, distance, heart rate, training load, subjective fields, exclusion
  timestamp.
- `source_records` — raw imported payloads with checksums and provenance
  (`source`, `record_type`, `external_id`, `raw_path`, `payload_json`,
  exclusion timestamp).
- `activity_sources` — links between canonical activities and source records,
  including match method, confidence, and primary flag.
- `activity_field_sources` — per-field provenance: which source wrote a value,
  the value it wrote, and whether it is a manual override.
- `activity_laps`, `activity_intervals`, `activity_zone_times` — detail data
  attached to activities, tagged by source record.
- `wellness_days`, `events`, `equipment`, `equipment_source_links`,
  `zone_configs` — supporting canonical data.
- `import_runs` — one row per import with parameters and outcome.
- `review_items` — the review queue: category, severity, detail, context,
  fingerprint, status, resolution note, activity/source links.

Two invariants are enforced by the writer:

- A manual field (`is_manual = 1`) is never overwritten by an import.
- An excluded activity cannot be written to or linked to.

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
     a `field_conflict` review item.
   Conflict-tracked fields are durations, distance, average HR, start
   time/date, timezone offset, sport, and training load. Subjective fields
   keep their owner silently.
4. **Quality rules.** Canonical values are checked for zero duration, missing
   distance for pace sports, and implausible implied pace; findings are queued.
5. **Record.** Every run is an `import_runs` row; review items are idempotent
   by fingerprint and supersede older items when the underlying conflict
   changes.

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
  immediately: inspect, open in Intervals, copy URL, edit, pick a conflicted
  value (`v`), exclude, resolve, ignore, note, link an ambiguous candidate,
  skip, quit.

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
   - markdown reports for the terminal (`reports.py`, `mdpretty.py`);
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

## Deployment

- **Sync job** on the homelab: Intervals incremental import, FIT archive scan,
  review scan, then dashboard regeneration. One command, idempotent, prints a
  diff summary (new activities, changed fields, new conflicts, new findings).
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
- CSV import and the Runalyze adapter remain deferred (see ROADMAP).

## Working conventions

- Package-scoped changes happen in package sessions; cross-package contracts,
  schema, and architecture happen at the repo root. Details in `AGENTS.md`.
- Tests are `unittest` (pytest is not installed) and run per package from its
  tests directory. All three suites must stay green for cross-package changes.
- Commits follow session scope; the user pushes manually.
