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

## Then

- Run on a DB copy, then migrate and triage the 9 open quality items on the real DB.
- Only after that: CSV import, then Runalyze (see [ROADMAP.md](ROADMAP.md)).
