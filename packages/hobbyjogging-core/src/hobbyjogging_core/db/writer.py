"""Write-side access to the canonical database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from hobbyjogging_core.model import EventZoneTime, Interval, Lap
from hobbyjogging_core.workouts import (
    WORKOUT_METHODS,
    WORKOUT_TARGETS,
    canonical_method,
    canonical_target,
)
from hobbyjogging_core.import_rules import (
    DATETIME_FIELDS,
    DEFAULT_NUMERIC_TOLERANCE,
    FIELD_RULES,
    MANUAL_FIELDS,
    METRIC_FIELDS,
    NUMERIC_TOLERANCES,
    START_TOLERANCE_S,
    authority_rank,
    metric_authority_rank,
)
from hobbyjogging_core.sports import NO_DISTANCE_SPORTS, is_known_sport

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
    "moving_s",
    "distance_m",
    "elevation_gain_m",
    "elevation_loss_m",
    "max_hr",
    "avg_hr",
    "training_load",
    "rpe",
    "feel",
    "intensity",
    "vo2max_garmin",
    "vo2max_runalyze",
    "device_id",
}

# Field ownership, conflict tolerances and manual-edit permissions live in
# hobbyjogging_core.import_rules. The writer applies them; it does not own a
# second copy.


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
        force: bool = False,
    ) -> list[FieldConflict]:
        """Write activity values from one source, without automatic priority.

        Precedence is owner-based, not source-based: a manual field is never
        overwritten; the first source to own a field keeps it as long as
        later sources agree (within tolerance); any meaningful cross-source
        disagreement is returned as a FieldConflict for the review queue and
        leaves the stored value untouched. Re-importing from the same source
        refreshes that source's own fields.

        ``moving_s`` and ``elapsed_s`` use a ranked authority (Intervals,
        then FIT): a higher-ranked value replaces another source's value
        silently and a lower-ranked value never overrides it or reports a
        conflict. Manual values still win.

        ``force=True`` lets this source take ownership of every non-manual
        field in ``values``, replacing another source's value silently. Manual
        fields are still kept. This is the explicit human trust decision used
        by triage; normal imports never set it.
        """
        unknown = set(values) - ACTIVITY_COLUMNS
        if unknown:
            raise ValueError(f"Unknown activity fields: {sorted(unknown)}")

        current = self.connection.execute(
            "SELECT * FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if current is not None and current["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

        values = self._apply_distance_policy(
            activity_id,
            values,
            current,
            source,
            source_record_id,
        )

        if current is None:
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
            if force:
                action, owner = self._plan_forced_update(
                    activity_id,
                    field,
                )
            else:
                action, owner = self._plan_field_update(
                    activity_id,
                    field,
                    source,
                    value,
                    current[field],
                    current=current,
                    values=values,
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

    def _apply_distance_policy(
        self,
        activity_id: str,
        values: dict[str, object],
        current,
        source: str,
        source_record_id: int,
    ) -> dict[str, object]:
        """Force distance to zero for sports where it is not meaningful.

        Raw source payloads keep whatever the device or service reported; the
        canonical column and its provenance reflect the sport policy. A manual
        distance is never touched.
        """
        sport = self._effective_distance_sport(
            activity_id,
            current,
            values,
            source,
        )
        if sport not in NO_DISTANCE_SPORTS:
            return values

        result = dict(values)
        result.pop("distance_m", None)

        if current is None:
            result["distance_m"] = 0.0
            return result

        if self._is_manual_field(activity_id, "distance_m"):
            return result

        if current["distance_m"] != 0:
            self.connection.execute(
                "UPDATE activities SET distance_m = 0, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (activity_id,),
            )
            self._record_field_source(
                activity_id,
                "distance_m",
                source,
                source_record_id,
                0.0,
            )
        return result

    def _effective_distance_sport(
        self,
        activity_id: str,
        current,
        values: dict[str, object],
        source: str,
    ) -> str:
        incoming = str(values.get("sport") or "")
        if current is None:
            return incoming

        current_sport = str(current["sport"] or "")
        if self._is_manual_field(activity_id, "sport"):
            return current_sport
        if incoming == current_sport:
            return current_sport
        if incoming in ("", "other") and current_sport:
            return current_sport
        if current_sport in ("", "other") and incoming:
            return incoming

        # Both are specific. A cross-source disagreement keeps the current
        # owner's sport; a same-source refresh is allowed to update it.
        row = self.connection.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = ? AND field_name = 'sport'
            """,
            (activity_id,),
        ).fetchone()
        if row is not None and row["source"] == source:
            return incoming
        return current_sport

    def _is_manual_field(
        self,
        activity_id: str,
        field_name: str,
    ) -> bool:
        row = self.connection.execute(
            """
            SELECT is_manual FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()
        return bool(row is not None and row["is_manual"])

    def _manual_owner(
        self,
        activity_id: str,
        field_name: str,
    ) -> str | None:
        row = self.connection.execute(
            """
            SELECT owner_source FROM activity_manual_fields
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()
        return row["owner_source"] if row is not None else None

    def _require_editable_activity(self, activity_id: str) -> None:
        row = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown activity: {activity_id}")
        if row["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

    def _plan_forced_update(
        self,
        activity_id: str,
        field_name: str,
    ) -> tuple[str, str]:
        """Force ownership unless the current owner is a manual edit."""
        row = self.connection.execute(
            """
            SELECT is_manual FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()

        if row is not None and row["is_manual"]:
            return "agree", "manual"
        return "write", ""

    def _plan_field_update(
        self,
        activity_id: str,
        field_name: str,
        source: str,
        value: object,
        current_value: object,
        *,
        current=None,
        values: dict[str, object] | None = None,
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

        if _is_unfilled(current_value):
            return "write", current_source  # fill a gap the owner left

        if value is None:
            return "agree", current_source  # incoming source has no value

        owner = self._manual_owner(activity_id, field_name)
        if owner is not None and source != owner:
            return "agree", current_source  # explicit ownership decision

        rule = FIELD_RULES.get(field_name)

        if rule is not None and rule.authority:
            incoming_rank = authority_rank(rule, source)
            current_rank = authority_rank(rule, current_source)
            # A ranked source replaces an unranked owner only at the top
            # rank. That preserves the old single-authority behaviour while
            # allowing a fallback list for an athlete without the primary.
            if incoming_rank is not None and (
                (current_rank is None and incoming_rank == 0)
                or (current_rank is not None and incoming_rank < current_rank)
            ):
                return "write", current_source
            return "agree", current_source

        if rule is not None and rule.placeholder:
            # "generic"/"other" is a placeholder, not a competing claim: a
            # specific sport fills it, and never conflicts with it.
            if not is_known_sport(value) and is_known_sport(current_value):
                return "agree", current_source
            if is_known_sport(value) and not is_known_sport(current_value):
                return "write", current_source

        if (
            rule is not None
            and rule.pause_accounting
            and current is not None
            and values is not None
        ):
            # Garmin records timer/recording time; Intervals historically
            # offered moving time. A duration difference that fits inside
            # either source's pause gap is accounting noise, not a conflict.
            if _duration_times_agree(
                current["duration_s"],
                current["elapsed_s"],
                value,
                values.get("elapsed_s"),
            ):
                return "agree", current_source

        if rule is None or not rule.conflict:
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

        The value is stored as an input row (``activity_manual_fields``) and
        projected into the activity. The field-source pointer keeps the
        derived owner and its snapshot, marked ``is_manual`` so imports leave
        it alone; ``clear_manual_field`` restores the snapshot.
        """
        if field_name not in MANUAL_FIELDS:
            raise ValueError(f"field cannot be edited: {field_name}")

        self._require_editable_activity(activity_id)

        self.connection.execute(
            f"UPDATE activities SET {field_name} = ?, "
            f"updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, activity_id),
        )
        self.connection.execute(
            """
            INSERT INTO activity_manual_fields (
                activity_id, field_name, value_json, owner_source
            ) VALUES (?, ?, ?, NULL)
            ON CONFLICT(activity_id, field_name) DO UPDATE SET
                value_json = excluded.value_json,
                owner_source = NULL,
                edited_at = CURRENT_TIMESTAMP
            """,
            (activity_id, field_name, json.dumps(value, default=str)),
        )

        row = self.connection.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()

        if row is None or row["source"] == "manual":
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
        else:
            self.connection.execute(
                """
                UPDATE activity_field_sources
                SET is_manual = 1, updated_at = CURRENT_TIMESTAMP
                WHERE activity_id = ? AND field_name = ?
                """,
                (activity_id, field_name),
            )

    def set_manual_owner(
        self,
        activity_id: str,
        field_name: str,
        source: str,
    ) -> None:
        """Record an explicit ownership decision for one field.

        The value is not changed: the forced import already wrote it. The
        patch keeps the chosen source owning the field, so a rebuild and a
        ranked source cannot silently override the decision.
        """
        if field_name not in ACTIVITY_COLUMNS:
            raise ValueError(f"unknown activity field: {field_name}")
        if not str(source).strip():
            raise ValueError("source must not be empty")

        self._require_editable_activity(activity_id)
        self.connection.execute(
            """
            INSERT INTO activity_manual_fields (
                activity_id, field_name, owner_source, value_json
            ) VALUES (?, ?, ?, NULL)
            ON CONFLICT(activity_id, field_name) DO UPDATE SET
                owner_source = excluded.owner_source,
                value_json = NULL,
                edited_at = CURRENT_TIMESTAMP
            """,
            (activity_id, field_name, source),
        )

    def record_edit_log(
        self,
        *,
        entity_kind: str,
        entity_id: str,
        field: str,
        old: object,
        new: object,
        source: str = "manual",
        note: str = "",
    ) -> None:
        """Append one manual change to the audit trail.

        The log is append-only (enforced by triggers): a later edit adds a
        row instead of rewriting history. It is written in the same
        transaction as the value it describes.
        """
        self.connection.execute(
            """
            INSERT INTO edit_log (
                entity_kind, entity_id, field, old_json, new_json,
                source, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_kind,
                entity_id,
                field,
                json.dumps(old, default=str),
                json.dumps(new, default=str),
                source,
                note,
            ),
        )

    def project_activity_field(
        self,
        activity_id: str,
        field_name: str,
        value: object,
        *,
        update_snapshot: bool = True,
    ) -> None:
        """Write a derived value back to the canonical row.

        Only the rebuild uses this: it keeps the stored owner and writes the
        value that owner's payload derives. ``update_snapshot=False`` is for a
        manual value, whose pointer snapshot belongs to the underlying source.
        """
        if field_name not in ACTIVITY_COLUMNS:
            raise ValueError(f"unknown activity field: {field_name}")

        self._require_editable_activity(activity_id)
        self._write_activity_field(activity_id, field_name, value)

        if update_snapshot:
            self.connection.execute(
                """
                UPDATE activity_field_sources
                SET value_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE activity_id = ? AND field_name = ?
                """,
                (
                    json.dumps(value, default=str),
                    activity_id,
                    field_name,
                ),
            )

    def clear_manual_field(
        self,
        activity_id: str,
        field_name: str,
    ) -> bool:
        """Remove a manual input and re-project the field.

        A manual value is restored from the field-source snapshot; a field
        with no derived owner falls back to the column default (zero, or the
        ``other`` sport). A required field with no source and no fallback
        cannot be cleared. An owner patch is removed without changing the
        current projection.
        """
        if field_name not in MANUAL_FIELDS:
            raise ValueError(f"field cannot be edited: {field_name}")

        self._require_editable_activity(activity_id)

        row = self.connection.execute(
            """
            SELECT owner_source FROM activity_manual_fields
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()
        if row is None:
            return False

        if row["owner_source"] is not None:
            self._delete_manual_input(activity_id, field_name)
            return True

        pointer = self.connection.execute(
            """
            SELECT source, value_json FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, field_name),
        ).fetchone()

        if pointer is not None and pointer["source"] != "manual":
            try:
                value = json.loads(pointer["value_json"])
            except (TypeError, ValueError):
                value = pointer["value_json"]
            self._delete_manual_input(activity_id, field_name)
            self._write_activity_field(activity_id, field_name, value)
            self.connection.execute(
                """
                UPDATE activity_field_sources
                SET is_manual = 0, updated_at = CURRENT_TIMESTAMP
                WHERE activity_id = ? AND field_name = ?
                """,
                (activity_id, field_name),
            )
            return True

        clearable, fallback = self._cleared_value(field_name)
        if not clearable:
            return False

        self._delete_manual_input(activity_id, field_name)
        if pointer is not None:
            self.connection.execute(
                "DELETE FROM activity_field_sources "
                "WHERE activity_id = ? AND field_name = ?",
                (activity_id, field_name),
            )
        self._write_activity_field(activity_id, field_name, fallback)
        return True

    def _delete_manual_input(
        self,
        activity_id: str,
        field_name: str,
    ) -> None:
        self.connection.execute(
            "DELETE FROM activity_manual_fields "
            "WHERE activity_id = ? AND field_name = ?",
            (activity_id, field_name),
        )

    def _write_activity_field(
        self,
        activity_id: str,
        field_name: str,
        value: object,
    ) -> None:
        self.connection.execute(
            f"UPDATE activities SET {field_name} = ?, "
            f"updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, activity_id),
        )

    def _cleared_value(self, field_name: str) -> tuple[bool, object]:
        """The value a field falls back to when no source owns it."""
        columns = {
            row["name"]: row
            for row in self.connection.execute("PRAGMA table_info(activities)")
        }
        column = columns.get(field_name)
        if column is None:
            return False, None
        if not column["notnull"]:
            return True, None
        default = column["dflt_value"]
        if default is not None:
            text = str(default).strip()
            if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
                return True, text[1:-1]
            if text.upper() == "NULL":
                return True, None
            try:
                return True, float(text)
            except ValueError:
                return True, text
        if str(column["type"]).upper().startswith(("INT", "REAL", "NUM")):
            return True, 0
        if field_name == "sport":
            return True, "other"
        return False, None

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
        source: str = "",
    ) -> None:
        self.connection.execute(
            "DELETE FROM activity_intervals WHERE activity_id = ?",
            (activity_id,),
        )
        self._insert_intervals(
            activity_id,
            intervals,
            source_record_id=source_record_id,
            source=source,
        )

    def stamp_interval_source(
        self,
        source: str,
        *,
        previous: str = "",
    ) -> int:
        """Set the provenance of intervals that predate the source column."""
        cursor = self.connection.execute(
            "UPDATE activity_intervals SET source = ? WHERE source = ?",
            (source, previous),
        )
        return cursor.rowcount

    def replace_derived_intervals(        self,
        activity_id: str,
        intervals: list[Interval],
    ) -> bool:
        """Replace a derived set, never a measured one.

        Returns ``False`` when the activity carries any interval whose source
        is neither empty nor ``derived`` — an Intervals.icu or manual set wins.
        """
        row = self.connection.execute(
            """
            SELECT 1 FROM activity_intervals
            WHERE activity_id = ? AND source NOT IN ('', 'derived')
            LIMIT 1
            """,
            (activity_id,),
        ).fetchone()
        if row is not None:
            return False

        self.connection.execute(
            """
            DELETE FROM activity_intervals
            WHERE activity_id = ? AND source = 'derived'
            """,
            (activity_id,),
        )
        self._insert_intervals(
            activity_id,
            intervals,
            source_record_id=None,
            source="derived",
        )
        return True

    def _insert_intervals(        self,
        activity_id: str,
        intervals: list[Interval],
        *,
        source_record_id: int | None,
        source: str,
    ) -> None:
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
                interval.source or source,
            )
            for index, interval in enumerate(intervals, start=1)
        ]
        if rows:
            self.connection.executemany(
                """
                INSERT INTO activity_intervals (
                    activity_id, interval_index, group_id, type,
                    start_time, duration_s, distance_m, avg_hr,
                    max_hr, source_record_id, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def upsert_route(
        self,
        route_id: str,
        *,
        name: str,
        source: str,
        external_ref: str | None = None,
        distance_m: float | None = None,
        notes: str = "",
    ) -> bool:
        """Write one route, leaving a manual route untouched.

        A reimport from the same source refreshes the name and fills a missing
        distance or external reference; it never clears a value. Returns
        ``True`` when a row was written.
        """
        if not route_id:
            raise ValueError("route id must not be empty")
        if not name:
            raise ValueError("route name must not be empty")

        existing = self.connection.execute(
            "SELECT source FROM routes WHERE id = ?",
            (route_id,),
        ).fetchone()

        if existing is None:
            self.connection.execute(
                """
                INSERT INTO routes (
                    id, name, external_ref, distance_m, source, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (route_id, name, external_ref, distance_m, source, notes),
            )
            return True

        if existing["source"] == "manual" and source != "manual":
            return False

        self.connection.execute(
            """
            UPDATE routes SET
                name = COALESCE(NULLIF(?, ''), name),
                external_ref = COALESCE(?, external_ref),
                distance_m = COALESCE(?, distance_m),
                notes = COALESCE(NULLIF(?, ''), notes),
                excluded_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, external_ref, distance_m, notes, route_id),
        )
        return True

    def replace_activity_routes(
        self,
        activity_id: str,
        route_ids: list[str],
        *,
        source: str,
        source_record_id: int | None = None,
        is_manual: bool = False,
    ) -> int:
        """Replace one source's routes for an activity.

        A reimport replaces only its own non-manual links; manual links are
        never touched. Returns the number of links written.
        """
        row = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"unknown activity: {activity_id}")
        if row["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

        cleaned = list(dict.fromkeys(route for route in route_ids if route))
        if cleaned:
            placeholders = ", ".join("?" for _ in cleaned)
            known = {
                item["id"]
                for item in self.connection.execute(
                    f"SELECT id FROM routes WHERE id IN ({placeholders})",
                    cleaned,
                )
            }
            missing = [route for route in cleaned if route not in known]
            if missing:
                raise ValueError(f"unknown routes: {missing}")

        self.connection.execute(
            """
            DELETE FROM activity_routes
            WHERE activity_id = ? AND source = ? AND is_manual = ?
            """,
            (activity_id, source, 1 if is_manual else 0),
        )

        if cleaned:
            self.connection.executemany(
                """
                INSERT INTO activity_routes (
                    activity_id, route_id, source, source_record_id, is_manual
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(activity_id, route_id, source) DO UPDATE SET
                    source_record_id = excluded.source_record_id,
                    is_manual = excluded.is_manual
                """,
                [
                    (
                        activity_id,
                        route,
                        source,
                        source_record_id,
                        1 if is_manual else 0,
                    )
                    for route in cleaned
                ],
            )

        return len(cleaned)

    def replace_event_activity_links(
        self,
        event_id: str,
        activity_ids: list[str],
        *,
        match_method: str = "auto",
        confidence: float | None = None,
    ) -> int:
        """Replace an event's automatic activity links, keeping manual ones."""
        event = self.connection.execute(
            "SELECT 1 FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if event is None:
            raise ValueError(f"unknown event: {event_id}")

        cleaned = list(dict.fromkeys(item for item in activity_ids if item))
        if cleaned:
            placeholders = ", ".join("?" for _ in cleaned)
            rows = self.connection.execute(
                f"SELECT id FROM activities WHERE id IN ({placeholders}) "
                "AND excluded_at IS NULL",
                cleaned,
            ).fetchall()
            known = {row["id"] for row in rows}
            missing = [item for item in cleaned if item not in known]
            if missing:
                raise ValueError(f"unknown or excluded activities: {missing}")

        self.connection.execute(
            "DELETE FROM event_activity_links "
            "WHERE event_id = ? AND is_manual = 0",
            (event_id,),
        )

        if cleaned:
            self.connection.executemany(
                """
                INSERT INTO event_activity_links (
                    event_id, activity_id, match_method, confidence, is_manual
                ) VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(event_id, activity_id) DO UPDATE SET
                    match_method = excluded.match_method,
                    confidence = excluded.confidence,
                    is_manual = 0,
                    linked_at = CURRENT_TIMESTAMP
                """,
                [
                    (event_id, item, match_method, confidence)
                    for item in cleaned
                ],
            )

        return len(cleaned)

    def upsert_equipment(
        self,
        equipment_id: str,
        *,
        type: str,
        name: str,
        brand: str = "",
        model: str = "",
        acquired_on: date | str | None = None,
        retired_on: date | str | None = None,
        target_distance_m: float | None = None,
        notes: str = "",
        source_record_id: int | None = None,
        is_manual: bool = False,
    ) -> bool:
        """Create or update one piece of equipment.

        Equipment is keyed by a stable id, so reimporting the same source row
        refreshes it instead of duplicating it. A manual row is an input: a
        source only attaches its link and never rewrites the fields. Returns
        ``True`` when the row was created.
        """
        if not str(equipment_id).strip():
            raise ValueError("equipment id must not be empty")
        if not str(name).strip():
            raise ValueError("equipment name must not be empty")

        existing = self.connection.execute(
            "SELECT is_manual FROM equipment WHERE id = ?",
            (equipment_id,),
        ).fetchone()

        if existing is not None and existing["is_manual"] and not is_manual:
            self._link_equipment_record(equipment_id, source_record_id)
            return False

        self.connection.execute(
            """
            INSERT INTO equipment (
                id, type, name, brand, model,
                acquired_on, retired_on, target_distance_m, notes, is_manual
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                name = excluded.name,
                brand = excluded.brand,
                model = excluded.model,
                acquired_on = excluded.acquired_on,
                retired_on = excluded.retired_on,
                target_distance_m = excluded.target_distance_m,
                notes = excluded.notes,
                is_manual = excluded.is_manual,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(equipment_id),
                str(type),
                str(name),
                str(brand or ""),
                str(model or ""),
                _iso_date(acquired_on),
                _iso_date(retired_on),
                target_distance_m,
                str(notes or ""),
                1 if is_manual else 0,
            ),
        )

        self._link_equipment_record(equipment_id, source_record_id)
        return existing is None

    def _link_equipment_record(
        self,
        equipment_id: str,
        source_record_id: int | None,
    ) -> None:
        if source_record_id is None:
            return
        self.connection.execute(
            """
            DELETE FROM equipment_source_links
            WHERE source_record_id = ?
            """,
            (source_record_id,),
        )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO equipment_source_links (
                equipment_id, source_record_id
            ) VALUES (?, ?)
            """,
            (str(equipment_id), source_record_id),
        )

    def link_equipment_source(
        self,
        equipment_id: str,
        source_record_id: int,
    ) -> bool:
        """Attach a source record to an existing equipment row, unchanged.

        A gear record that matches a sheet or manual item must not overwrite
        that item's name, brand, model or dates; this records provenance only.
        A source record points at one equipment row, so re-resolving it moves
        the link. Returns ``True`` when a link was written or moved.
        """
        if not str(equipment_id).strip():
            raise ValueError("equipment id must not be empty")

        equipment = self.connection.execute(
            "SELECT 1 FROM equipment WHERE id = ?",
            (equipment_id,),
        ).fetchone()
        if equipment is None:
            raise ValueError(f"unknown equipment: {equipment_id}")

        source = self.connection.execute(
            "SELECT 1 FROM source_records WHERE id = ?",
            (source_record_id,),
        ).fetchone()
        if source is None:
            raise ValueError(f"unknown source record: {source_record_id}")

        existing = self.connection.execute(
            """
            SELECT equipment_id FROM equipment_source_links
            WHERE source_record_id = ?
            """,
            (source_record_id,),
        ).fetchone()
        if existing is not None and existing["equipment_id"] == equipment_id:
            return False

        self.connection.execute(
            """
            INSERT INTO equipment_source_links (equipment_id, source_record_id)
            VALUES (?, ?)
            ON CONFLICT(source_record_id) DO UPDATE SET
                equipment_id = excluded.equipment_id
            """,
            (equipment_id, source_record_id),
        )
        return True

    def link_activity_equipment(
        self,
        activity_id: str,
        equipment_id: str,
        *,
        source: str,
        source_record_id: int | None = None,
        role: str = "primary",
        is_manual: bool = False,
    ) -> bool:
        """Attach equipment to an activity.

        A manual link is never replaced by an import, and the first import
        source keeps the primary slot until a human changes it. Returns
        ``True`` when a link was written or refreshed.
        """
        activity = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

        if activity is None:
            raise ValueError(f"unknown activity: {activity_id}")
        if activity["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

        equipment = self.connection.execute(
            "SELECT 1 FROM equipment WHERE id = ?",
            (equipment_id,),
        ).fetchone()
        if equipment is None:
            raise ValueError(f"unknown equipment: {equipment_id}")

        existing = self.connection.execute(
            """
            SELECT equipment_id, source, is_manual
            FROM activity_equipment
            WHERE activity_id = ? AND role = ?
            """,
            (activity_id, role),
        ).fetchone()

        if existing is not None:
            if not is_manual:
                if existing["is_manual"]:
                    return False
                if existing["source"] != source:
                    return False
            if (
                existing["equipment_id"] == equipment_id
                and bool(existing["is_manual"]) == is_manual
            ):
                return False
            self.connection.execute(
                """
                DELETE FROM activity_equipment
                WHERE activity_id = ? AND role = ?
                """,
                (activity_id, role),
            )

        self.connection.execute(
            """
            INSERT INTO activity_equipment (
                activity_id, equipment_id, role, source,
                source_record_id, is_manual
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                equipment_id,
                role,
                source,
                source_record_id,
                1 if is_manual else 0,
            ),
        )
        return True

    def unlink_activity_equipment(
        self,
        activity_id: str,
        *,
        source: str,
        equipment_type: str | None = None,
    ) -> int:
        """Remove non-manual equipment links written by one source.

        A manual link always survives. ``equipment_type`` limits the removal
        to one kind (for example, shoes on a ride). Returns the row count.
        """
        clauses = ["activity_id = ?", "source = ?", "is_manual = 0"]
        params: list[object] = [activity_id, source]

        if equipment_type is not None:
            clauses.append(
                "equipment_id IN "
                "(SELECT id FROM equipment WHERE type = ?)"
            )
            params.append(equipment_type)

        cursor = self.connection.execute(
            f"DELETE FROM activity_equipment WHERE {' AND '.join(clauses)}",
            params,
        )
        return cursor.rowcount

    def set_manual_activity_equipment(
        self,
        activity_id: str,
        equipment_ids: list[str],
    ) -> int:
        """Replace the manual equipment links for one activity.

        The first id becomes the primary item and the rest are secondary.
        Import links are left alone unless the manual primary displaces one
        in the primary slot (the writer's usual manual-wins rule).
        """
        self._require_editable_activity(activity_id)

        cleaned: list[str] = []
        for equipment_id in equipment_ids:
            text = str(equipment_id or "").strip()
            if not text or text in cleaned:
                continue
            cleaned.append(text)

        for equipment_id in cleaned:
            row = self.connection.execute(
                "SELECT 1 FROM equipment WHERE id = ?",
                (equipment_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown equipment: {equipment_id}")

        self.connection.execute(
            """
            DELETE FROM activity_equipment
            WHERE activity_id = ? AND is_manual = 1
            """,
            (activity_id,),
        )

        for index, equipment_id in enumerate(cleaned):
            self.link_activity_equipment(
                activity_id,
                equipment_id,
                source="manual",
                role="primary" if index == 0 else "secondary",
                is_manual=True,
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

    WELLNESS_FIELDS = (
        "hrv",
        "resting_hr",
        "sleep_s",
        "weight_kg",
        "sleep_score",
        "sleep_quality",
        "spo2",
        "steps",
        "floors_climbed",
        "ctl",
        "atl",
    )

    def upsert_wellness(
        self,
        *,
        local_date: str,
        source_record_id: int,
        **fields: object,
    ) -> None:
        """Write one day's wellness, never clearing a value another source set."""
        unknown = set(fields) - set(self.WELLNESS_FIELDS)
        if unknown:
            raise ValueError(f"Unknown wellness fields: {sorted(unknown)}")

        values = {
            key: value
            for key, value in fields.items()
            if value is not None
        }

        if not values:
            self.connection.execute(
                """
                INSERT INTO wellness_days (local_date, source_record_id)
                VALUES (?, ?)
                ON CONFLICT(local_date) DO UPDATE SET
                    source_record_id = excluded.source_record_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (local_date, source_record_id),
            )
            return

        columns = ["local_date", "source_record_id", *values]
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{key} = COALESCE(excluded.{key}, wellness_days.{key})"
            for key in values
        )
        self.connection.execute(
            f"""
            INSERT INTO wellness_days ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(local_date) DO UPDATE SET
                source_record_id = excluded.source_record_id,
                {updates},
                updated_at = CURRENT_TIMESTAMP
            """,
            (local_date, source_record_id, *values.values()),
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
        training_load: float | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO events (
                id, source_record_id, local_date, name, type,
                description, duration_s, distance_m, training_load
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_record_id = excluded.source_record_id,
                local_date = excluded.local_date,
                name = excluded.name,
                type = excluded.type,
                description = excluded.description,
                duration_s = excluded.duration_s,
                distance_m = excluded.distance_m,
                training_load = excluded.training_load,
                excluded_at = NULL,
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
                training_load,
            ),
        )

    def exclude_event(self, event_id: str) -> bool:
        """Soft-exclude one event (used by the Intervals sync prune)."""
        cursor = self.connection.execute(
            """
            UPDATE events
            SET excluded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND excluded_at IS NULL
            """,
            (event_id,),
        )
        return cursor.rowcount > 0

    def restore_event(self, event_id: str) -> bool:
        """Undo an event exclusion."""
        cursor = self.connection.execute(
            """
            UPDATE events
            SET excluded_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND excluded_at IS NOT NULL
            """,
            (event_id,),
        )
        return cursor.rowcount > 0

    def exclude_device(self, device_id: str) -> bool:
        """Soft-exclude a device row; the repository lists only active ones.

        Used for a provider alias that no activity points at after the FIT
        claim. The row stays for audit; a reimport cannot resurrect it.
        """
        row = self.connection.execute(
            "SELECT excluded_at FROM devices WHERE id = ?",
            (device_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown device: {device_id}")
        if row["excluded_at"]:
            return False

        self.connection.execute(
            """
            UPDATE devices
            SET excluded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (device_id,),
        )
        return True

    def set_event_zone_times(
        self,
        event_id: str,
        kind: str,
        zone_times: list[EventZoneTime],
    ) -> int:
        """Replace an event's planned zone distribution.

        Intervals is authoritative for events, so the whole set is replaced.
        An empty list clears it. Returns the number of rows written.
        """
        row = self.connection.execute(
            "SELECT excluded_at FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"unknown event: {event_id}")
        if row["excluded_at"]:
            raise ValueError(f"event {event_id} is excluded")

        self.connection.execute(
            """
            UPDATE events
            SET zone_kind = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (kind or "", event_id),
        )
        self.connection.execute(
            "DELETE FROM event_zone_times WHERE event_id = ?",
            (event_id,),
        )

        if not zone_times:
            return 0

        self.connection.executemany(
            """
            INSERT INTO event_zone_times (
                event_id, zone_index, zone_label, seconds
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    event_id,
                    zone.zone_index,
                    zone.zone_label,
                    zone.seconds,
                )
                for zone in zone_times
            ],
        )
        return len(zone_times)

    def replace_activity_workout_methods(
        self,
        activity_id: str,
        methods: list[str],
        *,
        source: str,
        source_record_id: int | None = None,
        is_manual: bool = False,
    ) -> int:
        """Replace one source's workout-method set for an activity."""
        return self._replace_workout_set(
            "activity_workout_methods",
            "activity_id",
            "method",
            activity_id,
            methods,
            source=source,
            source_record_id=source_record_id,
            is_manual=is_manual,
            allowed=WORKOUT_METHODS,
            canonical=canonical_method,
        )

    def replace_activity_workout_targets(
        self,
        activity_id: str,
        targets: list[str],
        *,
        source: str,
        source_record_id: int | None = None,
        is_manual: bool = False,
    ) -> int:
        """Replace one source's workout-target set for an activity."""
        return self._replace_workout_set(
            "activity_workout_targets",
            "activity_id",
            "target",
            activity_id,
            targets,
            source=source,
            source_record_id=source_record_id,
            is_manual=is_manual,
            allowed=WORKOUT_TARGETS,
            canonical=canonical_target,
        )

    def replace_event_workout_methods(
        self,
        event_id: str,
        methods: list[str],
        *,
        source: str = "manual",
        source_record_id: int | None = None,
        is_manual: bool = False,
    ) -> int:
        """Replace one source's workout-method set for a planned event."""
        return self._replace_workout_set(
            "event_workout_methods",
            "event_id",
            "method",
            event_id,
            methods,
            source=source,
            source_record_id=source_record_id,
            is_manual=is_manual,
            allowed=WORKOUT_METHODS,
            canonical=canonical_method,
        )

    def replace_event_workout_targets(
        self,
        event_id: str,
        targets: list[str],
        *,
        source: str = "manual",
        source_record_id: int | None = None,
        is_manual: bool = False,
    ) -> int:
        """Replace one source's workout-target set for a planned event."""
        return self._replace_workout_set(
            "event_workout_targets",
            "event_id",
            "target",
            event_id,
            targets,
            source=source,
            source_record_id=source_record_id,
            is_manual=is_manual,
            allowed=WORKOUT_TARGETS,
            canonical=canonical_target,
        )

    def _replace_workout_set(
        self,
        table: str,
        id_column: str,
        value_column: str,
        entity_id: str,
        values: list[str],
        *,
        source: str,
        source_record_id: int | None,
        is_manual: bool,
        allowed: dict[str, str],
        canonical,
    ) -> int:
        self._require_workout_entity(id_column, entity_id)
        cleaned = self._clean_workout_values(
            values,
            allowed=allowed,
            canonical=canonical,
        )

        existing_manual = {
            item[value_column]
            for item in self.connection.execute(
                f"""
                SELECT {value_column} FROM {table}
                WHERE {id_column} = ? AND is_manual = 1
                """,
                (entity_id,),
            )
        }

        if is_manual:
            self.connection.execute(
                f"DELETE FROM {table} WHERE {id_column} = ? AND is_manual = 1",
                (entity_id,),
            )
        else:
            cleaned = [
                value for value in cleaned if value not in existing_manual
            ]
            self.connection.execute(
                f"""
                DELETE FROM {table}
                WHERE {id_column} = ? AND source = ? AND is_manual = 0
                """,
                (entity_id, source),
            )

        if cleaned:
            self.connection.executemany(
                f"""
                INSERT OR IGNORE INTO {table} (
                    {id_column}, {value_column}, source,
                    source_record_id, is_manual
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        entity_id,
                        value,
                        source,
                        source_record_id,
                        1 if is_manual else 0,
                    )
                    for value in cleaned
                ],
            )

        return len(cleaned)

    def _require_workout_entity(
        self,
        id_column: str,
        entity_id: str,
    ) -> None:
        entity_table = "activities" if id_column == "activity_id" else "events"
        entity_name = "activity" if entity_table == "activities" else "event"
        row = self.connection.execute(
            f"SELECT excluded_at FROM {entity_table} WHERE id = ?",
            (entity_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"unknown {entity_name}: {entity_id}")
        if row["excluded_at"]:
            raise ValueError(f"{entity_name} {entity_id} is excluded")

    def _clean_workout_values(
        self,
        values: list[str],
        *,
        allowed: dict[str, str],
        canonical,
    ) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            token = canonical(value)
            if token not in allowed:
                raise ValueError(f"unknown workout value: {value!r}")
            if token not in cleaned:
                cleaned.append(token)
        return cleaned

    def set_manual_activity_workout_methods(
        self,
        activity_id: str,
        methods: list[str],
    ) -> int:
        """Replace an activity's whole method set as manual values.

        Unlike :meth:`replace_activity_workout_methods`, rows from every source
        are cleared: a deliberate reclassification defines the set instead of
        contributing one source's view of it.
        """
        self._require_workout_entity("activity_id", activity_id)
        cleaned = self._clean_workout_values(
            methods,
            allowed=WORKOUT_METHODS,
            canonical=canonical_method,
        )

        self.connection.execute(
            "DELETE FROM activity_workout_methods WHERE activity_id = ?",
            (activity_id,),
        )
        if cleaned:
            self.connection.executemany(
                """
                INSERT INTO activity_workout_methods (
                    activity_id, method, source, source_record_id, is_manual
                ) VALUES (?, ?, 'manual', NULL, 1)
                """,
                [(activity_id, value) for value in cleaned],
            )
        return len(cleaned)

    def set_manual_activity_workout_targets(
        self,
        activity_id: str,
        targets: list[str],
    ) -> int:
        """Replace an activity's whole target set as manual values.

        Symmetric to :meth:`set_manual_activity_workout_methods`: rows from
        every source are cleared, so the manual set is the whole decision.
        """
        self._require_workout_entity("activity_id", activity_id)
        cleaned = self._clean_workout_values(
            targets,
            allowed=WORKOUT_TARGETS,
            canonical=canonical_target,
        )

        self.connection.execute(
            "DELETE FROM activity_workout_targets WHERE activity_id = ?",
            (activity_id,),
        )
        if cleaned:
            self.connection.executemany(
                """
                INSERT INTO activity_workout_targets (
                    activity_id, target, source, source_record_id, is_manual
                ) VALUES (?, ?, 'manual', NULL, 1)
                """,
                [(activity_id, value) for value in cleaned],
            )
        return len(cleaned)

    def upsert_zone_config(
        self,
        *,
        kind: str,
        boundaries: list[float],
        source: str,
    ) -> str:
        """Return the id of the zone config for these boundaries.

        The id is derived from the boundaries, so two activities of the same
        era share one row and a changed boundary set creates a new one.
        """
        if not boundaries:
            raise ValueError("zone boundaries must not be empty")

        digest = hashlib.sha1(
            json.dumps(boundaries, sort_keys=True).encode()
        ).hexdigest()[:12]
        config_id = f"{source}:{kind}:{digest}"

        self.connection.execute(
            """
            INSERT INTO zone_configs (id, kind, source, boundaries_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                config_id,
                kind,
                source,
                json.dumps(boundaries),
            ),
        )
        return config_id

    def set_activity_zone_configs(
        self,
        activity_id: str,
        *,
        pace_zone_config_id: str | None = None,
        hr_zone_config_id: str | None = None,
    ) -> None:
        """Point an activity at the zone configs of its era."""
        assignments = []
        params: list[object] = []

        if pace_zone_config_id is not None:
            assignments.append("pace_zone_config_id = ?")
            params.append(pace_zone_config_id)
        if hr_zone_config_id is not None:
            assignments.append("hr_zone_config_id = ?")
            params.append(hr_zone_config_id)

        if not assignments:
            return

        params.append(activity_id)
        self.connection.execute(
            f"UPDATE activities SET {', '.join(assignments)} WHERE id = ?",
            params,
        )

    def replace_athlete_thresholds(
        self,
        rows: list[dict[str, object]],
        *,
        source: str,
    ) -> int:
        """Replace one source's dated threshold snapshots."""
        self.connection.execute(
            "DELETE FROM athlete_thresholds WHERE source = ?",
            (source,),
        )

        entries = [
            (
                row["effective_from"],
                row.get("sport") or "",
                row.get("max_hr"),
                row.get("lthr"),
                row.get("threshold_pace_mps"),
                source,
                row.get("source_record_id"),
            )
            for row in rows
        ]
        if not entries:
            return 0

        self.connection.executemany(
            """
            INSERT INTO athlete_thresholds (
                effective_from, sport, max_hr, lthr, threshold_pace_mps,
                source, source_record_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            entries,
        )
        return len(entries)

    def set_manual_threshold(
        self,
        effective_from: date | str,
        sport: str,
        *,
        max_hr: float | None = None,
        lthr: float | None = None,
        threshold_pace_mps: float | None = None,
    ) -> None:
        """Write or refresh one manual threshold snapshot.

        The snapshot is dated and per sport; a re-add for the same date
        replaces the values rather than creating a duplicate. The automatic
        recompute only replaces its own ``intervals`` source, so a manual
        snapshot survives every run.
        """
        self.connection.execute(
            """
            INSERT INTO athlete_thresholds (
                effective_from, sport, max_hr, lthr, threshold_pace_mps,
                source
            ) VALUES (?, ?, ?, ?, ?, 'manual')
            ON CONFLICT(source, sport, effective_from) DO UPDATE SET
                max_hr = excluded.max_hr,
                lthr = excluded.lthr,
                threshold_pace_mps = excluded.threshold_pace_mps
            """,
            (
                str(effective_from)[:10],
                sport,
                max_hr,
                lthr,
                threshold_pace_mps,
            ),
        )

    def upsert_device(
        self,
        device_id: str,
        *,
        manufacturer: str = "",
        product: str = "",
        serial_number: str = "",
        name: str = "",
        acquired_on: date | str | None = None,
        retired_on: date | str | None = None,
        notes: str = "",
    ) -> bool:
        """Create or refresh one recording device. Returns True when created."""
        if not str(device_id).strip():
            raise ValueError("device id must not be empty")

        existing = self.connection.execute(
            "SELECT 1 FROM devices WHERE id = ?",
            (device_id,),
        ).fetchone()

        self.connection.execute(
            """
            INSERT INTO devices (
                id, manufacturer, product, serial_number, name,
                acquired_on, retired_on, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                manufacturer = excluded.manufacturer,
                product = excluded.product,
                serial_number = excluded.serial_number,
                name = excluded.name,
                acquired_on = COALESCE(excluded.acquired_on, devices.acquired_on),
                retired_on = COALESCE(excluded.retired_on, devices.retired_on),
                notes = CASE
                    WHEN excluded.notes = '' THEN devices.notes
                    ELSE excluded.notes
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                device_id,
                manufacturer,
                product,
                serial_number,
                name,
                acquired_on,
                retired_on,
                notes,
            ),
        )
        return existing is None

    def replace_training_periods(
        self,
        rows: list[dict[str, object]],
        *,
        source: str,
    ) -> int:
        """Replace one source's training periods; manual rows are kept."""
        self.connection.execute(
            "DELETE FROM training_periods WHERE source = ?",
            (source,),
        )

        entries = [
            (
                row["id"],
                row["kind"],
                row.get("label") or "",
                row["start_date"],
                row.get("end_date"),
                source,
                row.get("source_record_id"),
                row.get("notes") or "",
            )
            for row in rows
        ]
        if not entries:
            return 0

        self.connection.executemany(
            """
            INSERT INTO training_periods (
                id, kind, label, start_date, end_date,
                source, source_record_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            entries,
        )
        return len(entries)

    def upsert_training_period(
        self,
        period_id: str,
        *,
        kind: str,
        start_date: str,
        label: str = "",
        end_date: str | None = None,
        notes: str = "",
    ) -> None:
        """Write one manual period, replacing the same id."""
        self.connection.execute(
            """
            INSERT INTO training_periods (
                id, kind, label, start_date, end_date, source, notes
            ) VALUES (?, ?, ?, ?, ?, 'manual', ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
                label = excluded.label,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                notes = excluded.notes,
                excluded_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (period_id, kind, label, start_date, end_date, notes),
        )

    RACE_RESULT_FIELDS = (
        "event_id",
        "name",
        "official_distance_m",
        "official_time_s",
        "officially_measured",
        "place_total",
        "place_gender",
        "place_ageclass",
        "participants_total",
        "participants_gender",
        "participants_ageclass",
        "priority_level",
        "status",
        "notes",
    )

    def upsert_race_result(
        self,
        activity_id: str,
        *,
        source: str,
        source_record_id: int | None = None,
        **fields: object,
    ) -> bool:
        """Insert or replace one activity's official race result.

        A manual row is never overwritten by a source; a source row is
        replaced by the same source. Returns ``True`` when a row was written.
        """
        unknown = set(fields) - set(self.RACE_RESULT_FIELDS)
        if unknown:
            raise ValueError(f"Unknown race-result fields: {sorted(unknown)}")

        existing = self.connection.execute(
            "SELECT source, excluded_at FROM race_results WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()

        if existing is not None:
            if existing["source"] == "manual" and source != "manual":
                return False
            if existing["excluded_at"] and source != "manual":
                return False

        values = {
            key: value
            for key, value in fields.items()
            if value is not None
        }

        if not values:
            return False

        if existing is None:
            columns = [
                "activity_id", "source", "source_record_id", *values
            ]
            placeholders = ", ".join("?" for _ in columns)
            self.connection.execute(
                f"INSERT INTO race_results ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                (activity_id, source, source_record_id, *values.values()),
            )
            return True

        assignments = ", ".join(f"{key} = ?" for key in values)
        self.connection.execute(
            f"UPDATE race_results SET {assignments}, "
            "source = ?, source_record_id = ?, excluded_at = NULL, "
            "updated_at = CURRENT_TIMESTAMP WHERE activity_id = ?",
            (
                *values.values(),
                source,
                source_record_id,
                activity_id,
            ),
        )
        return True

    WEATHER_FIELDS = (
        "temp_c",
        "feels_like_c",
        "humidity_pct",
        "wind_speed_ms",
        "wind_degree",
        "wind_gust_ms",
        "wind_chill_c",
        "heat_index_c",
        "pressure_hpa",
        "uv_index",
        "clouds_pct",
        "condition",
        "is_night",
    )

    def upsert_activity_weather(
        self,
        activity_id: str,
        *,
        source: str,
        source_record_id: int | None = None,
        **fields: object,
    ) -> bool:
        """Write one activity's weather, keeping the first source's row.

        A reimport from the same source refreshes its values. A different
        source only fills the fields the owner left empty, so two providers
        do not overwrite each other field by field.
        """
        unknown = set(fields) - set(self.WEATHER_FIELDS)
        if unknown:
            raise ValueError(f"Unknown weather fields: {sorted(unknown)}")

        row = self.connection.execute(
            "SELECT source FROM activity_weather WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()

        values = {
            key: value
            for key, value in fields.items()
            if value is not None and value != ""
        }

        if not values:
            return False

        if row is None:
            columns = ["activity_id", "source", "source_record_id", *values]
            placeholders = ", ".join("?" for _ in columns)
            self.connection.execute(
                f"INSERT INTO activity_weather ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                (activity_id, source, source_record_id, *values.values()),
            )
            return True

        if row["source"] != source:
            existing = self.connection.execute(
                "SELECT * FROM activity_weather WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()
            values = {
                key: value
                for key, value in values.items()
                if existing[key] is None or existing[key] == ""
            }

            if not values:
                return False

        assignments = ", ".join(f"{key} = ?" for key in values)
        self.connection.execute(
            f"UPDATE activity_weather SET {assignments}, "
            "updated_at = CURRENT_TIMESTAMP WHERE activity_id = ?",
            (*values.values(), activity_id),
        )
        return True

    def set_activity_ambient_temperature(
        self,
        activity_id: str,
        *,
        temp_c: float | None,
        source: str,
        source_record_id: int | None = None,
    ) -> bool:
        """Set or clear the ambient temperature, leaving other fields alone.

        ``temp_c`` is air temperature, never a device reading. A cleared row
        whose other weather fields are all empty is removed. Returns ``True``
        when anything changed.
        """
        row = self.connection.execute(
            "SELECT * FROM activity_weather WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()

        if row is None:
            if temp_c is None:
                return False
            self.connection.execute(
                """
                INSERT INTO activity_weather (
                    activity_id, source, source_record_id, temp_c
                ) VALUES (?, ?, ?, ?)
                """,
                (activity_id, source, source_record_id, temp_c),
            )
            return True

        if temp_c is None:
            if row["temp_c"] is None:
                return False
            self.connection.execute(
                "UPDATE activity_weather SET temp_c = NULL, "
                "updated_at = CURRENT_TIMESTAMP WHERE activity_id = ?",
                (activity_id,),
            )
            others = [
                field
                for field in self.WEATHER_FIELDS
                if field != "temp_c" and row[field] not in (None, "")
            ]
            if not others:
                self.connection.execute(
                    "DELETE FROM activity_weather WHERE activity_id = ?",
                    (activity_id,),
                )
            return True

        if (
            row["temp_c"] == temp_c
            and row["source"] == source
            and row["source_record_id"] == source_record_id
        ):
            return False

        self.connection.execute(
            """
            UPDATE activity_weather
            SET temp_c = ?, source = ?, source_record_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE activity_id = ?
            """,
            (temp_c, source, source_record_id, activity_id),
        )
        return True

    def upsert_activity_metrics(
        self,
        activity_id: str,
        *,
        source: str,
        source_record_id: int | None = None,
        **fields: object,
    ) -> bool:
        """Write one activity's session-average metrics.

        The row is shared: a field keeps its first owner, a later source only
        fills an empty value, and a source with a higher per-field authority
        (FIT for device-measured dynamics, Intervals for altitude) replaces a
        weaker source's value. A reimport from the same source refreshes its
        values. Returns ``True`` when any value was written.
        """
        unknown = set(fields) - set(METRIC_FIELDS)
        if unknown:
            raise ValueError(f"Unknown metric fields: {sorted(unknown)}")

        self._require_editable_activity(activity_id)

        values = {
            key: value
            for key, value in fields.items()
            if value is not None
        }
        if not values:
            return False

        row = self.connection.execute(
            "SELECT * FROM activity_metrics WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()

        if row is None:
            columns = ["activity_id", "source", "source_record_id", *values]
            owners = {field: source for field in values}
            columns.insert(3, "field_sources_json")
            placeholders = ", ".join("?" for _ in columns)
            self.connection.execute(
                f"INSERT INTO activity_metrics ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                (
                    activity_id,
                    source,
                    source_record_id,
                    json.dumps(owners, sort_keys=True),
                    *values.values(),
                ),
            )
            return True

        try:
            owners = json.loads(row["field_sources_json"] or "{}")
        except (TypeError, ValueError):
            owners = {}
        if not isinstance(owners, dict):
            owners = {}

        writes = {}
        for key, value in values.items():
            existing = row[key]
            field_source = owners.get(key, row["source"])
            if existing is None or field_source == source:
                writes[key] = value
                owners[key] = source
                continue

            incoming_rank = metric_authority_rank(key, source)
            current_rank = metric_authority_rank(key, field_source)
            if incoming_rank is not None and (
                current_rank is None or incoming_rank < current_rank
            ):
                writes[key] = value
                owners[key] = source

        if not writes:
            return False

        assignments = ", ".join(f"{key} = ?" for key in writes)
        self.connection.execute(
            f"UPDATE activity_metrics SET {assignments}, "
            "field_sources_json = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE activity_id = ?",
            (
                *writes.values(),
                json.dumps(owners, sort_keys=True),
                activity_id,
            ),
        )
        return True

    def upsert_activity_social(
        self,
        activity_id: str,
        *,
        source: str,
        source_record_id: int | None = None,
        title: str = "",
        description: str = "",
        external_id: str | None = None,
        url: str | None = None,
        is_manual: bool = False,
    ) -> bool:
        """Write one source's social text for an activity.

        Each source owns its row: a reimport refreshes that row, and a
        manual row is never touched by an importer. An empty incoming value
        is written because a source may clear its own title; it never clears
        another source's row. Returns ``True`` when the row was created.
        """
        if not str(source).strip():
            raise ValueError("source must not be empty")

        activity = self.connection.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        if activity is None:
            raise ValueError(f"unknown activity: {activity_id}")
        if activity["excluded_at"]:
            raise ValueError(f"activity {activity_id} is excluded")

        existing = self.connection.execute(
            """
            SELECT is_manual FROM activity_social
            WHERE activity_id = ? AND source = ?
            """,
            (activity_id, source),
        ).fetchone()
        if existing is not None and existing["is_manual"] and not is_manual:
            return False

        self.connection.execute(
            """
            INSERT INTO activity_social (
                activity_id, source, title, description, external_id, url,
                source_record_id, is_manual
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id, source) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                external_id = excluded.external_id,
                url = excluded.url,
                source_record_id = excluded.source_record_id,
                is_manual = excluded.is_manual,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                activity_id,
                source,
                title or "",
                description or "",
                external_id,
                url,
                source_record_id,
                1 if is_manual else 0,
            ),
        )
        return existing is None

    def record_fit_scan_file(
        self,
        *,
        path: str,
        size_bytes: int,
        mtime_ns: int,
        kind: str,
    ) -> None:
        """Record what the FIT scan decided about one file.

        The manifest lets a routine scan skip unchanged files whether or not
        they became an activity. ``kind`` is the scan's verdict (``activity``,
        ``other``, ``error``).
        """
        if not path:
            raise ValueError("path must not be empty")

        self.connection.execute(
            """
            INSERT INTO fit_scan_files (path, size_bytes, mtime_ns, kind)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                size_bytes = excluded.size_bytes,
                mtime_ns = excluded.mtime_ns,
                kind = excluded.kind,
                seen_at = CURRENT_TIMESTAMP
            """,
            (path, int(size_bytes), int(mtime_ns), kind),
        )

    def fit_scan_manifest(self) -> dict[str, tuple[int, int, str]]:
        """Return the scan manifest as ``path -> (size, mtime_ns, kind)``."""
        rows = self.connection.execute(
            "SELECT path, size_bytes, mtime_ns, kind FROM fit_scan_files"
        ).fetchall()

        return {
            row["path"]: (row["size_bytes"], row["mtime_ns"], row["kind"])
            for row in rows
        }

    def forget_fit_scan_files(self, paths: Iterable[str]) -> int:
        """Drop manifest rows for files that no longer exist."""
        entries = [(path,) for path in paths]

        if not entries:
            return 0

        cursor = self.connection.executemany(
            "DELETE FROM fit_scan_files WHERE path = ?",
            entries,
        )
        return cursor.rowcount

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


def _duration_times_agree(
    current_duration: object,
    current_elapsed: object,
    incoming_duration: object,
    incoming_elapsed: object,
    tolerance: float = 2.0,
) -> bool:
    """True when a duration difference fits inside either source's pause.

    Garmin's ``total_timer_time`` and Intervals' ``icu_recording_time`` both
    exclude pauses, but services can account around a pause slightly
    differently. A difference no larger than the pause gap of either source
    is recording semantics, not a competing measurement.
    """
    try:
        current_duration = float(current_duration)
        incoming_duration = float(incoming_duration)
        current_elapsed = float(current_elapsed)
        incoming_elapsed = float(incoming_elapsed)
    except (TypeError, ValueError):
        return False

    if current_duration <= 0 or incoming_duration <= 0:
        return False

    current_pause = max(0.0, current_elapsed - current_duration)
    incoming_pause = max(0.0, incoming_elapsed - incoming_duration)
    return abs(current_duration - incoming_duration) <= max(
        tolerance,
        current_pause,
        incoming_pause,
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


def _is_unfilled(value: object) -> bool:
    """True when a field holds no actual value yet.

    A blank string is a gap, not an owner decision: Intervals writes empty
    names/descriptions for activities it has no text for, and a later source
    may fill them.
    """
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _iso_date(value: date | str | None) -> str | None:
    """Normalize an optional date to the ISO text stored in SQLite."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


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
