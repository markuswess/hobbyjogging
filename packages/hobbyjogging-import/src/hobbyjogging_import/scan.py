"""Shared quality scan over canonical activities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from hobbyjogging_core import TrainingWriter

from .quality import quality_findings, record_quality_findings


@dataclass
class ScanSummary:
    activities: int = 0
    findings: int = 0
    recorded: int = 0


def scan_quality(
    writer: TrainingWriter,
    *,
    activity_id: str | None = None,
    dry_run: bool = False,
    on_finding: Callable[[object, object], None] | None = None,
) -> ScanSummary:
    """Run the canonical quality rules over one or all activities.

    The scan is idempotent: review items dedupe by fingerprint. It commits
    its writes when it succeeds; callers that need a larger transaction
    should pass a writer on a connection they control.
    """
    if activity_id is not None:
        rows = writer.connection.execute(
            """
            SELECT id, sport, duration_s, elapsed_s, distance_m, moving_s
            FROM activities WHERE id = ?
            """,
            (activity_id,),
        ).fetchall()

        if not rows:
            raise ValueError(f"unknown activity: {activity_id}")
    else:
        rows = writer.connection.execute(
            """
            SELECT id, sport, duration_s, elapsed_s, distance_m, moving_s
            FROM activities
            ORDER BY local_date, id
            """
        ).fetchall()

    summary = ScanSummary(activities=len(rows))

    try:
        for row in rows:
            findings = quality_findings(
                sport=row["sport"] or "",
                duration_s=row["duration_s"] or 0,
                elapsed_s=row["elapsed_s"] or 0,
                distance_m=row["distance_m"] or 0,
                moving_s=row["moving_s"],
            )
            if not findings:
                continue

            summary.findings += len(findings)

            for finding in findings:
                if on_finding is not None:
                    on_finding(row, finding)

            if dry_run:
                continue

            summary.recorded += record_quality_findings(
                writer,
                activity_id=row["id"],
                source_record_id=None,
                import_run_id=None,
                sport=row["sport"] or "",
                duration_s=row["duration_s"] or 0,
                elapsed_s=row["elapsed_s"] or 0,
                distance_m=row["distance_m"] or 0,
                moving_s=row["moving_s"],
            )

        if not dry_run:
            writer.connection.commit()

        return summary

    except Exception:
        writer.connection.rollback()
        raise
