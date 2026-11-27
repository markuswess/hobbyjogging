# Status and next steps

Updated 2026-11-24.

## Done

Recently landed; git history is the changelog. Structure and settled rules
live in [ARCHITECTURE.md](ARCHITECTURE.md), metric cards in
[METRICS.md](METRICS.md), and each package's own list in
`packages/*/NEXT_UP.md`.

- **Release 0.3.0 (2026-11-25).** All five `pyproject.toml` files and
  `uv.lock` say `0.3.0`; the changelog names schema 29, the new data tasks and
  the new CLI/report surface, and an annotated `v0.3.0` tag marks the phase-3
  state. The user pushes the tag.
- **Manual writes, equipment and selectors (2026-11-25).** Every manual write
  now appends one `edit_log` row per changed field: `race-result`, `threshold`,
  `period`, `equipment`, triage `(v)`/`(t)` and the existing activity edits.
  `equipment add|list|edit|retire|history` lands with schema 29
  (`equipment.is_manual`), so a later import links to a manual row without
  rewriting it; retire sets `retired_on`. `activity edit`, `race-result`,
  `threshold history`, `period remove|history`, `equipment edit|retire|history`
  and the review activity commands accept an id, ISO date, `last` or a name
  substring; ambiguity lists candidates and refuses to guess, and interactive
  edit prompts.
- **Duplicate detection and sheet cleanup (2026-11-25).**
  `duplicate_candidates_current` scans the whole database for same-session
  pairs (sport/day, distance 2 %, duration 5 %, HR 5 bpm) and opens one hiding
  `duplicate` item per pair; `sheet_duplicates_v1` copies a sheet-only
  duplicate's description to a blank device row and excludes the sheet row.
  On a copy: 33 pairs (30 sheet/device, 3 other); the cleanup filled 23
  descriptions, excluded 30 sheet rows, left 3 non-sheet duplicates for review,
  and `verify_canonical` stayed at 0 drift. Resolution is exclusion, never a
  merge.
- **Pre-run snapshots (2026-11-25).** A real maintenance run writes a
  `VACUUM INTO` snapshot beside the database
  (`<db>.bak-YYYYmmddTHHMMSSZ`), keeps the last five and prints the path; a dry
  run and a skipped backfill write none. A snapshot failure aborts the run. On
  the full copy the snapshot is 119 MB and takes about 0.35 s.
- **Tag lexicon and evidence proposals (2026-11-25).** The one normalized
  tag -> meaning table now drives the audit and the proposals: 157 of 216
  stored tags are mapped (the 59 unmapped are places and people), and the
  audit accounts for every tag. An empty run classification is filled from a
  mapped tag (`source='tag'`) or an explicit description (`source='comment'`)
  after the classifier/sheet/Runalyze-type proposals; on a copy this filled 32
  historical comments and rejected ambiguous strength reps and non-run tags.
  `illness_candidates_current` and `trail_candidates_current` open
  non-hiding `period_candidate`/`consistency` items (7 illness, 41 trail on a
  copy), and triage `(a)ccept` writes a suggested sport as manual. The
  `health` report and dashboard card already carry the review queue and
  coverage; duplicate counts appear there once item 42 opens them. The eight
  existing seasons are already labeled with their goal race and no year lacks
  a start, so no season candidates are needed now.
- **Evidence conflicts for classified activities (2026-11-25).**
  `workout_classification_queue` now compares a mapped tag or explicit
  description with the stored sets of an already-classified activity. It opens
  one `workout_classification` item only when the evidence names a method or
  target the stored set lacks; agreeing or absent evidence resolves stale
  items. The item context carries the evidence source, its sets and the stored
  sets, and triage `(k)` offers `4) evidence` and `s) kept stored` alongside
  the classifier/sheet choices. Choosing a set writes manual values and logs
  old/new through `edit_log`; `kept stored` resolves without a write. Nothing
  is applied automatically, and a resolved decision is not reopened.
- **Date and time-zone integrity (2026-11-25).** The canonical quality rules
  now parse `started_at_utc`, require `tz_offset_min` to be within −12..+14 h,
  and check that the UTC start plus the offset lands on `local_date`. A
  mismatch opens one `quality` item (`local_date_mismatch`,
  `tz_offset_out_of_range` or `started_at_invalid`) and rewrites nothing. FIT,
  Intervals and the sheet imports feed the same check; `review scan` and
  `refresh_activity_quality` re-run it over stored rows. Correct rows and
  missing evidence stay quiet, and a re-run is a no-op.
- **Field provenance in the session report (2026-11-25).** `DataSource`
  exposes `activity_field_sources`, and the session block lists each owned
  field (distance, duration, avg/max HR, elevation, sport, load, both VO2max
  owners and device) with its source and value. An open `field_conflict`
  supplies the losing source, its value, the cause and a link; a single-source
  activity collapses to one line. The CLI and the dashboard share the block,
  and the dashboard applies the usual collapsible-table treatment.
- **Corrections export (2026-11-25).** `reports.sh corrections
  [--days|--from|--to] [--format markdown|csv|json]` lists open
  `field_conflict` items grouped by the platform whose value disagrees, with
  the canonical value and owner, that source's value, cause, suggested action
  and a deep link (Intervals, Garmin or Strava when known), plus
  source-attributable quality findings. It is read-only: it never writes,
  calls a source API or resolves an item. With no range it covers every open
  item; CSV and JSON are flat checklists.
- **Sheet leftovers (2026-11-25).** Activities display the recorded local
  start (`started_at_utc` + `tz_offset_min`) instead of UTC in the activity
  table and the session report; `local_date` already carries the local day for
  every chart and range. Every started activity on the real DB has an offset
  (4,093/4,093). The sheet's equipment size, price, colour, legacy total km
  and remarks stay provenance text in `equipment.notes`: no report or rule
  consumes typed fields, and the canonical mileage is derived from activity
  links.
- **Classifier-sourced workout sets are re-derived (2026-11-25).**
  `workout_sets_current` now re-derives an activity whose sets are entirely
  classifier-sourced from the current name/RPE/intensity/work reps, so a
  rename cannot leave stale sets. Manual, sheet, Runalyze-type and imported
  sets stay untouched; a sheet-only or merged sheet proposal is written as
  `source='sheet'`, and no classifier evidence keeps the stored set
  (`stale_no_evidence`). A copy with a seeded stale `intervals`+`subthreshold`
  classifier set became `intervals`+`lt1`, and a second run was unchanged.
- **Session metrics (2026-11-25).** `activity_metrics` (v27/v28) stores one
  nullable row per activity: cadence, stride, vertical oscillation, stance
  time/percent/balance, vertical ratio, respiration, power, calories, training
  effect, GAP and average/min/max altitude. FIT owns device-measured dynamics,
  Intervals owns altitude, Runalyze fills the gaps, and a per-field source map
  keeps that stable across reimports. The FIT parser, the three other
  importers and `activity_metrics_v1` share one extractor; the session report
  shows `Metrics`/`Dynamics` lines and `maintenance audit --fit-sample`
  reports coverage and conflicts. On a copy: 2,917 rows, 0 canonical drift.
  The remaining chart work is item 62.
- **Activity editing (2026-11-24).** `activity edit <id>` is the
  direct human write surface: name, description, duration, distance, sport,
  sub-sport, RPE, feel, tags, methods, targets and equipment, plus `--clear`,
  `--dry-run`, `--history` and an interactive mode. Every change is a manual
  input through the triage write path; an item-less edit closes the matching
  `field_conflict` and, after a set change, the `workout_classification`
  item. Schema 26 adds the append-only `edit_log`.
- **Phase 2 complete (2026-11-24).** `init`/`doctor`, the full-source `sync`,
  the install docs, the MIT licence, CI, the lab detach, the
  source-capability matrix and selection, and the Runalyze+Garmin profile
  (items 44, 49–54 and the name label) landed; schema is v25. The acceptance
  run on a second athlete's real data passed; its findings 55 (subT selection
  and the derived table) and 56 (threshold coverage) are fixed and tested.
- **The canonical pipeline and all sources (phase 1).** FIT archive,
  Intervals.icu, the Garmin Personal API fetch, Runalyze (inventory,
  comments/tags, gear, race results, `vo2max_runalyze`) and the Strava CSV are
  imported and applied on the real DB: 4,143 non-excluded activities, schema
  v23, since grown to 4,148 and v25.
- **Inputs vs projections (item 17).** `activity_manual_fields` (v23) holds
  manual values and owner patches; `derive.py` declares the per-source mapping;
  `verify_canonical` reports 68,122 owned fields with 0 drift, 0 dangling and 0
  unmapped, and `recompute_canonical` is a no-op on the real DB.
- **Import policy and settings (item 40).** `sources.toml` carries enabled,
  create and text targets; the ladder creates only when nothing is left to
  review; `hobbyjogging-import sources|settings` and `reports.sh settings`
  render it.
- **Strava CSV (item 16).** 2,554 of 2,590 rows matched, 35 unmatched, 1
  ambiguous; 5 bikes, 3 equipment rows and 64 activity links. Social text is
  per source in `activity_social` (v22).
- **Runalyze payload repair.** All 2,843 payloads were re-read (the `hr_avg`
  gap fell from 1,752 to 5) and `vo2max_runalyze` went from 843 to 2,225
  values (2019-01-22 → 2026-11-16).
- **Race evidence.** `race_links_current` treats a non-excluded `race_results`
  row as evidence, so all 37 official results carry the `race` method.
- **Stored detail (v12–v21).** Routes, race results and race links, devices,
  training periods, wellness extras, weather, elevation and max HR, thresholds
  and zone configs.
- **Reports and lab.** One session renderer for CLI and dashboard, a clickable
  review queue, max HR/elevation lines, data-driven chart ceilings, official
  race pairs and Riegel anchoring; the lab promoted the efficiency line shape
  and running-only load, and parked the duration correction and the
  race-fitness bundle.
- **Four suites green**, and the demo deploys weekly from GitHub Actions.

## Bugs

_None._

## Next

Numbers are labels, not a schedule: a completed item leaves a gap and a new
one takes the next free number, so cross-references stay valid. The phases and
their exit tests are in [ARCHITECTURE.md](ARCHITECTURE.md). Work is picked by
impact per unit of effort, bugs first; small features (a bug fix, a dashboard
fix, a report over stored data, a promoted lab metric, docs) may land in their
package at any time and do not wait for a phase.

### Phase 2: works for someone else

Exit test: a computer-savvy Linux user clones the repo, runs `./demo.sh` with
no credentials, then fills `.env` and `sources.toml` and runs `init`, `doctor`,
`sync` (which covers every configured source) and the dashboard on their own
machine — no code or SQL edits. And a **Runalyze+Garmin athlete's dashboard is
usable**: categories, laps/reps, zones, load, wellness and races render.

**Phase 2 complete (2026-11-24).** Every code path exists, the source
capability matrix and selection are in place, and the fresh-database path is
covered by the demo and the suites. The acceptance run on a second athlete's
real data (a fresh DB with Runalyze + Garmin and the FIT archive, no Intervals)
passed; its two findings — **55** (subT selection and the derived table) and
**56** (threshold coverage) — are fixed and tested.

**2a · Install**

- **`doctor` and `init` (done 2026-11-24)** — `hobbyjogging-maintenance init`
  creates and migrates a fresh DB and the FIT directory, idempotently;
  `doctor` checks `uv`, the DB path, schema version, FIT dir, every configured
  credential, a bounded liveness probe (Garmin token exchange, Intervals and
  Runalyze reads), pending data migrations, source staleness and the sources
  file, and prints the next command. Root wrappers: `./init.sh`,
  `./doctor.sh`.
- **`sync.sh` skips an unconfigured source (done 2026-11-24)** — a missing
  credential or a disabled source is a warning, never a failed sync (item 44
  covers the rest).
- **44 sync covers every configured source (done 2026-11-24)** — Runalyze,
  Strava and the offline derivations join the one command. A budgeted Runalyze
  window, the offline gear/VO2max derivations, race results and the newest
  unimported Strava export run after the recording sources; `sync.sh` then runs
  the maintenance recomputes, the scan and the dashboard. Item 44 is closed.
- **`./demo.sh` as the zero-credential first run (done 2026-11-24)** —
  documented as the install proof and tested in CI and locally with no
  `.env`.
- **`sources.toml`, `.env.example` and the README first-run path (done
  2026-11-24)** — copy, edit, `init`, `doctor`, `sync` (GDPR export or
  `garmin fetch` → `sync` → dashboard).
- **A pull-request workflow and an MIT `LICENSE` (done 2026-11-24)** — the
  workflow runs the four suites, the todo check and the demo build on 3.12.
- **22 release versioning (done 2026-11-24)** — `CHANGELOG.md` records schema,
  data tasks and report changes with a compatibility line; `v0.1.0` tags the
  phase-1 state locally (the user pushes), `v0.2.0` waits for the phase-2
  exit.
- **29 lab detach (done 2026-11-24)** — the scripts and notebook moved to
  `~/projects/laufen_private/lab/`; the bench rules, template, `lab.sh` and
  the Lab tab stay, and a demo build never reads the private directory.
- **Defaults consolidation and the Python floor (done 2026-11-24)** — the
  athlete-tuned numbers live in `hobbyjogging_report/defaults.py` with the
  conflict tolerances re-exported from `core.import_rules`; `requires-python`
  is `>=3.12`, all four suites pass there, and the pull-request workflow runs
  on 3.12.

**2b · A usable dashboard without Intervals** (the Runalyze+Garmin profile)

- **49 Runalyze workout type → canonical sets (done 2026-11-24)** — Jogging,
  Long Slow Distance and SubThreshold map to canonical sets, applied on create
  and as a gap-filler; `runalyze types` audits every stored type. This is what
  gives a name-less athlete categories.
- **51 typed reps without Intervals (done 2026-11-24)** — `derived_intervals_current`
  infers WORK/RECOVERY from device laps, gated by the source type or lap
  variance and marked `source='derived'`; a measured set always wins, and the
  session report labels derived reps.
- **53 a load fallback (done 2026-11-24)** — `fit_trimp`/`trimp` fills an empty
  `training_load` under `source='runalyze'`; Intervals outranks it, and the
  vendor scale is documented per athlete.
- **50 manual thresholds and local zone configs (done 2026-11-24)** —
  `threshold add|list` writes dated per-sport snapshots; `derived_zone_configs_current`
  builds local HR/pace configs and lap zone times from them, and Intervals
  still wins where it has a config. The max-HR snapshot feeds effective VO2max.
- **52 Garmin wellness (done 2026-11-24)** — daily resting HR, HRV, sleep,
  steps, SpO2, floors and weight join `sync` after the activity fetch;
  fill-only, so the Intervals wellness stays the owner.
- **A name label (done 2026-11-24)** — when `name` is empty, tables and the
  session header render the sport plus distance ("Run 10.00 km") instead of a
  blank title.

### Phase 3: trustworthy data

Phase 3 is current (since 2026-11-24). **45** (readability baseline), **34**
(manual overlay + rebuild proof), **37**'s audit and evidence proposals,
**43**'s tag lexicon, the CLI write surface, **38/35** (session metrics),
**21** (sheet leftovers), **42** (duplicates), **47** (time-zone integrity),
**48** (field provenance), **57** (corrections export) and **22** (release
0.3.0) are done. The remaining work is the **CLI brush**: phase 3 is complete
when every pass in [DATA_BRUSH.md](DATA_BRUSH.md) can be done through the CLI.
The localhost browser moved to phase 4 (item 65).

Order: **45** (readability baseline, done) → **34** (manual overlay + rebuild
proof, the safety gate, done) → **37** audit and evidence (done) → the CLI
write surface (done) → **38/35** (session metrics, done; charts are item 62) →
**21** sheet leftovers (done) → **43** tag lexicon (done) → **42** duplicates
(done) → the CLI brush (the gate). The write-surface follow-ups **58–60** are
done; the secondary equipment link **66** follows the brush, and the duplicate
start-time gate **67** comes after the polish. The metric charts **62** and the
pace/HR calibration follow-up **64** slot alongside. The health report and
dashboard card show the duplicate count
now that 42 opens the items. Accepting a suggestion always writes a manual
value and an `edit_log` row; nothing canonical is auto-applied except an
empty, high-confidence classification. The corrections export (**57**) and the
session provenance block (**48**) are the read-only source-side pair.

### Phase 4: durable and more reach

Parked: 13 homelab, 14 platform independence, 25 coaching, 27 performance, the
Strava API, the stream half of 38, and the **localhost write UI** (65). Ordered
only when phases 1–3 are done.

Item 40 is closed (see its entry): the recording sources keep `enabled`, so
there is no create policy to wire. Item 41 (device identity) landed as a bug
fix, not as phase work. Items 12, 16, 17, 24, 32 and 39 are landed; 15 is a
reports item; 28 is the recurring cleanup.

12. **Runalyze enrichment** (core + import + reports). Phases 1–5 are landed
    and applied; this entry keeps only what matters to rerun it or to explain
    the open queue. Per-phase detail lives in the import package's list and in
    [SOURCE_NOTES.md](SOURCE_NOTES.md).
    - **What it supplies**: comments (fill a blank `description`), detail tags,
      gear identity, official race results and `vo2max_runalyze`. It never
      writes `name`, timing or distance.
    - **Access**: the header is `token: <key>` (not `Authorization: Bearer`);
      the collection is `/api/v1/activity` (singular) with `page` /
      `itemsPerPage`, and its `time[...]` filters are ignored, so the range is
      filtered locally. `sport`, `recurring-route`, `planned-race` and
      `device-profile` answer 403; the nested activity payload covers what they
      would have provided. The budget is 240 requests per window
      (`X-RateLimit-Reset`), so a full-history detail pass spans several
      windows — `runalyze enrich --wait` sleeps through them. Tags are
      detail-only; `vo2max` is Runalyze's effective estimate (the
      `_by_time`/`_with_elevation` variants stay in the raw payload).
    - **No Garmin id**: matching is temporal plus distance. A row the matcher
      rejects gets one exact-twin check (same day, duration within 2 s,
      distance within 10 m, exactly one candidate); a twin that is a sheet
      duplicate of a device row is treated as the duplicate. Everything else
      keeps its detail stored and opens one `ambiguous_match` item with the
      day's candidates; triage links a candidate and applies the stored note
      and tags.
    - **Gear identity** (settled): co-occurrence → normalized name
      (colour-stripped, acquisition date to break a tie) → a new
      `runalyze:equipment:<id>` row. A gear record only adds a source link to an
      existing equipment row; it never rewrites that row's name, brand, model
      or dates.
    - **State**: 2,225 `vo2max_runalyze` values (2019-01-22 → 2026-11-16), 37
      race results, 32 equipment rows and 3,299 activity links; the 19
      unmatched rows are open `ambiguous_match` items (3 suggesting the device
      row). That queue is user triage, not import code.
    - **Backstop**: `runalyze.com/my/exports` (CSV/JSON from the web UI) if the
      API regresses; the bulk path, not the daily one.
    - **Not scheduled for this athlete**: Runalyze weather (0 rows here, but
      `weather_condition` is on every athlete-2 payload — revisit when a
      non-Intervals athlete needs it), routes (0 here; `route_name` and
      `recurring_route` exist on athlete-2 payloads but the identity stays
      source-scoped), health entries (0 illness periods, 0 wellness rows) and
      the gear category map (two hard-coded IDs that a second athlete does not
      share — root item 23).

13. **Homelab cutover** (phase 4): DB + importer + dashboard generator + static
    server, periodic backups of the database **and the FIT archive**, Tailscale
    or basic auth. The archive is the only irreplaceable raw data (per-second
    streams), so it is backed up beside the database, not instead of it.
14. **Platform independence** (phase 4, dormant; ingestion unchanged). The
    goal is to stop depending on Intervals.icu as the *system of record* — not
    to stop using it as transport. The trigger is a paywall or wanting out, so
    nothing here starts now: Garmin, Intervals and FIT ingestion stay exactly
    as they are.
    - **Acceptance test**: for every action taken in Intervals today there is a
      local equivalent, and a reimport cannot undo it.
    - **What is missing**: events are Intervals-authoritative (`upsert_event`
      replaces every field including NULLs, removal soft-excludes), wellness has
      no owner tracking, and planned workouts carry methods/targets/zones but no
      step list.
    - **Source exit checklists**: a platform is retired **per metadata type,
      not per platform** — the type gets a DB surface first, the import keeps
      backfilling, and the platform stays a read-only fallback until the DB is
      at least as good for that type. Runalyze is nearly reachable: race
      results already have the manual `race-result` CLI (about five per year),
      comments live in Intervals, tags have the manual edit surface, and the
      only missing surface is equipment add/edit/retire; the lost series is
      `vo2max_runalyze`. Intervals is the hard one (plans, wellness, events,
      thresholds, zones), which is why it comes last.
    - **Phases**, in order: owner-tracked events (`event_field_sources`, manual
      wins, a new `AGENTS.md` rule) → planned-workout steps and authoring →
      subjective wellness ownership → thresholds/zones (item 8) → the front end
      from the `activity edit` surface → Garmin/FIT ingest so Intervals becomes
      optional.
    - **Not needed**: a notes/comments table. The field inventory shows one
      training-notes text per activity (`description`) plus a social text on
      Strava, so this work reuses `description` rather than adding
      `activity_notes`.
    - **Parked decisions**: whether programmed workouts are followed on the
      watch (which would need a `.fit` workout export and upload) or the lap
      button is enough — the 370 intervals activities with ≥3 WORK reps suggest
      the latter; and whether the front end ever replaces the CLI.
    - **Edit history** (`edit_log`, schema 26) is a prerequisite, not an extra:
      without it, dropping the platform also drops the audit trail.

15. **Reports backlog** — handed to the reports session; the list lives in
   `packages/hobbyjogging-reports/NEXT_UP.md` and is kept current there rather
   than duplicated here.
16. **Social titles, descriptions and links** (core + import + reports; phase
    1). Strava is the first social layer, but not the only possible one.
    - **Landed (Nov 2026)**: `activity_social` (schema v22), keyed by
      `(activity_id, source)`, with title, description, external id, url,
      source record and manual flag. A source refreshes only its own row; a
      manual row survives imports. The session report renders a `Strava: …`
      line under the external links. Schema v22 is applied to the real DB.
    - **CSV first, no subscription**: `hobbyjogging-import strava <zip|dir>`
      reads `activities.csv`, `bikes.csv` and `shoes.csv`. It matches by the
      export's date zone (`--date-zone auto|local|utc`) and falls back to the
      exact-twin rule. Distance is km by default (`--distance-unit m` for
      single-column exports). It writes nothing for an unmatched row today;
      the per-source create policy (item 40) makes that choice configurable,
      and this athlete's config keeps Strava at `ignore` (social + gear only).
    - **Text target**: title and description are written to `activity_social`
      first, always. A per-source target (item 40) may also promote them to
      `activities.name`/`description`; the default is social, because a
      promoted title feeds `classify()` and can flip a run's category
      ("Race you to the bakery" → race, a quality session). Descriptions do
      not feed the classifier.
    - **Gear**: exact normalized name links to existing equipment; an unknown
      name creates `strava:gear:<slug>` with the CSV brand/model; a matched
      row is never rewritten. The CSV has no gear distance or retirement date,
      so derive distance from the linked activities.
    - **Real export (Nov 2026)**: the 2026 archive is wide (`Distance` and
      `Elapsed Time` repeated, the second `Distance` in metres) and its
      `Activity Date` is the account timezone (UTC here). Applied: 2,554 of
      2,590 social rows, 35 unmatched (mostly other sports or genuine distance
      disagreements), 1 ambiguous; 5 bikes, 3 new equipment rows, 2 linked,
      64 activity links. A re-run is a no-op for social rows.
    - **Remaining**: optionally add the API for continuous sync and comments.
      The Strava-only creation question is settled — every source that yields
      activity rows may create, the per-source policy decides (item 40), and
      this athlete's config keeps Strava at `ignore`.
    - **API, deferred**: OAuth refresh token; app creation requires a Strava
      subscription in 2026; single-player reads are 100/15 min and 1,000/day.
      `suffer_score` is not `training_load`.
17. **Inputs vs projections: the manual layer, derive check and rebuild**
    (core + import + maintenance; phase 2, before item 38). Principle 3 stays:
    ownership is owner-based with per-field ranked exceptions and a review item
    on disagreement — no global source order. The ownership pointer is an
    **input** (a recorded decision); the canonical row is a **cache** rebuilt
    from inputs: payloads, pointers, manual edits, links, exclusions and review
    answers. The manual layer, the declared mapping, the derive check and the
    rebuild have landed; item 34's overlay export and fresh-database proof
    remain.
    - **Manual input layer (done Nov 2026, schema v23)**:
      `activity_manual_fields` holds one row per `(activity, field)` with
      either a `value_json` (a manual value) or an `owner_source` (a manual
      ownership decision), never both. `set_manual_field` keeps the derived
      pointer and its snapshot; `clear_manual_field` restores it (or the
      column default), so the stale-value bug is gone. Triage `(t)` records an
      owner patch for every field the force took, and another source can no
      longer override it. The migration copied the 73 existing manual edits.
      Force decisions made before this change are indistinguishable from a
      normal source win and cannot be recovered.
    - **Declared mapping (done Nov 2026)**: `hobbyjogging_import.derive`
      declares `FIELD_MAPS` per source (Intervals, FIT, Runalyze, Strava) and
      `SHEET_MAPS` per worksheet, with named transforms for units, sport
      vocabulary, dates and the device id. Contract tests compare every map
      with its importer, so a remap is a one-line, reviewable change.
    - **`verify_canonical` (done Nov 2026, read-only)**: derives each owned
      field from the manual patch → owner patch → stored pointer → payload and
      diffs it against the stored value. On the real DB: 4,143 activities,
      68,001 owned fields, **0 drift, 0 dangling, 0 unmapped**. It is the gate
      before a rebuild; run `maintenance run verify_canonical`.
    - **`recompute_canonical` (done Nov 2026)**: projects every owned field
      from the manual value, owner patch or stored pointer and writes it back
      through `project_activity_field`. On the real DB it is a no-op: 68,001
      fields, 0 written, 0 dangling. It never re-decides ownership and never
      touches links, exclusions, review answers, child tables or entity rows;
      manual edits are applied last. A mapping change is now a recompute, not
      a re-import.
    - **Documented**: ARCHITECTURE gains the inputs/projections paragraph; the
      pointer is described as a decision, not a derivation.
    - **Not doing**: a total priority order, a `redecide_field_owners` replay
      and a virtual read path. The pointer stays the decision of record; a
      rebuild that wants to change it is a separate, explicit task.
    - **Companion**: item 34 exports the overlay and proves the rebuild on a
      fresh database; item 38 consumes the mapping for `activity_metrics`;
      item 40 shows the mapping and the policy in the settings report.
    - **Order**: manual layer → mapping → `verify_canonical` → rebuild (all
      done). Item 34 and item 38 consume the result.

20. **Intervals' own metrics as a cross-check** (lab first, then reports; any
    time). The payload carries `decoupling`, `efficiency_factor`,
    `icu_intensity` and `icu_variability_index`, computed independently of
    ours. Compare them with our efficiency and intensity on the same activities
    to catch a formula bug before adding another derived number. Follows the
    metrics gate: a lab script first, a card only if it earns one.

62. **Session metric charts** (reports; small, phase 3, after item 38).
    `activity_metrics` now carries cadence, stride, running dynamics, power,
    calories, GAP and altitude, and the session report prints the two lines.
    What remains from item 38 is the visual layer: cadence/stride trends,
    a power or dynamics scatter, and calories/altitude over time, all over
    stored data. No schema change; follow the report parity rule (CLI and
    dashboard), and keep derived metrics (decoupling, efficiency, critical
    speed) in the lab with a card rather than adding them here.

64. **Pace/HR outlier calibration** (lab + import; after the lab). The first
    pass at 3.5 MAD / 12 bpm flagged 37 gross points, many legitimate, so the
    rule is not enabled. Calibrate on steady easy/recovery runs, excluding
    trail, race and interval sessions and explaining heat/elevation, then add
    the review rule only if the steady subset is clean. Evidence belongs in a
    lab script and a metric card first.

65. **Localhost write UI for the data brush** (reports + import; phase 4,
    after the CLI brush). Phase 3 closes on the CLI; this is the comfort layer
    for the recurring [data brush](DATA_BRUSH.md), not a general editor.
    - **Scope**: queue-first triage (next/skip/resolve/ignore/exclude/accept
      suggestion/pick value/trust source), filters by category/cause/source/
      sport/year and date/name search (item 60), batch actions with a
      confirmation and a manifest, a provenance dossier (side-by-side values,
      derived markers, edit history, links), health drill-down and the
      corrections list (item 57).
    - **Shape**: server-rendered forms on `127.0.0.1`, one user, no auth, no
      SPA, no client-side data fetching; reuse the existing HTML renderer and
      the CLI's write functions. Every action appends `edit_log`; the CLI stays
      the reference and the phone stays read-only.
    - **Placement**: keep it in the import package until a second consumer
      justifies `hobbyjogging-app` (item 1's placement rule). It must never run
      its own SQL or analysis.
    - **Build after a CLI-only brush** and implement only the friction that
      brush exposes — most likely batch decisions, filtering and provenance.
    - **Acceptance**: a 30-minute brush session with no terminal: duplicates,
      conflicts and coverage gaps triaged; every action visible in `edit_log`;
      the CLI and the browser agree on the numbers.
    - **Not first**: a generic activity form, charts, planning, or write-back
      to platforms.

66. **Secondary equipment link** (import + core; small, any time). `activity
    edit --equipment` replaces the manual set and makes the first id primary,
    so a trailer cannot be appended without promoting the bike to a manual
    link. Add `equipment link <activity> <equipment> [--role secondary|primary]`
    with `--note` and `--dry-run`, plus `equipment unlink <activity>
    <equipment>`; a manual link wins, a secondary append leaves the primary
    untouched, and the role is explicit. Resolve the activity by id, date,
    `last` or name (item 60).
    - **Acceptance**: Bob can be appended to a ride that already has Katy
      primary; the primary is unchanged; a re-run is a no-op; an unknown
      activity or equipment fails clearly; the link survives a reimport.

67. **Duplicate start-time gate** (import + maintenance; after the brush). The
    detector pairs same-day activities within the distance/duration/HR
    tolerances without requiring close starts, so a morning and an evening
    commute can pair. Live examples: item 1353 (two rides 8 h apart) and 1352
    (two runs 8.6 h apart). Require a start within ±15 min, or a missing
    precise start on one side (sheet rows), before an item opens; keep the
    same-day fallback only for the missing-start case.
    - **Acceptance**: 1352/1353 are not created, the true surf pair (delta 0)
      is, a sheet row without a start still matches, and the re-run is a no-op.

68. **Shoes are never linked to rides** (import + maintenance; bug, small). The
    sheet's `Schuhe` column is linked regardless of sport, so Lunge Fis is the
    primary equipment on two rides (2020-08-07 Afternoon Ride, 2021-03-20
    Lunch Ride) and its usage includes 36 km of cycling. A hike (2020-08-25)
    also carries the shoe and is fine: walking wears the shoe.
    - **Rule**: the sheet importer skips `Schuhe` for the ride sports (`ride`,
      `mtb_ride`, `gravel_ride`, `virtual_ride`); other sports keep the link.
    - **Backfill** `drop_ride_shoe_links_v1`: remove the existing source shoe
      links on rides (two rows) through the writer, dry run first; never touch
      a manual link.
    - **Acceptance**: Lunge Fis has no ride links, its usage km is running plus
      hiking only, a re-enabled sheet import does not recreate them, and the
      hike link stays.

69. **Equipment from tags** (core + maintenance; small). 124 activities carry
    a `Thule` tag (121 `Thule`, 3 `thule half half`), but only 74 link the
    Thule trailer; 43 have no equipment at all and 7 have only a shoe or bike.
    The tag is the evidence that the trailer was used, on runs and rides.
    - **Mapping**: tag → equipment, starting with `Thule` and
      `thule half half` → the `Thule` trailer (resolved by normalized name),
      code-level beside the tag lexicon until a second athlete needs it
      data-driven.
    - **Recompute** `equipment_from_tags_current`: for each activity carrying a
      mapped tag, link the equipment as **secondary** when another item exists,
      **primary** only when it is the only item; source `tag`, idempotent,
      never displacing a manual or existing primary; skip excluded activities.
    - **Audit**: list tags that look like gear but have no mapping, so a new
      trailer or tag is visible.
    - **Acceptance**: all 124 tagged activities link Thule; a shoe-primary run
      gets Thule secondary; a no-equipment run gets Thule primary; a manual
      link is untouched; a re-run is a no-op.

70. **Equipment usage counts every link** (core; bug, small migration). The
    `equipment_usage` view joins `activity_equipment` with `role='primary'`, so
    secondary equipment shows zero usage: the Thule trailer has 75 secondary
    links and Bob 21, both appear with no activities or km in the gear report.
    - **Fix**: count every link per equipment (the role is identity, not
      usage); replace the view in a migration (schema v30) and update the
      tests and gear-report expectations.
    - **Check**: the only secondary links today are trailers (`other`: Thule
      75, Bob 21), so no shoe or bike usage changes; a future secondary shoe
      would count too, which is correct for "times used".
    - **Acceptance**: Thule and Bob show their activity counts and km; a
      primary-only equipment is unchanged; `verify_canonical` is unaffected.

71. **Resolve the evidence classification backlog** (maintenance + import;
    small, after the brush). The 549 open `workout_classification` items break
    down as 303 tag evidence refining a **classifier-stored** set (211 a
    different method, 92 a more specific target), 17 generic tag-vs-classifier
    (`other`), 37 tag-vs-sheet and 192 comment evidence. Only the first group
    is a real improvement; the rest are noise because a comment or a generic
    tag cannot outrank a stored set.
    - **Order**: after item 72 (the drills mapping), so the LTT evidence is
      not resolved as threshold.
    - **Policy**: a specific tag refines a **classifier projection** (write
      `source='tag'`); a sheet or manual input wins over tag and comment
      evidence; a comment only fills an empty classification; `other` evidence
      never overrides a specific target.
    - **Race-day tags are context**: `Raceday` is used on 28 of its 29
      activities as the warm-up or cool-down around a race, not on the race
      itself; the race session gets `race` from the event/result link
      (`race_link`), so a race-day tag must not set `race` on a warm-up.
    - **One-time task** `workout_classification_evidence_v1`: accept the 303
      tag-specific sets, close the 246 with a policy note, dry run first.
    - **Rule fix**: the evidence task stops opening these items — a specific
      tag refines a classifier set in place, comments only fill empty.
    - **Acceptance**: open `workout_classification` is 0; only
      classifier-stored activities change; sheet/manual sets are untouched; a
      re-run is a no-op.

72. **Drills method and running-technique tags** (core + import + maintenance;
    small, before 71). The live tags `LTT` (28, 2021–2025) and `Lauftechnik`
    (5) describe running drills, but `LTT` is currently mapped to
    `continuous` + `threshold` in the tag lexicon, and there is no `drills`
    method. `Lauf-ABC` is not in the data yet but belongs to the same family.
    - **Vocabulary**: add `drills` to `WORKOUT_METHODS` beside `strides`; it is
      not a quality method by itself (a drills-only session stays non-quality;
      drills plus intervals stays intervals). Include the aliases `drill`,
      `lauf-abc`, `lauf abc`, `lauftechnik` and fix `ltt`.
    - **Additive**: drills (and strides) are additions to a session, never a
      replacement. The evidence proposal unions them into the stored methods
      and opens no conflict item for the additive method alone; a manual set is
      left for the human.
    - **Backfill** `drills_from_tags_v1`: add the method to the 33 tagged
      activities with non-manual sets (28 LTT + 5 Lauftechnik; the one manual
      set is skipped), source `tag`, idempotent; the LTT tag must no longer
      propose threshold.
    - **Acceptance**: the LTT/Lauftechnik runs carry `drills` plus their run
      method, the category is unchanged (easy/interval), the reports show
      `Drills`, a re-run is a no-op, and the 549 queue no longer contains a
      threshold proposal from `LTT`.

73. **Place tags become routes** (core + import + maintenance; small-medium,
    after the brush). 393 active activities (2021–2026) carry one of 30
    geographic tags — `Wienerberg` 44, `kanal` 43, `hauptallee` 34, `Arsenal`
    30, `Prater` 27, `donaukanal` 27, … — and **none links a route**;
    `activity_routes` is sheet-only and stops in 2019 (384 links, 36 routes).
    Runalyze `recurring_route` is not a substitute: 2,777 payloads carry 2,504
    mostly-singleton ids.
    - **Kind**: add `place` to the tag lexicon for the geographic tags; the
      remaining unmapped tags (people, errands, events) stay unmapped.
    - **Identity**: a tag-derived route is source-scoped
      (`runalyze:tag:<slug>`) and never merges with a sheet route; normalize
      obvious aliases (`kanal`/`donaukanal`, `Wienerberg`/`Wienerbergteich`)
      in one small map beside the lexicon.
    - **Backfill** `routes_from_place_tags_v1`: create the route and link the
      activity with `source='tag'`, idempotent; a manual route link wins.
    - **Acceptance**: modern route coverage is non-zero and the session report
      shows the place; the sheet routes are untouched; a re-run is a no-op.

74. **Strava comment evidence** (import + maintenance; small, after 71). The
    evidence task reads only `activities.description`; the 538 Strava
    `activity_social` descriptions (2021–2026) are ignored. 83 carry an
    interval pattern, 22 LT/subT and 19 tempo/threshold; they yield 103
    proposals, all on activities that already have a stored set, so item 71's
    "a comment only fills empty" would close every one. 59 proposals are
    material: 44 on a `backfill`/`classifier` set, 15 on a manual one.
    Examples: 2023-10-31 stored `long_run/base` vs "3x1.6 Threshold hopping";
    2024-08-13 `continuous/threshold` vs "12x200m in 33-35''".
    - **Source**: read the per-source `activity_social.description` for run
      sports, not only the canonical field.
    - **Precision first**: fix `description_proposal`'s first-match order
      (`Wechseltempo`/`Fahrtspiel` hit tempo before fartlek) and ignore
      alternatives and negations ("statt Wettkampf", "instead of", "not");
      require an explicit interval pattern or target word. Today it proposes
      `race` for a music/recap sentence and `threshold` for "zu hügelig für
      gleichmäßiges Tempo".
    - **Policy**: a structured comment may refine a `backfill`/`classifier`
      projection and opens a review item; it never overrides a manual or sheet
      set, and `other` never overrides a specific target.
    - **Acceptance**: the material backfill cases are triaged once; no manual
      or sheet set changes; the known false positives are tests; a re-run is a
      no-op.

75. **Weather temperature is the watch, not the air** (core + import +
    maintenance; bug, small). `activity_weather.temp_c` comes from Intervals
    `average_temp` on 2,834 of 2,988 activities and from the sheet
    `Temperatur in °C` on 154. `average_temp` is the device/watch
    temperature: on the 585 activities that also carry a sheet value it is
    warmer on 571 (+6.3 °C mean, up to +25.8 °C); the winter bias is +9…+11 °C
    (Dec–Feb) against +3 °C in summer, and the device `max_temp` reaches
    27–30 °C on December runs. The sheet has 739 ambient values (2011–2021),
    but `activity_weather_v1` orders Intervals first and the writer keeps the
    first source, so the watch value wins on all 585 overlaps. FIT
    temperature is not read at all; Runalyze weather is not implemented.
    - **Rule**: `temp_c` is ambient air only. The Intervals importer writes
      `average_weather_temp` when `has_weather` and never `average_temp`; the
      sheet writes its manual value.
    - **Backfill** `weather_ambient_v1`: rewrite `temp_c` from the sheet
      payload where present (739 rows); clear the device-only rows, so the
      report stops showing the watch value as air temperature. The raw payload
      keeps `average_temp` for diagnostics.
    - **Decided**: no `device_temp_c` column and no watch line in any report;
      the device value stays only in the raw Intervals/FIT payload. A weather
      row without an ambient value is not shown at all.
    - **Report**: no ambient value means no weather line; never fall back to
      the watch.
    - **Acceptance**: no `temp_c` comes from `average_temp`; January rows no
      longer read ~13 °C; the 739 sheet values survive; the health coverage
      shows the truthful share; a re-run is a no-op.

76. **Ambient weather from a historical source** (new source; phase queue,
    after 75). After 75 only 2011–2021 has an ambient temperature (the sheet);
    2022+ has none. Intervals' own `average_weather_temp` is the cheapest
    path: it is in the payload schema but `has_weather` is false on all 2,862
    rows today, so first check the account's weather feature; if it stays
    empty, fetch a historical archive.
    - **Source**: one request per outdoor activity at its start coordinate
      and hour (Open-Meteo archive is free, no key), stored as a source record
      so a rebuild reproduces it; round the coordinate (~1 km) and hour to
      cache and deduplicate.
    - **Fields**: temperature, feels-like, humidity, wind speed/gust/degree,
      pressure, cloud cover, condition and is-day; metric units in
      `activity_weather`.
    - **Identity**: source-scoped (`open-meteo` or `intervals`); it owns the
      ambient fields, the sheet is the fallback, the device value is not
      ambient.
    - **Scope**: outdoor sports with a start coordinate; an indoor activity
      stays empty; a missing coordinate reports a gap.
    - **Acceptance**: 2019–2021 station values agree with the sheet within a
      few degrees; a January run reads a plausible ambient value; an indoor
      ride stays empty; a rebuild reproduces the rows from the cache.

77. **Manual bike assignment for rides without one** (import + maintenance;
    small, after 66). 236 active rides have no bike link: 2013 3, 2019 23,
    2020 61, 2021 11, 2022 15, 2023 53, 2024 60, 2025 5, 2026 5. Two carry
    only the Lunge Fis shoe (item 68 removes it). The sheet ends 2021, the
    Strava gear field is empty for 2022–2023, and Runalyze has no 2023 links,
    so the usual bike is the athlete's knowledge, not a payload.
    - **Command**: `equipment assign <bike> --from <date> --to <date>
      [--sport ride|mtb_ride|…] [--dry-run]`, plus an explicit id list. It
      links the bike as primary and manual only where the activity has no
      bike; an existing bike or manual link is untouched; a shoe-only ride is
      left for item 68.
    - **Mapping**: filled per period in the private curation list (e.g.
      2023-05-05..2023-11-24 → Mery); the command prints the affected rides
      and skips the rest.
    - **Acceptance**: a dry run lists the rides per period; only gaps change;
      `is_manual=1`; a re-run is a no-op; a trailer ride keeps Bob secondary.

78. **Import the Leistungstests sheet** (core + import + maintenance; schema +
    backfill, not small). The sheet importer supports only `Rohdaten`,
    `Alternativtraining` and `Material`. The `Leistungstests` tab is unused and
    holds 37 test/race blocks (2011–2021): 538 per-km splits, 143 with HR, and
    18 blocks with a place/result comment ("Gesamt 5.", "Gesamt 173."). The
    general comments already sit in `activities.description` from `Rohdaten`;
    the new value is the pre-2019 race history, the places and the splits. 27
    blocks match an activity by date/distance; 10 need a manual mapping (a test
    inside a longer activity). The tab is uneven: 16 blocks have date cells, the
    rest text dates, one relay block is a 5-row placeholder, and two blocks have
    broken formulas (`#DIV/0!`, `/`, zero times).
    - **Input**: store each block as a `sheet` source record
      (`performance_test`) with the raw date, distance, target, comments and
      splits, so the sheet stays an input and a rebuild reproduces it.
    - **Race results**: for a race block, create or complete a `race_results`
      row (source `sheet`, `officially_measured=0`), with the official
      distance/time from the block, the place from "Gesamt N." and the result
      comment as notes; never overwrite a Runalyze row. This fills 2011–2018,
      where `race_results` is empty (the 37 rows start in 2019-04-07).
    - **Splits**: project the per-km rows as laps with `source='sheet_test'`.
      `activity_laps` is device-only and `replace_activity_laps` deletes all
      rows, so make the lap write source-scoped (add `source`, migration) or
      use a separate test-splits table; the session report already renders a
      lap table.
    - **Tests**: tag a non-race block `leistungstest` (context) so it stays out
      of race stats; a block that matches no activity is reported, not guessed.
    - **Acceptance**: 2011–2018 races and places appear; existing 2019+ race
      results are unchanged; the splits show in the session report and total the
      block time; broken blocks are skipped and listed; a re-run is a no-op.

79. **Clickable gear pages** (reports; small). The Gear tab lists gear in a
    table, but the name is plain text; the dashboard already renders
    per-activity, per-race and per-event pages. Add a `gear/<item>` page,
    linked from the Gear table, with the totals (sessions, km, km/month, first
    and last use), a mileage-over-time chart, the activities and their role
    (primary/secondary, each linking to the activity page), co-used gear (e.g.
    Bob with Katy), target/wear and retirement status.
    - **Shape**: reuse `equipment_usage` and `DataSource`; no new SQL; a
      retired or zero-use item still gets a page with an empty state; the page
      shows the subcategory once item 81 lands.
    - **Acceptance**: every gear row links to its page; the totals match the
      Gear tab; the demo builds; the pages are static files beside `gear.html`.

80. **Weight chart in wellness** (reports; small). `WellnessDay.weight_kg` is
    stored (358 values: 2012–2013 and 2023–2026, with a nine-year gap), but the
    recovery page plots only HRV, resting HR and sleep. Add a body-weight card:
    points and a 7-day mean on their own kg axis, with the gap left as a gap;
    no readiness bands.
    - **Surfaces**: the recovery tab and the recovery report summary; add a
      reference-catalogue row in `docs/METRICS.md` (definition, source, gap),
      not a promoted card unless weight becomes a metric.
    - **Acceptance**: the points match `wellness_days`; a window without weight
      shows an empty state; the gap is not interpolated; the HRV/RHR panels
      keep their scale.

81. **Gear subcategories and target mileage** (core + import + reports;
    schema migration, not small). `equipment.type` is only shoe/bike/other, and
    every shoe without an explicit target gets the single 800 km
    `DEFAULT_SHOE_TARGET_M`. Add a subcategory — race, trail, daily,
    supertrainer, barefoot, hiking, … — with a default target per subcategory
    and `target_distance_m` as the per-item override.
    - **Schema**: additive `category TEXT NOT NULL DEFAULT ''` on `equipment`
      (migration); an empty category keeps today's single default.
    - **Vocabulary**: one small map in core (labels and default targets), like
      `sports`; the athlete's numbers live there, not in the report code.
    - **Writer/CLI**: `equipment add/edit --category`; a manual category is
      never overwritten by a later sheet or Runalyze gear import; `equipment
      list` groups by it.
    - **Reports**: the Gear tab groups shoes by subcategory, colours the
      mileage chart by it, and marks a default target versus an explicit one.
      The usage view still counts every link (item 70).
    - **Acceptance**: a race shoe with the race default shows that target; an
      explicit target wins; a reimport keeps a manual category; the Gear tab
      groups by subcategory; existing totals do not change.

23. **Portability for a second user** (core + import + reports + CI; phase 2 —
    the acceptance checklist for the phase-2 exit test). The model is portable
    already: canonical activity, owner-based fields with ranked exceptions, the
    migration machinery, the importers, reports over `DataSource`, the
    synthetic demo. What is personal is the defaults. **One athlete per DB**;
    the second athlete's data stays private; there is no multi-tenant schema.
    Fix the generic code, do not fork it.

    **Target profile** (the real athlete's data comes later): Garmin, Runalyze
    and Strava — no Intervals, no sheet. Phase 2 proves the path on a fresh DB;
    the athlete's own run is the later validation. Athlete 2's profile is
    **Runalyze + Garmin, no Intervals**: no activity names, no thresholds or
    zones, tags plus Runalyze's own workout type, and FIT laps for structure.
    It is the acceptance case for 2b (items 49, 51, 50, 52 and 53), and the FIT
    import supplies the device serial, max HR and laps.

    - **Setup (import + CI)**
      - [x] `init` creates and migrates a fresh DB explicitly; a second run is
            a no-op.
      - [x] `doctor` checks `uv`, the DB path and writability, the schema
            version, the FIT directory, that each credential is present, a
            bounded liveness probe where the API allows one (Garmin token
            exchange, Runalyze ping), pending data migrations, whether a
            configured source has gone stale, and the sources file, and names
            what is missing.
      - [x] `sources.toml` alone selects the sources: Intervals and the sheet
            disabled, Runalyze `review`, Strava `create` or `ignore`.
      - [x] `sync.sh` skips an unconfigured source instead of failing on an
            absent credential, and never assumes Intervals.
      - [x] a pull-request workflow runs the four suites plus the demo build;
            today CI only covers pushes to `main`.
      - [x] an MIT `LICENSE`, `.env.example` and a README first-run path (GDPR
            export or `garmin fetch` → `sync`).
    - **Ingestion (core + import)**
      - [x] Garmin FIT is the only device source: `moving_s`/`elapsed_s` fall
            back to FIT through the existing ranked authority, with no code
            change.
      - [x] device identity is FIT-first: app names never become devices, a
            provider name claims the unique FIT device of its model, and an
            unused provider row is soft-excluded (landed).
      - [x] Strava `create` makes a summary activity using the configured
            timezone; title and description follow the text target.
      - [x] Runalyze honours `create|review|ignore`; unmatched rows become
            review items when set to `review`.
      - [x] gear works without a sheet: exact name → new row → ambiguous item,
            with the co-occurrence branch simply never firing.
      - [x] race results arrive without Intervals (Runalyze); no training
            periods and no planned events is an accepted empty state, not an
            error.
    - **Analysis and reports (reports)**
      - [x] no Intervals assumption in the read path: missing thresholds,
            zones, events or wellness degrade to an explicit "not available",
            never a wrong number or a crash.
      - [x] chart ceilings come from the data (landed); the known personal
            constants that remain are `COMPARE_VISIBLE_YEARS`, the compare colour
            anchor and `RACE_DAYS`.
      - [x] the analysis defaults (RPE > 3, 90-min long run, 40–75 min
            efficiency band, subT buckets, 5-bpm HR conflict, 10 %/20 m
            elevation) are one documented module of defaults, not laws.
      - [x] the demo builds from the synthetic athlete and renders every tab,
            so the second athlete's empty paths are exercised too — including
            the effective-VO2max overview and methods card, which is the
            zero-credential install proof.
      - [x] the Runalyze+Garmin profile renders categories, laps/reps, zones,
            load and wellness (items 49–53), and the demo still covers the
            empty paths.
    - **Language floor**: [x] `requires-python` is `>=3.12`; the suites pass
      there and the pull-request workflow runs on 3.12.

    **Acceptance passed 2026-11-24.** A fresh DB with athlete 2's Runalyze +
    Garmin data, no Intervals and no sheet: `init`/`doctor`/`sync` ran on the
    documented path, the dashboard rendered categories, laps/reps, zones, load,
    wellness and races, and `verify_canonical` was clean. The two findings it
    produced (55, 56) are fixed and tested.

    **Out of scope, stated**: multi-athlete, imperial units, a hosted service,
    arbitrary platforms, a per-athlete UI.

24. **Metric catalogue** (docs; decided 2026-11-19). The registry used to
    document only what passed the lab gate, so most computed numbers had no
    reference. The decision: **one document, two jobs.**
    - `docs/METRICS.md` stays the only home. It keeps the promotion gate, the
      short cards for promoted metrics, the rejected list, and a
      **`## Reference catalogue`** table: one line per number or method —
      definition in a phrase, the module that computes it, where it renders.
      It is written; keep it current when a number is added or removed.
    - **No `docs/ANALYSIS.md`.** A second document would restate the same facts
      and rot in a different place.
    - **No dashboard Metrics tab.** The Docs tab already publishes
      `METRICS.md`, so a tab would render the same file twice. Reports item 7
      has no input left under this decision and should be retired there.
    - **No generated registry and no prose-grep test.** A test that asserts
      every `analysis/` module is named is fragile and proves only that a name
      appears; the catalogue is hand-written and checked in the periodic
      cleanup (item 28).
    - **Where the detail lives**: a formula, its validation and its caveats
      belong to the promoted card or to the module's docstring — the catalogue
      only names the path. Paper references belong to the card that promotes a
      number, not to a shared bibliography; coaching conventions say so.

25. **LLM coaching workflow** (root + reports; phase 4). The workflow exists
    but lives
    outside the repo: another model reads the Markdown reports and plans through
    a terminal agent, discusses them, and writes a coaching note as Markdown
    that could be shown in the dashboard. Nothing defines where that note lives,
    what shape it has, or how the dashboard finds it. ARCHITECTURE already plans
    a deterministic "LLM coaching bundle" and an append-only decision log; this
    item makes the real workflow first-class and feeds that plan.
    - **Notes**: a `coaching/` directory of committed Markdown notes, one file
      per session, with front matter (`date`, `period`, `focus`, linked
      events) and sections (state, assessment, decision, next). The decision
      section *is* the append-only decision log ARCHITECTURE asks for.
    - **Input**: the model reads reports through the CLI on demand (`session`,
      `period`, `races`, `plan`) rather than a giant dump. A
      `reports.sh coaching-bundle` command would emit a compact digest — goals,
      planned events, load and recovery trends, key sessions, explicit caveats
      — plus pointers, bounded in size and reproducible for a date range.
    - **Continuity**: a session starts by reading the last N notes, so a
      recommendation and whether it was followed carries over; the next note
      records the outcome.
    - **Write safety**: the model never writes the database. Reports stay
      read-only and the only write is the note file.
    - **Dashboard**: a Coaching tab with the latest note rendered and an index
      of past ones, through the Markdown-to-HTML path the Docs tab already
      uses. The public demo builds from the synthetic database and must not
      ship real notes — exclude `coaching/` when a demo label is set, or ship a
      synthetic example.
    - **Later**: plans authored as events instead of prose, which ties into the
      platform-independence item.
    - **Open questions**: committed notes or local-only; one file per session
      or per week; JSON, Markdown or both for the bundle; and whether the tab
      is "Coaching" or part of "Docs".

26. **Keep the demo data current** (reports; recurring — the phase-2 install
    fixture and each release). The synthetic demo is
    now both the public face and a smoke test — it builds in CI on every
    relevant push. But `demo.py` predates the newest features, so a tab or chart
    that reads a new field (max HR, elevation, weather, devices, routes, Strava
    notes, thresholds and zones, fartlek) renders empty and the demo stops
    proving the feature works.
    - **Rule**: a change that adds a user-visible field, chart or tab updates
      `demo.py` in the same work; the demo build is part of the acceptance
      check, and it already runs in CI.
    - **Coverage check**: a `demo-db --check` (or a test) asserting that every
      report and dashboard tab renders non-empty content from the demo
      database, so a feature without demo data fails loudly instead of showing
      a blank card.
    - **Recurring review**: at each release tag (item 22) and schema bump,
      re-read the feature list against the demo and fill the gaps. Keep the seed
      fixed so the output stays deterministic and diffable.
    - **Open**: how realistic the synthetic athlete should be — a plausible
      build, a taper, a race, a couple of devices — versus how much to leave
      empty so the "no data" paths stay exercised.

27. **Performance budget** (reports + import; phase 4, watch, do not optimise
    blindly). Sync and dashboard run times grow with the data. They are not yet
    a nuisance, so the work is to measure, record and notice — and only
    optimise when a ceiling is crossed.
    - **Baseline** (real DB, 4,136 activities): a full dashboard build takes
      **~5 s and issues 6,803 SQL queries** — 4,457 `activity_intervals` calls,
      219 `activities(start, today)` range loads and 95 lap loads.
    - **Instrument**: a `--timing` summary on the CLI with per-phase numbers
      (read, analysis, charts, write), plus one line at the end of a dashboard
      build and of a sync, so a regression is visible in the log.
    - **Budget**: a ceiling (for example dashboard under 15 s on the real DB)
      that counts as a bug when crossed; re-record the numbers at each release
      tag (item 22).
    - **Suspects, in order**: per-activity interval/lap lookups inside loops;
      each dashboard section loading its own `activities()` range (219 calls
      per build); per-activity `classify()`; chart rendering.
    - **Cheap first**: a read-only per-build cache on `DataSource` —
      `activities()` by range and `activity_intervals()`/`activity_laps()` by
      id — removes most of it without touching the analysis code. Do that
      before rewriting queries.
    - **Tests**: bound the query count on the demo database, so a new N+1 fails
      the suite instead of the wall clock.

28. **Periodic cleanup pass** (all packages + docs; recurring). Nothing guards
    readability automatically: no linter is configured, and documentation
    drifts toward duplication. Human review is the guard, and the cadence is
    event-driven rather than calendar-based.
    - **Triggers**: a **phase boundary** (one session); **before extending a
      package** (the cheap one — review the package you are about to grow);
      **each release tag** once item 22 lands (today the phases are the
      anchor); and the **boy-scout rule** in every session.
    - **File budget**: a source file stays under 1,000 lines. A new file over
      it is a design decision, not drift; the known giants are a short
      allowlist that only shrinks (item 45, `tools/check_size.py`). A package
      that grows more than a quarter in one phase gets a pass before the next
      phase starts.
    - **Docs, done once (2026-11-19)**: the root `## Done` list is a short
      "recently landed" list and the landed Runalyze milestone is a summary
      rather than a phase log. Package lists trim their own `## Done`
      sections; they are not root edits.
    - **Docs, every pass**: sweep for facts stated twice (the phase paragraph,
      the roadmap pointer, the schema version) and for entries that restate
      git history.
    - **Code**: dead exports (start with `analysis/__init__`), unused flags and
      parameters, duplicated helpers, and a file that has outgrown its
      purpose. No `TODO`/`FIXME` markers exist today — keep it that way.
    - **Mechanical guard**: `tools/check_size.py` (item 45) fails a new
      oversized file. `ruff` remains an open question — it would catch unused
      imports and enforce formatting, at the cost of a first pass of violations
      and config churn; decide after phase 2.
    - **Acceptance**: no dead exports, no duplicated doc sections, no file that
      has outgrown its purpose without being split or trimmed.

29. **Detach the lab into `laufen_private`, keep the bench** (root + reports;
    done 2026-11-24). The lab's scripts and notebook carry personal research
    and findings and no longer live in the project repo; the bench ships so
    another user can run their own.
    - **Split (done)**: `experiments/` keeps the rules and `template.py`;
      `lab.sh`, the gate in `docs/METRICS.md` and the Lab tab stay. The 19
      scripts and the candidate table/notebook moved to
      `~/projects/laufen_private/lab/` (the existing private repo).
    - **Env vars (done)**: `shell.py` writes plots to
      `HOBBYJOGGING_LAB_OUTPUT_DIR` (default `data/lab`);
      `HOBBYJOGGING_LAB_DIR` now names the notebook and defaults to
      `experiments/`, so a fresh clone still works.
    - **Dashboard (done)**: a local build renders the shipped bench rules plus
      the notebook and scripts from `$HOBBYJOGGING_LAB_DIR`; a demo build never
      reads that directory and shows the bench guide only.
    - **Evidence split (done)**: `docs/METRICS.md` keeps the contract, the
      baselines and the aggregate statistics; the private narrative is the
      notebook, referenced by name.
    - **Risks accepted**: two repos to clone on a new machine; `lab.sh` fails
      clearly when an explicit lab dir is missing; CI never needs the private
      repo; the moved scripts keep their content but not their in-repo
      history.
    - **Related**: item 23 (its lab case), item 26 (demo upkeep) and item 25 —
      the coaching notes will live in the same private repo.

31. **Efficiency over all activities** (lab first, then reports and the card;
    any time after the gate). The steady aggregate stops at 75 min (`STEADY_DURATION_BAND`), so a long run
    contributes nothing to the trend; it used to start at 45 min as well.
    - **40-minute floor (landed).** The duration model gives `+135/T` bpm, so a
      40-minute run reads about 1.5 % lower than a 60-minute one; inside the
      40–75 min band that spread is acceptable while the band is printed. On the
      real log it added 26 steady runs over the last year (108 → 134) and 314
      all-time (1,165 → 1,479), moving the aggregate by 0.002 and 0.001. The
      card now says 40–75 min.
    - **An all-runs series.** Every run with HR, distance and duration, as a
      second labelled line beside the steady aggregate — never merged into it.
      The card's Comparability caveat says whole-session interval averages are
      not comparable to steady runs, so the two have to stay visually distinct
      and separately labelled.
    - **Lab first**: does the all-runs series track the steady one, and is it
      more reliable (more n) or noisier (protocols mixed)? Split-half
      reliability and a year-by-year comparison, per the gate in
      `docs/METRICS.md`.
    - **Card**: if it lands, the efficiency card gains the 40 min floor, the
      all-runs series and the reason they are not merged.
    - **Split**: the implementation lives in the reports list, under the
      efficiency-scope item; the lab files the candidate row in
      `experiments/README.md` and runs the split-half comparison. The root
      session updates the card.

32. **Explicit ownership on the todo lists** (docs + tools). Each package has
    its own `NEXT_UP.md` and the root list tags items with their packages, but
    ownership is prose: an item says what blocks it, not who owns it, and the
    numbered cross-references break silently when the root list is renumbered —
    which happened twice in one session.
    - **Check (done)**: `tools/check_todos.py` fails when a package list
      references a root item that does not exist, or when a root number appears
      twice. It runs in the CI test job, so a renumbering cannot land with a
      dangling pointer.
    - **Convention**: `AGENTS.md` says a package session starts from its own
      list and treats root items as dependencies, not work.
    - **Target format** for new or edited package items: one line —
      `Owner: <pkg> · Needs: root #N (title) · Status: blocked|ready` — so the
      state is visible to an agent that only reads the package list.
    - **Open**: whether the root items also get an owner line, and whether the
      check should compare the parenthetical title with the root item's title
      (fragile — probably not).

33. **Efficiency fallback when no resting-HR baseline exists** (reports + card;
    any time, and it helps the phase-2 athlete without wellness history).
    `robust_baselines` returns `None` for a date before the first wellness
    sample, so `excess_beats` yields `None` and efficiency is `-` for the whole
    pre-Sep-2022 log — eleven years of activities.
    - **Backward fill**: for a date before the first sample, use the earliest
      available 365-day median (the first baseline) instead of `None`. It is
      data-driven and continuous at the boundary, with no invented number.
    - **Last resort**: a configured default (for example 50 bpm) only when the
      wellness table has no resting HR at all, printed as an assumption.
    - **Mark it estimated**: the lookup returns the value plus an `estimated`
      flag, so the session report and the activities column can say "estimated
      baseline" while the trend aggregates keep using measured baselines only —
      an estimated period must not look measured.
    - **Guard**: keep `avg_hr − rhr ≥ 10` and reject a fallback outside a
      plausible 35–70 bpm range; a too-low fallback inflates efficiency.
    - **Card**: the efficiency card records the fallback, when it applies, and
      why the trends stay measured-only.
    - **Tests**: an activity before the first wellness day gets a value with the
      estimated flag; the compare and overview aggregates still exclude it; a
      fallback of 0 or 200 is rejected.

34. **Manual-layer export and rebuild check** (maintenance + core; done
    2026-11-24, the safety gate). The raw layer is preserved and SQLite stays
    readable, so the data does not disappear; what dies with the code is the
    *meaning*: which values were overridden, which sessions were deliberately
    excluded, which conflicts were decided.
    - **Export (done)**: `maintenance export-manual` writes JSONL — the
      `activity_manual_fields` overlay, manual workout sets, manual tags,
      manual equipment links, activity exclusions and the ignored/resolved
      review answers — and `import-manual` re-applies it to a database with the
      raw/structural layer. The format has a version header, sorted records and
      no timestamps, so it is diffable. On the real DB: 73 manual fields,
      529 manual set records, 8 exclusions and 734 review answers; 1,345
      lines, about 300 KB.
    - **Rebuild proof (done)**: `maintenance rebuild --source DB` copies the
      raw records, activity identities, links, ownership pointers, devices and
      equipment into a fresh schema, applies the overlay, projects
      `local_date`/`sport` first, runs `recompute_canonical`, and diffs every
      canonical value and the exclusion set; it also checks that the FIT
      archive files the raw records point at are present. On a copy of the real
      DB: **4,149 activities, 91,278 values, 0 drift, 0 missing, 0 extra, 8/8
      exclusions, 2,864 FIT files present** in about 2 s. It does not re-import
      from the network, re-match activities or re-decide ownership; the
      pointers stay the recorded decisions, and the proof is the projection.
    - **Placement and cadence**: the overlay lives in `laufen_private` next to
      the database (`hobbyjogging.manual.jsonl`) and is exported at each release
      tag. It is not a backup; `sqlite3 .backup` remains the safety net.
    - **Not doing**: a CSV/JSON export of the whole canonical database, and
      re-importing the FIT archive just to rebuild scalar fields.
    - **Why first, though it is insurance**: it protects the decisions and the
      design claim if the project is handed over, and the empty diff makes
      every later phase confident in `recompute_canonical`.

39. **Running-only load card** (docs; done 2026-11-19). The card is in
    `docs/METRICS.md` under Promoted, with its load row in the reference
    catalogue; the reports code landed in `66dd91b` and the evidence is
    `experiments/cross_training_load.py`. The number stays only so the reports
    list's handoff pointer keeps resolving.

40. **Import policy, settings view and source configuration** (core + import +
    maintenance + reports; done). Every source that yields activity
    rows may create; what varies per athlete is policy, not capability.
    - **Done (Nov 2026)**: `SourceProfile` declares `yields_activities` and
      `creation_fields` (no create/enrich role). `sources.toml` (or
      `HOBBYJOGGING_SOURCES`) carries `enabled`, `create`, `title` and
      `description`; unknown keys and impossible values fail loudly. The
      resolved policy is printed and recorded in the import run.
    - **Policy**: `create | review | ignore` for Strava and Runalyze; the
      recording sources (FIT, Intervals, sheet) always create and use
      `enabled`. `--create` / `--no-create` override one run.
    - **Ladder guard**: create only when there is nothing to review; a
      rejected candidate becomes a review item, not a duplicate.
    - **Create paths**: Strava and Runalyze create a summary activity when
      configured (Strava needs the configured timezone; its title and
      description still go to `activity_social`). A `review` outcome queues a
      `create_activity` item; triage `(c)` creates it from the stored values.
    - **Text targets**: Strava's title/description go to `activity_social`
      (default) or the canonical `name`/`description`; a promoted title feeds
      the classifier. `sources.toml` is the switch, so no separate promote
      command is needed.
    - **Settings view**: `hobbyjogging-import sources` prints the effective
      policy; `hobbyjogging-import settings` (also `reports.sh settings`)
      renders sources, field rules, matching, review categories, causes,
      classification and the payload mapping. The report delegates to the
      import package because it owns the rules and the mapping.
    - **Remainder, decided (2026-11-19)**: the recording sources keep `enabled`
      only. A recording source's unmatched row is the recording itself, so
      "do not create" would discard the only copy of the activity; there is no
      create policy to wire. `promote_social_text` is the existing
      `sources.toml` text target, not a command. The **dashboard Settings tab**
      stays optional reports polish (the CLI report already covers the
      question); the registry extension is unnecessary because the settings
      report renders quality and causes from the import side.
    - **Not doing**: migrating FIT/Intervals/sheet onto `decide_match`, a
      primary-source rank, and an import-order key in `sources.toml`.
    - **Sequence**: done; item 23's second-athlete test is the acceptance test.

41. **Device identity for provider-derived devices** (core + import +
    maintenance; done — bug fix, any time). The reports handoff
    (`packages/hobbyjogging-reports/NEXT_UP.md`, "Handed off: device
    identity") is the evidence: two provider rows duplicate FIT devices, app
    names become devices, and the provider casing flips on refresh. The rules
    are in ARCHITECTURE ("Device identity"); this item carries the import fix
    and the backfill.
    - **Import package**: skip app names (`Runalyze`, `Garmin Connect`,
      `Strava`, `intervals.icu`) in `intervals._device_id`; require a serial in
      `fit_import.device_id_from` (a serial-less FIT upload is not a device);
      normalise the provider name to title case and never overwrite an
      existing `devices.name`; map a provider name onto the unique FIT device
      (same manufacturer and product) instead of creating an `intervals:` row.
      Ambiguous models keep the provider id.
    - **Backfill `device_identity_v1` (applied Nov 2026)**: reassign the two
      `intervals:garmin-enduro` activities — Ramsau am Dachstein Surfing
      (`31bdd2f2-949a-5971-874e-c6a2b4a810a7`, 2024-08-04) and Vienna Cycling
      (`37a1b0a9-4316-52f7-b725-1bf55883ff3b`, 2025-09-04) — to
      `fit:garmin:enduro:3386253273`; set `device_id = NULL` on Höchst Other
      (`2e7411a6-2be1-581d-b15a-7608948d4129`, 2025-07-08,
      `intervals:runalyze`). The two 2019 "Garmin Connect" activities stay
      NULL.
    - **Tail (done Nov 2026)**: `devices.excluded_at` (v24) and the
      `TrainingRepository.devices()` filter; `device_identity_orphans_v1`
      soft-excluded the two unused provider rows (`intervals:garmin-enduro`,
      `intervals:runalyze`). The device report lists the four FIT devices only;
      never hard delete.
    - **Acceptance**: the device report shows one Enduro row, no app-name
      device rows, and a re-import leaves the stored ids and names unchanged.
    - **Reports**: no change; the hover id stays for a genuinely provider-only
      device.

44. **Sync covers every configured source** (import + maintenance + reports;
    done 2026-11-24). `hobbyjogging-import sync` runs the whole configured
    pipeline and `sync.sh` adds the stored derivations and the dashboard.
    - **Done**: Garmin, Intervals, the FIT archive, a budgeted Runalyze
      `enrich --since <last success − 14 d>`, the offline `runalyze gear` and
      `vo2max` passes, race results, and the newest **unimported**
      `export_*.zip` from the Strava drop directory. A `429` or a missing
      credential is a warning with a pending count, never a failed sync.
    - **Order**: fetch → offline derive → maintenance recomputes → review scan
      → dashboard. A disabled source or a missing credential prints a skip; a
      configured source that fails is reported and the rest still run.
    - **Freshness**: `hobbyjogging_import.freshness` reads the last successful
      run per source, the imported Strava export paths and staleness; `doctor`
      reports them. A dedicated CLI report stays optional.
    - **Acceptance (verified on a copy)**: one command brings every configured
      source in; a second run is a no-op for unchanged data; removing one
      credential skips that source and leaves the others working.

45. **Readability baseline pass** (reports + tools; done 2026-11-24, phase 3
    first, reports session). The codebase was not bloated yet, but reports and
    import were two-thirds of it and two files were doing too much. Measured
    2026-11-19: reports 75 modules / 22.8k lines, import 41 / 16k, core 14 /
    6.3k, maintenance 33 / 4.6k; `charts.py` 3,610 lines, `writer.py` 2,898,
    and `analysis/__init__` re-exported 154 names.
    - **Done**: `charts.py` is now a `charts/` package split by family
      (overview, volume, load, time, subt, races, compare, gear, recovery,
      vo2max, pace/HR, common) behind the same public imports; it left the
      `check_size` allowlist, which now lists the five cohesive or mechanical
      giants (`writer.py`, `demo.py`, `triage.py`, `runalyze_import.py`,
      `format.py`). The dead `analysis/__init__` exports are gone — the surface
      is 121 names, down from 154 — and `tools/check_size.py` enforces the
      1,000-line budget with that shrinking allowlist and is wired into CI
      beside `check_todos.py`.
    - **Not now**: splitting `writer.py` (cohesive) or `demo.py` (mechanical),
      a linter, package renames, or extracting `hobbyjogging-app` — that waits
      for the front end (the `activity edit` CLI is its reference).
    - **Acceptance**: four suites green, the demo dashboard renders
      identically, the public import paths still resolve, and a deliberately
      oversized new file fails CI.

49. **Runalyze workout type → canonical sets** (import + maintenance; done
    2026-11-24). Runalyze's `type` object is the one classification signal a
    name-less, RPE-less athlete has.
    - **Done**: `hobbyjogging_import.runalyze_types` maps Jogging → `continuous`
      + `base`, Long Slow Distance → `long_run` + `base`, SubThreshold →
      `intervals` + `subthreshold`, by name or abbreviation and case/separator
      insensitive. It is applied on create and as a gap-filler in
      `workout_sets_current` when the classifier and sheet have nothing;
      manual and existing source sets always win. Only run sports are mapped.
    - **Audit**: `hobbyjogging-import runalyze types` prints the distinct
      stored types with counts and the unmapped ones. On this athlete's log it
      finds `Easy Run`/`JOG` mapped and eight unmapped types; the athlete-2
      slice (`Jogging`, `SubThreshold`, `Long Slow Distance`) maps completely.
    - **Not this item**: rep structure and laps (item 51); Runalyze's laps are
      untyped auto splits and never create work reps.
    - **Acceptance**: Jogging runs read easy, LSD long runs and SubThreshold
      quality; a re-run is a no-op; unmapped types are reported; the current
      athlete's Intervals/sheet sets are untouched.

50. **Manual thresholds and local zone configs** (core + import + maintenance +
    reports; done 2026-11-24).
    - **Write surface (done)**: `threshold add|list` writes dated, per-sport
      `max_hr`, `lthr` and `threshold_pace_mps` snapshots with
      `source='manual'`; a re-add for the same date replaces the values. No
      schema change, and `athlete_thresholds_current` only replaces its own
      `intervals` source, so a manual snapshot survives every recompute.
    - **Derivation (done)**: `derived_zone_configs_current` builds a local
      config from the snapshot in force on the activity's date — HR at 80/89/
      100/110 % of LTHR (or 60–90 % of max HR), pace at 75/85/100/110 % of
      threshold speed — and sums lap zone times from the device laps. An
      activity with no applicable threshold, or no laps, stays without zone
      times; an Intervals config and its times always win.
    - **Unlocks**: HR/pace zones for a non-Intervals athlete, the max-HR
      snapshot effective VO2max reads, and threshold-relative subT.
    - **Not**: Runalyze's zone percentages as canonical zones.
    - **Applied**: 242 activities gained a local config and 99 gained lap zone
      times; 2,238 kept their Intervals config, and 1,201 predate the first
      threshold snapshot.

51. **Typed work reps without Intervals** (import + maintenance + reports;
    done 2026-11-24). Athlete 2's FIT archive gives device laps but no
    WORK/RECOVERY typing; `derived_intervals_current` infers them.
    - **Probe first**: one of 782 sampled FIT files carries Garmin
      `workout`/`workout_step` messages (17 steps, `open`/`distance`/`time`
      durations, 50 laps). The steps describe the plan but do not type the
      laps, so a step-to-lap matcher is not justified; the lap heuristic is
      the fallback and a programmed-workout importer stays unplanned.
    - **Heuristic**: run sports only, at least two laps of ≥60 s and ≥100 m,
      no measured interval set, and the gate is the stored `intervals` method /
      `subthreshold` target (Runalyze type, item 49) or a lap-pace spread of
      1.50. A WORK lap is within 1.20 of the fastest third's pace; at least
      two WORK laps and one slower RECOVERY lap are required, so a uniform
      easy run stays laps.
    - **Storage**: `activity_intervals.source` (schema v25) records `intervals`
      or `derived`; `replace_derived_intervals` never touches a measured set
      and is idempotent. `interval_source_v1` stamped the 14,680 existing rows.
    - **Reporting**: the session report labels a derived interval table and
      its work reps, so a derived rep is never mistaken for a measured one.
    - **Acceptance**: the synthetic tests cover a structured set, a uniform
      easy run, a measured set and a re-run; on this athlete's log 0 runs
      derive (the structured ones already have Intervals sets) and the 4 false
      positives the first pass found were road rides, now excluded by the
      run-only gate.

52. **Garmin wellness** (import + reports; done 2026-11-24).
    - **Probe**: the Personal API exposes
      `/usersummary-service/usersummary/daily?user=<id>&calendarDate=…`
      (resting HR, sleep seconds, steps, floors, SpO2),
      `/hrv-service/hrv/<date>?user=<id>` (last-night HRV) and
      `/weight-service/weight/range/<start>/<end>?user=<id>` (weight in
      grams). Sleep detail and sleep score are 404 and stay empty; the GDPR
      export remains the fallback for a missing feed.
    - **User id**: `ownerDisplayName` or `ownerId` from one activity summary;
      no activity means no id, and the import reports that instead of guessing.
    - **Write**: `wellness_days` with hrv, resting_hr, sleep_s, weight_kg,
      spo2, steps and floors_climbed. The importer filters to the fields the
      stored day leaves NULL, so an existing value is never overwritten and
      Intervals stays the owner where both run.
    - **Sync**: joins `sync` after the Garmin activity fetch; idempotent, and a
      missing wellness feed is a skip with a warning, never a failed sync.
      `hobbyjogging-import garmin wellness --days N` runs it alone.
    - **Applied**: 8 recent days read on the real DB, 0 written, 8 unchanged —
      the Intervals values already fill every exposed field.

53. **A load fallback when there is no Intervals** (import + maintenance +
    reports; done 2026-11-24).
    - **Mapping (done)**: the Runalyze `FIELD_MAP` takes `fit_trimp` first and
      `trimp` as the fallback. `training_load` declares the ranked authority
      Intervals → Runalyze, so a mixed database keeps the Intervals value and a
      Runalyze TRIMP fills only an empty one, under `source='runalyze'`.
    - **Create and refresh**: the derive map fills a Runalyze-created activity;
      `runalyze_load_current` fills a matched activity from its stored payload.
      Applied to the real DB: 15 historical 2019/2021 runs gained a load,
      2,815 Intervals-owned values were kept, and `verify_canonical` stayed at
      0 drift.
    - **Reports**: no code change; the load chart, EWMAs and compare read
      `training_load`. The metric card states that a Runalyze-only series is a
      different vendor scale and its level is not comparable with Intervals'.
    - **Acceptance**: an Intervals-less database renders the overview/load/
      compare from TRIMP; a mixed database keeps Intervals; provenance shows
      the source.

54. **Source capability matrix and capability selection** (core + import +
    maintenance; done 2026-11-24). The capability layer is now registered,
    rendered, selected and checked.
    - **Register (done)**: Runalyze declares `workout_type` and `trimp` (and
      `training_load` as a creation field); Garmin declares `wellness`;
      Intervals declares `intervals`. The profile stays the single capability
      declaration.
    - **Render (done)**: `settings` (and `reports.sh settings`) prints a
      capability matrix — per source the record types, yields-activities,
      match, detail need, budget and creation fields — plus capability
      selection, the uncovered record types and activity fields, and the
      dashboard coverage. Uncovered entries distinguish
      `<source> (source disabled)` from `<source> (capability disabled)` and
      "not available in any profile".
    - **Doctor (done)**: one fixed `DASHBOARD_CAPABILITIES` list (wellness,
      load, zones, social, reps/intervals, race results) drives a `capabilities`
      warning when the enabled sources cannot supply a visible area. It is a
      warning, never a failure, and names the disabled source or capability or
      the manual fallback (`threshold add` for zones).
    - **Select (done)**: `sources.toml` accepts `tags`, `gear`, `races`,
      `vo2max`, `workout_type` and `trimp` under `[sources.runalyze]`, and
      `wellness` under `[sources.garmin]`, all true by default. Unknown keys
      and non-booleans fail loudly. A disabled capability skips only its step:
      `tags` the enrich step, `gear`/`vo2max`/`races` their derivations,
      `workout_type` the type gap-filler, `trimp` the load fallback, `wellness`
      the Garmin feed. Tests cover each skip.
    - **Not**: field priority or an import-order key. The four axes stay
      distinct — capability (profile), selection (TOML), precedence
      (owner-based plus per-field ranked authority in code), review (the queue
      and its causes). Manual and triage remain the per-athlete override.
    - **Acceptance**: the settings matrix and the uncovered list render for the
      Runalyze+Garmin profile; the doctor warns about zones and social; a
      disabled capability is visible and skips its step; no ownership or
      canonical value changes; four suites green. The real second-athlete
      acceptance run is the next session's work.

55. **Athlete-2 report bugs: subT selection and derived tables** (reports; done
    2026-11-24). The acceptance run found two bugs; both are fixed and tested.
    - **SubT/LT1 selection was name-only.** `analysis/common.py`'s
      `is_subt_activity`/`is_lt1_activity` only checked `a.name`, so a session
      with the stored `subthreshold` target never reached the subT report, the
      session's work-reps section, the period report, the activities table or
      the report command.
      - Fixed: the stored sets win — `fartlek` still wins, `lt1` target → LT1,
        `subthreshold` target → subT; with no sets the name is the fallback, so
        the current athlete's behaviour is unchanged. Every call site goes
        through those two functions.
      - A session still needs usable reps: derived intervals supply them; a
        SubThreshold run with no laps stays out by design.
      - A derived work-rep block is labelled as derived in the subT report.
    - **The derived table and list broke in the dashboard.** `format_session`
      appended the "Derived from device laps…" note directly before the
      Markdown table, and the "Reps are derived…" note directly before the
      list; Python-Markdown needs a blank line, while the CLI renderer is
      lenient.
      - Fixed: a blank line after both notes, plus a test that renders a
        derived session through `markdown_to_html` and asserts `<table>` and
        `<ul>`.
    - **Acceptance (2026-11-24)**: athlete 2's SubThreshold sessions list in the
      subT report and show work reps; the dashboard activity page renders the
      derived table and list; the current athlete's name-based selection is
      unchanged where no sets exist; four suites green.
    - **Not**: no schema change; no name-based heuristics written into the
      stored sets.

56. **Threshold coverage for historical activities** (import + maintenance;
    done 2026-11-24). `threshold add` defaulted `effective_from` to today, and
    `derived_zone_configs_current` only accepts a snapshot with
    `effective_from <= activity.date`, so the historical gap was silent.
    - **CLI (done)**: `--from first` resolves to the earliest non-excluded
      activity of the sport; `--from` still takes an explicit date and defaults
      to today. After saving, the command prints the effective date and, when
      there are earlier activities of that sport with no zone config,
      `N earlier <sport> activities stay unzoned (use --from first)`. The help
      and the import README document it.
    - **Task (done)**: `derived_zone_configs_current` adds one note with the
      `no_threshold` count and the earliest snapshot date, so the gap appears
      in the run summary.
    - **No silent backfill**: earlier dates do not borrow the first snapshot;
      the VO2max earliest-snapshot fallback remains separate and documented.
    - **Acceptance**: `threshold add --from first` anchors on the earliest
      activity; the message names the coverage; an Intervals config still wins;
      four suites green.

## Parked ideas

Not queued and not scheduled; recorded so they are not re-invented. The lab
owns experimentation, and items 13/14/25 own the eventual home.

- **What-if load sandbox** — add or remove a hypothetical session and read the
  42/182-day load impact from the existing load model (lab, no schema).
- **Race execution scorecard** — pacing vs plan, split consistency, HR drift
  and heat for a race day, from data already stored (lab first, then a card if
  it earns one).
- **"As-of" reports** — render the log as it looked at a past date; possible
  because inputs are preserved, expensive, so phase 4 at the earliest.

## Notes

- Reports hide activities with open review items by default
  (`--include-review` shows them); excluded activities never appear.
- `events sync` defaults to today .. today + 182 days; `--from`/`--to`
  override the window, and `--dry-run` reports without writing.
- `./sync.sh` runs the whole pipeline — Garmin → Intervals → FIT → Runalyze →
  Strava → offline derivations → maintenance recomputes → review scan →
  dashboard; `--no-garmin`, `--no-intervals`, `--no-fit`, `--no-runalyze`,
  `--no-strava`, `--no-derive`, `--no-maintenance`/`--no-classify`, `--no-scan`
  and `--no-dashboard` skip those steps. `./init.sh` creates and migrates the
  database and `./doctor.sh` checks the installation.
- `./dashboard.sh` regenerates the dashboard and opens `index.html` in the
  browser; `--no-open` or `NO_OPEN=1` suppresses the browser.
- The `planned` report always starts tomorrow.
- Reports use `duration_s` (recording/timer time) for pace and time.
  `moving_s` is stored for provenance and the `moving_time_mismatch` rule
  only; it is not a report denominator.
- The Garmin key is valid for 30/90/180/365 days; each run exchanges it for a
  24 h bearer token.
- Runalyze's activity payload exposes no Garmin activity id, so matching stays
  temporal.
