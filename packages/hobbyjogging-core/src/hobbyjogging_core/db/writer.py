"""Write-side access to the canonical database."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from hobbyjogging_core.model import Interval, Lap
from hobbyjogging_core.sports import is_known_sport

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
    "vo2max_garmin",
    "vo2max_runalyze",
}

MANUAL_FIELDS = (
    "duration_s",
    "elapsed_s",
    "distance_m",
    "avg_hr",
    "started_at_utc",
    "local_date",
    "tz_offset_min",
    "sport",
    "training_load",
    "vo2max_garmin",
    "vo2max_runalyze",
)

# Fields whose cross-source disagreement is surfaced for review. Subjective
# fields (name, description, feel, rpe, ...) keep their current owner
# silently: two sources naming one ride differently is normal, not a
# decision the human wants to make thousands of times.
CONFLICT_FIELDS = frozenset(
    {
        "duration_s",
        "elapsed_s",
        "distance_m",
        "avg_hr",
        "started_at_utc",
        "local_date",
        "tz_offset_min",
        "sport",
        "training_load",
    }
)

# Cross-source agreement tolerances: (relative, absolute) per field. Values
# inside the tolerance are treated as the same measurement; outside it they
# become a field_conflict review item.
NUMERIC_TOLERANCES = {
    "duration_s": (0.01, 2.0),
    "elapsed_s": (0.01, 2.0),
    "distance_m": (0.01, 10.0),
    "avg_hr": (0.01, 2.0),
}
DEFAULT_NUMERIC_TOLERANCE = (0.01, 0.5)
START_TOLERANCE_S = 15.0
DATETIME_FIELDS = frozenset({"started_at_utc"})


@dataclass(frozen=True)
class FieldConflict:
    """A cross-source field disagreement a human must decide on.

    Produced by upsert_activity when an incoming value meaningfully differs
    from the value already owned by another source. The canonical value is
    NOT changed by a conflict; the review queue drives the decision.
    """

    activity_id: str
    field_name: str
    current_value: object
    incoming_value: object
    current_source: str
    incoming_source: str
    source_record_id: int


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
    ) -> list[FieldConflict]:
        """Write activity values from one source, without automatic priority.

        Precedence is owner-based, not source-based: a manual field is never
        overwritten; the first source to own a field keeps it as long as
        later sources agree (within tolerance); any meaningful cross-source
        disagreement is returned as a FieldConflict for the review queue and
        leaves the stored value untouched. Re-importing from the same source
        refreshes that source's own fields.
        """
        unknown = set(values) - ACTIVITY_COLUMNS
        if unknown:
            raise ValueError(f"Unknown activity fields: {sorted(unknown)}")

        exists = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
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
            return []

        if exists["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

        current = self.connection.execute(
            "SELECT * FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        self.connection.execute(
            """
            UPDATE activities
            SET source_record_id = COALESCE(source_record_id, ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_record_id, activity_id),
        )

        conflicts: list[FieldConflict] = []
        for field, value in values.items():
            action, owner = self._plan_field_update(
                activity_id,
                field,
                source,
                value,
                current[field],
            )

            if action == "write":
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
            elif action == "conflict":
                conflicts.append(
                    FieldConflict(
                        activity_id=activity_id,
                        field_name=field,
                        current_value=current[field],
                        incoming_value=value,
                        current_source=owner,
                        incoming_source=source,
                        source_record_id=source_record_id,
                    )
                )

        return conflicts

    def _plan_field_update(
        self,
        activity_id: str,
        field_name: str,
        source: str,
        value: object,
        current_value: object,
    ) -> tuple[str, str]:
        """Decide what to do with one incoming field value.

        Returns (action, current_source) where action is one of "write",
        "agree", "conflict". "agree" and "conflict" leave the stored value
        and its owner untouched; "conflict" additionally reports the
        disagreement.
        """
        row = self.connection.execute(
            """
            SELECT source, is_manual FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()

        if row is not None and row["is_manual"]:
            return "agree", "manual"

        if row is None or row["source"] == source:
            return "write", source

        current_source = row["source"]

        if current_value is None:
            return "write", current_source  # fill a gap the owner left

        if value is None:
            return "agree", current_source  # incoming source has no value

        if field_name == "vo2max_garmin":
            # FIT owns the Garmin estimate. Runalyze may only fill an empty
            # slot with its own estimate (handled by the NULL check above);
            # a later FIT import replaces that fallback.
            if source == "runalyze":
                return "agree", current_source
            if source == "fit":
                return "write", current_source

        if field_name == "sport":
            # "generic"/"other" is a placeholder, not a competing claim: a
            # specific sport fills it, and never conflicts with it.
            if not is_known_sport(value) and is_known_sport(current_value):
                return "agree", current_source
            if is_known_sport(value) and not is_known_sport(current_value):
                return "write", current_source

        if field_name not in CONFLICT_FIELDS:
            return "agree", current_source

        if self._values_conflict(current_value, value, field_name):
            return "conflict", current_source

        return "agree", current_source

    def _values_conflict(
        self,
        current: object,
        incoming: object,
        field_name: str,
    ) -> bool:
        """True when two source values for one field meaningfully differ."""
        if field_name in DATETIME_FIELDS:
            difference = _timestamp_difference_s(current, incoming)
            if difference is None:
                return str(current) != str(incoming)
            return difference > START_TOLERANCE_S

        if isinstance(current, (int, float)) and isinstance(
            incoming, (int, float)
        ):
            relative, absolute = NUMERIC_TOLERANCES.get(
                field_name,
                DEFAULT_NUMERIC_TOLERANCE,
            )
            tolerance = max(absolute, relative * abs(float(current)))
            return abs(float(current) - float(incoming)) > tolerance

        return current != incoming

    def exclude_activity(
        self,
        activity_id: str,
        *,
        resolve_note: str = "excluded",
    ) -> int:
        """Durably soft-delete an activity.

        Marks the activity and every linked source record as excluded so
        reports hide it and reimports never resurrect it (source records are
        skipped while excluded). Open review items are resolved so the
        activity also leaves the review queue. Rows are retained for audit.
        Returns the number of review items that were resolved.
        """
        row = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"unknown activity: {activity_id}")

        if row["excluded_at"]:
            return 0

        self.connection.execute(
            """
            UPDATE activities
            SET excluded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (activity_id,),
        )

        source_records = self.connection.execute(
            """
            SELECT sr.id
            FROM source_records sr
            JOIN activity_sources als ON als.source_record_id = sr.id
            WHERE als.activity_id = ?
            """,
            (activity_id,),
        ).fetchall()

        for source_record in source_records:
            self.connection.execute(
                """
                UPDATE source_records
                SET excluded_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (source_record["id"],),
            )

        cursor = self.connection.execute(
            """
            UPDATE review_items
            SET status = 'resolved',
                resolved_at = CURRENT_TIMESTAMP,
                resolved_note = ?
            WHERE activity_id = ? AND status = 'open'
            """,
            (resolve_note, activity_id),
        )
        return cursor.rowcount

    def restore_activity(
        self,
        activity_id: str,
    ) -> None:
        """Undo an exclusion; review items stay resolved."""
        self.connection.execute(
            """
            UPDATE activities
            SET excluded_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (activity_id,),
        )

        source_records = self.connection.execute(
            """
            SELECT sr.id
            FROM source_records sr
            JOIN activity_sources als ON als.source_record_id = sr.id
            WHERE als.activity_id = ?
            """,
            (activity_id,),
        ).fetchall()

        for source_record in source_records:
            self.connection.execute(
                """
                UPDATE source_records
                SET excluded_at = NULL
                WHERE id = ?
                """,
                (source_record["id"],),
            )

    def is_activity_excluded(self, activity_id: str | None) -> bool:
        """True when the activity exists and is excluded (soft-deleted)."""
        if activity_id is None:
            return False

        row = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        return bool(row and row["excluded_at"])

    def set_manual_field(
        self,
        activity_id: str,
        field_name: str,
        value: object,
    ) -> None:
        """Write one activity value as a manual override.

        The value outranks every import source and is protected from being
        overwritten by reimports. Use clear_manual_field to hand the field
        back to importers.
        """
        if field_name not in MANUAL_FIELDS:
            raise ValueError(f"field cannot be edited: {field_name}")

        row = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"unknown activity: {activity_id}")
        if row["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

        self.connection.execute(
            f"UPDATE activities SET {field_name} = ?, "
            f"updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, activity_id),
        )
        self.connection.execute(
            """
            INSERT INTO activity_field_sources (
                activity_id, field_name, source, source_record_id,
                value_json, is_manual
            ) VALUES (?, ?, 'manual', NULL, ?, 1)
            ON CONFLICT(activity_id, field_name) DO UPDATE SET
                source = 'manual',
                source_record_id = NULL,
                value_json = excluded.value_json,
                is_manual = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (activity_id, field_name, json.dumps(value, default=str)),
        )

    def clear_manual_field(
        self,
        activity_id: str,
        field_name: str,
    ) -> bool:
        """Remove a manual override so imports can own the field again."""
        if field_name not in MANUAL_FIELDS:
            raise ValueError(f"field cannot be edited: {field_name}")

        cursor = self.connection.execute(
            """
            DELETE FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ? AND is_manual = 1
            """,
            (activity_id, field_name),
        )
        return cursor.rowcount > 0

    def is_source_record_excluded(
        self,
        *,
        source: str,
        record_type: str,
        external_id: str,
    ) -> bool:
        """True when a known source record is excluded (soft-deleted)."""
        row = self.connection.execute(
            """
            SELECT excluded_at FROM source_records
            WHERE source = ? AND record_type = ? AND external_id = ?
            """,
            (source, record_type, external_id),
        ).fetchone()
        return bool(row and row["excluded_at"])

    def link_activity_source(
        self,
        activity_id: str,
        source_record_id: int,
        *,
        match_method: str = "external_id",
        confidence: float | None = None,
    ) -> None:
        excluded = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if excluded is None:
            raise ValueError(f"unknown activity: {activity_id}")

        if excluded["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

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

    def replace_activity_tags(
        self,
        activity_id: str,
        tags: list[str],
        *,
        source: str,
        source_record_id: int | None = None,
        is_manual: bool = False,
    ) -> int:
        """Replace one source's tags for an activity.

        A reimport replaces only its own non-manual tags; manual tags
        (``is_manual = 1``) are never touched. Pass ``is_manual=True`` to
        replace the manual tag set explicitly. Returns the number of tags
        written.
        """
        row = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"unknown activity: {activity_id}")
        if row["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

        self.connection.execute(
            """
            DELETE FROM activity_tags
            WHERE activity_id = ? AND source = ? AND is_manual = ?
            """,
            (activity_id, source, 1 if is_manual else 0),
        )

        cleaned = _clean_tags(tags)
        if cleaned:
            self.connection.executemany(
                """
                INSERT INTO activity_tags (
                    activity_id, tag, source, source_record_id, is_manual
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(activity_id, tag, source) DO UPDATE SET
                    source_record_id = excluded.source_record_id,
                    is_manual = excluded.is_manual
                """,
                [
                    (
                        activity_id,
                        tag,
                        source,
                        source_record_id,
                        1 if is_manual else 0,
                    )
                    for tag in cleaned
                ],
            )

        return len(cleaned)

    def record_review_item(
        self,
        *,
        category: str,
        detail: str,
        fingerprint: str,
        activity_id: str | None = None,
        source_record_id: int | None = None,
        import_run_id: int | None = None,
        context: dict | None = None,
        severity: str = "warn",
    ) -> int:
        """Insert a review item unless its fingerprint already exists.

        The fingerprint makes detection idempotent: reimporting the same
        problem never duplicates an item and never reopens a resolved one.
        ``source_record_id`` is provenance, not identity: the same canonical
        finding detected during an import and again during `review scan` must
        share one item even though only the import knows the source record.
        Returns (review_item_id, created).
        """
        row = self.connection.execute(
            """
            SELECT id FROM review_items
            WHERE category = ? AND fingerprint = ?
              AND COALESCE(activity_id, '') = COALESCE(?, '')
            """,
            (
                category,
                fingerprint,
                activity_id,
            ),
        ).fetchone()

        if row is not None:
            return row["id"], False

        cursor = self.connection.execute(
            """
            INSERT INTO review_items (
                activity_id, source_record_id, import_run_id,
                category, detail, context_json, fingerprint, severity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                source_record_id,
                import_run_id,
                category,
                detail,
                json.dumps(context or {}, sort_keys=True),
                fingerprint,
                severity,
            ),
        )
        return cursor.lastrowid, True

    def review_items(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        severity: str | None = None,
    ) -> list[sqlite3.Row]:
        """Read review items joined with activity and source-record info."""
        clauses = []
        params: list[object] = []

        if status is not None and status != "all":
            clauses.append("r.status = ?")
            params.append(status)

        if category is not None:
            clauses.append("r.category = ?")
            params.append(category)

        if severity is not None:
            clauses.append("r.severity = ?")
            params.append(severity)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        return self.connection.execute(
            f"""
            SELECT
                r.id, r.activity_id, r.source_record_id, r.import_run_id,
                r.category, r.detail, r.context_json, r.fingerprint,
                r.status, r.severity, r.reported_at, r.resolved_at,
                r.resolved_note,
                a.local_date, a.name AS activity_name, a.sport,
                a.excluded_at AS activity_excluded_at,
                sr.source AS record_source, sr.external_id,
                sr.record_type AS record_type
            FROM review_items r
            LEFT JOIN activities a ON a.id = r.activity_id
            LEFT JOIN source_records sr
                ON sr.id = r.source_record_id
            {where}
            ORDER BY
                CASE r.status WHEN 'open' THEN 0 ELSE 1 END,
                CASE r.severity
                    WHEN 'error' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END,
                r.reported_at, r.id
            """,
            params,
        ).fetchall()

    def review_item(self, review_item_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT
                r.id, r.activity_id, r.source_record_id, r.import_run_id,
                r.category, r.detail, r.context_json, r.fingerprint,
                r.status, r.severity, r.reported_at, r.resolved_at,
                r.resolved_note,
                a.local_date, a.name AS activity_name, a.sport,
                a.excluded_at AS activity_excluded_at,
                sr.source AS record_source, sr.external_id,
                sr.record_type AS record_type
            FROM review_items r
            LEFT JOIN activities a ON a.id = r.activity_id
            LEFT JOIN source_records sr ON sr.id = r.source_record_id
            WHERE r.id = ?
            """,
            (review_item_id,),
        ).fetchone()

    def set_review_status(
        self,
        review_item_id: int,
        status: str,
        *,
        note: str = "",
    ) -> None:
        if status not in ("open", "ignored", "resolved"):
            raise ValueError(f"invalid review status: {status}")

        resolved_at = (
            "CURRENT_TIMESTAMP" if status in ("ignored", "resolved") else None
        )

        if resolved_at is not None:
            self.connection.execute(
                """
                UPDATE review_items
                SET status = ?, resolved_at = CURRENT_TIMESTAMP,
                    resolved_note = ?
                WHERE id = ?
                """,
                (status, note, review_item_id),
            )
        else:
            self.connection.execute(
                """
                UPDATE review_items
                SET status = ?, resolved_at = NULL, resolved_note = ?
                WHERE id = ?
                """,
                (status, note, review_item_id),
            )

    def resolve_review_match(
        self,
        review_item_id: int,
        activity_id: str,
        *,
        note: str = "",
    ) -> None:
        """Resolve an ambiguous-match item by linking its source record.

        The source record is re-linked to the chosen canonical activity.
        Field values from the source are applied by re-running the relevant
        importer for that record.
        """
        item = self.review_item(review_item_id)

        if item is None:
            raise ValueError(f"unknown review item: {review_item_id}")

        if item["source_record_id"] is None:
            raise ValueError(
                "review item has no source record to link "
                f"(id {review_item_id})"
            )

        exists = self.connection.execute(
            "SELECT 1 FROM activities WHERE id = ?", (activity_id,)
        ).fetchone()

        if exists is None:
            raise ValueError(f"unknown activity: {activity_id}")

        self.connection.execute(
            "DELETE FROM activity_sources WHERE source_record_id = ?",
            (item["source_record_id"],),
        )
        self.link_activity_source(
            activity_id,
            item["source_record_id"],
            match_method="review_resolved",
        )
        self.set_review_status(review_item_id, "resolved", note=note)

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


def _timestamp_difference_s(current: object, incoming: object) -> float | None:
    """Seconds between two ISO-8601 timestamps; None when unparseable."""
    try:
        first = _parse_timestamp(current)
        second = _parse_timestamp(incoming)
    except (ValueError, TypeError):
        return None

    if first is None or second is None:
        return None

    try:
        return abs((first - second).total_seconds())
    except TypeError:
        return None


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value)


def _clean_tags(tags: list[str]) -> list[str]:
    """Strip, drop empties, and de-duplicate tags while preserving order."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        text = str(tag or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned
