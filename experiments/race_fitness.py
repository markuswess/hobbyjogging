"""Experiment: race-derived fitness from all race logs.

Question
--------
What do the races imply for current fitness (VDOT, critical speed, Riegel
exponent, equivalent times), and how stable is that view when including the
older sheet races rather than only `race_results` rows?

Data
----
Every activity with the `race` method, plus every `race_results` row. A result
row supplies official time/distance when present; otherwise the race activity's
own distance and duration are used. Sheet races are therefore included, with a
minute-rounded time flagged rather than discarded.

Elevation classification
------------------------
- hard exclusions: `trail_run`, distance > 50 km, relay/staffel by name, and
  gain/km > 20 (the last is flagged as elevation-only when nothing else
  corroborates it);
- road-hilly: gain/km 8-20, included in the main fit and removed in sensitivity;
- road-flat: gain/km <= 8;
- unknown elevation: included, flagged.

Models
------
- VDOT (Daniels/Gilbert) per race.
- Critical speed: distance = CS*time + D' on road races >= 10 min.
- Riegel: log(time) = a + b*log(distance).
- Level: residual from the global Riegel fit; higher = faster.
- Leave-one-out prediction error for both models.
- Equivalent 5k/10k/HM/M times anchored to the most recent road 10k, with the
  exponent fitted over all race activities as the dashboard does, compared with
  the free-global filtered fit and latest-five methods.

Deliverable
-----------
A lab verdict plus plots; no card or report handoff.

    uv run --env-file .env python experiments/race_fitness.py
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from statistics import mean, median

import plotly.graph_objects as go

from hobbyjogging_report.analysis import RUN_TYPES
from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source

MAX_ULTRA_KM = 50.0
HILL_GAIN_PER_KM = 20.0
HILLY_GAIN_PER_KM = 8.0
STANDARD_DISTANCES = {
    "5k": 5.0,
    "10k": 10.0,
    "HM": 21.0975,
    "M": 42.195,
}
RELAY_WORDS = ("relay", "staffel")


def vdot(distance_m: float, time_s: float) -> float | None:
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


def format_pace(seconds_per_km: float | None) -> str:
    if not seconds_per_km:
        return "-"
    return f"{int(seconds_per_km // 60)}:{seconds_per_km % 60:04.1f}"


def format_time(minutes: float | None) -> str:
    if minutes is None:
        return "-"
    hours = int(minutes // 60)
    rest = minutes - hours * 60
    return f"{hours}:{rest:04.1f}" if hours else f"{rest:.1f}m"


def correlation(xs: list[float], ys: list[float]) -> float:
    mx = mean(xs)
    my = mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return cov / (vx * vy) ** 0.5 if vx and vy else 0.0


def fit_line(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    mx = mean(xs)
    my = mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    residuals = [
        y - (intercept + slope * x) for x, y in zip(xs, ys)
    ]
    ss_res = sum(value ** 2 for value in residuals)
    ss_tot = sum((y - my) ** 2 for y in ys)
    return slope, intercept, 1 - ss_res / ss_tot if ss_tot else 0.0


def classify(row: dict) -> str:
    if row["sport"] == "trail_run":
        return "trail"
    if row["km"] > MAX_ULTRA_KM:
        return "ultra"
    if any(word in row["name"].lower() for word in RELAY_WORDS):
        return "relay"
    if row["gain_per_km"] is None:
        return "unknown-elevation"
    if row["gain_per_km"] > HILL_GAIN_PER_KM:
        return "hill"
    if row["gain_per_km"] >= HILLY_GAIN_PER_KM:
        return "road-hilly"
    return "road-flat"


def build_rows(source) -> tuple[list[dict], list[dict]]:
    activities = source.activities(date(2000, 1, 1), date.today())
    results = {result.activity_id: result for result in source.race_results()}
    activity_by_id = {activity.id: activity for activity in activities}

    selected = [
        activity
        for activity in activities
        if activity.type in RUN_TYPES
        and (
            "race" in activity.workout_methods
            or activity.id in results
        )
    ]

    rows = []
    for activity in selected:
        result = results.get(activity.id)
        distance_m = (
            result.official_distance_m
            if result is not None and result.official_distance_m
            else activity.distance_m
        )
        time_s = (
            result.official_time_s
            if result is not None and result.official_time_s
            else activity.duration_s
        )

        if not distance_m or not time_s:
            continue

        km = distance_m / 1000.0
        gain = activity.elevation_gain_m
        loss = activity.elevation_loss_m
        gain_per_km = gain / km if gain is not None and km else None
        loss_per_km = loss / km if loss is not None and km else None
        name = (
            result.name
            if result is not None and result.name
            else activity.name
        ) or ""

        if result is not None and result.official_time_s:
            time_source = "result"
        elif activity.duration_s % 60 == 0:
            time_source = "activity-minute"
        else:
            time_source = "activity-second"

        rows.append(
            {
                "id": activity.id,
                "date": activity.date,
                "year": activity.date.year,
                "name": name,
                "sport": activity.type,
                "tier": "result" if result is not None else "race-log",
                "measured": result.officially_measured if result is not None else None,
                "km": km,
                "time_s": time_s,
                "time_min": time_s / 60.0,
                "pace": time_s / km,
                "speed": distance_m / time_s,
                "gain": gain,
                "loss": loss,
                "gain_per_km": gain_per_km,
                "loss_per_km": loss_per_km,
                "net_per_km": (
                    (loss - gain) / km
                    if gain is not None and loss is not None and km
                    else None
                ),
                "time_source": time_source,
                "vo2max_garmin": activity.vo2max_garmin,
            }
        )

    for row in rows:
        row["class"] = classify(row)
        row["vdot"] = vdot(row["km"] * 1000.0, row["time_s"])
        row["excluded"] = row["class"] in {
            "trail",
            "ultra",
            "relay",
            "hill",
        }

    return rows, sorted(rows, key=lambda row: row["date"])


def fit_cs(rows: list[dict]) -> tuple[float, float, float] | None:
    usable = [
        row
        for row in rows
        if row["time_min"] >= 10
        and row["km"] <= MAX_ULTRA_KM
        and not row["excluded"]
    ]
    if len(usable) < 8:
        return None
    slope, intercept, r2 = fit_line(
        [row["time_s"] for row in usable],
        [row["km"] * 1000.0 for row in usable],
    )
    return slope, intercept, r2


def fit_riegel(rows: list[dict]) -> tuple[float, float, float] | None:
    usable = [
        row for row in rows if not row["excluded"] and row["km"] > 0
    ]
    if len(usable) < 8:
        return None
    slope, intercept, r2 = fit_line(
        [math.log(row["km"]) for row in usable],
        [math.log(row["time_min"]) for row in usable],
    )
    return slope, intercept, r2


def leave_one_out(rows: list[dict], kind: str) -> tuple[float, float] | None:
    usable = [row for row in rows if not row["excluded"]]
    errors = []

    for index, row in enumerate(usable):
        rest = usable[:index] + usable[index + 1 :]
        if len(rest) < 8:
            continue

        if kind == "riegel":
            fit = fit_riegel(rest)
            if fit is None:
                continue
            b, a, _ = fit
            predicted = math.exp(a + b * math.log(row["km"]))
        else:
            fit = fit_cs(rest)
            if fit is None:
                continue
            cs, d_prime, _ = fit
            if cs <= 0:
                continue
            predicted = (row["km"] * 1000.0 - d_prime) / cs / 60.0

        errors.append(abs(predicted - row["time_min"]))

    if not errors:
        return None
    return median(errors), 100 * median(errors) / median(
        row["time_min"] for row in usable
    )


def sensitivity(rows: list[dict]) -> None:
    variants = [
        ("all usable", [row for row in rows if not row["excluded"]]),
        (
            "result rows only",
            [
                row
                for row in rows
                if not row["excluded"] and row["tier"] == "result"
            ],
        ),
        (
            "flat/unknown only",
            [
                row
                for row in rows
                if not row["excluded"]
                and row["class"] in {"road-flat", "unknown-elevation"}
            ],
        ),
        (
            "no minute-rounded",
            [
                row
                for row in rows
                if not row["excluded"] and row["time_source"] != "activity-minute"
            ],
        ),
    ]

    output = []
    for label, chunk in variants:
        cs = fit_cs(chunk)
        riegel = fit_riegel(chunk)
        output.append(
            (
                label,
                len(chunk),
                f"{cs[0]:.3f}" if cs else "-",
                f"{cs[1]:.0f}" if cs else "-",
                f"{riegel[0]:.3f}" if riegel else "-",
                f"{riegel[2]:.2f}" if riegel else "-",
            )
        )

    table(
        output,
        headers=["population", "races", "CS m/s", "D' m", "Riegel b", "Riegel R²"],
    )


def plot_classification(rows: list[dict]) -> None:
    colors = {
        "road-flat": "#4c78a8",
        "road-hilly": "#f58518",
        "hill": "#e45756",
        "trail": "#b279a2",
        "ultra": "#333333",
        "relay": "#999999",
        "unknown-elevation": "#54a24b",
    }
    figure = go.Figure()

    for category in colors:
        chunk = [row for row in rows if row["class"] == category]
        if not chunk:
            continue
        figure.add_trace(
            go.Scatter(
                x=[row["date"] for row in chunk],
                y=[
                    row["gain_per_km"]
                    if row["gain_per_km"] is not None
                    else 0.1
                    for row in chunk
                ],
                mode="markers",
                marker={
                    "size": 8,
                    "color": colors[category],
                    "symbol": [
                        "circle" if row["tier"] == "result" else "diamond"
                        for row in chunk
                    ],
                },
                name=category,
            )
        )

    figure.add_hline(y=HILLY_GAIN_PER_KM, line={"dash": "dot", "color": "#777777"})
    figure.add_hline(y=HILL_GAIN_PER_KM, line={"dash": "dot", "color": "#e45756"})
    figure.update_yaxes(
        title_text="elevation gain (m/km, log; 0.1 = unknown)",
        type="log",
    )
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Race inventory and elevation classification",
        legend={"orientation": "h", "y": -0.25},
    )
    save(figure, "race-classification")


def fit_riegel_rows(rows: list[dict]) -> tuple[float, float, float] | None:
    """Free log-log fit without the road/trail exclusions."""
    points = [row for row in rows if row["km"] > 0 and row["time_min"] > 0]
    if len(points) < 3:
        return None
    return fit_line(
        [math.log(row["km"]) for row in points],
        [math.log(row["time_min"]) for row in points],
    )


def latest_road_reference(
    rows: list[dict],
    *,
    result_only: bool = False,
) -> dict | None:
    candidates = [
        row
        for row in rows
        if not row["excluded"]
        and 9.5 <= row["km"] <= 10.5
        and (not result_only or row["tier"] == "result")
    ]
    if not candidates:
        candidates = [
            row
            for row in rows
            if not row["excluded"]
            and (not result_only or row["tier"] == "result")
        ]
    return max(candidates, key=lambda row: row["date"]) if candidates else None


def latest_in_bucket(
    rows: list[dict],
    low: float,
    high: float,
) -> dict | None:
    candidates = [
        row
        for row in rows
        if not row["excluded"] and low <= row["km"] <= high
    ]
    return max(candidates, key=lambda row: row["date"]) if candidates else None


def anchored_time(reference: dict, exponent: float, km: float) -> float:
    return reference["time_min"] * (km / reference["km"]) ** exponent


def plot_models(rows: list[dict], cs, riegel, anchored) -> None:
    figure = go.Figure()
    usable = [row for row in rows if not row["excluded"]]
    excluded = [row for row in rows if row["excluded"]]

    figure.add_trace(
        go.Scatter(
            x=[row["km"] for row in usable],
            y=[row["time_min"] for row in usable],
            mode="markers",
            marker={"size": 8, "color": "#4c78a8"},
            text=[row["name"] for row in usable],
            name="usable races",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[row["km"] for row in excluded],
            y=[row["time_min"] for row in excluded],
            mode="markers",
            marker={"size": 9, "color": "#e45756", "symbol": "x"},
            text=[row["name"] for row in excluded],
            name="excluded (trail/hill/ultra/relay)",
        )
    )

    if riegel:
        b, a, _ = riegel
        grid = [4 + 0.25 * i for i in range(160)]
        figure.add_trace(
            go.Scatter(
                x=grid,
                y=[math.exp(a + b * math.log(d)) for d in grid],
                mode="lines",
                line={"color": "#54a24b", "width": 2},
                name=f"Riegel b={b:.2f}",
            )
        )
    if anchored:
        reference, exponent = anchored
        grid = [4 + 0.25 * i for i in range(160)]
        figure.add_trace(
            go.Scatter(
                x=grid,
                y=[anchored_time(reference, exponent, d) for d in grid],
                mode="lines",
                line={"color": "#b279a2", "width": 2, "dash": "dot"},
                name=f"anchored {reference['name'] or '10k'}"
                f" (b={exponent:.2f})",
            )
        )
    if cs:
        speed, d_prime, _ = cs
        grid = [4 + 0.25 * i for i in range(160)]
        figure.add_trace(
            go.Scatter(
                x=grid,
                y=[(d * 1000.0 - d_prime) / speed / 60.0 for d in grid],
                mode="lines",
                line={"color": "#f58518", "width": 2, "dash": "dash"},
                name=f"CS {speed:.2f} m/s",
            )
        )

    figure.update_xaxes(title_text="distance (km, log)", type="log")
    figure.update_yaxes(title_text="race time (min, log)", type="log")
    figure.update_layout(
        title="Race time vs distance",
        legend={"orientation": "h", "y": -0.2},
    )
    save(figure, "race-models")


def plot_level(rows: list[dict], riegel) -> None:
    if riegel is None:
        return
    b, a, _ = riegel
    usable = [row for row in rows if not row["excluded"]]

    for row in usable:
        row["level"] = -(math.log(row["time_min"]) - (a + b * math.log(row["km"])))

    buckets = {
        "5k": lambda km: 4 <= km <= 6,
        "10k": lambda km: 9 <= km <= 11,
        "HM": lambda km: 20 <= km <= 22,
        "M": lambda km: 41 <= km <= 44,
        "other": lambda km: True,
    }
    assigned = set()
    figure = go.Figure()

    for label, predicate in buckets.items():
        chunk = [
            row
            for row in usable
            if predicate(row["km"]) and row["id"] not in assigned
        ]
        for row in chunk:
            assigned.add(row["id"])
        if not chunk:
            continue
        figure.add_trace(
            go.Scatter(
                x=[row["date"] for row in chunk],
                y=[row["level"] for row in chunk],
                mode="markers",
                marker={
                    "size": 8,
                    "symbol": [
                        "circle" if row["tier"] == "result" else "diamond"
                        for row in chunk
                    ],
                },
                name=label,
            )
        )

    ordered = sorted(usable, key=lambda row: row["date"])
    rolling = []
    for index in range(4, len(ordered)):
        window = ordered[index - 4 : index + 1]
        rolling.append(
            (ordered[index]["date"], median(row["level"] for row in window))
        )
    if rolling:
        figure.add_trace(
            go.Scatter(
                x=[point[0] for point in rolling],
                y=[point[1] for point in rolling],
                mode="lines",
                line={"color": "#333333", "width": 1.5},
                name="5-race median",
            )
        )

    figure.update_yaxes(title_text="Riegel level (higher = faster)")
    figure.update_xaxes(title_text="date")
    figure.update_layout(
        title="Race level over time",
        legend={"orientation": "h", "y": -0.25},
    )
    save(figure, "race-level")


def main() -> None:
    with create_source() as source:
        rows, ordered = build_rows(source)
        thresholds = source.athlete_thresholds()

    if len(rows) < 20:
        print(f"only {len(rows)} race rows")
        return

    print(f"{len(rows)} race activities; "
          f"{sum(row['tier'] == 'result' for row in rows)} result rows, "
          f"{sum(row['tier'] == 'race-log' for row in rows)} race-log rows")

    counts = defaultdict(int)
    for row in rows:
        counts[row["class"]] += 1
    table(
        [
            (name, count)
            for name, count in sorted(counts.items())
        ],
        headers=["class", "races"],
    )

    print("\nrace inventory:")
    table(
        [
            (
                row["date"].isoformat(),
                row["name"] or "-",
                row["tier"],
                row["class"],
                f"{row['km']:.2f}",
                format_time(row["time_min"]),
                format_pace(row["pace"]),
                f"{row['gain_per_km']:.1f}"
                if row["gain_per_km"] is not None
                else "-",
                f"{row['vdot']:.1f}" if row["vdot"] else "-",
                row["time_source"],
            )
            for row in ordered
        ],
        headers=[
            "date",
            "race",
            "tier",
            "class",
            "km",
            "time",
            "pace",
            "gain/km",
            "VDOT",
            "time source",
        ],
    )

    usable = [row for row in rows if not row["excluded"]]
    cs = fit_cs(usable)
    riegel = fit_riegel(usable)
    print("\nmodel fits:")
    table(
        [
            (
                "critical speed",
                f"{cs[0]:.3f}" if cs else "-",
                f"{format_pace(1000.0 / cs[0]) if cs else '-'}",
                f"{cs[1]:.0f}" if cs else "-",
                f"{cs[2]:.2f}" if cs else "-",
            ),
            (
                "Riegel",
                f"{riegel[0]:.3f}" if riegel else "-",
                "-",
                "-",
                f"{riegel[2]:.2f}" if riegel else "-",
            ),
        ],
        headers=["model", "CS m/s / b", "CS pace", "D' m", "R²"],
    )

    for kind in ("riegel", "cs"):
        error = leave_one_out(usable, kind)
        if error:
            print(
                f"{kind} leave-one-out median error: "
                f"{error[0]:.1f} min ({error[1]:.1f}%)"
            )

    anchored = None
    if riegel:
        b, a, _ = riegel
        split = len(usable) // 2
        early = fit_riegel(usable[:split])
        late = fit_riegel(usable[split:])
        print(
            f"Riegel shape early {early[0]:.3f} vs late {late[0]:.3f}"
            if early and late
            else "Riegel shape split unavailable"
        )

        recent = usable[-5:]
        current_a = median(
            math.log(row["time_min"]) - b * math.log(row["km"])
            for row in recent
        )
        dashboard_fit = fit_riegel_rows(rows)
        reference = (
            latest_road_reference(rows, result_only=True)
            or latest_road_reference(rows)
        )
        dashboard_b = dashboard_fit[0] if dashboard_fit else None
        anchored = (
            (reference, dashboard_b) if reference and dashboard_b else None
        )

        print("\ncurrent-form predictions (actual = latest race in bucket):")
        buckets = {
            "5k": (4.0, 6.0),
            "10k": (9.0, 11.0),
            "HM": (20.0, 22.0),
            "M": (41.0, 44.0),
        }
        comparison = []
        errors = {
            "free global (filtered)": [],
            "latest five": [],
            "anchored dashboard b": [],
            "anchored filtered b": [],
        }

        for label, (low, high) in buckets.items():
            distance = STANDARD_DISTANCES[label]
            actual = latest_in_bucket(usable, low, high)
            free_global = math.exp(a + b * math.log(distance))
            latest_five = math.exp(current_a + b * math.log(distance))
            anchored_dashboard = (
                anchored_time(reference, dashboard_b, distance)
                if reference and dashboard_b
                else None
            )
            anchored_filtered = (
                anchored_time(reference, b, distance)
                if reference
                else None
            )

            if actual is not None:
                errors["free global (filtered)"].append(
                    abs(free_global - actual["time_min"])
                )
                errors["latest five"].append(
                    abs(latest_five - actual["time_min"])
                )
                if anchored_dashboard is not None:
                    errors["anchored dashboard b"].append(
                        abs(anchored_dashboard - actual["time_min"])
                    )
                if anchored_filtered is not None:
                    errors["anchored filtered b"].append(
                        abs(anchored_filtered - actual["time_min"])
                    )

            comparison.append(
                (
                    label,
                    format_time(actual["time_min"]) if actual else "-",
                    format_time(free_global),
                    format_time(latest_five),
                    format_time(anchored_dashboard)
                    if anchored_dashboard is not None
                    else "-",
                    format_time(anchored_filtered)
                    if anchored_filtered is not None
                    else "-",
                )
            )

        table(
            comparison,
            headers=[
                "distance",
                "latest actual",
                "free global (filtered)",
                "latest five",
                "anchored dashboard b",
                "anchored filtered b",
            ],
        )
        if reference and dashboard_b:
            print(
                f"anchored to {reference['date']} "
                f"{reference['name'] or 'race'} "
                f"({reference['km']:.2f} km, "
                f"{format_time(reference['time_min'])}); "
                f"dashboard exponent b={dashboard_b:.4f} "
                "over all race activities; filtered exponent "
                f"b={b:.4f}"
            )
        table(
            [
                (
                    method,
                    f"{mean(values):.1f} min" if values else "-",
                    f"{median(values):.1f} min" if values else "-",
                )
                for method, values in errors.items()
            ],
            headers=["method", "mean abs error", "median abs error"],
        )

    print("\nsensitivity:")
    sensitivity(rows)

    # Validation against Garmin VO2max.
    paired = [
        row
        for row in usable
        if row["vo2max_garmin"] is not None and row["vdot"] is not None
    ]
    if len(paired) >= 6:
        corr = correlation(
            [row["vdot"] for row in paired],
            [row["vo2max_garmin"] for row in paired],
        )
        differences = [
            row["vdot"] - row["vo2max_garmin"] for row in paired
        ]
        print(
            f"\nVDOT vs Garmin VO2max: n={len(paired)}, r={corr:+.2f}, "
            f"median difference {median(differences):+.2f}"
        )

    # CS against the latest threshold pace at the end of the period.
    if cs and thresholds:
        speeds = [
            threshold.threshold_pace_mps
            for threshold in thresholds
            if threshold.sport == "run" and threshold.threshold_pace_mps
        ]
        if speeds:
            print(
                f"critical speed {cs[0]:.2f} m/s vs latest threshold pace "
                f"{speeds[-1]:.2f} m/s"
            )

    plot_classification(rows)
    plot_models(rows, cs, riegel, anchored)
    plot_level(rows, riegel)

    print("\nverdict: inspect the inventory, fits, sensitivity and level plot. "
          "No card or report handoff; lab evidence only.")


if __name__ == "__main__":
    main()
