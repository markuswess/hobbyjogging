"""Browser links for canonical activities and review items."""

from __future__ import annotations

import json
from datetime import datetime, timezone

INTERVALS_URL = "https://intervals.icu/activities/{}"
GARMIN_URL = "https://connect.garmin.com/app/activity/{}"

# Garmin's activity list and the canonical start can differ by a second or
# two after matching. Keep the fallback tight enough that two nearby starts
# cannot both match.
GARMIN_MATCH_TOLERANCE_S = 15.0


def intervals_url(connection, item) -> str | None:
    """Return the Intervals activity URL for a review item, if linked."""
    if item["record_source"] == "intervals" and item["external_id"]:
        return INTERVALS_URL.format(item["external_id"])

    activity_id = item["activity_id"]
    if not activity_id:
        return None

    external_id = intervals_activity_id(connection, activity_id)
    return INTERVALS_URL.format(external_id) if external_id else None


def intervals_activity_id(
    connection,
    activity_id: str,
) -> str | None:
    """Return the linked Intervals external activity id, if any."""
    row = connection.execute(
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


def garmin_url(
    connection,
    item,
    *,
    index: list[tuple[datetime, str]] | None = None,
) -> str | None:
    """Return the Garmin Connect activity URL for a review item, if known."""
    activity_id = item["activity_id"]
    if not activity_id:
        return None

    external_id = garmin_activity_id(
        connection,
        activity_id,
        index=index,
    )
    return GARMIN_URL.format(external_id) if external_id else None


def garmin_activity_id(
    connection,
    activity_id: str,
    *,
    index: list[tuple[datetime, str]] | None = None,
) -> str | None:
    """Resolve a canonical activity to a Garmin activity id.

    The fetch manifest stores the Garmin id next to the downloaded FIT. A
    path join is exact when the linked FIT source record is the fetched file.
    When the archive copy was imported instead, fall back to the manifest's
    ``beginTimestamp`` and the canonical start time.
    """
    row = connection.execute(
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

    started = connection.execute(
        "SELECT started_at_utc FROM activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    if started is None or not started["started_at_utc"]:
        return None

    try:
        target = _utc(started["started_at_utc"])
    except ValueError:
        return None

    manifests = index if index is not None else garmin_manifest_index(connection)
    best: tuple[float, str] | None = None
    for moment, external_id in manifests:
        difference = abs((moment - target).total_seconds())
        if (
            difference <= GARMIN_MATCH_TOLERANCE_S
            and (best is None or difference < best[0])
        ):
            best = (difference, external_id)
    return best[1] if best else None


def garmin_manifest_index(
    connection,
) -> list[tuple[datetime, str]]:
    """Return ``(start, garmin_activity_id)`` for every fetch manifest."""
    index: list[tuple[datetime, str]] = []
    rows = connection.execute(
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
    return index


def _utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
