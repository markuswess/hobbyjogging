"""The data source interface.

Every adapter (Intervals.icu API, local database, file export, ...) implements
this protocol and returns canonical model objects. Analysis, charts, and
reports should depend only on this interface.
"""

from datetime import date
from typing import Protocol

from .model import (
    Activity,
    Equipment,
    Event,
    Interval,
    Lap,
    ReviewItem,
    WellnessDay,
)


class DataSource(Protocol):

    def activities(self, start: date, end: date) -> list[Activity]:
        ...

    def wellness(self, start: date, end: date) -> list[WellnessDay]:
        ...

    def events(self, start: date, end: date) -> list[Event]:
        ...

    def activity_intervals(self, activity_id: str) -> list[Interval]:
        ...

    def activity_laps(self, activity_id: str) -> list[Lap]:
        ...

    def equipment(self) -> list[Equipment]:
        ...

    def review_items(
        self,
        *,
        status: str = "open",
        category: str | None = None,
    ) -> list[ReviewItem]:
        """Return review-queue entries, newest and most severe first."""
        ...
