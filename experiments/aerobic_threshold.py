"""Experiment: is the pace at a fixed heart rate moving?

Question
--------
"Speed at a fixed HR" is the most intuitive aerobic-fitness index: how fast
the same heart rate buys you. It is not a measured threshold; it is the
speed predicted by the HR-speed line of a period at a reference HR.

Definitions
-----------
For each quarter, fit two ordinary least-squares lines on steady runs::

    HR      = a + b * speed          -> speed at 140 bpm (absolute index)
    HR-RHR  = a + b * speed          -> speed at RHR + 90 bpm (relative index)

RHR is the existing 365-day median resting-HR baseline. Reporting both
separates a real fitness change from a resting-HR shift: the absolute index
moves when RHR moves, the relative one does not.

Population and guards
---------------------
Steady runs, 30-90 min, no recovery target, no interval/race/progression
workout, no trail, valid HR/distance/time and RHR, average HR at least 10 bpm
above resting, sane speed. Quarters need at least 20 runs to fit. The
reference HR must lie inside the quarter's observed range, otherwise the
estimate is an extrapolation and is flagged. RHR starts in Sep 2022.

Comparisons
-----------
- Quarterly and yearly pace at both references, with bootstrap intervals.
- Trend slope and R², split-half reliability, correlation with quarter
  duration and RHR.
- Sensitivity: 40-75 min band, RHR 180-day baseline.

Decision
--------
If the index is reliable and its trend agrees with the efficiency series, it
is a candidate card ("speed at 140 bpm" / "speed at RHR+90"). If it is too
noisy or mostly tracks RHR or duration mix, reject it.

    uv run --env-file .env python experiments/aerobic_threshold.py
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime
from statistics import mean, median, stdev

import plotly.graph_objects as go

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    MIN_EXCESS_HR,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_MINUTES = 30.0
MAX_MINUTES = 90.0
MIN_SPEED = 1.5
MAX_SPEED = 6.0
MIN_RUNS = 20
TARGET_HR = 140.0
TARGET_EXCESS = 90.0
NON_STEADY_METHODS = {"intervals", "race", "progression"}
REPEATS = 300
SEED = 13


def quarter_key(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def quarter_label(key: tuple[int, int]) -> str:
    return f"{key[0]}Q{key[1]}"


def quarter_start(key: tuple[int, int]) -> datetime:
    return datetime(key[0], 3 * (key[1] - 1) + 1, 1)


def format_pace(speed_mps: float | None) -> str:
    if not speed_mps or speed_mps <= 0:
        return "-"
    seconds = 1000.0 / speed_mps
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def build_rows(activities, baseline) -> tuple[list[dict], dict[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    rows = []

    for activity in activities:
        counts["activities"] += 1

        if activity.type not in RUN_TYPES:
            continue
        counts["running"] += 1

        if activity.type != "run":
            counts["trail/other run sport"] += 1
            continue

        if activity.duration_s <= 0 or activity.distance_m <= 0:
            continue

        minutes = activity.duration_s / 60.0
        if not (MIN_MINUTES <= minutes <= MAX_MINUTES):
            counts["outside 30-90 min"] += 1
            continue

        if activity.avg_hr is None:
            continue

        resting_hr = baseline(activity.date)
        if resting_hr is None:
            continue

        excess = activity.avg_hr - resting_hr
        if excess < MIN_EXCESS_HR:
            counts["small HR excess"] += 1
            continue

        speed = activity.distance_m / activity.duration_s
        if not (MIN_SPEED <= speed <= MAX_SPEED):
            counts["sane speed"] += 1
            continue

        if activity.workout_methods and (
            set(activity.workout_methods) & NON_STEADY_METHODS
        ):
            counts["interval/race/progression"] += 1
            continue

        if "recovery" in activity.workout_targets:
            counts["recovery target"] += 1
            continue

        rows.append(
            {
                "date": activity.date,
                "quarter": quarter_key(activity.date),
                "speed": speed,
                "hr": activity.avg_hr,
                "excess": excess,
                "rhr": resting_hr,
                "minutes": minutes,
            }
        )

    return rows, counts


def fit_line(rows: list[dict], key: str) -> tuple[float, float, float]:
    """OLS y = intercept + slope * speed; return slope, intercept, R²."""
    xs = [row["speed"] for row in rows]
    ys = [row[key] for row in rows]
    mean_x = mean(xs)
    mean_y = mean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    intercept = mean_y - slope * mean_x
    ss_res = sum(
        (y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)
    )
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    return slope, intercept, 1 - ss_res / ss_tot if ss_tot else 0.0


def speed_at(
    slope: float,
    intercept: float,
    target: float,
) -> float | None:
    if slope <= 0:
        return None
    speed = (target - intercept) / slope
    return speed if MIN_SPEED <= speed <= MAX_SPEED else None


def quarter_stats(chunk: list[dict]) -> dict:
    hr_slope, hr_intercept, hr_r2 = fit_line(chunk, "hr")
    excess_slope, excess_intercept, excess_r2 = fit_line(chunk, "excess")

    return {
        "hr_slope": hr_slope,
        "hr_intercept": hr_intercept,
        "v140": speed_at(hr_slope, hr_intercept, TARGET_HR),
        "hr_r2": hr_r2,
        "excess_slope": excess_slope,
        "excess_intercept": excess_intercept,
        "v90": speed_at(
            excess_slope, excess_intercept, TARGET_EXCESS
        ),
        "excess_r2": excess_r2,
        "hr_in_range": min(row["hr"] for row in chunk)
        <= TARGET_HR
        <= max(row["hr"] for row in chunk),
        "min_hr": min(row["hr"] for row in chunk),
        "max_hr": max(row["hr"] for row in chunk),
        "excess_in_range": min(row["excess"] for row in chunk)
        <= TARGET_EXCESS
        <= max(row["excess"] for row in chunk),
        "min_excess": min(row["excess"] for row in chunk),
        "max_excess": max(row["excess"] for row in chunk),
        "median_minutes": median(row["minutes"] for row in chunk),
        "median_rhr": median(row["rhr"] for row in chunk),
        "n": len(chunk),
    }


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap(chunk: list[dict], iterations: int = REPEATS):
    rng = random.Random(SEED)
    count = len(chunk)
    samples_v140 = []
    samples_v90 = []

    for _ in range(iterations):
        draw = [chunk[rng.randrange(count)] for _ in range(count)]
        stats = quarter_stats(draw)
        if stats["v140"] is not None:
            samples_v140.append(stats["v140"])
        if stats["v90"] is not None:
            samples_v90.append(stats["v90"])

    def interval(samples):
        if len(samples) < 10:
            return None, None
        return percentile(samples, 0.025), percentile(samples, 0.975)

    return interval(samples_v140), interval(samples_v90)


def correlation(xs: list[float], ys: list[float]) -> float:
    mean_x = mean(xs)
    mean_y = mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    return cov / (var_x * var_y) ** 0.5 if var_x and var_y else 0.0


def trend_values(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mean_x = mean(xs)
    mean_y = mean(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    intercept = mean_y - slope * mean_x
    ss_res = sum(
        (y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)
    )
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    return slope, 1 - ss_res / ss_tot if ss_tot else 0.0


def trend(series: list[dict], key: str) -> tuple[float, float]:
    return trend_values(
        [entry["time"] for entry in series],
        [entry[key] for entry in series],
    )


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a small dense linear system by Gaussian elimination."""
    size = len(vector)
    work = [row[:] for row in matrix]
    values = vector[:]

    for column in range(size):
        pivot = max(range(column, size), key=lambda i: abs(work[i][column]))
        if abs(work[pivot][column]) < 1e-12:
            raise ValueError("singular design matrix")
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


def adjusted_speed(chunk: list[dict], target: float) -> float | None:
    """Speed at ``target`` HR from HR = a + b*v + c*(duration - median)."""
    center = median(row["minutes"] for row in chunk)
    xtx = [[0.0] * 3 for _ in range(3)]
    xty = [0.0] * 3

    for row in chunk:
        x = [1.0, row["speed"], row["minutes"] - center]
        y = row["hr"]
        for i in range(3):
            xty[i] += x[i] * y
            for j in range(3):
                xtx[i][j] += x[i] * x[j]

    try:
        beta = solve(xtx, xty)
    except ValueError:
        return None

    if beta[1] <= 0:
        return None

    speed = (target - beta[0]) / beta[1]
    return speed if MIN_SPEED <= speed <= MAX_SPEED else None


def adjusted_reference_sensitivity(series: list[dict]) -> list[tuple]:
    rows = []

    for reference in (125, 130, 135, 140, 145, 150):
        valid = []
        for entry in series:
            speed = adjusted_speed(entry["rows"], reference)
            if speed is not None:
                valid.append((entry, speed))

        if len(valid) < 6:
            continue

        values = [speed for _, speed in valid]
        slope, r2 = trend_values(
            [entry["time"] for entry, _ in valid], values
        )
        duration_correlation = correlation(
            [entry["median_minutes"] for entry, _ in valid], values
        )
        rows.append(
            (
                f"{reference:.0f} bpm",
                len(valid),
                format_pace(mean(values)),
                f"{slope:+.3f}",
                f"{r2:.2f}",
                f"{duration_correlation:+.2f}",
            )
        )

    return rows


def reference_sensitivity(series: list[dict]) -> list[tuple]:
    """Trend quality for different fixed-HR references."""
    rows = []

    for reference in (125, 130, 135, 140, 145, 150):
        valid = []
        for entry in series:
            speed = speed_at(
                entry["hr_slope"], entry["hr_intercept"], reference
            )
            if speed is not None:
                valid.append((entry, speed))

        if len(valid) < 6:
            continue

        values = [speed for _, speed in valid]
        slope, r2 = trend_values(
            [entry["time"] for entry, _ in valid], values
        )
        in_range = sum(
            entry["min_hr"] <= reference <= entry["max_hr"]
            for entry, _ in valid
        )
        duration_correlation = correlation(
            [entry["median_minutes"] for entry, _ in valid], values
        )
        rows.append(
            (
                f"{reference:.0f} bpm",
                len(valid),
                format_pace(mean(values)),
                f"{slope:+.3f}",
                f"{r2:.2f}",
                f"{100 * in_range / len(valid):.0f}%",
                f"{duration_correlation:+.2f}",
            )
        )

    return rows


def split_half(series: list[dict]):
    rng = random.Random(SEED)
    eligible = [entry for entry in series if entry["n"] >= 30]

    if len(eligible) < 6:
        return None, None

    correlations_v140 = []
    correlations_v90 = []

    for _ in range(200):
        left_v140, right_v140 = [], []
        left_v90, right_v90 = [], []

        for entry in eligible:
            chunk = entry["rows"][:]
            rng.shuffle(chunk)
            half = len(chunk) // 2
            first = quarter_stats(chunk[:half])
            second = quarter_stats(chunk[half:])
            if first["v140"] and second["v140"]:
                left_v140.append(first["v140"])
                right_v140.append(second["v140"])
            if first["v90"] and second["v90"]:
                left_v90.append(first["v90"])
                right_v90.append(second["v90"])

        if len(left_v140) >= 6:
            correlations_v140.append(correlation(left_v140, right_v140))
        if len(left_v90) >= 6:
            correlations_v90.append(correlation(left_v90, right_v90))

    return (
        mean(correlations_v140) if correlations_v140 else None,
        mean(correlations_v90) if correlations_v90 else None,
    )


def summarize(name: str, series: list[dict], key: str) -> tuple:
    valid = [entry for entry in series if entry[key] is not None]
    values = [entry[key] for entry in valid]
    trend_slope, trend_r2 = trend(valid, key)
    split_v140, split_v90 = split_half(series)
    split = split_v140 if key == "v140" else split_v90
    return (
        name,
        len(values),
        f"{mean(values):.2f}",
        f"{stdev(values):.3f}" if len(values) > 1 else "-",
        f"{trend_slope:+.3f}",
        f"{trend_r2:.2f}",
        f"{split:.2f}" if split is not None else "-",
        f"{correlation([entry['median_minutes'] for entry in valid], values):+.2f}",
        f"{correlation([entry['median_rhr'] for entry in valid], values):+.2f}",
    )


def main() -> None:
    with create_source() as source:
        activities = source.activities(date(2000, 1, 1), date.today())
        wellness = source.wellness(date(1999, 1, 1), date.today())

    baseline = resting_hr_baselines(wellness)
    rows, counts = build_rows(activities, baseline)

    print(
        f"{counts['activities']} activities, {counts['running']} running; "
        f"{len(rows)} steady runs after the guards"
    )
    table(
        [
            (reason, count)
            for reason, count in counts.items()
            if reason not in {"activities", "running"}
        ],
        headers=["guard", "excluded"],
    )

    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["quarter"]].append(row)

    series = []
    for key in sorted(groups):
        chunk = groups[key]
        if len(chunk) < MIN_RUNS:
            continue
        stats = quarter_stats(chunk)
        if stats["v140"] is None or stats["v90"] is None:
            continue
        v140_interval, v90_interval = bootstrap(chunk)
        entry = {
            "key": key,
            "label": quarter_label(key),
            "time": key[0] + (key[1] - 1) / 4,
            "rows": chunk,
            "v140_ci": v140_interval,
            "v90_ci": v90_interval,
        }
        entry.update(stats)
        series.append(entry)

    if len(series) < 6:
        print(f"only {len(series)} usable quarters; not enough for a trend")
        return

    print("\nquarterly pace at fixed HR:")
    table(
        [
            (
                entry["label"],
                entry["n"],
                f"{entry['median_minutes']:.0f}",
                f"{entry['median_rhr']:.0f}",
                format_pace(entry["v140"]),
                (
                    f"{format_pace(entry['v140_ci'][0])}-"
                    f"{format_pace(entry['v140_ci'][1])}"
                    if entry["v140_ci"][0]
                    else "-"
                ),
                format_pace(entry["v90"]),
                "yes" if entry["hr_in_range"] else "extrapolated",
                f"{entry['hr_r2']:.2f}",
            )
            for entry in series
        ],
        headers=[
            "quarter",
            "n",
            "min",
            "RHR",
            "pace @140",
            "95% CI",
            "pace @RHR+90",
            "140 in range",
            "R²",
        ],
    )

    print("\nreliability and trend:")
    table(
        [
            summarize("speed @140 bpm", series, "v140"),
            summarize("speed @RHR+90", series, "v90"),
        ],
        headers=[
            "index",
            "quarters",
            "mean m/s",
            "SD",
            "trend m/s per year",
            "R²",
            "split-half r",
            "r(duration)",
            "r(RHR)",
        ],
    )
    print(
        "r(duration) and r(RHR) are correlations of the quarterly index "
        "with the quarter's median duration and resting HR."
    )

    print("\nreference-HR sensitivity (absolute index):")
    table(
        reference_sensitivity(series),
        headers=[
            "reference",
            "quarters",
            "mean pace",
            "trend m/s per year",
            "R²",
            "in observed range",
            "r(duration)",
        ],
    )

    print("\nduration-adjusted fit (at quarter median duration):")
    table(
        adjusted_reference_sensitivity(series),
        headers=[
            "reference",
            "quarters",
            "mean pace",
            "trend m/s per year",
            "R²",
            "r(duration)",
        ],
    )

    by_year: dict[int, list[dict]] = defaultdict(list)
    for entry in series:
        by_year[entry["key"][0]].append(entry)

    print("\nby year:")
    table(
        [
            (
                year,
                len(chunk),
                sum(entry["n"] for entry in chunk),
                format_pace(mean(entry["v140"] for entry in chunk)),
                format_pace(mean(entry["v90"] for entry in chunk)),
                f"{median(entry['median_rhr'] for entry in chunk):.0f}",
            )
            for year, chunk in sorted(by_year.items())
        ],
        headers=["year", "quarters", "runs", "pace @140", "pace @RHR+90", "RHR"],
    )

    # Sensitivity: narrower duration band.
    narrower = [
        row for row in rows if 40.0 <= row["minutes"] <= 75.0
    ]
    narrow_groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in narrower:
        narrow_groups[row["quarter"]].append(row)
    narrow_series = []
    for key in sorted(narrow_groups):
        chunk = narrow_groups[key]
        if len(chunk) < MIN_RUNS:
            continue
        stats = quarter_stats(chunk)
        if stats["v140"] is None or stats["v90"] is None:
            continue
        entry = {
            "key": key,
            "label": quarter_label(key),
            "time": key[0] + (key[1] - 1) / 4,
            "rows": chunk,
        }
        entry.update(stats)
        narrow_series.append(entry)

    if len(narrow_series) >= 6:
        print("\nsensitivity (40-75 min):")
        table(
            [
                summarize("speed @140 bpm", narrow_series, "v140"),
                summarize("speed @RHR+90", narrow_series, "v90"),
            ],
            headers=[
                "index",
                "quarters",
                "mean m/s",
                "SD",
                "trend m/s per year",
                "R²",
                "split-half r",
                "r(duration)",
                "r(RHR)",
            ],
        )

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[quarter_start(entry["key"]) for entry in series],
            y=[1000.0 / entry["v140"] for entry in series],
            error_y={
                "type": "data",
                "array": [
                    (1000.0 / entry["v140"])
                    - (1000.0 / entry["v140_ci"][1])
                    if entry["v140_ci"][1]
                    else 0
                    for entry in series
                ],
                "arrayminus": [
                    (1000.0 / entry["v140_ci"][0])
                    - (1000.0 / entry["v140"])
                    if entry["v140_ci"][0]
                    else 0
                    for entry in series
                ],
                "visible": True,
            },
            mode="lines+markers",
            name="pace at 140 bpm",
            line={"color": "#4c78a8", "width": 2},
            marker={"size": 6},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[quarter_start(entry["key"]) for entry in series],
            y=[1000.0 / entry["v90"] for entry in series],
            mode="lines+markers",
            name="pace at RHR+90",
            line={"color": "#54a24b", "width": 2, "dash": "dash"},
            marker={"size": 5},
        )
    )
    figure.update_yaxes(
        title_text="pace (s/km, faster up)",
        autorange="reversed",
    )
    figure.update_xaxes(title_text="quarter")
    figure.update_layout(
        title="Pace at a fixed heart rate",
        legend={"orientation": "h", "y": -0.25},
    )
    save(figure, "aerobic-threshold-pace")


if __name__ == "__main__":
    main()
