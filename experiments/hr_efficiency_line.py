"""Experiment: does one efficiency value reproduce the HR-vs-speed line?

The pace/HR chart fits ``HR = a + b·v`` by least squares. Efficiency is
defined as ``v·60 / (HR − RHR)``, so if it were constant every point would sit
on ``HR = RHR + v·60/E`` — a line through the resting baseline, with no free
intercept. This compares the two, and fits the offset-corrected form
``HR − RHR = a' + b'·v`` to see whether ``a'`` is really zero.

    uv run --env-file .env python experiments/hr_efficiency_line.py
"""

from datetime import date
from statistics import median

import plotly.graph_objects as go

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    aggregate_efficiency,
    m_per_excess_beat,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_DURATION_S = 20 * 60
MIN_DISTANCE_M = 3000


def fit(xs, ys):
    """Least-squares slope, intercept, R² and RMSE."""
    count = len(xs)
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum(
        (y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)
    )
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, intercept, r2, (ss_res / count) ** 0.5


def main() -> None:
    with create_source() as source:
        wellness = source.wellness(date(2000, 1, 1), date.today())
        baseline = resting_hr_baselines(wellness)
        activities = source.activities(date(2000, 1, 1), date.today())

    rows = []
    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue
        if not (activity.duration_s and activity.distance_m and activity.avg_hr):
            continue
        if activity.duration_s < MIN_DURATION_S:
            continue
        if activity.distance_m < MIN_DISTANCE_M:
            continue

        resting_hr = baseline(activity.date)
        if resting_hr is None:
            continue

        speed = activity.distance_m / activity.duration_s
        efficiency = m_per_excess_beat(
            activity.distance_m,
            activity.duration_s,
            activity.avg_hr,
            resting_hr,
        )
        if efficiency is None:
            continue

        rows.append(
            {
                "date": activity.date,
                "speed": speed,
                "hr": activity.avg_hr,
                "rhr": resting_hr,
                "eff": efficiency,
                "distance_m": activity.distance_m,
                "duration_s": activity.duration_s,
            }
        )

    if len(rows) < 20:
        print(f"only {len(rows)} usable runs; need at least 20")
        return

    speeds = [row["speed"] for row in rows]
    hrs = [row["hr"] for row in rows]
    rhrs = [row["rhr"] for row in rows]
    rhr_center = median(rhrs)

    # Model A: the current chart's regression.
    slope_a, intercept_a, r2_a, rmse_a = fit(speeds, hrs)

    # Model B: the offset-corrected fit; a' should be ~0 if RHR is the right
    # offset.
    slope_b, intercept_b, r2_b, rmse_b = fit(
        speeds,
        [hr - rhr for hr, rhr in zip(hrs, rhrs)],
    )

    # Model C: one efficiency value, no free intercept.
    efficiency = aggregate_efficiency(
        (
            row["distance_m"],
            row["duration_s"],
            row["hr"],
            row["rhr"],
        )
        for row in rows
    )
    slope_c = 60 / efficiency
    rmse_c = (
        sum(
            (row["hr"] - (row["rhr"] + row["speed"] * slope_c)) ** 2
            for row in rows
        )
        / len(rows)
    ) ** 0.5
    mean_hr = sum(hrs) / len(hrs)
    ss_tot = sum((hr - mean_hr) ** 2 for hr in hrs)
    ss_res_c = sum(
        (row["hr"] - (row["rhr"] + row["speed"] * slope_c)) ** 2
        for row in rows
    )
    r2_c = 1 - ss_res_c / ss_tot if ss_tot else 0.0

    print(
        f"{len(rows)} runs, {rows[0]['date']} .. {rows[-1]['date']}, "
        f"median RHR {rhr_center:.1f} bpm\n"
    )
    table(
        [
            (
                "A: HR = a + b·v",
                f"{intercept_a:.1f}",
                f"{slope_a:.2f}",
                f"{r2_a:.3f}",
                f"{rmse_a:.2f}",
            ),
            (
                "B: HR−RHR = a' + b'·v",
                f"{intercept_b:+.1f}",
                f"{slope_b:.2f}",
                f"{r2_b:.3f}",
                f"{rmse_b:.2f}",
            ),
            (
                "C: HR = RHR + v·60/E",
                f"{rhr_center:.1f}",
                f"{slope_c:.2f}",
                f"{r2_c:.3f}",
                f"{rmse_c:.2f}",
            ),
        ],
        headers=["model", "intercept", "slope", "R²", "RMSE (bpm)"],
    )

    print(
        f"\nEfficiency (weighted) = {efficiency:.3f} m/excess beat "
        f"-> {slope_c:.2f} bpm per m/s"
    )
    print(
        f"Regression-implied efficiency: A {60 / slope_a:.3f}, "
        f"B {60 / slope_b:.3f} m/excess beat"
    )

    mean_speed = sum(speeds) / len(speeds)
    mean_eff = sum(row["eff"] for row in rows) / len(rows)
    cov = sum(
        (row["speed"] - mean_speed) * (row["eff"] - mean_eff) for row in rows
    )
    var_speed = sum((speed - mean_speed) ** 2 for speed in speeds)
    var_eff = sum((row["eff"] - mean_eff) ** 2 for row in rows)
    correlation = cov / (var_speed * var_eff) ** 0.5 if var_eff else 0.0
    print(f"correlation(efficiency, speed) = {correlation:+.3f}")
    print(
        f"Regression intercept {intercept_a:.1f} vs median RHR "
        f"{rhr_center:.1f} bpm  (gap {intercept_a - rhr_center:+.1f})"
    )
    print(
        f"Offset-corrected intercept {intercept_b:+.1f} bpm "
        "(~0 means the baseline is the right offset)"
    )

    # Is efficiency constant across speed? Quartile medians.
    ordered = sorted(rows, key=lambda row: row["speed"])
    quarter = len(ordered) // 4
    print("\nefficiency by speed quartile:")
    table(
        [
            (
                f"Q{index + 1}",
                f"{median(r['speed'] for r in chunk):.2f}",
                f"{median(r['hr'] for r in chunk):.0f}",
                f"{median(r['eff'] for r in chunk):.3f}",
            )
            for index, chunk in enumerate(
                ordered[i * quarter : (i + 1) * quarter]
                for i in range(4)
            )
            if chunk
        ],
        headers=["band", "speed m/s", "HR", "efficiency"],
    )

    # Within the aerobic range (below the top quartile) the constant-
    # efficiency model should hold best.
    aerobic = [row for row in ordered if row["speed"] <= ordered[3 * quarter]["speed"]]
    aerobic_rmse_c = (
        sum(
            (row["hr"] - (row["rhr"] + row["speed"] * slope_c)) ** 2
            for row in aerobic
        )
        / len(aerobic)
    ) ** 0.5
    aerobic_rmse_a = (
        sum(
            (row["hr"] - (intercept_a + slope_a * row["speed"])) ** 2
            for row in aerobic
        )
        / len(aerobic)
    ) ** 0.5
    print(
        f"aerobic range only (n={len(aerobic)}): RMSE A {aerobic_rmse_a:.2f} "
        f"vs C {aerobic_rmse_c:.2f} bpm"
    )

    # Year by year: is the slope stable?
    by_year = {}
    for row in rows:
        by_year.setdefault(row["date"].year, []).append(row)

    print("\nby year:")
    table(
        [
            (
                year,
                len(chunk),
                f"{aggregate_efficiency((r['distance_m'], r['duration_s'], r['hr'], r['rhr']) for r in chunk):.3f}",
                f"{fit([r['speed'] for r in chunk], [r['hr'] for r in chunk])[0]:.2f}",
            )
            for year, chunk in sorted(by_year.items())
            if len(chunk) >= 20
        ],
        headers=["year", "runs", "efficiency", "regression slope"],
    )

    low = min(speeds)
    high = max(speeds)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=speeds,
            y=hrs,
            mode="markers",
            marker={"size": 4, "opacity": 0.35, "color": "#4c78a8"},
            name="runs",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[low, high],
            y=[intercept_a + slope_a * value for value in (low, high)],
            mode="lines",
            line={"color": "#e45756", "width": 2},
            name="regression (A)",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[low, high],
            y=[rhr_center + slope_c * value for value in (low, high)],
            mode="lines",
            line={"color": "#54a24b", "width": 2, "dash": "dash"},
            name="one efficiency (C)",
        )
    )
    figure.update_xaxes(title_text="speed (m/s)")
    figure.update_yaxes(title_text="average HR (bpm)")
    figure.update_layout(
        title=(
            f"HR vs speed: regression R² {r2_a:.3f} vs "
            f"efficiency R² {r2_c:.3f}"
        )
    )
    save(figure, "hr-efficiency-line")


if __name__ == "__main__":
    main()
