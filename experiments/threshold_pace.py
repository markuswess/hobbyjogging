"""Experiment: is the Intervals threshold-pace setting a fitness signal?

Question
--------
`athlete_thresholds` stores the athlete's threshold settings as Intervals
stamps them on activities. The run series has 14 snapshots and threshold pace
moves from 4.587 to 4.854 m/s (3:38 -> 3:26 min/km), while LTHR and max HR stay
constant. Is that movement corroborated by actual work-rep efforts, or is it
just a manually maintained setting?

Data
----
- `DataSource.athlete_thresholds()` for the run and trail settings.
- Threshold-target sessions and subT/LT1 sessions, reduced to their WORK reps
  with the canonical `work_intervals()` helper.
- Race activities for change-event alignment.
- Steady runs for a quarterly efficiency cross-check.

Outputs
-------
1. Threshold snapshot table and step plot.
2. Setting vs measured work-rep pace per setting interval.
3. Change events and whether a race or hard session occurred nearby.
4. Agreement with the quarterly steady efficiency series.
5. Sensitivity: threshold-target vs subT/LT1 efforts.

Decision
--------
- Corroborated: median |setting - measured| <= 10 s/km, no drift in the delta,
  and at least 60% of changes near a race/threshold effort.
- Mixed: efforts move with the setting but coverage or alignment is weak.
- Uncorroborated: the setting moves independently of measured work-rep pace;
  keep it as an input setting, not a metric.

    uv run --env-file .env python experiments/threshold_pace.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean, median

import plotly.graph_objects as go

from hobbyjogging_core.classify import work_intervals
from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.analysis.efficiency import (
    MIN_EXCESS_HR,
    resting_hr_baselines,
)
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

NEAR_DAYS = 14
MIN_SESSIONS = 3
MIN_REP_S = 60
MIN_SPEED = 1.5
MAX_SPEED = 6.0
PRIMARY_TARGET = "threshold"
SECONDARY_TARGETS = {"subthreshold", "lt1"}


def pace_seconds(mps: float | None) -> float | None:
    return 1000.0 / mps if mps and mps > 0 else None


def format_pace(mps: float | None) -> str:
    seconds = pace_seconds(mps)
    if seconds is None:
        return "-"
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def session_effort(activity, intervals) -> dict | None:
    """Weighted WORK-rep pace and HR for one activity."""
    work = [
        interval
        for interval in work_intervals(intervals)
        if interval.duration_s >= MIN_REP_S and interval.distance_m > 0
    ]

    if len(work) < 2:
        return None

    total_time = sum(interval.duration_s for interval in work)
    total_distance = sum(interval.distance_m for interval in work)

    if total_time <= 0 or total_distance <= 0:
        return None

    hr_pairs = [
        (interval.avg_hr, interval.duration_s)
        for interval in work
        if interval.avg_hr is not None
    ]
    avg_hr = (
        sum(hr * seconds for hr, seconds in hr_pairs)
        / sum(seconds for _, seconds in hr_pairs)
        if hr_pairs
        else None
    )

    return {
        "id": activity.id,
        "date": activity.date,
        "name": activity.name,
        "sport": activity.type,
        "pace": total_time / total_distance * 1000.0,
        "distance": total_distance,
        "work_time": total_time,
        "hr": avg_hr,
        "reps": len(work),
    }


def aggregate(efforts: list[dict]) -> dict | None:
    if not efforts:
        return None

    total_time = sum(effort["work_time"] for effort in efforts)
    total_distance = sum(effort["distance"] for effort in efforts)

    if total_time <= 0 or total_distance <= 0:
        return None

    hr_pairs = [
        (effort["hr"], effort["work_time"])
        for effort in efforts
        if effort["hr"] is not None
    ]
    avg_hr = (
        sum(hr * seconds for hr, seconds in hr_pairs)
        / sum(seconds for _, seconds in hr_pairs)
        if hr_pairs
        else None
    )

    return {
        "n": len(efforts),
        "pace": total_time / total_distance * 1000.0,
        "hr": avg_hr,
    }


def interval_for(day: date, snapshots) -> object | None:
    current = None
    for snapshot in snapshots:
        if snapshot.effective_from <= day:
            current = snapshot
        else:
            break
    return current


def quarter_key(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def quarter_end(key: tuple[int, int]) -> date:
    month = 3 * key[1]
    if month == 12:
        return date(key[0], 12, 31)
    return date(key[0], month + 1, 1) - timedelta(days=1)


def quarter_start(key: tuple[int, int]) -> datetime:
    return datetime(key[0], 3 * (key[1] - 1) + 1, 1)


def correlation(xs: list[float], ys: list[float]) -> float:
    mean_x = mean(xs)
    mean_y = mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    return cov / (var_x * var_y) ** 0.5 if var_x and var_y else 0.0


def steady_efficiency(activities, baseline) -> list[dict]:
    rows = []

    for activity in activities:
        if activity.type not in RUN_TYPES or activity.type == "trail_run":
            continue
        if activity.duration_s <= 0 or activity.distance_m <= 0:
            continue
        if activity.avg_hr is None:
            continue

        minutes = activity.duration_s / 60.0
        if not (30.0 <= minutes <= 90.0):
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

        if activity.workout_methods and (
            set(activity.workout_methods) & {"intervals", "race", "progression"}
        ):
            continue
        if "recovery" in activity.workout_targets:
            continue

        rows.append(
            {
                "date": activity.date,
                "quarter": quarter_key(activity.date),
                "distance_m": activity.distance_m,
                "minutes": minutes,
                "excess": excess,
            }
        )

    return rows


def main() -> None:
    with create_source() as source:
        activities = source.activities(date(2000, 1, 1), date.today())
        wellness = source.wellness(date(1999, 1, 1), date.today())
        # DatabaseSource does not expose the newer DataSource methods yet;
        # the repository on the same connection has them.
        loader = getattr(source, "athlete_thresholds", None)
        thresholds = (
            loader()
            if callable(loader)
            else source.repository.athlete_thresholds()
        )

        run_snapshots = sorted(
            [
                snapshot
                for snapshot in thresholds
                if snapshot.sport == "run"
                and snapshot.threshold_pace_mps is not None
            ],
            key=lambda snapshot: snapshot.effective_from,
        )
        trail_snapshots = sorted(
            [
                snapshot
                for snapshot in thresholds
                if snapshot.sport == "trail_run"
                and snapshot.threshold_pace_mps is not None
            ],
            key=lambda snapshot: snapshot.effective_from,
        )

        # Session efforts.
        primary = []
        secondary = []
        races = []

        for activity in activities:
            if activity.type not in RUN_TYPES:
                continue
            if activity.type == "trail_run":
                continue

            targets = set(activity.workout_targets)
            methods = set(activity.workout_methods)

            if "race" in methods:
                races.append(activity)

            if PRIMARY_TARGET in targets:
                intervals = source.activity_intervals(activity.id)
                effort = session_effort(activity, intervals)
                if effort is not None and "race" not in methods:
                    effort["kind"] = "threshold"
                    primary.append(effort)
            elif targets & SECONDARY_TARGETS:
                intervals = source.activity_intervals(activity.id)
                effort = session_effort(activity, intervals)
                if effort is not None and "race" not in methods:
                    effort["kind"] = "subt/lt1"
                    secondary.append(effort)

        for effort in primary + secondary:
            snapshot = interval_for(effort["date"], run_snapshots)
            effort["snapshot"] = snapshot.effective_from if snapshot else None

        print(
            f"{len(run_snapshots)} run threshold snapshots, "
            f"{len(trail_snapshots)} trail; "
            f"{len(primary)} threshold-target efforts, "
            f"{len(secondary)} subT/LT1 efforts, {len(races)} race activities"
        )

        print("\nrun threshold snapshots:")
        rows = []
        for index, snapshot in enumerate(run_snapshots):
            previous = run_snapshots[index - 1] if index else None
            pace_change = (
                pace_seconds(snapshot.threshold_pace_mps)
                - pace_seconds(previous.threshold_pace_mps)
                if previous
                else None
            )
            rows.append(
                (
                    snapshot.effective_from.isoformat(),
                    format_pace(snapshot.threshold_pace_mps),
                    f"{snapshot.lthr:.0f}" if snapshot.lthr else "-",
                    f"{snapshot.max_hr:.0f}" if snapshot.max_hr else "-",
                    f"{pace_change:+.1f}"
                    if pace_change is not None
                    else "-",
                    (
                        f"{(snapshot.effective_from - previous.effective_from).days}"
                        if previous
                        else "-"
                    ),
                )
            )
        table(
            rows,
            headers=["date", "pace @LT", "LTHR", "max HR", "Δ s/km", "gap days"],
        )

        # Setting intervals and measured efforts.
        interval_rows = []
        deltas = []
        delta_x = []
        delta_y = []
        setting_values = []
        measured_values = []

        for index, snapshot in enumerate(run_snapshots):
            start = snapshot.effective_from
            end = (
                run_snapshots[index + 1].effective_from - timedelta(days=1)
                if index + 1 < len(run_snapshots)
                else date.max
            )
            efforts = [
                effort
                for effort in primary
                if effort["snapshot"] == start
            ]
            measured = aggregate(efforts)
            setting = pace_seconds(snapshot.threshold_pace_mps)

            if measured is None or len(efforts) < MIN_SESSIONS:
                interval_rows.append(
                    (
                        start.isoformat(),
                        len(efforts),
                        format_pace(snapshot.threshold_pace_mps),
                        "-",
                        "-",
                        "-",
                    )
                )
                continue

            delta = measured["pace"] - setting
            deltas.append(delta)
            delta_x.append(start)
            delta_y.append(delta)
            setting_values.append(setting)
            measured_values.append(measured["pace"])
            interval_rows.append(
                (
                    start.isoformat(),
                    len(efforts),
                    format_pace(snapshot.threshold_pace_mps),
                    f"{int(measured['pace'] // 60)}:"
                    f"{measured['pace'] % 60:04.1f}",
                    f"{delta:+.1f}",
                    f"{measured['hr']:.0f}"
                    if measured["hr"] is not None
                    else "-",
                )
            )

        print("\nsetting vs threshold-target work reps:")
        table(
            interval_rows,
            headers=[
                "from",
                "sessions",
                "setting",
                "measured",
                "delta s/km",
                "measured HR",
            ],
        )

        # Change events and nearby efforts.
        hard_efforts = primary + secondary
        change_rows = []
        aligned = 0
        changes = 0

        for index in range(1, len(run_snapshots)):
            previous = run_snapshots[index - 1]
            current = run_snapshots[index]
            pace_change = pace_seconds(current.threshold_pace_mps) - pace_seconds(
                previous.threshold_pace_mps
            )
            hr_change = (current.lthr or 0) != (previous.lthr or 0)

            if abs(pace_change) < 0.01 and not hr_change:
                continue

            changes += 1
            nearby = [
                activity
                for activity in races
                if abs((activity.date - current.effective_from).days) <= NEAR_DAYS
            ]
            nearby_efforts = [
                effort
                for effort in hard_efforts
                if abs((effort["date"] - current.effective_from).days)
                <= NEAR_DAYS
            ]

            if nearby or nearby_efforts:
                aligned += 1
                labels = [
                    f"{activity.date} {activity.name}"
                    for activity in nearby
                ] + [
                    f"{effort['date']} {effort['name']}"
                    for effort in nearby_efforts
                ]
                note = "; ".join(labels[:3])
            else:
                note = "none"

            change_rows.append(
                (
                    current.effective_from.isoformat(),
                    f"{pace_change:+.1f}",
                    "yes" if nearby or nearby_efforts else "no",
                    note,
                )
            )

        print("\nthreshold changes and nearby efforts (±14 days):")
        table(change_rows, headers=["date", "Δ s/km", "nearby", "evidence"])

        median_abs_delta = median(abs(delta) for delta in deltas) if deltas else None
        half = len(deltas) // 2
        drift = (
            median(deltas[half:]) - median(deltas[:half])
            if half >= 2
            else None
        )
        alignment = aligned / changes if changes else None
        measured_corr = (
            correlation(setting_values, measured_values)
            if len(setting_values) >= 3
            else None
        )

        print("\nsummary:")
        table(
            [
                ("intervals with >= 3 efforts", len(deltas)),
                (
                    "median |setting - measured|",
                    f"{median_abs_delta:.1f} s/km"
                    if median_abs_delta is not None
                    else "-",
                ),
                (
                    "delta drift (second half - first half)",
                    f"{drift:+.1f} s/km" if drift is not None else "-",
                ),
                (
                    "setting vs measured correlation",
                    f"{measured_corr:+.2f}" if measured_corr is not None else "-",
                ),
                (
                    "changes with nearby effort",
                    f"{aligned}/{changes} ({100 * alignment:.0f}%)"
                    if alignment is not None
                    else "-",
                ),
            ],
            headers=["metric", "value"],
        )

        # Cross-check against quarterly steady efficiency.
        baseline = resting_hr_baselines(wellness)
        steady = steady_efficiency(activities, baseline)
        by_quarter: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for row in steady:
            by_quarter[row["quarter"]].append(row)

        efficiency_pairs = []
        for key in sorted(by_quarter):
            chunk = by_quarter[key]
            if len(chunk) < 5:
                continue
            end = quarter_end(key)
            snapshot = interval_for(end, run_snapshots)
            if snapshot is None:
                continue
            beats = sum(row["excess"] * row["minutes"] for row in chunk)
            distance = sum(row["distance_m"] for row in chunk)
            if beats <= 0:
                continue
            efficiency_pairs.append(
                (
                    f"{key[0]}Q{key[1]}",
                    distance / beats,
                    snapshot.threshold_pace_mps,
                )
            )

        if len(efficiency_pairs) >= 6:
            efficiency_corr = correlation(
                [pair[1] for pair in efficiency_pairs],
                [pair[2] for pair in efficiency_pairs],
            )
            print("\nquarterly efficiency vs threshold setting:")
            table(
                [
                    (
                        pair[0],
                        f"{pair[1]:.3f}",
                        format_pace(pair[2]),
                    )
                    for pair in efficiency_pairs
                ][-8:],
                headers=["quarter", "efficiency", "threshold pace"],
            )
            print(f"correlation (efficiency, threshold speed): {efficiency_corr:+.2f}")
        else:
            efficiency_corr = None

        # Sensitivity: secondary subT/LT1 efforts.
        secondary_deltas = []
        for index, snapshot in enumerate(run_snapshots):
            start = snapshot.effective_from
            efforts = [
                effort
                for effort in secondary
                if effort["snapshot"] == start
            ]
            measured = aggregate(efforts)
            if measured is None or len(efforts) < MIN_SESSIONS:
                continue
            secondary_deltas.append(
                measured["pace"] - pace_seconds(snapshot.threshold_pace_mps)
            )

        print("\nsensitivity:")
        table(
            [
                (
                    "threshold-target work reps",
                    len(deltas),
                    f"{median_abs_delta:.1f} s/km"
                    if median_abs_delta is not None
                    else "-",
                ),
                (
                    "subT/LT1 work reps",
                    len(secondary_deltas),
                    f"{median(abs(delta) for delta in secondary_deltas):.1f} s/km"
                    if secondary_deltas
                    else "-",
                ),
            ],
            headers=["population", "intervals", "median |delta|"],
        )

        # Verdict against the pre-registered criteria.
        if (
            median_abs_delta is not None
            and drift is not None
            and alignment is not None
        ):
            if median_abs_delta <= 10 and abs(drift) <= 5 and alignment >= 0.6:
                verdict = "corroborated"
            elif median_abs_delta > 20 or alignment < 0.3:
                verdict = "uncorroborated"
            else:
                verdict = "mixed"
            print(f"\nverdict: {verdict}")
            print(
                "Absolute delta is expected to be non-zero because the setting "
                "is a ceiling and the work reps are session-specific; the "
                "criteria test stability and alignment, not equality."
            )

        # Plot: setting step line plus measured efforts.
        figure = go.Figure()
        step_x = [snapshot.effective_from for snapshot in run_snapshots]
        step_y = [
            pace_seconds(snapshot.threshold_pace_mps)
            for snapshot in run_snapshots
        ]
        figure.add_trace(
            go.Scatter(
                x=step_x,
                y=step_y,
                mode="lines+markers",
                line={"shape": "hv", "color": "#4c78a8", "width": 2},
                marker={"size": 5},
                name="threshold setting",
            )
        )

        if trail_snapshots:
            figure.add_trace(
                go.Scatter(
                    x=[snapshot.effective_from for snapshot in trail_snapshots],
                    y=[
                        pace_seconds(snapshot.threshold_pace_mps)
                        for snapshot in trail_snapshots
                    ],
                    mode="lines+markers",
                    line={
                        "shape": "hv",
                        "color": "#54a24b",
                        "width": 1,
                        "dash": "dot",
                    },
                    marker={"size": 4},
                    name="trail setting",
                )
            )

        measured_x = []
        measured_y = []
        for index, snapshot in enumerate(run_snapshots):
            efforts = [
                effort
                for effort in primary
                if effort["snapshot"] == snapshot.effective_from
            ]
            measured = aggregate(efforts)
            if measured is not None and len(efforts) >= MIN_SESSIONS:
                measured_x.append(snapshot.effective_from)
                measured_y.append(measured["pace"])

        figure.add_trace(
            go.Scatter(
                x=measured_x,
                y=measured_y,
                mode="markers",
                marker={"size": 8, "color": "#e45756", "symbol": "diamond"},
                name="measured work reps",
            )
        )
        figure.update_yaxes(
            title_text="pace (s/km, faster up)",
            autorange="reversed",
        )
        figure.update_xaxes(title_text="date")
        figure.update_layout(
            title="Threshold setting vs measured work-rep pace",
            legend={"orientation": "h", "y": -0.2},
        )
        save(figure, "threshold-pace")

        # Plot: delta over time.
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=delta_x,
                y=delta_y,
                mode="lines+markers",
                line={"color": "#e45756", "width": 1.5},
                marker={"size": 6},
                name="measured - setting",
            )
        )
        figure.add_hline(y=0, line={"color": "#999999", "width": 1})
        figure.update_yaxes(title_text="delta (s/km)")
        figure.update_xaxes(title_text="date")
        figure.update_layout(title="Setting vs measured delta")
        save(figure, "threshold-pace-delta")


if __name__ == "__main__":
    main()
