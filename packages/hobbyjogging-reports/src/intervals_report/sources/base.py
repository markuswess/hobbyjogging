"""The data source interface.

Every adapter (Intervals.icu API today, a local database later) implements
this protocol and returns model objects (see ``intervals_report.model``).
Analysis and chart code should only ever depend on this interface.
"""

from datetime import date
from typing import Protocol

from ..model import Activity, Event, Interval, WellnessDay


class DataSource(Protocol):

    def activities(self, start: date, end: date) -> list[Activity]:
        ...

    def wellness(self, start: date, end: date) -> list[WellnessDay]:
        ...

    def events(self, start: date, end: date) -> list[Event]:
        ...

    def activity_intervals(self, activity_id: str) -> list[Interval]:
        ...
