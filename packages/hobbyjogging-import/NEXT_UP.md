# Next up: import package

Handoff from the root architecture session. Both original tasks are done;
this file now tracks the remaining real-data steps.

## Done

- **Quality review dedupe.** Quality fingerprints no longer include
  `source_record_id`, and `TrainingWriter.record_review_item` dedupes by
  `(category, fingerprint, activity_id)`. The source record stays on the item
  for provenance. Tests cover an import finding and a later `review scan`
  finding the same issue.
- **`garmin fetch`.** Personal API client with shared bearer-token cache,
  paged activity list, ZIP download, atomic FIT extraction into
  `HOBBYJOGGING_FIT_DIR/garmin`, a `source_records` manifest, `--dry-run`,
  `--limit`, `--force`, `--fit-dir`, and `--since`/`--to`/`--days`.
- **Garmin VO2max.** `fit.py` reads undocumented message 140 field 7
  (`raw * 3.5 / 65536`) into `FitSession.vo2max_garmin`; `fit_import.py`
  writes `vo2max_garmin` at full precision; the FIT summary reports coverage.
- Tests: import 160, core 79, reports 188 (all green).

## Remaining (real data, user)

1. Re-run the normal full archive import against the real DB:
   `hobbyjogging-import fit` (no batching; ~2.8k activity files). Expect
   `vo2max_garmin` on roughly 2,836 activities.
2. Spot-check one value against Garmin Connect (the watch shows two
   decimals; the database keeps the raw precision).
3. Run `garmin fetch --dry-run`, then a small real fetch, then
   `hobbyjogging-import fit --recursive` over the archive.
4. Later: Runalyze enrichment writes `vo2max_runalyze` and tags.

## Notes / risks

- Message 140 is undocumented; Garmin can strip it. The VO2max line in the
  FIT import summary is the early warning.
- The Personal API activity FIT is byte-identical to the GDPR archive copy
  (4/4 activities tested in November 2026). The JSON `vO2MaxValue` is null;
  the type-44 `max_met_data` files are not needed.
- The manifest is a bandwidth optimization. The FIT importer is
  checksum-idempotent, so a redownload does not duplicate source records or
  laps.
- One core change was needed for task 1: the review-item dedupe query no
  longer includes `source_record_id`. The v5 schema came from the root
  session.
