# Status and next steps

Updated 2026-11-19.

## Done

Recently landed; git history is the changelog. Structure and settled rules
live in [ARCHITECTURE.md](ARCHITECTURE.md), metric cards in
[METRICS.md](METRICS.md), and each package's own list in
`packages/*/NEXT_UP.md`.

- **The canonical pipeline and all sources (phase 1).** FIT archive,
  Intervals.icu, the Garmin Personal API fetch, Runalyze (inventory,
  comments/tags, gear, race results, `vo2max_runalyze`) and the Strava CSV are
  imported and applied on the real DB: 4,143 non-excluded activities, schema
  v23.
- **Inputs vs projections (item 17).** `activity_manual_fields` (v23) holds
  manual values and owner patches; `derive.py` declares the per-source mapping;
  `verify_canonical` reports 68,001 owned fields with 0 drift, 0 dangling and 0
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

**2a · Install**

- **`doctor` and `init`** — create and migrate a fresh DB explicitly; `doctor`
  checks `uv`, the DB path, schema version, FIT dir, each credential and its
  age, pending data migrations, source staleness and the sources file, and
  prints the next command.
- **`sync.sh` skips an unconfigured source** instead of failing on an absent
  credential, so a missing credential is never a failed sync (item 44 covers
  the rest).
- **44 sync covers every configured source** — Runalyze, Strava and the
  offline derivations join the one command.
- **`./demo.sh` as the zero-credential first run**, documented and tested on a
  clean checkout with an empty `$HOBBYJOGGING_DB`.
- **`sources.toml`, `.env.example` and the README first-run path** (GDPR export
  or `garmin fetch` → `sync` → dashboard).
- **A pull-request workflow** (four suites + demo build) and a `LICENSE`.
- **22 release versioning** — "which code built this DB" must be answerable for
  someone else's install.
- **29 lab detach** — a clone must not ship this athlete's findings; last,
  after the install path works.
- **Defaults consolidation and the Python floor** — the remaining personal
  constants in one documented module; `requires-python` 3.12 once the suites
  pass there.

**2b · A usable dashboard without Intervals** (the Runalyze+Garmin profile)

- **49 Runalyze workout type → canonical sets** — `Jogging`, `SubThreshold`
  (always `intervals` + `subthreshold`), `Long Slow Distance`, with an
  unmapped-type audit. This is what gives a name-less athlete categories.
- **51 typed reps without Intervals** — Garmin workout steps if the FIT has
  them, otherwise derived WORK/RECOVERY from laps, gated by the source type;
  marked derived, never overwriting Intervals reps.
- **53 a load fallback** — map `fit_trimp`/`trimp` when no Intervals
  `training_load` exists, with the vendor scale documented per athlete.
- **50 manual thresholds and local zone configs** — `threshold add|list`,
  derived zone configs, and the max-HR snapshot the effective-VO2max metric
  needs.
- **52 Garmin wellness** — daily resting HR, HRV, sleep and steps into
  `wellness_days`, so the recovery tab and the efficiency baseline exist.
- **A name label** — when `name` is empty, render sport + distance in tables
  and the session header instead of a blank title (small reports change).

### Phase 3: trustworthy data

Order: **34** (manual overlay + rebuild proof, the safety gate) → **37** audit
(read-only, cheap, informs everything) → **1** (CLI write surface) →
**38/35/21** extraction → **37**'s rules and **43** tags → **42** duplicates →
health score → browser. Accepting a suggestion always writes a manual value and
an `edit_log` row; nothing canonical is auto-applied except an empty,
high-confidence classification.

### Phase 4: durable and more reach

Parked: 13 homelab, 14 platform independence, 25 coaching, 27 performance, the
Strava API and the stream half of 38. Ordered only when phases 1–3 are done.

Item 40 is closed (see its entry): the recording sources keep `enabled`, so
there is no create policy to wire. Item 41 (device identity) landed as a bug
fix, not as phase work. Items 12, 16, 17, 24, 32 and 39 are landed; 15 is a
reports item; 28 is the recurring cleanup.

1. **Activity editing, CLI first** (core + import; phase 3). The only manual
   write surface is `review edit`, which changes `duration_s`, `distance_m` and
   `sport`, and only with a review item attached. Name, description, RPE, feel,
   sub-sport, tags, classification and equipment have no free-form edit, no way
   to clear a value, and no history — `activity_field_sources` stores only the
   current owner and value, so there is nothing to undo against.
   - **Command**: `hobbyjogging activity edit <id>` with explicit flags
     (`--name`, `--description`, `--rpe`, `--feel`, `--sub-sport`, repeatable
     `--tag`, `--method`, `--target`, `--equipment`), plus `--clear <field>`,
     `--dry-run`, `--history`, and an interactive mode that prompts field by
     field with the current value as the default. A review item is never
     required.
   - **Provenance**: every field goes through `TrainingWriter.set_manual_field`
     (`is_manual=1`, `source='manual'`), so a reimport cannot undo it; `sport`
     still normalizes through `core.sports`; the sets go through
     `set_manual_activity_workout_methods` / `_targets`. **`MANUAL_FIELDS`
     currently rejects `name`, `description`, `rpe`, `feel` and `sub_sport`**,
     so that tuple has to grow first — `set_manual_field` raises for every one
     of those flags today.
   - **Quality**: reuse `apply_manual_edit`, which re-runs the quality rules and
     prints the findings that still stand.
   - **Relationship to triage**: both surfaces share one write path —
     `apply_manual_edit` → `set_manual_field` + `refresh_activity_quality` — so
     provenance and the quality re-check never diverge. Triage stays the
     contextual surface (sources, `(v)` pick value, `(t)` trust Intervals,
     `(ci)`/`(cg)` links, `(d)` exclude, `(k)` classification proposals); edit
     is the direct surface and must not grow those actions. Only
     `duration_s`/`distance_m`/`sport` and the classification sets genuinely
     duplicate, which is intended: `_VALUE_PROMPTS` covers exactly three
     fields, and `(k)` adds the proposals the raw `--method`/`--target` cannot.
   - **Item lifecycle fix**: `refresh_activity_quality` only closes
     `category=quality` items, and `prune_field_conflicts` only closes a
     conflict whose *recorded* current/incoming values agree — it knows nothing
     about a manual override. An item-less edit therefore leaves the matching
     `field_conflict` open forever. `apply_manual_edit` must also resolve open
     `field_conflict` items for the touched `(activity, field)` and open
     `workout_classification` items when methods/targets are written; `--item`
     then becomes a convenience, not a requirement. `edit_log` records the
     resolved item id so the history explains the closure.
   - **Prompt table**: move `_VALUE_PROMPTS` from `triage.py` to `values.py`
     so the interactive edit mode and triage share one prompt/parser table.
   - **Text fields (decided).** One training-notes text per activity, not a
     list. `activities.description` is the training notes — Intervals
     description, the sheet's `Beschreibung`, Runalyze as a blank-fill fallback
     — and the edit CLI edits it with `--description`. **No `activity_notes`
     table**: the field inventory shows one training text and one social text
     per activity, so a notes table would be the speculative abstraction the
     rules warn about. The social text lives in `activity_social` (item 16).
   - **Edit log (new)**: `edit_log(entity_kind, entity_id, field, old_json,
     new_json, source, note, created_at)`, append-only, written in the same
     transaction as the edit. `activity_field_sources` is a snapshot, not a
     history; independence later means the database has to carry the audit
     trail a platform would have kept. `--history` reads it, and events and
     wellness reuse it.
   - **Placement**: keep it in the import CLI for now — `editing`, `values`,
     `quality` and `causes` already live there. When the front end starts,
     extract a `hobbyjogging-app` package and move those modules behind it, the
     same move the classifier made to core once it had a second consumer.
   - **Localhost write surface (later in phase 3, after the CLI)**:
     server-rendered forms bound to `127.0.0.1`, one user, no auth,
     POST-redirect-GET, reusing the existing HTML renderer and **the same write
     functions as the CLI** — the UI never runs its own SQL and never becomes a
     second implementation. The CLI stays the reference implementation: if the
     UI needs something the CLI cannot do, the CLI is wrong. Start with the
     standard library
     (`wsgiref`/`http.server`, zero new dependencies) and escalate to a small
     framework only if forms, uploads or sessions demand it. No SPA, no JS
     framework, no background jobs; the static dashboard stays read-only and
     the phone stays read-only. The database is single-writer (WAL, 5 s busy
     timeout) and unauthenticated, so it must never be exposed beyond loopback.
     No long write transaction, and never overlap with `sync.sh`: a lock is a
     bug to fix, not a retry to hide.
   - **Tests**: a manual edit survives a reimport; `--clear` removes the value
     and its manual ownership; `--history` shows the prior value; `--dry-run`
     writes nothing; quality findings print; an empty interactive answer keeps
     the current value; tags/methods/targets replace as sets; an item-less edit
     closes the matching `field_conflict` and leaves other fields' items open;
     a classification edit closes the `workout_classification` item; `--item`
     still resolves explicitly.
   - **Docs**: the ARCHITECTURE role list gains the human write surface, and
     the import README documents the command.

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
      comments live in Intervals, tags move with item 1, and the only missing
      surface is equipment add/edit/retire; the lost series is
      `vo2max_runalyze`. Intervals is the hard one (plans, wellness, events,
      thresholds, zones), which is why it comes last.
    - **Phases**, in order: owner-tracked events (`event_field_sources`, manual
      wins, a new `AGENTS.md` rule) → planned-workout steps and authoring →
      subjective wellness ownership → thresholds/zones (item 8) → the front end
      from item 1 → Garmin/FIT ingest so Intervals becomes optional.
    - **Not needed**: a notes/comments table. The field inventory shows one
      training-notes text per activity (`description`) plus a social text on
      Strava, so this work reuses `description` rather than adding
      `activity_notes`.
    - **Parked decisions**: whether programmed workouts are followed on the
      watch (which would need a `.fit` workout export and upload) or the lap
      button is enough — the 370 intervals activities with ≥3 WORK reps suggest
      the latter; and whether the front end ever replaces the CLI.
    - **Edit history** from item 1 is a prerequisite, not an extra: without it,
      dropping the platform also drops the audit trail.

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

21. **Sheet leftovers** (import + reports; phase 3, with item 38).
    `equipment.notes`
    holds size, price and colour from the sheet and is never parsed;
    `tz_offset_min` is populated on the activities and unused. Parse the notes
    into typed equipment fields (or leave them as text) and use
    `tz_offset_min` where local time matters — chart day boundaries and session
    times. Decide per field whether it earns a place.

22. **Release versioning** (repo-level; no package; phase 2). Every
    `pyproject.toml` says
    `0.1.0` and never changes, and there are no tags, so "which code built this
    database" is unanswerable. The *data* contract already exists — `PRAGMA
    user_version`, immutable ordered migrations, and `migrate()` refusing a
    database newer than the code — so only the code version is missing.
    - **Triggers**: the homelab cutover (item 13), where scheduled syncs and
      ad-hoc reports can run two code versions against one DB; a second
      installation; any destructive migration; and the published demo, which
      already ships output without provenance.
    - **Shape**: one repo-level semver tag (the four packages move together),
      a `CHANGELOG.md` with schema/data-task/report sections and a
      compatibility line ("v0.4 requires schema ≥10, migrates to 10"), and a
      GitHub release note. **No PyPI** — private workspace, no consumer.
      Pre-1.0 while the schema moves; 1.0 only once a second person's data is
      on it.
    - **Cadence**: not time-based — tag now for the current state, then at each
      schema bump and milestone.
    - **Not versioned**: experiments, report output, docs.
    - **Checklist instead of tests**: suites green, changelog written, DB
      backed up before the migration, tag pushed.

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
      - [ ] `init` creates and migrates a fresh DB explicitly; a second run is
            a no-op.
      - [ ] `doctor` checks `uv`, the DB path and writability, the schema
            version, the FIT directory, the credentials (including the Garmin
            key's age), pending data migrations, whether a configured source
            has gone stale, and the sources file, and names what is missing.
      - [ ] `sources.toml` alone selects the sources: Intervals and the sheet
            disabled, Runalyze `review`, Strava `create` or `ignore`.
      - [ ] `sync.sh` skips an unconfigured source instead of failing on an
            absent credential, and never assumes Intervals.
      - [ ] a pull-request workflow runs the four suites plus the demo build;
            today CI only covers pushes to `main`.
      - [ ] `LICENSE`, `.env.example` and a README first-run path (GDPR export
            or `garmin fetch` → `sync`).
    - **Ingestion (core + import)**
      - [ ] Garmin FIT is the only device source: `moving_s`/`elapsed_s` fall
            back to FIT through the existing ranked authority, with no code
            change.
      - [ ] device identity is FIT-first: app names never become devices, a
            provider name claims the unique FIT device of its model, and an
            unused provider row is soft-excluded (landed).
      - [ ] Strava `create` makes a summary activity using the configured
            timezone; title and description follow the text target.
      - [ ] Runalyze honours `create|review|ignore`; unmatched rows become
            review items when set to `review`.
      - [ ] gear works without a sheet: exact name → new row → ambiguous item,
            with the co-occurrence branch simply never firing.
      - [ ] race results arrive without Intervals (Runalyze); no training
            periods and no planned events is an accepted empty state, not an
            error.
    - **Analysis and reports (reports)**
      - [ ] no Intervals assumption in the read path: missing thresholds,
            zones, events or wellness degrade to an explicit "not available",
            never a wrong number or a crash.
      - [ ] chart ceilings come from the data (landed); the known personal
            constants that remain are `COMPARE_VISIBLE_YEARS`, the 2009 colour
            anchor and `RACE_DAYS`.
      - [ ] the analysis defaults (RPE > 3, 90-min long run, 40–75 min
            efficiency band, subT buckets, 5-bpm HR conflict, 10 %/20 m
            elevation) are one documented module of defaults, not laws.
      - [ ] the demo builds from the synthetic athlete and renders every tab,
            so the second athlete's empty paths are exercised too — including
            the effective-VO2max overview and methods card, which is the
            zero-credential install proof.
      - [ ] the Runalyze+Garmin profile renders categories, laps/reps, zones,
            load and wellness (items 49–53), and the demo still covers the
            empty paths.
    - **Language floor**: [ ] `requires-python` drops to 3.12 once the suites
      pass there; no 3.14-only syntax was found.

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
    phase 2, last). The lab's scripts and notebook carry personal research and
    findings and should not live in the project repo — but the bench must stay
    so another user can run their own.
    - **Split**: the bench ships (the rules, `experiments/template.py`,
      `lab.sh`, the gate in `docs/METRICS.md`, the Lab tab); the log moves to
      `laufen_private/lab/` (the scripts, the candidate table, the statuses and
      the rejected findings).
    - **Env var rename**: `HOBBYJOGGING_LAB_DIR` currently means the output
      directory (`data/lab`) in `shell.py`; rename that to
      `HOBBYJOGGING_LAB_OUTPUT_DIR` and give `HOBBYJOGGING_LAB_DIR` the lab
      itself, defaulting to `experiments/` so a fresh clone works out of the
      box.
    - **Dashboard**: read `$HOBBYJOGGING_LAB_DIR` for local builds; demo builds
      never read it and render the bench guide only (see the reports bug).
    - **Evidence split**: `docs/METRICS.md` keeps the contract (definition,
      baseline, thresholds) and the aggregate statistics; the personal
      narrative — illness dates, resting-HR values, run counts tied to events —
      moves to the lab repo and is referenced by name.
    - **Move checklist**: create `laufen_private/lab/`, move the scripts and the
      candidate table, split `experiments/README.md` into bench rules and
      notebook, then update `lab.sh`, the lab section of `AGENTS.md`, the
      dashboard and the `.env` example.
    - **Risks**: two repos to clone on a new machine; `lab.sh` must fail
      clearly when the lab dir is missing; CI must never need the private repo;
      the moved scripts lose their in-repo history.
    - **Related**: item 23 (this is its lab case), item 26 (demo upkeep) and
      item 25 — the coaching notes will live in the same private repo, so the
      dashboard reads both from there.

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

34. **Manual-layer export and rebuild check** (maintenance + core; phase 3,
    the safety gate). The raw layer is preserved and
    SQLite stays readable, so the data does not disappear; what dies with the
    code is the *meaning*: which values were overridden, which sessions were
    deliberately excluded, which conflicts were decided. That layer is small —
    measured on the real DB: 73 manual field overrides (`sport` 38, `avg_hr`
    28, …), 335 + 209 manual workout method/target rows, 29 exclusions, 33
    ignored review items — against 14,393 source records and 4,148 activities
    that are raw or recomputable.
    - **Export**: `maintenance export-manual` writes JSONL — the
      `activity_manual_fields` overlay (item 17), manual sets, manual tags,
      manual equipment links, exclusions and the ignored/resolved review
      fingerprints — and `import-manual` re-applies it to a fresh database,
      idempotently. Human-readable, diffable, a few kilobytes.
    - **Rebuild proof**: a `rebuild` check — fresh database, replay the raw
      layer (`source_records` plus the FIT archive), apply the overlay, run
      `recompute_canonical`, then diff the canonical layer against the live
      database. An empty diff is the proof that raw + overlay + code reproduce
      everything. Companion to item 17.
    - **Placement and cadence**: the overlay lives in `laufen_private` next to
      the database (item 29) and is exported at each release tag (item 22).
    - **Not doing**: a CSV/JSON export of the whole canonical database — it
      duplicates the raw layer and rots with the schema — and not treating the
      overlay as a backup; a periodic `sqlite3 .backup` remains the safety net.
    - **Why first, though it is insurance**: the raw sources and the database
      are already safe; this protects the decisions and the design claim, which
      matters if the project is ever abandoned or handed over. It is small,
      the rebuild it exercises just landed, and an empty diff makes every
      later phase confident in `recompute_canonical`. The input table itself
      belongs to item 17; this item is the export and the fresh-database proof.

35. **Runalyze's extra metrics: what to store, what to ignore** (core + import
    + reports; phase 3, with item 38). The activity payload carries more than
    our schema holds. Coverage measured in the Intervals payloads we already keep:
    `average_cadence` 2,353 of 2,851 (83%), `average_stride` 2,334, but the
    running-dynamics family (`average_vertical_oscillation`,
    `average_stance_time`, `average_vertical_ratio`) only 110 (4%). The FIT
    session message carries the same averages (`avg_vertical_oscillation`,
    `avg_stance_time`, `avg_stance_time_balance`, `avg_vertical_ratio`,
    `avg_step_length`, `avg_running_cadence`) and the records carry them per
    second, so the 4 % is Intervals' coverage, not the ceiling — the importer
    just does not extract them yet. Runalyze adds `gap`/`x_gap`,
    `aerobic_decoupling_pace/power`, `trimp`/`fit_trimp`/`fit_training_effect`,
    `required_critical_pace/power`, `climbs`, `hrv`, and zone distributions as
    percentages.
    - **Store**: `cadence` and `stride_length` (83 % coverage, actionable) and
      `gap_mps` — Runalyze's grade-adjusted pace beats a lap-based estimate.
    - **Lab**: decoupling and critical speed already have candidates; use
      Runalyze's values as a cross-check, not as stored metrics.
    - **Out of scope for now**: vertical oscillation, stance time and ratio
      (4 % in Intervals, more in FIT), impact loading, leg spring stiffness,
      training effect (we keep Intervals' `training_load`), climbs as
      an entity, HRV analysis, and zone distributions as percentages. If the
      dynamics ever matter, extract the FIT session averages rather than
      storing streams.
    - **Load**: the TRIMP fallback moved to phase 2 (item 53); this item keeps
      the cadence, stride and GAP decision.
    - **Open**: whether cadence and stride sit on `activities` or in an
      `activity_dynamics` row; two columns are defensible at 83 % coverage.

37. **Refurbish historical data from evidence already stored** (maintenance +
    import + reports; phase 3, step 2). The log already contains
    facts we do not use: tags carry workout targets, illness recovery and race
    days, descriptions describe interval sessions, and big races anchor
    seasons. The point is to fill empty fields and propose corrections, never
    to invent facts.
    - **Sequence**: the Runalyze import has landed, so the tags and comments are
      complete; the audit is read-only and can start now. Proposals that need
      the activity edit surface wait for item 1.
    - **Audit first** (maintenance): a read-only report per field and year —
      raw payload keys not stored, tag semantics, interval-like descriptions,
      elevation/trail evidence, race evidence, and coverage gaps. It is the
      gate for the phases below and is re-runnable as imports land.
    - **Workout classification** (import + maintenance): parse explicit
      interval patterns in `description` and the Runalyze tags (`sub
      threshold`, `LT1`, `Longjog`, `Regeneration`, `strides`, rep lengths)
      into method/target proposals. High-confidence proposals fill an empty
      classification with a `comment`/`tag` source; conflicting or weaker ones
      extend the existing `workout_classification` review item, never a new
      queue. Do not reconstruct rep rows from text until the audit shows the
      comments are structured enough.
    - **Trail candidates** (maintenance): combine session and lap elevation
      (the existing ≥40 m/km rule), `sub_sport` (`trail`, `mountain`), the
      `Trail` tag and route names; open `consistency` review items instead of
      changing the sport automatically. Calibrate the threshold on the 31
      measured candidates first.
    - **Pace/HR outliers** (import): fit the steady-run pace/HR relationship
      (robust, per year or a rolling window) and open a review item for extreme
      residuals. Exclude trail/race/interval sessions and heat/elevation
      explanations; a first pass at 3.5 MAD / 12 bpm flagged 37 gross points,
      many of them legitimate, so calibrate on the steady subset before
      enabling it.
    - **Illness candidates** (maintenance): `krank`, `verkühlt`, `Infekt`,
      `Magen-Darm`, `Fieber`, `Grippe`, `erkältet` are active evidence;
      `wieder gesund` closes a range; `schlapp` is ignored. Compare the
      observed days with `training_periods` and open `period_candidate` review
      items for gaps or extensions; never write a period automatically.
    - **Season labels** (maintenance + reports): label the three existing
      seasons with their goal race first. For years with no `SEASON_START`,
      propose a season from the clear A-race (`RACE_A`/priority, `race`/
      `Raceday` tags, distance/name) as a `season_candidate`; do not derive a
      build start silently.
    - **Manual surface**: accepted candidates write manual values through the
      activity edit CLI or `period add` and land in `edit_log` (item 1).
      Review is the default; auto-fill only for high-confidence empty
      classifications.
    - **Health score** (reports; rides on this audit): one view of data trust —
      open review items by category, duplicate count, and per-field/per-year
      coverage — as a dashboard card with a CLI equivalent, so phase 3 has a
      number that can go down. It reads existing data; no schema change.
    - **Separate**: Gmap route identity (931 rows, 528 IDs) is route coverage,
      not classification; keep it as its own item if it is taken up.
    - **Tag meaning** lives in item 43; this audit lists the unmapped tags
      first, and the proposals read that lexicon instead of hard-coded words.

38. **Session-average metrics now, streams later** (core + import + maintenance
    + reports; phase 3, step 4). The session-level aggregates are already in
    the raw payloads and the FIT archive, but most are not stored: FIT session
    fields
    (cadence, stride, vertical oscillation, stance time/percent/balance,
    vertical ratio, respiration, power, calories, training effect, altitude),
    Intervals (cadence 83 %, stride 82 %, calories 100 %, altitude 98 %),
    Runalyze (dynamics 79 %, GAP 80 %, power 97 %) and the sheet
    (cadence/contact/oscillation ~33 %). Extract the session averages; leave
    per-second streams in the FIT archive for later.
    - **Audit first**: list every session-average field, its coverage, units and
      conflicts across the four sources; reuse item 37's raw-field audit.
    - **Schema**: one `activity_metrics` row per activity (like
      `activity_weather`), with nullable Tier 1 columns: cadence (spm), stride
      (m), vertical oscillation (mm), stance time (ms/percent), stance balance
      (%), vertical ratio (%), respiration, power (rides), calories, training
      effect, GAP (m/s), average/min/max altitude. The first source owns the
      row and later sources fill gaps; FIT is the authority for
      device-measured dynamics, Runalyze fills gaps, and Intervals owns
      cadence/stride/calories/altitude where FIT has none. Tier 2 (climb score,
      percentage hilly, power variability, HR recovery, decoupling, efficiency
      factor, TRIMP) stays in the raw payload until a report needs it.
    - **Extraction**: extend `FitSession` and the FIT parser, then backfill from
      `source_records.raw_path`; map the Intervals, Runalyze and sheet payloads
      and backfill them too, reusing item 17's `FIELD_MAP` and recompute
      machinery. Calories is the quick win: FIT already parses it
      and drops it, and Intervals/Runalyze cover it at ~100 %.
    - **Reports/lab**: session-report lines and dynamics/power charts; derived
      metrics (decoupling, efficiency, critical speed) stay in the lab with a
      metric card.
    - **Streams later**: keep the raw FIT archive as the stream source; add a
      stream index/metadata table and parse on demand or into Parquet. Do not
      put per-second rows in the canonical SQLite database.
    - **Sequence**: step 4 — after items 34, 37 and 1. The Tier-1 extraction
      audit reuses item 37's raw-field audit, and both audits can start before
      the schema lands. Streams stay phase 4.

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

42. **Duplicate detection and cleanup** (maintenance + import + reports;
    phase 3, after the rules). Two activities that are the same session
    double-count every total, and the historical log has a known class of them:
    1,272 sheet-only rows, 38 of which mirror a device (FIT/Intervals) row on
    the same day with the duration within 5%. The sheet row often holds the
    only description (`mit Vicky`, `Oberwolfach am Ende gas`).
    - **Detection** (import): a dataset-wide rule for same sport, start within
      ±15 min or the same day, distance within ~2%, and HR within 5 bpm when
      both carry it; emit one `duplicate` review item carrying both activity
      ids, idempotent by a fingerprint over the sorted pair.
    - **Athlete-2 finding**: the Runalyze-only test left 10 of 40 rows in
      review, each with exactly one same-day candidate — mostly rides and one
      other sport. Before a broad rule runs, check whether the candidate is a
      different sport or duration; the same-day guard is currently too strict
      for a legitimate second session on the same day.
    - **Sheet pairs** (maintenance): a task that blank-fills the description
      from the sheet row and then excludes it, so the session keeps its text
      and stops counting twice. It rewrites existing rows, so it is a
      registered task with a dry run, not an import write.
    - **Resolution is exclusion, never merge**: "delete" stays a durable soft
      exclude, and there stays one identity model. A true merge is not a
      feature — the canonical row and its payloads are the record.
    - **Surface**: triage today; the bulk review surface and the health score
      (item 37) show the remaining count.
    - **Acceptance**: a dry run lists the candidate pairs on a copy, the known
      sheet duplicates drop out of the totals, and a re-run is a no-op.

43. **Tag lexicon** (core + import + maintenance; phase 3, after item 49).
    Tags already carry facts the rules need — workout targets (`sub
    threshold`, `LT1`, `Longjog`, `Regeneration`, `strides`), rep lengths
    (`6'`, `3'`, `10'`), illness (`krank`, `verkühlt`, `Infekt`, `Magen-Darm`,
    `wieder gesund`), race days (`Raceday`, `race`) and the sheet's
    training-area labels (`w`, `m`, `wb`, `a`, `t`, `I`) — but their meaning
    is implicit in code or prose. Athlete 2 is the tag-first case: tags on 19
    of 30 runs, no names, empty notes.
    - **Order**: item 49 maps the source's own workout type first — that is
      the reliable classification signal. The lexicon then covers what the
      type cannot say: rep lengths, illness, race day and context tags
      (`Commute`, `Rucksack`, `GAT1`, people).
    - **Shape**: one lexicon that maps a stored tag (normalized) to a meaning
      and the rule it feeds, plus an audit that lists every stored tag as
      mapped or **unmapped**. Start as a code-level module beside
      `hobbyjogging_import.sheet_codes`; add a `tag_semantics` table only when a
      second athlete's tags must be mapped without a release (the trigger, not
      before).
    - **Consumers**: item 37's classification, illness and season proposals
      read the lexicon instead of hard-coded word lists; no rule invents a
      meaning for an unmapped tag.
    - **Acceptance**: the audit accounts for every stored tag, the proposals
      use the lexicon, and adding a tag meaning is a one-line change with a
      test.

44. **Sync covers every configured source** (import + reports; phase 2). Today
    `sync.sh` runs Garmin, Intervals, the FIT scan, the review scan, the
    classifier and the dashboard; Runalyze and Strava are manual one-offs, so
    the mirror can be weeks stale and nothing says so. The phase-2 exit test
    says "runs `sync`", which has to mean the whole configured pipeline — also
    for an athlete with no Intervals.
    - **Runalyze (online, budgeted)**: one `runalyze enrich --since <last sync
      − 14 d>` per run. Re-runs only fetch new rows (a stored, linked detail is
      skipped); a `429` ends the step with a pending count and a warning, never
      a failed sync, and `--wait` is never used inside a scheduled run. Then
      the offline `runalyze gear`, `vo2max` and `races` steps run every time —
      they read stored payloads and cost no requests.
    - **Strava (manual drop)**: import the newest `export_*.zip` from
      `data/strava/` when it is new, and no-op when it is absent or already
      recorded. The download stays a human chore — no API, no scraping; the
      deferred-API decision stands. Tags and gear keep Runalyze as their interim
      home (item 1 moves tags to the DB later).
    - **Order**: fetch (Garmin, Intervals, FIT, Runalyze, Strava) → offline
      derive (gear, vo2max, races) → maintenance recomputes → review scan →
      dashboard. A source that failed or is unconfigured prints a warning and
      the rest still run.
    - **Companion, any time (reports)**: a source-freshness view — last
      successful run, last activity date, pending Runalyze rows and Strava
      export age per source, read from `import_runs`/`source_records`, no
      schema change. `doctor` answers "can it run"; this answers "is it
      current".
    - **Acceptance**: a fresh install with Garmin, Intervals, Runalyze and
      Strava brings all four in with one command; a second run is a no-op;
      removing one credential skips that source with a warning and leaves the
      others working; the dashboard reflects the new metadata.

45. **Readability baseline pass** (reports + tools; small item, after
    `init`/`doctor` and before the phase-3 UI). The codebase is not bloated
    yet, but reports and import are two-thirds of it and two files are doing
    too much. Measured 2026-11-19: reports 75 modules / 22.8k
    lines, import 41 / 16k, core 14 / 6.3k, maintenance 33 / 4.6k;
    `charts.py` 3,610 lines, `writer.py` 2,898, and
    `analysis/__init__` re-exports 154 names. This item is deletions and
    splits, not a rewrite.
    - **Split `charts.py`** by chart family (overview, volume, load, time,
      subt, races, compare, devices) behind the same public imports, with no
      behaviour change; each figure builder moves with the charts it serves.
    - **Audit `analysis/__init__`**: delete the exports nothing imports and
      keep the renderer-facing surface explicit. This is the highest-value
      deletion in the package.
    - **Add `tools/check_size.py`**: fail when a source file exceeds 1,000
      lines unless it is on a short allowlist — today `charts.py`,
      `writer.py`, `demo.py`, `triage.py`, `runalyze_import.py`,
      `format.py`. Wire it into the CI job beside `check_todos.py`; the
      allowlist only shrinks, and splitting a giant removes its entry.
    - **Not now**: splitting `writer.py` (cohesive) or `demo.py` (mechanical),
      a linter, package renames, or extracting `hobbyjogging-app` — that waits
      for the front end (item 1).
    - **Acceptance**: four suites green, the demo dashboard renders
      identically, the public import paths still resolve, and a deliberately
      oversized new file fails CI.

46. **Snapshot before a write task** (maintenance; small, before the phase-3
    mass edits). `--dry-run` protects the decision, but a real run — a
    backfill, the bulk duplicate cleanup (item 42) or a `--force` rerun — has
    no automatic restore point; the backup is a manual `sqlite3 .backup`
    habit.
    - **Runner**: before any non-dry run, `VACUUM INTO` a timestamped snapshot
      beside the database (`<db>.bak-YYYYmmddTHHMMSSZ`), keep the last five,
      and print the path. A dry run writes nothing, not even a snapshot.
    - **Not a backup replacement**: the snapshot protects the minutes around a
      task; the periodic backup still protects the machine. A following
      `verify_canonical` run is the check for a task that touched canonical
      fields.
    - **Acceptance**: a real run creates exactly one snapshot, a dry run none,
      retention keeps five, and the printed path opens as a valid database.

47. **Date and time-zone integrity** (core + import + reports; small, any
    time). `tz_offset_min` is stored but unused, and nothing checks that
    `started_at_utc + tz_offset_min` lands on `local_date`. A bad offset or a
    midnight/DST edge moves a session to the wrong day, and streaks, illness
    periods and race matches all read dates.
    - **Rule**: a quality check against the invariant plus a plausible range
      (−12..+14 h); it opens a `quality` item instead of rewriting, because the
      date stays owner-tracked.
    - **Import**: FIT, Intervals and the sheet offsets feed the same check;
      the Strava export's account timezone stays a per-import choice, and the
      chosen reading is already recorded.
    - **Reports**: use the offset wherever a day boundary matters (item 21) —
      no new column.
    - **Acceptance**: a synthetic midnight/DST case and a bad offset each
      produce one item, a correct activity produces none, and a re-run is a
      no-op.

48. **Field provenance in the session report** (reports; small, any time).
    `activity_field_sources` records who owns each value and what it wrote, but
    the session page shows only review status. The obvious question — "why is
    distance 42.45 and not 42.19?" — needs SQL today.
    - **Block**: per owned field (distance, duration, avg/max HR, elevation,
      sport, load, VO2max, device), the owner source, its value, and whether a
      later source agrees within tolerance; a conflict links to its review
      item.
    - **Placement**: after the metrics block, collapsed on the dashboard (the
      same native toggle as the long tables); the CLI prints the same lines,
      per the parity rule.
    - **No schema change**; it reads the existing provenance rows.
    - **Acceptance**: a disputed activity names the winning source and the
      losing value, a single-source activity stays short, and the CLI and the
      dashboard print the same list.

49. **Runalyze workout type → canonical sets** (import + maintenance; phase 2b,
    first). Runalyze's activity payload carries a `type` object
    with `name`, `abbreviation`, `quality_session` and a reference `avg_hr` —
    per activity, no parsing. Measured on the athlete-2 slice (30 runs):
    `Jogging`/`JOG` ×20 (`quality_session: false`), `SubThreshold`/`ST` ×8
    (true), `Long Slow Distance`/`LSD` ×2 (true); rides and other sports carry
    no type. It is the one classification signal a name-less, RPE-less
    athlete has.
    - **Mapping**: a code-level module beside `hobbyjogging_import.sheet_codes`
      (`runalyze_types`), applied on create and as a gap-filler for matched
      activities with no sets, the same way `workout_sets_current` treats the
      sheet. Manual and existing source sets always win; an unknown type is
      listed, never guessed.
    - **Decision (settled)**: Jogging → `continuous` + `base` (non-quality);
      Long Slow Distance → `long_run` (quality); SubThreshold → `intervals` +
      `subthreshold`, **always** — the athlete uses the type for structured
      work, so the method should say reps were intended even when no rep data
      exists. The display kind is `quality/intervals/other` until reps arrive,
      and the subT rep-length buckets stay empty without them.
      `quality_session` is a cross-check, not an override: quality is derived.
    - **Audit**: print the distinct stored types with counts and the unmapped
      ones, so a new Runalyze type is visible before it silently classifies
      nothing.
    - **Not this item**: rep structure and laps. The type says
      "SubThreshold", not "6×3′". Runalyze's payload does carry `laps` (30 of
      40 in the probe), but each is only `{distance, duration, intensity:
      'unknown'}` — auto splits or device laps with no WORK/RECOVERY type, HR
      or pace. Laps belong to `activity_laps` (the segment table); typed
      intervals come from Intervals.icu, or are derived from those laps by
      item 51. A Runalyze interval importer is not planned. If no FIT archive
      exists, importing the Runalyze laps as `activity_laps` is an acceptable
      fallback; it never creates work reps.
    - **Acceptance**: athlete 2's Jogging runs read easy, LSD long runs and
      SubThreshold quality; a re-run is a no-op; an unmapped type is reported;
      the current athlete's Intervals/sheet sets are untouched.

50. **Manual thresholds and local zone configs** (core + import + maintenance +
    reports; phase 2b, small write surface). Zones, the derived VO2max and
    intensity all read `athlete_thresholds` and `zone_configs`, which only the
    Intervals recomputes fill. An Intervals-less athlete therefore has no
    zones at all, and Runalyze cannot supply the boundaries (`/api/v1/sport`
    is 403; only percentages are in the payload).
    - **Write surface**: `threshold add|list` per sport with `max_hr`, `lthr`
      and `threshold_pace_mps`, written as dated snapshots with
      `source='manual'` (the tables already carry `source`; no schema change).
      The recompute never removes a manual snapshot.
    - **Derivation**: build the zone configs from the manual snapshots with a
      documented, printed model (for example %LTHR for HR and %threshold pace
      for pace), registered as a recompute; an activity with no config stays
      unzoned rather than borrowing a guess.
    - **Unlocks**: HR/pace zones and zone charts for a non-Intervals athlete;
      the max-HR snapshot the effective-VO2max metric needs; threshold-relative
      subT comparisons where reps exist.
    - **Not**: importing Runalyze's zone percentages as canonical zones — they
      are shares of an unknown config. Keep them as a cross-check if wanted.
    - **Acceptance**: athlete 2 gets zones and a VO2max series from entered
      thresholds; a manual snapshot survives every recompute; a missing
      threshold leaves the report explicitly empty.

51. **Typed work reps without Intervals** (import + maintenance + reports;
    phase 2b). Athlete 2's FIT archive gives device laps but no WORK/RECOVERY
    typing, and Intervals is the only typed source today, so structured runs
    have a segment table but no subT reps.
    - **Check first**: inspect a structured FIT for Garmin `workout` /
      `workout_step` messages. If the watch ran a programmed workout, the
      steps are authoritative; map those before any heuristic.
    - **Fallback heuristic**: when an activity has at least two laps and no
      intervals, infer reps from lap pace and duration — a WORK lap is within a
      small percentage of the session's fastest qualifying laps and at least
      60 s, the rest are RECOVERY. Gate on the Runalyze type (`intervals` /
      `subthreshold`) or on lap variance, so an easy run with 1 km auto splits
      stays laps. Write `activity_intervals` with `source='derived'`, never
      overwriting Intervals or manual rows, idempotent.
    - **Reporting**: the session table already shows laps; a derived set may
      feed the subT tables only when labelled derived, so a worked rep is
      never mistaken for a measured one.
    - **Calibration**: athlete 2's structured sessions show ~3 km reps with
      150–265 m recoveries; that is the first test case. A session whose laps
      cluster into equal fast/slow pairs is the target; a uniform easy run is
      not.
    - **Acceptance**: a SubThreshold session shows work reps and a subT table
      marked derived; an easy run with auto splits stays laps; a re-run is a
      no-op; Intervals-derived reps win where they exist.

52. **Garmin wellness** (import + reports; phase 2b). Athlete 2 has no wellness
    source, so resting HR, HRV and sleep are empty, the recovery tab is blank
    and efficiency has no baseline. Runalyze is not the source: its API exposes
    no daily wellness endpoints (its health entries are injury and sickness
    ranges) and it derives wellness from Garmin.
    - **Path**: probe the Garmin Personal API for daily summaries (sleep, HRV,
      resting HR, steps) with the athlete's key; if the key's API does not
      expose them, parse the wellness files in the GDPR export — the same
      archive that already supplies the FITs.
    - **Write**: `wellness_days` (HRV, resting HR, sleep, weight, SpO2, steps,
      floors), fill-only: an existing day is never overwritten, so Intervals
      stays the owner where both run. A field-level fill is a follow-up.
    - **Sync**: joins item 44 after the activity fetch; idempotent, and a
      missing wellness feed is a warning, not a failure.
    - **Acceptance**: athlete 2's recovery tab and the efficiency baseline
      render from Garmin; the current athlete's Intervals wellness is
      untouched; a re-run is a no-op.

53. **A load fallback when there is no Intervals** (import + reports; phase 2b).
    `training_load` comes only from Intervals' `icu_training_load`, so an
    Intervals-less athlete has an empty load chart, no fitness/fatigue and no
    quality-load split, while the payload carries `trimp` and `fit_trimp` on
    every activity (40/40 on the athlete-2 slice).
    - **Mapping**: `fit_trimp` (device) first, `trimp` as fallback, written to
      `activities.training_load` under `source='runalyze'` only when no
      Intervals load exists. The vendor scale is documented per athlete and
      never presented as the same number as an Intervals load.
    - **Reports**: no change — the load chart, EWMAs and compare read
      `training_load`; the axis is data-driven, so a TRIMP-scale series still
      plots.
    - **Guard**: a mixed database (Intervals plus Runalyze) keeps Intervals'
      value and does not blend the two; provenance shows which source filled
      it.
    - **Acceptance**: athlete 2's overview, load chart and compare render; the
      current athlete's numbers are unchanged; the source is visible in the
      settings/provenance.

## Parked ideas

Not queued and not scheduled; recorded so they are not re-invented. The lab
owns experimentation, and items 13/14/25 own the eventual home.

- **What-if load sandbox** — add or remove a hypothetical session and read the
  42/182-day load impact from the existing load model (lab, no schema).
- **Race execution scorecard** — pacing vs plan, split consistency, HR drift
  and heat for a race day, from data already stored (lab first, then a card if
  it earns one).
- **Corrections export** — a "to fix in Intervals/Runalyze" list built from
  conflicts and their causes, applied by hand; closes the loop without
  write-back (phase 4, with item 14).
- **"As-of" reports** — render the log as it looked at a past date; possible
  because inputs are preserved, expensive, so phase 4 at the earliest.

## Notes

- Reports hide activities with open review items by default
  (`--include-review` shows them); excluded activities never appear.
- `events sync` defaults to today .. today + 182 days; `--from`/`--to`
  override the window, and `--dry-run` reports without writing.
- `./sync.sh` runs the incremental sync (Garmin → Intervals → FIT → review
  scan) and then regenerates the dashboard; `--no-garmin`, `--no-intervals`,
  `--no-fit`, `--no-scan`, and `--no-dashboard` skip those steps.
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
