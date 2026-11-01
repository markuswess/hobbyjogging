"""Read-side access to the canonical database."""

import sqlite3
from collections import defaultdict
from datetime import date

from hobbyjogging_core.model import (
    Activity,
    Equipment,
    Event,
    Interval,
    WellnessDay,
)


class TrainingRepository:
    """Read canonical training data from a migrated SQLite database."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def activities(self, start: date, end: date) -> list[Activity]:
        rows = self.connection.execute(
            """
            SELECT
                id, local_date, sport, name, description,
                duration_s, distance_m, avg_hr, training_load,
                rpe, feel, intensity
            FROM activities
            WHERE local_date BETWEEN ? AND ?
            ORDER BY local_date, COALESCE(started_at_utc, local_date), id
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        if not rows:
            return []

        activity_ids = [row["id"] for row in rows]
        zone_times = self._zone_times(activity_ids)
        equipment = self._equipment_by_activity(activity_ids)

        return [
            Activity(
                id=row["id"],
                date=date.fromisoformat(row["local_date"]),
                type=row["sport"],
                name=row["name"],
                description=row["description"],
                duration_s=row["duration_s"],
                distance_m=row["distance_m"],
                avg_hr=row["avg_hr"],
                training_load=row["training_load"],
                rpe=row["rpe"],
                feel=row["feel"],
                intensity=row["intensity"],
                pace_zone_times=zone_times[row["id"]]["pace"],
                hr_zone_times=zone_times[row["id"]]["hr"],
                equipment=equipment[row["id"]],
            )
            for row in rows
        ]

    def wellness(self, start: date, end: date) -> list[WellnessDay]:
        rows = self.connection.execute(
            """
            SELECT local_date, hrv, resting_hr, sleep_s
            FROM wellness_days
            WHERE local_date BETWEEN ? AND ?
            ORDER BY local_date
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        return [
            WellnessDay(
                date=date.fromisoformat(row["local_date"]),
                hrv=row["hrv"],
                resting_hr=row["resting_hr"],
                sleep_s=row["sleep_s"],
            )
            for row in rows
        ]

    def events(self, start: date, end: date) -> list[Event]:
        rows = self.connection.execute(
            """
            SELECT local_date, name, type, description, duration_s, distance_m
            FROM events
            WHERE local_date BETWEEN ? AND ?
            ORDER BY local_date, name
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        return [
            Event(
                date=date.fromisoformat(row["local_date"]),
                name=row["name"],
                type=row["type"],
                description=row["description"],
                duration_s=row["duration_s"],
                distance_m=row["distance_m"],
            )
            for row in rows
        ]

    def activity_intervals(self, activity_id: str) -> list[Interval]:
        rows = self.connection.execute(
            """
            SELECT group_id, type, start_time, duration_s, distance_m, avg_hr, max_hr
            FROM activity_intervals
            WHERE activity_id = ?
            ORDER BY interval_index
            """,
            (activity_id,),
        ).fetchall()

        return [
            Interval(
                group_id=row["group_id"],
                type=row["type"],
                start_time=row["start_time"],
                duration_s=row["duration_s"],
                distance_m=row["distance_m"],
                avg_hr=row["avg_hr"],
                max_hr=row["max_hr"],
            )
            for row in rows
        ]

    def equipment(self) -> list[Equipment]:
        rows = self.connection.execute(
            """
            SELECT
                id, type, name, brand, model,
                acquired_on, retired_on, target_distance_m, notes
            FROM equipment
            ORDER BY type, name, id
            """
        ).fetchall()

        return [self._equipment_from_row(row) for row in rows]

    def _zone_times(self, activity_ids: list[str]) -> dict[str, dict[str, list[float]]]:
        raw: dict[str, dict[str, dict[int, float]]] = defaultdict(
            lambda: {"pace": {}, "hr": {}}
        )
        placeholders = ", ".join("?" for _ in activity_ids)
        rows = self.connection.execute(
            f"""
            SELECT activity_id, kind, zone_index, seconds
            FROM activity_zone_times
            WHERE activity_id IN ({placeholders})
            ORDER BY activity_id, kind, zone_index
            """,
            activity_ids,
        ).fetchall()

        for row in rows:
            if row["kind"] in ("pace", "hr"):
                raw[row["activity_id"]][row["kind"]][row["zone_index"]] = row["seconds"]

        result: dict[str, dict[str, list[float]]] = {}
        for activity_id in activity_ids:
            result[activity_id] = {}
            for kind in ("pace", "hr"):
                values = raw[activity_id][kind]
                if values:
                    last_zone = max(values)
                    result[activity_id][kind] = [
                        values.get(zone, 0.0) for zone in range(1, last_zone + 1)
                    ]
                else:
                    result[activity_id][kind] = []

        return result

    def _equipment_by_activity(
        self,
        activity_ids: list[str],
    ) -> dict[str, list[Equipment]]:
        placeholders = ", ".join("?" for _ in activity_ids)
        rows = self.connection.execute(
            f"""
            SELECT
                ae.activity_id,
                e.id, e.type, e.name, e.brand, e.model,
                e.acquired_on, e.retired_on, e.target_distance_m, e.notes
            FROM activity_equipment ae
            JOIN equipment e ON e.id = ae.equipment_id
            WHERE ae.activity_id IN ({placeholders})
            ORDER BY
                ae.activity_id,
                CASE ae.role WHEN 'primary' THEN 0 ELSE 1 END,
                e.name
            """,
            activity_ids,
        ).fetchall()

        result: dict[str, list[Equipment]] = defaultdict(list)
        for row in rows:
            result[row["activity_id"]].append(self._equipment_from_row(row))

        return result

    @staticmethod
    def _equipment_from_row(row: sqlite3.Row) -> Equipment:
        return Equipment(
            id=row["id"],
            type=row["type"],
            name=row["name"],
            brand=row["brand"],
            model=row["model"],
            acquired_on=_parse_optional_date(row["acquired_on"]),
            retired_on=_parse_optional_date(row["retired_on"]),
            target_distance_m=row["target_distance_m"],
            notes=row["notes"],
        )


def _parse_optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
