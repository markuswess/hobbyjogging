"""Experiment: audit the per-activity payloads and the Runalyze curation.

Question
--------
Which per-activity payload fields are available in `source_records`, at what
coverage, in which units, and what does Runalyze's manual `use_vo2max`
exclusion actually select? This is the inventory before using payload fields
as terrain, route, durability or economy covariates.

Data
----
`source_records` payloads linked through `activity_sources` to canonical run
activities. The canonical model supplies date, sport, duration, distance,
elevation, HR and device. No streams are read.

Outputs
-------
- Field coverage overall and by year.
- Device coverage for the running-dynamics fields.
- `use_vo2max` selection: counts, values on excluded rows, reason proxies and
  a simple rule's confusion matrix.
- Unit checks for `gap`, `PaceHR`, decoupling, efficiency index, HR recovery,
  weight and resting HR.
- Source agreement for temperature, weight and VO2max.
- A usable / needs-audit / do-not-use recommendation.

Decision
--------
Only fields with clear units and stable coverage move to the next stage.

    uv run --env-file .env python experiments/payload_audit.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean, median

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.shell import table
from hobbyjogging_report.sources import create_source

RUNALYZE_FIELDS = [
    "use_vo2max",
    "gap",
    "vo2max",
    "vo2max_with_elevation",
    "aerobic_decoupling_pace",
    "efficiency_index",
    "fit_training_effect",
    "cadence",
    "stride_length",
    "groundcontact",
    "vertical_oscillation",
    "recurring_route",
    "route_name",
    "climb_score",
    "percentage_hilly",
    "running_effectiveness",
    "temperature",
    "humidity",
    "wind_speed",
    "uphill_efficiency",
    "downhill_efficiency",
]

INTERVALS_FIELDS = [
    "PaceHR",
    "icu_hrr",
    "AerobicEffect",
    "AnaerobicEffect",
    "icu_weight",
    "icu_resting_hr",
    "icu_training_load",
    "icu_intensity",
    "interval_summary",
    "compliance",
    "average_temp",
    "decoupling",
    "icu_efficiency_factor",
    "GAPOverAvgHR",
    "gap",
    "route_id",
]

KEY_YEAR_FIELDS = {
    "runalyze": [
        "use_vo2max",
        "gap",
        "vo2max_with_elevation",
        "aerobic_decoupling_pace",
        "recurring_route",
    ],
    "intervals": ["icu_hrr", "icu_weight", "icu_training_load"],
}


def has_value(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = mean(xs)
    my = mean(ys)
    covariance = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    variance_x = sum((x - mx) ** 2 for x in xs)
    variance_y = sum((y - my) ** 2 for y in ys)
    if not variance_x or not variance_y:
        return None
    return covariance / (variance_x * variance_y) ** 0.5


def percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def load_payloads(connection, source_name: str, activities: dict) -> list[dict]:
    rows = connection.execute(
        """
        SELECT sr.id, sr.payload_json, asrc.activity_id
        FROM source_records sr
        JOIN activity_sources asrc ON asrc.source_record_id = sr.id
        WHERE sr.source = ? AND sr.record_type = 'activity'
          AND sr.excluded_at IS NULL
        ORDER BY sr.id
        """,
        (source_name,),
    ).fetchall()

    by_activity: dict[str, dict] = {}

    for row in rows:
        activity = activities.get(row["activity_id"])
        if activity is None or activity.type not in RUN_TYPES:
            continue
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
        by_activity[activity.id] = {
            "activity": activity,
            "payload": payload,
        }

    return list(by_activity.values())


def nearest_wellness(day: date, wellness: dict[date, object]):
    for offset in range(0, 8):
        for sign in (1, -1) if offset else (1,):
            key = day + timedelta(days=sign * offset)
            if key in wellness:
                return wellness[key]
    return None


def coverage_table(records: list[dict], fields: list[str], source: str) -> None:
    rows = []
    for field in fields:
        count = sum(
            has_value(record["payload"].get(field))
            for record in records
        )
        rows.append(
            (
                source,
                field,
                count,
                f"{100 * count / len(records):.0f}%" if records else "-",
            )
        )
    table(rows, headers=["source", "field", "n", "share"])


def year_table(records: list[dict], fields: list[str], source: str) -> None:
    years = ["2022", "2023", "2024", "2025", "2026"]
    by_year: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()

    for record in records:
        year = record["activity"].date.isoformat()[:4]
        if year not in years:
            continue
        totals[year] += 1
        for field in fields:
            if has_value(record["payload"].get(field)):
                by_year[year][field] += 1

    rows = []
    for field in fields:
        rows.append(
            (
                source,
                field,
                *[
                    f"{100 * by_year[year][field] / totals[year]:.0f}%"
                    if totals[year]
                    else "-"
                    for year in years
                ],
            )
        )
    table(rows, headers=["source", "field", *years])


def device_table(
    records: list[dict],
    devices: dict[str, str],
) -> None:
    fields = [
        "cadence",
        "stride_length",
        "groundcontact",
        "vertical_oscillation",
    ]
    by_device: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        device = devices.get(record["activity"].device_id, "unknown")
        by_device[device].append(record)

    def share(chunk, field):
        count = sum(has_value(row["payload"].get(field)) for row in chunk)
        return f"{100 * count / len(chunk):.0f}%"

    rows = []
    for device, chunk in sorted(
        by_device.items(), key=lambda item: -len(item[1])
    ):
        if len(chunk) < 20:
            continue
        rows.append(
            (device, len(chunk), *[share(chunk, field) for field in fields])
        )
    table(rows, headers=["device", "runs", *fields])


def selection_table(records: list[dict], activities: dict) -> None:
    by_year: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        year = record["activity"].date.isoformat()[:4]
        flag = bool(record["payload"].get("use_vo2max"))
        by_year[year]["true" if flag else "false"] += 1

    table(
        [
            (
                year,
                counts["true"] + counts["false"],
                counts["true"],
                counts["false"],
                f"{100 * counts['false'] / (counts['true'] + counts['false']):.0f}%"
                if counts["true"] + counts["false"]
                else "-",
            )
            for year, counts in sorted(by_year.items())
            if counts["true"] + counts["false"]
        ],
        headers=["year", "runs", "use true", "use false", "false share"],
    )

    excluded = [
        record
        for record in records
        if not bool(record["payload"].get("use_vo2max"))
    ]
    included = [
        record
        for record in records
        if bool(record["payload"].get("use_vo2max"))
    ]

    def share(chunk, predicate):
        return (
            100 * sum(predicate(record) for record in chunk) / len(chunk)
            if chunk
            else 0
        )

    def gain_per_km(record):
        activity = record["activity"]
        if not activity.elevation_gain_m or not activity.distance_m:
            return None
        return activity.elevation_gain_m / (activity.distance_m / 1000.0)

    def median_km(chunk):
        values = [
            record["activity"].distance_m / 1000.0
            for record in chunk
            if record["activity"].distance_m
        ]
        return median(values) if values else None

    def median_gain(chunk):
        values = [
            gain_per_km(record)
            for record in chunk
            if gain_per_km(record) is not None
        ]
        return median(values) if values else None

    def hilly(record):
        value = gain_per_km(record)
        return value is not None and value > 20

    def recovery(record):
        return "recovery" in set(record["activity"].workout_targets)

    def warm(record):
        name = (record["activity"].name or "").lower()
        return "warm" in name or "cool" in name

    def family(record):
        name = (record["activity"].name or "").lower()
        return any(
            word in name
            for word in ("family", "familie", "kinder", "pram", "stroller", "buggy")
        )

    def trail(record):
        return record["activity"].type == "trail_run"

    def short(record):
        return record["activity"].duration_s < 20 * 60

    def duplicate_day(record):
        return day_counts[record["activity"].date] > 1

    day_counts = Counter(
        activity.date
        for activity in activities.values()
        if activity.type in RUN_TYPES
    )

    table(
        [
            ("excluded runs", len(excluded)),
            ("with vo2max value", sum(
                has_value(record["payload"].get("vo2max"))
                for record in excluded
            )),
            ("with elevation value", sum(
                has_value(record["payload"].get("vo2max_with_elevation"))
                for record in excluded
            )),
            (
                "median km",
                f"{median_km(excluded):.1f}" if median_km(excluded) else "-",
            ),
            (
                "median gain/km",
                f"{median_gain(excluded):.1f}"
                if median_gain(excluded)
                else "-",
            ),
            ("trail share", f"{share(excluded, trail):.0f}%"),
            ("recovery target", f"{share(excluded, recovery):.0f}%"),
            ("warm/cool name", f"{share(excluded, warm):.0f}%"),
            ("family name", f"{share(excluded, family):.0f}%"),
            ("hilly >20 m/km", f"{share(excluded, hilly):.0f}%"),
            ("short <20 min", f"{share(excluded, short):.0f}%"),
            ("duplicate day", f"{share(excluded, duplicate_day):.0f}%"),
        ],
        headers=["excluded selection", "value"],
    )

    proxies = [
        ("recovery target", recovery),
        ("warm/cool name", warm),
        ("family name", family),
        ("trail", trail),
        ("hilly >20", hilly),
        ("short <20", short),
        ("duplicate day", duplicate_day),
    ]
    table(
        [
            (
                label,
                f"{share(excluded, predicate):.0f}%",
                f"{share(included, predicate):.0f}%",
            )
            for label, predicate in proxies
        ],
        headers=["proxy", "excluded", "included"],
    )

    def rule(record, include_hilly: bool) -> bool:
        return (
            recovery(record)
            or warm(record)
            or family(record)
            or trail(record)
            or short(record)
            or (include_hilly and hilly(record))
        )

    for include_hilly in (True, False):
        tp = sum(rule(record, include_hilly) for record in excluded)
        fp = sum(rule(record, include_hilly) for record in included)
        fn = len(excluded) - tp
        tn = len(included) - fp
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        label = "rule + hilly" if include_hilly else "rule without hilly"
        print(
            f"  {label}: TP {tp}, FP {fp}, FN {fn}, TN {tn}; "
            f"precision {precision:.2f}, recall {recall:.2f}"
        )


def unit_checks(records: list[dict], activities: dict, wellness: dict) -> None:
    gaps = []
    ratios = []
    products = []
    for record in records:
        activity = record["activity"]
        gap = record["payload"].get("gap")
        if (
            not isinstance(gap, (int, float))
            or not activity.distance_m
            or not activity.duration_s
        ):
            continue
        speed_kmh = activity.distance_m / activity.duration_s * 3.6
        if speed_kmh <= 0:
            continue
        gaps.append(float(gap))
        ratios.append(float(gap) / speed_kmh)
        products.append(float(gap) * speed_kmh)

    if ratios:
        print(
            f"  gap: n={len(ratios)}, median {median(gaps):.2f}; "
            f"gap/speed_kmh median {median(ratios):.2f} "
            f"(~1 = km/h, ~3.6 = m/s), "
            f"gap*speed_kmh median {median(products):.1f} "
            f"(~60 = min/km)"
        )

    vo2_raw = []
    vo2_canonical = []
    for record in records:
        payload = record["payload"]
        value = payload.get("vo2max")
        canonical = record["activity"].vo2max_runalyze
        if isinstance(value, (int, float)) and canonical is not None:
            vo2_raw.append(float(value))
            vo2_canonical.append(float(canonical))
    if vo2_raw:
        differences = [a - b for a, b in zip(vo2_canonical, vo2_raw)]
        print(
            f"  vo2max payload vs canonical: n={len(differences)}, "
            f"median diff {median(differences):+.2f}, "
            f"r {correlation(vo2_raw, vo2_canonical) or 0:+.2f}"
        )

    elevation_gain = []
    for record in records:
        payload = record["payload"]
        raw = payload.get("vo2max")
        corrected = payload.get("vo2max_with_elevation")
        activity = record["activity"]
        if (
            isinstance(raw, (int, float))
            and isinstance(corrected, (int, float))
            and activity.distance_m
        ):
            gain = activity.elevation_gain_m or 0
            elevation_gain.append(
                (gain / (activity.distance_m / 1000.0), corrected - raw)
            )
    if elevation_gain:
        buckets = [
            ("flat <5", lambda value: value < 5),
            ("rolling 5-15", lambda value: 5 <= value < 15),
            ("hilly 15+", lambda value: value >= 15),
        ]
        rows = []
        for label, predicate in buckets:
            values = [
                delta
                for gain, delta in elevation_gain
                if predicate(gain)
            ]
            if values:
                rows.append(
                    (label, len(values), f"{median(values):+.2f}")
                )
        print("  vo2max_with_elevation - vo2max by gain/km:")
        table(rows, headers=["terrain", "n", "median delta"])

    decoupling = [
        float(record["payload"]["aerobic_decoupling_pace"])
        for record in records
        if isinstance(
            record["payload"].get("aerobic_decoupling_pace"), (int, float)
        )
    ]
    if decoupling:
        print(
            f"  aerobic_decoupling_pace: n={len(decoupling)}, "
            f"min {min(decoupling):.1f}, median {median(decoupling):.1f}, "
            f"p90 {percentile(decoupling, 0.9):.1f}"
        )

    efficiency = [
        float(record["payload"]["efficiency_index"])
        for record in records
        if isinstance(record["payload"].get("efficiency_index"), (int, float))
    ]
    if efficiency:
        print(
            f"  efficiency_index: n={len(efficiency)}, "
            f"min {min(efficiency):.2f}, median {median(efficiency):.3f}, "
            f"p90 {percentile(efficiency, 0.9):.2f}"
        )


def intervals_checks(records: list[dict], wellness: dict) -> None:
    pace_hr = []
    speed_hr = []
    speed_excess = []
    for record in records:
        value = record["payload"].get("PaceHR")
        activity = record["activity"]
        if (
            not isinstance(value, (int, float))
            or not activity.distance_m
            or not activity.duration_s
            or not activity.avg_hr
        ):
            continue
        speed = activity.distance_m / activity.duration_s
        pace_hr.append(float(value))
        speed_hr.append(speed / activity.avg_hr)
        moment = nearest_wellness(activity.date, wellness)
        if moment is not None and moment.resting_hr is not None:
            excess = activity.avg_hr - moment.resting_hr
            if excess > 0:
                speed_excess.append((value, speed / excess))
    if pace_hr:
        print(
            f"  PaceHR: n={len(pace_hr)}, median {median(pace_hr):.3f}; "
            f"r vs speed/HR {correlation(pace_hr, speed_hr) or 0:+.2f}"
        )
    if speed_excess:
        xs = [pair[0] for pair in speed_excess]
        ys = [pair[1] for pair in speed_excess]
        print(
            f"  PaceHR vs speed/excess HR: n={len(xs)}, "
            f"r {correlation(xs, ys) or 0:+.2f}"
        )

    hrr = []
    for record in records:
        value = record["payload"].get("icu_hrr")
        if isinstance(value, dict) and isinstance(value.get("hrr"), (int, float)):
            hrr.append(float(value["hrr"]))
    if hrr:
        print(
            f"  icu_hrr: n={len(hrr)}, min {min(hrr):.0f}, "
            f"median {median(hrr):.0f}, p90 {percentile(hrr, 0.9):.0f}"
        )

    weights = []
    rhrs = []
    for record in records:
        activity = record["activity"]
        moment = nearest_wellness(activity.date, wellness)
        payload = record["payload"]
        if (
            moment is not None
            and moment.weight_kg is not None
            and isinstance(payload.get("icu_weight"), (int, float))
        ):
            weights.append(float(payload["icu_weight"]) - moment.weight_kg)
        if (
            moment is not None
            and moment.resting_hr is not None
            and isinstance(payload.get("icu_resting_hr"), (int, float))
        ):
            rhrs.append(float(payload["icu_resting_hr"]) - moment.resting_hr)
    if weights:
        print(
            f"  icu_weight vs wellness: n={len(weights)}, "
            f"median diff {median(weights):+.2f} kg"
        )
    if rhrs:
        print(
            f"  icu_resting_hr vs wellness: n={len(rhrs)}, "
            f"median diff {median(rhrs):+.1f} bpm"
        )


def temperature_check(
    runalyze: list[dict],
    intervals: list[dict],
    weather: dict[str, float],
) -> None:
    pairs = []
    for record in runalyze:
        activity = record["activity"]
        runalyze_temp = record["payload"].get("temperature")
        canonical = weather.get(activity.id)
        intervals_temp = next(
            (
                other["payload"].get("average_temp")
                for other in intervals
                if other["activity"].id == activity.id
            ),
            None,
        )
        if isinstance(runalyze_temp, (int, float)) and isinstance(
            intervals_temp, (int, float)
        ):
            pairs.append(("runalyze-intervals", runalyze_temp - intervals_temp))
        if (
            isinstance(runalyze_temp, (int, float))
            and canonical is not None
        ):
            pairs.append(("runalyze-canonical", runalyze_temp - canonical))
    by_source = defaultdict(list)
    for label, difference in pairs:
        by_source[label].append(difference)
    for label, values in sorted(by_source.items()):
        print(
            f"  temperature {label}: n={len(values)}, "
            f"median diff {median(values):+.2f} C"
        )


def main() -> None:
    with create_source() as source:
        connection = getattr(source, "connection", None)
        activities = {
            activity.id: activity
            for activity in source.activities(date(2000, 1, 1), date.today())
            if activity.type in RUN_TYPES
        }
        wellness = {
            day.date: day
            for day in source.wellness(date(2000, 1, 1), date.today())
        }
        devices = {
            device.id: device.product or device.name or device.id
            for device in source.devices()
        }
        weather = {
            row["activity_id"]: row["temp_c"]
            for row in connection.execute(
                "SELECT activity_id, temp_c FROM activity_weather"
            )
        }
        runalyze = load_payloads(connection, "runalyze", activities)
        intervals = load_payloads(connection, "intervals", activities)

    print(
        f"run activities: {len(activities)}; "
        f"Runalyze payloads: {len(runalyze)}; "
        f"Intervals payloads: {len(intervals)}"
    )

    print("\nRunalyze field coverage:")
    coverage_table(runalyze, RUNALYZE_FIELDS, "runalyze")

    print("\nIntervals field coverage:")
    coverage_table(intervals, INTERVALS_FIELDS, "intervals")

    print("\nKey field coverage by year:")
    for source_name, records, fields in (
        ("runalyze", runalyze, KEY_YEAR_FIELDS["runalyze"]),
        ("intervals", intervals, KEY_YEAR_FIELDS["intervals"]),
    ):
        year_table(records, fields, source_name)

    print("\nRunning-dynamics coverage by device (Runalyze, >=20 runs):")
    device_table(runalyze, devices)

    print("\nRunalyze use_vo2max selection:")
    selection_table(runalyze, activities)

    print("\nRunalyze unit and value checks:")
    unit_checks(runalyze, activities, wellness)

    print("\nIntervals unit and value checks:")
    intervals_checks(intervals, wellness)

    print("\nSource agreement:")
    temperature_check(runalyze, intervals, weather)

    print("\nrecommendation:")
    print(
        "  use as a label: use_vo2max is manual comparability, not data "
        "availability; 355 runs are excluded and still carry values."
    )
    print(
        "  use after unit check: Runalyze gap is km/h (median ratio 1.01); "
        "vo2max_with_elevation is terrain-sensitive (+1.0 / +2.4 / +6.7 "
        "by gain bucket)."
    )
    print(
        "  use as candidates: aerobic_decoupling_pace, recurring_route, "
        "cadence/stride/GCT/VO, icu_hrr, icu_weight, icu_resting_hr."
    )
    print(
        "  cross-check only: PaceHR (gross speed/HR, r 0.99 with speed/HR; "
        "r 0.60 with speed/excess HR), efficiency_index, "
        "running_effectiveness."
    )
    print(
        "  do not mix temperature sources: Runalyze is ~5.7 C below "
        "canonical/Intervals."
    )
    print(
        "  the manual exclusion is not a simple rule: precision 0.33, "
        "recall 0.40; keep the flag as a label."
    )
    print("  next: Stage 1 curated-subset validation.")


if __name__ == "__main__":
    main()
