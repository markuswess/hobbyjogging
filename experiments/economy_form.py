"""Experiment: is the efficiency/VO2max ratio an economy signal?

Question
--------
Efficiency and the HR/economy VO2max estimate share the same speed and HR data.
Does their ratio carry independent running-economy information, or is it just a
pace/RHR artefact? The Runalyze payload stores cadence, stride length, ground
contact and vertical oscillation; Intervals stores weight.

Data
----
Canonical steady runs in the 40-75 min band, Runalyze running-dynamics payloads,
Intervals weight, resting-HR baselines and the HR/economy VO2max estimate. No
streams.

Outputs
-------
- Correlation of the E/VO2 ratio with pace, HR, weight and form metrics.
- Speed-partial correlations, so a pace artefact is visible.
- The ratio by speed quartile.
- A bar chart of full and speed-partial correlations.

Decision
--------
If form metrics remain correlated with the ratio after controlling for pace,
the ratio is a usable economy proxy. If only pace matters, it is not.

    uv run --env-file .env python experiments/economy_form.py
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from statistics import mean

import plotly.graph_objects as go

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

FORM_FIELDS = (
    ("cadence", "cadence"),
    ("stride_length", "stride length"),
    ("groundcontact", "ground contact"),
    ("vertical_oscillation", "vertical oscillation"),
    ("efficiency_index", "Runalyze efficiency"),
    ("running_effectiveness", "running effectiveness"),
)


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


def residualise(values: list[float], control: list[float]) -> list[float]:
    mx = mean(control)
    my = mean(values)
    variance = sum((x - mx) ** 2 for x in control)
    if not variance:
        return [value - my for value in values]
    slope = (
        sum((x - mx) * (y - my) for x, y in zip(control, values))
        / variance
    )
    intercept = my - slope * mx
    return [
        value - (intercept + slope * x)
        for value, x in zip(values, control)
    ]


def partial_correlation(
    xs: list[float],
    ys: list[float],
    control: list[float],
) -> float | None:
    return correlation(residualise(xs, control), residualise(ys, control))


def nearest_weight(day: date, wellness: dict[date, object]) -> float | None:
    for offset in range(0, 8):
        for sign in (1, -1) if offset else (1,):
            moment = wellness.get(day + timedelta(days=sign * offset))
            if moment is not None and moment.weight_kg is not None:
                return moment.weight_kg
    return None


def main() -> None:
    with create_source() as source:
        activities = {
            activity.id: activity
            for activity in source.activities(date(2000, 1, 1), date.today())
            if activity.type in RUN_TYPES
        }
        wellness = {
            day.date: day
            for day in source.wellness(date(1999, 1, 1), date.today())
        }
        baseline = resting_hr_baselines(list(wellness.values()))
        thresholds = source.athlete_thresholds()
        runalyze = load_payloads(
            getattr(source, "connection", None), "runalyze", activities
        )
        intervals = load_payloads(
            getattr(source, "connection", None), "intervals", activities
        )

    rows = []
    for activity_id, activity in activities.items():
        if not is_steady_run(activity):
            continue
        payload = runalyze.get(activity_id, {})
        rhr = baseline(activity.date)
        if rhr is None:
            continue
        efficiency = activity_efficiency(activity, rhr)
        vo2 = effective_vo2max(
            activity, threshold_max_hr(thresholds, activity.date)
        )
        if efficiency is None or vo2 is None:
            continue

        weight = intervals.get(activity_id, {}).get("icu_weight")
        if not isinstance(weight, (int, float)):
            weight = nearest_weight(activity.date, wellness)

        rows.append(
            {
                "date": activity.date,
                "efficiency": efficiency,
                "vo2": vo2,
                "ratio": efficiency / vo2,
                "speed": activity.distance_m / activity.duration_s,
                "hr": activity.avg_hr,
                "weight": weight if isinstance(weight, (int, float)) else None,
                **{
                    field: payload.get(field)
                    for field, _ in FORM_FIELDS
                },
            }
        )

    print(f"{len(rows)} steady 40-75 runs with efficiency and VO2max")
    if len(rows) < 50:
        print("not enough rows")
        return

    ratio_values = [row["ratio"] for row in rows]
    speeds = [row["speed"] for row in rows]

    def pair(field: str):
        pairs = [
            (row["ratio"], float(row[field]))
            for row in rows
            if isinstance(row.get(field), (int, float))
        ]
        return pairs

    def aligned(field: str):
        return [
            (row["ratio"], float(row[field]), row["speed"])
            for row in rows
            if isinstance(row.get(field), (int, float))
        ]

    print("\nratio correlations (full and speed-partial):")
    correlation_rows = []
    for label, field in (
        ("pace (m/s)", "speed"),
        ("HR", "hr"),
        ("weight", "weight"),
        *[(label, field) for field, label in FORM_FIELDS],
    ):
        triples = aligned(field)
        if not triples:
            correlation_rows.append((label, 0, "-", "-"))
            continue
        xs = [item[0] for item in triples]
        ys = [item[1] for item in triples]
        full = correlation(xs, ys)
        partial = (
            None
            if field == "speed"
            else partial_correlation(
                xs, ys, [item[2] for item in triples]
            )
        )
        correlation_rows.append(
            (
                label,
                len(triples),
                f"{full:+.2f}" if full is not None else "-",
                f"{partial:+.2f}" if partial is not None else "-",
            )
        )
    table(
        correlation_rows,
        headers=["variable", "n", "r", "speed-partial r"],
    )

    def mean_field(chunk, field: str) -> str:
        values = [
            float(row[field])
            for row in chunk
            if isinstance(row.get(field), (int, float))
        ]
        return f"{mean(values):.1f}" if values else "-"

    print("\nratio and form by speed quartile:")
    ordered = sorted(rows, key=lambda row: row["speed"])
    quartile = max(1, len(ordered) // 4)
    table(
        [
            (
                f"Q{index + 1}",
                len(chunk),
                f"{mean(row['speed'] for row in chunk):.3f}",
                f"{mean(row['ratio'] for row in chunk):.4f}",
                mean_field(chunk, "cadence"),
                mean_field(chunk, "stride_length"),
                mean_field(chunk, "groundcontact"),
                mean_field(chunk, "vertical_oscillation"),
            )
            for index, chunk in enumerate(
                [
                    ordered[0:quartile],
                    ordered[quartile:2 * quartile],
                    ordered[2 * quartile:3 * quartile],
                    ordered[3 * quartile:],
                ]
            )
        ],
        headers=["quartile", "n", "speed", "ratio", "cadence", "stride", "GCT", "VO"],
    )

    form_pairs = []
    for field, label in FORM_FIELDS:
        pairs = pair(field)
        if len(pairs) < 10:
            continue
        xs = [a for a, _ in pairs]
        ys = [b for _, b in pairs]
        controls = [
            row["speed"]
            for row in rows
            if isinstance(row.get(field), (int, float))
        ]
        form_pairs.append(
            (
                label,
                correlation(xs, ys),
                partial_correlation(xs, ys, controls),
            )
        )

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=[label for label, _, _ in form_pairs],
            y=[r if r is not None else 0 for _, r, _ in form_pairs],
            name="full r",
            marker_color="#4c78a8",
        )
    )
    figure.add_trace(
        go.Bar(
            x=[label for label, _, _ in form_pairs],
            y=[r if r is not None else 0 for _, _, r in form_pairs],
            name="speed-partial r",
            marker_color="#f58518",
        )
    )
    figure.update_yaxes(title_text="correlation with E/VO2 ratio", range=[-1, 1])
    figure.update_layout(
        title="Is the E/VO2 ratio an economy signal?",
        barmode="group",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "economy-form")

    print(
        "\nreading: if the speed-partial bars stay away from zero, form metrics "
        "add information beyond pace; if they collapse, the ratio is mostly a "
        "pace/RHR artefact."
    )


if __name__ == "__main__":
    main()
