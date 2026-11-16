"""Per-year data coverage for the health view."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hobbyjogging_core.model import Activity


@dataclass(frozen=True)
class YearCoverage:
    """Activities and how many of them carry weather, for one year."""

    year: int
    activities: int
    weather: int

    @property
    def weather_share(self) -> float:
        return self.weather / self.activities if self.activities else 0.0


def yearly_coverage(
    activities: Iterable[Activity],
    weather_ids: set[str],
) -> list[YearCoverage]:
    """Coverage per calendar year, newest first.

    ``weather_ids`` is the set of activities with a stored weather row; the
    caller owns the lookup, because only it knows whether an extra query is
    affordable.
    """
    totals: dict[int, list[int]] = {}

    for activity in activities:
        row = totals.setdefault(activity.date.year, [0, 0])
        row[0] += 1

        if activity.id in weather_ids:
            row[1] += 1

    return [
        YearCoverage(year=year, activities=row[0], weather=row[1])
        for year, row in sorted(totals.items(), reverse=True)
    ]
