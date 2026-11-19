"""Experiment: Garmin VO2max drops in the Enduro era, with canonical elevation.

Question
--------
The Enduro-era running Garmin VO2max still makes sudden negative jumps of
1-2.5 ml/kg/min. Are they explained by terrain (hills, net downhill), long or
trail sessions, short recovery runs, or are they device noise? Runalyze and a
session-level effective estimate are shown beside each drop to separate a real
performance change from a Garmin update.

    uv run --env-file .env python experiments/enduro_vo2max_drops.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean, median

import plotly.graph_objects as go

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

DROP = 1.0
DEVICE_PRODUCT = "enduro"
FORMULA_MAX_HR = 192.0


def terrain(row: dict) -> str:
    net = row["net_per_km"]
    if net is None:
        return "unknown"
    if net <= -10:
        return "uphill"
    if net >= 10:
        return "downhill"
    if row["gain_per_km"] is not None and row["gain_per_km"] > 20:
        return "hilly"
    return "flat"


def session_type(row: dict) -> str:
    if "recovery" in row["targets"]:
        return "recovery"
    if "race" in row["methods"]:
        return "race"
    if "intervals" in row["methods"]:
        return "intervals"
    if "long_run" in row["methods"]:
        return "long_run"
    if row["minutes"] < 30:
        return "short"
    return "easy/other"


def effective_estimate(row: dict) -> float | None:
    if not row["hr"] or not row["km"] or not row["minutes"]:
        return None
    speed_min = row["km"] * 1000.0 / row["minutes"]
    fraction = row["hr"] / FORMULA_MAX_HR
    if not 0.5 <= fraction <= 0.95:
        return None
    return (3.5 + 0.2 * speed_min) / fraction


def build_rows(source) -> list[dict]:
    devices = {
        device.id: device.product
        for device in source.devices()
    }
    rows = []

    for activity in source.activities(date(2000, 1, 1), date.today()):
        if activity.type not in RUN_TYPES:
            continue
        if devices.get(activity.device_id) != DEVICE_PRODUCT:
            continue
        if activity.vo2max_garmin is None or activity.vo2max_garmin <= 0:
            continue

        km = activity.distance_m / 1000.0
        minutes = activity.duration_s / 60.0
        gain = activity.elevation_gain_m
        loss = activity.elevation_loss_m
        weather = source.activity_weather(activity.id)
        temp = weather.temp_c if weather is not None else None

        rows.append(
            {
                "id": activity.id,
                "date": activity.date,
                "start": activity.started_at_utc
                or f"{activity.date.isoformat()}T00:00:00",
                "name": activity.name,
                "sport": activity.type,
                "trail": activity.type == "trail_run",
                "value": activity.vo2max_garmin,
                "runalyze": activity.vo2max_runalyze,
                "km": km,
                "minutes": minutes,
                "hr": activity.avg_hr,
                "gain_per_km": gain / km if gain is not None and km else None,
                "loss_per_km": loss / km if loss is not None and km else None,
                "net_per_km": (
                    (loss - gain) / km
                    if loss is not None and gain is not None and km
                    else None
                ),
                "temp": temp,
                "methods": set(activity.workout_methods),
                "targets": set(activity.workout_targets),
            }
        )

    rows.sort(key=lambda row: (row["start"], row["id"]))
    for index, row in enumerate(rows):
        previous = rows[index - 1] if index else None
        row["previous"] = previous["value"] if previous else None
        row["delta"] = row["value"] - previous["value"] if previous else None
        row["terrain"] = terrain(row)
        row["session"] = session_type(row)
        row["estimate"] = effective_estimate(row)

    return rows


def main() -> None:
    with create_source() as source:
        rows = build_rows(source)

    transitions = [row for row in rows if row["delta"] is not None]
    drops = [row for row in transitions if row["delta"] <= -DROP]
    non_drops = [row for row in transitions if row["delta"] > -DROP]

    print(
        f"{len(rows)} Enduro running readings, {len(transitions)} transitions; "
        f"{len(drops)} drops >= {DROP}"
    )

    def med(chunk, key):
        values = [row[key] for row in chunk if row[key] is not None]
        return median(values) if values else None

    def share(chunk, predicate):
        return 100 * sum(predicate(row) for row in chunk) / len(chunk)

    table(
        [
            (
                "n",
                len(drops),
                len(non_drops),
            ),
            ("median km", f"{med(drops, 'km'):.1f}", f"{med(non_drops, 'km'):.1f}"),
            (
                "median min",
                f"{med(drops, 'minutes'):.0f}",
                f"{med(non_drops, 'minutes'):.0f}",
            ),
            ("median HR", f"{med(drops, 'hr'):.0f}", f"{med(non_drops, 'hr'):.0f}"),
            (
                "gain/km",
                f"{med(drops, 'gain_per_km'):.1f}",
                f"{med(non_drops, 'gain_per_km'):.1f}",
            ),
            (
                "loss/km",
                f"{med(drops, 'loss_per_km'):.1f}",
                f"{med(non_drops, 'loss_per_km'):.1f}",
            ),
            (
                "net/km",
                f"{med(drops, 'net_per_km'):+.1f}",
                f"{med(non_drops, 'net_per_km'):+.1f}",
            ),
            ("temp", f"{med(drops, 'temp'):.0f}", f"{med(non_drops, 'temp'):.0f}"),
            ("trail %", f"{share(drops, lambda r: r['trail']):.0f}%", f"{share(non_drops, lambda r: r['trail']):.0f}%"),
            (
                "long_run %",
                f"{share(drops, lambda r: r['session'] == 'long_run'):.0f}%",
                f"{share(non_drops, lambda r: r['session'] == 'long_run'):.0f}%",
            ),
            (
                "recovery %",
                f"{share(drops, lambda r: r['session'] == 'recovery'):.0f}%",
                f"{share(non_drops, lambda r: r['session'] == 'recovery'):.0f}%",
            ),
        ],
        headers=["attribute", "drop", "other"],
    )

    rates = defaultdict(lambda: [0, 0])
    for row in transitions:
        rates[row["terrain"]][0] += 1
        if row["delta"] <= -DROP:
            rates[row["terrain"]][1] += 1
    print("\ndrop rate by terrain:")
    table(
        [
            (
                name,
                total,
                count,
                f"{100 * count / total:.0f}%",
            )
            for name, (total, count) in sorted(rates.items())
        ],
        headers=["terrain", "transitions", "drops", "share"],
    )

    print("\nEnduro drops:")
    table(
        [
            (
                row["date"].isoformat(),
                row["name"] or "-",
                f"{row['previous']:.1f}",
                f"{row['value']:.1f}",
                f"{row['delta']:+.1f}",
                f"{row['km']:.1f}",
                f"{row['minutes']:.0f}",
                f"{row['hr']:.0f}" if row["hr"] is not None else "-",
                f"{row['gain_per_km']:.1f}"
                if row["gain_per_km"] is not None
                else "-",
                f"{row['loss_per_km']:.1f}"
                if row["loss_per_km"] is not None
                else "-",
                f"{row['net_per_km']:+.1f}"
                if row["net_per_km"] is not None
                else "-",
                row["terrain"],
                row["session"],
                f"{row['estimate']:.1f}"
                if row["estimate"] is not None
                else "-",
                f"{row['runalyze']:.1f}"
                if row["runalyze"] is not None
                else "-",
            )
            for row in drops
        ],
        headers=[
            "date",
            "name",
            "prev",
            "value",
            "delta",
            "km",
            "min",
            "HR",
            "gain",
            "loss",
            "net",
            "terrain",
            "session",
            "est",
            "Runalyze",
        ],
    )

    # Transience: does the next reading return to the pre-drop level?
    recovered = 0
    for index, row in enumerate(rows):
        if row["delta"] is None or row["delta"] > -DROP:
            continue
        target = row["previous"]
        for offset in range(1, 4):
            position = index + offset
            if position >= len(rows):
                break
            if rows[position]["value"] >= target - 0.5:
                recovered += 1
                break
    print(f"\ndrops reverting within 3 readings: {recovered}/{len(drops)}")

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[row["date"] for row in rows],
            y=[row["value"] for row in rows],
            mode="lines+markers",
            line={"color": "#4c78a8", "width": 1},
            marker={"size": 3},
            name="Enduro running VO2max",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[row["date"] for row in drops],
            y=[row["value"] for row in drops],
            mode="markers",
            marker={"size": 9, "color": "#e45756", "symbol": "x"},
            name="drop >= 1",
        )
    )
    figure.update_yaxes(title_text="Garmin VO2max")
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Enduro-era Garmin VO2max drops",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "enduro-vo2max-drops")

    # Drop size vs net grade.
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[row["net_per_km"] for row in transitions if row["net_per_km"] is not None],
            y=[row["delta"] for row in transitions if row["net_per_km"] is not None],
            mode="markers",
            marker={"size": 6, "color": "#4c78a8", "opacity": 0.6},
            text=[row["date"].isoformat() for row in transitions if row["net_per_km"] is not None],
            name="transitions",
        )
    )
    figure.update_xaxes(title_text="net grade (m/km, + downhill)")
    figure.update_yaxes(title_text="VO2max change")
    figure.update_layout(
        title="Drop size vs net grade",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "enduro-vo2max-grade")


if __name__ == "__main__":
    main()
