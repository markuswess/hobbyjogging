"""Shared quality scan over canonical activities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from hobbyjogging_core import TrainingWriter

from .quality import (
    QUALITY,
    quality_findings,
    record_quality_findings,
    review_fingerprint,
)


@dataclass
class ScanSummary:
    activities: int = 0
    findings: int = 0
    recorded: int = 0
    checked: int = 0
    pruned: int = 0
    kept: int = 0


def scan_quality(
    writer: TrainingWriter,
    *,
    activity_id: str | None = None,
    dry_run: bool = False,
    prune: bool = False,
    on_finding: Callable[[object, object], None] | None = None,
) -> ScanSummary:
    """Run the canonical quality rules over one or all activities.

    The scan is idempotent: review items dedupe by fingerprint. With
    ``prune`` it also resolves open quality items whose rule no longer
    triggers for the activity's current values (and every quality item of an
    excluded activity). It commits its writes when it succeeds; callers that
    need a larger transaction should pass a writer on a connection they
    control.
    """
    if activity_id is not None:
        rows = writer.connection.execute(
            """
            SELECT id, sport, duration_s, elapsed_s, distance_m, moving_s,
                   excluded_at
            FROM activities WHERE id = ?
            """,
            (activity_id,),
        ).fetchall()

        if not rows:
            raise ValueError(f"unknown activity: {activity_id}")
    else:
        rows = writer.connection.execute(
            """
            SELECT id, sport, duration_s, elapsed_s, distance_m, moving_s,
                   excluded_at
            FROM activities
            ORDER BY local_date, id
            """
        ).fetchall()

    summary = ScanSummary(activities=len(rows))
    current: dict[str, set[str]] = {}
    excluded: set[str] = set()

    try:
        for row in rows:
            findings = quality_findings(
                sport=row["sport"] or "",
                duration_s=row["duration_s"] or 0,
                elapsed_s=row["elapsed_s"] or 0,
                distance_m=row["distance_m"] or 0,
                moving_s=row["moving_s"],
            )
            current[row["id"]] = {
                review_fingerprint(
                    [finding.rule, row["id"], finding.context]
                )
                for finding in findings
            }
            if row["excluded_at"]:
                excluded.add(row["id"])

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

        if prune:
            _prune_quality(
                writer,
                current=current,
                excluded=excluded,
                activity_id=activity_id,
                summary=summary,
                dry_run=dry_run,
            )

        if not dry_run:
            writer.connection.commit()

        return summary

    except Exception:
        writer.connection.rollback()
        raise


def _prune_quality(
    writer: TrainingWriter,
    *,
    current: dict[str, set[str]],
    excluded: set[str],
    activity_id: str | None,
    summary: ScanSummary,
    dry_run: bool,
) -> None:
    """Resolve open quality items that the current values no longer trigger."""
    for item in writer.review_items(category=QUALITY, status="open"):
        scoped = item["activity_id"]
        if activity_id is not None and scoped != activity_id:
            continue

        summary.checked += 1

        if scoped is not None and scoped in excluded:
            note = "prune: activity excluded"
        elif scoped is None or scoped not in current:
            summary.kept += 1
            continue
        elif item["fingerprint"] in current[scoped]:
            summary.kept += 1
            continue
        else:
            note = "prune: no longer triggered"

        summary.pruned += 1
        if not dry_run:
            writer.set_review_status(item["id"], "resolved", note=note)
