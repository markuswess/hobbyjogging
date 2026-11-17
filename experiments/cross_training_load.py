"""Experiment: how much should cross-training load count toward running fitness?

Question
--------
`daily_training_load()` sums every sport, so the running fitness/fatigue
EWMAs include cycling and other cross-training. Cycling load is not a running
load unit. Does total load track running performance better than running-only
load, and is there an estimable transfer factor for cross load?

Data
----
Daily training load split into running and cross-training. Running performance
is steady-run efficiency in the 40-75 min band with an RHR baseline (2022+),
plus a year control. Load EWMAs use the report windows (7/42/182 days) and the
previous day's value, so a run never sees its own load.

Analyses
--------
1. Annual running vs cross load composition.
2. Weekly cross-load share and the performance of high-cross weeks.
3. Correlation of efficiency with running-only, total and cross load (raw and
   year-adjusted).
4. `efficiency ~ running_load + cross_load + year`, with the transfer ratio
   `k = cross_coefficient / running_coefficient` and a bootstrap CI.
5. A grid over `combined = running + k*cross` to show which k fits best.
6. Sensitivity: 7/42/182-day EWMAs.

Decision
--------
- If cross load adds no measurable fit (k CI includes 0, tiny R² gain), the
  running-only load is the honest running-fitness series.
- If cross load adds a positive, stable contribution, report k with its
  uncertainty, but do not promote a factor on a handful of cycling phases.

    uv run --env-file .env python experiments/cross_training_load.py
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

import plotly.graph_objects as go

from hobbyjogging_core.workouts import is_quality
from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    MIN_EXCESS_HR,
    resting_hr_baselines,
)
from hobbyjogging_report.series import alpha_from_time_constant, date_range, ewma
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

WINDOWS = (7, 42, 182)
PRIMARY_WINDOW = 42
MIN_SPEED = 1.5
MAX_SPEED = 6.0
STEADY_MIN = 40.0
STEADY_MAX = 75.0
QUALITY_METHODS = {"intervals", "race", "progression", "long_run", "fartlek"}
QUALITY_TARGETS = {
    "lt1",
    "subthreshold",
    "threshold",
    "vo2max",
    "speed",
    "marathon",
}
BOOTSTRAP = 400
SEED = 23


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    work = [row[:] for row in matrix]
    values = vector[:]

    for column in range(size):
        pivot = max(range(column, size), key=lambda i: abs(work[i][column]))
        if abs(work[pivot][column]) < 1e-12:
            raise ValueError("singular design")
        work[column], work[pivot] = work[pivot], work[column]
        values[column], values[pivot] = values[pivot], values[column]

        for row in range(size):
            if row == column:
                continue
            factor = work[row][column] / work[column][column]
            if factor == 0:
                continue
            for k in range(column, size):
                work[row][k] -= factor * work[column][k]
            values[row] -= factor * values[column]

    return [values[i] / work[i][i] for i in range(size)]


def correlation(xs: list[float], ys: list[float]) -> float:
    mx = mean(xs)
    my = mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return cov / (vx * vy) ** 0.5 if vx and vy else 0.0


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def residuals_on(values: list[float], control: list[float]) -> list[float]:
    mean_c = mean(control)
    mean_v = mean(values)
    sxx = sum((c - mean_c) ** 2 for c in control)
    if not sxx:
        return [value - mean_v for value in values]
    slope = (
        sum((c - mean_c) * (v - mean_v) for c, v in zip(control, values))
        / sxx
    )
    intercept = mean_v - slope * mean_c
    return [
        value - (intercept + slope * c) for value, c in zip(values, control)
    ]


def daily_load(activities, start: date, end: date):
    running: dict[date, float] = defaultdict(float)
    cross: dict[date, float] = defaultdict(float)

    for activity in activities:
        load = activity.training_load or 0.0
        if activity.type in RUN_TYPES:
            running[activity.date] += load
        else:
            cross[activity.date] += load

    days = date_range(start, end)
    return days, [running[day] for day in days], [cross[day] for day in days]


def ewma_map(days: list[date], values: list[float], window: int) -> dict[date, float]:
    series = ewma(values, alpha_from_time_constant(window), initial=values[0])
    return dict(zip(days, series))


def performance_rows(activities, baseline) -> list[dict]:
    rows = []

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue
        if activity.duration_s <= 0 or activity.distance_m <= 0:
            continue
        if activity.avg_hr is None:
            continue

        minutes = activity.duration_s / 60.0
        if not (STEADY_MIN <= minutes <= STEADY_MAX):
            continue

        methods = set(activity.workout_methods)
        targets = set(activity.workout_targets)
        if methods & QUALITY_METHODS or targets & QUALITY_TARGETS:
            continue
        if "recovery" in targets:
            continue
        if is_quality(methods, targets) is True:
            continue

        resting_hr = baseline(activity.date)
        if resting_hr is None:
            continue

        excess = activity.avg_hr - resting_hr
        if excess < MIN_EXCESS_HR:
            continue

        speed = activity.distance_m / activity.duration_s
        if not (MIN_SPEED <= speed <= MAX_SPEED):
            continue

        rows.append(
            {
                "date": activity.date,
                "year": activity.date.year,
                "week": activity.date - timedelta(days=activity.date.weekday()),
                "efficiency": activity.distance_m / (excess * minutes),
                "trail": activity.type == "trail_run",
            }
        )

    return rows


def attach_load(rows: list[dict], days, run_maps, cross_maps) -> list[dict]:
    index = {day: position for position, day in enumerate(days)}
    attached = []

    for row in rows:
        position = index.get(row["date"] - timedelta(days=1))
        if position is None:
            continue
        features = {"date": row["date"], "year": row["year"], "week": row["week"],
                    "efficiency": row["efficiency"], "trail": row["trail"]}
        complete = True
        for window in WINDOWS:
            run = run_maps[window][days[position]]
            cross = cross_maps[window][days[position]]
            features[f"run_{window}"] = run
            features[f"cross_{window}"] = cross
            features[f"total_{window}"] = run + cross
            if run + cross <= 0:
                complete = False
        if complete:
            attached.append(features)

    return attached


def fit(rows: list[dict], features) -> tuple[list[float], float, float]:
    width = len(features(rows[0]))
    xtx = [[0.0] * width for _ in range(width)]
    xty = [0.0] * width

    for row in rows:
        x = features(row)
        y = row["efficiency"]
        for i in range(width):
            xty[i] += x[i] * y
            for j in range(width):
                xtx[i][j] += x[i] * x[j]

    beta = solve(xtx, xty)
    residual = [
        row["efficiency"]
        - sum(weight * value for weight, value in zip(features(row), beta))
        for row in rows
    ]
    sse = sum(value ** 2 for value in residual)
    mean_y = mean(row["efficiency"] for row in rows)
    ss_tot = sum((row["efficiency"] - mean_y) ** 2 for row in rows)
    return beta, 1 - sse / ss_tot if ss_tot else 0.0, sse / len(rows)


def main() -> None:
    with create_source() as source:
        activities = source.activities(date(2000, 1, 1), date.today())
        wellness = source.wellness(date(1999, 1, 1), date.today())

    baseline = resting_hr_baselines(wellness)
    valid = [a for a in activities if a.training_load is not None]
    start = min(a.date for a in activities)
    end = max(a.date for a in activities)
    days, running_load, cross_load = daily_load(activities, start, end)

    print(
        f"{len(valid)} activities with load, {len(days)} days "
        f"({start}..{end})"
    )

    annual = defaultdict(lambda: [0.0, 0.0])
    for day, run, cross in zip(days, running_load, cross_load):
        annual[day.year][0] += run
        annual[day.year][1] += cross
    table(
        [
            (
                year,
                f"{values[0]:.0f}",
                f"{values[1]:.0f}",
                f"{100 * values[1] / (values[0] + values[1]):.0f}%"
                if values[0] + values[1]
                else "-",
            )
            for year, values in sorted(annual.items())
        ],
        headers=["year", "running load", "cross load", "cross share"],
    )

    run_maps = {
        window: ewma_map(days, running_load, window) for window in WINDOWS
    }
    cross_maps = {
        window: ewma_map(days, cross_load, window) for window in WINDOWS
    }

    performance = performance_rows(activities, baseline)
    rows = attach_load(performance, days, run_maps, cross_maps)
    print(
        f"{len(performance)} steady performance runs, "
        f"{len(rows)} with load features"
    )
    if len(rows) < 100:
        print("not enough performance rows")
        return

    # Weekly cross-load share and high-cross weeks.
    weekly_run = defaultdict(float)
    weekly_cross = defaultdict(float)
    for day, run, cross in zip(days, running_load, cross_load):
        week = day - timedelta(days=day.weekday())
        weekly_run[week] += run
        weekly_cross[week] += cross

    high_weeks = {
        week
        for week in weekly_run
        if weekly_run[week] + weekly_cross[week] > 0
        and weekly_cross[week] / (weekly_run[week] + weekly_cross[week]) >= 0.2
    }
    high_rows = [row for row in rows if row["week"] in high_weeks]
    low_rows = [row for row in rows if row["week"] not in high_weeks]
    print(
        f"weeks with >=20% cross load: {len(high_weeks)}; "
        f"performance runs in them: {len(high_rows)} vs {len(low_rows)}"
    )
    if high_rows and low_rows:
        high_mean = mean(row["efficiency"] for row in high_rows)
        low_mean = mean(row["efficiency"] for row in low_rows)
        print(
            f"mean efficiency: high-cross {high_mean:.3f} "
            f"vs other {low_mean:.3f}"
        )

    print("\ncorrelations with efficiency (42-day EWMA unless noted):")
    corr_rows = []
    years = [float(row["year"]) for row in rows]
    efficiency = [row["efficiency"] for row in rows]
    adjusted_efficiency = residuals_on(efficiency, years)
    for window in WINDOWS:
        for name in ("run", "total", "cross"):
            values = [row[f"{name}_{window}"] for row in rows]
            adjusted = correlation(
                adjusted_efficiency, residuals_on(values, years)
            )
            corr_rows.append(
                (
                    f"{window}d {name}",
                    f"{correlation(efficiency, values):+.2f}",
                    f"{adjusted:+.2f}",
                )
            )
    table(
        corr_rows,
        headers=["load", "raw r", "year-adjusted r"],
    )

    # Running + cross + year, primary window.
    def features(row: dict) -> list[float]:
        return [
            1.0,
            row[f"run_{PRIMARY_WINDOW}"],
            row[f"cross_{PRIMARY_WINDOW}"],
            row["year"] - 2024,
            row["trail"],
        ]

    beta, r2, mse = fit(rows, features)
    k = beta[2] / beta[1] if beta[1] else None
    rng = random.Random(SEED)
    samples = []
    for _ in range(BOOTSTRAP):
        draw = [rows[rng.randrange(len(rows))] for _ in range(len(rows))]
        try:
            sample, _, _ = fit(draw, features)
        except ValueError:
            continue
        if sample[1]:
            samples.append(sample[2] / sample[1])
    low, high = (
        (percentile(samples, 0.025), percentile(samples, 0.975))
        if samples
        else (None, None)
    )
    print(f"\nmodel: efficiency ~ run + cross + year + trail "
          f"(R²={r2:.3f}, RMSE={mse ** 0.5:.3f})")
    print(
        f"running coefficient {beta[1]:+.6f}, "
        f"cross coefficient {beta[2]:+.6f}, "
        f"transfer k={k:+.2f}" if k is not None else "transfer k unavailable"
    )
    if low is not None:
        print(f"bootstrap 95% k: {low:+.2f}..{high:+.2f}")

    # Grid over combined load.
    print("\ntransfer grid (combined = running + k*cross, with year):")
    grid_rows = []
    best = None
    for step in range(0, 11):
        factor = step / 10
        def grid_features(row: dict) -> list[float]:
            return [
                1.0,
                row[f"run_{PRIMARY_WINDOW}"]
                + factor * row[f"cross_{PRIMARY_WINDOW}"],
                row["year"] - 2024,
                row["trail"],
            ]
        _, grid_r2, grid_mse = fit(rows, grid_features)
        grid_rows.append((f"{factor:.1f}", f"{grid_r2:.3f}", f"{grid_mse ** 0.5:.3f}"))
        if best is None or grid_r2 > best[1]:
            best = (factor, grid_r2)
    table(grid_rows, headers=["k", "R²", "RMSE"])
    print(f"best grid k: {best[0]:.1f} (R² {best[1]:.3f})")

    # Plot: running vs total 42-day EWMA.
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=days,
            y=[run_maps[PRIMARY_WINDOW][day] for day in days],
            mode="lines",
            name="running load",
            line={"color": "#4c78a8", "width": 2},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=days,
            y=[
                run_maps[PRIMARY_WINDOW][day] + cross_maps[PRIMARY_WINDOW][day]
                for day in days
            ],
            mode="lines",
            name="total load",
            line={"color": "#e45756", "width": 1.5, "dash": "dash"},
        )
    )
    figure.update_yaxes(title_text=f"{PRIMARY_WINDOW}-day load EWMA")
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Running vs total load",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "cross-training-load")

    # Plot: transfer grid.
    factors = [step / 10 for step in range(11)]
    values = []
    for factor in factors:
        def grid_features(row: dict) -> list[float]:
            return [
                1.0,
                row[f"run_{PRIMARY_WINDOW}"]
                + factor * row[f"cross_{PRIMARY_WINDOW}"],
                row["year"] - 2024,
                row["trail"],
            ]
        _, grid_r2, _ = fit(rows, grid_features)
        values.append(grid_r2)
    figure = go.Figure(
        go.Scatter(x=factors, y=values, mode="lines+markers")
    )
    figure.update_xaxes(title_text="cross-load transfer k")
    figure.update_yaxes(title_text="R²")
    figure.update_layout(title="Fit vs cross-training transfer")
    save(figure, "cross-training-transfer")


if __name__ == "__main__":
    main()
