"""Race results report and single-race execution report."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    bucket_label,
    equivalent_times,
    fit_riegel,
    half_split,
    official_by_activity,
    official_pair,
    pace_s_per_km,
    personal_bests,
    race_results,
    riegel_reference,
    upcoming_races,
)
from .classify import classify
from .command_support import activity_start, resting_hr_lookup
from .format import (
    fmt_clock,
    format_pace,
    format_place,
    format_session_activity,
    table_text,
)
from .links import resolve_activity_links
from .review import exclude_review, review_note
from .sessions import select_session


def _pace(value: float | None) -> str:
    return "-" if value is None else f"{format_pace(value)}/km"


def _distance(distance_m: float | None) -> str:
    return "-" if not distance_m else f"{distance_m / 1000:.2f} km"


def _load(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def races_report(
    source: DataSource,
    *,
    bucket: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    today: date | None = None,
    include_review: bool = False,
    future_days: int = 180,
) -> str:
    """Render race results, PBs, upcoming races, and Riegel estimates.

    ``bucket``, ``start``/``end`` and ``limit`` scope the results and PB
    tables. A date filter also scopes the upcoming list, because it is an
    explicit range; bucket and limit never do.
    """
    today = today or date.today()
    activities, excluded = exclude_review(
        source.activities(activity_start(source, today), today),
        include_review=include_review,
    )
    results = [
        result
        for result in race_results(
            activities,
            official_by_activity(source.race_results()),
        )
        if (bucket is None or result.bucket == bucket)
        and (start is None or result.activity.date >= start)
        and (end is None or result.activity.date <= end)
    ]
    shown = results if limit is None else results[:limit]
    upcoming = upcoming_races(
        source.events(today, today + timedelta(days=future_days)),
        today,
        days=future_days,
    )

    if start is not None or end is not None:
        upcoming = [
            event
            for event in upcoming
            if (start is None or event.date >= start)
            and (end is None or event.date <= end)
        ]

    fit = fit_riegel(results)
    predictions = equivalent_times(results, fit)

    lines = ["# Races", f"Through {today}"]
    filters = []

    if bucket is not None:
        filters.append(f"bucket {bucket}")
    if start is not None and end is not None:
        filters.append(f"{start} → {end}")
    elif start is not None:
        filters.append(f"from {start}")
    elif end is not None:
        filters.append(f"through {end}")
    if limit is not None:
        filters.append(f"latest {limit}")

    if filters:
        lines.append(f"Filter: {' · '.join(filters)}")

    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    if not results and not upcoming:
        lines.extend(["", "- No races found"])
        return "\n".join(lines)

    if upcoming:
        lines.extend([
            "",
            "## Upcoming",
            "",
            "| Date | Days | Race | Distance | Load |",
            "|---|---:|---|---:|---:|",
        ])
        for event in upcoming:
            lines.append(
                f"| {event.date} | {(event.date - today).days} | "
                f"{table_text(event.name) or '-'} | "
                f"{_distance(event.distance_m)} | "
                f"{_load(event.training_load)} |"
            )

    if results:
        lines.extend([
            "",
            "## Results",
            "",
            "| Date | Session | Race | Bucket | Distance | Time | Pace | "
            "Place | AG | HR | Load |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for result in shown:
            activity = result.activity
            overall = format_place(
                result.place_overall,
                result.participants_overall,
            )
            ageclass = format_place(
                result.place_ageclass,
                result.participants_ageclass,
            )
            lines.append(
                f"| {activity.date} | "
                f"{table_text(activity.name) or '-'} | "
                f"{table_text(result.official_name) or '-'} | "
                f"{result.bucket} | {_distance(result.distance_m)} | "
                f"{fmt_clock(result.time_s)} | "
                f"{_pace(result.pace_s_per_km)} | "
                f"{overall} | {ageclass} | "
                f"{'-' if activity.avg_hr is None else f'{activity.avg_hr:.0f}'} | "
                f"{_load(activity.training_load)} |"
            )

        if any(result.official_used for result in shown):
            lines.extend([
                "",
                "Official distance and time replace the measured activity "
                "where the race result provides them.",
            ])

        if len(shown) < len(results):
            lines.extend([
                "",
                f"Showing the latest {len(shown)} of "
                f"{len(results)} matching races.",
            ])

        groups = personal_bests(results)
        lines.extend([
            "",
            "## Personal bests",
            "",
            "| Bucket | Date | Session | Race | Distance | Time | Pace |",
            "|---|---|---|---|---:|---:|---:|",
        ])
        for result in groups:
            lines.append(
                f"| {bucket_label(result.bucket)} | "
                f"{result.activity.date} | "
                f"{table_text(result.activity.name) or '-'} | "
                f"{table_text(result.official_name) or '-'} | "
                f"{_distance(result.distance_m)} | "
                f"{fmt_clock(result.time_s)} | "
                f"{_pace(result.pace_s_per_km)} |"
            )
    else:
        lines.extend([
            "",
            "## Results",
            "",
            "- No race results found.",
        ])

    if fit is not None:
        lines.extend([
            "",
            "## Riegel estimate",
            "",
            (
                f"`time = a * distance^{fit.exponent:.2f}` over "
                f"{fit.points} races (R² = {fit.r2:.2f})."
            ),
        ])
        reference = riegel_reference(results)

        if reference is not None:
            lines.extend([
                "",
                f"Predictions are anchored to the {reference.bucket} on "
                f"{reference.activity.date}.",
            ])

    if predictions:
        lines.extend([
            "",
            "| Distance | Predicted | Pace | PB | PB pace |",
            "|---|---:|---:|---:|---:|",
        ])
        for row in predictions:
            lines.append(
                f"| {row.label} | {fmt_clock(row.predicted_s)} | "
                f"{_pace(row.predicted_pace_s_per_km)} | "
                f"{'-' if row.pb_s is None else fmt_clock(row.pb_s)} | "
                f"{_pace(row.pb_pace_s_per_km)} |"
            )

        lines.extend([
            "",
            "PB paces use the official distance where a race result provides "
            "one, otherwise the measured activity distance.",
        ])

    return "\n".join(lines)


def _event_match(source: DataSource, activity) -> list:
    events = source.events(activity.date, activity.date)

    return [
        event
        for event in events
        if "race" in set(event.workout_methods)
        | set(event.workout_targets)
    ]


def _zone_rows(activity, events) -> list[str]:
    if not events or not activity.pace_zone_times:
        return []

    event = events[0]
    planned = {
        zone.zone_label: zone.seconds
        for zone in event.zone_times
    }

    if not planned:
        return []

    actual_kind = "hr" if event.zone_kind == "hr" else "pace"
    actual_times = (
        activity.hr_zone_times
        if actual_kind == "hr"
        else activity.pace_zone_times
    )
    lines = [
        "\n### Planned vs actual zones",
        "",
        "| Zone | Planned | Actual | Delta |",
        "|---|---:|---:|---:|",
    ]

    for index, seconds in enumerate(actual_times, start=1):
        label = f"Z{index}"
        planned_s = planned.get(label, 0.0)
        delta = seconds - planned_s
        lines.append(
            f"| {label} | {fmt_clock(planned_s)} | {fmt_clock(seconds)} | "
            f"{'+' if delta >= 0 else '-'}{fmt_clock(abs(delta))} |"
        )

    return lines


def _plan_lines(activity, events) -> list[str]:
    if not events:
        return []

    event = events[0]
    lines = ["\n### Plan"]
    if event.duration_s:
        delta = activity.duration_s - event.duration_s
        lines.append(
            f"- Duration: planned {fmt_clock(event.duration_s)}, "
            f"actual {fmt_clock(activity.duration_s)} "
            f"({'+' if delta >= 0 else '-'}{fmt_clock(abs(delta))})"
        )
    if event.distance_m:
        delta = (activity.distance_m or 0) - event.distance_m
        lines.append(
            f"- Distance: planned {_distance(event.distance_m)}, "
            f"actual {_distance(activity.distance_m)} "
            f"({'+' if delta >= 0 else '-'}"
            f"{abs(delta) / 1000:.2f} km)"
        )

    return lines


def race_report(
    selector,
    source: DataSource,
    *,
    include_review: bool = False,
    today: date | None = None,
) -> str:
    """Render one race, including splits, plan delta, and zone execution."""
    day, activities, excluded = select_session(
        source,
        selector,
        include_review=include_review,
        today=today,
    )
    activity = next(
        (activity for activity in activities if activity.id == selector),
        None,
    )

    if activity is None or "race" not in set(activity.workout_methods) | set(
        activity.workout_targets
    ):
        return f"# Race\n\n- No race found for `{selector}`"

    intervals = source.activity_intervals(activity.id)
    laps = source.activity_laps(activity.id)
    events = _event_match(source, activity)
    wellness = source.wellness(activity.date, activity.date)
    wellness = wellness[0] if wellness else None
    review_items = [
        item
        for item in source.review_items(status="open")
        if item.activity_id == activity.id
    ]
    official = next(
        (
            result
            for result in source.race_results()
            if result.activity_id == activity.id
        ),
        None,
    )

    lines = [f"# Race {activity.date}"]

    if official is not None and official.name and official.name != activity.name:
        lines.append(f"- Race: {official.name}")

    if official_pair(official):
        time_s = official.official_time_s or activity.duration_s
        distance_m = official.official_distance_m or (activity.distance_m or 0)
        time_note = (
            " (official)"
            if abs(time_s - activity.duration_s) < 1
            else f" (official; measured {fmt_clock(activity.duration_s)})"
        )
        distance_note = (
            " (official)"
            if abs(distance_m - (activity.distance_m or 0)) < 10
            else f" (official; measured {_distance(activity.distance_m)})"
        )
        lines.extend([
            f"- Time: {fmt_clock(time_s)}{time_note}",
            f"- Distance: {_distance(distance_m)}{distance_note}",
            f"- Pace: {_pace(pace_s_per_km(time_s, distance_m))}",
        ])
    else:
        lines.extend([
            f"- Time: {fmt_clock(activity.duration_s)}",
            f"- Distance: {_distance(activity.distance_m)}",
            f"- Pace: {_pace(pace_s_per_km(activity.duration_s, activity.distance_m))}",
        ])

    if official is not None:
        overall = format_place(
            official.place_total,
            official.participants_total,
        )
        ageclass = format_place(
            official.place_ageclass,
            official.participants_ageclass,
        )

        if overall != "-":
            lines.append(f"- Place: {overall} overall")
        if ageclass != "-":
            lines.append(f"- Age group: {ageclass}")

    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    baseline = resting_hr_lookup(
        source,
        day or activity.date,
        day or activity.date,
        backfill=True,
    )
    lines.extend(
        format_session_activity(
            activity,
            intervals,
            category=classify(activity, intervals).path,
            links=resolve_activity_links(source, activity.id),
            resting_hr=baseline(activity.date),
            resting_hr_estimated=baseline.estimated(activity.date),
            planned_events=events,
            weather=source.activity_weather(activity.id),
            wellness=wellness,
            review_items=review_items,
            laps=laps,
        )
    )

    split = half_split(laps)
    if split is not None:
        lines.append("\n### Race execution")
        lines.append(
            f"- First half: {_pace(split.first_pace_s_per_km)}; "
            f"second half: {_pace(split.second_pace_s_per_km)}"
        )
        delta = split.delta_s_per_km
        if delta is not None:
            lines.append(
                "- Split: "
                + ("negative" if delta < 0 else "positive")
                + f" ({'+' if delta >= 0 else '-'}"
                f"{format_pace(abs(delta))}/km)"
            )

    lines.extend(_plan_lines(activity, events))
    lines.extend(_zone_rows(activity, events))

    return "\n".join(lines)
