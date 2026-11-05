# Next up: import package

Handoff from the root architecture session. Delete or rewrite this file when
the tasks are done.

## Context

- Canonical DB at `HOBBYJOGGING_DB` (schema v4). Owner-based field precedence
  is in place; cross-source disagreement becomes a `field_conflict` review
  item (see `docs/ARCHITECTURE.md`).
- The full FIT archive import is complete: the archive holds 2,839 activity
  files and all are imported (plus 2 excluded). No missing FIT activities.
- Recent commits: `93488b6` (shared sport vocabulary), `dab0e10`
  (owner-based conflicts), `370b883` (architecture docs).
- Key files: `quality.py`, `fit_import.py`, `cli.py`, `intervals.py`,
  `matching.py`, `values.py`.

## Task 1 — fix duplicate quality review items

`record_quality_findings` includes `source_record_id` in the fingerprint,
while `review scan` / `refresh_activity_quality` use `None`. The same finding
is recorded twice.

- Drop `source_record_id` from the quality fingerprint; keep it on the item
  for provenance.
- Update/add tests (scan item + import item for the same finding dedupe).
- Existing duplicates on the real DB are left for triage.

## Task 2 — Garmin fetch command

Use the official Garmin Connect Personal API. The key is in `.env` as
`GARMIN_PERSONAL_API_KEY` (valid 365 days).

- Token: `POST https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token`
  with `Authorization: ApiKey <key>` → bearer token. Tokens last 24 h, no
  refresh tokens; re-obtain on 401.
- Activity list (paged):
  `GET /activitylist-service/activities/search/activities?start=&limit=&startDate=&endDate=`
- Original file: `GET /download-service/files/activity/{id}` → ZIP bytes
  containing the FIT.
- Prefer Garmin's official Python client (`garmin_personal_api`,
  `garmin/connect-personal-api-python`); keep auth and HTTP injectable for
  tests.
- Command: `hobbyjogging-import garmin fetch --since DATE`
  - downloads missing FITs into `HOBBYJOGGING_FIT_DIR`, extracts them
  - records a fetch manifest and skips known activity ids
  - the existing FIT importer ingests the files; reuse `fit_import`, do not
    duplicate parsing/import logic.
- Tests: fake client, no network, idempotent re-fetch, 401 → new token.
- Verify one API-downloaded FIT against a manually exported FIT; note any
  fields Garmin strips.

## Done when

- Both fixes have tests and the package suite is green.
- A `garmin fetch --dry-run`-style path is testable without network.
- Report: files changed, tests run, decisions/risks. Do not run against the
  real database.
