"""Canonical data-quality review rules and shared review recording.

The rule set operates on canonical values only (sport, duration, elapsed,
distance) so every source importer can run it, and future backfill scans can
re-apply it to existing activities without knowing where the data came from.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.sports import (
    NO_DISTANCE_SPORTS,
    PACE_SPORTS,
    RIDE_SPORTS,
)

from .values import format_field

# Implied whole-activity pace sanity windows, in seconds per kilometer.
# Running and cycling have very different plausible ranges. Cycling rides a
# wide style range (MTB climbs, pushing the bike), so only absurd mismatches
# between distance and duration get flagged.
MIN_RUN_PACE_S_PER_KM = 120.0  # 2:00 /km
MAX_RUN_PACE_S_PER_KM = 600.0  # 10:00 /km
MIN_RIDE_PACE_S_PER_KM = 36.0  # ~100 km/h
MAX_RIDE_PACE_S_PER_KM = 900.0  # 15:00 /km walking pace

AMBIGUOUS_MATCH = "ambiguous_match"
QUALITY = "quality"
MANUAL_FLAG = "manual_flag"
CONFLICT = "field_conflict"


@dataclass(frozen=True)
class Finding:
    """One detected review-worthy property of an activity."""

    rule: str
    detail: str
    context: dict
    severity: str = "warn"


def quality_findings(
    *,
    sport: str,
    duration_s: float,
    elapsed_s: float,
    distance_m: float,
) -> list[Finding]:
    """Apply the canonical quality rule set to one activity's values."""
    findings: list[Finding] = []

    if duration_s == 0:
        findings.append(
            Finding(
                rule="zero_duration",
                detail=(
                    f"duration is 0 s while elapsed is {elapsed_s:.0f} s"
                    if elapsed_s > 0
                    else "no timing data: duration is 0 s"
                ),
                context={"duration_s": duration_s, "elapsed_s": elapsed_s},
            )
        )

    pace_sport = (
        sport in PACE_SPORTS and sport not in NO_DISTANCE_SPORTS
    )
    distance_required = pace_sport
    pace_s_per_km = None

    if pace_sport and duration_s > 0 and distance_m > 0:
        pace_s_per_km = duration_s / (distance_m / 1000)

    if distance_m == 0 and distance_required:
        findings.append(
            Finding(
                rule="zero_distance",
                detail="distance is 0 m where distance is expected",
                context={"distance_m": distance_m, "sport": sport},
            )
        )

    if pace_s_per_km is not None:
        if sport in RIDE_SPORTS:
            window = (MIN_RIDE_PACE_S_PER_KM, MAX_RIDE_PACE_S_PER_KM)
        else:
            window = (MIN_RUN_PACE_S_PER_KM, MAX_RUN_PACE_S_PER_KM)

        if not (window[0] <= pace_s_per_km <= window[1]):
            findings.append(
                Finding(
                    rule="implied_pace",
                    detail=(
                        "implied pace "
                        f"{_format_pace(pace_s_per_km)} /km is outside "
                        "the plausible "
                        f"{_format_pace(window[0])}-{_format_pace(window[1])}"
                        " /km window"
                    ),
                    context={
                        "pace_s_per_km": round(pace_s_per_km, 1),
                        "duration_s": duration_s,
                        "distance_m": distance_m,
                        "sport": sport,
                    },
                )
            )

    return findings


def record_quality_findings(
    writer: TrainingWriter,
    *,
    activity_id: str | None,
    source_record_id: int | None,
    import_run_id: int | None,
    sport: str,
    duration_s: float,
    elapsed_s: float,
    distance_m: float,
) -> int:
    """Run the quality rules and record findings as review items.

    Returns the number of newly inserted review items; known fingerprints
    stay untouched.
    """
    recorded = 0

    for finding in quality_findings(
        sport=sport,
        duration_s=duration_s,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
    ):
        # The source record stays on the item for provenance, but it must not
        # be part of the identity: an import and a later `review scan` detect
        # the same canonical finding and must share one fingerprint.
        scope = [finding.rule, activity_id, finding.context]
        _, created = writer.record_review_item(
            category=QUALITY,
            detail=finding.detail,
            context={**finding.context, "rule": finding.rule},
            severity=finding.severity,
            fingerprint=review_fingerprint(scope),
            activity_id=activity_id,
            source_record_id=source_record_id,
            import_run_id=import_run_id,
        )
        recorded += created

    return recorded


def record_ambiguous_match(
    writer: TrainingWriter,
    *,
    source_record_id: int,
    external_id: str,
    candidates: list,
    import_run_id: int | None,
) -> int:
    """Persist an ambiguous match as an open review item.

    `candidates` is a list of MatchCandidate objects (or objects with
    activity_id, match_method, and confidence attributes).
    """
    context = {
        "external_id": external_id,
        "candidates": [
            {
                "activity_id": candidate.activity_id,
                "match_method": candidate.match_method,
                "confidence": candidate.confidence,
            }
            for candidate in candidates
        ],
    }
    _, created = writer.record_review_item(
        category=AMBIGUOUS_MATCH,
        detail=(
            "ambiguous match: "
            f"{len(candidates)} candidate activities "
            f"({', '.join(c.activity_id for c in candidates)})"
        ),
        context=context,
        severity="warn",
        fingerprint=review_fingerprint(
            [AMBIGUOUS_MATCH, source_record_id, external_id]
            + sorted(c.activity_id for c in candidates)
        ),
        source_record_id=source_record_id,
        import_run_id=import_run_id,
    )
    return int(created)


def refresh_activity_quality(
    writer: TrainingWriter,
    *,
    activity_id: str,
    resolve_item_id: int | None = None,
    resolve_note: str = "manual edit",
) -> list[Finding]:
    """Re-evaluate the quality rules after a manual edit.

    Resolves the triggering review item and every open quality item whose
    fingerprint no longer matches the current values (fixed or superseded),
    then records fresh findings for the new values. Returns the current
    findings so callers can report ``quality: ok`` or what remains.
    """
    row = writer.connection.execute(
        """
        SELECT sport, duration_s, elapsed_s, distance_m
        FROM activities WHERE id = ?
        """,
        (activity_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"unknown activity: {activity_id}")

    sport = row["sport"] or ""
    duration_s = row["duration_s"] or 0
    elapsed_s = row["elapsed_s"] or 0
    distance_m = row["distance_m"] or 0

    findings = quality_findings(
        sport=sport,
        duration_s=duration_s,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
    )
    current_fingerprints = {
        review_fingerprint([finding.rule, activity_id, finding.context])
        for finding in findings
    }

    if resolve_item_id is not None:
        item = writer.review_item(resolve_item_id)
        if item is not None and item["status"] == "open":
            writer.set_review_status(
                resolve_item_id,
                "resolved",
                note=resolve_note,
            )

    for item in writer.review_items(category=QUALITY, status="open"):
        if item["activity_id"] != activity_id:
            continue
        if (
            item["id"] != resolve_item_id
            and item["fingerprint"] in current_fingerprints
        ):
            continue
        writer.set_review_status(item["id"], "resolved", note=resolve_note)

    record_quality_findings(
        writer,
        activity_id=activity_id,
        source_record_id=None,
        import_run_id=None,
        sport=sport,
        duration_s=duration_s,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
    )

    return findings


def record_manual_flag(
    writer: TrainingWriter,
    *,
    activity_id: str,
    category: str,
    detail: str,
    severity: str,
) -> int:
    """Flag an activity manually; re-flagging the same content is a no-op."""
    _, created = writer.record_review_item(
        category=category,
        detail=detail,
        severity=severity,
        fingerprint=review_fingerprint([category, activity_id, detail]),
        activity_id=activity_id,
    )
    return int(created)


def record_field_conflicts(
    writer: TrainingWriter,
    *,
    activity_id: str,
    source_record_id: int | None,
    import_run_id: int | None,
    conflicts: list,
) -> int:
    """Record cross-source field disagreements as review items.

    One item per differing field. Re-recording an identical conflict is a
    no-op (fingerprint over sources and normalized values); when the values
    involved change, older open conflict items for the same activity+field
    are superseded so only the current state stays open.
    """
    recorded = 0

    for conflict in conflicts:
        context = {
            "rule": "field_conflict",
            "field": conflict.field_name,
            "current": {
                "source": conflict.current_source,
                "value": conflict.current_value,
            },
            "incoming": {
                "source": conflict.incoming_source,
                "value": conflict.incoming_value,
            },
        }
        fingerprint = review_fingerprint(
            [
                CONFLICT,
                activity_id,
                conflict.field_name,
                conflict.current_source,
                conflict.incoming_source,
                _conflict_signature(
                    conflict.field_name, conflict.current_value
                ),
                _conflict_signature(
                    conflict.field_name, conflict.incoming_value
                ),
            ]
        )

        # Leave an unchanged conflict untouched; supersede older ones whose
        # values no longer match the current disagreement.
        for item in writer.review_items(category=CONFLICT, status="open"):
            if (
                item["activity_id"] == activity_id
                and item["fingerprint"] != fingerprint
                and json.loads(item["context_json"] or "{}").get("field")
                == conflict.field_name
            ):
                writer.set_review_status(
                    item["id"],
                    "resolved",
                    note="superseded: field conflict changed",
                )

        detail = (
            f"{conflict.field_name} differs: {conflict.current_source} has "
            f"{format_field(conflict.field_name, conflict.current_value)}, "
            f"{conflict.incoming_source} reports "
            f"{format_field(conflict.field_name, conflict.incoming_value)}"
        )
        _, created = writer.record_review_item(
            category=CONFLICT,
            detail=detail,
            context=context,
            severity="warn",
            fingerprint=fingerprint,
            activity_id=activity_id,
            source_record_id=source_record_id,
            import_run_id=import_run_id,
        )
        recorded += created

    return recorded


def _conflict_signature(field_name: str, value: object) -> object:
    """Normalize a value so repeated imports produce stable fingerprints."""
    if isinstance(value, (int, float)):
        if field_name in ("duration_s", "elapsed_s", "distance_m"):
            return round(float(value), 1)
        return round(float(value), 2)
    return value


def review_fingerprint(parts: list) -> str:
    """Stable content hash for idempotent review-item detection."""
    payload = json.dumps(
        parts,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _format_pace(pace_s_per_km: float) -> str:
    minutes = int(pace_s_per_km // 60)
    seconds = int(round(pace_s_per_km % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"
