"""The data source interface.

Every adapter (Intervals.icu API, local database, file export, ...) implements
this protocol and returns canonical model objects. Analysis, charts, and
reports should depend only on this interface.
"""

from datetime import date
from typing import Protocol

from .model import (
    Activity,
    ActivityWeather,
    AthleteThreshold,
    Device,
    RaceResult,
    TrainingPeriod,
    Equipment,
    Event,
    Interval,
    Lap,
    ReviewItem,
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

    def activity_weather(self, activity_id: str) -> ActivityWeather | None:
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

    def review_items(
        self,
        *,
        status: str = "open",
        category: str | None = None,
    ) -> list[ReviewItem]:
        """Return review-queue entries, newest and most severe first."""
        ...
