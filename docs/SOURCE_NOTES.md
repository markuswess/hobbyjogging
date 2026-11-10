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
- `moving_s` and `elapsed_s` are Intervals-authoritative and never produce a
  review item.
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

## Planned events

Intervals events expose only `moving_time`, never elapsed/recording time. The
event `duration_s` is therefore the planned **moving** duration, and
`training_load` comes from `icu_training_load`. Planned zone time comes from
`workout_doc.zoneTimes` (see `event_zones.py`).

## Code references

- `packages/hobbyjogging-import/src/hobbyjogging_import/fit.py` — FIT parsing
  and VO2max message 140.
- `packages/hobbyjogging-import/src/hobbyjogging_import/intervals.py` —
  Intervals activity/event mapping.
- `packages/hobbyjogging-import/src/hobbyjogging_import/quality.py` —
  `moving_time_mismatch` and other quality rules.
- `packages/hobbyjogging-import/src/hobbyjogging_import/causes.py` — conflict
  classification.
- `packages/hobbyjogging-core/src/hobbyjogging_core/db/writer.py` — field
  ownership and tolerances.
