# Next up

The three commits that finish the review/edit workflow, then real-data verification.

## Commit 1 — schema v4 + durable soft delete

- Columns `activities.excluded_at`, `source_records.excluded_at`.
- "Delete" in the review queue = exclusion: the activity and all its linked source records are
  marked, open review items are resolved with a `triage: excluded` note.
- Reports/repository reads filter `excluded_at IS NULL`; FIT and Intervals importers skip
  excluded source records and never match into excluded activities; the writer refuses to
  write into an excluded activity.
- Result: deleted data stays deleted across reimports, with the rows kept for audit;
  CLI twins `review exclude <activity> [--note]` / `review restore <activity>` are included.

## Commit 2 — manual edit

- Writer methods `set_manual_field` / `clear_manual_field`; a manual write also records
  `activity_field_sources(source='manual', is_manual=1)` so no reimport can overwrite it.
- Value parsers: duration `46:20`, `1:02:03`, plain seconds; distance `8.2km`, `8200m`;
  sport validated against the canonical set. Editable fields: `duration_s`, `distance_m`,
  `sport` (several flagged items are mislabeled walks/rides — sport is the honest fix).
- CLI: `review edit <activity> [--duration …] [--distance …] [--sport …] [--resolve]`.
- Refactor the quality re-run so `review scan --activity` and the queue share one function;
  after an edit the activity is re-checked and the result printed.

## Commit 3 — `review triage`

Interactive walk over open review items:

```
Review 1/9  warn  quality  2019-01-30  Run  (no timing data: duration is 0 s)
  fit:2019-01-30_18-02-00.fit  → activity 5d459fa1
  (i)nspect  (o)pen  (c)opy URL  (e)nter valid time  (d)elete  (r)esolve
  (x)ignore  (n)ote  (s)kip  (h)elp  (q)uit > _
```

- `o` opens `https://intervals.icu/activities/<external_id>` in a browser; `c` copies it
  (wl-copy, xclip/xsel fallback; URL always printed). Ambiguous items get `1`–`9` to pick a
  candidate and link it.
- Every action commits immediately; `q`/Ctrl-C end with a summary. Input/output and the
  browser/clipboard calls are injectable so the loop is testable.
- `review show` gets the activity timing/distance enrichment while we're in there; README
  documents the whole workflow.

## Commit 4 — no automatic source priority

A real import overwrote values the user had corrected in Intervals. Fix: the writer no longer
ranks sources.

- `upsert_activity` returns `FieldConflict` objects instead of applying a priority table.
  Manual fields are never written; a source refreshes its own fields; the first owner keeps a
  field when another source agrees within tolerance; a meaningful disagreement changes nothing
  and becomes a `field_conflict` review item.
- Conflict-tracked fields: durations, distance, average HR, start time/date, timezone offset,
  sport, training load. Subjective fields keep their owner silently.
- `record_field_conflicts` is idempotent by fingerprint; changed conflicts supersede their
  older open item. Triage gains `(v) pick value` (choose current vs incoming), which applies
  the choice as a manual value so reimports cannot re-open it.

## Garmin VO2max — root-session handoff

Verified 2026-11-05: the Personal API activity FIT is byte-identical to the
GDPR archive copy (4/4 activities tested), and Garmin VO2max is still inside
it as undocumented message 140, field 7 (`raw * 3.5 / 65536`). It is present
in 2,836 of 2,839 archive activity files and in every API file tested. The
JSON activity summary's `vO2MaxValue` is null; the separate type-44
`max_met_data` files are an integer-only copy and are not exposed by the API.
Do not add a JSON or companion-file path for VO2max.

Core work (root session, before the import package consumes it):

- Schema v5: `activities.vo2max_garmin REAL`,
  `activities.vo2max_runalyze REAL`, plus `activity_tags` (activity, tag,
  source, source_record_id, is_manual).
- Writer: both columns in `ACTIVITY_COLUMNS`, neither in
  `CONFLICT_FIELDS`; FIT writes only `vo2max_garmin`, Runalyze writes only
  `vo2max_runalyze` and fills `vo2max_garmin` only when it is NULL; manual
  wins per field; same-source reimport refreshes.
- Tags: replace a source's tags on reimport, never touch `is_manual = 1`.
- Model/repository/datasource: expose both VO2max values and tags.
- Tests: migration, independent owners, tags replace.

Then in the import package: parse `unknown_140` in `fit.py`, write
`vo2max_garmin` from `fit_import.py`, and report VO2max coverage in the FIT
summary. Backfill by re-running the normal full archive import; it is
checksum-idempotent.

## Current priorities

1. **Full FIT archive import** on the real DB. The archive holds ~64k files,
   2.8k of them activity recordings. One run (date filters apply after
   parsing, so batching does not help). Re-run after the parser writes
   `vo2max_garmin`.
2. **`garmin fetch`** in the import package: Garmin Personal API key → 24 h
   bearer token, paged activity list, original FIT ZIP download, extract into
   the archive, manifest/dedupe. API files are currently byte-identical to
   the archive, so no separate VO2max JSON path.
3. **View models + static weekly dashboard** in the reports package.
4. **Runalyze enrichment** after schema v5: comments merged into
   `description`, tags in `activity_tags`, gear via the
   equipment-categories endpoint, and Runalyze's own `vo2max_runalyze`
   estimate. Unmatched rows create activities.

Still open: Runalyze API auth/endpoint details, homelab cutover.
