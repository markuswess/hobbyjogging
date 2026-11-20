"""Experiment: does the efficiency trend survive route adjustment?

Question
--------
The pooled efficiency trend mixes routes. Does the yearly trend survive after
removing each pseudo-route's level, or is it driven by a changing route mix?
Runalyze's `recurring_route.id` is too fragmented to use directly, so a route
fingerprint is built from the rounded start coordinate, the route distance and
the circuit flag.

Data
----
Canonical steady runs in the 40-75 min band, Runalyze `recurring_route` and
`gap` payloads, and resting-HR baselines. No streams.

Outputs
-------
- Pseudo-route groups with enough steady runs.
- Pooled vs route-adjusted yearly efficiency, raw and GAP.
- Route share of variance and the pooled/adjusted slopes.
- A two-panel plot: raw and GAP, pooled vs adjusted.

Decision
--------
If the adjusted trend is close to the pooled trend, route mix is not driving
the fitness signal. If it differs materially, the pooled trend needs route or
terrain segmentation.

    uv run --env-file .env python experiments/route_efficiency.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from statistics import mean, median

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    activity_efficiency,
    is_steady_run,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_ROUTE_RUNS = 20
START_DECIMALS = 2
DISTANCE_STEP_KM = 1.0


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


def gap_efficiency(activity, gap_kmh: float, resting_hr: float) -> float | None:
    if not activity.duration_s or activity.avg_hr is None:
        return None
    excess = activity.avg_hr - resting_hr
    if excess < 10:
        return None
    speed_m_min = gap_kmh * 1000.0 / 60.0
    return speed_m_min / excess


def fingerprint(route: dict) -> tuple | None:
    lat = route.get("start_latitude")
    lon = route.get("start_longitude")
    distance = route.get("distance")
    if lat is None or lon is None or distance is None:
        return None
    return (
        round(float(lat), START_DECIMALS),
        round(float(lon), START_DECIMALS),
        round(float(distance) / DISTANCE_STEP_KM) * DISTANCE_STEP_KM,
        bool(route.get("is_circuit")),
    )


def slope(years: list[int], values: list[float]) -> float | None:
    if len(years) < 2:
        return None
    mx = mean(years)
    my = mean(values)
    sxx = sum((year - mx) ** 2 for year in years)
    sxy = sum((year - mx) * (value - my) for year, value in zip(years, values))
    return sxy / sxx if sxx else None


def yearly_means(rows: list[dict], key: str) -> dict[int, float]:
    grouped = defaultdict(list)
    for row in rows:
        if row.get(key) is not None:
            grouped[int(row["date"].isoformat()[:4])].append(row[key])
    return {year: mean(values) for year, values in grouped.items()}


def route_adjusted(rows: list[dict], key: str) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        if row.get(key) is not None:
            grouped[row["route"]].append(row[key])

    route_means = {
        route: mean(values) for route, values in grouped.items()
    }
    global_mean = mean(
        row[key] for row in rows if row.get(key) is not None
    )

    adjusted = []
    for row in rows:
        if row.get(key) is None:
            continue
        adjusted.append(
            {
                "date": row["date"],
                "route": row["route"],
                key: global_mean + row[key] - route_means[row["route"]],
            }
        )
    return adjusted


def main() -> None:
    with create_source() as source:
        activities = {
            activity.id: activity
            for activity in source.activities(date(2000, 1, 1), date.today())
            if activity.type in RUN_TYPES
        }
        wellness = source.wellness(date(1999, 1, 1), date.today())
        baseline = resting_hr_baselines(wellness)
        payloads = load_runalyze(
            getattr(source, "connection", None), activities
        )

    rows = []
    for activity_id, activity in activities.items():
        if not is_steady_run(activity):
            continue
        payload = payloads.get(activity_id)
        if not payload:
            continue
        route = payload.get("recurring_route")
        if not isinstance(route, dict):
            continue
        route_key = fingerprint(route)
        if route_key is None:
            continue
        rhr = baseline(activity.date)
        if rhr is None:
            continue
        raw = activity_efficiency(activity, rhr)
        if raw is None:
            continue

        gap = payload.get("gap")
        adjusted = (
            gap_efficiency(activity, float(gap), rhr)
            if isinstance(gap, (int, float)) and 3 <= gap <= 30
            else None
        )
        rows.append(
            {
                "date": activity.date,
                "route": route_key,
                "raw": raw,
                "gap": adjusted,
            }
        )

    counts = defaultdict(int)
    for row in rows:
        counts[row["route"]] += 1
    rows = [
        row for row in rows if counts[row["route"]] >= MIN_ROUTE_RUNS
    ]

    print(
        f"{len(rows)} steady runs in {len({row['route'] for row in rows})} "
        f"pseudo-routes with >= {MIN_ROUTE_RUNS} runs"
    )
    if len(rows) < 50:
        print("not enough route groups")
        return

    route_rows = []
    for route in sorted(
        {row["route"] for row in rows},
        key=lambda key: -counts[key],
    ):
        chunk = [row for row in rows if row["route"] == route]
        raw_years = yearly_means(chunk, "raw")
        gap_years = yearly_means(chunk, "gap")
        route_rows.append(
            (
                f"{route[0]:.2f},{route[1]:.2f} {route[2]:.0f}km",
                len(chunk),
                f"{min(row['date'] for row in chunk).year}–"
                f"{max(row['date'] for row in chunk).year}",
                f"{mean(row['raw'] for row in chunk):.3f}",
                f"{mean(row['gap'] for row in chunk if row['gap']):.3f}"
                if any(row["gap"] for row in chunk)
                else "-",
                f"{slope(list(raw_years), list(raw_years.values())):+.4f}"
                if len(raw_years) >= 2
                else "-",
                f"{slope(list(gap_years), list(gap_years.values())):+.4f}"
                if len(gap_years) >= 2
                else "-",
            )
        )

    print("\npseudo-route groups:")
    table(route_rows, headers=[
        "route", "n", "years", "raw", "GAP", "raw slope", "GAP slope",
    ])

    total_variance = mean(
        (row["raw"] - mean(r["raw"] for r in rows)) ** 2 for row in rows
    )
    route_means = {
        route: mean(r["raw"] for r in rows if r["route"] == route)
        for route in {row["route"] for row in rows}
    }
    within_variance = mean(
        (row["raw"] - route_means[row["route"]]) ** 2 for row in rows
    )
    route_share = 1 - within_variance / total_variance if total_variance else 0

    pooled_raw = yearly_means(rows, "raw")
    pooled_gap = yearly_means(rows, "gap")
    adjusted_raw = yearly_means(route_adjusted(rows, "raw"), "raw")
    adjusted_gap = yearly_means(route_adjusted(rows, "gap"), "gap")

    years = sorted(
        year
        for year in set(pooled_raw) | set(pooled_gap) | set(adjusted_raw)
        if year >= 2022
    )
    print("\nyearly efficiency, pooled vs route-adjusted:")
    table(
        [
            (
                year,
                f"{pooled_raw.get(year, float('nan')):.3f}"
                if year in pooled_raw
                else "-",
                f"{adjusted_raw.get(year, float('nan')):.3f}"
                if year in adjusted_raw
                else "-",
                f"{pooled_gap.get(year, float('nan')):.3f}"
                if year in pooled_gap
                else "-",
                f"{adjusted_gap.get(year, float('nan')):.3f}"
                if year in adjusted_gap
                else "-",
            )
            for year in years
        ],
        headers=["year", "raw pooled", "raw adjusted", "GAP pooled", "GAP adjusted"],
    )

    def trend(values: dict[int, float]) -> str:
        keys = [year for year in years if year in values]
        if len(keys) < 2:
            return "-"
        value = slope(keys, [values[year] for year in keys])
        return f"{value:+.4f}" if value is not None else "-"

    print(
        f"\nroute share of raw efficiency variance: {route_share:.1%}; "
        f"slopes raw pooled {trend(pooled_raw)} / adjusted "
        f"{trend(adjusted_raw)}; GAP pooled {trend(pooled_gap)} / adjusted "
        f"{trend(adjusted_gap)} per year"
    )

    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Raw efficiency", "Stored GAP efficiency"),
    )
    for column, key, pooled, adjusted in (
        (1, "raw", pooled_raw, adjusted_raw),
        (2, "gap", pooled_gap, adjusted_gap),
    ):
        figure.add_trace(
            go.Scatter(
                x=years,
                y=[pooled.get(year) for year in years],
                mode="lines+markers",
                name="pooled",
                legendgroup="pooled",
                showlegend=column == 1,
                line={"color": "#4c78a8"},
            ),
            row=1,
            col=column,
        )
        figure.add_trace(
            go.Scatter(
                x=years,
                y=[adjusted.get(year) for year in years],
                mode="lines+markers",
                name="route-adjusted",
                legendgroup="adjusted",
                showlegend=column == 1,
                line={"color": "#f58518", "dash": "dash"},
            ),
            row=1,
            col=column,
        )
        figure.update_yaxes(title_text="m/excess beat", row=1, col=column)

    figure.update_layout(
        title="Efficiency trend: pooled vs route-adjusted",
        legend={"orientation": "h", "y": -0.15},
    )
    save(figure, "route-efficiency")

    print(
        "\nreading: if the adjusted lines are close to the pooled lines, route "
        "mix is not driving the trend. A large gap means the pooled trend "
        "needs route or terrain segmentation."
    )


if __name__ == "__main__":
    main()
