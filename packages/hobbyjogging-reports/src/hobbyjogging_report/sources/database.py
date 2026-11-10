"""Database-backed DataSource adapter."""

import json
import sqlite3
from datetime import date, datetime, timezone
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

from ..links import (
    GARMIN_MATCH_TOLERANCE_S,
    GARMIN_URL,
    INTERVALS_URL,
    ActivityLinks,
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

    def activity_links(self, activity_id: str) -> ActivityLinks:
        """Return the Intervals and Garmin Connect pages for an activity."""
        intervals_id = self._intervals_activity_id(activity_id)
        garmin_id = self._garmin_activity_id(activity_id)

        return ActivityLinks(
            intervals=(
                INTERVALS_URL.format(intervals_id)
                if intervals_id
                else None
            ),
            garmin=GARMIN_URL.format(garmin_id) if garmin_id else None,
        )

    def _intervals_activity_id(self, activity_id: str) -> str | None:
        row = self.connection.execute(
            """
            SELECT sr.external_id
            FROM activity_sources als
            JOIN source_records sr ON sr.id = als.source_record_id
            WHERE als.activity_id = ? AND sr.source = 'intervals'
            ORDER BY als.is_primary DESC, sr.id
            LIMIT 1
            """,
            (activity_id,),
        ).fetchone()

        return str(row["external_id"]) if row is not None else None

    def _garmin_activity_id(self, activity_id: str) -> str | None:
        """Resolve a canonical activity to a Garmin Connect activity id.

        The fetch manifest stores the Garmin id next to the downloaded FIT.
        A path join is exact when the linked FIT source record is the fetched
        file. When the archive copy was imported instead, fall back to the
        manifest's ``beginTimestamp`` and the canonical start time.
        """
        row = self.connection.execute(
            """
            SELECT g.external_id
            FROM activity_sources als
            JOIN source_records f ON f.id = als.source_record_id
            JOIN source_records g ON g.raw_path = f.raw_path
            WHERE als.activity_id = ?
              AND g.source = 'garmin'
              AND g.record_type = 'activity-file'
            ORDER BY als.is_primary DESC, g.id
            LIMIT 1
            """,
            (activity_id,),
        ).fetchone()

        if row is not None:
            return str(row["external_id"])

        started = self.connection.execute(
            "SELECT started_at_utc FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if started is None or not started["started_at_utc"]:
            return None

        try:
            target = _utc(started["started_at_utc"])
        except ValueError:
            return None

        best: tuple[float, str] | None = None

        for moment, external_id in self._garmin_manifest_index():
            difference = abs((moment - target).total_seconds())

            if (
                difference <= GARMIN_MATCH_TOLERANCE_S
                and (best is None or difference < best[0])
            ):
                best = (difference, external_id)

        return best[1] if best else None

    def _garmin_manifest_index(self) -> list[tuple[datetime, str]]:
        """Return ``(start, garmin_activity_id)`` for every fetch manifest."""
        cached = getattr(self, "_garmin_index", None)

        if cached is not None:
            return cached

        index: list[tuple[datetime, str]] = []
        rows = self.connection.execute(
            """
            SELECT external_id, payload_json
            FROM source_records
            WHERE source = 'garmin' AND record_type = 'activity-file'
            ORDER BY id
            """
        )

        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except ValueError:
                continue

            timestamp = payload.get("beginTimestamp")

            if timestamp is None:
                continue

            try:
                moment = datetime.fromtimestamp(
                    float(timestamp) / 1000,
                    tz=timezone.utc,
                )
            except (TypeError, ValueError, OSError):
                continue

            index.append((moment, str(row["external_id"])))

        self._garmin_index = index
        return index


def _utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc)
