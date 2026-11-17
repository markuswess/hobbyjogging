"""Sickness report: illness periods and the training inside them."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import TrainingPeriod

from .format import fmt_time
from .review import exclude_review

DEFAULT_SICKNESS_DAYS = 365


def _clip(
    period: TrainingPeriod,
    start: date,
    end: date,
) -> tuple[date, date]:
    """The part of an illness period inside the report range."""
    return max(period.start_date, start), min(period.end_date or end, end)


def _days(first: date, last: date) -> int:
    return (last - first).days + 1


def _span(first: date, last: date) -> str:
    return f"{first} → {last}" if first != last else str(first)


def _show(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def sickness_report(
    source: DataSource,
    *,
    start: date,
    end: date,
    include_review: bool = False,
) -> str:
    """Render illness episodes in a date range with the training inside them."""
    if start > end:
        raise ValueError("start must not be after end")

    periods = [
        period
        for period in source.training_periods()
        if period.kind == "illness" and period.start_date is not None
    ]
    episodes = []

    for period in periods:
        first, last = _clip(period, start, end)

        if last < first:
            continue

        episodes.append((period, first, last))

    episodes.sort(key=lambda item: (item[1], item[0].id), reverse=True)

    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )
    lines = ["# Sickness report", f"{start} → {end}"]

    if excluded:
        lines.append(f"\n> {excluded} activities excluded (import review)")

    if not episodes:
        lines.append("\n- No illness periods in this range")
        return "\n".join(lines)

    illness_days = set()

    for _period, first, last in episodes:
        for offset in range(_days(first, last)):
            illness_days.add(first + timedelta(days=offset))

    longest = max(episodes, key=lambda item: _days(item[1], item[2]))
    total_days = _days(start, end)
    share = len(illness_days) / total_days * 100
    current = next(
        (
            (period, first, last)
            for period, first, last in episodes
            if first <= end <= last
            and (period.end_date is None or period.end_date >= end)
        ),
        None,
    )

    lines.extend([
        "",
        f"- Episodes: {len(episodes)}",
        f"- Illness days: {len(illness_days)} of {total_days} "
        f"({share:.1f}%)",
        f"- Longest: {_days(longest[1], longest[2])} days "
        f"({_span(longest[1], longest[2])}"
        + (f", {longest[0].label}" if longest[0].label else "")
        + ")",
    ])

    if current is not None:
        period, first, last = current
        lines.append(
            f"- Current: day {_days(first, last)} of "
            f"{period.label or 'illness'} (from {period.start_date})"
        )
    else:
        _period, first, last = episodes[0]
        lines.append(
            f"- Last: {_days(first, last)} days ending {last}"
        )

    lines.extend([
        "",
        "## Episodes",
        "",
        "| From | To | Days | Episode | Sessions | Time | Load |",
        "|---|---|---:|---|---:|---:|---:|",
    ])

    for period, first, last in episodes:
        inside = [
            activity
            for activity in activities
            if first <= activity.date <= last
        ]
        seconds = sum(activity.duration_s or 0 for activity in inside)
        load = sum(activity.training_load or 0 for activity in inside)
        label = (period.label or "Illness").replace("|", "\\|")
        lines.append(
            f"| {first} | {last} | {_days(first, last)} | "
            f"{label} | {len(inside)} | "
            f"{fmt_time(seconds)} | {_show(load)} |"
        )

    lines.extend([
        "",
        "Illness days are shaded, never excluded from training aggregates.",
    ])

    return "\n".join(lines)
