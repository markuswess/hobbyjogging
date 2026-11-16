"""Read-side access to the canonical database."""

import json
import sqlite3
from collections import defaultdict
from datetime import date

from hobbyjogging_core.model import (
    Activity,
    ActivityWeather,
    AthleteThreshold,
    Device,
    RaceResult,
    Equipment,
    Event,
    EventZoneTime,
    Interval,
    Lap,
    ReviewItem,
    WellnessDay,
    ZoneConfig,
)

# Review categories that do not make an activity's data untrusted. They stay
# in the queue but never hide the activity from reports.
NON_HIDING_REVIEW_CATEGORIES = ("workout_classification",)


class TrainingRepository:
    """Read canonical training data from a migrated SQLite database."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def activities(self, start: date, end: date) -> list[Activity]:
        rows = self.connection.execute(
            """
            SELECT
                id, local_date, started_at_utc, sport, name, description,
                duration_s, elapsed_s, distance_m, avg_hr, training_load,
                rpe, feel, intensity, vo2max_garmin, vo2max_runalyze,
                moving_s, device_id
            FROM activities
            WHERE local_date BETWEEN ? AND ?
              AND excluded_at IS NULL
            ORDER BY local_date, COALESCE(started_at_utc, local_date), id
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        if not rows:
            return []

        activity_ids = [row["id"] for row in rows]
        zone_times = self._zone_times(activity_ids)
        equipment = self._equipment_by_activity(activity_ids)
        tags = self._tags_by_activity(activity_ids)
        methods, targets = self._activity_workout_sets(activity_ids)
        flagged = self._open_review_activity_ids(activity_ids)

        return [
            Activity(
                id=row["id"],
                date=date.fromisoformat(row["local_date"]),
                started_at_utc=row["started_at_utc"] or "",
                type=row["sport"],
                name=row["name"],
                description=row["description"],
                duration_s=row["duration_s"],
                elapsed_s=row["elapsed_s"],
                moving_s=row["moving_s"],
                distance_m=row["distance_m"],
                avg_hr=row["avg_hr"],
                training_load=row["training_load"],
                rpe=row["rpe"],
                feel=row["feel"],
                intensity=row["intensity"],
                vo2max_garmin=row["vo2max_garmin"],
                vo2max_runalyze=row["vo2max_runalyze"],
                workout_methods=methods[row["id"]],
                workout_targets=targets[row["id"]],
                tags=tags[row["id"]],
                pace_zone_times=zone_times[row["id"]]["pace"],
                hr_zone_times=zone_times[row["id"]]["hr"],
                equipment=equipment[row["id"]],
                device_id=row["device_id"] or "",
                needs_review=row["id"] in flagged,
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
            SELECT id, local_date, name, type, description, duration_s,
                   distance_m, training_load, zone_kind
            FROM events
            WHERE local_date BETWEEN ? AND ?
              AND excluded_at IS NULL
            ORDER BY local_date, name
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        if not rows:
            return []

        event_ids = [row["id"] for row in rows]
        zone_times = self._event_zone_times(event_ids)
        methods, targets = self._event_workout_sets(event_ids)

        return [
            Event(
                date=date.fromisoformat(row["local_date"]),
                id=row["id"],
                name=row["name"],
                type=row["type"],
                description=row["description"],
                duration_s=row["duration_s"],
                distance_m=row["distance_m"],
                training_load=row["training_load"],
                zone_kind=row["zone_kind"],
                zone_times=zone_times[row["id"]],
                workout_methods=methods[row["id"]],
                workout_targets=targets[row["id"]],
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

    def devices(self) -> list[Device]:
        rows = self.connection.execute(
            """
            SELECT id, manufacturer, product, serial_number, name,
                   acquired_on, retired_on, notes
            FROM devices
            ORDER BY acquired_on, product, id
            """
        ).fetchall()

        return [
            Device(
                id=row["id"],
                manufacturer=row["manufacturer"] or "",
                product=row["product"] or "",
                serial_number=row["serial_number"] or "",
                name=row["name"] or "",
                acquired_on=(
                    date.fromisoformat(row["acquired_on"])
                    if row["acquired_on"]
                    else None
                ),
                retired_on=(
                    date.fromisoformat(row["retired_on"])
                    if row["retired_on"]
                    else None
                ),
                notes=row["notes"] or "",
            )
            for row in rows
        ]

    def race_results(self) -> list[RaceResult]:
        """Official race results, newest first, with the activity's date."""
        rows = self.connection.execute(
            """
            SELECT r.activity_id, a.local_date, r.name, r.official_distance_m,
                   r.official_time_s, r.officially_measured, r.place_total,
                   r.place_gender, r.place_ageclass, r.participants_total,
                   r.participants_gender, r.participants_ageclass,
                   r.priority_level, r.status, r.notes, r.event_id, r.source
            FROM race_results r
            JOIN activities a ON a.id = r.activity_id
            WHERE r.excluded_at IS NULL
            ORDER BY a.local_date DESC, r.activity_id
            """
        ).fetchall()

        return [
            RaceResult(
                activity_id=row["activity_id"],
                date=date.fromisoformat(row["local_date"]),
                name=row["name"] or "",
                official_distance_m=row["official_distance_m"],
                official_time_s=row["official_time_s"],
                officially_measured=(
                    None
                    if row["officially_measured"] is None
                    else bool(row["officially_measured"])
                ),
                place_total=row["place_total"],
                place_gender=row["place_gender"],
                place_ageclass=row["place_ageclass"],
                participants_total=row["participants_total"],
                participants_gender=row["participants_gender"],
                participants_ageclass=row["participants_ageclass"],
                priority_level=row["priority_level"] or "",
                status=row["status"] or "completed",
                notes=row["notes"] or "",
                event_id=row["event_id"],
                source=row["source"] or "",
            )
            for row in rows
        ]

    def athlete_thresholds(self) -> list[AthleteThreshold]:
        rows = self.connection.execute(
            """
            SELECT effective_from, sport, max_hr, lthr, threshold_pace_mps,
                   source
            FROM athlete_thresholds
            ORDER BY sport, effective_from, id
            """
        ).fetchall()

        return [
            AthleteThreshold(
                effective_from=date.fromisoformat(row["effective_from"]),
                sport=row["sport"] or "",
                max_hr=row["max_hr"],
                lthr=row["lthr"],
                threshold_pace_mps=row["threshold_pace_mps"],
                source=row["source"],
            )
            for row in rows
        ]

    def zone_config(self, zone_config_id: str) -> ZoneConfig | None:
        row = self.connection.execute(
            """
            SELECT id, kind, source, boundaries_json
            FROM zone_configs WHERE id = ?
            """,
            (zone_config_id,),
        ).fetchone()

        if row is None:
            return None

        return ZoneConfig(
            id=row["id"],
            kind=row["kind"],
            boundaries=json.loads(row["boundaries_json"]),
            source=row["source"],
        )

    def activity_weather(self, activity_id: str) -> ActivityWeather | None:
        row = self.connection.execute(
            """
            SELECT temp_c, feels_like_c, humidity_pct, wind_speed_ms,
                   wind_degree, wind_gust_ms, wind_chill_c, heat_index_c,
                   pressure_hpa, uv_index, clouds_pct, condition, is_night,
                   source
            FROM activity_weather
            WHERE activity_id = ?
            """,
            (activity_id,),
        ).fetchone()

        if row is None:
            return None

        return ActivityWeather(
            temp_c=row["temp_c"],
            feels_like_c=row["feels_like_c"],
            humidity_pct=row["humidity_pct"],
            wind_speed_ms=row["wind_speed_ms"],
            wind_degree=row["wind_degree"],
            wind_gust_ms=row["wind_gust_ms"],
            wind_chill_c=row["wind_chill_c"],
            heat_index_c=row["heat_index_c"],
            pressure_hpa=row["pressure_hpa"],
            uv_index=row["uv_index"],
            clouds_pct=row["clouds_pct"],
            condition=row["condition"] or "",
            is_night=(
                None if row["is_night"] is None else bool(row["is_night"])
            ),
            source=row["source"] or "",
        )

    def activity_laps(self, activity_id: str) -> list[Lap]:
        rows = self.connection.execute(
            """
            SELECT
                lap_index, start_time_utc, duration_s, distance_m,
                avg_hr, max_hr, elevation_gain_m
            FROM activity_laps
            WHERE activity_id = ?
            ORDER BY lap_index
            """,
            (activity_id,),
        ).fetchall()

        return [
            Lap(
                index=row["lap_index"],
                start_time_utc=row["start_time_utc"] or "",
                duration_s=row["duration_s"],
                distance_m=row["distance_m"],
                avg_hr=row["avg_hr"],
                max_hr=row["max_hr"],
                elevation_gain_m=row["elevation_gain_m"],
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

    def review_items(
        self,
        *,
        status: str = "open",
        category: str | None = None,
    ) -> list[ReviewItem]:
        """Return review-queue entries, most severe and newest first.

        Reports read the queue through this method; writing stays with the
        importers, triage, and the maintenance tasks.
        """
        clauses = []
        params: list[object] = []

        if status and status != "all":
            clauses.append("r.status = ?")
            params.append(status)
        if category is not None:
            clauses.append("r.category = ?")
            params.append(category)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            f"""
            SELECT
                r.id, r.category, r.severity, r.status, r.detail,
                r.reported_at, r.context_json, r.activity_id,
                a.local_date, a.name AS activity_name, a.sport,
                sr.source AS record_source, sr.external_id
            FROM review_items r
            LEFT JOIN activities a ON a.id = r.activity_id
            LEFT JOIN source_records sr ON sr.id = r.source_record_id
            {where}
            ORDER BY
                CASE r.severity
                    WHEN 'error' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END,
                r.reported_at DESC, r.id DESC
            """,
            params,
        ).fetchall()

        return [
            ReviewItem(
                id=row["id"],
                category=row["category"],
                severity=row["severity"],
                status=row["status"],
                detail=row["detail"],
                reported_at=row["reported_at"] or "",
                activity_id=row["activity_id"],
                activity_date=(
                    date.fromisoformat(row["local_date"])
                    if row["local_date"]
                    else None
                ),
                activity_name=row["activity_name"] or "",
                sport=row["sport"] or "",
                source=row["record_source"] or "",
                external_id=row["external_id"] or "",
                context=_context(row["context_json"]),
            )
            for row in rows
        ]

    def _open_review_activity_ids(
        self,
        activity_ids: list[str],
    ) -> set[str]:
        placeholders = ", ".join("?" for _ in activity_ids)
        # A workout-classification item means "not labelled yet", not
        # "untrusted data", so it must not hide the activity from reports.
        hidden = ", ".join("?" for _ in NON_HIDING_REVIEW_CATEGORIES)
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT activity_id
            FROM review_items
            WHERE status = 'open'
              AND category NOT IN ({hidden})
              AND activity_id IN ({placeholders})
            """,
            [*NON_HIDING_REVIEW_CATEGORIES, *activity_ids],
        ).fetchall()
        return {row["activity_id"] for row in rows}

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

    def _tags_by_activity(
        self,
        activity_ids: list[str],
    ) -> dict[str, list[str]]:
        placeholders = ", ".join("?" for _ in activity_ids)
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT activity_id, tag
            FROM activity_tags
            WHERE activity_id IN ({placeholders})
            ORDER BY activity_id, tag
            """,
            activity_ids,
        ).fetchall()

        result: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            result[row["activity_id"]].append(row["tag"])

        return result

    def _event_zone_times(
        self,
        event_ids: list[str],
    ) -> dict[str, list[EventZoneTime]]:
        placeholders = ", ".join("?" for _ in event_ids)
        rows = self.connection.execute(
            f"""
            SELECT event_id, zone_index, zone_label, seconds
            FROM event_zone_times
            WHERE event_id IN ({placeholders})
            ORDER BY event_id, COALESCE(zone_index, 99), zone_label
            """,
            event_ids,
        ).fetchall()

        result: dict[str, list[EventZoneTime]] = defaultdict(list)
        for row in rows:
            result[row["event_id"]].append(
                EventZoneTime(
                    zone_label=row["zone_label"],
                    seconds=row["seconds"],
                    zone_index=row["zone_index"],
                )
            )

        return result

    def _activity_workout_sets(
        self,
        activity_ids: list[str],
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        return self._workout_sets(
            "activity_workout_methods",
            "activity_workout_targets",
            "activity_id",
            "method",
            "target",
            activity_ids,
        )

    def _event_workout_sets(
        self,
        event_ids: list[str],
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        return self._workout_sets(
            "event_workout_methods",
            "event_workout_targets",
            "event_id",
            "method",
            "target",
            event_ids,
        )

    def _workout_sets(
        self,
        methods_table: str,
        targets_table: str,
        id_column: str,
        method_column: str,
        target_column: str,
        entity_ids: list[str],
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        placeholders = ", ".join("?" for _ in entity_ids)
        methods: dict[str, list[str]] = defaultdict(list)
        targets: dict[str, list[str]] = defaultdict(list)

        for row in self.connection.execute(
            f"""
            SELECT {id_column}, {method_column} AS value
            FROM {methods_table}
            WHERE {id_column} IN ({placeholders})
            ORDER BY {id_column}, value
            """,
            entity_ids,
        ):
            methods[row[id_column]].append(row["value"])

        for row in self.connection.execute(
            f"""
            SELECT {id_column}, {target_column} AS value
            FROM {targets_table}
            WHERE {id_column} IN ({placeholders})
            ORDER BY {id_column}, value
            """,
            entity_ids,
        ):
            targets[row[id_column]].append(row["value"])

        return methods, targets

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


def _context(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
