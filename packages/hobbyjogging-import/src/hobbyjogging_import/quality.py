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

# Implied whole-activity pace sanity window, in seconds per kilometer.
MIN_PACE_S_PER_KM = 120.0  # 2:00 /km
MAX_PACE_S_PER_KM = 600.0  # 10:00 /km

PACE_SPORTS = frozenset(
    {
        "run",
        "trail_run",
        "treadmill_run",
        "track_run",
        "ride",
        "virtual_ride",
        "gravel_ride",
        "mtb_ride",
    }
)

AMBIGUOUS_MATCH = "ambiguous_match"
QUALITY = "quality"
MANUAL_FLAG = "manual_flag"


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

    if distance_m == 0:
        findings.append(
            Finding(
                rule="zero_distance",
                detail="distance is 0 m",
                context={"distance_m": distance_m, "sport": sport},
            )
        )

    if (
        sport in PACE_SPORTS
        and duration_s > 0
        and distance_m > 0
    ):
        pace_s_per_km = duration_s / (distance_m / 1000)

        if not (MIN_PACE_S_PER_KM <= pace_s_per_km <= MAX_PACE_S_PER_KM):
            findings.append(
                Finding(
                    rule="implied_pace",
                    detail=(
                        "implied pace "
                        f"{_format_pace(pace_s_per_km)} /km is outside "
                        "the plausible 2:00-10:00 /km window"
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
        scope = [finding.rule, activity_id, source_record_id, finding.context]
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
