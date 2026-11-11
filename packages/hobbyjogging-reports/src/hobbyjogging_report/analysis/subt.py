"""subT/LT1 work-rep detection and report blocks."""

from __future__ import annotations

from hobbyjogging_core.model import Activity, Interval

from .common import (
    SUBT_CATEGORY_ORDER,
    classify_interval,
    is_lt1_activity,
    is_subt_activity,
    pace_s_per_km,
    work_intervals,
)
from ..model import SubtBlock, SubtPoint, SubtSummary


def _subt_point(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
) -> SubtPoint | None:
    """Aggregate a list of work reps into one pace point."""
    total_time = sum(i.duration_s for i in intervals)
    total_distance = sum(i.distance_m for i in intervals)

    pace = pace_s_per_km(total_time, total_distance)
    if pace is None:
        return None

    # Time-weighted average heart rate.
    hr_pairs = [
        (i.avg_hr, i.duration_s)
        for i in intervals
        if i.avg_hr is not None
    ]

    avg_hr = None
    if hr_pairs:
        avg_hr = (
            sum(hr * t for hr, t in hr_pairs)
            / sum(t for _, t in hr_pairs)
        )

    max_hr = max(
        (i.max_hr for i in intervals if i.max_hr is not None),
        default=None,
    )

    # Efficiency only counts reps with both a heart rate and a distance.
    efficiency_distance = sum(
        i.distance_m for i in intervals if i.avg_hr is not None
    )
    efficiency_beats = sum(
        i.avg_hr * i.duration_s / 60
        for i in intervals
        if i.avg_hr is not None
    )
    efficiency = (
        efficiency_distance / efficiency_beats
        if efficiency_beats > 0
        else None
    )

    rep_paces = []
    for interval in intervals:
        rep_pace = pace_s_per_km(interval.duration_s, interval.distance_m)
        if rep_pace is not None:
            rep_paces.append(rep_pace)

    return SubtPoint(
        date=activity.date,
        category=category or classify_interval(total_time / len(intervals)),
        pace_s_per_km=pace,
        count=len(intervals),
        avg_hr=avg_hr,
        max_hr=max_hr,
        avg_rep_s=total_time / len(intervals),
        fastest_pace_s_per_km=min(rep_paces) if rep_paces else None,
        slowest_pace_s_per_km=max(rep_paces) if rep_paces else None,
        distance_m=efficiency_distance,
        beats=efficiency_beats,
        efficiency=efficiency,
    )


def _paced_work(intervals: list[Interval]) -> list[Interval]:
    return [
        i for i in work_intervals(intervals)
        if i.duration_s and i.distance_m
    ]


def subt_work_points(
    activity: Activity,
    intervals: list[Interval],
) -> list[SubtPoint]:
    """One point per WORK interval group (set of reps) in an activity."""
    work = _paced_work(intervals)

    groups: dict[str, list[Interval]] = {}

    for index, interval in enumerate(work):
        key = interval.group_id or f"interval-{index}"
        groups.setdefault(key, []).append(interval)

    points = []

    for group in groups.values():
        point = _subt_point(activity, group)
        if point is not None:
            points.append(point)

    return points


def subt_session_point(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
) -> SubtPoint | None:
    """One point per activity, aggregating all of its work reps.

    ``category`` can override the rep-length category, e.g. for LT1.
    """
    work = _paced_work(intervals)

    if not work:
        return None

    return _subt_point(activity, work, category=category)


def _combine_points(
    activity: Activity,
    category: str,
    points: list[SubtPoint],
) -> SubtBlock | None:
    """Merge same-category points from one session into one report block."""
    count = sum(point.count for point in points)

    if count <= 0:
        return None

    total_time = sum(
        point.count * point.avg_rep_s
        for point in points
    )
    total_distance = sum(
        (point.count * point.avg_rep_s) / point.pace_s_per_km * 1000
        for point in points
    )
    block_pace = pace_s_per_km(total_time, total_distance)

    if block_pace is None:
        return None

    hr_pairs = [
        (point.avg_hr, point.count * point.avg_rep_s)
        for point in points
        if point.avg_hr is not None
    ]
    hr_time = sum(time for _, time in hr_pairs)

    avg_hr = (
        sum(hr * time for hr, time in hr_pairs) / hr_time
        if hr_time
        else None
    )

    max_hrs = [
        point.max_hr
        for point in points
        if point.max_hr is not None
    ]
    fastest = [
        point.fastest_pace_s_per_km
        for point in points
        if point.fastest_pace_s_per_km is not None
    ]
    slowest = [
        point.slowest_pace_s_per_km
        for point in points
        if point.slowest_pace_s_per_km is not None
    ]

    return SubtBlock(
        date=activity.date,
        activity_id=activity.id,
        activity_name=activity.name,
        category=category,
        count=count,
        avg_rep_s=total_time / count,
        total_time_s=total_time,
        total_distance_m=total_distance,
        pace_s_per_km=block_pace,
        fastest_pace_s_per_km=min(fastest) if fastest else None,
        slowest_pace_s_per_km=max(slowest) if slowest else None,
        avg_hr=avg_hr,
        max_hr=max(max_hrs) if max_hrs else None,
        efficiency=(
            sum(point.distance_m for point in points)
            / sum(point.beats for point in points)
            if sum(point.beats for point in points) > 0
            else None
        ),
    )


def subt_blocks(
    activity: Activity,
    intervals: list[Interval],
) -> list[SubtBlock]:
    """Return one block per work category within a subT or LT1 session."""
    if not (is_subt_activity(activity) or is_lt1_activity(activity)):
        return []

    points = subt_work_points(activity, intervals)

    if not points:
        return []

    grouped: dict[str, list[SubtPoint]] = {}

    for point in points:
        category = "lt1" if is_lt1_activity(activity) else point.category
        grouped.setdefault(category, []).append(point)

    blocks = []

    for category, category_points in grouped.items():
        block = _combine_points(activity, category, category_points)
        if block is not None:
            blocks.append(block)

    return blocks


def subt_report_blocks(
    activities: list[Activity],
    intervals_by_id: dict[str, list[Interval]],
) -> list[SubtBlock]:
    """Collect report blocks for subT/LT1 sessions, grouped and sorted."""
    blocks = []

    for activity in activities:
        blocks.extend(
            subt_blocks(
                activity,
                intervals_by_id.get(activity.id, []),
            )
        )

    order = {
        category: index
        for index, category in enumerate(SUBT_CATEGORY_ORDER)
    }

    return sorted(
        blocks,
        key=lambda block: (
            order.get(block.category, len(order)),
            block.date,
            block.activity_name,
            block.activity_id,
        ),
    )


def _summary_from_blocks(
    category: str,
    blocks: list[SubtBlock],
) -> SubtSummary:
    total_time = sum(block.total_time_s for block in blocks)
    total_distance = sum(block.total_distance_m for block in blocks)

    hr_pairs = [
        (block.avg_hr, block.total_time_s)
        for block in blocks
        if block.avg_hr is not None
    ]
    hr_time = sum(time for _, time in hr_pairs)

    max_hrs = [
        block.max_hr
        for block in blocks
        if block.max_hr is not None
    ]
    avg_hr = (
        sum(hr * time for hr, time in hr_pairs) / hr_time
        if hr_time
        else None
    )

    return SubtSummary(
        category=category,
        sessions=len({block.activity_id for block in blocks}),
        reps=sum(block.count for block in blocks),
        total_time_s=total_time,
        total_distance_m=total_distance,
        pace_s_per_km=pace_s_per_km(total_time, total_distance),
        avg_hr=avg_hr,
        max_hr=max(max_hrs) if max_hrs else None,
        efficiency=(
            total_distance / (avg_hr * total_time / 60)
            if avg_hr is not None and total_time > 0
            else None
        ),
    )


def subt_report_summary(
    blocks: list[SubtBlock],
) -> tuple[list[SubtSummary], SubtSummary]:
    """Return per-category summaries (including empty ones) and a total."""
    by_category: dict[str, list[SubtBlock]] = {
        category: []
        for category in SUBT_CATEGORY_ORDER
    }

    for block in blocks:
        by_category.setdefault(block.category, []).append(block)

    summaries = [
        _summary_from_blocks(category, by_category.get(category, []))
        for category in SUBT_CATEGORY_ORDER
    ]

    return summaries, _summary_from_blocks("total", blocks)
