"""Database-backed DataSource adapter."""

import sqlite3
from datetime import date
from pathlib import Path

from hobbyjogging_core.db import open_database
from hobbyjogging_core.db.repository import TrainingRepository
from hobbyjogging_core.model import (
    Activity,
    Equipment,
    Event,
    Interval,
    ReviewItem,
    WellnessDay,
)


class DatabaseSource:
    """Read canonical training data from the hobbyjogging database."""

    def __init__(
        self,
        path: str | Path | None = None,
        connection: sqlite3.Connection | None = None,
    ):
        if connection is not None:
            self.connection = connection
            self._owns_connection = False
        else:
            self.connection = open_database(path)
            self._owns_connection = True

        self.repository = TrainingRepository(self.connection)

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def activities(self, start: date, end: date) -> list[Activity]:
        return self.repository.activities(start, end)

    def wellness(self, start: date, end: date) -> list[WellnessDay]:
        return self.repository.wellness(start, end)

    def events(self, start: date, end: date) -> list[Event]:
        return self.repository.events(start, end)

    def review_items(
        self,
        *,
        status: str = "open",
        category: str | None = None,
    ) -> list[ReviewItem]:
        return self.repository.review_items(
            status=status,
            category=category,
        )

    def earliest_activity_date(self) -> date | None:
        """Return the first non-excluded activity date, if any."""
        row = self.connection.execute(
            """
            SELECT MIN(local_date)
            FROM activities
            WHERE excluded_at IS NULL
            """
        ).fetchone()

        if row is None or row[0] is None:
            return None

        return date.fromisoformat(row[0])

    def activity_intervals(self, activity_id: str) -> list[Interval]:
        return self.repository.activity_intervals(activity_id)

    def equipment(self) -> list[Equipment]:
        return self.repository.equipment()
