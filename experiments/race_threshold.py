"""Experiment: derive threshold pace from race results and compare the setting.

Threshold is approximately one-hour all-out pace. For each run threshold
snapshot, fit the prior official road races and predict the 60-minute pace with
two models:

- Riegel: log(time) = a + b*log(distance), solved for 60 minutes;
- critical speed: distance = CS*time + D', evaluated at 3600 s.

Compare both with the stored Intervals threshold pace and the official race
paces. This tests whether the setting behaves like a 1-hour threshold or like a
faster 10k/ceiling reference.

    uv run --env-file .env python experiments/race_threshold.py
"""

from __future__ import annotations

import math
from datetime import date
from statistics import mean, median

import plotly.graph_objects as go

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_RACES = 6
MAX_ULTRA_KM = 50.0
HILL_GAIN_PER_KM = 20.0


def fit_line(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx = mean(xs)
    my = mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    return slope, my - slope * mx


def format_pace(seconds: float | None) -> str:
    if not seconds:
        return "-"
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def race_rows(source) -> list[dict]:
    activities = {
        activity.id: activity
        for activity in source.activities(date(2000, 1, 1), date.today())
    }
    rows = []

    for result in source.race_results():
        activity = activities.get(result.activity_id)
        if activity is None or activity.type not in RUN_TYPES:
            continue
        if activity.type == "trail_run":
            continue
        if not result.official_distance_m or not result.official_time_s:
            continue

        km = result.official_distance_m / 1000.0
        if km > MAX_ULTRA_KM:
            continue
        gain = activity.elevation_gain_m
        if gain is not None and km and gain / km > HILL_GAIN_PER_KM:
            continue
        name = (result.name or activity.name or "").lower()
        if "relay" in name or "staffel" in name:
            continue

        rows.append(
            {
                "date": activity.date,
                "name": result.name or activity.name,
                "km": km,
                "minutes": result.official_time_s / 60.0,
                "pace": result.official_time_s / km,
            }
        )

    return sorted(rows, key=lambda row: row["date"])


def estimate_60(rows: list[dict]) -> dict[str, float] | None:
    if len(rows) < MIN_RACES:
        return None

    riegel_b, riegel_a = fit_line(
        [math.log(row["km"]) for row in rows],
        [math.log(row["minutes"]) for row in rows],
    )
    if riegel_b <= 0:
        riegel_pace = None
    else:
        distance = math.exp((math.log(60.0) - riegel_a) / riegel_b)
        riegel_pace = 3600.0 / distance if distance > 0 else None

    cs, d_prime = fit_line(
        [row["minutes"] * 60.0 for row in rows],
        [row["km"] * 1000.0 for row in rows],
    )
    distance = cs * 3600.0 + d_prime
    cs_pace = 3600.0 / (distance / 1000.0) if distance > 0 and cs > 0 else None

    return {
        "n": len(rows),
        "riegel_b": riegel_b,
        "riegel": riegel_pace,
        "cs": cs,
        "d_prime": d_prime,
        "cs_pace": cs_pace,
    }


def main() -> None:
    with create_source() as source:
        races = race_rows(source)
        thresholds = sorted(
            [
                snapshot
                for snapshot in source.athlete_thresholds()
                if snapshot.sport == "run"
                and snapshot.threshold_pace_mps is not None
            ],
            key=lambda snapshot: snapshot.effective_from,
        )

    if len(races) < MIN_RACES:
        print("not enough official road races")
        return

    print(f"{len(races)} official road races; {len(thresholds)} run snapshots")
    rows = []
    estimates = []

    for snapshot in thresholds:
        prior = [race for race in races if race["date"] < snapshot.effective_from]
        estimate = estimate_60(prior)
        setting = 1000.0 / snapshot.threshold_pace_mps
        if estimate is None:
            rows.append(
                (
                    snapshot.effective_from.isoformat(),
                    format_pace(setting),
                    "-",
                    "-",
                    "-",
                    len(prior),
                )
            )
            continue

        row = {
            "date": snapshot.effective_from,
            "setting": setting,
            "riegel": estimate["riegel"],
            "cs": estimate["cs_pace"],
            "n": estimate["n"],
        }
        estimates.append(row)
        rows.append(
            (
                snapshot.effective_from.isoformat(),
                format_pace(setting),
                format_pace(estimate["riegel"]),
                format_pace(estimate["cs_pace"]),
                f"{setting - estimate['riegel']:+.1f}"
                if estimate["riegel"] is not None
                else "-",
                estimate["n"],
            )
        )

    table(
        rows,
        headers=[
            "snapshot",
            "setting",
            "Riegel 60m",
            "CS 60m",
            "setting - Riegel s/km",
            "races",
        ],
    )

    if estimates:
        deltas = [
            row["setting"] - row["riegel"]
            for row in estimates
            if row["riegel"] is not None
        ]
        print(
            f"\nsetting vs Riegel 60m: mean {mean(deltas):+.1f}, "
            f"median {median(deltas):+.1f} s/km (negative = setting faster)"
        )
        cs_deltas = [
            row["setting"] - row["cs"]
            for row in estimates
            if row["cs"] is not None
        ]
        if cs_deltas:
            print(
                f"setting vs critical speed 60m: mean {mean(cs_deltas):+.1f}, "
                f"median {median(cs_deltas):+.1f} s/km"
            )

    current = estimate_60(races)
    if current:
        latest = thresholds[-1]
        setting = 1000.0 / latest.threshold_pace_mps
        print(
            f"\nlatest setting {format_pace(setting)}; full-race Riegel "
            f"{format_pace(current['riegel'])}, CS {format_pace(current['cs_pace'])} "
            f"(n={current['n']})"
        )

    figure = go.Figure()
    setting_x = [snapshot.effective_from for snapshot in thresholds]
    setting_y = [1000.0 / snapshot.threshold_pace_mps for snapshot in thresholds]
    figure.add_trace(
        go.Scatter(
            x=setting_x,
            y=setting_y,
            mode="lines+markers",
            line={"shape": "hv", "color": "#2ca02c", "width": 2},
            marker={"size": 6},
            name="stored threshold",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[race["date"] for race in races],
            y=[race["pace"] for race in races],
            mode="markers",
            marker={"size": 7, "color": "#9467bd", "symbol": "diamond"},
            text=[f"{race['name']} ({race['km']:.1f} km)" for race in races],
            name="official race pace",
        )
    )
    if estimates:
        figure.add_trace(
            go.Scatter(
                x=[row["date"] for row in estimates],
                y=[row["riegel"] for row in estimates],
                mode="lines+markers",
                line={"color": "#4c78a8", "width": 2},
                marker={"size": 6},
                name="Riegel 60m",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[row["date"] for row in estimates],
                y=[row["cs"] for row in estimates],
                mode="lines+markers",
                line={"color": "#f58518", "width": 2, "dash": "dash"},
                marker={"size": 5},
                name="critical speed 60m",
            )
        )

    figure.update_yaxes(
        title_text="pace (s/km, faster up)",
        autorange="reversed",
    )
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Threshold setting, official race pace, and race-derived 1-hour pace",
        legend={"orientation": "h", "y": -0.25},
    )
    save(figure, "race-threshold")

    print(
        "\nreading: a race-derived 1-hour pace below the setting (smaller "
        "s/km) means the setting is a ceiling; a close match means the setting "
        "is a measured threshold. The number of prior races is shown per point."
    )


if __name__ == "__main__":
    main()
