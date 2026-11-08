# Roadmap

Where the hobbyjogging monorepo is heading, stage by stage.

## 1. Canonical pipeline — done

One SQLite database is the single ground truth for all training data. FIT
archives, Intervals.icu, and the Garmin Personal API import into a canonical
activity model; activities from different sources are unified when they overlap
in time, so one forest run can carry GPS/HR data from a FIT file and subjective
data (RPE, feel, training load) from Intervals. There is no automatic
per-source field priority: the first owner keeps a field, and any cross-source
disagreement is queued for a human decision, except that Intervals owns moving
and elapsed time. The raw source records are kept as provenance next to the
canonical values.

The review mechanism is in place: suspicious data (zero durations, absurd
paces, ambiguous matches, field conflicts) is recorded as review items, and
reports hide flagged activities until they are handled.

## 2. Review & editing — done

- An interactive triage walk: inspect, open the Intervals/Garmin activity,
  copy links, fix a value, pick a conflicted value, force re-import Intervals,
  or permanently discard a bad activity.
- Manual edits that outrank every import source and survive reimports.
- Durable deletion as exclusion, so bad data disappears from reports without
  resurrecting itself on the next import.
- Activity linking and ambiguous matches resolved through the queue.

The database is now trustworthy enough to build on.

## 3. Dashboard — next

Static-first, generated on the homelab and served read-only:

- view models over the same analysis layer the Markdown reports use;
- weekly overview (load, volume/time, zones, plan vs actual, data health),
  activity list, and activity detail;
- self-contained HTML + SVG, generation timestamp, atomic swap;
- Markdown reports remain the terminal view; no SPA or phone interactivity.

## 4. More sources

- **Garmin Personal API fetch** — done. Official API, original FIT files into
  the archive, fetch manifest, VO2max from FIT message 140.
- **Runalyze enrichment** — next. Comments merged into `description`, tags in
  `activity_tags`, gear via the equipment-categories endpoint, and
  `vo2max_runalyze`. Enrichment only — never timing or distance. Unmatched rows
  create activities so old history stays complete.
- **CSV import** — optional/deferred. Third-party exports that are neither FIT
  nor Intervals, ingested through the same owner/conflict review rules.

## 5. Later ideas

- equipment/shoe mileage tracking from the canonical distance data
- wellness data (HRV, sleep) in recovery views
- training-load charts that treat all sources uniformly
- a small web or TUI front end over the reports
- a deterministic LLM coaching bundle built from the dashboard view models

## Principles that hold across all stages

- **The DB is the truth; every importer is replaceable.** Reimporting anything
  is safe and idempotent; manual data always wins over imported data.
- **Ingestion writes, reports read.** Reports and charts only ever see
  canonical model objects, never source-specific shapes — adding a source never
  changes a report.
- **Doubtful data is surfaced, never silently mixed in.** Anything the rules
  flag waits in the review queue; reports exclude open items but never churn
  because of them.
- **Terminal-first, matplotlib-only, no heavyweight deps.**
