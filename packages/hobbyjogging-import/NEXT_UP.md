# Next up: import package

This file records what was completed and what the package is still waiting
on.

## Done

- **Duplicate detection.** `duplicates.py` finds same-session pairs (sport/day,
  distance 2 %, duration 5 %, HR 5 bpm) and links the weaker copy; the
  maintenance recompute opens one `duplicate` item per pair. The sheet cleanup
  is a maintenance backfill, not an import write.
- **Tag lexicon and evidence proposals.** `tag_lexicon.py` maps stored tags to
  workout sets, illness/recovery, race/trail, rep lengths, area codes and
  context; the audit accounts for every tag (157 mapped / 59 unmapped on the
  real DB). `workout_sets_current` fills an empty run classification from a
  tag (`source='tag'`) or an explicit description (`source='comment'`), and
  triage `(a)ccept` writes a consistency suggestion.
- **Session metrics.** FIT, Intervals, Runalyze and sheet session averages are
  extracted into `activity_metrics` (cadence, stride, dynamics, respiration,
  power, calories, training effect, GAP, altitude), normalized to canonical
  units by `metrics.py`, and written by every importer. The FIT parser now
  keeps the averages it used to drop. `maintenance activity_metrics_v1`
  backfills the history.
- **Activity edit command.** `activity edit <id>` is the direct human write
  surface: name, description, duration, distance, sport, sub-sport, RPE, feel,
  tags, methods, targets and equipment, with `--clear`, `--dry-run`,
  `--history` and an interactive mode. It reuses `apply_manual_edit`, re-runs
  the quality rules, writes an `edit_log` row and closes the matching
  `field_conflict` / `workout_classification` item. `_VALUE_PROMPTS` moved to
  `values.py`.
- **Garmin daily wellness.** `garmin wellness` reads the Personal API's daily
  summary (resting HR, sleep seconds, steps, floors, SpO2), the HRV summary
  and the weight range, and fills only the NULL fields of a stored day. Sleep
  detail and score are not exposed and stay empty. It joins `sync` after the
  activity fetch; a missing feed is a skip with a warning. Real DB: 8 days
  read, 0 written, 8 unchanged.
- **Runalyze workout type.** `runalyze_types` maps `Jogging`/`JOG` →
  `continuous` + `base`, `Long Slow Distance`/`LSD` → `long_run` + `base`, and
  `SubThreshold`/`ST` → `intervals` + `subthreshold`, by name or abbreviation,
  case and separator insensitive. It is written on create and used by
  `workout_sets_current` as a gap-filler when the classifier and sheet have
  nothing; existing sets win and only run sports are mapped.
  `hobbyjogging-import runalyze types` audits the stored types and lists the
  unmapped ones.
- **Sync covers every configured source.** `hobbyjogging-import sync` now runs
  Garmin, Intervals, the FIT archive, a budgeted Runalyze enrichment, the
  offline gear/VO2max derivations and the newest unimported Strava export, then
  the quality scan. A source disabled in `sources.toml` or missing a credential
  is skipped with a warning instead of failing the run; a configured source
  that fails is reported and the rest still run. `sync.sh` adds the maintenance
  recomputes and the dashboard in that order. See root item 44.
- **Setup and doctor.** `hobbyjogging-maintenance init` creates and migrates a
  fresh database and the FIT directory, idempotently; `doctor` checks `uv`, the
  DB path and writability, the schema version, the FIT directory, each
  configured credential, bounded API liveness probes, pending backfills, source
  freshness and `sources.toml`, and prints the next command. See root item 23.
- **Provider device identity.** An Intervals `device_name` that names an app
  (`Runalyze`, `Garmin Connect`, `Strava`, `intervals.icu`; case and spacing
  insensitive) writes no device row and no `device_id`. A real name still fills
  the fallback `intervals:<slug>` row, whose `devices.name` is collapsed,
  title-cased and set once. A name that matches exactly one FIT device of its
  model (manufacturer plus product, separators ignored, serial present) claims
  that device instead of creating a duplicate row; two devices of the same
  model keep the provider id. `fit_import.device_id_from` now requires a
  serial, so a serial-less upload is not a device. Runalyze payloads also carry
  `device_name`, but nothing maps it to `device_id` today; a mapping would have
  to use the same resolver. `device_identity_v1` (maintenance) is the stored
  half: it re-resolves activities already on an `intervals:<slug>` row through
  this rule — 2 moved to the Enduro serial, 1 app-name fallback cleared — and
  `verify_canonical` derives the same claim, so the canonical row stays at 0
  drift. The two now-unused provider rows were soft-excluded by
  `device_identity_orphans_v1` (v24).
- **Source policy and settings view.** `sources.toml` sets enabled, create
  (`create | review | ignore` for Strava and Runalyze) and the text targets;
  `sources` prints the effective policy and `settings` renders the rules and
  payload mapping. `reports.sh settings` delegates to it. A review outcome
  queues a `create_activity` item with triage `(c)`.
- **Declared payload mapping.** `hobbyjogging_import.derive` holds the
  per-source `FIELD_MAPS` and per-sheet `SHEET_MAPS`, with named transforms
  for units, sports, dates and the device id. Contract tests compare each map
  with its importer (Intervals, FIT, Runalyze, both sheet worksheets).
- **Triage force records an owner patch.** `(t)` still re-imports Intervals and
  takes ownership, but now writes an `activity_manual_fields` owner row for
  every field it took, so a rebuild keeps the decision (root item 17).
- **Sync timing and a real FIT fixture.** `sync` records wall-clock seconds
  per phase (`garmin`, `intervals`, `fit`, `review`, `total`) and prints one
  `timing:` line; `sync.sh` adds `classify` and `dashboard` to it. CI parses
  `tests/fixtures/sample-run.fit` instead of skipping every real-file test.
- **VO2max is per sport.** Message 140 field 7 carries the estimate for the
  activity's own sport, so `vo2max_garmin` is correct as written and needs no
  parser change. The session report qualifies non-run values, the charts are
  running-only, and `docs/SOURCE_NOTES.md` records the semantics.
- **Thresholds and zones come from maintenance, not the importer.**
  `athlete_thresholds_current` derives the dated snapshots from the Intervals
  payloads and `activity_zone_configs_current` writes the zone configs; the
  importer does not duplicate that logic.
- **Sheet vocabulary moved here.** `SHEET_TYPE_CODES` and
  `classification_for_sheet_code` now live in `hobbyjogging_import.sheet_codes`
  instead of `hobbyjogging_core.workouts`, so the canonical vocabulary is not
  shaped by one spreadsheet; maintenance imports the mapping from here.
- **Runalyze payload repair and VO2max fill.** The `--refresh-before` sweep
  re-read all 2,843 activity payloads (a 2023 row went from 64 to 87 keys with
  `hr_avg`/`vo2max`), closing the `hr_avg` gap from 1,752 linked rows to 5;
  three transient 502s recovered on retry. `runalyze vo2max` then filled
  `vo2max_runalyze` from 843 to 2,225 values (2019-01-22 → 2026-11-16), which
  unblocks reports item 15.

- **Strava CSV social + gear.** `hobbyjogging-import strava <zip|dir>` reads
  `activities.csv`, `bikes.csv` and `shoes.csv` without an API app or
  subscription. The 2026 export is wide: `Distance` and `Elapsed Time` appear
  twice and the second `Distance` is always metres; gear lives in
  `Activity Gear`. The reader parses by column index, prefers the metres
  column, and `--date-zone auto` picks whether `Activity Date` is local or UTC
  (this account is UTC). Social text goes to `activity_social(source='strava')`;
  the canonical text target is a per-source setting (root item 40), default
  social. Gear links by exact normalized name or creates
  `strava:gear:<slug>` without rewriting an existing row. Applied to the real
  export: 2,554 of 2,590 social rows, 35 unmatched (mostly other sports or
  genuine distance disagreements), 1 ambiguous; 5 bikes, 3 new equipment rows,
  2 linked, 64 activity links. A re-run is a no-op for social rows. The create
  decision is settled (root item 40): every source may create, and this
  athlete configures Strava as `ignore`.

- **Runalyze match review.** A row the temporal matcher rejects is checked
  once more for a perfect twin (same day, duration within 2 s, distance within
  10 m, exactly one candidate) — start-time drift without guessing. A twin
  that is a sheet-only duplicate of a device row is the duplicate, not the
  target, so that day becomes a review item that suggests the device row.
  Unresolved rows keep their detail (unlinked) and open one
  `ambiguous_match` item with the same-day candidates; triage `(1-N)` links a
  candidate and applies the stored note and tags on the spot. Applied to the
  real DB over the 19 leftover rows: 0 links, 19 items (3 suggesting a device
  row), 19 details stored, no activity created, no-op re-run.
- **Runalyze phase 4.** `runalyze races` imports `/api/v1/raceresult` into
  `race_results` under `source='runalyze'`, resolving each row through its
  Runalyze activity id (the stored payload's `external_id`) and never guessing
  a match. Distance, official time, placement, participant counts, priority
  and status map straight across; a manual `race-result` row is kept. Validated
  on a DB copy: 37 results (33 with a placement, 21 officially measured) and a
  no-op re-run. Applied to the real DB: 37 `race_results` rows and 37 source
  records. `official_ascent`/`official_descent` and `race_event_id` are not
  imported (no column / no matching identity).
- **Runalyze `enrich --ids`.** The repair path for a detail whose fetch failed:
  it reads the named activities directly and matches from the detail's own
  date/duration/distance instead of the collection.
- **Short activities match.** The matcher's flat 120 s overlap floor made any
  session under two minutes unmatchable: a 142 s cooldown reported
  `no_temporal_match` against a 141 s activity. Below 200 s the floor now
  scales with the shorter window and the 60 % ratio decides, and contained
  FIT segments inherit the same rule. The 2026-04-12 Linz cooldown links now
  and carries its two Runalyze tags (`Auslaufen`, `Raceday`).
- **Runalyze phase 5.** Offline `runalyze vo2max` fills `vo2max_runalyze` from
  the stored payloads' effective `vo2max`, leaving `vo2max_garmin` untouched
  and skipping unlinked activities. 843 values, all 2019–2022, and a second
  run reports 843 `unchanged`. Applied to the real DB, so `vo2max_runalyze`
  now sits beside `vo2max_garmin` (2,812 values).
- **Runalyze phase 3 follow-up.** Clothing (category 78698) is skipped, name
  matching falls back to the colour-stripped form (the sheet names carry no
  colour, and co-occurrence cannot bridge gear before 2023 — no sheet-linked
  activity carries Runalyze gear), and a row the importer created earlier is
  reconciled onto the matched row: links move, the duplicate goes. Validated
  on a DB copy with the full history: 2,823 payloads, 26 gear records, 6
  clothing skipped, 2 linked to sheet rows (`Brooks Adrenaline 20`,
  `Lunge Fis`), 1 duplicate reconciled (`Lunge Neo Run (grau)` → sheet
  `Lunge Neo Run`), 491 new activity links, and a no-op re-run. A name tie is
  now broken by the acquisition date (Runalyze `date_start` = the row's
  `acquired_on`), which closed the last open item: `Lunge C-Dur (rot)` →
  `sheet:equipment:5` and `(schwarz)` reconciled onto `sheet:equipment:6`
  (31 equipment rows, no open review items).
  Applied to the real DB: 32 equipment rows, 3,299 activity links, one open
  `ambiguous_equipment` item.
- **Runalyze phase 3.** Offline `runalyze gear` reads the stored activity
  payloads' `equipment` arrays and resolves each gear record by
  co-occurrence → exact normalized name → new `runalyze:equipment:<id>` row,
  then links activities (`source='runalyze'`; first shoe/bike primary, rest
  secondary) without touching sheet or manual links. Ambiguity opens a
  non-hiding `ambiguous_equipment` item. Validated on a DB copy: 807 payloads,
  21 gear records (16 shoes, 4 bikes, 1 other), 796 activity links (774
  primary, 22 secondary); no gear has sheet co-occurrence or a name match yet,
  and the second run is a no-op. The co-occurrence/name branches are covered
  by fixtures and will apply when the 2019–2021 payloads arrive; re-run then.
- **Runalyze phase 2.** `runalyze enrich` fills a blank `description` from the
  Runalyze `note`, imports detail `tags` into `activity_tags` under
  `source='runalyze'` (manual tags survive), and reports unmatched/ambiguous
  rows (`--output` JSON). Matching is temporal plus distance; `name`, timing
  and distance are never written. A mid-run 429 stops cleanly, lists
  `processed`/`not processed`, keeps the rows already processed, and marks the
  import run `partial`. Re-runs skip any stored detail already linked to the
  same activity, so the next window continues with the remainder (`--refresh`
  re-fetches to pick up edits). `--wait` fetches the collection once, sleeps
  through the windows unattended and resumes until the range is complete.
  (An earlier `edited_at` comparison re-fetched a growing prefix every window
  and starved the new rows; the linked-detail skip fixed the slowdown.)
  Validated on a DB copy: one week, 9/9 matched, 5 tags on 3 activities,
  second run a no-op.
- **Runalyze phase 1.** Read-only `runalyze.py` client (`token` header,
  rate-limit-aware, numbered pages, local `--since`/`--to` filtering) and
  `runalyze inventory --dry-run`, which probes the known endpoints and reports
  activity-field coverage per year without writing. Verified live: 2,841
  activities (2019–2026), 88 fields in the detail payload, and the four
  expected 403 endpoints. Tests use recorded fixtures. Phases 3–6 remain in
  root item 12.
- **Sheet routes.** `Strecke`/`Streckennummer` resolve to a canonical route
  (number first, then the name's number when unambiguous) and the activity is
  linked; a Gmap URL is not a route. The sheet remains the only route source
  before 2022, and Runalyze's `recurring_route` will be a separate identity.
- **`period` command.** `period add|list|remove` writes a manual training
  period (kind, start, optional end, label, notes), keyed by kind and start so
  re-adding updates it. The recompute owns the Intervals-derived periods and
  never removes a manual one.
- **Device capture.** The FIT importer upserts the device from
  `file.manufacturer/product/serial_number` and sets `activities.device_id`;
  the Intervals importer normalizes `device_name` and fills only what FIT left
  empty (FIT owns the field). Garmin Connect uploads are not devices.
- **`race-result` command.** `race-result add|list|remove` writes one activity's
  official race metadata by hand (distance, time, place, participants,
  `officially_measured`, priority, status), replacing its own row and never
  overwriting a manual one. The schema is v16 `race_results`.
- **Max HR and temperature capture.** The v12 columns and the v13
  `activity_weather` table are written by the importers: FIT session max HR,
  Intervals `max_heartrate` and `average_temp`, the sheet's `max. Hf` and
  `Temperatur in °C`. Runalyze's richer weather fields (humidity, wind,
  pressure, UV, clouds, condition) are shaped into the table and wait for that
  importer.
- **Fartlek for the sheet `fs` code.** `SHEET_TYPE_CODES` maps `fs` to
  `fartlek` + `vo2max`, with the `fahrtspiel` / `fartlek_run` aliases, so new
  sheet imports land in the right bucket. The existing rows were converted by
  `fartlek_from_fs_v1`.
- **FIT scan manifest.** Routine scans (`sync`) skip files whose resolved
  path, size and mtime match the `fit_scan_files` manifest, so non-activity
  FITs are not re-read. Deleted files are pruned, `--full` ignores the
  manifest, and known activities are seeded from stat on the first run.
  Measured on the real archive: 18.3 s → 2.7 s over 64,349 files (61,470
  recorded as non-activity). Out-of-range files stay unrecorded so a wider
  range still imports them.
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
  counts as `updated`. The `event_zones_v1` backfill in
  `hobbyjogging-maintenance` repairs stored events from their saved Intervals
  payloads without network access and is idempotent.
- **Incremental `sync`.** Runs Garmin fetch, Intervals import, FIT archive
  import with `skip_known`, and the shared quality scan. `--no-*` flags skip
  sources, `--full` reimports all FIT paths, failures are reported per source
  and the command exits non-zero after continuing with the rest. The scan core
  is shared with `review scan`.
- **Field-conflict prune.** `review prune [--dry-run]` resolves open field
  conflicts whose recorded values now agree under the current core
  tolerances. FIT/Intervals reimports also resolve a field's old conflict
  automatically when that field agrees again.
- **Quality prune.** `review scan --prune` resolves open `quality` items whose
  rule no longer triggers for the activity's current values (or whose activity
  is excluded). It reuses the fingerprint identity of
  `record_quality_findings`, reports `checked/resolved/kept` with
  `--dry-run`, leaves the other review categories alone, and is idempotent.
- **Conflict causes and bulk triage.** New `field_conflict` items carry a
  `cause`/`cause_note` computed from the stored source summaries (`causes.py`).
  Advisory causes (`elapsed_definition`, `moving_estimate`, `small_difference`,
  `start_offset`) are `info`; the rest stay `warn` and need a per-activity
  decision. `review causes`, `review classify [--dry-run]`, `--cause` filters
  on `list`/`triage`, and `review resolve --cause <cause> [--dry-run]` support
  the workflow.
- **Race categories.** `event_methods` maps Intervals `RACE_A`/`RACE_B`/
  `RACE_C` onto the canonical `race` method during event sync. It is public so
  the maintenance `event_race_method_v1` backfill can re-derive the method for
  events that predate the mapping.
- **Spreadsheet import.** `sheet` reads the hand-maintained `.ods` log with a
  standard-library ODS reader (`ods.py`), maps the German columns
  (`Rohdaten`, `Alternativtraining`, `Material`), links shoes, and keeps the
  raw row in `source_records.payload_json`. Start times are matched at
  minute precision; matched activities keep their precise start, and rows
  without a start create dated activities. Imports are stable and idempotent.
- **Empty Intervals artifact.** `is_empty_interval` in `intervals.py` drops the
  trailing 1 s / 0 m `RECOVERY` row Intervals appends when building the stored
  interval list; genuine short segments (2 s or any distance) survive. The raw
  payload keeps the original rows. The maintenance `drop_empty_intervals_v1`
  backfill reused the predicate and removed the existing rows (239 across 235
  activities).
- Full FIT archive import, VO2max backfill, and the historical spreadsheet
  import have been run against the real DB.

## Next

- **Consistency audit** (`review scan --rules consistency`). A dataset-wide
  scan for contradictions between the stored classification and the evidence,
  producing `consistency` review items (info, non-hiding) with a suggestion in
  `context_json` and a triage `(a)ccept` action that writes the suggestion as
  manual. Evidence-gated and conservative.
  **The exact rule set and thresholds are still to be determined** — the rules
  below are measured candidates, not a committed set; settle them (and the
  90% / 40 m/km / 5 min / 150 bpm / 90 min thresholds) before implementing.
  **Prerequisites**: elevation is now stored (schema v12), so the trail rule
  has its evidence; the vo2max rule must filter to running activities — a ride
  carries its own cycling estimate, which is valid data, not a running one.
  Measured yields:
  - `intervals` but the WORK reps cover >90% of the activity → suggest
    `continuous` (38), or `fartlek` when the reps are irregular.
  - `intervals` with **no usable WORK reps** (170) → a `missing_reps`
    data-gap item (info), **not** a reclassification: the session was
    structured, the device data is absent. Only suggest `fartlek` when the
    name or the sheet `fs` code says so.
  - `run` with ≥40 m/km lap elevation → suggest `trail_run` (9); also use
    `sub_sport` (`trail`, `mountain`, `treadmill`) as evidence.
  - `race` but no event within ±1 day, inside calendar coverage → suggest
    dropping `race` (1); `sub_sport='RACE'` is supporting evidence.
  - `vo2max` but no WORK rep ≤5 min → suggest `threshold` (6).
  - `recovery` target with avg HR ≥150 → suggest `base` (3).
  - `long_run` under 90 min → suggest dropping it (2).
  - `intervals`+`threshold` without a sustained WORK block → suggest `tempo`
    (1).
  Rules fire only when the evidence exists; ungated, the counts explode with
  history artefacts (162 / 45 / 69). A changed suggestion supersedes the old
  item.
- **Pace/HR outlier scan** (historical refurbishment). Add a dataset-wide quality rule
  that fits the steady-run pace/HR relationship (robust, per year or a rolling
  window) and records a `quality` review item when a run's average HR is far
  from the expected value for its pace. Start with steady easy/recovery runs only;
  exclude trail/race/interval sessions and heat/elevation explanations, or
  carry them in the item context. A first pass at 3.5 MAD / 12 bpm flagged 37
  gross points, many legitimate, so calibrate on the steady subset before
  enabling. Run it from `review scan` (a new `--outliers` flag or a separate
  command), prune when an edit or a model change clears the flag, and let the
  reports mark the flagged points later. Using `quality` hides the activity
  until reviewed; decide whether that is wanted or a non-hiding category is
  needed.
- **Duplicate/overlap detection.** Flag two activities that are the same
  session: same sport, overlapping start (±15 min) or same day, distance
  within ~2%, and HR within 5 bpm when both have it. Emit a `duplicate` review
  item carrying both activity ids; resolve by excluding one. Runs in the
  quality scan, idempotent by a fingerprint over the sorted pair.

## Waiting on

- **Historical refurbishment.** The read-only audit is done; the
  comment/tag workout proposals and triage actions start after the Runalyze
  import settles.
- **Sheet duplicates (38).** 1,272 activities are sheet-only, and 38 of them
  mirror a device (FIT/Intervals) row on the same day with the duration within
  5 %, so those sessions count twice in the reports. The sheet row often holds
  the only description (`mit Vicky`, `Oberwolfach am Ende gas`). Fixing it
  rewrites existing rows, so it belongs in a maintenance task — blank-fill the
  description from the sheet row, then exclude the sheet row — not an import
  write.

Nothing else. Runalyze phases 1–5 have landed; phase 6 (reports) has the race
pair done and the VO2max series ready (`vo2max_runalyze` now holds 2,225
values). The unmatched rows are 19 open `ambiguous_match` items, which is a
triage job, not import code.

## Notes / risks

- Message 140 is undocumented; Garmin can strip it. The VO2max line in the FIT
  import summary is the early warning.
- The Personal API activity FIT is byte-identical to the GDPR archive copy
  (4/4 activities tested in November 2026). The JSON `vO2MaxValue` is null;
  the type-44 `max_met_data` files are not needed.
- The manifest is a bandwidth optimization. The FIT importer is
  checksum-idempotent, so a redownload does not duplicate source records or
  laps.
