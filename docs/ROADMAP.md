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
and elapsed time, and average-HR differences only count beyond 5 bpm. The raw
source records are kept as provenance next to the canonical values.

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

## 3. Dashboard — done (first static version)

Static-first, generated on the homelab and served read-only:

- view models over the same analysis layer the Markdown reports use;
- weekly overview (load, volume/time, zones, plan vs actual, data health),
  recovery and health, activity list, activity detail, selected Markdown
  reports;
- self-contained HTML with bundled plotly charts, generation timestamp, and
  atomic swap;
- Markdown reports remain the terminal view; no SPA or phone interactivity.

Follow-ups: expose the review queue through `DataSource`, add race cards and
session-level planned-vs-actual views, and keep the dashboard generation in the
sync job as those views grow.

## 4. More sources

- **Garmin Personal API fetch** — done. Official API, original FIT files into
  the archive, fetch manifest, VO2max from FIT message 140.
- **Runalyze enrichment** — next. Comments merged into `description`, tags in
  `activity_tags`, gear via the equipment-categories endpoint, and
  `vo2max_runalyze`. Enrichment only — never timing or distance. Unmatched rows
  create activities so old history stays complete.
- **Historical spreadsheet import** — done. `hobbyjogging-import sheet`
  ingests the hand-maintained `.ods` log (`Rohdaten`, `Alternativtraining`,
  `Material`) with German column mapping, minute-precision start times,
  equipment links, and the same owner/conflict review rules. The ODS reader
  uses only the standard library.
- **CSV import** — optional/deferred. Third-party exports that are neither FIT
  nor Intervals, ingested through the same owner/conflict review rules.

## 5. Race tracking & reports

Turn planned races into a first-class part of the record:

- store race metadata on events (Intervals `category`/priority, goal time and
  distance) and race results (official time, placing, participants,
  conditions);
- link a planned race event to the completed activity so plan and execution
  sit side by side;
- sources: Intervals race categories, Runalyze `race_result`, and manual entry
  for older races;
- reports: an upcoming-race calendar with countdown, a past-results table, and
  a race-day report (pacing, HR/zone execution vs plan, splits);
- dashboard: a races card and race-detail page.

## 6. Later ideas

- equipment/shoe mileage tracking from the canonical distance data
- wellness data (HRV, sleep) in recovery views
- training-load charts that treat all sources uniformly
- a small web or TUI front end over the reports
- a deterministic LLM coaching bundle built from the dashboard view models

## Principles that hold across all stages

The durable rules live in one place: the seven principles in
[ARCHITECTURE.md](ARCHITECTURE.md#principles). In short — three roles (importers
write facts, maintenance writes derived values, reports compute on read),
placement follows cost, the database is the truth, delete is exclusion,
compute → render, source-independent reads, reproducible output.

This roadmap only stages the work that follows from them.
