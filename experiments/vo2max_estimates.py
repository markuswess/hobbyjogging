"""Experiment: Garmin vs Runalyze VO2max and a session-level estimate.

Question
--------
Garmin's `vo2max_garmin` looks like a smoothed, history-aware value, while
Runalyze's effective `vo2max_runalyze` moves almost every run. Can we derive a
comparable metric from the available session data (pace, HR, RHR, max HR)
without streams?

Definitions
-----------
- ACSM running oxygen cost: ``VO2 = 3.5 + 0.2 * speed_m_min``.
- HR/HRmax fraction: ``HR / max_HR``.
- HR-reserve fraction: ``(HR - RHR) / (max_HR - RHR)``.
- Estimated effective VO2max = oxygen cost / fraction. Guarded to a
  physiological fraction range.
- Max HR is the latest running threshold snapshot (192), not the noisy
  per-activity max; sensitivity uses the activity max HR.

Comparisons
-----------
- Coverage and levels of Garmin, Runalyze and both estimates.
- Garmin/Runalyze change frequency (the smoothing check).
- Correlations and RMSE, raw and over rolling 7/14/28/42/90/182-day windows.
- Smoothing/lag validation against race VDOT (rolling means vs EWMAs).
- Yearly means and plots.

    uv run --env-file .env python experiments/vo2max_estimates.py
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    MIN_EXCESS_HR,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.series import alpha_from_time_constant, date_range, ewma
from hobbyjogging_report.sources import create_source

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
WINDOWS = (7, 14, 28, 42, 90, 182)
SMOOTH_WINDOWS = (14, 28, 42, 63, 90, 182)
SMOOTH_LAGS = (0, 7, 14, 21, 28, 42, 56, 90)


def correlation(xs: list[float], ys: list[float]) -> float:
    mx = mean(xs)
    my = mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return cov / (vx * vy) ** 0.5 if vx and vy else 0.0


def threshold_max_hr(thresholds, day: date) -> float | None:
    runs = [
        threshold
        for threshold in thresholds
        if threshold.sport == "run" and threshold.max_hr
    ]
    if not runs:
        return None
    runs.sort(key=lambda threshold: threshold.effective_from)
    current = None
    for threshold in runs:
        if threshold.effective_from <= day:
            current = threshold.max_hr
        else:
            break
    return current or runs[0].max_hr


def effective_vo2max(
    speed_m_min: float,
    avg_hr: float,
    resting_hr: float | None,
    max_hr: float,
    use_activity_max: float | None = None,
) -> dict[str, float | None]:
    oxygen = 3.5 + 0.2 * speed_m_min
    fraction_hr = avg_hr / max_hr if max_hr else None
    fraction_reserve = None
    if resting_hr is not None and max_hr:
        reserve = max_hr - resting_hr
        if reserve > 0:
            fraction_reserve = (avg_hr - resting_hr) / reserve

    def estimate(fraction):
        if fraction is None or not (0.5 <= fraction <= 0.95):
            return None
        return oxygen / fraction

    result = {
        "estimate_hr": estimate(fraction_hr),
        "estimate_reserve": estimate(fraction_reserve),
    }

    if (
        use_activity_max
        and use_activity_max > 0
        and resting_hr is not None
        and use_activity_max > resting_hr
    ):
        result["estimate_activity_max"] = estimate(
            (avg_hr - resting_hr) / (use_activity_max - resting_hr)
        )
    else:
        result["estimate_activity_max"] = None

    return result


def build_rows(
    source,
    *,
    steady_only: bool = True,
) -> tuple[list[dict], list[str]]:
    activities = source.activities(date(2000, 1, 1), date.today())
    wellness = source.wellness(date(1999, 1, 1), date.today())
    thresholds = source.athlete_thresholds()
    devices = {
        device.id: device.product or device.name or device.id
        for device in source.devices()
    }
    baseline = resting_hr_baselines(wellness)

    rows = []
    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue
        if steady_only and activity.type == "trail_run":
            continue
        if activity.avg_hr is None or activity.distance_m <= 0:
            continue
        if not activity.duration_s:
            continue

        minutes = activity.duration_s / 60.0
        if steady_only and not (STEADY_MIN <= minutes <= STEADY_MAX):
            continue

        methods = set(activity.workout_methods)
        targets = set(activity.workout_targets)
        if steady_only and (
            methods & QUALITY_METHODS or targets & QUALITY_TARGETS
        ):
            continue
        if steady_only and "recovery" in targets:
            continue

        resting_hr = baseline(activity.date)

        speed = activity.distance_m / activity.duration_s
        if not (MIN_SPEED <= speed <= MAX_SPEED):
            continue

        max_hr = threshold_max_hr(thresholds, activity.date)
        if max_hr is None:
            continue

        estimates = effective_vo2max(
            speed * 60.0,
            activity.avg_hr,
            resting_hr,
            max_hr,
            activity.max_hr,
        )
        gain = activity.elevation_gain_m
        loss = activity.elevation_loss_m

        def corrected(gain_factor: float, loss_factor: float):
            if gain is None or loss is None or not activity.duration_s:
                return None
            distance = (
                activity.distance_m
                + gain * gain_factor
                - loss * loss_factor
            )
            if distance <= 0:
                return None
            return effective_vo2max(
                distance / activity.duration_s * 60.0,
                activity.avg_hr,
                resting_hr,
                max_hr,
            )["estimate_hr"]

        rows.append(
            {
                "date": activity.date,
                "year": activity.date.year,
                "name": activity.name,
                "device": devices.get(activity.device_id, "unknown"),
                "is_race": "race" in methods or "race" in targets,
                "garmin": activity.vo2max_garmin,
                "runalyze": activity.vo2max_runalyze,
                "runalyze_raw": (
                    activity.vo2max_runalyze / 0.93
                    if activity.vo2max_runalyze is not None
                    else None
                ),
                "speed": speed,
                "hr": activity.avg_hr,
                "rhr": resting_hr,
                "max_hr": max_hr,
                "minutes": minutes,
                "gain": gain,
                "loss": loss,
                "estimate_5_1": corrected(5.0, 1.0),
                "estimate_5_5": corrected(5.0, 5.0),
                "estimate_1_1": corrected(1.0, 1.0),
                **estimates,
            }
        )

    return sorted(rows, key=lambda row: row["date"]), []


def rolling(rows: list[dict], key: str, window: int) -> list[float | None]:
    values = []
    for index, row in enumerate(rows):
        start = row["date"] - timedelta(days=window)
        samples = [
            candidate[key]
            for candidate in rows[: index + 1]
            if candidate["date"] >= start and candidate[key] is not None
        ]
        values.append(mean(samples) if samples else None)
    return values


def change_stats(rows: list[dict], key: str) -> dict[str, float] | None:
    values = [row[key] for row in rows if row[key] is not None]
    if len(values) < 2:
        return None
    changes = [
        abs(second - first) for first, second in zip(values, values[1:])
    ]
    return {
        "n": len(values),
        "same": sum(value == 0 for value in changes),
        "changed": sum(value >= 0.1 for value in changes),
        "mean_abs": mean(changes),
    }


def race_vdot(distance_m: float, time_s: float) -> float | None:
    if distance_m <= 0 or time_s <= 0:
        return None
    velocity = distance_m / (time_s / 60.0)
    oxygen = -4.60 + 0.182258 * velocity + 0.000104 * velocity ** 2
    minutes = time_s / 60.0
    fraction = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * minutes)
        + 0.2989558 * math.exp(-0.1932605 * minutes)
    )
    return oxygen / fraction if fraction else None


def race_validation(source, steady: list[dict]) -> None:
    activities = {
        activity.id: activity
        for activity in source.activities(date(2000, 1, 1), date.today())
    }
    global_estimate = mean(
        row["estimate_hr"]
        for row in steady
        if row["estimate_hr"] is not None
    )
    rows = []

    for result in source.race_results():
        activity = activities.get(result.activity_id)
        if activity is None or activity.type != "run":
            continue
        if activity.date < date(2019, 1, 1):
            continue
        if not result.official_distance_m or not result.official_time_s:
            continue

        km = result.official_distance_m / 1000.0
        gain = activity.elevation_gain_m
        gain_per_km = gain / km if gain is not None and km else None
        if km > 50 or gain_per_km is not None and gain_per_km > 20:
            continue
        name = result.name.lower()
        if "relay" in name or "staffel" in name:
            continue

        nearest = [
            row["estimate_hr"]
            for row in steady
            if row["estimate_hr"] is not None
            and not row["is_race"]
            and abs((row["date"] - activity.date).days) <= 14
        ]
        estimate = mean(nearest) if nearest else global_estimate
        vdot = race_vdot(result.official_distance_m, result.official_time_s)
        if vdot is None:
            continue

        rows.append(
            {
                "date": activity.date,
                "name": result.name or activity.name,
                "km": km,
                "vdot": vdot,
                "garmin": activity.vo2max_garmin,
                "runalyze": activity.vo2max_runalyze,
                "estimate": estimate,
            }
        )

    if len(rows) < 6:
        print("not enough recent road races for validation")
        return []

    print("\nDaniels VDOT vs the VO2max series (recent road races):")
    table(
        [
            (
                row["date"].isoformat(),
                row["name"][:28],
                f"{row['km']:.2f}",
                f"{row['vdot']:.1f}",
                f"{row['garmin']:.1f}"
                if row["garmin"] is not None
                else "-",
                f"{row['runalyze']:.1f}"
                if row["runalyze"] is not None
                else "-",
                f"{row['estimate']:.1f}",
            )
            for row in rows
        ],
        headers=["date", "race", "km", "VDOT", "Garmin", "Runalyze", "estimate"],
    )

    def difference(key: str) -> str:
        values = [
            row["vdot"] - row[key]
            for row in rows
            if row[key] is not None
        ]
        if not values:
            return "-"
        return f"{mean(values):+.2f} / {median(values):+.2f}"

    vdot_mean = mean(row["vdot"] for row in rows)
    vdot_median = median(row["vdot"] for row in rows)
    table(
        [
            ("VDOT mean / median", f"{vdot_mean:.2f} / {vdot_median:.2f}"),
            ("VDOT - Garmin", difference("garmin")),
            ("VDOT - Runalyze", difference("runalyze")),
            ("VDOT - estimate", difference("estimate")),
        ],
        headers=["comparison", "mean / median"],
    )

    figure = go.Figure()
    garmin_rows = [row for row in rows if row["garmin"] is not None]
    figure.add_trace(
        go.Scatter(
            x=[row["vdot"] for row in garmin_rows],
            y=[row["garmin"] for row in garmin_rows],
            mode="markers",
            name="Garmin",
            marker={"size": 7, "color": "#4c78a8"},
        )
    )
    runalyze_rows = [row for row in rows if row["runalyze"] is not None]
    figure.add_trace(
        go.Scatter(
            x=[row["vdot"] for row in runalyze_rows],
            y=[row["runalyze"] for row in runalyze_rows],
            mode="markers",
            name="Runalyze",
            marker={"size": 6, "color": "#999999"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[row["vdot"] for row in rows],
            y=[row["estimate"] for row in rows],
            mode="markers",
            name="session estimate",
            marker={"size": 7, "color": "#54a24b", "symbol": "diamond"},
        )
    )
    low = 55
    high = 70
    figure.add_trace(
        go.Scatter(
            x=[low, high],
            y=[low, high],
            mode="lines",
            line={"color": "#333333", "width": 1, "dash": "dot"},
            name="y = x",
        )
    )
    figure.update_xaxes(title_text="Daniels race VDOT")
    figure.update_yaxes(title_text="VO2max estimate")
    figure.update_layout(
        title="Race VDOT vs Garmin, Runalyze and the session estimate",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "vo2max-race-validation")
    return rows


def yearly(rows: list[dict]) -> None:
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["year"]].append(row)

    year_rows = []
    for year, chunk in sorted(groups.items()):
        garmin = [row["garmin"] for row in chunk if row["garmin"] is not None]
        runalyze = [
            row["runalyze"] for row in chunk if row["runalyze"] is not None
        ]
        estimate_hr = [
            row["estimate_hr"]
            for row in chunk
            if row["estimate_hr"] is not None
        ]
        estimate_reserve = [
            row["estimate_reserve"]
            for row in chunk
            if row["estimate_reserve"] is not None
        ]
        year_rows.append(
            (
                year,
                len(chunk),
                f"{mean(garmin):.1f}" if garmin else "-",
                f"{mean(runalyze):.1f}" if runalyze else "-",
                f"{mean(estimate_hr):.1f}" if estimate_hr else "-",
                f"{mean(estimate_reserve):.1f}" if estimate_reserve else "-",
            )
        )

    table(
        year_rows,
        headers=[
            "year",
            "runs",
            "Garmin",
            "Runalyze",
            "estimate HR/HRmax",
            "estimate reserve",
        ],
    )


def runalyze_correction(rows: list[dict]) -> str:
    """Compare distance-correction variants against Runalyze."""
    variants = [
        ("raw pace", "estimate_hr"),
        ("d + 5*gain - loss", "estimate_5_1"),
        ("d + 5*gain - 5*loss", "estimate_5_5"),
        ("d + gain - loss", "estimate_1_1"),
    ]
    output = []
    best = None

    for label, key in variants:
        paired = [
            row
            for row in rows
            if row["runalyze"] is not None and row[key] is not None
        ]
        if len(paired) < 10:
            output.append((label, len(paired), "-", "-", "-", "-"))
            continue
        derived = [row[key] for row in paired]
        stored = [row["runalyze"] for row in paired]
        errors = [
            value - target for value, target in zip(derived, stored)
        ]
        rmse = (sum(error ** 2 for error in errors) / len(errors)) ** 0.5
        corr = correlation(derived, stored)
        output.append(
            (
                label,
                len(paired),
                f"{mean(derived):.1f}",
                f"{corr:+.2f}",
                f"{rmse:.2f}",
                f"{mean(errors):+.2f}",
            )
        )
        if best is None or rmse < best[1]:
            best = (label, rmse, key)

    print("\nRunalyze distance-correction candidates (all runs):")
    table(
        output,
        headers=["variant", "n", "mean", "r stored", "RMSE", "bias"],
    )
    if best:
        print(f"best against stored Runalyze: {best[0]} (RMSE {best[1]:.2f})")
    return best[2] if best else "estimate_hr"


def plot_series(
    rows: list[dict],
    key: str = "estimate_hr",
    race_rows: list[dict] | None = None,
) -> None:
    dates = [row["date"] for row in rows]
    figure = go.Figure()
    device_colors = {
        "fr645": "#e45756",
        "enduro": "#4c78a8",
        "unknown": "#999999",
    }
    for device, color in device_colors.items():
        chunk = [row for row in rows if row["device"] == device]
        if not chunk:
            continue
        figure.add_trace(
            go.Scatter(
                x=[row["date"] for row in chunk],
                y=[row["garmin"] for row in chunk],
                mode="markers",
                marker={"size": 4, "color": color},
                name=f"Garmin {device}",
            )
        )
    figure.add_trace(
        go.Scatter(
            x=dates,
            y=[row["runalyze"] for row in rows],
            mode="markers",
            marker={"size": 3, "color": "#999999", "opacity": 0.5},
            name="Runalyze raw",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=dates,
            y=rolling(rows, "runalyze", 42),
            mode="lines",
            line={"color": "#777777", "width": 2, "dash": "dot"},
            name="Runalyze 42d mean",
        )
    )

    for key_name, label, color, dash in (
        (key, "best estimate, 42d mean", "#54a24b", "solid"),
        (
            "estimate_reserve",
            "estimate HR reserve, 42d mean",
            "#f58518",
            "dash",
        ),
    ):
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=rolling(rows, key_name, 42),
                mode="lines",
                line={"color": color, "width": 2, "dash": dash},
                name=label,
            )
        )

    figure.update_yaxes(title_text="VO2max (ml/kg/min)")
    figure.update_xaxes(title_text="date")
    if race_rows:
        figure.add_trace(
            go.Scatter(
                x=[row["date"] for row in race_rows],
                y=[row["vdot"] for row in race_rows],
                mode="markers",
                marker={"size": 9, "color": "#e45756", "symbol": "star"},
                name="race VDOT",
            )
        )
    figure.update_layout(
        title="Garmin, Runalyze and session-level estimates",
        legend={"orientation": "h", "y": -0.3},
    )
    save(figure, "vo2max-estimates")


def plot_scatter(rows: list[dict], key: str = "estimate_hr") -> None:
    points = [
        row
        for row in rows
        if row["garmin"] is not None and row[key] is not None
    ]
    figure = go.Figure(
        go.Scatter(
            x=[row[key] for row in points],
            y=[row["garmin"] for row in points],
            mode="markers",
            marker={"size": 5, "opacity": 0.5},
            text=[row["date"] for row in points],
        )
    )
    figure.update_xaxes(title_text="session estimate (HR reserve)")
    figure.update_yaxes(title_text="Garmin VO2max")
    figure.update_layout(title="Estimate vs Garmin")
    save(figure, "vo2max-estimate-scatter")


def device_smoothing(source) -> None:
    """Garmin change frequency by watch, using all runs with a value."""
    devices = {
        device.id: device.product or device.name or device.id
        for device in source.devices()
    }
    rows = [
        {
            "date": activity.date,
            "device": devices.get(activity.device_id, "unknown"),
            "garmin": activity.vo2max_garmin,
        }
        for activity in source.activities(date(2000, 1, 1), date.today())
        if activity.type in RUN_TYPES
        and activity.vo2max_garmin is not None
    ]
    rows.sort(key=lambda row: row["date"])

    print("\nGarmin smoothing by device (all runs with a value):")
    table(
        [
            (
                device,
                stats["n"],
                f"{stats['same']:.0f}",
                f"{stats['changed']:.0f}",
                f"{stats['mean_abs']:.3f}",
            )
            for device in ("fr645", "enduro", "unknown")
            for stats in [change_stats(
                [row for row in rows if row["device"] == device],
                "garmin",
            )]
            if stats
        ],
        headers=["device", "n", "same", "changed>=0.1", "mean |change|"],
    )


def smoothing_validation(
    race_rows: list[dict],
    all_runs: list[dict],
    steady: list[dict],
) -> None:
    """Which smoothing window and lag best follows race VDOT?"""
    if not race_rows:
        return

    populations = (("all runs", all_runs), ("steady 40-75", steady))
    results = []

    for population, data in populations:
        days, series = daily_estimate_series(data)
        if not days:
            continue
        index = {day: position for position, day in enumerate(days)}
        ewmas = {
            window: ewma(
                series,
                alpha_from_time_constant(window),
                initial=series[0],
            )
            for window in SMOOTH_WINDOWS
        }

        for method in ("rolling", "ewma"):
            for window in SMOOTH_WINDOWS:
                for lag in SMOOTH_LAGS:
                    errors = []
                    for race in race_rows:
                        target = race["date"] - timedelta(days=lag)
                        if method == "ewma":
                            position = index.get(target)
                            if position is None:
                                continue
                            value = ewmas[window][position]
                        else:
                            value = rolling_estimate(data, target, window)
                        if value is None:
                            continue
                        errors.append(value - race["vdot"])
                    if len(errors) < 10:
                        continue
                    results.append(
                        {
                            "population": population,
                            "method": method,
                            "window": window,
                            "lag": lag,
                            "n": len(errors),
                            "mae": mean(abs(error) for error in errors),
                            "median": median(abs(error) for error in errors),
                            "bias": mean(errors),
                        }
                    )

    results.sort(key=lambda result: result["median"])
    print("\nsmoothing/lag validation against race VDOT:")
    table(
        [
            (
                result["population"],
                result["method"],
                f"{result['window']}d",
                f"{result['lag']}d",
                result["n"],
                f"{result['mae']:.2f}",
                f"{result['median']:.2f}",
                f"{result['bias']:+.2f}",
            )
            for result in results[:16]
        ],
        headers=[
            "population",
            "smoothing",
            "window",
            "lag",
            "n",
            "mean abs",
            "median abs",
            "bias",
        ],
    )
    print(
        "These are in-sample choices over a small race set; the top rows are "
        "hypotheses, not independent validation."
    )

    focused = [
        ("ewma", 42, 0),
        ("ewma", 182, 0),
        ("rolling", 42, 0),
        ("rolling", 182, 0),
        ("rolling", 14, 7),
        ("rolling", 63, 0),
    ]
    print("\nfocused comparison (all runs):")
    table(
        [
            (
                method,
                f"{window}d",
                f"{lag}d",
                f"{result['mae']:.2f}",
                f"{result['median']:.2f}",
                f"{result['bias']:+.2f}",
            )
            for method, window, lag in focused
            for result in [
                next(
                    (
                        item
                        for item in results
                        if item["population"] == "all runs"
                        and item["method"] == method
                        and item["window"] == window
                        and item["lag"] == lag
                    ),
                    None,
                )
            ]
            if result
        ],
        headers=["smoothing", "window", "lag", "mean abs", "median abs", "bias"],
    )

    # Best result per population and method.
    best = {}
    for result in results:
        key = (result["population"], result["method"])
        if key not in best:
            best[key] = result
    print("\nbest per population/method:")
    table(
        [
            (
                population,
                method,
                f"{result['window']}d",
                f"{result['lag']}d",
                f"{result['mae']:.2f}",
                f"{result['median']:.2f}",
            )
            for (population, method), result in sorted(best.items())
        ],
        headers=["population", "smoothing", "window", "lag", "mean abs", "median"],
    )

    # Heatmaps for the all-runs population.
    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("rolling mean", "EWMA"),
    )
    for column, method in enumerate(("rolling", "ewma"), start=1):
        matrix = []
        for window in SMOOTH_WINDOWS:
            row = []
            for lag in SMOOTH_LAGS:
                match = next(
                    (
                        result["median"]
                        for result in results
                        if result["population"] == "all runs"
                        and result["method"] == method
                        and result["window"] == window
                        and result["lag"] == lag
                    ),
                    None,
                )
                row.append(match)
            matrix.append(row)
        if any(value is not None for row in matrix for value in row):
            figure.add_trace(
                go.Heatmap(
                    z=matrix,
                    x=[f"{lag}d" for lag in SMOOTH_LAGS],
                    y=[f"{window}d" for window in SMOOTH_WINDOWS],
                    colorscale="Viridis",
                    colorbar={"title": "median error"},
                ),
                row=1,
                col=column,
            )
    figure.update_xaxes(title_text="lag before race")
    figure.update_yaxes(title_text="window")
    figure.update_layout(title="VO2max smoothing vs race VDOT")
    save(figure, "vo2max-smoothing")


def daily_estimate_series(rows: list[dict]) -> tuple[list[date], list[float]]:
    by_day: dict[date, list[float]] = defaultdict(list)
    for row in rows:
        if row["is_race"] or row["estimate_hr"] is None:
            continue
        by_day[row["date"]].append(row["estimate_hr"])
    if not by_day:
        return [], []

    daily = {day: mean(values) for day, values in by_day.items()}
    days = date_range(min(daily), max(daily))
    series = []
    carried = None
    for day in days:
        if day in daily:
            carried = daily[day]
        series.append(carried)
    return days, series


def rolling_estimate(
    rows: list[dict],
    target: date,
    window: int,
) -> float | None:
    start = target - timedelta(days=window - 1)
    values = [
        row["estimate_hr"]
        for row in rows
        if not row["is_race"]
        and start <= row["date"] <= target
        and row["estimate_hr"] is not None
    ]
    return mean(values) if values else None


def main() -> None:
    with create_source() as source:
        rows, _ = build_rows(source)
        all_runs, _ = build_rows(source, steady_only=False)
        race_rows = race_validation(source, all_runs)
        device_smoothing(source)
        smoothing_validation(race_rows, all_runs, rows)

    print(f"{len(rows)} steady runs with RHR and max HR")
    if len(rows) < 100:
        print("not enough rows")
        return

    garmin_count = sum(row["garmin"] is not None for row in rows)
    runalyze_count = sum(row["runalyze"] is not None for row in rows)
    both_count = sum(
        row["garmin"] is not None and row["runalyze"] is not None
        for row in rows
    )
    print(
        f"Garmin {garmin_count}, Runalyze {runalyze_count}, both {both_count}"
    )

    table(
        [
            (
                key,
                sum(row[key] is not None for row in rows),
                f"{mean(row[key] for row in rows if row[key] is not None):.2f}",
                f"{median(row[key] for row in rows if row[key] is not None):.2f}",
            )
            for key in (
                "garmin",
                "runalyze",
                "runalyze_raw",
                "estimate_hr",
                "estimate_reserve",
            )
        ],
        headers=["series", "n", "mean", "median"],
    )
    print(
        "Runalyze values are stored with its 0.93 correction applied; the "
        "'runalyze_raw' row divides that back out for comparison."
    )

    def paired_correlation(first: str, second: str) -> str:
        paired = [
            row
            for row in rows
            if row[first] is not None and row[second] is not None
        ]
        if len(paired) < 10:
            return "-"
        xs = [row[first] for row in paired]
        ys = [row[second] for row in paired]
        return f"{correlation(xs, ys):+.2f}"

    table(
        [
            ("Garmin vs Runalyze", paired_correlation("garmin", "runalyze")),
            (
                "Garmin vs estimate HR/HRmax",
                paired_correlation("garmin", "estimate_hr"),
            ),
            (
                "Garmin vs estimate reserve",
                paired_correlation("garmin", "estimate_reserve"),
            ),
            (
                "Runalyze vs estimate HR/HRmax",
                paired_correlation("runalyze", "estimate_hr"),
            ),
        ],
        headers=["pair", "r"],
    )

    print("\nsmoothing check (consecutive run changes):")
    for key in ("garmin", "runalyze"):
        stats = change_stats(rows, key)
        if stats:
            print(
                f"{key}: n={stats['n']}, same={stats['same']:.0f}, "
                f"changed>=0.1={stats['changed']:.0f}, "
                f"mean |change|={stats['mean_abs']:.2f}"
            )

    print("\nrolling series vs Garmin:")
    rolling_rows = []

    def rolling_metrics_for(
        data: list[dict],
        key: str,
        window: int,
    ) -> tuple[str, str]:
        values = rolling(data, key, window)
        paired = [
            (row["garmin"], value)
            for row, value in zip(data, values)
            if row["garmin"] is not None and value is not None
        ]
        if not paired:
            return "-", "-"
        errors = [value - garmin for garmin, value in paired]
        corr = correlation(
            [pair[0] for pair in paired], [pair[1] for pair in paired]
        )
        rmse = (sum(error ** 2 for error in errors) / len(errors)) ** 0.5
        return f"{corr:+.2f}", f"{rmse:.2f}"

    for window in WINDOWS:
        estimate_corr, estimate_rmse = rolling_metrics_for(
            rows, "estimate_hr", window
        )
        runalyze_corr, runalyze_rmse = rolling_metrics_for(
            rows, "runalyze", window
        )
        rolling_rows.append(
            (
                f"{window}d",
                estimate_corr,
                estimate_rmse,
                runalyze_corr,
                runalyze_rmse,
            )
        )
    table(
        rolling_rows,
        headers=[
            "window",
            "estimate r",
            "estimate RMSE",
            "Runalyze r",
            "Runalyze RMSE",
        ],
    )

    print("\ndevice-era estimate vs Garmin:")
    device_rows = []
    for device in ("fr645", "enduro", "unknown"):
        data = [row for row in all_runs if row["device"] == device]
        raw = [
            row
            for row in data
            if row["garmin"] is not None
            and row["estimate_hr"] is not None
        ]
        smooth = rolling(data, "estimate_hr", 42)
        smooth_pairs = [
            (row["garmin"], value)
            for row, value in zip(data, smooth)
            if row["garmin"] is not None and value is not None
        ]
        if not raw or not smooth_pairs:
            continue
        raw_corr = correlation(
            [row["estimate_hr"] for row in raw],
            [row["garmin"] for row in raw],
        )
        smooth_corr = correlation(
            [pair[0] for pair in smooth_pairs],
            [pair[1] for pair in smooth_pairs],
        )
        smooth_rmse = (
            mean((pair[1] - pair[0]) ** 2 for pair in smooth_pairs)
        ) ** 0.5
        device_rows.append(
            (
                device,
                len(raw),
                f"{raw_corr:+.2f}",
                f"{smooth_corr:+.2f}",
                f"{smooth_rmse:.2f}",
            )
        )
    table(
        device_rows,
        headers=["device", "n", "raw r", "42d r", "42d RMSE"],
    )

    print("\nall-runs sensitivity (Runalyze uses all runs and GAP):")
    sensitivity_rows = []
    for label, data in (("steady 40-75", rows), ("all runs", all_runs)):
        estimates = [
            row["estimate_hr"]
            for row in data
            if row["estimate_hr"] is not None
        ]
        paired = [
            row
            for row in data
            if row["garmin"] is not None
            and row["estimate_hr"] is not None
        ]
        runalyze_paired = [
            row
            for row in data
            if row["runalyze"] is not None
            and row["estimate_hr"] is not None
        ]
        rolling_42 = rolling_metrics_for(data, "estimate_hr", 42)
        garmin_corr = (
            correlation(
                [row["garmin"] for row in paired],
                [row["estimate_hr"] for row in paired],
            )
            if len(paired) >= 10
            else None
        )
        runalyze_corr = (
            correlation(
                [row["runalyze"] for row in runalyze_paired],
                [row["estimate_hr"] for row in runalyze_paired],
            )
            if len(runalyze_paired) >= 10
            else None
        )
        sensitivity_rows.append(
            (
                label,
                len(estimates),
                f"{mean(estimates):.1f}" if estimates else "-",
                f"{garmin_corr:+.2f}" if garmin_corr is not None else "-",
                f"{runalyze_corr:+.2f}"
                if runalyze_corr is not None
                else "-",
                rolling_42[0] if rolling_42[0] != "-" else "-",
            )
        )
    table(
        sensitivity_rows,
        headers=[
            "population",
            "n",
            "estimate mean",
            "r Garmin",
            "r Runalyze",
            "42d r Garmin",
        ],
    )
    print(
        "Runalyze uses all runs and a grade-adjusted pace; the estimate here "
        "uses raw pace, so hilly/interval runs are not like-for-like."
    )
    yearly(all_runs)
    best_key = runalyze_correction(all_runs)
    plot_series(all_runs, best_key, race_rows)
    plot_scatter(all_runs, best_key)

    print("\nverdict: inspect level, correlation, and the Garmin/Runalyze noise.")


if __name__ == "__main__":
    main()
