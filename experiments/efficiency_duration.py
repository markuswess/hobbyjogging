"""Experiment: does session efficiency depend on duration?

Hypothesis
----------
Session efficiency is ``distance / ((avg_hr - RHR) * minutes)``. Two effects
push the session average in opposite directions:

- the start-up transient: heart rate takes a few minutes to reach steady
  state, so short runs carry a larger share of low-HR minutes and look more
  efficient;
- cardiac drift: at the same pace, heart rate rises with time, so long runs
  look less efficient.

Model
-----
With session totals only (no laps, no streams)::

    excess = a + b*speed + c/T + d*T

``c < 0`` is the fixed transient (bpm*min deficit), ``d > 0`` the drift
(bpm/min). Efficiency at speed ``v`` is ``60*v/excess`` m/beat.

Population and guards
---------------------
Running activities with HR/distance/duration, a resting-HR baseline
(365-day median, expanding before that), duration 20-240 min, average HR at
least 10 bpm above resting, and a sane speed. The primary population excludes
interval/race/progression workouts; those are analyzed separately as a
population using their session averages (not single work reps). The same fit
is also repeated with them (and with trail runs) as sensitivity. RHR starts
in Sep 2022, so the analysis is limited to that period.

Decision
--------
Both coefficients significant with a meaningful efficiency difference
(>1% between 30 and 60 min, or >2% between 60 and 120 min) means the existing
metric has a duration bias and needs a guard or correction. Only ``c`` means
short runs are the problem; only ``d`` is the durability question; neither
means reject the correction. This experiment does not promote a metric; it
sizes the bias.

    uv run --env-file .env python experiments/efficiency_duration.py
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from math import sqrt
from statistics import mean, median, stdev

import plotly.graph_objects as go

from hobbyjogging_core.workouts import is_quality
from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    MIN_EXCESS_HR,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_DURATION_MIN = 20.0
MAX_DURATION_MIN = 240.0
MIN_SPEED = 1.5  # 11:07 min/km
MAX_SPEED = 6.0  # 2:47 min/km
NON_STEADY_METHODS = {"intervals", "race", "progression"}
BIN_EDGES = [
    (20, 30),
    (30, 45),
    (45, 60),
    (60, 90),
    (90, 120),
    (120, 180),
    (180, 240),
]
SPEED_BANDS = [(0.0, 10.5), (10.5, 11.5), (11.5, 12.5), (12.5, 99.0)]
BOOTSTRAP_ITERATIONS = 500
SEED = 7


# --- rows -----------------------------------------------------------------


def build_rows(activities, baseline) -> list[dict]:
    """Per-activity session rows with the values the model needs."""
    rows = []

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue
        if activity.duration_s <= 0 or activity.distance_m <= 0:
            continue
        if activity.avg_hr is None:
            continue

        minutes = activity.duration_s / 60.0
        speed = activity.distance_m / activity.duration_s
        resting_hr = baseline(activity.date)

        if resting_hr is None:
            continue

        excess = activity.avg_hr - resting_hr

        rows.append(
            {
                "id": activity.id,
                "date": activity.date,
                "name": activity.name,
                "sport": activity.type,
                "minutes": minutes,
                "speed": speed,
                "excess": excess,
                "rhr": resting_hr,
                "distance_m": activity.distance_m,
                "avg_hr": activity.avg_hr,
                "started_at_utc": activity.started_at_utc,
                "training_load": activity.training_load,
                "rpe": activity.rpe,
                "intensity": activity.intensity,
                "tags": set(activity.tags),
                "methods": set(activity.workout_methods),
                "targets": set(activity.workout_targets),
                "efficiency": (
                    activity.distance_m / (excess * minutes)
                    if excess >= MIN_EXCESS_HR
                    else None
                ),
            }
        )

    return rows


def select(
    rows: list[dict],
    *,
    include_intervals: bool = False,
    include_trail: bool = False,
    max_minutes: float = MAX_DURATION_MIN,
    intervals_only: bool = False,
) -> list[dict]:
    """Apply the population guards."""
    selected = []

    for row in rows:
        if row["minutes"] < MIN_DURATION_MIN or row["minutes"] > max_minutes:
            continue
        if row["excess"] < MIN_EXCESS_HR:
            continue
        if not (MIN_SPEED <= row["speed"] <= MAX_SPEED):
            continue
        if not include_trail and row["sport"] == "trail_run":
            continue
        non_steady = bool(row["methods"] & NON_STEADY_METHODS)
        if intervals_only:
            if not non_steady:
                continue
        elif not include_intervals and non_steady:
            continue
        selected.append(row)

    return selected


def funnel(rows: list[dict]) -> None:
    """Print how many activities survive each sequential guard."""
    steps = [
        ("rows with HR, distance, time and RHR", len(rows)),
        (
            "duration 20-240 min",
            sum(
                MIN_DURATION_MIN <= r["minutes"] <= MAX_DURATION_MIN
                for r in rows
            ),
        ),
        (
            "average HR at least 10 bpm above resting",
            sum(
                MIN_DURATION_MIN <= r["minutes"] <= MAX_DURATION_MIN
                and r["excess"] >= MIN_EXCESS_HR
                for r in rows
            ),
        ),
        (
            "sane speed",
            sum(
                MIN_DURATION_MIN <= r["minutes"] <= MAX_DURATION_MIN
                and r["excess"] >= MIN_EXCESS_HR
                and MIN_SPEED <= r["speed"] <= MAX_SPEED
                for r in rows
            ),
        ),
        (
            "not trail",
            sum(
                MIN_DURATION_MIN <= r["minutes"] <= MAX_DURATION_MIN
                and r["excess"] >= MIN_EXCESS_HR
                and MIN_SPEED <= r["speed"] <= MAX_SPEED
                and r["sport"] != "trail_run"
                for r in rows
            ),
        ),
        (
            "not interval/race/progression (primary)",
            len(select(rows)),
        ),
    ]

    table(steps, headers=["step", "activities"])


# --- ordinary least squares ----------------------------------------------


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination for a small dense system."""
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


def features_linear(row: dict) -> list[float]:
    return [1.0, row["speed"], 1.0 / row["minutes"], row["minutes"]]


def features_speed(row: dict) -> list[float]:
    return [1.0, row["speed"]]


def features_quadratic(row: dict) -> list[float]:
    return [
        1.0,
        row["speed"],
        row["speed"] ** 2,
        1.0 / row["minutes"],
        row["minutes"],
    ]


def fit(rows: list[dict], features=features_linear):
    """Fit ``excess = features · beta``; return coefficients, R², RMSE."""
    width = len(features(rows[0]))
    xtx = [[0.0] * width for _ in range(width)]
    xty = [0.0] * width

    for row in rows:
        x = features(row)
        y = row["excess"]
        for i in range(width):
            xty[i] += x[i] * y
            for j in range(width):
                xtx[i][j] += x[i] * x[j]

    beta = solve(xtx, xty)

    mean_y = sum(row["excess"] for row in rows) / len(rows)
    ss_tot = sum((row["excess"] - mean_y) ** 2 for row in rows)
    ss_res = 0.0

    for row in rows:
        predicted = sum(
            weight * value for weight, value in zip(features(row), beta)
        )
        ss_res += (row["excess"] - predicted) ** 2

    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    rmse = (ss_res / len(rows)) ** 0.5
    return beta, r2, rmse


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap(
    rows: list[dict],
    features=features_linear,
    iterations: int = BOOTSTRAP_ITERATIONS,
):
    """Coefficient confidence intervals by resampling activities."""
    rng = random.Random(SEED)
    count = len(rows)
    width = len(features(rows[0]))
    samples = [[] for _ in range(width)]

    for _ in range(iterations):
        draw = [rows[rng.randrange(count)] for _ in range(count)]
        try:
            beta, _, _ = fit(draw, features)
        except ValueError:
            continue
        for index in range(width):
            samples[index].append(beta[index])

    return [
        (percentile(values, 0.025), percentile(values, 0.975))
        for values in samples
    ]


def correlation(xs: list[float], ys: list[float]) -> float:
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    return cov / (var_x * var_y) ** 0.5 if var_x and var_y else 0.0


# --- reporting ------------------------------------------------------------


def weighted_efficiency(rows: list[dict]) -> float | None:
    distance = sum(row["distance_m"] for row in rows)
    beats = sum(row["excess"] * row["minutes"] for row in rows)
    return distance / beats if beats else None


def bin_rows(rows: list[dict]) -> list[tuple]:
    result = []

    for low, high in BIN_EDGES:
        last = high == BIN_EDGES[-1][1]
        chunk = [
            row
            for row in rows
            if low <= row["minutes"]
            and (row["minutes"] <= high if last else row["minutes"] < high)
        ]
        if not chunk:
            result.append((f"{low}-{high}", 0, None, None, None))
            continue
        result.append(
            (
                f"{low}-{high}",
                len(chunk),
                median(row["minutes"] for row in chunk),
                median(row["speed"] for row in chunk) * 3.6,
                weighted_efficiency(chunk),
            )
        )

    return result


def in_duration_bin(minutes: float, low: float, high: float) -> bool:
    if high == BIN_EDGES[-1][1]:
        return low <= minutes <= high
    return low <= minutes < high


def speed_band_table(rows: list[dict]) -> list[tuple]:
    """Efficiency by duration bin within fixed speed bands."""
    result = []

    for low, high in SPEED_BANDS:
        for dlow, dhigh in BIN_EDGES:
            chunk = [
                row
                for row in rows
                if low <= row["speed"] * 3.6 < high
                and in_duration_bin(row["minutes"], dlow, dhigh)
            ]
            if len(chunk) < 3:
                continue
            result.append(
                (
                    f"{low:.1f}-{high:.1f}" if high < 90 else f"{low:.1f}+",
                    f"{dlow}-{dhigh}",
                    len(chunk),
                    f"{weighted_efficiency(chunk):.2f}",
                )
            )

    return result


def contributions(beta: list[float], speed_ref: float, minutes: float) -> tuple:
    _, b, c, d = beta
    steady = beta[0] + b * speed_ref
    transient = c / minutes
    drift = d * minutes
    excess = steady + transient + drift
    efficiency = 60.0 * speed_ref / excess if excess > 0 else None
    return steady, transient, drift, excess, efficiency


def describe(beta: list[float], speed_ref: float) -> None:
    _, _, c, d = beta

    print(
        f"\nstart-up c = {c:+.1f} bpm*min "
        f"({c / 60:+.1f} bpm at 60 min, {c / 30:+.1f} bpm at 30 min)"
    )
    if c < 0:
        print("  negative: short runs carry fewer excess beats (warm-up dilution)")
    else:
        print(
            "  positive: short runs carry MORE excess HR at the same speed "
            "(no warm-up dilution in session averages)"
        )
    print(
        f"drift     d = {d:+.4f} bpm/min "
        f"({d * 60:+.2f} bpm/h, {d * 120:+.1f} bpm at 120 min)"
    )

    if c > 0 and d > 0:
        crossover = (c / d) ** 0.5
        print(
            f"crossover T* = {crossover:.0f} min "
            "(start-up term and drift balance; efficiency peaks here)"
        )
    elif c < 0 and d > 0:
        crossover = None
        print(
            "no crossover: the start-up term fades while drift grows, "
            "so efficiency falls monotonically with duration"
        )
    else:
        crossover = None
        print("coefficient signs do not describe a transient-plus-drift shape")

    rows = []
    reference = contributions(beta, speed_ref, 60.0)[4]

    for minutes in (30.0, 60.0, 90.0, 120.0, 180.0):
        steady, transient, drift, excess, efficiency = contributions(
            beta, speed_ref, minutes
        )
        bias = (
            (efficiency / reference - 1.0) * 100
            if efficiency is not None and reference
            else None
        )
        rows.append(
            (
                f"{minutes:.0f}",
                f"{steady:.1f}",
                f"{transient:+.1f}",
                f"{drift:+.1f}",
                f"{excess:.1f}",
                f"{efficiency:.2f}" if efficiency is not None else "-",
                f"{bias:+.1f}%" if bias is not None else "-",
            )
        )

    table(
        rows,
        headers=[
            "T min",
            "steady bpm",
            "start-up",
            "drift",
            "excess",
            "eff",
            "vs 60 min",
        ],
    )

    if crossover:
        position = (
            "inside"
            if MIN_DURATION_MIN < crossover < MAX_DURATION_MIN
            else "outside"
        )
        print(
            f"data range is {MIN_DURATION_MIN:.0f}-{MAX_DURATION_MIN:.0f} min; "
            f"crossover {position} it"
        )


def sensitivity(
    rows: list[dict],
    primary: list[dict],
    baseline_180,
) -> None:
    variants = [
        ("primary (steady, no trail)", primary),
        (
            "plus interval/race/progression",
            select(rows, include_intervals=True),
        ),
        ("plus trail", select(rows, include_trail=True)),
        ("cap 180 min", select(rows, max_minutes=180.0)),
        (
            "easy/steady only (non-quality)",
            [
                row
                for row in primary
                if row["methods"] <= {"continuous", "long_run", "strides"}
                and row["targets"] <= {"base", "recovery", "other"}
            ],
        ),
        (
            "exclude recovery target",
            [row for row in primary if "recovery" not in row["targets"]],
        ),
    ]

    # The 180-day resting-HR baseline needs its own rows.
    rows_180 = []
    for row in rows:
        lookup_row = dict(row)
        resting_hr = baseline_180(row["date"])
        if resting_hr is None:
            continue
        lookup_row["rhr"] = resting_hr
        lookup_row["excess"] = row["excess"] + row["rhr"] - resting_hr
        lookup_row["efficiency"] = (
            row["distance_m"] / (lookup_row["excess"] * row["minutes"])
            if lookup_row["excess"] >= MIN_EXCESS_HR
            else None
        )
        rows_180.append(lookup_row)

    variants.append(
        (
            "180-day RHR baseline",
            select(
                [
                    row
                    for row in rows_180
                    if row["excess"] >= MIN_EXCESS_HR
                ]
            ),
        )
    )

    table_rows = []
    for name, chunk in variants:
        chunk = [
            row
            for row in chunk
            if row["excess"] >= MIN_EXCESS_HR and row["efficiency"] is not None
        ]
        if len(chunk) < 30:
            table_rows.append((name, len(chunk), "-", "-", "-", "-"))
            continue
        beta, r2, _ = fit(chunk)
        _, _, c, d = beta
        speed_ref = median(row["speed"] for row in chunk)
        e30 = contributions(beta, speed_ref, 30.0)[4]
        e60 = contributions(beta, speed_ref, 60.0)[4]
        e120 = contributions(beta, speed_ref, 120.0)[4]
        bias_30_60 = (e30 / e60 - 1) * 100 if e30 and e60 else None
        bias_60_120 = (e120 / e60 - 1) * 100 if e120 and e60 else None
        table_rows.append(
            (
                name,
                len(chunk),
                f"{c:+.1f}",
                f"{d:+.4f}",
                f"{bias_30_60:+.1f}%" if bias_30_60 is not None else "-",
                f"{bias_60_120:+.1f}%" if bias_60_120 is not None else "-",
            )
        )

    table(
        table_rows,
        headers=["variant", "n", "c", "d", "30 vs 60", "60 vs 120"],
    )


def _median(values):
    cleaned = [value for value in values if value is not None]
    return median(cleaned) if cleaned else None


def _fmt(value, digits=1):
    return f"{value:.{digits}f}" if value is not None else "-"


def _hour(started_at_utc: str) -> int | None:
    if not started_at_utc:
        return None
    try:
        moment = datetime.fromisoformat(started_at_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.hour


def _group(rows: list[dict], low: float, high: float) -> list[dict]:
    return [row for row in rows if low <= row["minutes"] < high]


def diagnose(primary: list[dict], intervals: list[dict], activities: list) -> None:
    """Characterize the 20-30 min runs against the 30-60 min reference."""
    day_count = Counter(activity.date for activity in activities)
    load_by_date: dict[date, float] = defaultdict(float)
    for activity in activities:
        load_by_date[activity.date] += activity.training_load or 0.0

    short = _group(primary, 20, 30)
    reference = _group(primary, 30, 60)

    table_rows = []

    for label, chunk in (
        ("20-30", short),
        ("30-60", reference),
        ("interval (all)", intervals),
    ):
        quality = [
            is_quality(row["methods"], row["targets"]) for row in chunk
        ]
        known = [value for value in quality if value is not None]
        hours = [_hour(row["started_at_utc"]) for row in chunk]
        known_hours = [hour for hour in hours if hour is not None]
        table_rows.append(
            (
                label,
                len(chunk),
                _fmt(median(row["speed"] * 3.6 for row in chunk), 1),
                _fmt(weighted_efficiency(chunk), 2),
                _fmt(median(row["avg_hr"] for row in chunk), 0),
                _fmt(
                    100 * sum(value is True for value in known) / len(known)
                    if known
                    else None,
                    0,
                ),
                _fmt(_median(row["rpe"] for row in chunk), 1),
                _fmt(_median(row["intensity"] for row in chunk), 2),
                _fmt(
                    _median(
                        row["training_load"] / (row["minutes"] / 60)
                        for row in chunk
                        if row["training_load"] is not None
                    ),
                    0,
                ),
                _fmt(
                    100
                    * sum(day_count[row["date"]] > 1 for row in chunk)
                    / len(chunk),
                    0,
                ),
                _fmt(
                    100
                    * sum(4 <= hour < 9 for hour in known_hours)
                    / len(known_hours)
                    if known_hours
                    else None,
                    0,
                ),
                _fmt(
                    100
                    * sum(5 <= row["date"].month <= 9 for row in chunk)
                    / len(chunk),
                    0,
                ),
            )
        )

    print("\nwhat are the 20-30 min runs?")
    table(
        table_rows,
        headers=[
            "min",
            "n",
            "km/h",
            "eff",
            "HR",
            "quality %",
            "RPE",
            "IF",
            "load/h",
            "double %",
            "morning %",
            "May-Sep %",
        ],
    )

    print("\nefficiency by target and duration:")
    target_rows = []
    for label, low, high in (
        ("20-30", 20, 30),
        ("30-60", 30, 60),
        ("60-120", 60, 120),
        ("120-240", 120, 241),
    ):
        chunk = _group(primary, low, high)
        for target in ("base", "recovery"):
            subset = [row for row in chunk if target in row["targets"]]
            if not subset:
                continue
            target_rows.append(
                (
                    label,
                    target,
                    len(subset),
                    _fmt(median(row["speed"] * 3.6 for row in subset), 1),
                    _fmt(weighted_efficiency(subset), 2),
                    _fmt(median(row["avg_hr"] for row in subset), 0),
                )
            )
    table(
        target_rows,
        headers=["min", "target", "n", "km/h", "eff", "HR"],
    )

    for kind in ("methods", "targets"):
        short_counts = Counter(
            token for row in short for token in (row[kind] or {None})
        )
        ref_counts = Counter(
            token for row in reference for token in (row[kind] or {None})
        )
        int_counts = Counter(
            token for row in intervals for token in (row[kind] or {None})
        )
        tokens = sorted(
            set(short_counts) | set(ref_counts) | set(int_counts),
            key=lambda token: -(
                short_counts[token]
                + ref_counts[token]
                + int_counts[token]
            ),
        )
        table(
            [
                (
                    token or "(none)",
                    short_counts[token],
                    ref_counts[token],
                    int_counts[token],
                )
                for token in tokens
            ],
            headers=[kind[:-1], "20-30", "30-60", "interval"],
        )

    short_tags = Counter(tag for row in short for tag in row["tags"])
    ref_tags = Counter(tag for row in reference for tag in row["tags"])
    tags = sorted(
        set(short_tags) | set(ref_tags),
        key=lambda tag: -(short_tags[tag] + ref_tags[tag]),
    )[:8]
    if tags:
        table(
            [(tag, short_tags[tag], ref_tags[tag]) for tag in tags],
            headers=["tag", "20-30", "30-60"],
        )

    # First-lap behavior: a fast start shows up as a first lap faster than
    # the session and faster than the other laps.
    lap_rows = []
    with create_source() as source:
        for label, chunk in (("20-30", short), ("30-60", reference)):
            ratios = []
            hr_deltas = []
            first_minutes = []
            faster_share = []

            for row in chunk:
                laps = source.activity_laps(row["id"])
                if len(laps) < 2:
                    continue
                first = min(laps, key=lambda lap: lap.index)
                others = [
                    lap
                    for lap in laps
                    if lap.index != first.index
                    and lap.duration_s > 0
                    and lap.distance_m > 0
                ]
                if not (
                    first.duration_s > 0
                    and first.distance_m > 0
                    and first.avg_hr is not None
                    and others
                ):
                    continue

                first_pace = first.duration_s / first.distance_m * 1000
                session_pace = row["minutes"] * 60 / row["distance_m"] * 1000
                ratios.append(first_pace / session_pace)
                hr_deltas.append(first.avg_hr - row["avg_hr"])
                first_minutes.append(first.duration_s / 60.0)
                other_paces = [
                    lap.duration_s / lap.distance_m * 1000 for lap in others
                ]
                faster_share.append(first_pace < median(other_paces))

            lap_rows.append(
                (
                    label,
                    len(ratios),
                    _fmt(_median(first_minutes), 1),
                    _fmt(_median(ratios), 2),
                    _fmt(_median(hr_deltas), 1),
                    _fmt(100 * sum(faster_share) / len(faster_share), 0)
                    if faster_share
                    else "-",
                )
            )

    print("\nfirst-lap behavior (runs with >= 2 laps):")
    table(
        lap_rows,
        headers=[
            "min",
            "n",
            "first lap min",
            "first/session pace",
            "first HR vs session",
            "first faster than other laps %",
        ],
    ),
    print(
        "pace ratio < 1 means the first lap was faster than the session "
        "average; HR delta is first-lap average minus session average."
    )


def month_key(day: date) -> tuple[int, int]:
    return day.year, day.month


def monthly_series(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        groups[month_key(row["date"])].append(row)

    series = []
    for key in sorted(groups):
        chunk = groups[key]
        series.append(
            {
                "key": key,
                "label": f"{key[0]}-{key[1]:02d}",
                "n": len(chunk),
                "rows": chunk,
                "eff": weighted_efficiency(chunk),
                "minutes": median(row["minutes"] for row in chunk),
                "recovery": sum(
                    "recovery" in row["targets"] for row in chunk
                )
                / len(chunk),
            }
        )
    return series


def split_half(series: list[dict], repeats: int = 200) -> float | None:
    """Average correlation of two random halves of each month's runs."""
    rng = random.Random(SEED)
    eligible = [entry for entry in series if entry["n"] >= 6]

    if len(eligible) < 6:
        return None

    values = []

    for _ in range(repeats):
        left = []
        right = []
        for entry in eligible:
            chunk = entry["rows"][:]
            rng.shuffle(chunk)
            half = len(chunk) // 2
            first = weighted_efficiency(chunk[:half])
            second = weighted_efficiency(chunk[half:])
            if first and second:
                left.append(first)
                right.append(second)
        if len(left) >= 6:
            values.append(correlation(left, right))

    return mean(values) if values else None


def series_stats(series: list[dict]) -> dict:
    effs = [entry["eff"] for entry in series]
    diffs = [second - first for first, second in zip(effs, effs[1:])]
    residuals = []

    for index in range(1, len(series) - 1):
        window = series[index - 1 : index + 2]
        pooled = weighted_efficiency(
            [row for entry in window for row in entry["rows"]]
        )
        if pooled:
            residuals.append(series[index]["eff"] - pooled)

    return {
        "months": len(series),
        "eligible": sum(entry["n"] >= 6 for entry in series),
        "n": sum(entry["n"] for entry in series),
        "mean": mean(effs),
        "sd": stdev(effs) if len(effs) > 1 else None,
        "diff_sd": stdev(diffs) if len(diffs) > 1 else None,
        "residual_pct": (
            100 * stdev(residuals) / mean(effs)
            if len(residuals) > 1
            else None
        ),
        "split_half": split_half(series),
        "r_minutes": correlation(
            effs, [entry["minutes"] for entry in series]
        ),
        "r_recovery": correlation(
            effs, [entry["recovery"] for entry in series]
        ),
    }


def yearly_series(rows: list[dict]) -> dict[int, tuple[int, float]]:
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["date"].year].append(row)
    return {
        year: (len(chunk), weighted_efficiency(chunk))
        for year, chunk in groups.items()
    }


def trend_filters(primary: list[dict], intervals: list[dict]) -> None:
    """Compare all steady runs with length/recovery filters over time."""
    variants = [
        (
            "all (20-240)",
            primary,
        ),
        (
            "30-90, with recovery",
            [row for row in primary if 30 <= row["minutes"] <= 90],
        ),
        (
            "no recovery (20-240)",
            [row for row in primary if "recovery" not in row["targets"]],
        ),
        (
            "30-90, no recovery",
            [
                row
                for row in primary
                if 30 <= row["minutes"] <= 90
                and "recovery" not in row["targets"]
            ],
        ),
        (
            "30-120, no recovery",
            [
                row
                for row in primary
                if 30 <= row["minutes"] <= 120
                and "recovery" not in row["targets"]
            ],
        ),
        ("interval (overall)", intervals),
        ("steady + intervals", primary + intervals),
    ]

    summary = []
    for name, chunk in variants:
        series = monthly_series(chunk)
        stats = series_stats(series)
        summary.append(
            (
                name,
                stats["n"],
                stats["months"],
                stats["eligible"],
                _fmt(stats["mean"], 2),
                _fmt(stats["sd"], 3),
                _fmt(stats["diff_sd"], 3),
                _fmt(stats["residual_pct"], 1),
                _fmt(stats["split_half"], 2),
                _fmt(stats["r_minutes"], 2),
                _fmt(stats["r_recovery"], 2),
            )
        )

    table(
        summary,
        headers=[
            "population",
            "n",
            "months",
            "months >= 6",
            "eff mean",
            "monthly SD",
            "Δ SD",
            "resid %",
            "split-half r",
            "r(duration)",
            "r(recovery)",
        ],
    )
    print(
        "lower SD / Δ SD / residual % means a smoother series; higher "
        "split-half r means the monthly values are more reliable; "
        "correlations near 0 mean less composition leakage."
    )

    years = sorted(
        {row["date"].year for row in primary}
    )
    year_rows = []
    for name, chunk in variants:
        yearly = yearly_series(chunk)
        year_rows.append(
            (
                name,
                *[
                    (
                        f"{yearly[year][1]:.2f} ({yearly[year][0]})"
                        if year in yearly
                        else "-"
                    )
                    for year in years
                ],
            )
        )
    table(
        year_rows,
        headers=["population", *[str(year) for year in years]],
    )
    print(
        "year cells are weighted efficiency with the run count in "
        "parentheses."
    )

    figure = go.Figure()
    colors = ["#4c78a8", "#f58518", "#e45756", "#54a24b", "#b279a2"]

    for index, (name, chunk) in enumerate(variants):
        series = monthly_series(chunk)
        figure.add_trace(
            go.Scatter(
                x=[
                    datetime(entry["key"][0], entry["key"][1], 15)
                    for entry in series
                ],
                y=[entry["eff"] for entry in series],
                mode="lines+markers",
                name=f"{name} (n={len(chunk)})",
                line={"color": colors[index % len(colors)], "width": 1.5},
                marker={"size": 4},
            )
        )

    figure.update_yaxes(title_text="efficiency (m/excess beat)")
    figure.update_xaxes(title_text="month")
    figure.update_layout(
        title="Monthly efficiency under different filters",
        legend={"orientation": "h", "y": -0.25},
    )
    save(figure, "efficiency-trend-filters")


def plot_efficiency(rows: list[dict], beta: list[float]) -> None:
    speed_ref = median(row["speed"] for row in rows)
    points = [row for row in rows if row["efficiency"] is not None]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[row["minutes"] for row in points],
            y=[row["efficiency"] for row in points],
            mode="markers",
            marker={"size": 4, "opacity": 0.25, "color": "#4c78a8"},
            name="runs",
        )
    )

    binned = [row for row in bin_rows(rows) if row[1] and row[4]]
    figure.add_trace(
        go.Scatter(
            x=[row[2] for row in binned],
            y=[row[4] for row in binned],
            mode="lines+markers",
            line={"color": "#e45756", "width": 2},
            marker={"size": 7},
            name="weighted by duration bin",
        )
    )

    grid = [
        MIN_DURATION_MIN + (MAX_DURATION_MIN - MIN_DURATION_MIN) * i / 200
        for i in range(201)
    ]
    predicted = [contributions(beta, speed_ref, t)[4] for t in grid]
    figure.add_trace(
        go.Scatter(
            x=grid,
            y=predicted,
            mode="lines",
            line={"color": "#54a24b", "width": 2, "dash": "dash"},
            name=f"model at {speed_ref * 3.6:.1f} km/h",
        )
    )

    figure.update_xaxes(type="log", title_text="duration (min, log scale)")
    figure.update_yaxes(title_text="efficiency (m/excess beat)")
    figure.update_layout(
        title="Session efficiency vs duration",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "efficiency-duration")


def plot_contributions(beta: list[float]) -> None:
    grid = [
        MIN_DURATION_MIN + (MAX_DURATION_MIN - MIN_DURATION_MIN) * i / 200
        for i in range(201)
    ]
    transient = [beta[2] / t for t in grid]
    drift = [beta[3] * t for t in grid]
    total = [a + b for a, b in zip(transient, drift)]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=grid,
            y=transient,
            mode="lines",
            name="start-up term (c/T)",
            line={"color": "#4c78a8"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=grid,
            y=drift,
            mode="lines",
            name="cardiac drift (d·T)",
            line={"color": "#e45756"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=grid,
            y=total,
            mode="lines",
            name="net effect on avg HR",
            line={"color": "#333333", "width": 2},
        )
    )
    figure.add_hline(y=0, line={"color": "#999999", "width": 1})
    figure.update_xaxes(title_text="duration (min)")
    figure.update_yaxes(title_text="effect on average HR (bpm)")
    figure.update_layout(
        title="Transient vs drift over the session",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "efficiency-duration-effects")


def main() -> None:
    with create_source() as source:
        activities = source.activities(date(2000, 1, 1), date.today())
        wellness = source.wellness(date(1999, 1, 1), date.today())

    baseline = resting_hr_baselines(wellness)
    rows = build_rows(activities, baseline)
    primary = select(rows)
    interval_sessions = select(rows, intervals_only=True)
    print(
        f"{len(activities)} activities, {len(wellness)} wellness days; "
        f"{len(rows)} runs with HR, time, distance and an RHR baseline"
    )
    print(
        f"populations: {len(primary)} steady runs, "
        f"{len(interval_sessions)} interval/race/progression sessions (overall)"
    )

    funnel(rows)

    if len(primary) < 100:
        print(f"only {len(primary)} usable runs; need at least 100")
        return

    by_year: dict[int, int] = {}
    for row in primary:
        by_year[row["date"].year] = by_year.get(row["date"].year, 0) + 1
    table(
        [(year, count) for year, count in sorted(by_year.items())],
        headers=["year", "runs"],
    )

    print("\nefficiency by duration bin (weighted sum(distance)/sum(beats)):")
    table(
        [
            (
                label,
                count,
                f"{median_minutes:.0f}" if median_minutes else "-",
                f"{kmh:.1f}" if kmh else "-",
                f"{efficiency:.2f}" if efficiency else "-",
            )
            for label, count, median_minutes, kmh, efficiency in bin_rows(primary)
        ],
        headers=["min", "n", "median", "km/h", "efficiency"],
    )

    print("\nsame, within fixed speed bands:")
    table(
        speed_band_table(primary),
        headers=["km/h", "min", "n", "efficiency"],
    )

    print("\ninterval/race/progression sessions (overall averages):")
    table(
        [
            (
                label,
                count,
                f"{median_minutes:.0f}" if median_minutes else "-",
                f"{kmh:.1f}" if kmh else "-",
                f"{efficiency:.2f}" if efficiency else "-",
            )
            for label, count, median_minutes, kmh, efficiency in bin_rows(
                interval_sessions
            )
        ],
        headers=["min", "n", "median", "km/h", "efficiency"],
    )

    print("\npredictor correlations (collinearity check):")
    speeds = [row["speed"] for row in primary]
    inverse = [1.0 / row["minutes"] for row in primary]
    minutes = [row["minutes"] for row in primary]
    table(
        [
            ("speed vs 1/T", f"{correlation(speeds, inverse):+.2f}"),
            ("speed vs T", f"{correlation(speeds, minutes):+.2f}"),
            ("1/T vs T", f"{correlation(inverse, minutes):+.2f}"),
        ],
        headers=["pair", "r"],
    )

    beta, r2, rmse = fit(primary)
    intervals = bootstrap(primary)
    speed_ref = median(speeds)

    print(
        f"\nOLS on {len(primary)} runs: R² {r2:.3f}, RMSE {rmse:.1f} bpm; "
        f"reference speed {speed_ref * 3.6:.1f} km/h"
    )
    table(
        [
            (
                "a (bpm)",
                f"{beta[0]:+.1f}",
                f"[{intervals[0][0]:+.1f}, {intervals[0][1]:+.1f}]",
            ),
            (
                "b (bpm per m/s)",
                f"{beta[1]:+.1f}",
                f"[{intervals[1][0]:+.1f}, {intervals[1][1]:+.1f}]",
            ),
            (
                "c (bpm*min)",
                f"{beta[2]:+.1f}",
                f"[{intervals[2][0]:+.1f}, {intervals[2][1]:+.1f}]",
            ),
            (
                "d (bpm/min)",
                f"{beta[3]:+.4f}",
                f"[{intervals[3][0]:+.4f}, {intervals[3][1]:+.4f}]",
            ),
        ],
        headers=["term", "estimate", "95% bootstrap CI"],
    )

    describe(beta, speed_ref)

    print("\nduration model by population:")
    population_rows = []
    for name, chunk in (
        ("steady", primary),
        ("interval (overall)", interval_sessions),
        ("combined", primary + interval_sessions),
    ):
        if len(chunk) < 30:
            population_rows.append((name, len(chunk), "-", "-", "-", "-", "-"))
            continue
        population_beta, population_r2, _ = fit(chunk)
        _, _, c, d = population_beta
        population_speed = median(row["speed"] for row in chunk)
        e30 = contributions(population_beta, population_speed, 30.0)[4]
        e60 = contributions(population_beta, population_speed, 60.0)[4]
        e120 = contributions(population_beta, population_speed, 120.0)[4]
        population_rows.append(
            (
                name,
                len(chunk),
                f"{population_r2:.3f}",
                f"{c:+.1f}",
                f"{d:+.4f}",
                f"{(e30 / e60 - 1) * 100:+.1f}%"
                if e30 and e60
                else "-",
                f"{(e120 / e60 - 1) * 100:+.1f}%"
                if e120 and e60
                else "-",
            )
        )
    table(
        population_rows,
        headers=["population", "n", "R²", "c", "d", "30 vs 60", "60 vs 120"],
    )
    print(
        "interval sessions are not steady; their model fit is descriptive, "
        "not a steady-state claim. They have almost no data beyond 90 min, "
        "so 60 vs 120 there is an extrapolation."
    )

    print("\nmodel comparison (does the duration shape survive curvature?):")
    r2_speed = fit(primary, features_speed)[1]
    beta_quad, r2_quad, _ = fit(primary, features_quadratic)
    table(
        [
            ("speed only", f"{r2_speed:.3f}", "-", "-"),
            (
                "speed + 1/T + T",
                f"{r2:.3f}",
                f"{beta[2]:+.1f}",
                f"{beta[3]:+.4f}",
            ),
            (
                "speed + speed² + 1/T + T",
                f"{r2_quad:.3f}",
                f"{beta_quad[3]:+.1f}",
                f"{beta_quad[4]:+.4f}",
            ),
        ],
        headers=["model", "R²", "c", "d"],
    )

    print("\nsensitivity:")
    baseline_180 = resting_hr_baselines(wellness, window_days=180)
    sensitivity(rows, primary, baseline_180)

    diagnose(primary, interval_sessions, activities)

    print("\ndoes filtering make the evolution more consistent?")
    trend_filters(primary, interval_sessions)

    plot_efficiency(primary, beta)
    plot_contributions(beta)


if __name__ == "__main__":
    main()
