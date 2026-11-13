"""Experiment: what causes the Garmin VO2max jumps?

Question
--------
The stored `vo2max_garmin` series jumps by several ml/kg/min. Are the jumps
sport-specific values (running vs cycling), terrain (hills, net downhill),
session type (short recovery, race, intervals), or a historical device
behaviour?

Data
----
All activities with a positive Garmin VO2max, ordered by start time. The
canonical model supplies the value, sport, date, distance, time and HR.
Intervals payloads supply elevation gain/loss and temperature for the subset
that has them; canonical lap ascent is the fallback for gain. This raw-payload
lookup is a diagnostic, not a metric implementation — elevation and
temperature are not canonical columns yet.

Outputs
-------
- Transitions split by same sport vs sport switch, with jump rates.
- Running-only jumps by year.
- Jump vs non-jump session attributes.
- Jump rates by terrain category and session type.
- How often a running jump reverts (transient) rather than establishing a
  new level.
- Case studies for 2026-07-18, 2026-08-02 and 2026-08-05.

The decision this supports: whether the stored value needs a sport-specific
representation, a report caveat, or an activity-level guard.

    uv run --env-file .env python experiments/vo2max_jumps.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from statistics import mean, median

import plotly.graph_objects as go

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

JUMP = 1.0
REVERT_TOLERANCE = 0.5
CASE_DATES = ("2026-07-18", "2026-08-02", "2026-08-05")
CHUNK = 400


def load_conditions(connection, ids: list[str]) -> dict[str, dict]:
    """Elevation gain/loss and temperature from stored Intervals payloads."""
    conditions: dict[str, dict] = {}

    if connection is None:
        return conditions

    for start in range(0, len(ids), CHUNK):
        chunk = ids[start : start + CHUNK]
        marks = ",".join("?" for _ in chunk)
        query = f"""
            SELECT al.activity_id,
                   json_extract(sr.payload_json, '$.total_elevation_gain')
                       AS gain,
                   json_extract(sr.payload_json, '$.total_elevation_loss')
                       AS loss,
                   json_extract(sr.payload_json, '$.average_temp')
                       AS temp
            FROM activity_sources al
            JOIN source_records sr ON sr.id = al.source_record_id
            WHERE sr.source = 'intervals'
              AND sr.record_type = 'activity'
              AND al.activity_id IN ({marks})
        """
        for row in connection.execute(query, chunk):
            conditions[row["activity_id"]] = {
                "gain": row["gain"],
                "loss": row["loss"],
                "temp": row["temp"],
            }

    return conditions


def lap_gain(connection) -> dict[str, float]:
    if connection is None:
        return {}
    return {
        row["activity_id"]: row["gain"]
        for row in connection.execute(
            """
            SELECT activity_id, SUM(elevation_gain_m) AS gain
            FROM activity_laps
            WHERE elevation_gain_m IS NOT NULL
            GROUP BY activity_id
            """
        )
    }


def build_rows(activities, connection) -> list[dict]:
    selected = [
        activity
        for activity in activities
        if activity.vo2max_garmin is not None
        and activity.vo2max_garmin > 0
    ]
    conditions = load_conditions(
        connection, [activity.id for activity in selected]
    )
    laps = lap_gain(connection)

    rows = []

    for activity in selected:
        minutes = activity.duration_s / 60.0
        km = activity.distance_m / 1000.0
        condition = conditions.get(activity.id, {})
        gain = condition.get("gain")
        if gain is None:
            gain = laps.get(activity.id)
        loss = condition.get("loss")

        rows.append(
            {
                "id": activity.id,
                "date": activity.date,
                "start": activity.started_at_utc
                or f"{activity.date.isoformat()}T00:00:00",
                "name": activity.name,
                "sport": activity.type,
                "running": activity.type in RUN_TYPES,
                "value": activity.vo2max_garmin,
                "km": km,
                "minutes": minutes,
                "hr": activity.avg_hr,
                "gain": gain,
                "loss": loss,
                "temp": condition.get("temp"),
                "gain_per_km": gain / km if gain is not None and km else None,
                "loss_per_km": loss / km if loss is not None and km else None,
                "net_per_km": (
                    (loss - gain) / km
                    if loss is not None and gain is not None and km
                    else None
                ),
                "methods": set(activity.workout_methods),
                "targets": set(activity.workout_targets),
                "tags": set(activity.tags),
            }
        )

    rows.sort(key=lambda row: (row["start"], row["id"]))

    for index, row in enumerate(rows):
        previous = rows[index - 1] if index else None
        row["previous"] = previous["value"] if previous else None
        row["previous_sport"] = previous["sport"] if previous else None
        row["delta"] = (
            row["value"] - previous["value"] if previous else None
        )

    return rows


def terrain(row: dict) -> str:
    if row["net_per_km"] is None:
        return "unknown"
    if row["net_per_km"] <= -10:
        return "uphill"
    if row["net_per_km"] >= 10:
        return "downhill"
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


def transitions(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["previous"] is not None]


def jump_rates(rows: list[dict], key) -> list[tuple]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)

    result = []
    for name, chunk in sorted(groups.items()):
        jumps = sum(abs(row["delta"]) >= JUMP for row in chunk)
        result.append(
            (
                name,
                len(chunk),
                jumps,
                f"{100 * jumps / len(chunk):.0f}%",
                f"{mean(row['delta'] for row in chunk):+.2f}",
                f"{median(abs(row['delta']) for row in chunk):.2f}",
            )
        )
    return result


def attribute_table(rows: list[dict]) -> list[tuple]:
    jumps = [row for row in rows if abs(row["delta"]) >= JUMP]
    others = [row for row in rows if abs(row["delta"]) < JUMP]

    def median_of(chunk, name):
        values = [row[name] for row in chunk if row[name] is not None]
        return median(values) if values else None

    def share(chunk, predicate):
        return f"{100 * sum(predicate(row) for row in chunk) / len(chunk):.0f}%"

    def fmt(value, digits=1):
        return f"{value:.{digits}f}" if value is not None else "-"

    return [
        ("n", len(jumps), len(others)),
        (
            "median km",
            fmt(median_of(jumps, "km")),
            fmt(median_of(others, "km")),
        ),
        (
            "median min",
            fmt(median_of(jumps, "minutes"), 0),
            fmt(median_of(others, "minutes"), 0),
        ),
        (
            "median HR",
            fmt(median_of(jumps, "hr"), 0),
            fmt(median_of(others, "hr"), 0),
        ),
        (
            "gain m/km",
            fmt(median_of(jumps, "gain_per_km")),
            fmt(median_of(others, "gain_per_km")),
        ),
        (
            "loss m/km",
            fmt(median_of(jumps, "loss_per_km")),
            fmt(median_of(others, "loss_per_km")),
        ),
        (
            "net m/km (+ downhill)",
            fmt(median_of(jumps, "net_per_km")),
            fmt(median_of(others, "net_per_km")),
        ),
        (
            "median temp",
            fmt(median_of(jumps, "temp")),
            fmt(median_of(others, "temp")),
        ),
        (
            "trail",
            share(jumps, lambda row: row["sport"] == "trail_run"),
            share(others, lambda row: row["sport"] == "trail_run"),
        ),
        (
            "recovery target",
            share(jumps, lambda row: "recovery" in row["targets"]),
            share(others, lambda row: "recovery" in row["targets"]),
        ),
        (
            "race",
            share(jumps, lambda row: "race" in row["methods"]),
            share(others, lambda row: "race" in row["methods"]),
        ),
        (
            "intervals",
            share(jumps, lambda row: "intervals" in row["methods"]),
            share(others, lambda row: "intervals" in row["methods"]),
        ),
    ]


def transience(
    running: list[dict],
    running_transitions: list[dict],
) -> dict[str, float]:
    recovered_readings = []
    recovered_days = []
    jumps = 0

    for row in running_transitions:
        if abs(row["delta"]) < JUMP:
            continue
        jumps += 1
        target = row["previous"]
        index = running.index(row)

        for offset in range(1, 6):
            position = index + offset
            if position >= len(running):
                break
            if abs(running[position]["value"] - target) <= REVERT_TOLERANCE:
                recovered_readings.append(offset)
                recovered_days.append(
                    (running[position]["date"] - row["date"]).days
                )
                break

    return {
        "jumps": jumps,
        "recovered": len(recovered_readings),
        "within_2_readings": sum(
            offset <= 2 for offset in recovered_readings
        ),
        "within_14_days": sum(day <= 14 for day in recovered_days),
        "median_days": median(recovered_days) if recovered_days else None,
    }


def case_studies(rows: list[dict], running: list[dict]) -> None:
    for date_text in CASE_DATES:
        target = date.fromisoformat(date_text)
        day_rows = [row for row in rows if row["date"] == target]

        print(f"\n{date_text}:")
        table(
            [
                (
                    row["name"],
                    row["sport"],
                    f"{row['previous']:.1f}"
                    if row["previous"] is not None
                    else "-",
                    f"{row['value']:.1f}",
                    f"{row['delta']:+.1f}"
                    if row["delta"] is not None
                    else "-",
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
                    f"{row['temp']:.0f}"
                    if row["temp"] is not None
                    else "-",
                )
                for row in day_rows
            ],
            headers=[
                "activity",
                "sport",
                "prev",
                "value",
                "delta",
                "km",
                "min",
                "HR",
                "gain/km",
                "loss/km",
                "net/km",
                "temp",
            ],
        )

        running_day = [row for row in running if row["date"] == target]
        if not running_day:
            continue

        for row in running_day:
            position = running.index(row)
            neighbours = []
            if position > 0:
                before = running[position - 1]
                neighbours.append(
                    (
                        "previous running",
                        before["date"].isoformat(),
                        f"{before['value']:.1f}",
                        "",
                    )
                )
            if position + 1 < len(running):
                after = running[position + 1]
                neighbours.append(
                    (
                        "next running",
                        after["date"].isoformat(),
                        f"{after['value']:.1f}",
                        f"{after['value'] - row['value']:+.1f}",
                    )
                )
            if neighbours:
                table(neighbours, headers=["reading", "date", "value", "delta"])


def main() -> None:
    with create_source() as source:
        activities = source.activities(date(2000, 1, 1), date.today())
        connection = getattr(source, "connection", None)
        rows = build_rows(activities, connection)

    all_transitions = transitions(rows)
    running = [row for row in rows if row["running"]]
    running_transitions = [
        row
        for row in all_transitions
        if row["running"] and row["previous_sport"] in RUN_TYPES
    ]

    print(
        f"{len(rows)} Garmin VO2max readings; "
        f"{len(all_transitions)} transitions, "
        f"{len(running_transitions)} running-to-running"
    )

    same_sport = [
        row
        for row in all_transitions
        if row["sport"] == row["previous_sport"]
    ]
    switched = [
        row
        for row in all_transitions
        if row["sport"] != row["previous_sport"]
    ]

    print("\ntransitions by sport relation:")
    table(
        [
            (
                "same sport",
                len(same_sport),
                sum(abs(row["delta"]) >= JUMP for row in same_sport),
                f"{mean(abs(row['delta']) for row in same_sport):.2f}",
            ),
            (
                "sport switch",
                len(switched),
                sum(abs(row["delta"]) >= JUMP for row in switched),
                f"{mean(abs(row['delta']) for row in switched):.2f}",
            ),
        ],
        headers=["relation", "transitions", f"jumps >= {JUMP}", "mean |delta|"],
    )

    print("\ntop sport switches:")
    switches = jump_rates(
        [
            row
            for row in all_transitions
            if row["sport"] != row["previous_sport"]
        ],
        lambda row: f"{row['previous_sport']} -> {row['sport']}",
    )
    switches.sort(key=lambda row: row[1], reverse=True)
    table(
        switches[:10],
        headers=["switch", "n", "jumps", "share", "mean delta", "median |delta|"],
    )

    print("\nrunning-only jumps by year:")
    table(
        jump_rates(running_transitions, lambda row: str(row["date"].year)),
        headers=["year", "n", "jumps", "share", "mean delta", "median |delta|"],
    )

    print("\nrunning-only jumps by terrain (net gain/loss from payloads):")
    table(
        jump_rates(running_transitions, terrain),
        headers=["terrain", "n", "jumps", "share", "mean delta", "median |delta|"],
    )

    print("\nrunning-only jumps by session type:")
    table(
        jump_rates(running_transitions, session_type),
        headers=["session", "n", "jumps", "share", "mean delta", "median |delta|"],
    )

    print("\njump vs non-jump running sessions (|delta| >= 1):")
    table(
        attribute_table(running_transitions),
        headers=["attribute", "jump", "no jump"],
    )

    stats = transience(running, running_transitions)
    if stats["median_days"] is not None:
        print(
            f"\ntransience: {stats['jumps']} running jumps, "
            f"{stats['recovered']} reverted to the pre-jump level within "
            f"5 readings; {stats['within_2_readings']} within 2 readings, "
            f"{stats['within_14_days']} within 14 days; "
            f"median {stats['median_days']:.0f} days"
        )
    else:
        print(
            f"\ntransience: {stats['jumps']} running jumps, "
            f"{stats['recovered']} reverted within 5 readings"
        )

    case_studies(rows, running)

    # Plot 1: the sport-specific levels.
    figure = go.Figure()
    for label, predicate, color in (
        ("running", lambda row: row["running"], "#4c78a8"),
        ("cycling", lambda row: "ride" in row["sport"], "#e45756"),
        (
            "other",
            lambda row: not row["running"] and "ride" not in row["sport"],
            "#999999",
        ),
    ):
        points = [row for row in rows if predicate(row)]
        figure.add_trace(
            go.Scatter(
                x=[row["date"] for row in points],
                y=[row["value"] for row in points],
                mode="markers",
                marker={"size": 4, "opacity": 0.6, "color": color},
                name=label,
            )
        )
    figure.update_yaxes(title_text="Garmin VO2max")
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Garmin VO2max by sport",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "vo2max-by-sport")

    # Plot 2: running series with jumps marked.
    jumps = [
        row
        for row in running_transitions
        if abs(row["delta"]) >= JUMP
    ]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[row["date"] for row in running],
            y=[row["value"] for row in running],
            mode="lines+markers",
            line={"color": "#4c78a8", "width": 1},
            marker={"size": 3},
            name="running readings",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[row["date"] for row in jumps],
            y=[row["value"] for row in jumps],
            mode="markers",
            marker={"size": 9, "color": "#e45756", "symbol": "x"},
            name=f"jump >= {JUMP}",
        )
    )
    for date_text in CASE_DATES:
        figure.add_vline(
            x=datetime.fromisoformat(date_text),
            line={"color": "#54a24b", "width": 1, "dash": "dot"},
        )
    figure.update_yaxes(title_text="Garmin VO2max")
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Running Garmin VO2max with jumps and case-study dates",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "vo2max-running-jumps")


if __name__ == "__main__":
    main()
