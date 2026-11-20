"""Experiment: does stored Runalyze GAP change the efficiency conclusions?

Question
--------
The efficiency metric uses raw pace, so hills and terrain remain a caveat. The
Runalyze payload stores a grade-adjusted pace (`gap`, km/h) for every linked
run. Does using that stored GAP flatten the terrain effect, and does it change
the duration or yearly efficiency trends? The same payload also stores an
elevation-corrected VO2max; do the Enduro Garmin drops look smaller there?

Data
----
Canonical steady runs in the 40-75 min band, Runalyze `gap`, `vo2max` and
`vo2max_with_elevation` payloads, resting-HR baselines, and the Enduro Garmin
VO2max series. No streams.

Outputs
-------
- Raw vs GAP efficiency overall and by terrain bucket.
- Raw vs GAP efficiency by duration and year.
- Enduro drop runs with Garmin, Runalyze and Runalyze-with-elevation deltas.
- A two-panel plot: terrain buckets and yearly trend.

Decision
--------
If GAP flattens the terrain buckets without changing the yearly trend, it is a
useful terrain covariate. If it changes the duration effect too, the earlier
duration caveat was partly terrain. If it changes nothing, raw pace is enough.

    uv run --env-file .env python experiments/gap_efficiency.py
"""

from __future__ import annotations

import json
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

DROP = 1.0
DEVICE_PRODUCT = "enduro"
TERRAIN_BUCKETS = (
    ("flat <5", lambda gain: gain is not None and gain < 5),
    ("rolling 5-15", lambda gain: gain is not None and 5 <= gain < 15),
    ("hilly 15+", lambda gain: gain is not None and gain >= 15),
    ("unknown", lambda gain: gain is None),
)
DURATION_BUCKETS = (
    ("40-50", 40, 50),
    ("50-60", 50, 60),
    ("60-75", 60, 75),
)


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


def terrain_bucket(gain: float | None) -> str:
    for label, predicate in TERRAIN_BUCKETS:
        if predicate(gain):
            return label
    return "unknown"


def duration_bucket(minutes: float) -> str:
    for label, low, high in DURATION_BUCKETS:
        if low <= minutes < high:
            return label
    return DURATION_BUCKETS[-1][0]


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
        devices = {
            device.id: device.product or device.name or device.id
            for device in source.devices()
        }

    rows = []
    skipped = 0
    for activity_id, activity in activities.items():
        if not is_steady_run(activity):
            continue
        payload = payloads.get(activity_id)
        if not payload:
            continue
        gap = payload.get("gap")
        if not isinstance(gap, (int, float)) or not 3 <= gap <= 30:
            skipped += 1
            continue
        rhr = baseline(activity.date)
        if rhr is None:
            skipped += 1
            continue
        raw = activity_efficiency(activity, rhr)
        adjusted = gap_efficiency(activity, float(gap), rhr)
        if raw is None or adjusted is None:
            skipped += 1
            continue
        km = activity.distance_m / 1000.0
        gain = activity.elevation_gain_m
        gain_per_km = gain / km if gain is not None and km else None
        rows.append(
            {
                "date": activity.date,
                "name": activity.name,
                "minutes": activity.duration_s / 60.0,
                "gain_per_km": gain_per_km,
                "terrain": terrain_bucket(gain_per_km),
                "duration": duration_bucket(activity.duration_s / 60.0),
                "year": activity.date.isoformat()[:4],
                "raw": raw,
                "adjusted": adjusted,
                "ratio": adjusted / raw if raw else None,
            }
        )

    print(
        f"{len(rows)} steady 40-75 runs with stored GAP; {skipped} skipped "
        f"(missing GAP, RHR, or value)"
    )
    if not rows:
        return

    print("\nraw vs GAP efficiency:")
    table(
        [
            (
                "all",
                len(rows),
                f"{mean(row['raw'] for row in rows):.3f}",
                f"{mean(row['adjusted'] for row in rows):.3f}",
                f"{median(row['ratio'] for row in rows):.3f}",
            )
        ],
        headers=["group", "n", "raw", "GAP", "GAP/raw"],
    )

    print("\nby terrain (m/km):")
    table(
        [
            (
                label,
                len(chunk),
                f"{mean(row['raw'] for row in chunk):.3f}",
                f"{mean(row['adjusted'] for row in chunk):.3f}",
                f"{median(row['ratio'] for row in chunk):.3f}",
            )
            for label, _ in TERRAIN_BUCKETS
            for chunk in [
                [row for row in rows if row["terrain"] == label]
            ]
            if chunk
        ],
        headers=["terrain", "n", "raw", "GAP", "GAP/raw"],
    )

    print("\nby duration (min):")
    table(
        [
            (
                label,
                len(chunk),
                f"{mean(row['raw'] for row in chunk):.3f}",
                f"{mean(row['adjusted'] for row in chunk):.3f}",
                f"{median(row['ratio'] for row in chunk):.3f}",
            )
            for label, _, _ in DURATION_BUCKETS
            for chunk in [
                [row for row in rows if row["duration"] == label]
            ]
            if chunk
        ],
        headers=["duration", "n", "raw", "GAP", "GAP/raw"],
    )

    print("\nby year (mean):")
    table(
        [
            (
                year,
                len(chunk),
                f"{mean(row['raw'] for row in chunk):.3f}",
                f"{mean(row['adjusted'] for row in chunk):.3f}",
                f"{median(row['ratio'] for row in chunk):.3f}",
            )
            for year in sorted({row["year"] for row in rows})
            if year >= "2022"
            for chunk in [[row for row in rows if row["year"] == year]]
        ],
        headers=["year", "n", "raw", "GAP", "GAP/raw"],
    )

    # Enduro Garmin drops and the vendor corrected values.
    enduro = sorted(
        [
            activity
            for activity in activities.values()
            if devices.get(activity.device_id) == DEVICE_PRODUCT
            and activity.vo2max_garmin is not None
            and activity.vo2max_garmin > 0
        ],
        key=lambda activity: (
            activity.started_at_utc or activity.date.isoformat(),
            activity.id,
        ),
    )
    drops = []
    for previous, current in zip(enduro, enduro[1:]):
        delta = current.vo2max_garmin - previous.vo2max_garmin
        if delta > -DROP:
            continue
        payload = payloads.get(current.id, {})
        previous_payload = payloads.get(previous.id, {})
        km = current.distance_m / 1000.0
        gain = current.elevation_gain_m
        gain_per_km = gain / km if gain is not None and km else None
        vendor = payload.get("vo2max")
        vendor_elev = payload.get("vo2max_with_elevation")
        previous_vendor = previous_payload.get("vo2max")
        previous_vendor_elev = previous_payload.get("vo2max_with_elevation")
        drops.append(
            (
                current.date.isoformat(),
                (current.name or "")[:24],
                f"{previous.vo2max_garmin:.1f}",
                f"{current.vo2max_garmin:.1f}",
                f"{delta:+.1f}",
                f"{vendor:.1f}" if isinstance(vendor, (int, float)) else "-",
                f"{vendor_elev:.1f}"
                if isinstance(vendor_elev, (int, float))
                else "-",
                f"{vendor - previous_vendor:+.1f}"
                if isinstance(vendor, (int, float))
                and isinstance(previous_vendor, (int, float))
                else "-",
                f"{vendor_elev - previous_vendor_elev:+.1f}"
                if isinstance(vendor_elev, (int, float))
                and isinstance(previous_vendor_elev, (int, float))
                else "-",
                f"{gain_per_km:.0f}" if gain_per_km is not None else "-",
            )
        )

    print("\nEnduro Garmin drops vs Runalyze values:")
    table(
        drops,
        headers=[
            "date",
            "name",
            "Garmin prev",
            "Garmin",
            "Garmin Δ",
            "Runalyze",
            "Runalyze+el",
            "Runalyze Δ",
            "Elev Δ",
            "gain/km",
        ],
    )

    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "Efficiency by terrain (raw vs GAP)",
            "Yearly efficiency (raw vs GAP)",
        ),
        specs=[[{"type": "xy"}, {"type": "xy"}]],
    )
    terrain_labels = [
        label
        for label, _ in TERRAIN_BUCKETS
        if any(row["terrain"] == label for row in rows)
    ]
    terrain_raw = [
        mean(row["raw"] for row in rows if row["terrain"] == label)
        for label in terrain_labels
    ]
    terrain_adjusted = [
        mean(row["adjusted"] for row in rows if row["terrain"] == label)
        for label in terrain_labels
    ]
    figure.add_trace(
        go.Scatter(
            x=terrain_labels,
            y=terrain_raw,
            mode="lines+markers",
            name="raw pace",
            legendgroup="raw",
            line={"color": "#4c78a8"},
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=terrain_labels,
            y=terrain_adjusted,
            mode="lines+markers",
            name="stored GAP",
            legendgroup="gap",
            line={"color": "#f58518"},
        ),
        row=1,
        col=1,
    )
    years = sorted({row["year"] for row in rows if row["year"] >= "2022"})
    figure.add_trace(
        go.Scatter(
            x=years,
            y=[
                mean(row["raw"] for row in rows if row["year"] == year)
                for year in years
            ],
            mode="lines+markers",
            name="raw pace",
            legendgroup="raw",
            showlegend=False,
            line={"color": "#4c78a8"},
        ),
        row=1,
        col=2,
    )
    figure.add_trace(
        go.Scatter(
            x=years,
            y=[
                mean(row["adjusted"] for row in rows if row["year"] == year)
                for year in years
            ],
            mode="lines+markers",
            name="stored GAP",
            legendgroup="gap",
            showlegend=False,
            line={"color": "#f58518"},
        ),
        row=1,
        col=2,
    )
    figure.update_yaxes(
        title_text="m/excess beat", range=[2.25, 2.55], row=1, col=1
    )
    figure.update_yaxes(
        title_text="m/excess beat", range=[2.35, 2.56], row=1, col=2
    )
    figure.update_layout(
        title="Efficiency: raw pace vs stored Runalyze GAP",
        legend={"orientation": "h", "y": -0.15},
    )
    save(figure, "gap-efficiency")

    print(
        "\nreading: if the GAP line is flatter across terrain, stored GAP "
        "removes a terrain confound; if the yearly lines stay parallel, it "
        "does not change the fitness trend."
    )


if __name__ == "__main__":
    main()
