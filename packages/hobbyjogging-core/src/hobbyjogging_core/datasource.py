"""The data source interface.

Every adapter (Intervals.icu API, local database, file export, ...) implements
this protocol and returns canonical model objects. Analysis, charts, and
reports should depend only on this interface.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .model import (
    Activity,
    ActivitySocial,
    ActivityWeather,
    ActivityMetrics,
    AthleteThreshold,
    Device,
    FieldProvenance,
    RaceResult,
    TrainingPeriod,
    Equipment,
    Event,
    EventActivityLink,
    Interval,
    Lap,
    ReviewItem,
    Route,
    WellnessDay,
    ZoneConfig,
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

    def activity_test_splits(self, activity_id: str) -> list[Lap]:
        ...

    def activity_weather(self, activity_id: str) -> ActivityWeather | None:
        ...

    def activity_metrics(self, activity_id: str) -> ActivityMetrics | None:
        """Return the session-average metrics for one activity."""
        ...

    def activity_social(self, activity_id: str) -> list[ActivitySocial]:
        """Return social text rows for one activity, manual first."""
        ...

    def activity_field_sources(
        self,
        activity_id: str,
    ) -> list[FieldProvenance]:
        """Return the recorded owner of each canonical field, by field."""
        ...

    def athlete_thresholds(self) -> list[AthleteThreshold]:
        ...

    def race_results(self) -> list[RaceResult]:
        ...

    def devices(self) -> list[Device]:
        ...

    def training_periods(self) -> list[TrainingPeriod]:
        ...

    def zone_config(self, zone_config_id: str) -> ZoneConfig | None:
        ...

    def equipment(self) -> list[Equipment]:
        ...

    def routes(self) -> list[Route]:
        ...

    def event_activity_links(self) -> list[EventActivityLink]:
        ...

    def review_items(
        self,
        *,
        status: str = "open",
        category: str | None = None,
    ) -> list[ReviewItem]:
        """Return review-queue entries, newest and most severe first."""
        ...
