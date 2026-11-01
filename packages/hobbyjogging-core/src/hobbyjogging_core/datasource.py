"""The data source interface.

Every adapter (Intervals.icu API, local database, file export, ...) implements
this protocol and returns canonical model objects. Analysis, charts, and
reports should depend only on this interface.
"""

from datetime import date
from typing import Protocol

from .model import Activity, Equipment, Event, Interval, WellnessDay


class DataSource(Protocol):

    def activities(self, start: date, end: date) -> list[Activity]:
        ...

    def wellness(self, start: date, end: date) -> list[WellnessDay]:
        ...

    def events(self, start: date, end: date) -> list[Event]:
        ...

    def activity_intervals(self, activity_id: str) -> list[Interval]:
        ...

    def equipment(self) -> list[Equipment]:
        ...
