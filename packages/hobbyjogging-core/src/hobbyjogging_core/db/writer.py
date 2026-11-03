"""Write-side access to the canonical database."""

import json
import sqlite3

from hobbyjogging_core.model import Interval, Lap

ACTIVITY_COLUMNS = {
    "local_date",
    "started_at_utc",
    "tz_offset_min",
    "sport",
    "sub_sport",
    "name",
    "description",
    "duration_s",
    "elapsed_s",
    "distance_m",
    "avg_hr",
    "training_load",
    "rpe",
    "feel",
    "intensity",
}

TIMING_FIELDS = {
    "local_date",
    "started_at_utc",
    "tz_offset_min",
    "duration_s",
    "elapsed_s",
    "distance_m",
    "avg_hr",
}

SOURCE_PRIORITY = {
    "fit": {"timing": 30, "other": 10},
    "intervals": {"timing": 20, "other": 20},
    "manual": {"timing": 100, "other": 100},
}

DEFAULT_PRIORITY = 10


class TrainingWriter:
    """Persist imported data into the canonical schema.

    Methods deliberately do not commit; callers should wrap a batch in a
    transaction. Import-run start/finish are the exception because they must
    remain visible if a batch later fails.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def start_import_run(
        self,
        source: str,
        parameters: dict | None = None,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO import_runs (source, parameters_json)
            VALUES (?, ?)
            """,
            (
                source,
                json.dumps(parameters, sort_keys=True) if parameters else None,
            ),
        )
        self.connection.commit()
        return cursor.lastrowid

    def finish_import_run(
        self,
        run_id: int,
        status: str,
        *,
        records_seen: int = 0,
        records_imported: int = 0,
        records_skipped: int = 0,
        error: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE import_runs
            SET
                finished_at = CURRENT_TIMESTAMP,
                status = ?,
                records_seen = ?,
                records_imported = ?,
                records_skipped = ?,
                error = ?
            WHERE id = ?
            """,
            (
                status,
                records_seen,
                records_imported,
                records_skipped,
                error,
                run_id,
            ),
        )
        self.connection.commit()

    def upsert_source_record(
        self,
        *,
        source: str,
        record_type: str,
        external_id: str,
        checksum: str,
        import_run_id: int,
        payload_json: str | None = None,
        raw_path: str | None = None,
    ) -> int:
        row = self.connection.execute(
            """
            SELECT id FROM source_records
            WHERE source = ? AND record_type = ? AND external_id = ?
            """,
            (source, record_type, external_id),
        ).fetchone()

        if row is not None:
            self.connection.execute(
                """
                UPDATE source_records
                SET
                    import_run_id = ?,
                    checksum = ?,
                    payload_json = ?,
                    raw_path = ?,
                    fetched_at = CURRENT_TIMESTAMP,
                    imported_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    import_run_id,
                    checksum,
                    payload_json,
                    raw_path,
                    row["id"],
                ),
            )
            return row["id"]

        cursor = self.connection.execute(
            """
            INSERT INTO source_records (
                import_run_id, source, record_type, external_id,
                checksum, payload_json, raw_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_run_id,
                source,
                record_type,
                external_id,
                checksum,
                payload_json,
                raw_path,
            ),
        )
        return cursor.lastrowid

    def upsert_activity(
        self,
        activity_id: str,
        values: dict[str, object],
        *,
        source: str,
        source_record_id: int,
    ) -> None:
        unknown = set(values) - ACTIVITY_COLUMNS
        if unknown:
            raise ValueError(f"Unknown activity fields: {sorted(unknown)}")

        exists = self.connection.execute(
            "SELECT 1 FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if exists is None:
            columns = ["id", "source_record_id", *values]
            placeholders = ", ".join("?" for _ in columns)
            self.connection.execute(
                f"INSERT INTO activities ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                [activity_id, source_record_id, *values.values()],
            )
            for field, value in values.items():
                self._record_field_source(
                    activity_id,
                    field,
                    source,
                    source_record_id,
                    value,
                )
            return

        self.connection.execute(
            """
            UPDATE activities
            SET source_record_id = COALESCE(source_record_id, ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_record_id, activity_id),
        )

        for field, value in values.items():
            if not self._should_update_field(activity_id, field, source):
                continue

            self.connection.execute(
                f"UPDATE activities SET {field} = ?, "
                f"updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (value, activity_id),
            )
            self._record_field_source(
                activity_id,
                field,
                source,
                source_record_id,
                value,
            )

    def link_activity_source(
        self,
        activity_id: str,
        source_record_id: int,
        *,
        match_method: str = "external_id",
        confidence: float | None = None,
    ) -> None:
        existing = self.connection.execute(
            """
            SELECT id FROM activity_sources
            WHERE activity_id = ? AND source_record_id = ?
            """,
            (activity_id, source_record_id),
        ).fetchone()

        if existing is not None:
            return

        has_primary = self.connection.execute(
            """
            SELECT 1 FROM activity_sources
            WHERE activity_id = ? AND is_primary = 1
            """,
            (activity_id,),
        ).fetchone()

        self.connection.execute(
            """
            INSERT INTO activity_sources (
                activity_id, source_record_id, match_method,
                confidence, is_primary
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                source_record_id,
                match_method,
                confidence,
                1 if has_primary is None else 0,
            ),
        )

    def set_activity_zone_times(
        self,
        activity_id: str,
        kind: str,
        zone_times: list[float],
    ) -> None:
        self.connection.execute(
            "DELETE FROM activity_zone_times "
            "WHERE activity_id = ? AND kind = ?",
            (activity_id, kind),
        )
        rows = [
            (activity_id, kind, index, seconds)
            for index, seconds in enumerate(zone_times, start=1)
            if seconds
        ]
        if rows:
            self.connection.executemany(
                """
                INSERT INTO activity_zone_times (
                    activity_id, kind, zone_index, seconds
                ) VALUES (?, ?, ?, ?)
                """,
                rows,
            )

    def replace_activity_intervals(
        self,
        activity_id: str,
        intervals: list[Interval],
        *,
        source_record_id: int | None = None,
    ) -> None:
        self.connection.execute(
            "DELETE FROM activity_intervals WHERE activity_id = ?",
            (activity_id,),
        )
        rows = [
            (
                activity_id,
                index,
                interval.group_id,
                interval.type,
                interval.start_time,
                interval.duration_s,
                interval.distance_m,
                interval.avg_hr,
                interval.max_hr,
                source_record_id,
            )
            for index, interval in enumerate(intervals, start=1)
        ]
        if rows:
            self.connection.executemany(
                """
                INSERT INTO activity_intervals (
                    activity_id, interval_index, group_id, type,
                    start_time, duration_s, distance_m, avg_hr,
                    max_hr, source_record_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def replace_activity_laps(
        self,
        activity_id: str,
        laps: list[Lap],
        *,
        source_record_id: int | None = None,
    ) -> None:
        self.connection.execute(
            "DELETE FROM activity_laps WHERE activity_id = ?",
            (activity_id,),
        )
        rows = [
            (
                activity_id,
                lap.index,
                lap.start_time_utc,
                lap.duration_s,
                lap.distance_m,
                lap.avg_hr,
                lap.max_hr,
                lap.elevation_gain_m,
                source_record_id,
            )
            for lap in laps
        ]
        if rows:
            self.connection.executemany(
                """
                INSERT INTO activity_laps (
                    activity_id, lap_index, start_time_utc,
                    duration_s, distance_m, avg_hr, max_hr,
                    elevation_gain_m, source_record_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def merge_activity_laps(
        self,
        activity_id: str,
        laps: list[Lap],
        *,
        source_record_id: int,
    ) -> None:
        """Replace one source's laps while preserving laps from other sources."""
        existing = self.connection.execute(
            """
            SELECT
                start_time_utc, duration_s, distance_m,
                avg_hr, max_hr, elevation_gain_m, source_record_id
            FROM activity_laps
            WHERE activity_id = ?
              AND (source_record_id IS NULL OR source_record_id != ?)
            """,
            (activity_id, source_record_id),
        ).fetchall()

        combined = [
            (
                row["start_time_utc"] or "",
                row["duration_s"],
                row["distance_m"],
                row["avg_hr"],
                row["max_hr"],
                row["elevation_gain_m"],
                row["source_record_id"],
            )
            for row in existing
        ]
        combined.extend(
            (
                lap.start_time_utc,
                lap.duration_s,
                lap.distance_m,
                lap.avg_hr,
                lap.max_hr,
                lap.elevation_gain_m,
                source_record_id,
            )
            for lap in laps
        )
        combined.sort(key=lambda lap: (not bool(lap[0]), lap[0]))

        self.connection.execute(
            "DELETE FROM activity_laps WHERE activity_id = ?",
            (activity_id,),
        )
        rows = [
            (
                activity_id,
                index,
                *lap,
            )
            for index, lap in enumerate(combined, start=1)
        ]
        if rows:
            self.connection.executemany(
                """
                INSERT INTO activity_laps (
                    activity_id, lap_index, start_time_utc,
                    duration_s, distance_m, avg_hr, max_hr,
                    elevation_gain_m, source_record_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def upsert_wellness(
        self,
        *,
        local_date: str,
        source_record_id: int,
        hrv: float | None = None,
        resting_hr: float | None = None,
        sleep_s: float | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO wellness_days (
                local_date, source_record_id, hrv, resting_hr, sleep_s
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(local_date) DO UPDATE SET
                source_record_id = excluded.source_record_id,
                hrv = COALESCE(excluded.hrv, wellness_days.hrv),
                resting_hr = COALESCE(
                    excluded.resting_hr,
                    wellness_days.resting_hr
                ),
                sleep_s = COALESCE(excluded.sleep_s, wellness_days.sleep_s),
                updated_at = CURRENT_TIMESTAMP
            """,
            (local_date, source_record_id, hrv, resting_hr, sleep_s),
        )

    def upsert_event(
        self,
        *,
        event_id: str,
        local_date: str,
        name: str,
        type: str,
        source_record_id: int,
        description: str = "",
        duration_s: float | None = None,
        distance_m: float | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO events (
                id, source_record_id, local_date, name, type,
                description, duration_s, distance_m
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_record_id = excluded.source_record_id,
                local_date = excluded.local_date,
                name = excluded.name,
                type = excluded.type,
                description = excluded.description,
                duration_s = COALESCE(
                    excluded.duration_s,
                    events.duration_s
                ),
                distance_m = COALESCE(
                    excluded.distance_m,
                    events.distance_m
                ),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                event_id,
                source_record_id,
                local_date,
                name,
                type,
                description,
                duration_s,
                distance_m,
            ),
        )

    def _should_update_field(
        self,
        activity_id: str,
        field_name: str,
        source: str,
    ) -> bool:
        if self._is_manual_field(activity_id, field_name):
            return False

        row = self.connection.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()

        if row is None:
            return True

        return self._field_priority(source, field_name) >= self._field_priority(
            row["source"],
            field_name,
        )

    @staticmethod
    def _field_priority(source: str, field_name: str) -> int:
        kind = "timing" if field_name in TIMING_FIELDS else "other"
        return SOURCE_PRIORITY.get(source, {}).get(kind, DEFAULT_PRIORITY)

    def _is_manual_field(self, activity_id: str, field_name: str) -> bool:
        row = self.connection.execute(
            """
            SELECT is_manual FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()
        return bool(row and row["is_manual"])

    def _record_field_source(
        self,
        activity_id: str,
        field_name: str,
        source: str,
        source_record_id: int,
        value: object,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO activity_field_sources (
                activity_id, field_name, source, source_record_id,
                value_json, is_manual
            ) VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(activity_id, field_name) DO UPDATE SET
                source = excluded.source,
                source_record_id = excluded.source_record_id,
                value_json = excluded.value_json,
                is_manual = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                activity_id,
                field_name,
                source,
                source_record_id,
                json.dumps(value, default=str),
            ),
        )
