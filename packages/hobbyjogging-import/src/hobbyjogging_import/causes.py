"""Classify cross-source field conflicts for the review queue.

The classifier only uses data we already store: the canonical values on the
review item and the summary payloads in ``source_records``. It deliberately
does not fetch activity streams, so genuinely unusual cases stay ``unknown``
and require a human decision.

A cause is advisory. Only causes marked ``resolvable`` may be closed in bulk;
everything else needs a per-activity choice in triage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .values import format_field
from .numeric import number as _number

CONFLICT_CATEGORY = "field_conflict"
UNCLASSIFIED = "unclassified"

# A conflict is treated as a trimmed upload when *both* the recording time
# and the distance differ by at least this ratio between the two sources.
TRIM_RATIO = 1.15
SMALL_DIFFERENCE_RATIO = 0.05
SMALL_HR_DIFFERENCE_BPM = 5.0
# Beyond this a heart-rate maximum is not a plausible measurement; it is a
# strap or sensor fault and the average built on top of it is suspect.
HR_IMPLAUSIBLE_MAX = 205.0

ACTIVITY_TRIMMED = "activity_trimmed"
ELAPSED_DEFINITION = "elapsed_definition"
MOVING_ESTIMATE = "moving_estimate"
SMALL_DIFFERENCE = "small_difference"
START_OFFSET = "start_offset"
HR_SENSOR_ANOMALY = "hr_sensor_anomaly"
SPORT_VOCABULARY = "sport_vocabulary"
DISTANCE_ESTIMATE = "distance_estimate"
DURATION_ESTIMATE = "duration_estimate"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Cause:
    """One explainable class of cross-source disagreement."""

    name: str
    label: str
    explanation: str
    severity: str = "warn"
    resolvable: bool = False


CAUSES: dict[str, Cause] = {
    ACTIVITY_TRIMMED: Cause(
        name=ACTIVITY_TRIMMED,
        label="trimmed activity",
        explanation=(
            "the sources cover different spans of the same activity; one "
            "upload was trimmed or reprocessed"
        ),
    ),
    HR_SENSOR_ANOMALY: Cause(
        name=HR_SENSOR_ANOMALY,
        label="HR sensor anomaly",
        explanation=(
            "one source's heart-rate summary is implausible (spikes or "
            "dropouts); the average is not trustworthy"
        ),
    ),
    SPORT_VOCABULARY: Cause(
        name=SPORT_VOCABULARY,
        label="sport vocabulary",
        explanation="the sources map the activity to different sports",
    ),
    DISTANCE_ESTIMATE: Cause(
        name=DISTANCE_ESTIMATE,
        label="distance estimate",
        explanation=(
            "distance differs beyond a small difference without a duration "
            "mismatch (GPS smoothing or recalculation)"
        ),
    ),
    DURATION_ESTIMATE: Cause(
        name=DURATION_ESTIMATE,
        label="duration estimate",
        explanation="recording/timer time differs beyond a small difference",
    ),
    UNKNOWN: Cause(
        name=UNKNOWN,
        label="unexplained",
        explanation="no summary-level explanation; inspect the source streams",
    ),
    # Advisory disagreements a human has already accepted as harmless.
    ELAPSED_DEFINITION: Cause(
        name=ELAPSED_DEFINITION,
        label="elapsed-time definition",
        explanation=(
            "Garmin elapsed is start-to-save time (it includes trailing "
            "stopped time); Intervals elapsed is the last-record offset"
        ),
        severity="info",
        resolvable=True,
    ),
    MOVING_ESTIMATE: Cause(
        name=MOVING_ESTIMATE,
        label="moving-time estimate",
        explanation=(
            "moving time uses each source's own auto-pause/movement estimate"
        ),
        severity="info",
        resolvable=True,
    ),
    SMALL_DIFFERENCE: Cause(
        name=SMALL_DIFFERENCE,
        label="small difference",
        explanation=(
            "the values differ by at most 5% (or 5 bpm); likely rounding or "
            "stream smoothing"
        ),
        severity="info",
        resolvable=True,
    ),
    START_OFFSET: Cause(
        name=START_OFFSET,
        label="start offset",
        explanation="start timestamps differ by less than one minute",
        severity="info",
        resolvable=True,
    ),
}

CAUSE_NAMES = tuple(CAUSES) + (UNCLASSIFIED,)


def cause_severity(name: str) -> str:
    """Return the review severity for one cause (warn for unknown values)."""
    cause = CAUSES.get(name)
    return cause.severity if cause is not None else "warn"


@dataclass(frozen=True)
class SourceSummary:
    """The activity-level numbers a source reported, when we stored them."""

    source: str
    duration_s: float | None = None
    elapsed_s: float | None = None
    moving_s: float | None = None
    distance_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None


@dataclass
class ClassifySummary:
    checked: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass
class ResolveCauseSummary:
    cause: str
    resolved: int = 0


@dataclass
class CauseCount:
    cause: str
    count: int = 0
    fields: dict[str, int] = field(default_factory=dict)
    severity: str = "warn"
    resolvable: bool = False
    label: str = ""


def item_context(item) -> dict:
    """Decode a review item's stored context without raising on bad JSON."""
    try:
        context = json.loads(item["context_json"] or "{}")
    except (TypeError, ValueError):
        return {}
    return context if isinstance(context, dict) else {}


def item_cause(item) -> str | None:
    """Return the stored cause of a field conflict, or None."""
    if item["category"] != CONFLICT_CATEGORY:
        return None
    return item_context(item).get("cause") or None


def classify_conflict(
    connection,
    *,
    activity_id: str,
    field_name: str,
    current_source: str,
    current_value: object,
    incoming_source: str,
    incoming_value: object,
    incoming_source_record_id: int | None = None,
) -> tuple[str, str]:
    """Classify one conflict and return ``(cause, human-readable note)``."""
    current = source_summary(
        connection,
        source=current_source,
        source_record_id=_record_for_field(
            connection,
            activity_id,
            field_name,
            current_source,
        ),
    )
    incoming = source_summary(
        connection,
        source=incoming_source,
        source_record_id=_record_for_source(
            connection,
            activity_id,
            incoming_source,
            incoming_source_record_id,
        ),
    )
    return classify_values(
        field_name=field_name,
        current_source=current_source,
        current_value=current_value,
        incoming_source=incoming_source,
        incoming_value=incoming_value,
        current=current,
        incoming=incoming,
    )


def classify_values(
    *,
    field_name: str,
    current_source: str,
    current_value: object,
    incoming_source: str,
    incoming_value: object,
    current: SourceSummary,
    incoming: SourceSummary,
) -> tuple[str, str]:
    """Classify a conflict from its values and the two source summaries."""
    if field_name == "sport":
        return (
            SPORT_VOCABULARY,
            "the sources use different sport vocabulary",
        )

    if field_name == "started_at_utc":
        return START_OFFSET, "start timestamps differ by less than a minute"

    if _looks_trimmed(current, incoming):
        return ACTIVITY_TRIMMED, (
            "the sources cover different spans: "
            f"{current_source} {_span(current)}, "
            f"{incoming_source} {_span(incoming)}"
        )

    if field_name == "elapsed_s":
        return ELAPSED_DEFINITION, (
            "elapsed is start-to-save time on one source and the "
            "last-record offset on the other"
        )

    if field_name == "moving_s":
        return MOVING_ESTIMATE, (
            "moving time uses each source's own auto-pause estimate"
        )

    if field_name == "avg_hr":
        suspect = _implausible_hr(current, incoming)
        if suspect is not None:
            return HR_SENSOR_ANOMALY, (
                f"{suspect.source} reports a maximum HR of "
                f"{suspect.max_hr:.0f} bpm; treat its heart-rate stream "
                "as suspect"
            )
        if _small_difference(field_name, current_value, incoming_value):
            return SMALL_DIFFERENCE, _small_note(field_name)
        return UNKNOWN, "no summary-level explanation; compare the HR streams"

    if _small_difference(field_name, current_value, incoming_value):
        return SMALL_DIFFERENCE, _small_note(field_name)

    if field_name == "distance_m":
        return DISTANCE_ESTIMATE, (
            "distance differs beyond 5% without a duration mismatch "
            "(GPS smoothing or recalculation)"
        )

    if field_name == "duration_s":
        return DURATION_ESTIMATE, (
            "recording/timer time differs beyond 5%"
        )

    return UNKNOWN, "no summary-level explanation; inspect the source records"


def source_summary(
    connection,
    *,
    source: str,
    source_record_id: int | None,
) -> SourceSummary:
    """Read one source record's activity summary, if we have it."""
    if source_record_id is None:
        return SourceSummary(source=source)

    row = connection.execute(
        "SELECT source, payload_json FROM source_records WHERE id = ?",
        (source_record_id,),
    ).fetchone()
    if row is None:
        return SourceSummary(source=source)

    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, ValueError):
        return SourceSummary(source=row["source"] or source)
    if not isinstance(payload, dict):
        return SourceSummary(source=row["source"] or source)

    return _parse_summary(row["source"] or source, payload)


def _parse_summary(source: str, payload: dict) -> SourceSummary:
    if source == "fit":
        session = payload.get("session") or {}
        if not isinstance(session, dict):
            session = {}
        return SourceSummary(
            source=source,
            duration_s=_number(session.get("duration_s")),
            elapsed_s=_number(session.get("elapsed_s")),
            moving_s=_number(session.get("moving_s")),
            distance_m=_number(session.get("distance_m")),
            avg_hr=_number(session.get("avg_hr")),
            max_hr=_number(session.get("max_hr")),
        )

    if source == "garmin":
        return SourceSummary(
            source=source,
            duration_s=_number(payload.get("duration")),
            elapsed_s=_number(payload.get("elapsedDuration")),
            moving_s=_number(payload.get("movingDuration")),
            distance_m=_number(payload.get("distance")),
            avg_hr=_number(payload.get("averageHR")),
            max_hr=_number(payload.get("maxHR")),
        )

    if source == "intervals":
        recording = _number(payload.get("icu_recording_time"))
        if recording is None:
            recording = _number(payload.get("moving_time"))
        return SourceSummary(
            source=source,
            duration_s=recording,
            elapsed_s=_number(payload.get("elapsed_time")),
            moving_s=_number(payload.get("moving_time")),
            distance_m=_number(payload.get("distance")),
            avg_hr=_number(payload.get("average_heartrate")),
            max_hr=_number(payload.get("max_heartrate")),
        )

    return SourceSummary(source=source)


def annotate_conflicts(
    writer,
    *,
    activity_id: str | None = None,
    dry_run: bool = False,
) -> ClassifySummary:
    """Backfill causes onto open field-conflict items. Idempotent."""
    summary = ClassifySummary()

    for item in writer.review_items(
        category=CONFLICT_CATEGORY,
        status="open",
    ):
        if activity_id is not None and item["activity_id"] != activity_id:
            continue

        summary.checked += 1
        context = item_context(item)
        field_name = context.get("field")
        current = context.get("current") or {}
        incoming = context.get("incoming") or {}

        if not field_name or not item["activity_id"]:
            summary.unchanged += 1
            continue

        cause, note = classify_conflict(
            writer.connection,
            activity_id=item["activity_id"],
            field_name=field_name,
            current_source=str(current.get("source") or ""),
            current_value=current.get("value"),
            incoming_source=str(incoming.get("source") or ""),
            incoming_value=incoming.get("value"),
            incoming_source_record_id=item["source_record_id"],
        )
        severity = cause_severity(cause)

        if (
            context.get("cause") == cause
            and context.get("cause_note") == note
            and item["severity"] == severity
        ):
            summary.unchanged += 1
            continue

        summary.updated += 1
        if dry_run:
            continue

        context["cause"] = cause
        context["cause_note"] = note
        writer.connection.execute(
            """
            UPDATE review_items
            SET context_json = ?, severity = ?
            WHERE id = ?
            """,
            (
                json.dumps(context, sort_keys=True),
                severity,
                item["id"],
            ),
        )

    if not dry_run:
        writer.connection.commit()

    return summary


def resolve_by_cause(
    writer,
    cause: str,
    *,
    dry_run: bool = False,
    note: str = "",
) -> ResolveCauseSummary:
    """Resolve open conflicts with one bulk-resolvable cause."""
    spec = CAUSES.get(cause)
    if spec is None:
        raise ValueError(f"unknown conflict cause: {cause!r}")
    if not spec.resolvable:
        raise ValueError(
            f"cause {cause!r} needs a per-activity decision; "
            f"use: review triage --cause {cause}"
        )

    summary = ResolveCauseSummary(cause=cause)
    for item in writer.review_items(
        category=CONFLICT_CATEGORY,
        status="open",
    ):
        if item_cause(item) != cause:
            continue

        summary.resolved += 1
        if dry_run:
            continue

        writer.set_review_status(
            item["id"],
            "resolved",
            note=note or f"bulk: {cause}",
        )

    if not dry_run:
        writer.connection.commit()

    return summary


def cause_counts(writer, *, status: str = "open") -> list[CauseCount]:
    """Count field conflicts per cause, most frequent first."""
    counts: dict[str, CauseCount] = {}

    for item in writer.review_items(
        category=CONFLICT_CATEGORY,
        status=status,
    ):
        context = item_context(item)
        name = context.get("cause") or UNCLASSIFIED
        entry = counts.get(name)
        if entry is None:
            spec = CAUSES.get(name)
            entry = CauseCount(
                cause=name,
                severity=spec.severity if spec is not None else "warn",
                resolvable=spec.resolvable if spec is not None else False,
                label=spec.label if spec is not None else "not classified yet",
            )
            counts[name] = entry

        entry.count += 1
        field_name = context.get("field") or "?"
        entry.fields[field_name] = entry.fields.get(field_name, 0) + 1

    order = {name: index for index, name in enumerate(CAUSE_NAMES)}
    return sorted(
        counts.values(),
        key=lambda entry: (-entry.count, order.get(entry.cause, 999)),
    )


def _record_for_field(
    connection,
    activity_id: str,
    field_name: str,
    source: str,
) -> int | None:
    """The source record that owns a field, if it belongs to ``source``."""
    row = connection.execute(
        """
        SELECT source, source_record_id
        FROM activity_field_sources
        WHERE activity_id = ? AND field_name = ?
        """,
        (activity_id, field_name),
    ).fetchone()

    if (
        row is not None
        and row["source"] == source
        and row["source_record_id"] is not None
    ):
        return row["source_record_id"]

    return latest_source_record(connection, activity_id, source)


def _record_for_source(
    connection,
    activity_id: str,
    source: str,
    source_record_id: int | None,
) -> int | None:
    """Trust an explicit record id only when it belongs to ``source``."""
    if source_record_id is not None:
        row = connection.execute(
            "SELECT source FROM source_records WHERE id = ?",
            (source_record_id,),
        ).fetchone()
        if row is not None and row["source"] == source:
            return source_record_id

    return latest_source_record(connection, activity_id, source)


def latest_source_record(
    connection,
    activity_id: str,
    source: str,
) -> int | None:
    """Best-effort lookup of an activity's linked record for one source."""
    row = connection.execute(
        """
        SELECT als.source_record_id
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE als.activity_id = ? AND sr.source = ?
        ORDER BY als.is_primary DESC, als.source_record_id DESC
        LIMIT 1
        """,
        (activity_id, source),
    ).fetchone()
    return row["source_record_id"] if row is not None else None


def _looks_trimmed(
    current: SourceSummary,
    incoming: SourceSummary,
) -> bool:
    duration = _ratio(current.duration_s, incoming.duration_s)
    distance = _ratio(current.distance_m, incoming.distance_m)
    return (
        duration is not None
        and duration >= TRIM_RATIO
        and distance is not None
        and distance >= TRIM_RATIO
    )


def _ratio(first: float | None, second: float | None) -> float | None:
    if first is None or second is None or first <= 0 or second <= 0:
        return None
    return max(first, second) / min(first, second)


def _implausible_hr(
    *summaries: SourceSummary,
) -> SourceSummary | None:
    for summary in summaries:
        if (
            summary.max_hr is not None
            and summary.max_hr > HR_IMPLAUSIBLE_MAX
        ):
            return summary
    return None


def _small_difference(
    field_name: str,
    current_value: object,
    incoming_value: object,
) -> bool:
    current = _number(current_value)
    incoming = _number(incoming_value)
    if current is None or incoming is None:
        return False

    difference = abs(current - incoming)
    if field_name == "avg_hr":
        return difference <= SMALL_HR_DIFFERENCE_BPM

    scale = max(abs(current), abs(incoming), 1.0)
    return difference / scale <= SMALL_DIFFERENCE_RATIO


def _small_note(field_name: str) -> str:
    if field_name == "avg_hr":
        return "heart rate differs by at most 5 bpm"
    return "values differ by at most 5%; likely rounding or stream smoothing"


def _span(summary: SourceSummary) -> str:
    parts = []
    if summary.duration_s is not None:
        parts.append(
            f"timer {format_field('duration_s', summary.duration_s)}"
        )
    if summary.distance_m is not None:
        parts.append(format_field("distance_m", summary.distance_m))
    return " / ".join(parts) if parts else "unknown span"
