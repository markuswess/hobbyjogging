"""Detect activities that are the same session recorded twice.

The pairwise rule is dataset-wide and source-independent: the same sport on
the same local day, distance within 2 %, duration within 5 % and average HR
within 5 bpm when both carry it. The start time is recorded but is not a gate:
the historical sheet's minute-precision start is often approximate and can
differ by hours even when the distance and duration match exactly.

A pair is a review candidate, never a merge. The sheet-specific cleanup task
uses the same rule to remove a sheet-only row after keeping its text on the
device row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from hobbyjogging_core.model import Activity

DISTANCE_TOLERANCE = 0.02
DURATION_TOLERANCE = 0.05
HR_TOLERANCE = 5.0


@dataclass(frozen=True)
class DuplicatePair:
    first: Activity
    second: Activity
    start_delta_s: float | None = None
    distance_delta_m: float = 0.0
    duration_delta_s: float = 0.0
    hr_delta: float | None = None

    @property
    def ids(self) -> tuple[str, str]:
        one, two = sorted((self.first.id, self.second.id))
        return one, two

    def detail(self) -> str:
        first, second = self.first, self.second
        return (
            f"same session: {first.id} ({first.date}, {first.type}, "
            f"{first.distance_m / 1000:.2f} km) and {second.id} "
            f"({second.date}, {second.type}, {second.distance_m / 1000:.2f} km)"
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "rule": "duplicate_candidate",
            "activities": list(self.ids),
            "start_delta_s": (
                None
                if self.start_delta_s is None
                else round(self.start_delta_s, 1)
            ),
            "distance_delta_m": round(self.distance_delta_m, 1),
            "duration_delta_s": round(self.duration_delta_s, 1),
            "hr_delta": (
                None if self.hr_delta is None else round(self.hr_delta, 1)
            ),
        }


def find_duplicates(activities: list[Activity]) -> list[DuplicatePair]:
    """Return every same-session pair, deterministically ordered."""
    by_day: dict[tuple[object, str], list[Activity]] = {}
    for activity in activities:
        by_day.setdefault((activity.date, activity.type), []).append(activity)

    pairs = []
    for group in by_day.values():
        ordered = sorted(group, key=lambda item: (item.id))
        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                pair = same_session(first, second)
                if pair is not None:
                    pairs.append(pair)
    return sorted(pairs, key=lambda pair: (pair.ids, pair.first.date))


def same_session(first: Activity, second: Activity) -> DuplicatePair | None:
    """Return the pair when two activities look like the same session."""
    if first.id == second.id:
        return None
    if first.type != second.type or first.date != second.date:
        return None

    if not first.distance_m or not second.distance_m:
        return None
    distance_delta = abs(first.distance_m - second.distance_m)
    if distance_delta > DISTANCE_TOLERANCE * max(
        first.distance_m, second.distance_m
    ):
        return None

    if not first.duration_s or not second.duration_s:
        return None
    duration_delta = abs(first.duration_s - second.duration_s)
    if duration_delta > DURATION_TOLERANCE * max(
        first.duration_s, second.duration_s
    ):
        return None

    hr_delta = None
    if first.avg_hr is not None and second.avg_hr is not None:
        hr_delta = abs(first.avg_hr - second.avg_hr)
        if hr_delta > HR_TOLERANCE:
            return None

    return DuplicatePair(
        first=first,
        second=second,
        start_delta_s=_start_delta(first, second),
        distance_delta_m=distance_delta,
        duration_delta_s=duration_delta,
        hr_delta=hr_delta,
    )


def preferred_activity(
    pair: DuplicatePair,
    sources: dict[str, set[str]],
) -> Activity:
    """Pick the activity to link the review item to (the one to remove).

    A sheet-only row is the weaker copy and is linked first; otherwise the
    activity with fewer sources is the likely duplicate. Ties fall back to the
    lexicographically larger id so repeated scans are stable.
    """
    first, second = pair.first, pair.second
    first_sources = sources.get(first.id, set())
    second_sources = sources.get(second.id, set())

    if first_sources == {"sheet"} and second_sources != {"sheet"}:
        return first
    if second_sources == {"sheet"} and first_sources != {"sheet"}:
        return second
    if len(first_sources) != len(second_sources):
        return first if len(first_sources) < len(second_sources) else second
    return max(first, second, key=lambda item: item.id)


def _start_delta(first: Activity, second: Activity) -> float | None:
    one = _parse(first.started_at_utc)
    two = _parse(second.started_at_utc)
    if one is None or two is None:
        return None
    return abs((one - two).total_seconds())


def _parse(value: str) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
