# Next up: import package

This file records what was completed and what the package is still waiting
on.

## Done

- **Quality review dedupe.** Quality fingerprints no longer include
  `source_record_id`; `record_review_item` dedupes by
  `(category, fingerprint, activity_id)`. The source record stays on the item
  for provenance.
- **`garmin fetch`.** Personal API client with shared bearer-token cache,
  paged activity list, ZIP download, atomic FIT extraction into
  `HOBBYJOGGING_FIT_DIR/garmin`, a `source_records` manifest, `--dry-run`,
  `--limit`, `--force`, `--fit-dir`, and `--since`/`--to`/`--days`.
- **Garmin VO2max.** `fit.py` reads undocumented message 140 field 7
  (`raw * 3.5 / 65536`) into `FitSession.vo2max_garmin`; `fit_import.py`
  writes `vo2max_garmin` at full precision; the FIT summary reports coverage.
- **Intervals plan horizon.** Planned calendar events are fetched through
  `max(--to, today + --plan-days)` (default 182 days); activities and wellness
  keep the original range.
- **Triage links.** `o` opens every available link; `ci` copies the Intervals
  URL and `cg` the Garmin Connect URL (resolved from the fetch manifest by
  file path, then by start-time match). `review show` prints both.
- **Time fields.** Intervals `moving_time` is stored as `moving_s` (recording
  time stays `duration_s`); FIT `total_moving_time` is parsed when present.
  Planned events get `duration_s` from `moving_time` and `training_load` from
  `icu_training_load`. The `moving_time_mismatch` quality rule flags a gap
  larger than `max(10 min, 25% of recording)`.
- **Triage Intervals re-import.** `(t)rust Intervals` re-fetches one linked
  activity with `force=True`: Intervals takes ownership of non-manual fields,
  conflicts on those fields resolve, and quality rules re-run.
- **Recording-time duration.** Intervals `duration_s` now uses
  `icu_recording_time` (falling back to `moving_time`). A duration difference
  within either source's pause gap is agreement, so Garmin/Intervals stop-time
  accounting no longer creates review items.
- **No-distance sports.** The writer forces canonical distance to zero for
  `treadmill_run`, `virtual_run`, `soccer`, `racket`, `training`, `other`, and
  `workout`; manual distance wins, and the quality rules skip
  `zero_distance` for them.
- **Planned-events sync.** `events sync` and the regular Intervals import
  reconcile planned events: fields are replaced (including NULLs), events
  that disappeared are soft-excluded, returning events are revived,
  manual/other-source events are untouched, and the summary reports
  fetched/new/updated/unchanged/removed/revived/skipped. `--dry-run` writes
  nothing.
- **Planned-event zone times (schema v8).** Event sync parses
  `workout_doc.zoneTimes` (`Z1`–`Z7`, `SS`, zero seconds kept), infers
  `zone_kind` from the dominant step target (`pace`/`hr`/`power`) or the
  sport's natural kind, and writes via `set_event_zone_times`. An event
  without a workout document clears its kind and rows. A zone-only change
  counts as `updated`. `events backfill-zones [--dry-run]` repairs stored
  events from their saved Intervals payloads without network access and is
  idempotent.
- **Incremental `sync`.** Runs Garmin fetch, Intervals import, FIT archive
  import with `skip_known`, and the shared quality scan. `--no-*` flags skip
  sources, `--full` reimports all FIT paths, failures are reported per source
  and the command exits non-zero after continuing with the rest. The scan core
  is shared with `review scan`.
- **Field-conflict prune.** `review prune [--dry-run]` resolves open field
  conflicts whose recorded values now agree under the current core
  tolerances. FIT/Intervals reimports also resolve a field's old conflict
  automatically when that field agrees again.
- **Conflict causes and bulk triage.** New `field_conflict` items carry a
  `cause`/`cause_note` computed from the stored source summaries (`causes.py`).
  Advisory causes (`elapsed_definition`, `moving_estimate`, `small_difference`,
  `start_offset`) are `info`; the rest stay `warn` and need a per-activity
  decision. `review causes`, `review classify [--dry-run]`, `--cause` filters
  on `list`/`triage`, and `review resolve --cause <cause> [--dry-run]` support
  the workflow.
- Full FIT archive import and VO2max backfill have been run against the real
  DB.

## Next task: .ods spreadsheet import

Import the historical training log from `data/laufen.ods` (gitignored user
data; tests must use synthetic `.ods` fixtures). No schema changes: max HR,
ascent, cadence, contact time, temperature, weight, and links stay in
`source_records.payload_json`.

### Scope

Import these sheets:

- `Rohdaten` — historical runs (2,042 rows, from 2011).
- `Alternativtraining` — cross-training (256 rows).
- `Material` — shoes/gear (15 rows).

Skip `Leistungstests` / `Leistungstests_Graph` (race results/time trials),
`7Tage`, `28Tage`, `Monatsbilanz`, `Strecken`, `Trainingsbereiche`, and
`Läufe_Graph`.

### ODS reader

Add `ods.py` using only the standard library (`zipfile` +
`xml.etree.ElementTree`), no new dependency:

- read `content.xml`, list `table:table` sheets by name;
- expand `table:number-columns-repeated` and
  `table:number-rows-repeated`, but skip trailing empty repeats and cap
  expansions (LibreOffice pads sheets to ~1M rows);
- handle `table:covered-table-cell` (merged cells) and typed values:
  `office:value-type` `float`/`percentage`/`currency`/`date`/`time`/`boolean`/
  `string`, using `office:value`, `office:date-value`, `office:time-value`,
  and cached formula values;
- return `headers + rows` with cell positions preserved; trim trailing empty
  columns/rows.

ODS time values are ISO durations (`PT11H30M00S`, fractional seconds
possible), not clock strings. Dates are `YYYY-MM-DD`.

### Import

Add `sheet.py` / `sheet_import.py` and a CLI:

```bash
hobbyjogging-import sheet data/laufen.ods --sheet Rohdaten
hobbyjogging-import sheet data/laufen.ods --sheet Alternativtraining
hobbyjogging-import sheet data/laufen.ods --sheet Material
hobbyjogging-import sheet data/laufen.ods --sheet Rohdaten --dry-run
hobbyjogging-import sheet --inspect data/laufen.ods   # list sheets/headers
```

Options: `--sheet NAME`, `--timezone` (default `Europe/Vienna`), `--from`/
`--to`, `--limit`, `--dry-run`, `--database`.

**Rohdaten mapping**

| Sheet column | Canonical |
|---|---|
| `Datum` | `local_date` |
| `Datum` + `Startzeit` | `started_at_utc` + `tz_offset_min` (Europe/Vienna) |
| `Distanz in m` | `distance_m` |
| `Zeit` | `duration_s` |
| `d. Hf` | `avg_hr` |
| `Strecke` | `name` |
| `Beschreibung` | `description` |
| `Trainigstyp`, `Trainingsgebiet` | `activity_tags` (source `sheet`) |
| `Schuhe` | equipment link by name |

- `sport='run'`; `Startzeit` missing → store `local_date` only and create
  (no temporal match).
- Raw row JSON goes to `source_records.payload_json`; keep max HR, ascent,
  cadence, contact time, oscillation, temperature, meters/beat, and gmap link
  there.
- Ignore `/`, `N/A`, `#REF!`, and empty strings as missing.

**Alternativtraining mapping**

- `Datum` + `Uhrzeit` → date/start (Europe/Vienna).
- `Was` → sport: `Kicken` → `soccer`, `Badminton` → `racket`, else `other`
  (extend the alias map as needed).
- `Zeit` → `duration_s`, `Distanz` → `distance_m` (verify units),
  `Puls Durchschnitt` → `avg_hr`, `Beschreibung` → description.
- Raw row JSON in `source_records`.

**Material mapping**

- Upsert `equipment` keyed by the sheet id; parse `Kaufdatum` and
  `Entsorgungsdatum` (`D.M.YYYY`), brand/type/name, and notes.
- Store size/price/`gesamt km` in `equipment.notes` (mileage is derived from
  linked activities, not stored as a target).
- Link `Rohdaten.Schuhe` to equipment by name.

**Core prerequisite:** the writer currently has no `upsert_equipment` /
`link_activity_equipment` methods (tables exist). That is a small core
addition with no schema change; do it in a root session first, or coordinate
before touching core.

### Idempotency and precedence

- `source='sheet'`; `record_type='activity'` / `'equipment'`.
- Stable activity external id from date/time/route (hash fallback for
  duplicate rows); checksum over the row JSON. Reimport updates the same
  records.
- Synthesize UTC from date + time and match existing activities temporally;
  rows without a start time create a dated activity.
- Owner-based precedence applies; disagreements with FIT/Intervals become
  `field_conflict` items, manual values win.

### Tests

- ODS parser: typed cells, repeated rows/columns, trailing padding, multiple
  sheets, covered cells, cached formula values.
- Mapping: German headers, ODS date/time durations, missing markers,
  distance/HR, sport aliases, timezone.
- Import: new/matched/idempotent/dry-run/limit/from-to, conflict recording.
- Equipment: upsert, shoe links, missing ids.
- Synthetic `.ods` fixtures only; never read the real `data/laufen.ods` in
  tests.

### Docs

- Update `packages/hobbyjogging-import/README.md` with the `sheet` command and
  the German column mapping.
- Update `docs/ROADMAP.md` (spreadsheet import moved from deferred) and
  `docs/NEXT_UP.md` when it lands.

## Waiting on

- **Runalyze enrichment** (blocked on API auth/endpoint details): comments
  merged into `description`, tags in `activity_tags`, gear via the
  equipment-categories endpoint, and `vo2max_runalyze`.
- **`review scan` quality prune**: resolving stale quality items whose
  current values no longer trigger them (field conflicts are pruned; quality
  items are not yet).
- **Core tolerance / sport-alias decisions** (root session): the duration and
  avg-HR tolerances that produce the minimal FIT/Intervals conflicts, plus
  the `standuppaddling`, `openwaterswim`, and `nordicski` aliases.
- The dashboard is reports-package work.
- The planned-event zone display is reports-package work.

## Notes / risks

- Message 140 is undocumented; Garmin can strip it. The VO2max line in the FIT
  import summary is the early warning.
- The Personal API activity FIT is byte-identical to the GDPR archive copy
  (4/4 activities tested in November 2026). The JSON `vO2MaxValue` is null;
  the type-44 `max_met_data` files are not needed.
- The manifest is a bandwidth optimization. The FIT importer is
  checksum-idempotent, so a redownload does not duplicate source records or
  laps.
