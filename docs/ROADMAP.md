# Roadmap

Where the hobbyjogging monorepo is heading, stage by stage.

## 1. Canonical pipeline — done

One SQLite database is the single ground truth for all training data. FIT archives and
Intervals.icu import into a canonical activity model; activities from different sources are
unified when they overlap in time, so one forest run can carry GPS/HR data from a FIT file and
subjective data (RPE, feel, training load) from Intervals. There is no automatic per-source
field priority: the first owner keeps a field, and any cross-source disagreement is queued for
a human decision; the raw source records are kept as provenance next to the canonical values.

A first review mechanism exists: suspicious data (zero durations, absurd paces, ambiguous
cross-source matches) is detected by a rule set and recorded as review items; reports hide
activities with open items until they are handled.

## 2. Review & editing — current stage

Make the review queue actually workable and make manual corrections a first-class citizen:

- an interactive queue walk for ticking through review items: inspect, open the matching
  activity in a browser, fix a wrong value, or permanently discard a bad activity
- manual edits that outrank every import source and survive reimports
- durable deletion as exclusion, so bad data disappears from reports without resurrecting
  itself on the next import
- activity linking resolved through the queue instead of manual SQL

After this stage, the database becomes trustworthy enough to build on.

## 3. More sources — next

- **CSV import** (deferred until the review/edit workflow is solid): third-party exports that
  are neither FIT nor Intervals, ingested through the same owner/conflict review rules.
- **Runalyze adapter**: the last big source (years of history in a system without usable
  bulk export). Blocked on export/API access; once available it plugs into the same
  canonical model, matching, and review machinery as everything else.

## 4. Later ideas

- equipment/shoe mileage tracking from the canonical distance data
- wellness data (HRV, sleep) in recovery views
- training-load charts that treat all sources uniformly
- a small web or TUI front end over the reports

## Principles that hold across all stages

- **The DB is the truth; every importer is replaceable.** Reimporting anything is safe and
  idempotent; manual data always wins over imported data.
- **Ingestion writes, reports read.** Reports and charts only ever see canonical model
  objects, never source-specific shapes — adding a source never changes a report.
- **Doubtful data is surfaced, never silently mixed in.** Anything the rules flag waits in
  the review queue; reports exclude open items but never churn because of them.
- **Terminal-first, matplotlib-only, no heavyweight deps.**
