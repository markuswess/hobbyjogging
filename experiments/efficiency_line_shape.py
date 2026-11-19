"""Experiment: is the HR-speed efficiency line linear, and what tightens it?

Questions
---------
1. Is `HR = RHR + v*60/E` (linear through resting HR) adequate, or does a
   quadratic, log or piecewise curve fit better out of sample?
2. How much of the scatter is explained by duration, workout quality, trail,
   elevation and temperature when only session averages are used?

Data
----
One row per run with average HR, distance, time and a resting-HR baseline.
Weather is the canonical `activity_weather.temp_c` (temperature only; humidity
and wind are empty). Elevation comes from the canonical `activities` columns;
the Activity model does not expose them yet, so the experiment reads them from
the same connection. Workout classification uses the stored method/target sets,
not the heuristic.

Classification caution
----------------------
Continuous-run classification is not perfect. The experiment therefore builds
three populations: all runs, a conservative steady band (40-75 min, no quality
method/target), and a strict band (also drops unclassified runs and suspicious
names such as tempo/threshold/subT). Conclusions must hold across them.

Models
------
- current: HR = RHR + b*v (no free intercept)
- linear:  HR = a + b*v
- quadratic: HR = a + b*v + c*v²
- log: HR = a + b*ln(v)
- piecewise: HR = a + b*v + c*max(0, v-knot)

Comparison uses R², RMSE, AIC/BIC and 5-fold time-based cross-validation.
Controls are added in blocks on the same complete-case rows: session
(duration, quality, unclassified, trail), terrain (gain/loss per km), weather
(temperature), time (year).

Decision
--------
- Curvature matters if the quadratic term's bootstrap CI excludes zero and
  time-CV RMSE improves by at least ~0.2 bpm.
- Controls matter if they cut CV RMSE by at least ~0.5 bpm or lift R² by 0.05
  on the same rows.
- If the conclusion changes between the conservative and strict populations,
  classification uncertainty is the limiting factor, not the model.

    uv run --env-file .env python experiments/efficiency_line_shape.py
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median

import plotly.graph_objects as go

from hobbyjogging_core.workouts import is_quality
from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    MIN_EXCESS_HR,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_SPEED = 1.5
MAX_SPEED = 6.0
STEADY_MIN = 40.0
STEADY_MAX = 75.0
CV_FOLDS = 5
BOOTSTRAP = 400
SEED = 17
QUALITY_METHODS = {"intervals", "race", "progression", "long_run", "fartlek"}
QUALITY_TARGETS = {
    "lt1",
    "subthreshold",
    "threshold",
    "vo2max",
    "speed",
    "marathon",
}
SUSPICIOUS_WORDS = (
    "tempo",
    "threshold",
    "schwelle",
    "subt",
    "lt1",
    "race",
    "interval",
    "fartlek",
    "wettkampf",
)


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


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_rows(source, activities, baseline) -> list[dict]:
    rows = []

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue
        if activity.duration_s <= 0 or activity.distance_m <= 0:
            continue
        if activity.avg_hr is None:
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

        minutes = activity.duration_s / 60.0
        km = activity.distance_m / 1000.0
        gain = activity.elevation_gain_m
        loss = activity.elevation_loss_m
        weather = source.activity_weather(activity.id)
        temp = weather.temp_c if weather is not None else None

        methods = set(activity.workout_methods)
        targets = set(activity.workout_targets)
        quality = is_quality(methods, targets)
        unclassified = not methods and not targets
        text = activity.name.lower()

        rows.append(
            {
                "id": activity.id,
                "date": activity.date,
                "year": activity.date.year,
                "name": activity.name,
                "sport": activity.type,
                "trail": activity.type == "trail_run",
                "speed": speed,
                "hr": activity.avg_hr,
                "rhr": resting_hr,
                "excess": excess,
                "minutes": minutes,
                "km": km,
                "gain_per_km": gain / km if gain is not None and km else None,
                "loss_per_km": loss / km if loss is not None and km else None,
                "temp": temp,
                "quality": quality,
                "unclassified": unclassified,
                "suspicious": any(word in text for word in SUSPICIOUS_WORDS),
                "quality_method": bool(methods & QUALITY_METHODS),
                "quality_target": bool(targets & QUALITY_TARGETS),
            }
        )

    return rows


def population(rows: list[dict], kind: str) -> list[dict]:
    if kind == "all":
        return rows

    steady = [
        row
        for row in rows
        if STEADY_MIN <= row["minutes"] <= STEADY_MAX
        and not row["quality_method"]
        and not row["quality_target"]
    ]

    if kind == "strict":
        return [
            row
            for row in steady
            if not row["unclassified"] and not row["suspicious"]
        ]

    return steady


# --- models ---------------------------------------------------------------


def fit_current(rows: list[dict]) -> dict:
    numerator = sum(row["excess"] * row["speed"] for row in rows)
    denominator = sum(row["speed"] ** 2 for row in rows)
    slope = numerator / denominator if denominator else 0.0
    predictions = [row["rhr"] + slope * row["speed"] for row in rows]
    return metrics(rows, predictions, 1)


def fit_offset(rows: list[dict], features) -> tuple[dict, list[float]]:
    """Fit HR - RHR = features · beta; the current line plus controls."""
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
    predictions = [
        row["rhr"]
        + sum(weight * value for weight, value in zip(features(row), beta))
        for row in rows
    ]
    return metrics(rows, predictions, width), beta


def fit_ols(rows: list[dict], features) -> tuple[dict, list[float]]:
    width = len(features(rows[0]))
    xtx = [[0.0] * width for _ in range(width)]
    xty = [0.0] * width

    for row in rows:
        x = features(row)
        y = row["hr"]
        for i in range(width):
            xty[i] += x[i] * y
            for j in range(width):
                xtx[i][j] += x[i] * x[j]

    beta = solve(xtx, xty)
    predictions = [
        sum(weight * value for weight, value in zip(features(row), beta))
        for row in rows
    ]
    return metrics(rows, predictions, width), beta


def metrics(rows: list[dict], predictions: list[float], parameters: int) -> dict:
    residuals = [
        row["hr"] - prediction for row, prediction in zip(rows, predictions)
    ]
    sse = sum(residual ** 2 for residual in residuals)
    count = len(rows)
    mean_hr = mean(row["hr"] for row in rows)
    ss_tot = sum((row["hr"] - mean_hr) ** 2 for row in rows)
    r2 = 1 - sse / ss_tot if ss_tot else 0.0
    rmse = (sse / count) ** 0.5 if count else 0.0
    aic = count * math.log(sse / count) + 2 * parameters if sse else 0.0
    bic = count * math.log(sse / count) + parameters * math.log(count) if sse else 0.0
    return {
        "n": count,
        "r2": r2,
        "rmse": rmse,
        "aic": aic,
        "bic": bic,
        "parameters": parameters,
        "residuals": residuals,
    }


def features_linear(row: dict) -> list[float]:
    return [1.0, row["speed"]]


def features_offset_quadratic(row: dict) -> list[float]:
    return [row["speed"], row["speed"] ** 2]


def features_quadratic(row: dict) -> list[float]:
    return [1.0, row["speed"], row["speed"] ** 2]


def features_log(row: dict) -> list[float]:
    return [1.0, math.log(row["speed"])]


def features_piecewise(row: dict, knot: float) -> list[float]:
    return [1.0, row["speed"], max(0.0, row["speed"] - knot)]


def time_folds(rows: list[dict], folds: int = CV_FOLDS) -> list[list[dict]]:
    ordered = sorted(rows, key=lambda row: (row["date"], row["id"]))
    size = len(ordered) // folds
    if size == 0:
        return [ordered]
    chunks = [
        ordered[index * size : (index + 1) * size] for index in range(folds)
    ]
    chunks[-1].extend(ordered[folds * size :])
    return chunks


def cv_rmse(rows: list[dict], fitter) -> float:
    folds = time_folds(rows)
    errors = []

    for index, test in enumerate(folds):
        train = [
            row
            for other, chunk in enumerate(folds)
            if other != index
            for row in chunk
        ]
        if not train or not test:
            continue
        try:
            predictions = fitter(train, test)
        except ValueError:
            continue
        errors.extend(
            (row["hr"] - prediction) ** 2
            for row, prediction in zip(test, predictions)
        )

    return (sum(errors) / len(errors)) ** 0.5 if errors else float("nan")


def predict_current(train: list[dict], test: list[dict]) -> list[float]:
    numerator = sum(row["excess"] * row["speed"] for row in train)
    denominator = sum(row["speed"] ** 2 for row in train)
    slope = numerator / denominator if denominator else 0.0
    return [row["rhr"] + slope * row["speed"] for row in test]


def ols_predictor(features):
    def predict(train: list[dict], test: list[dict]) -> list[float]:
        _, beta = fit_ols(train, features)
        return [
            sum(weight * value for weight, value in zip(features(row), beta))
            for row in test
        ]

    return predict


def show_model_comparison(rows: list[dict], knot: float) -> None:
    models = [
        ("current (through RHR)", fit_current(rows), predict_current),
        (
            "current + v²",
            fit_offset(rows, features_offset_quadratic)[0],
            offset_predictor(features_offset_quadratic),
        ),
        (
            "free linear",
            fit_ols(rows, features_linear)[0],
            ols_predictor(features_linear),
        ),
        (
            "quadratic",
            fit_ols(rows, features_quadratic)[0],
            ols_predictor(features_quadratic),
        ),
        (
            "log speed",
            fit_ols(rows, features_log)[0],
            ols_predictor(features_log),
        ),
        (
            "piecewise",
            fit_ols(
                rows, lambda row: features_piecewise(row, knot)
            )[0],
            ols_predictor(lambda row: features_piecewise(row, knot)),
        ),
    ]

    print(f"\nmodel comparison (n={len(rows)}, knot={knot:.2f} m/s):")
    table(
        [
            (
                name,
                result["n"],
                f"{result['r2']:.3f}",
                f"{result['rmse']:.2f}",
                f"{result['aic']:.0f}",
                f"{result['bic']:.0f}",
                f"{cv_rmse(rows, predictor):.2f}",
            )
            for name, result, predictor in models
        ],
        headers=["model", "n", "R²", "RMSE bpm", "AIC", "BIC", "time-CV RMSE"],
    )


def curvature(rows: list[dict]) -> None:
    _, beta = fit_offset(rows, features_offset_quadratic)
    coefficient = beta[1]
    rng = random.Random(SEED)
    samples = []

    for _ in range(BOOTSTRAP):
        draw = [rows[rng.randrange(len(rows))] for _ in range(len(rows))]
        try:
            _, sample = fit_offset(draw, features_offset_quadratic)
        except ValueError:
            continue
        samples.append(sample[1])

    low, high = (
        percentile(samples, 0.025),
        percentile(samples, 0.975),
    ) if samples else (None, None)
    print(
        f"quadratic coefficient c: {coefficient:+.4f} bpm/(m/s)² "
        f"(95% bootstrap {low:+.4f}..{high:+.4f})"
        if low is not None
        else f"quadratic coefficient c: {coefficient:+.4f}"
    )


def control_offset_features(level: str):
    def features(row: dict) -> list[float]:
        values = [row["speed"]]
        if level == "base":
            return values
        values += [
            row["minutes"] - 57.5,
            1.0
            if row["quality"] is True
            else (-1.0 if row["quality"] is None else 0.0),
            1.0 if row["trail"] else 0.0,
        ]
        if level == "session":
            return values
        values += [row["gain_per_km"], row["loss_per_km"]]
        if level == "terrain":
            return values
        values.append(row["temp"])
        if level == "weather":
            return values
        values.append(row["year"] - 2018)
        return values

    return features


def offset_predictor(features):
    def predict(train: list[dict], test: list[dict]) -> list[float]:
        _, beta = fit_offset(train, features)
        return [
            row["rhr"]
            + sum(weight * value for weight, value in zip(features(row), beta))
            for row in test
        ]

    return predict


def features_offset_elevation(row: dict) -> list[float]:
    return [row["speed"], row["gain_per_km"], row["loss_per_km"]]


def features_offset_curv_elevation(row: dict) -> list[float]:
    return [
        row["speed"],
        row["speed"] ** 2,
        row["gain_per_km"],
        row["loss_per_km"],
    ]


def terrain_class(row: dict) -> str:
    gain = row["gain_per_km"]
    if gain is None:
        return "unknown"
    if gain < 5:
        return "flat"
    if gain < 10:
        return "rolling"
    return "hilly"


def show_elevation_models(rows: list[dict]) -> None:
    complete = [
        row
        for row in rows
        if row["gain_per_km"] is not None
        and row["loss_per_km"] is not None
    ]
    if len(complete) < 50:
        print("not enough steady rows with elevation")
        return

    models = [
        ("current (speed)", lambda row: [row["speed"]]),
        (
            "current + elevation",
            features_offset_elevation,
        ),
        (
            "current + v²",
            lambda row: [row["speed"], row["speed"] ** 2],
        ),
        (
            "current + v² + elevation",
            features_offset_curv_elevation,
        ),
    ]

    print(f"\nsteady elevation models (complete cases n={len(complete)}):")
    table(
        [
            (
                label,
                result["n"],
                f"{result['r2']:.3f}",
                f"{result['rmse']:.2f}",
                f"{cv_rmse(complete, offset_predictor(features)):.2f}",
            )
            for label, features in models
            for result, _ in [fit_offset(complete, features)]
        ],
        headers=["model", "n", "R²", "RMSE bpm", "time-CV RMSE"],
    )


def show_terrain(rows: list[dict]) -> None:
    complete = [
        row
        for row in rows
        if row["gain_per_km"] is not None
        and row["loss_per_km"] is not None
    ]
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in complete:
        groups[terrain_class(row)].append(row)

    print("\ncurrent line by terrain class:")
    table(
        [
            (
                name,
                len(chunk),
                f"{median(row['gain_per_km'] for row in chunk):.1f}",
                f"{median(row['loss_per_km'] for row in chunk):.1f}",
                f"{fit_offset(chunk, lambda row: [row['speed']])[1][0]:.2f}",
                f"{fit_offset(chunk, lambda row: [row['speed']])[0]['rmse']:.2f}",
            )
            for name, chunk in sorted(groups.items())
        ],
        headers=["terrain", "runs", "gain/km", "loss/km", "slope b", "RMSE"],
    )


def plot_terrain(rows: list[dict]) -> None:
    complete = [
        row
        for row in rows
        if row["gain_per_km"] is not None
        and row["loss_per_km"] is not None
    ]
    if len(complete) < 50:
        return

    _, beta = fit_offset(complete, lambda row: [row["speed"]])
    slope = beta[0]
    for row in complete:
        row["residual"] = row["hr"] - (row["rhr"] + slope * row["speed"])

    colors = {"flat": "#4c78a8", "rolling": "#f58518", "hilly": "#e45756"}
    figure = go.Figure()
    for name, color in colors.items():
        chunk = [row for row in complete if terrain_class(row) == name]
        if not chunk:
            continue
        figure.add_trace(
            go.Scatter(
                x=[row["gain_per_km"] for row in chunk],
                y=[row["residual"] for row in chunk],
                mode="markers",
                marker={"size": 6, "opacity": 0.6, "color": color},
                name=name,
            )
        )

    figure.add_hline(y=0, line={"color": "#999999", "width": 1})
    figure.update_xaxes(title_text="elevation gain (m/km)")
    figure.update_yaxes(title_text="HR residual from the current line (bpm)")
    figure.update_layout(
        title="Does elevation explain the remaining HR scatter?",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "efficiency-line-terrain")


def show_controls(rows: list[dict]) -> None:
    complete = [
        row
        for row in rows
        if row["gain_per_km"] is not None
        and row["loss_per_km"] is not None
        and row["temp"] is not None
    ]

    print(
        f"\nincremental controls on the current through-RHR line "
        f"(complete cases n={len(complete)}):"
    )
    rows_out = []
    base_cv = None

    for level, label in (
        ("base", "current line (speed)"),
        ("session", "+ duration/quality/trail"),
        ("terrain", "+ elevation"),
        ("weather", "+ temperature"),
        ("time", "+ year"),
    ):
        features = control_offset_features(level)
        result, _ = fit_offset(complete, features)
        cv = cv_rmse(complete, offset_predictor(features))
        if base_cv is None:
            base_cv = cv
        rows_out.append(
            (
                label,
                result["n"],
                f"{result['r2']:.3f}",
                f"{result['rmse']:.2f}",
                f"{cv:.2f}",
                f"{cv - base_cv:+.2f}" if base_cv is not None else "-",
            )
        )

    table(
        rows_out,
        headers=[
            "block",
            "n",
            "R²",
            "RMSE bpm",
            "time-CV RMSE",
            "Δ CV",
        ],
    )


def collinearity(rows: list[dict]) -> None:
    columns = [
        ("speed", [row["speed"] for row in rows]),
        ("duration", [row["minutes"] for row in rows]),
        ("gain/km", [row["gain_per_km"] for row in rows]),
        ("loss/km", [row["loss_per_km"] for row in rows]),
        ("temp", [row["temp"] for row in rows]),
        ("year", [float(row["year"]) for row in rows]),
    ]
    complete = [
        index
        for index in range(len(rows))
        if all(column[1][index] is not None for column in columns)
    ]
    values = [
        (name, [values_list[index] for index in complete])
        for name, values_list in columns
    ]

    def corr(xs, ys):
        mx = mean(xs)
        my = mean(ys)
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        return cov / (vx * vy) ** 0.5 if vx and vy else 0.0

    print(f"\npredictor correlations (n={len(complete)}):")
    table(
        [
            (
                first,
                second,
                f"{corr(a, b):+.2f}",
            )
            for i, (first, a) in enumerate(values)
            for second, b in values[i + 1 :]
        ],
        headers=["pair", "", "r"],
    )


def plot_curves(rows: list[dict]) -> None:
    if not rows:
        return

    bins: dict[float, list[dict]] = defaultdict(list)
    for row in rows:
        bins[round(row["speed"] * 4) / 4].append(row)

    binned_x = sorted(bins)
    binned_y = [mean(row["hr"] for row in bins[x]) for x in binned_x]
    binned_n = [len(bins[x]) for x in binned_x]

    _, linear = fit_ols(rows, features_linear)
    _, quadratic = fit_ols(rows, features_quadratic)
    grid = [1.5 + 4.5 * i / 200 for i in range(201)]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=binned_x,
            y=binned_y,
            mode="markers",
            marker={"size": [max(4, min(12, n / 10)) for n in binned_n]},
            name="binned mean",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=grid,
            y=[linear[0] + linear[1] * x for x in grid],
            mode="lines",
            line={"color": "#4c78a8", "width": 2},
            name="free linear",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=grid,
            y=[
                quadratic[0] + quadratic[1] * x + quadratic[2] * x * x
                for x in grid
            ],
            mode="lines",
            line={"color": "#e45756", "width": 2, "dash": "dash"},
            name="quadratic",
        )
    )
    figure.update_xaxes(title_text="speed (m/s)")
    figure.update_yaxes(title_text="average HR (bpm)")
    figure.update_layout(
        title="HR vs speed: linear or curved?",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "efficiency-line-shape")


def plot_controls(rows: list[dict]) -> None:
    complete = [
        row
        for row in rows
        if row["gain_per_km"] is not None
        and row["loss_per_km"] is not None
        and row["temp"] is not None
    ]
    labels = []
    values = []
    for level, label in (
        ("base", "speed"),
        ("session", "+session"),
        ("terrain", "+terrain"),
        ("weather", "+weather"),
        ("time", "+time"),
    ):
        features = control_offset_features(level)
        labels.append(label)
        values.append(cv_rmse(complete, offset_predictor(features)))

    figure = go.Figure(
        go.Bar(x=labels, y=values, marker={"color": "#4c78a8"})
    )
    figure.update_yaxes(title_text="time-CV RMSE (bpm)")
    figure.update_xaxes(title_text="control block")
    figure.update_layout(title="Scatter left after each control block")
    save(figure, "efficiency-line-controls")


def main() -> None:
    with create_source() as source:
        activities = source.activities(date(2000, 1, 1), date.today())
        wellness = source.wellness(date(1999, 1, 1), date.today())
        rows = build_rows(source, activities, resting_hr_baselines(wellness))

    print(
        f"{len(rows)} runs with HR, speed and RHR; "
        f"{sum(row['temp'] is not None for row in rows)} with temperature, "
        f"{sum(row['gain_per_km'] is not None for row in rows)} with elevation"
    )

    for kind in ("all", "steady", "strict"):
        chunk = population(rows, kind)
        print(
            f"{kind}: n={len(chunk)}, "
            f"unclassified={sum(row['unclassified'] for row in chunk)}, "
            f"quality={sum(row['quality'] is True for row in chunk)}, "
            f"trail={sum(row['trail'] for row in chunk)}"
        )

    steady = population(rows, "steady")
    strict = population(rows, "strict")
    if len(steady) < 100:
        print("not enough steady runs")
        return

    knot = median(row["speed"] for row in steady)
    print("\nsteady population:")
    show_model_comparison(steady, knot)
    curvature(steady)

    print("\nstrict population (classification-suspicious rows removed):")
    show_model_comparison(strict, knot)
    curvature(strict)

    print("\nall runs:")
    show_model_comparison(rows, knot)

    show_controls(rows)
    collinearity(rows)
    show_elevation_models(steady)
    show_terrain(steady)

    plot_curves(steady)
    plot_controls(rows)
    plot_terrain(steady)


if __name__ == "__main__":
    main()
