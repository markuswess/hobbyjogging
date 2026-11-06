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
- **Schema v5.** `activities.vo2max_garmin`, `activities.vo2max_runalyze`, and
  `activity_tags` (per source, manual tags protected).
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

1. **View models + static weekly dashboard** in the reports package (main
   focus): weekly overview, activity list/detail, data-health banner.
2. **Runalyze enrichment** when the API auth/endpoint details are settled:
   comments merged into `description`, tags, gear via the
   equipment-categories endpoint, `vo2max_runalyze`. Unmatched rows create
   activities.
3. **Homelab cutover**: DB + importer + dashboard generator + static server,
   periodic backups, Tailscale/basic auth.

## Notes

- Reports hide activities with open review items by default
  (`--include-review` shows them); excluded activities never appear.
- The Garmin key is valid for 30/90/180/365 days; each run exchanges it for a
  24 h bearer token.
- Runalyze's activity payload exposes no Garmin activity id, so matching stays
  temporal.
