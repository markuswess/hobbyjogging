# Status and next steps

Updated 2026-11-06.

## Done

- **Canonical pipeline.** FIT archive, Intervals.icu, and Garmin Personal API
  import into one SQLite database with raw-source provenance, temporal
  matching, and owner-based field precedence (no per-source priority).
- **Review & editing.** Interactive triage, manual field overrides, durable
  exclusion, ambiguous-match linking, field-conflict pick value (`v`), forced
  Intervals re-import (`t`), and Intervals/Garmin activity links (`ci`/`cg`).
- **Sources.** Garmin `fetch` downloads original FITs into the archive;
  API-downloaded FITs are byte-identical to the GDPR export. VO2max is read
  from FIT message 140 into `vo2max_garmin`.
- **Schema v5/v6.** `vo2max_garmin`/`vo2max_runalyze` owners, `activity_tags`,
  `activities.moving_s`, and `events.training_load` (with backfill).
- **Schema v7.** `events.excluded_at`; the repository hides excluded events.
  `upsert_event` now replaces event fields (including NULLs) and revives an
  excluded event; `exclude_event`/`restore_event` support the sync prune.
- **Schema v8.** `events.zone_kind` and `event_zone_times` store the planned
  zone distribution (`Z1`–`Z7`, `SS`); the repository exposes it on `Event`.
- **Planned-events sync.** `events sync` (and the regular Intervals import)
  reconciles the calendar: fields are replaced (including NULLs), events that
  disappeared are soft-excluded, reappearing ones are revived, and only
  Intervals-linked events are touched. `--dry-run` writes nothing.
- **Time fields.** Intervals `moving_time` → `moving_s`; FIT
  `total_moving_time` is parsed when present; event duration comes from
  `moving_time` and `training_load` from `icu_training_load`. The
  `moving_time_mismatch` rule flags gaps above `max(10 min, 25%)`.
- **Quality dedupe.** Review items dedupe by
  `(category, fingerprint, activity_id)`, not by source record.
- **Reports.** Markdown reports (daily/weekly/monthly/yearly, period, subT,
  session, activities table), charts, and the terminal renderer; report code
  is split per report.
- **Real data.** Full FIT archive import and Garmin VO2max backfill have run
  against the real database (2,840 activities, 2,797 with a Garmin VO2max).
  The queue cleanup is mostly done; remaining warnings are intentionally left
  in the review list and hide their activities from reports until handled.

## Next

1. **Import package: event zone times.** Map `workout_doc.zoneTimes` into
   `event_zone_times` (kind inferred from targets, sport fallback), have the
   event sync replace/clear them, and add a local `events backfill-zones`
   command for the 620 existing payloads.
2. **View models + static weekly dashboard** in the reports package (main
   focus): weekly overview, activity list/detail, data-health banner, and the
   planned zone distribution (see
   `packages/hobbyjogging-reports/NEXT_UP.md`).
3. **Reports: moving time.** Use `moving_s or duration_s` for pace/volume and
   show planned load in the planned-session sections.
4. **Runalyze enrichment** when the API auth/endpoint details are settled:
   comments merged into `description`, tags, gear via the
   equipment-categories endpoint, `vo2max_runalyze`. Unmatched rows create
   activities.
5. **`review scan` prune mode**: resolve stale quality items whose current
   values no longer trigger them.
6. **Homelab cutover**: DB + importer + dashboard generator + static server,
   periodic backups, Tailscale/basic auth.

## Notes

- Reports hide activities with open review items by default
  (`--include-review` shows them); excluded activities never appear.
- `events sync` defaults to today .. today + 182 days; `--from`/`--to`
  override the window, and `--dry-run` reports without writing.
- The Garmin key is valid for 30/90/180/365 days; each run exchanges it for a
  24 h bearer token.
- Runalyze's activity payload exposes no Garmin activity id, so matching stays
  temporal.
