"""Experiment: is the best-case efficiency frontier more consistent than the average?

Question
--------
Session efficiency averaged over all runs mixes good and bad days, heat,
fatigue and workout mix. A "frontier" estimator instead uses only the most
efficient runs of a period, approximating what the athlete demonstrates when
conditions are good. Does that track fitness more consistently?

Definitions
-----------
- Run efficiency: ``distance / ((avg_hr - RHR) * minutes)`` (m/excess beat),
  RHR from the existing 365-day median baseline.
- Average: weighted ``sum(distance) / sum(beats)`` over all runs in a quarter.
- Frontier: the same weighted estimator over the top 25% of runs by
  efficiency. This is the scalar version of the best-run envelope / upper
  hull in the pace-vs-HR plot; no per-sample streams are used.
- Equal-n subsampling: each quarter is sampled down to 20 runs, 300 times,
  so a quarter with more runs cannot win by having a better extreme. The
  mean over samples is the estimate; their spread is a sampling-noise band.

Population and guards
---------------------
Steady runs only, 30-90 min, no recovery target, no interval/race/progression
workout, no trail, valid HR/distance/time and RHR, average HR at least 10 bpm
above resting, sane speed, plausible efficiency (1.0-4.0) and average HR
(<=210). RHR starts in Sep 2022, so the series starts then.

Comparisons
-----------
Quarterly average vs frontier on: level, quarterly SD, quarter-to-quarter
SD, trend slope and R², split-half reliability, correlation with the number
of runs per quarter, and the 2025->2026 change. The frontier is expected to
sit above the average — only its shape and stability matter here.

Decision
--------
If the frontier has clearly better split-half reliability or a cleaner trend
and is not driven by run count or a few outliers, it is a candidate
"best demonstrated" series. If not, reject it: the average is sufficient.
This is an experiment, not a promoted metric.

    uv run --env-file .env python experiments/efficiency_frontier.py
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime
from statistics import mean, stdev

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
MIN_EFFICIENCY = 1.0
MAX_EFFICIENCY = 4.0
MAX_AVG_HR = 210.0
NON_STEADY_METHODS = {"intervals", "race", "progression"}
SAMPLE_SIZE = 20
REPEATS = 300
TOP_SHARE = 0.25
SEED = 11


def weighted_efficiency(rows: list[dict]) -> float:
    distance = sum(row["distance_m"] for row in rows)
    beats = sum(row["excess"] * row["minutes"] for row in rows)
    return distance / beats


def quarter_key(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def quarter_label(key: tuple[int, int]) -> str:
    return f"{key[0]}Q{key[1]}"


def quarter_start(key: tuple[int, int]) -> datetime:
    return datetime(key[0], 3 * (key[1] - 1) + 1, 1)


def build_rows(activities, baseline) -> tuple[list[dict], dict[str, int]]:
    """Per-run rows with the frontier population guards applied."""
    counts = defaultdict(int)
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

        if activity.avg_hr > MAX_AVG_HR:
            counts["implausible avg HR"] += 1
            continue

        efficiency = activity.distance_m / (excess * minutes)
        if not (MIN_EFFICIENCY <= efficiency <= MAX_EFFICIENCY):
            counts["implausible efficiency"] += 1
            continue

        rows.append(
            {
                "date": activity.date,
                "quarter": quarter_key(activity.date),
                "minutes": minutes,
                "speed": speed,
                "avg_hr": activity.avg_hr,
                "excess": excess,
                "distance_m": activity.distance_m,
                "efficiency": efficiency,
            }
        )

    return rows, counts


def subsample(chunk: list[dict], top_share: float = TOP_SHARE) -> dict[str, float]:
    """Equal-n resampling of the average and the top-share frontier."""
    rng = random.Random(SEED)
    averages = []
    frontiers = []

    for _ in range(REPEATS):
        draw = (
            rng.sample(chunk, SAMPLE_SIZE)
            if len(chunk) > SAMPLE_SIZE
            else chunk[:]
        )
        averages.append(weighted_efficiency(draw))

        ranked = sorted(
            draw, key=lambda row: row["efficiency"], reverse=True
        )
        take = max(1, round(top_share * len(ranked)))
        frontiers.append(weighted_efficiency(ranked[:take]))

    return {
        "average": mean(averages),
        "average_sd": stdev(averages),
        "frontier": mean(frontiers),
        "frontier_sd": stdev(frontiers),
    }


def raw_stats(chunk: list[dict], top_share: float = TOP_SHARE) -> dict[str, float]:
    """Unbalanced estimates, for showing the sample-size bias."""
    ranked = sorted(chunk, key=lambda row: row["efficiency"], reverse=True)
    take = max(1, round(top_share * len(ranked)))
    return {
        "average": weighted_efficiency(chunk),
        "frontier": weighted_efficiency(ranked[:take]),
    }


def correlation(xs: list[float], ys: list[float]) -> float:
    mean_x = mean(xs)
    mean_y = mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    return cov / (var_x * var_y) ** 0.5 if var_x and var_y else 0.0


def trend(series: list[dict], key: str) -> tuple[float, float]:
    """OLS slope per year and R² for one series."""
    xs = [entry["time"] for entry in series]
    ys = [entry[key] for entry in series]
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


def split_half(
    series: list[dict],
    top_share: float = TOP_SHARE,
) -> tuple[float | None, float | None]:
    """Average split-half correlation of the average and the frontier."""
    rng = random.Random(SEED)
    eligible = [entry for entry in series if entry["n"] >= SAMPLE_SIZE]

    if len(eligible) < 6:
        return None, None

    average_correlations = []
    frontier_correlations = []

    for _ in range(200):
        left_average, right_average = [], []
        left_frontier, right_frontier = [], []

        for entry in eligible:
            chunk = entry["rows"][:]
            rng.shuffle(chunk)
            half = len(chunk) // 2

            for part, averages, frontiers in (
                (chunk[:half], left_average, left_frontier),
                (chunk[half:], right_average, right_frontier),
            ):
                averages.append(weighted_efficiency(part))
                ranked = sorted(
                    part, key=lambda row: row["efficiency"], reverse=True
                )
                take = max(1, round(top_share * len(ranked)))
                frontiers.append(weighted_efficiency(ranked[:take]))

        average_correlations.append(
            correlation(left_average, right_average)
        )
        frontier_correlations.append(
            correlation(left_frontier, right_frontier)
        )

    return mean(average_correlations), mean(frontier_correlations)


def frontier_series(
    groups: dict[tuple[int, int], list[dict]],
    top_share: float,
) -> list[dict]:
    """Equal-n series for one frontier definition."""
    entries = []

    for key in sorted(groups):
        chunk = groups[key]
        if len(chunk) < SAMPLE_SIZE:
            continue
        entry = {
            "key": key,
            "label": quarter_label(key),
            "time": key[0] + (key[1] - 1) / 4,
            "n": len(chunk),
            "rows": chunk,
        }
        entry.update(subsample(chunk, top_share=top_share))
        entries.append(entry)

    return entries


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
    excluded = [
        (reason, count)
        for reason, count in counts.items()
        if reason not in {"activities", "running"}
    ]
    if excluded:
        table(excluded, headers=["guard", "excluded"])

    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["quarter"]].append(row)

    series = []
    for key in sorted(groups):
        chunk = groups[key]
        entry = {
            "key": key,
            "label": quarter_label(key),
            "time": key[0] + (key[1] - 1) / 4,
            "n": len(chunk),
            "rows": chunk,
            "raw": raw_stats(chunk),
            "available": len(chunk) >= SAMPLE_SIZE,
        }
        if entry["available"]:
            entry.update(subsample(chunk))
        series.append(entry)

    print("\nquarterly series (equal-n average vs top-quartile frontier):")
    table(
        [
            (
                entry["label"],
                entry["n"],
                f"{entry['average']:.2f}"
                if entry["available"]
                else "-",
                f"{entry['frontier']:.2f}"
                if entry["available"]
                else "-",
                f"{entry['raw']['average']:.2f}",
                f"{entry['raw']['frontier']:.2f}",
                f"{entry['frontier'] - entry['average']:+.3f}"
                if entry["available"]
                else "-",
            )
            for entry in series
        ],
        headers=[
            "quarter",
            "n",
            "average",
            "frontier",
            "raw avg",
            "raw front",
            "gap",
        ],
    )

    usable = [entry for entry in series if entry["available"]]
    if len(usable) < 6:
        print("fewer than six usable quarters; not enough for a comparison")
        return

    average_sd = stdev(entry["average"] for entry in usable)
    frontier_sd = stdev(entry["frontier"] for entry in usable)
    average_diff_sd = stdev(
        second["average"] - first["average"]
        for first, second in zip(usable, usable[1:])
    )
    frontier_diff_sd = stdev(
        second["frontier"] - first["frontier"]
        for first, second in zip(usable, usable[1:])
    )
    average_slope, average_r2 = trend(usable, "average")
    frontier_slope, frontier_r2 = trend(usable, "frontier")
    average_split, frontier_split = split_half(series)

    counts_n = [entry["n"] for entry in usable]
    average_by_count = correlation(
        counts_n, [entry["average"] for entry in usable]
    )
    frontier_by_count = correlation(
        counts_n, [entry["frontier"] for entry in usable]
    )
    raw_by_count = correlation(
        counts_n, [entry["raw"]["frontier"] for entry in usable]
    )
    raw_diff_sd = stdev(
        second["raw"]["frontier"] - first["raw"]["frontier"]
        for first, second in zip(usable, usable[1:])
    )

    summary = [
        (
            "average",
            f"{mean(entry['average'] for entry in usable):.3f}",
            f"{average_sd:.3f}",
            f"{average_diff_sd:.3f}",
            f"{average_slope:+.3f}",
            f"{average_r2:.2f}",
            f"{average_split:.2f}" if average_split is not None else "-",
            f"{average_by_count:+.2f}",
        ),
        (
            "frontier",
            f"{mean(entry['frontier'] for entry in usable):.3f}",
            f"{frontier_sd:.3f}",
            f"{frontier_diff_sd:.3f}",
            f"{frontier_slope:+.3f}",
            f"{frontier_r2:.2f}",
            f"{frontier_split:.2f}" if frontier_split is not None else "-",
            f"{frontier_by_count:+.2f}",
        ),
        (
            "raw frontier",
            f"{mean(entry['raw']['frontier'] for entry in usable):.3f}",
            f"{stdev(entry['raw']['frontier'] for entry in usable):.3f}",
            f"{raw_diff_sd:.3f}",
            "-",
            "-",
            "-",
            f"{raw_by_count:+.2f}",
        ),
    ]

    print("\nconsistency summary:")
    table(
        summary,
        headers=[
            "estimator",
            "mean",
            "quarterly SD",
            "Δ SD",
            "trend/yr",
            "R²",
            "split-half r",
            "r(n)",
        ],
    )
    print(
        "r(n) is the correlation with the quarter's run count. The raw "
        "frontier should show a positive value; equal-n sampling should "
        "remove it."
    )

    print("\nfrontier definition sensitivity:")
    sensitivity = []
    for share in (0.10, 0.25, 0.33, 0.50):
        entries = frontier_series(groups, share)
        slope, r2 = trend(entries, "frontier")
        _, split = split_half(entries, top_share=share)
        by_count = correlation(
            [entry["n"] for entry in entries],
            [entry["frontier"] for entry in entries],
        )
        sensitivity.append(
            (
                f"top {share:.0%}",
                len(entries),
                f"{mean(entry['frontier'] for entry in entries):.3f}",
                f"{stdev(entry['frontier'] for entry in entries):.3f}",
                f"{slope:+.3f}",
                f"{r2:.2f}",
                f"{split:.2f}" if split is not None else "-",
                f"{by_count:+.2f}",
            )
        )
    table(
        sensitivity,
        headers=[
            "frontier",
            "quarters",
            "mean",
            "SD",
            "trend/yr",
            "R²",
            "split-half r",
            "r(n)",
        ],
    )

    by_year: dict[int, list[dict]] = defaultdict(list)
    for entry in usable:
        by_year[entry["key"][0]].append(entry)
    shifts = []
    for year in sorted(by_year):
        if len(by_year[year]) < 2:
            continue
        shifts.append(
            (
                year,
                len(by_year[year]),
                f"{mean(entry['average'] for entry in by_year[year]):.3f}",
                f"{mean(entry['frontier'] for entry in by_year[year]):.3f}",
            )
        )
    print("\nby year:")
    table(shifts, headers=["year", "quarters", "average", "frontier"])

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[quarter_start(entry["key"]) for entry in usable],
            y=[entry["average"] for entry in usable],
            error_y={
                "type": "data",
                "array": [entry["average_sd"] for entry in usable],
                "visible": True,
            },
            mode="lines+markers",
            name="average (equal n)",
            line={"color": "#4c78a8", "width": 1.5},
            marker={"size": 5},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[quarter_start(entry["key"]) for entry in usable],
            y=[entry["frontier"] for entry in usable],
            error_y={
                "type": "data",
                "array": [entry["frontier_sd"] for entry in usable],
                "visible": True,
            },
            mode="lines+markers",
            name="frontier (top 25%, equal n)",
            line={"color": "#54a24b", "width": 2},
            marker={"size": 6},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[quarter_start(entry["key"]) for entry in usable],
            y=[entry["raw"]["frontier"] for entry in usable],
            mode="lines+markers",
            name="raw frontier (not equal n)",
            line={"color": "#e45756", "width": 1, "dash": "dot"},
            marker={"size": 4},
        )
    )
    figure.update_yaxes(title_text="efficiency (m/excess beat)")
    figure.update_xaxes(title_text="quarter")
    figure.update_layout(
        title="Average vs best-case efficiency by quarter",
        legend={"orientation": "h", "y": -0.25},
    )
    save(figure, "efficiency-frontier")


if __name__ == "__main__":
    main()
