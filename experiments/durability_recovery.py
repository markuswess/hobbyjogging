"""Experiment: do durability and HR recovery add independent signal?

Question
--------
Efficiency and VO2max describe the aerobic level. Do within-run decoupling,
heart-rate recovery after work reps, and rep-to-rep fade add a separate
durability axis? The Runalyze payload stores `aerobic_decoupling_pace`; the
Intervals payload stores `icu_hrr`. Both are validated against lap and interval
data before use.

Data
----
Canonical activities and laps, Runalyze decoupling, Intervals HR recovery,
work intervals, resting-HR baselines. No streams.

Outputs
-------
- Lap-derived decoupling vs Runalyze `aerobic_decoupling_pace`.
- Runalyze decoupling by year and duration.
- `icu_hrr` by structure group and year.
- Rep-to-rep pace and HR fade for subT/threshold sessions.
- A two-panel plot: decoupling validation and HR recovery trend.

Decision
--------
If the vendor decoupling tracks the lap-derived value, it is usable for the
runs without enough laps. If HR recovery or rep fade adds signal beyond
efficiency, keep them as a separate durability axis; otherwise drop them.

    uv run --env-file .env python experiments/durability_recovery.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from statistics import mean, median

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hobbyjogging_core.classify import work_intervals
from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    is_steady_run,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_LAP_MINUTES = 30.0
MIN_LAP_HALF = 2


def load_payloads(connection, source_name: str, activities: dict) -> dict[str, dict]:
    rows = connection.execute(
        """
        SELECT sr.payload_json, asrc.activity_id
        FROM source_records sr
        JOIN activity_sources asrc ON asrc.source_record_id = sr.id
        WHERE sr.source = ? AND sr.record_type = 'activity'
          AND sr.excluded_at IS NULL
        ORDER BY sr.id
        """,
        (source_name,),
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


def group_of(activity) -> str:
    methods = set(activity.workout_methods)
    targets = set(activity.workout_targets)
    if "race" in methods or "race" in targets:
        return "race"
    if "recovery" in targets:
        return "recovery"
    if "long_run" in methods:
        return "long"
    if targets & {"subthreshold", "threshold", "lt1"}:
        return "subT/threshold"
    if "vo2max" in targets or "intervals" in methods:
        return "VO2max/intervals"
    if methods & {"fartlek", "progression"}:
        return "fartlek/progression"
    return "easy/base"


def half_efficiency(laps: list, resting_hr: float) -> float | None:
    if not laps:
        return None
    duration = sum(lap.duration_s for lap in laps)
    distance = sum(lap.distance_m for lap in laps)
    hr_pairs = [
        (lap.avg_hr, lap.duration_s)
        for lap in laps
        if lap.avg_hr is not None
    ]
    if duration <= 0 or distance <= 0 or not hr_pairs:
        return None
    hr = sum(value * seconds for value, seconds in hr_pairs) / sum(
        seconds for _, seconds in hr_pairs
    )
    excess = hr - resting_hr
    if excess < 10:
        return None
    return distance / (excess * duration / 60.0)


def lap_decoupling(laps: list, resting_hr: float) -> float | None:
    usable = [
        lap
        for lap in laps
        if lap.duration_s > 0 and lap.distance_m > 0 and lap.avg_hr is not None
    ]
    if len(usable) < 2 * MIN_LAP_HALF:
        return None
    if sum(lap.duration_s for lap in usable) < MIN_LAP_MINUTES * 60:
        return None

    total = sum(lap.duration_s for lap in usable)
    first = []
    second = []
    cumulative = 0.0
    for lap in usable:
        if cumulative + lap.duration_s / 2 <= total / 2:
            first.append(lap)
        else:
            second.append(lap)
        cumulative += lap.duration_s

    if len(first) < MIN_LAP_HALF or len(second) < MIN_LAP_HALF:
        return None

    first_eff = half_efficiency(first, resting_hr)
    second_eff = half_efficiency(second, resting_hr)
    if first_eff is None or second_eff is None or first_eff <= 0:
        return None
    return (first_eff - second_eff) / first_eff * 100.0


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


def main() -> None:
    with create_source() as source:
        activities = {
            activity.id: activity
            for activity in source.activities(date(2000, 1, 1), date.today())
            if activity.type in RUN_TYPES
        }
        wellness = source.wellness(date(1999, 1, 1), date.today())
        baseline = resting_hr_baselines(wellness)
        runalyze = load_payloads(
            getattr(source, "connection", None), "runalyze", activities
        )
        intervals = load_payloads(
            getattr(source, "connection", None), "intervals", activities
        )
        laps_by_id = {
            activity_id: source.activity_laps(activity_id)
            for activity_id, activity in activities.items()
            if is_steady_run(activity)
        }
        work_by_id = {
            activity_id: source.activity_intervals(activity_id)
            for activity_id, activity in activities.items()
            if "intervals" in set(activity.workout_methods)
            or set(activity.workout_targets)
            & {"subthreshold", "threshold", "lt1", "vo2max"}
        }

    decoupling_rows = []
    for activity_id, activity in activities.items():
        if not is_steady_run(activity):
            continue
        payload = runalyze.get(activity_id, {})
        vendor = payload.get("aerobic_decoupling_pace")
        if not isinstance(vendor, (int, float)):
            continue
        rhr = baseline(activity.date)
        if rhr is None:
            continue
        lap_value = lap_decoupling(laps_by_id.get(activity_id, []), rhr)
        if lap_value is None:
            continue
        decoupling_rows.append(
            {
                "date": activity.date,
                "year": activity.date.year,
                "minutes": activity.duration_s / 60.0,
                "lap": lap_value,
                "vendor": float(vendor),
            }
        )

    print(
        f"{len(decoupling_rows)} steady runs with both lap and Runalyze "
        f"decoupling"
    )
    if decoupling_rows:
        xs = [row["lap"] for row in decoupling_rows]
        ys = [row["vendor"] for row in decoupling_rows]
        r = correlation(xs, ys)
        sign = 1.0 if r is None or r >= 0 else -1.0
        aligned = [sign * value for value in ys]
        differences = [
            value - row["lap"] for value, row in zip(aligned, decoupling_rows)
        ]
        print(
            f"  correlation {r:+.2f}; sign-aligned median vendor-lap "
            f"{median(differences):+.2f} percentage points"
        )
        table(
            [
                (
                    "lap halves",
                    len(decoupling_rows),
                    f"{median(xs):+.2f}%",
                    f"{median(ys):+.2f}%",
                    f"{median(differences):+.2f}",
                )
            ],
            headers=["method", "n", "median", "vendor median", "difference"],
        )

    print("\nRunalyze decoupling by year (all runs):")
    by_year = defaultdict(list)
    for activity_id, payload in runalyze.items():
        activity = activities.get(activity_id)
        value = payload.get("aerobic_decoupling_pace")
        if activity is not None and isinstance(value, (int, float)):
            by_year[activity.date.year].append(float(value))
    table(
        [
            (year, len(values), f"{median(values):+.2f}%")
            for year, values in sorted(by_year.items())
            if year >= 2022
        ],
        headers=["year", "n", "median"],
    )

    hrr_rows = []
    for activity_id, payload in intervals.items():
        activity = activities.get(activity_id)
        if activity is None:
            continue
        value = payload.get("icu_hrr")
        if isinstance(value, dict) and isinstance(value.get("hrr"), (int, float)):
            hrr_rows.append(
                {
                    "year": activity.date.year,
                    "group": group_of(activity),
                    "hrr": float(value["hrr"]),
                }
            )

    print("\nHR recovery by group:")
    by_group = defaultdict(list)
    for row in hrr_rows:
        by_group[row["group"]].append(row["hrr"])
    table(
        [
            (group, len(values), f"{median(values):.0f}")
            for group, values in sorted(by_group.items())
        ],
        headers=["group", "n", "median hrr (bpm)"],
    )

    print("\nHR recovery by year:")
    hrr_by_year = defaultdict(list)
    for row in hrr_rows:
        hrr_by_year[row["year"]].append(row["hrr"])
    table(
        [
            (year, len(values), f"{median(values):.0f}")
            for year, values in sorted(hrr_by_year.items())
            if year >= 2022
        ],
        headers=["year", "n", "median hrr (bpm)"],
    )

    fade_rows = []
    for activity_id, activity in activities.items():
        if not (
            "intervals" in set(activity.workout_methods)
            or set(activity.workout_targets)
            & {"subthreshold", "threshold", "lt1", "vo2max"}
        ):
            continue
        reps = [
            interval
            for interval in work_intervals(work_by_id.get(activity_id, []))
            if interval.duration_s >= 60 and interval.distance_m > 0
        ]
        if len(reps) < 3:
            continue
        first = reps[0]
        last = reps[-1]
        pace_first = first.duration_s / first.distance_m * 1000.0
        pace_last = last.duration_s / last.distance_m * 1000.0
        hr_first = first.avg_hr
        hr_last = last.avg_hr
        hrr = intervals.get(activity_id, {}).get("icu_hrr")
        hrr_value = (
            float(hrr["hrr"])
            if isinstance(hrr, dict) and isinstance(hrr.get("hrr"), (int, float))
            else None
        )
        fade_rows.append(
            {
                "group": group_of(activity),
                "year": activity.date.year,
                "pace_fade": pace_last - pace_first,
                "hr_fade": (
                    hr_last - hr_first
                    if hr_first is not None and hr_last is not None
                    else None
                ),
                "hrr": hrr_value,
            }
        )

    print("\nrep-to-rep fade (last minus first work rep):")
    by_fade_group = defaultdict(list)
    for row in fade_rows:
        by_fade_group[row["group"]].append(row)

    def hr_fade(chunk) -> str:
        values = [
            row["hr_fade"] for row in chunk if row["hr_fade"] is not None
        ]
        return f"{median(values):+.1f} bpm" if values else "-"

    table(
        [
            (
                group,
                len(chunk),
                f"{median(row['pace_fade'] for row in chunk):+.1f} s/km",
                hr_fade(chunk),
            )
            for group, chunk in sorted(by_fade_group.items())
        ],
        headers=["group", "n", "pace fade", "HR fade"],
    )

    paired = [
        (row["pace_fade"], row["hrr"])
        for row in fade_rows
        if row["hrr"] is not None
    ]
    if paired:
        print(
            f"  pace fade vs HR recovery: n={len(paired)}, "
            f"r {correlation([a for a, _ in paired], [b for _, b in paired]) or 0:+.2f}"
        )

    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "Lap vs Runalyze decoupling",
            "HR recovery by year",
        ),
    )
    if decoupling_rows:
        figure.add_trace(
            go.Scatter(
                x=[row["lap"] for row in decoupling_rows],
                y=[row["vendor"] for row in decoupling_rows],
                mode="markers",
                marker={"size": 6, "color": "#4c78a8", "opacity": 0.6},
                name="steady runs",
            ),
            row=1,
            col=1,
        )
        low = min(
            min(row["lap"] for row in decoupling_rows),
            min(row["vendor"] for row in decoupling_rows),
        )
        high = max(
            max(row["lap"] for row in decoupling_rows),
            max(row["vendor"] for row in decoupling_rows),
        )
        figure.add_trace(
            go.Scatter(
                x=[low, high],
                y=[low, high],
                mode="lines",
                line={"color": "#888888", "dash": "dash"},
                name="1:1",
            ),
            row=1,
            col=1,
        )
        figure.update_xaxes(title_text="lap decoupling (%)", row=1, col=1)
        figure.update_yaxes(title_text="Runalyze decoupling (%)", row=1, col=1)

    hrr_years = sorted(year for year in hrr_by_year if year >= 2022)
    figure.add_trace(
        go.Scatter(
            x=hrr_years,
            y=[median(hrr_by_year[year]) for year in hrr_years],
            mode="lines+markers",
            name="median hrr",
            line={"color": "#f58518"},
        ),
        row=1,
        col=2,
    )
    figure.update_yaxes(title_text="bpm", row=1, col=2)
    figure.update_layout(
        title="Durability and HR recovery",
        legend={"orientation": "h", "y": -0.15},
    )
    save(figure, "durability-recovery")

    print(
        "\nreading: a high lap-vendor correlation makes the vendor decoupling "
        "usable for runs without enough laps. A flat HR-recovery or fade trend "
        "means it is not adding a fitness signal; a structured one is a "
        "separate durability axis."
    )


if __name__ == "__main__":
    main()
