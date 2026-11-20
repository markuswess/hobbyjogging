"""Experiment: is the fitness trend explained by a changing training mix?

Question
--------
The pooled VO2max/efficiency series mixes easy runs, recovery runs, long runs,
threshold work, VO2max intervals and races. If the mix shifts (for example a
Canova-style block where the 45-minute easy runs become recovery runs), the
pooled number can move without a fitness change. Did the mix change, and does
standardising it remove the trend?

Data
----
Canonical run activities and methods/targets, Intervals payloads
(`AerobicEffect`, `AnaerobicEffect`, `icu_training_load`, `icu_intensity`),
resting-HR baselines and the HR/economy VO2max estimate. No streams.

Outputs
-------
- Yearly structure shares.
- Group means of the vendor effects and load/intensity.
- Pooled vs fixed-mix-standardised VO2max trend.
- Pooled vs easy-only efficiency trend.
- A two-panel plot: shares and the two adjusted trends.

Decision
--------
If the standardised VO2max trend is close to the pooled trend, mix is not
driving it. If not, the pooled series needs structure segmentation. The
easy-only efficiency trend is the independent check.

    uv run --env-file .env python experiments/structure_mix.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from statistics import mean

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    activity_efficiency,
    is_steady_run,
    resting_hr_baselines,
)
from hobbyjogging_report.analysis.vo2max import (
    effective_vo2max,
    threshold_max_hr,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

GROUPS = (
    "easy/base",
    "recovery",
    "long",
    "subT/threshold",
    "VO2max/intervals",
    "fartlek/progression",
    "race",
)
GROUP_COLORS = {
    "easy/base": "#4c78a8",
    "recovery": "#9ecae9",
    "long": "#54a24b",
    "subT/threshold": "#f58518",
    "VO2max/intervals": "#e45756",
    "fartlek/progression": "#b279a2",
    "race": "#000000",
}


def load_intervals(connection, activities: dict) -> dict[str, dict]:
    rows = connection.execute(
        """
        SELECT sr.payload_json, asrc.activity_id
        FROM source_records sr
        JOIN activity_sources asrc ON asrc.source_record_id = sr.id
        WHERE sr.source = 'intervals' AND sr.record_type = 'activity'
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


def yearly_means(rows: list[dict], key: str) -> dict[int, float]:
    grouped = defaultdict(list)
    for row in rows:
        if row.get(key) is not None:
            grouped[row["year"]].append(row[key])
    return {year: mean(values) for year, values in grouped.items()}


def main() -> None:
    with create_source() as source:
        activities = {
            activity.id: activity
            for activity in source.activities(date(2000, 1, 1), date.today())
            if activity.type in RUN_TYPES
        }
        wellness = source.wellness(date(1999, 1, 1), date.today())
        baseline = resting_hr_baselines(wellness)
        thresholds = source.athlete_thresholds()
        payloads = load_intervals(
            getattr(source, "connection", None), activities
        )

    rows = []
    for activity_id, activity in activities.items():
        if activity.date.year < 2019:
            continue
        year = activity.date.year
        group = group_of(activity)
        payload = payloads.get(activity_id, {})

        vo2 = effective_vo2max(
            activity, threshold_max_hr(thresholds, activity.date)
        )
        rhr = baseline(activity.date)
        efficiency = (
            activity_efficiency(activity, rhr)
            if is_steady_run(activity) and rhr is not None
            else None
        )

        rows.append(
            {
                "date": activity.date,
                "year": year,
                "group": group,
                "vo2": vo2,
                "efficiency": efficiency,
                "aerobic": payload.get("AerobicEffect"),
                "anaerobic": payload.get("AnaerobicEffect"),
                "load": payload.get("icu_training_load"),
                "intensity": payload.get("icu_intensity"),
            }
        )

    totals = defaultdict(int)
    group_counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        totals[row["year"]] += 1
        group_counts[row["year"]][row["group"]] += 1

    years = sorted(year for year in totals if year >= 2022)
    print(f"{len(rows)} runs, {len(payloads)} Intervals payloads")

    print("\nstructure share by year:")
    table(
        [
            (
                year,
                totals[year],
                *[
                    f"{100 * group_counts[year][group] / totals[year]:.0f}%"
                    for group in GROUPS
                ],
            )
            for year in years
        ],
        headers=["year", "runs", *GROUPS],
    )

    print("\ngroup effects (mean):")
    group_rows = []
    for group in GROUPS:
        chunk = [row for row in rows if row["group"] == group]
        if not chunk:
            continue

        def mean_of(key):
            values = [
                row[key]
                for row in chunk
                if isinstance(row[key], (int, float))
            ]
            return f"{mean(values):.2f}" if values else "-"

        group_rows.append(
            (
                group,
                len(chunk),
                mean_of("aerobic"),
                mean_of("anaerobic"),
                mean_of("load"),
                mean_of("intensity"),
            )
        )
    table(
        group_rows,
        headers=["group", "n", "AerobicEffect", "AnaerobicEffect", "load", "intensity"],
    )

    overall_share = {
        group: sum(
            row["group"] == group for row in rows
        ) / len(rows)
        for group in GROUPS
    }
    overall_vo2 = {}
    for group in GROUPS:
        values = [
            row["vo2"]
            for row in rows
            if row["group"] == group and row["vo2"] is not None
        ]
        if values:
            overall_vo2[group] = mean(values)

    year_group_vo2: dict[int, dict[str, float]] = defaultdict(dict)
    for year in years:
        for group in GROUPS:
            values = [
                row["vo2"]
                for row in rows
                if row["year"] == year
                and row["group"] == group
                and row["vo2"] is not None
            ]
            if values:
                year_group_vo2[year][group] = mean(values)

    pooled_vo2 = yearly_means(
        [row for row in rows if row["vo2"] is not None], "vo2"
    )
    standardised_vo2 = {}
    for year in years:
        total = 0.0
        weight = 0.0
        for group in GROUPS:
            share = overall_share[group]
            value = year_group_vo2[year].get(group, overall_vo2.get(group))
            if value is None:
                continue
            total += share * value
            weight += share
        if weight:
            standardised_vo2[year] = total / weight

    print("\nVO2max trend, pooled vs fixed-mix standardised:")
    table(
        [
            (
                year,
                f"{pooled_vo2[year]:.2f}" if year in pooled_vo2 else "-",
                f"{standardised_vo2[year]:.2f}"
                if year in standardised_vo2
                else "-",
                f"{standardised_vo2[year] - pooled_vo2[year]:+.2f}"
                if year in pooled_vo2 and year in standardised_vo2
                else "-",
            )
            for year in years
        ],
        headers=["year", "pooled", "standardised", "difference"],
    )

    steady = [row for row in rows if row["efficiency"] is not None]
    pooled_eff = yearly_means(steady, "efficiency")
    easy_eff = yearly_means(
        [row for row in steady if row["group"] == "easy/base"],
        "efficiency",
    )
    print("\nefficiency trend, pooled vs easy/base only:")
    table(
        [
            (
                year,
                f"{pooled_eff[year]:.3f}" if year in pooled_eff else "-",
                f"{easy_eff[year]:.3f}" if year in easy_eff else "-",
                f"{easy_eff[year] - pooled_eff[year]:+.3f}"
                if year in pooled_eff and year in easy_eff
                else "-",
            )
            for year in years
        ],
        headers=["year", "pooled", "easy/base", "difference"],
    )

    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "Structure share by year",
            "VO2max: pooled vs fixed mix",
        ),
    )
    for group in GROUPS:
        figure.add_trace(
            go.Bar(
                x=years,
                y=[
                    100 * group_counts[year][group] / totals[year]
                    for year in years
                ],
                name=group,
                marker_color=GROUP_COLORS[group],
            ),
            row=1,
            col=1,
        )
    figure.update_layout(barmode="stack")
    figure.update_yaxes(title_text="share of runs (%)", row=1, col=1)
    figure.add_trace(
        go.Scatter(
            x=years,
            y=[pooled_vo2.get(year) for year in years],
            mode="lines+markers",
            name="pooled",
            line={"color": "#4c78a8"},
        ),
        row=1,
        col=2,
    )
    figure.add_trace(
        go.Scatter(
            x=years,
            y=[standardised_vo2.get(year) for year in years],
            mode="lines+markers",
            name="fixed mix",
            line={"color": "#f58518", "dash": "dash"},
        ),
        row=1,
        col=2,
    )
    figure.update_yaxes(title_text="VO2max estimate", row=1, col=2)
    figure.update_layout(
        title="Training mix and the pooled VO2max trend",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "structure-mix")

    print(
        "\nreading: if the fixed-mix line is close to the pooled line, the "
        "fitness trend is not a composition artefact. A large gap means the "
        "pooled trend needs structure segmentation. The easy/base efficiency "
        "trend is the independent check."
    )


if __name__ == "__main__":
    main()
