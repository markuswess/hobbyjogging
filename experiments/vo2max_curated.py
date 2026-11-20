"""Experiment: does Runalyze's manual VO2max curation bias the comparison?

Question
--------
Runalyze's `use_vo2max` flag excludes runs from its VO2max trend: recoveries,
warm-ups, family runs and unusually hilly terrain in normal use. The values
still exist on excluded rows. How much does matching that curated subset change
the agreement between our HR/economy estimate and race VDOT?

Data
----
Canonical run activities, Runalyze payloads linked through `activity_sources`,
and official road race results. No streams.

Outputs
-------
- Per-run our estimate vs Runalyze `vo2max`, all runs vs curated runs.
- Our estimate and Runalyze value on included vs excluded runs.
- Race validation: VDOT vs our all-run estimate, our curated estimate,
  Runalyze `vo2max` and `vo2max_with_elevation`, all from the ±14-day training
  window.

Decision
--------
If the curated subset materially changes the VDOT agreement, the earlier
all-runs validation was selection-biased; if not, the earlier result stands.

    uv run --env-file .env python experiments/vo2max_curated.py
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from statistics import mean, median

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.vo2max import (
    effective_vo2max,
    race_vdot,
    threshold_max_hr,
)
from hobbyjogging_report.shell import table
from hobbyjogging_report.sources import create_source

RECENT_DAYS = 14
MAX_ULTRA_KM = 50.0
HILL_GAIN_PER_KM = 20.0


def load_runalyze(connection, activities: dict) -> dict[str, dict]:
    rows = connection.execute(
        """
        SELECT sr.payload_json, asrc.activity_id
        FROM source_records sr
        JOIN activity_sources asrc ON asrc.source_record_id = sr.id
        WHERE sr.source = 'runalyze' AND sr.record_type = 'activity'
          AND sr.excluded_at IS NULL
        ORDER BY sr.id
        """
    ).fetchall()

    result = {}
    for row in rows:
        activity = activities.get(row["activity_id"])
        if activity is None or activity.type not in RUN_TYPES:
            continue
        try:
            result[activity.id] = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
    return result


def is_race(activity) -> bool:
    return (
        "race" in set(activity.workout_methods)
        or "race" in set(activity.workout_targets)
    )


def stats(pairs: list[tuple[float, float]], label: str):
    if not pairs:
        return (label, 0, "-", "-", "-", "-", "-")

    differences = [a - b for a, b in pairs]
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx = mean(xs)
    my = mean(ys)
    covariance = sum((x - mx) * (y - my) for x, y in pairs)
    variance_x = sum((x - mx) ** 2 for x in xs)
    variance_y = sum((y - my) ** 2 for y in ys)
    r = (
        covariance / (variance_x * variance_y) ** 0.5
        if variance_x and variance_y
        else 0.0
    )
    rmse = (mean([value * value for value in differences])) ** 0.5

    return (
        label,
        len(pairs),
        f"{mean(differences):+.2f}",
        f"{median(differences):+.2f}",
        f"{mean(abs(value) for value in differences):.2f}",
        f"{rmse:.2f}",
        f"{r:+.2f}",
    )


def race_rows(source, activities: dict) -> list[dict]:
    rows = []
    for result in source.race_results():
        activity = activities.get(result.activity_id)
        if activity is None or activity.type != "run":
            continue
        if activity.date < date(2019, 1, 1):
            continue
        if not result.official_distance_m or not result.official_time_s:
            continue

        km = result.official_distance_m / 1000.0
        gain = activity.elevation_gain_m
        if km > MAX_ULTRA_KM:
            continue
        if gain is not None and km and gain / km > HILL_GAIN_PER_KM:
            continue
        name = (result.name or activity.name or "").lower()
        if "relay" in name or "staffel" in name:
            continue

        vdot = race_vdot(result.official_distance_m, result.official_time_s)
        if vdot is None:
            continue

        rows.append(
            {
                "activity": activity,
                "name": result.name or activity.name,
                "km": km,
                "vdot": vdot,
            }
        )
    return sorted(rows, key=lambda row: row["activity"].date)


def main() -> None:
    with create_source() as source:
        activities = {
            activity.id: activity
            for activity in source.activities(date(2000, 1, 1), date.today())
            if activity.type in RUN_TYPES
        }
        payloads = load_runalyze(
            getattr(source, "connection", None), activities
        )
        thresholds = source.athlete_thresholds()
        races = race_rows(source, activities)

    estimates = {}
    for activity_id, activity in activities.items():
        value = effective_vo2max(
            activity, threshold_max_hr(thresholds, activity.date)
        )
        if value is not None:
            estimates[activity_id] = value

    global_curated = [
        payload["vo2max"]
        for payload in payloads.values()
        if payload.get("use_vo2max")
        and isinstance(payload.get("vo2max"), (int, float))
    ]
    global_curated_elev = [
        payload["vo2max_with_elevation"]
        for payload in payloads.values()
        if payload.get("use_vo2max")
        and isinstance(payload.get("vo2max_with_elevation"), (int, float))
    ]
    global_our = mean(estimates.values()) if estimates else None
    curated_estimates = [
        estimates[activity_id]
        for activity_id, payload in payloads.items()
        if payload.get("use_vo2max") and activity_id in estimates
    ]
    global_our_curated = (
        mean(curated_estimates) if curated_estimates else global_our
    )

    print(
        f"{len(activities)} run activities, {len(payloads)} Runalyze payloads, "
        f"{len(estimates)} our estimates, {len(races)} usable road races"
    )

    all_pairs = []
    curated_pairs = []
    included_our = []
    excluded_our = []
    included_vendor = []
    excluded_vendor = []

    for activity_id, payload in payloads.items():
        our = estimates.get(activity_id)
        vendor = payload.get("vo2max")
        curated = bool(payload.get("use_vo2max"))

        if isinstance(vendor, (int, float)):
            if curated:
                included_vendor.append(float(vendor))
            else:
                excluded_vendor.append(float(vendor))

        if our is None:
            continue

        if curated:
            included_our.append(our)
        else:
            excluded_our.append(our)

        if isinstance(vendor, (int, float)):
            pair = (our, float(vendor))
            all_pairs.append(pair)
            if curated:
                curated_pairs.append(pair)

    print("\nper-run agreement (our estimate - Runalyze vo2max):")
    table(
        [
            stats(all_pairs, "all runs"),
            stats(curated_pairs, "curated only"),
        ],
        headers=["group", "n", "mean", "median", "MAD", "RMSE", "r"],
    )

    print("\nselection effect:")
    table(
        [
            (
                "included",
                len(included_our),
                f"{mean(included_our):.2f}" if included_our else "-",
                f"{median(included_our):.2f}" if included_our else "-",
                f"{mean(included_vendor):.2f}" if included_vendor else "-",
                f"{median(included_vendor):.2f}" if included_vendor else "-",
            ),
            (
                "excluded",
                len(excluded_our),
                f"{mean(excluded_our):.2f}" if excluded_our else "-",
                f"{median(excluded_our):.2f}" if excluded_our else "-",
                f"{mean(excluded_vendor):.2f}" if excluded_vendor else "-",
                f"{median(excluded_vendor):.2f}" if excluded_vendor else "-",
            ),
        ],
        headers=[
            "group",
            "n",
            "our mean",
            "our median",
            "Runalyze mean",
            "Runalyze median",
        ],
    )

    race_table = []
    pairs_all = []
    pairs_curated = []
    pairs_vendor = []
    pairs_vendor_elev = []
    fallback = 0
    curated_fallback = 0

    for race in races:
        activity = race["activity"]
        start = activity.date - timedelta(days=RECENT_DAYS)
        end = activity.date + timedelta(days=RECENT_DAYS)
        neighbors = [
            other
            for other in activities.values()
            if other.id != activity.id
            and start <= other.date <= end
            and not is_race(other)
        ]
        all_est = [
            estimates[other.id]
            for other in neighbors
            if other.id in estimates
        ]
        curated_est = [
            estimates[other.id]
            for other in neighbors
            if other.id in estimates
            and bool(payloads.get(other.id, {}).get("use_vo2max"))
        ]
        vendor = [
            float(payloads[other.id]["vo2max"])
            for other in neighbors
            if other.id in payloads
            and payloads[other.id].get("use_vo2max")
            and isinstance(payloads[other.id].get("vo2max"), (int, float))
        ]
        vendor_elev = [
            float(payloads[other.id]["vo2max_with_elevation"])
            for other in neighbors
            if other.id in payloads
            and payloads[other.id].get("use_vo2max")
            and isinstance(
                payloads[other.id].get("vo2max_with_elevation"),
                (int, float),
            )
        ]

        if vendor:
            vendor_value = mean(vendor)
        else:
            vendor_value = mean(global_curated)
            fallback += 1
        if vendor_elev:
            vendor_elev_value = mean(vendor_elev)
        else:
            vendor_elev_value = mean(global_curated_elev)

        all_value = mean(all_est) if all_est else global_our
        if curated_est:
            curated_value = mean(curated_est)
        else:
            curated_value = global_our_curated
            curated_fallback += 1

        pairs_all.append((race["vdot"], all_value))
        pairs_curated.append((race["vdot"], curated_value))
        pairs_vendor.append((race["vdot"], vendor_value))
        pairs_vendor_elev.append((race["vdot"], vendor_elev_value))

        race_table.append(
            (
                activity.date.isoformat(),
                (race["name"] or "")[:28],
                f"{race['km']:.1f}",
                f"{race['vdot']:.1f}",
                f"{all_value:.1f}",
                f"{curated_value:.1f}",
                f"{vendor_value:.1f}",
                f"{vendor_elev_value:.1f}",
                len(all_est),
                len(curated_est),
            )
        )

    print("\nrace validation (VDOT - training-window estimate):")
    table(race_table, headers=[
        "date", "race", "km", "VDOT", "all", "curated",
        "Runalyze", "Runalyze+el", "n all", "n cur",
    ])

    print("\nsummary (VDOT - estimate):")
    table(
        [
            stats(pairs_all, "our all runs"),
            stats(pairs_curated, "our curated"),
            stats(pairs_vendor, "Runalyze"),
            stats(pairs_vendor_elev, "Runalyze + elevation"),
        ],
        headers=["estimate", "n", "mean", "median", "MAD", "RMSE", "r"],
    )

    if pairs_all and pairs_curated:
        shift = mean(
            [a - b for (_, a), (_, b) in zip(pairs_curated, pairs_all)]
        )
        print(
            f"\ncurated minus all training estimate: {shift:+.2f} VO2 units "
            f"({fallback} vendor / {curated_fallback} our-estimate races used "
            f"the global curated fallback)"
        )

    print(
        "\nreading: if 'our curated' is materially closer to VDOT than "
        "'our all runs', the earlier all-run validation was selection-biased. "
        "If the curated and all-run rows are similar, the exclusion mostly "
        "removes noise rather than changing the level."
    )


if __name__ == "__main__":
    main()
