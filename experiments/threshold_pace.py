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
3. Per-rep ceiling compliance, margins, HR lag by rep length, and execution
   consistency.
4. Change events and whether a race or hard session occurred nearby.
5. Agreement with the quarterly steady efficiency series.
6. Sensitivity: threshold-target vs subT/LT1 efforts.

Decision
--------
The setting is a target for threshold sessions and a ceiling for subT/LT1
sessions, so absolute closeness is not the test. The revised criteria are:

- threshold target: at most 15% of WORK reps over the pace setting or above
  LTHR, with a median overshoot <= 3 s/km and <= 2 bpm;
- subT/LT1 ceiling: at most 5% of reps over either limit;
- execution stability: work-rep HR SD <= 3 bpm across measured intervals;
- relative tracking: change in setting and change in measured pace correlate
  (>= 0.6).

Passing means the setting is a useful target/reference; it still is not a
measured LT2. Failing relative tracking means it is a manual input, not a
fitness signal.

    uv run --env-file .env python experiments/threshold_pace.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean, median, stdev

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
        "rep_details": [
            {
                "pace": interval.duration_s / interval.distance_m * 1000.0,
                "hr": interval.avg_hr,
                "duration_s": interval.duration_s,
            }
            for interval in work
        ],
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


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def compliance(primary: list[dict], snapshots) -> dict:
    """Per-rep overshoots, session margins, and signed range deltas."""
    total_reps = 0
    pace_violations = 0
    hr_violations = 0
    pace_overshoots = []
    hr_overshoots = []
    session_pace_margins = []
    session_pace_pct = []
    session_hr_margins = []
    session_hr_delta = []

    for effort in primary:
        snapshot = interval_for(effort["date"], snapshots)
        if snapshot is None:
            continue

        setting_pace = pace_seconds(snapshot.threshold_pace_mps)
        if setting_pace is None:
            continue

        session_pace_margins.append(effort["pace"] - setting_pace)
        session_pace_pct.append(
            100.0 * (effort["pace"] - setting_pace) / setting_pace
        )

        if effort["hr"] is not None and snapshot.lthr:
            session_hr_margins.append(snapshot.lthr - effort["hr"])
            session_hr_delta.append(effort["hr"] - snapshot.lthr)

        for rep in effort["rep_details"]:
            total_reps += 1
            if rep["pace"] < setting_pace:
                pace_violations += 1
                pace_overshoots.append(setting_pace - rep["pace"])
            if (
                snapshot.lthr
                and rep["hr"] is not None
                and rep["hr"] > snapshot.lthr
            ):
                hr_violations += 1
                hr_overshoots.append(rep["hr"] - snapshot.lthr)

    return {
        "reps": total_reps,
        "pace_violations": pace_violations,
        "hr_violations": hr_violations,
        "pace_overshoots": pace_overshoots,
        "hr_overshoots": hr_overshoots,
        "pace_margins": session_pace_margins,
        "pace_pct": session_pace_pct,
        "hr_margins": session_hr_margins,
        "hr_delta": session_hr_delta,
    }


def hr_lag(primary: list[dict], snapshots) -> list[tuple]:
    """HR and pace by work-rep duration bucket."""
    buckets = [
        ("<=2 min", 0.0, 120.0),
        ("2-5 min", 120.0, 300.0),
        ("5-10 min", 300.0, 600.0),
        (">10 min", 600.0, float("inf")),
    ]
    result = []

    for label, low, high in buckets:
        paces = []
        hrs = []
        hr_shares = []

        for effort in primary:
            snapshot = interval_for(effort["date"], snapshots)
            if snapshot is None or not snapshot.lthr:
                continue
            for rep in effort["rep_details"]:
                if not (low <= rep["duration_s"] < high):
                    continue
                paces.append(rep["pace"])
                if rep["hr"] is not None:
                    hrs.append(rep["hr"])
                    hr_shares.append(100.0 * rep["hr"] / snapshot.lthr)

        if not hrs:
            continue

        result.append(
            (
                label,
                len(hrs),
                f"{int(median(paces) // 60)}:"
                f"{median(paces) % 60:04.1f}",
                f"{median(hrs):.0f}",
                f"{median(hr_shares):.0f}%",
            )
        )

    return result


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
        measured_intervals = []

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
            measured_intervals.append(
                {
                    "start": start,
                    "setting": setting,
                    "measured": measured["pace"],
                    "hr": measured["hr"],
                }
            )
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

        # Ceiling/target behaviour and execution quality.
        stats = compliance(primary, run_snapshots)
        secondary_stats = compliance(secondary, run_snapshots)
        pace_rate = (
            stats["pace_violations"] / stats["reps"] if stats["reps"] else None
        )
        hr_rate = (
            stats["hr_violations"] / stats["reps"] if stats["reps"] else None
        )
        secondary_pace_rate = (
            secondary_stats["pace_violations"] / secondary_stats["reps"]
            if secondary_stats["reps"]
            else None
        )
        secondary_hr_rate = (
            secondary_stats["hr_violations"] / secondary_stats["reps"]
            if secondary_stats["reps"]
            else None
        )

        def overshoot_row(name: str, item: dict) -> tuple:
            reps = item["reps"]
            pace = item["pace_overshoots"]
            hr = item["hr_overshoots"]
            return (
                name,
                reps,
                f"{len(pace)} ({100 * len(pace) / reps:.0f}%)"
                if reps
                else "-",
                f"{median(pace):.1f}" if pace else "-",
                f"{percentile(pace, 0.9):.1f}" if pace else "-",
                f"{max(pace):.1f}" if pace else "-",
                f"{len(hr)} ({100 * len(hr) / reps:.0f}%)"
                if reps
                else "-",
                f"{median(hr):.1f}" if hr else "-",
                f"{percentile(hr, 0.9):.1f}" if hr else "-",
                f"{max(hr):.1f}" if hr else "-",
            )

        print("\nper-rep overshoot (pace faster than setting, HR above LTHR):")
        table(
            [
                overshoot_row("threshold target", stats),
                overshoot_row("subT/LT1", secondary_stats),
            ],
            headers=[
                "population",
                "reps",
                "pace over",
                "median s/km",
                "p90",
                "max",
                "HR over",
                "median bpm",
                "p90",
                "max",
            ],
        )

        def share_within(values: list[float], limit: float) -> float:
            if not values:
                return 0.0
            return 100.0 * sum(abs(value) <= limit for value in values) / len(
                values
            )

        print("\nsession range (signed: pace slower positive, HR above positive):")
        table(
            [
                (
                    "pace (% of setting)",
                    len(stats["pace_pct"]),
                    f"{share_within(stats['pace_pct'], 3):.0f}%",
                    f"{share_within(stats['pace_pct'], 5):.0f}%",
                    f"{share_within(stats['pace_pct'], 10):.0f}%",
                ),
                (
                    "HR (bpm from LTHR)",
                    len(stats["hr_delta"]),
                    f"{share_within(stats['hr_delta'], 3):.0f}%",
                    f"{share_within(stats['hr_delta'], 5):.0f}%",
                    f"{share_within(stats['hr_delta'], 10):.0f}%",
                ),
            ],
            headers=["measure", "sessions", "±3", "±5", "±10"],
        )
        print(
            f"session pace margin: median "
            f"{median(stats['pace_margins']):+.1f} s/km, "
            f"IQR {percentile(stats['pace_margins'], 0.25):+.1f}.."
            f"{percentile(stats['pace_margins'], 0.75):+.1f}; "
            f"session HR margin (LTHR - measured): median "
            f"{median(stats['hr_margins']):+.1f} bpm."
            if stats["pace_margins"] and stats["hr_margins"]
            else "session margins: insufficient data"
        )

        print("\nHR lag by work-rep length:")
        table(
            hr_lag(primary, run_snapshots),
            headers=["rep length", "reps", "median pace", "median HR", "%LTHR"],
        )

        hr_values = [
            interval["hr"]
            for interval in measured_intervals
            if interval["hr"] is not None
        ]
        pace_values = [interval["measured"] for interval in measured_intervals]
        hr_sd = stdev(hr_values) if len(hr_values) > 1 else None
        pace_sd = stdev(pace_values) if len(pace_values) > 1 else None

        print("\nexecution consistency across measured intervals:")
        table(
            [
                (
                    "work-rep HR",
                    f"{mean(hr_values):.1f}" if hr_values else "-",
                    f"{hr_sd:.1f}" if hr_sd is not None else "-",
                ),
                (
                    "work-rep pace (s/km)",
                    f"{mean(pace_values):.1f}" if pace_values else "-",
                    f"{pace_sd:.1f}" if pace_sd is not None else "-",
                ),
            ],
            headers=["measure", "mean", "SD"],
        )

        change_setting = [
            second["setting"] - first["setting"]
            for first, second in zip(measured_intervals, measured_intervals[1:])
        ]
        change_measured = [
            second["measured"] - first["measured"]
            for first, second in zip(measured_intervals, measured_intervals[1:])
        ]
        relative_corr = (
            correlation(change_setting, change_measured)
            if len(change_setting) >= 3
            else None
        )
        if relative_corr is not None:
            print(
                f"relative change correlation (Δsetting vs Δmeasured): "
                f"{relative_corr:+.2f} over {len(change_setting)} changes"
            )
        print(
            "The absolute delta is expected for a ceiling; compliance, "
            "execution stability and relative movement are the tests."
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

        # Verdict against the target/ceiling criteria.
        pace_over_median = (
            median(stats["pace_overshoots"])
            if stats["pace_overshoots"]
            else None
        )
        hr_over_median = (
            median(stats["hr_overshoots"])
            if stats["hr_overshoots"]
            else None
        )
        threshold_ok = (
            pace_rate is not None
            and hr_rate is not None
            and pace_rate <= 0.15
            and hr_rate <= 0.15
            and (pace_over_median is None or pace_over_median <= 3.0)
            and (hr_over_median is None or hr_over_median <= 2.0)
        )
        subt_ok = (
            (secondary_pace_rate is None or secondary_pace_rate <= 0.05)
            and (secondary_hr_rate is None or secondary_hr_rate <= 0.05)
        )

        if (
            threshold_ok
            and subt_ok
            and hr_sd is not None
            and relative_corr is not None
        ):
            if hr_sd <= 3 and relative_corr >= 0.6:
                verdict = "corroborated as a target/reference"
            else:
                verdict = "mixed"
        elif pace_rate is not None and (
            pace_rate > 0.3 or (relative_corr is not None and relative_corr < 0)
        ):
            verdict = "uncorroborated"
        else:
            verdict = "mixed"

        print(f"\nverdict: {verdict}")
        print(
            f"threshold target: {100 * pace_rate:.0f}% of reps over pace, "
            f"{100 * hr_rate:.0f}% over LTHR; median overshoot "
            f"{pace_over_median if pace_over_median is not None else '-'} s/km / "
            f"{hr_over_median if hr_over_median is not None else '-'} bpm. "
            f"subT/LT1: "
            f"{100 * secondary_pace_rate if secondary_pace_rate is not None else '-'}% "
            f"pace / "
            f"{100 * secondary_hr_rate if secondary_hr_rate is not None else '-'}% "
            "HR over. Only four measured intervals, so the change correlation "
            "is suggestive; the setting is a reference, not a measured LT2."
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
