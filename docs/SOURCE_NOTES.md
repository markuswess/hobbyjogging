# Source field notes

Per-source field names and the differences we have actually observed between
Garmin FIT files and Intervals.icu. The canonical model is defined in
`hobbyjogging_core.model`; this page explains how the raw sources map onto it
and why some disagreements are expected.

## Canonical time fields

| Canonical | FIT session field | Intervals.icu field | Meaning |
|---|---|---|---|
| `duration_s` | `total_timer_time` | `icu_recording_time` (fallback `moving_time`) | recording / timer time |
| `moving_s` | `total_moving_time` (optional) | `moving_time` | moving time |
| `elapsed_s` | `total_elapsed_time` | `elapsed_time` | elapsed / wall time |
| `avg_hr` | `avg_heart_rate` | `average_heartrate` | average heart rate |
| `max_hr` | `max_heart_rate` | `max_heartrate` | maximum heart rate |
| `distance_m` | `total_distance` | `distance` | distance |

FIT `total_moving_time` is **optional** and absent in many files. When it is
missing, `moving_s` stays empty and reports fall back to `duration_s`;
Intervals normally supplies it.

Intervals `icu_recording_time` is also optional; old payloads only have
`moving_time`, which is used as the recording-time fallback.

## Observed differences

### Recording/timer vs moving time

The same run can carry three different durations:

- Garmin FIT `total_timer_time` is the timer/recording time. Garmin displays it
  as "moving", but it does not apply Intervals' movement estimate.
- Intervals `moving_time` uses Intervals' own auto-pause/movement estimate.
- Intervals `icu_recording_time` is the recording time and is the closest
  match to FIT `total_timer_time`.

When the device records stopped time (auto-pause off, traffic lights, manual
stops), moving time can be much shorter than recording time. A large gap is
worth reviewing, but it is not automatically an error.

Two sources' recording times are treated as the same measurement when the
difference fits inside either source's pause gap (`elapsed - duration`), or
when it is within **5%** of the stored value. Observed FIT/Intervals
differences run up to about 5% (median ~1.7%), which is what the cause
classifier already calls a "small difference"; anything beyond that is a
different recording (a trim, a manual Intervals edit, or a sheet estimate) and
stays a review item. `duration_s` remains owner-tracked.

### Elapsed time

Garmin elapsed (`total_elapsed_time`) is start-to-save time and includes
trailing stopped time. Intervals elapsed (`elapsed_time`) is the last-record
offset. They usually differ by seconds, and can differ by minutes when the
device kept recording after the workout.

### Average heart rate

Intervals and Garmin can average over different windows (moving vs elapsed,
trimmed vs full recording, sensor dropouts). Small differences are normal;
beyond **5 bpm** the values are treated as a real conflict. A maximum HR above
about 205 bpm suggests a strap/sensor fault, making the average untrustworthy.

### VO2max is per sport

Garmin's FIT message 140 field 7 carries the estimate for the **activity's own
sport**, so `activities.vo2max_garmin` on a ride is the cycling estimate, on a
swim the swimming one, and only on a run the running series. The field is
correct as written; `activities.sport` is the discriminator. Consumers that
present one athlete-level series — the VO2max chart, any trend — must filter to
running, and the session report qualifies the value on non-runs. Intervals
exposes a single `VO2MaxGarmin`, which is the running value.

### Trimmed or reprocessed uploads

One source may cover a different span of the same activity (a trimmed FIT
upload, a reprocessed Intervals activity). In that case both recording time and
distance differ together; this is classified as `activity_trimmed` and usually
needs a human decision about which source is complete.

### Manual Intervals edits

Intervals payloads carry `icu_intervals_edited` (and `source =
"GARMIN_CONNECT"`). When it is true, the user has edited the activity in
Intervals; Intervals is the corrected truth even if the FIT file still holds
the device's original values. Under the owner-based rules this becomes a
review item rather than an automatic overwrite.

## The Gumpoldskirchen case (2026-03-14)

A concrete example of all three differences at once:

| | FIT | Intervals (after manual edit) |
|---|---|---|
| recording / timer | 56:55 | 17:35 |
| moving | — (no `total_moving_time`) | 17:35 |
| elapsed | 56:59 | 17:36 |
| distance | 3.73 km | 3.21 km |
| average HR | 103 bpm | 131 bpm |

The device recorded 56:55 of timer time; the user corrected the activity in
Intervals to 17:35 moving time over 3.21 km with 131 bpm
(`icu_intervals_edited = true`). The old FIT-priority rule overwrote the
correction. Today this produces `field_conflict` review items for
`duration_s`, `moving_s`/`elapsed_s`, `distance_m`, and `avg_hr`; the user
picks the correct values in triage. The moving/recording gap (69%) also fires
the `moving_time_mismatch` quality rule.

## Precedence and review

- `duration_s` is owner-tracked; reimports from the same source refresh it.
- `moving_s` and `elapsed_s` use a ranked authority (Intervals, then FIT) and
  never produce a review item.
- `avg_hr` differences only count beyond 5 bpm.
- Other timing fields use about 1% relative tolerance with 2 s / 10 m floors;
  start times tolerate 15 s.
- Conflicts are classified by `hobbyjogging_import.causes`:
  `activity_trimmed`, `elapsed_definition`, `moving_estimate`,
  `small_difference`, `start_offset`, `hr_sensor_anomaly`,
  `sport_vocabulary`, `distance_estimate`, `duration_estimate`, `unknown`.
  Advisory causes (`elapsed_definition`, `moving_estimate`,
  `small_difference`, `start_offset`) can be bulk-resolved; the rest need a
  per-activity decision.

## Routes

The sheet's `Strecke` is the route name and `Streckennummer` the stable key;
389 rows carry a name, 360 a number, and 29 name-only rows are resolved through
the number seen for the same name elsewhere (`Kaserne` → 6). A name with no
single number, or with several (`Lusthaus` 33/330), keeps a name-scoped key
instead of being merged. The Gmap link is not a route. Runalyze's activity
payload nests a `recurring_route` (id, name, distance, start/end coordinates,
bounding box); its id is a different identity from a `Streckennummer`, so the
two never merge automatically.

## Planned events

Intervals events expose only `moving_time`, never elapsed/recording time. The
event `duration_s` is therefore the planned **moving** duration, and
`training_load` comes from `icu_training_load`. Planned zone time comes from
`workout_doc.zoneTimes` (see `event_zones.py`).

## Runalyze

The personal API is read-only for the current token. The base is
`https://runalyze.com/api/v1` and the header is `token: <key>`. The budget is
**240 requests per window** (roughly an hour); `Retry-After` and
`X-RateLimit-Reset` give the exact reset, and the client stops cleanly on a
429. One activity detail is one request, so a full history of 2,841 activities
needs about 12 windows.

- The activity collection is **`/api/v1/activity` (singular)** with `page` and
  `itemsPerPage`. Its `time[...]` filters are ignored, so read every page and
  apply `--since`/`--to` locally. The live inventory saw 2,841 activities
  (2019–2026).
- The collection carries 82 non-null fields; the detail carries 85–88 of the
  153 fields in the schema. Detail-only data includes `tags`
  (`[{id, tag}]`) and `equipment` when present.
- **Comments are `note`**; `title` is the Garmin auto-title and never becomes
  `activities.name`.
- **Tags are detail-only.** The collection has no `tags`, `?tag=<id>` on the
  collection is ignored, and `/api/v1/statistics/tags` answers 403. The
  `/api/v1/tag` collection lists the definitions (`{id, tag}`), but the
  activity-to-tag link comes from each activity's detail payload.
- `sport` and `type` are nested objects; `device_name` is the recorder;
  `recurring_route` nests id, name, distance and start/end/bounding
  coordinates; `vo2max`, `vo2max_by_time`, `vo2max_with_elevation` and
  `use_vo2max` are all present.
- Endpoints that answer 200: `ping`, `activity`, `equipment`, `tag`. The four
  that answer 403 are `sport`, `recurring-route`, `planned-race` and
  `device-profile`; the nested activity data covers the route and device name.
- `equipment` is an array of full `EquipmentDto` objects in the activity
  detail (`id`, `name`, `notes`, `category_id`, `date_start`, `date_end`, usage
  fields), so gear comes with the detail and needs no separate fetch. The
  `/api/v1/equipment` collection returns the same shape, and
  `/api/v1/equipment/category` lists the category names. There is **no brand
  or model**.
- The OpenAPI document at `/api/docs.jsonopenapi` needs
  `Accept: application/vnd.openapi+json`; a plain JSON accept gets a 406.

## Strava

The bulk export (ZIP or extracted directory) is the supported path. It needs
no API app, OAuth token or Strava subscription.

- `activities.csv` is the manifest: activity id, date/time, name, type,
  description, elapsed and moving time, distance, gear, filename, privacy and
  commute flags. Headers vary by export version and account language, so the
  reader uses aliases; fields containing commas are quoted by Strava.
- The 2026 export is **wide**: `Distance` and `Elapsed Time` appear twice, and
  the second `Distance` is always metres (the first is km for runs and rides,
  metres for swims and rowing). Gear lives in `Activity Gear`, while `Gear`
  stays empty. The reader parses by column index and prefers the metres
  column; `--distance-unit` only applies to a single-column export.
- `bikes.csv` and `shoes.csv` carry gear name, brand and model, but no gear
  id, distance or retirement date. `activities.csv` names the gear.
- `activities/` holds the original FIT/TCX/GPX files. It is ignored: the FIT
  archive already covers the recordings, and importing both would duplicate
  them.
- `Activity Date` carries the **account's** timezone, not necessarily the
  activity's local time; this account is UTC. `--date-zone auto` (default)
  matches the export under both readings and keeps the one that matches more
  activities; `local` and `utc` force one. The choice is printed and recorded
  in the import run.
- On the real 2026 export, 2,554 of 2,590 activities matched; the 35 unmatched
  are mostly other sports (alpine ski, swim, hike) or genuine distance
  disagreements, and write nothing.
- Social text goes to `activity_social(source='strava')` by default. A
  per-source target in `sources.toml` may promote it to `activities.name`/
  `description`; a promoted title reaches `classify()`, which matches `race`,
  `tempo`, `subt` and `warm up` as substrings — "Race you to the bakery"
  classifies as a race (quality). Descriptions do not feed the classifier.
- Unmatched rows follow the per-source `create | review | ignore` policy in
  `sources.toml` (this athlete keeps Strava at `ignore`), and creation only
  happens when there is nothing to review.
- Gear is matched by exact normalized name. A matched equipment row is only
  linked, never rewritten; an unknown name creates
  `strava:gear:<slug>` with the CSV brand/model.
- The API is deferred. Creating a Strava app now requires a Strava
  subscription; single-player read limits are 100 requests per 15 minutes and
  1,000 per day. The summary list plus per-activity detail is the shape, and
  `suffer_score` must not be mapped to `training_load`.

## Open-Meteo

The keyless archive is the historical ambient-weather source.

- The command is `hobbyjogging-import weather [--from DATE --to DATE]
  [--days N] [--limit N] [--dry-run] [--refresh]`.
- The start coordinate comes from the linked FIT session
  (`start_position_lat/long` or the first GPS record); the FIT archive is
  re-read for payloads written before the coordinate was stored. A missing
  coordinate is reported, never guessed.
- The coordinate is rounded to two decimals (~1 km) and the UTC start to the
  hour. One response serves every activity in that cell and hour; it is stored
  as `source_records(source='open-meteo', record_type='weather')`.
- `temp_c`, feels-like, humidity, wind/gust/direction, pressure, cloud cover,
  condition and the day/night flag are written to `activity_weather`.
  Open-Meteo owns the ambient fields; a later sheet or Intervals import only
  fills an empty row or keeps its value as the fallback.
- An indoor sport is skipped even when its file carries a stale coordinate.

## Leistungstests

The legacy performance-test tab is a block layout, not a row-per-activity
table. A block starts at a `Start` row (or a date-only heading) and runs to
the next block.

- The main header gives `Datum`, `Startzeit`, `Distanz`, `Zielzeit`,
  `CP Nr`, `Distanz`, `Ges. D.`, `Zeit`, `Puls` and `Gesamtzeit`. The
  `Geschw/Puls Test` block overrides the middle columns with `Strecke`,
  `Puls` and `Zeit`; the reader detects it.
- A split is a row with a positive segment `Distanz` and a positive `Zeit`.
  `Ges. D.` supplies the cumulative distance and the run's last valid
  `Gesamtzeit` the official total time.
- `Datum` may be a date cell, a text date (`26.3.2017`), a date without a
  year (`29.9.`), or absent on a second block on the same day. The year is
  borrowed from the neighboring block and the date from the previous block;
  both assumptions are recorded.
- A result comment in the first two columns carries the place: `Gesamt N.`,
  `Gesamtstaffel N.`, `Klasse N.` / `Klassen N.`, `M-30: N.` and `Sieg`.
- The relay block (`Vienna City Marathon Staffel`, 15.9 km) is a normal race
  result, not a special status. The `Wien Rundumadum` placeholder and
  `VCM 10K` have no usable splits; `Paris Marathon` is empty.

## Code references

- `packages/hobbyjogging-import/src/hobbyjogging_import/fit.py` — FIT parsing
  and VO2max message 140.
- `packages/hobbyjogging-import/src/hobbyjogging_import/intervals.py` —
  Intervals activity/event mapping.
- `packages/hobbyjogging-import/src/hobbyjogging_import/runalyze.py` —
  read-only Runalyze client and inventory.
- `packages/hobbyjogging-import/src/hobbyjogging_import/strava.py` — Strava
  bulk-export reader.
- `packages/hobbyjogging-import/src/hobbyjogging_import/strava_import.py` —
  Strava social/gear import.
- `packages/hobbyjogging-import/src/hobbyjogging_import/routes.py` — sheet
  route identity.
- `packages/hobbyjogging-import/src/hobbyjogging_import/quality.py` —
  `moving_time_mismatch` and other quality rules.
- `packages/hobbyjogging-import/src/hobbyjogging_import/causes.py` — conflict
  classification.
- `packages/hobbyjogging-core/src/hobbyjogging_core/db/writer.py` — field
  ownership and tolerances.
