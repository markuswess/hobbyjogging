"""Experiment: which threshold reference matches the setting and the work reps?

Question
--------
Threshold is not a race distance, so "60-minute all-out pace" is only one
approximation of it. Which candidate reference best matches the stored
Intervals threshold pace, and which best matches the executed subT-short work
reps and recent official races?

Candidates
----------
- **Daniels T pace** from the current-form VDOT (mean of the best two race
  VDOTs of the last five prior road races). The T pace is the velocity at 88%
  of VDOT, which reproduces the Daniels table within about 2 s/km.
- **Current-form 60m** Riegel pace: exponent fitted on prior races, level
  anchored to the mean of the best two of the last five prior road races.
- **% of 10k** and **% of 5k**: the latest prior race of that distance within
  365 days, divided by a 0.95 / 0.92 speed share. The freshness guard avoids
  carrying a stale race forward.
- **Critical speed**: distance = CS*time + D' on prior road races, evaluated
  at 3600 s.

Validation targets
------------------
- The stored Intervals threshold setting.
- The weighted work-rep pace of subT-short sessions (target ``subthreshold``,
  method ``intervals``, average work rep <= 240 s). These reps run well below
  LTHR, so they are an executed-pace benchmark, not a measured LT2.
- The race-implied 60m pace: median of the last 365 days of official road
  races, each converted to 60 minutes on the prior-race Riegel exponent.

Outputs
-------
- Per-snapshot levels of every candidate, the setting, the race benchmark and
  the subT-short work reps.
- Mean/median signed offset, mean absolute deviation and correlation for each
  candidate against each target.
- A combined ranking, a time-series plot and an error bar chart.

    uv run --env-file .env python experiments/threshold_references.py
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean, median, stdev

import plotly.graph_objects as go

from hobbyjogging_core.classify import classify_interval, work_intervals
from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MIN_RACES = 6
MAX_ULTRA_KM = 50.0
HILL_GAIN_PER_KM = 20.0
RECENT_DAYS = 365
TEN_K = (9.5, 10.5)
FIVE_K = (4.8, 5.2)
TEN_K_SHARE = 0.95
FIVE_K_SHARE = 0.92
THRESHOLD_VO2_SHARE = 0.88
MIN_REP_S = 60

CANDIDATES = (
    ("daniels", "Daniels T"),
    ("sixty", "60m"),
    ("ten_k", "10k%"),
    ("five_k", "5k%"),
    ("cs", "CS"),
)
TARGETS = (
    ("setting", "setting"),
    ("subt", "subT short"),
    ("race60", "race 60m"),
)


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


def vdot(km: float, minutes: float) -> float | None:
    if km <= 0 or minutes <= 0:
        return None
    velocity = km * 1000.0 / minutes
    oxygen = -4.60 + 0.182258 * velocity + 0.000104 * velocity ** 2
    fraction = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * minutes)
        + 0.2989558 * math.exp(-0.1932605 * minutes)
    )
    return oxygen / fraction if fraction else None


def threshold_pace(vdot_value: float) -> float:
    """Daniels T pace in s/km: the velocity at 88% of VDOT."""
    target = THRESHOLD_VO2_SHARE * vdot_value
    velocity = (
        -0.182258
        + math.sqrt(
            0.182258 ** 2 + 4 * 0.000104 * (4.60 + target)
        )
    ) / (2 * 0.000104)
    return 60000.0 / velocity


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


def short_subt_sessions(source) -> list[dict]:
    """Weighted work-rep pace of the subT-short interval sessions."""
    sessions = []

    for activity in source.activities(date(2000, 1, 1), date.today()):
        if activity.type not in RUN_TYPES or activity.type == "trail_run":
            continue
        if "subthreshold" not in set(activity.workout_targets):
            continue
        if "intervals" not in set(activity.workout_methods):
            continue
        if "race" in set(activity.workout_methods):
            continue

        work = [
            interval
            for interval in work_intervals(
                source.activity_intervals(activity.id)
            )
            if interval.duration_s >= MIN_REP_S and interval.distance_m > 0
        ]
        if len(work) < 2:
            continue

        average_rep = mean(interval.duration_s for interval in work)
        if classify_interval(average_rep) != "short":
            continue

        total_time = sum(interval.duration_s for interval in work)
        total_distance = sum(interval.distance_m for interval in work)
        hr_pairs = [
            (interval.avg_hr, interval.duration_s)
            for interval in work
            if interval.avg_hr is not None
        ]

        sessions.append(
            {
                "date": activity.date,
                "name": activity.name,
                "pace": total_time / total_distance * 1000.0,
                "time": total_time,
                "distance": total_distance,
                "reps": len(work),
                "hr": (
                    sum(hr * seconds for hr, seconds in hr_pairs)
                    / sum(seconds for _, seconds in hr_pairs)
                    if hr_pairs
                    else None
                ),
            }
        )

    return sorted(sessions, key=lambda session: session["date"])


def level(row: dict, exponent: float) -> float:
    return math.log(row["minutes"]) - exponent * math.log(row["km"])


def predict_60(prior: list[dict], exponent: float) -> float | None:
    if len(prior) < MIN_RACES:
        return None
    recent = [level(row, exponent) for row in prior[-5:]]
    anchor = mean(sorted(recent)[:2])
    distance = math.exp((math.log(60.0) - anchor) / exponent)
    return 3600.0 / distance if distance > 0 else None


def latest_in(
    prior: list[dict],
    bounds: tuple[float, float],
    as_of: date,
) -> dict | None:
    fresh = [
        row
        for row in prior
        if bounds[0] <= row["km"] <= bounds[1]
        and row["date"] >= as_of - timedelta(days=RECENT_DAYS)
    ]
    return fresh[-1] if fresh else None


def estimate(prior: list[dict], as_of: date) -> dict | None:
    if len(prior) < MIN_RACES:
        return None

    exponent, _ = fit_line(
        [math.log(row["km"]) for row in prior],
        [math.log(row["minutes"]) for row in prior],
    )
    if exponent <= 0:
        return None

    vdots = sorted(
        vdot(row["km"], row["minutes"]) for row in prior[-5:]
    )
    current_vdot = mean(vdots[-2:])

    ten = latest_in(prior, TEN_K, as_of)
    five = latest_in(prior, FIVE_K, as_of)

    cs, d_prime = fit_line(
        [row["minutes"] * 60.0 for row in prior],
        [row["km"] * 1000.0 for row in prior],
    )
    cs_distance = cs * 3600.0 + d_prime
    cs_pace = 3600.0 / (cs_distance / 1000.0) if cs > 0 else None

    window = [
        row
        for row in prior
        if row["date"] >= as_of - timedelta(days=RECENT_DAYS)
    ]
    equivalents = [
        math.exp((math.log(60.0) - level(row, exponent)) / exponent)
        for row in window
    ]
    race60 = (
        3600.0 / median(equivalents) if equivalents else None
    )

    return {
        "exponent": exponent,
        "vdot": current_vdot,
        "daniels": threshold_pace(current_vdot),
        "daniels_med5": threshold_pace(median(vdots)),
        "sixty": predict_60(prior, exponent),
        "ten_k": ten["pace"] / TEN_K_SHARE if ten else None,
        "ten_k_age": (
            (as_of - ten["date"]).days if ten else None
        ),
        "five_k": five["pace"] / FIVE_K_SHARE if five else None,
        "five_k_age": (
            (as_of - five["date"]).days if five else None
        ),
        "cs": cs_pace,
        "race60": race60,
        "race60_n": len(window),
    }


def snapshot_subt(
    snapshots: list,
    sessions: list[dict],
) -> list[dict | None]:
    """Aggregate subT-short sessions per setting validity window."""
    buckets: list[list[dict]] = [[] for _ in snapshots]

    for session in sessions:
        index = 0
        for position, snapshot in enumerate(snapshots):
            if snapshot.effective_from <= session["date"]:
                index = position
        buckets[index].append(session)

    result = []
    for bucket in buckets:
        if not bucket:
            result.append(None)
            continue

        total_time = sum(session["time"] for session in bucket)
        total_distance = sum(session["distance"] for session in bucket)
        hr_pairs = [
            (session["hr"], session["time"])
            for session in bucket
            if session["hr"] is not None
        ]
        result.append(
            {
                "pace": total_time / total_distance * 1000.0,
                "sessions": len(bucket),
                "reps": sum(session["reps"] for session in bucket),
                "hr": (
                    sum(hr * seconds for hr, seconds in hr_pairs)
                    / sum(seconds for _, seconds in hr_pairs)
                    if hr_pairs
                    else None
                ),
            }
        )

    return result


def delta_stats(
    values: list[float | None],
    target: list[float | None],
) -> dict | None:
    pairs = [
        (value, goal)
        for value, goal in zip(values, target)
        if value is not None and goal is not None
    ]
    if not pairs:
        return None

    deltas = [value - goal for value, goal in pairs]
    return {
        "n": len(deltas),
        "mean": mean(deltas),
        "median": median(deltas),
        "mad": mean(abs(delta) for delta in deltas),
        "sd": stdev(deltas) if len(deltas) > 1 else 0.0,
    }


def correlation(
    values: list[float | None],
    target: list[float | None],
) -> float | None:
    pairs = [
        (value, goal)
        for value, goal in zip(values, target)
        if value is not None and goal is not None
    ]
    if len(pairs) < 3:
        return None

    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    mx = mean(xs)
    my = mean(ys)
    covariance = sum((x - mx) * (y - my) for x, y in pairs)
    variance_x = sum((x - mx) ** 2 for x in xs)
    variance_y = sum((y - my) ** 2 for y in ys)
    if not variance_x or not variance_y:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def main() -> None:
    with create_source() as source:
        races = race_rows(source)
        sessions = short_subt_sessions(source)
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

    subt_by_snapshot = snapshot_subt(thresholds, sessions)
    rows = []

    for index, snapshot in enumerate(thresholds):
        prior = [
            race for race in races if race["date"] < snapshot.effective_from
        ]
        estimates = estimate(prior, snapshot.effective_from)
        row = {
            "date": snapshot.effective_from,
            "setting": 1000.0 / snapshot.threshold_pace_mps,
            "subt": (
                subt_by_snapshot[index]["pace"]
                if subt_by_snapshot[index]
                else None
            ),
            "subt_sessions": (
                subt_by_snapshot[index]["sessions"]
                if subt_by_snapshot[index]
                else 0
            ),
            "subt_hr": (
                subt_by_snapshot[index]["hr"]
                if subt_by_snapshot[index]
                else None
            ),
        }
        if estimates:
            row.update(estimates)
        rows.append(row)

    usable = [row for row in rows if "daniels" in row]
    print(
        f"{len(races)} official road races, {len(sessions)} subT-short "
        f"sessions, {len(thresholds)} run snapshots; "
        f"{len(usable)} snapshots with enough prior races"
    )

    def age_label(age: int | None) -> str:
        return f" ({age}d)" if age is not None else ""

    print("\nper snapshot (pace s/km, faster is a smaller value):")
    table(
        [
            (
                row["date"].isoformat(),
                format_pace(row["setting"]),
                format_pace(row.get("daniels")),
                format_pace(row.get("sixty")),
                format_pace(row.get("ten_k"))
                + age_label(row.get("ten_k_age")),
                format_pace(row.get("five_k"))
                + age_label(row.get("five_k_age")),
                format_pace(row.get("cs")),
                format_pace(row.get("race60"))
                + (
                    f" ({row['race60_n']})"
                    if row.get("race60_n")
                    else ""
                ),
                format_pace(row.get("subt")),
                row["subt_sessions"] or "-",
                f"{row['subt_hr']:.0f}" if row.get("subt_hr") else "-",
            )
            for row in rows
        ],
        headers=[
            "snapshot",
            "setting",
            "Daniels T",
            "60m",
            "10k%",
            "5k%",
            "CS",
            "race 60m",
            "subT short",
            "n",
            "HR",
        ],
    )

    baseline = [row["setting"] for row in rows]
    print("\noffset from the stored setting (positive = reference slower):")
    setting_rows = []
    for key, label in CANDIDATES:
        values = [row.get(key) for row in rows]
        stats = delta_stats(values, baseline)
        if stats is None:
            setting_rows.append((label, "-", "-", "-", "-", "-"))
            continue
        coefficient = correlation(values, baseline)
        setting_rows.append(
            (
                label,
                stats["n"],
                f"{stats['mean']:+.1f}",
                f"{stats['median']:+.1f}",
                f"{stats['mad']:.1f}",
                f"{coefficient:+.2f}" if coefficient is not None else "-",
            )
        )
    table(
        setting_rows,
        headers=["reference", "n", "mean", "median", "MAD", "r"],
    )

    print("\noffset from subT-short work reps (positive = reference slower):")
    subt_rows = []
    for key, label in CANDIDATES:
        stats = delta_stats(
            [row.get(key) for row in rows],
            [row.get("subt") for row in rows],
        )
        if stats is None:
            subt_rows.append((label, "-", "-", "-", "-", "-"))
            continue
        subt_rows.append(
            (
                label,
                stats["n"],
                f"{stats['mean']:+.1f}",
                f"{stats['median']:+.1f}",
                f"{stats['mad']:.1f}",
                f"{stats['sd']:.1f}",
            )
        )
    table(
        subt_rows,
        headers=["reference", "n", "mean", "median", "MAD", "SD"],
    )

    print(
        "\noffset from the race-implied 60m "
        "(positive = reference slower):"
    )
    race_rows_stats = []
    for key, label in CANDIDATES:
        stats = delta_stats(
            [row.get(key) for row in rows],
            [row.get("race60") for row in rows],
        )
        if stats is None:
            race_rows_stats.append((label, "-", "-", "-", "-", "-"))
            continue
        race_rows_stats.append(
            (
                label,
                stats["n"],
                f"{stats['mean']:+.1f}",
                f"{stats['median']:+.1f}",
                f"{stats['mad']:.1f}",
                f"{stats['sd']:.1f}",
            )
        )
    table(
        race_rows_stats,
        headers=["reference", "n", "mean", "median", "MAD", "SD"],
    )

    print("\ncombined ranking (equal-weight mean of the three MADs):")
    ranking = []
    for key, label in CANDIDATES:
        values = [row.get(key) for row in rows]
        setting_stats = delta_stats(values, baseline)
        subt_stats = delta_stats(
            values, [row.get("subt") for row in rows]
        )
        race_stats = delta_stats(
            values, [row.get("race60") for row in rows]
        )
        if not setting_stats or not subt_stats or not race_stats:
            continue
        score = mean(
            [setting_stats["mad"], subt_stats["mad"], race_stats["mad"]]
        )
        ranking.append((score, label, setting_stats, subt_stats, race_stats))

    ranking.sort()
    table(
        [
            (
                position,
                label,
                f"{score:.1f}",
                f"{setting['mad']:.1f}",
                f"{subt['mad']:.1f}",
                f"{race['mad']:.1f}",
            )
            for position, (score, label, setting, subt, race) in enumerate(
                ranking, start=1
            )
        ],
        headers=[
            "rank",
            "reference",
            "score",
            "vs setting",
            "vs subT",
            "vs race",
        ],
    )

    ratios = [
        (
            row["setting"] / (row["ten_k"] * TEN_K_SHARE),
            row["daniels"] / (row["ten_k"] * TEN_K_SHARE),
            row["sixty"] / (row["ten_k"] * TEN_K_SHARE),
            (
                row["subt"] / (row["ten_k"] * TEN_K_SHARE)
                if row.get("subt")
                else None
            ),
            (
                row["race60"] / (row["ten_k"] * TEN_K_SHARE)
                if row.get("race60")
                else None
            ),
        )
        for row in rows
        if row.get("ten_k")
    ]
    if ratios:
        print(
            "\npace relative to the latest 10k race pace "
            "(>1 = slower than 10k; median over fresh-10k snapshots):"
        )
        for index, label in enumerate(
            [
                "setting",
                "Daniels T",
                "60m",
                "subT short",
                "race-implied 60m",
            ]
        ):
            values = [
                ratio[index] for ratio in ratios if ratio[index] is not None
            ]
            if values:
                print(f"  {label:<21} {median(values):.3f}")
        print(
            f"  {'textbook 0.95 share':<21} {1 / TEN_K_SHARE:.3f}"
        )

    heart_rates = [
        row["subt_hr"] for row in rows if row.get("subt_hr")
    ]
    if heart_rates:
        print(
            f"\nsubT-short work-rep HR: median {median(heart_rates):.0f} bpm "
            f"vs LTHR 174; short reps do not reach steady-state threshold HR."
        )

    median5 = delta_stats(
        [row.get("daniels_med5") for row in rows],
        baseline,
    )
    if median5:
        print(
            f"Daniels T anchor sensitivity: median-5 VDOT vs setting mean "
            f"{median5['mean']:+.1f}, median {median5['median']:+.1f}, "
            f"MAD {median5['mad']:.1f} s/km; the best-2 anchor is faster."
        )

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[row["date"] for row in rows],
            y=[row["setting"] for row in rows],
            mode="lines+markers",
            line={"shape": "hv", "color": "#2ca02c", "width": 2},
            marker={"size": 6},
            name="stored setting",
        )
    )
    for key, label, color, dash in (
        ("daniels", "Daniels T", "#d62728", "solid"),
        ("sixty", "current-form 60m", "#1f77b4", "solid"),
        ("ten_k", "10k% (0.95)", "#9467bd", "dash"),
        ("five_k", "5k% (0.92)", "#8c564b", "dot"),
        ("cs", "critical speed", "#f58518", "dash"),
        ("race60", "race-implied 60m", "#7f7f7f", "dashdot"),
    ):
        points = [
            (row["date"], row[key])
            for row in rows
            if row.get(key) is not None
        ]
        if not points:
            continue
        figure.add_trace(
            go.Scatter(
                x=[point[0] for point in points],
                y=[point[1] for point in points],
                mode="lines+markers",
                line={"color": color, "width": 1.5, "dash": dash},
                marker={"size": 5},
                name=label,
            )
        )

    figure.add_trace(
        go.Scatter(
            x=[
                race["date"] for race in races
                if race["date"] >= date(2022, 1, 1)
            ],
            y=[
                race["pace"] for race in races
                if race["date"] >= date(2022, 1, 1)
            ],
            mode="markers",
            marker={
                "size": 6,
                "color": "#000000",
                "symbol": "diamond",
                "opacity": 0.45,
            },
            text=[
                f"{race['name']} ({race['km']:.1f} km)"
                for race in races
                if race["date"] >= date(2022, 1, 1)
            ],
            name="official race pace",
        )
    )

    if sessions:
        figure.add_trace(
            go.Scatter(
                x=[session["date"] for session in sessions],
                y=[session["pace"] for session in sessions],
                mode="markers",
                marker={"size": 5, "color": "#17becf", "opacity": 0.6},
                text=[
                    f"{session['name']} ({session['reps']} reps, "
                    f"HR {session['hr']:.0f})"
                    if session["hr"] is not None
                    else session["name"]
                    for session in sessions
                ],
                name="subT-short work reps",
            )
        )

    figure.update_yaxes(
        title_text="pace (s/km, faster up)",
        range=[240, 195],
    )
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Threshold setting, candidate references and subT-short work reps",
        legend={"orientation": "h", "y": -0.25},
    )
    save(figure, "threshold-references")

    if ranking:
        figure = go.Figure()
        plotted = list(reversed(ranking))
        for target_index, target_label in enumerate(
            ["vs setting", "vs subT", "vs race"]
        ):
            figure.add_trace(
                go.Bar(
                    y=[entry[1] for entry in plotted],
                    x=[
                        (entry[2], entry[3], entry[4])[target_index]["mad"]
                        for entry in plotted
                    ],
                    orientation="h",
                    name=target_label,
                )
            )
        figure.update_xaxes(title_text="mean absolute difference (s/km)")
        figure.update_layout(
            title="Reference error against setting, work reps and race form",
            barmode="group",
            legend={"orientation": "h", "y": -0.15},
        )
        save(figure, "threshold-reference-errors")

    print("\nplots: data/lab/threshold-references.png, "
          "data/lab/threshold-reference-errors.png")
    print(
        "caveat: %10k and the race-implied 60m both encode a ~5% "
        "10k-to-60m conversion, so their agreement is partly built in."
    )
    print(
        "\nreading: a candidate with a small MAD against the setting is close "
        "to the stored number; a small MAD against the subT work reps and the "
        "race-implied 60m tracks executed and race-observed pace. The setting "
        "is treated as a ceiling, not as a measured LT2."
    )


if __name__ == "__main__":
    main()
