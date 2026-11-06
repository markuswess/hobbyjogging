"""Incremental sync job across Garmin, Intervals, FIT, and review scan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingWriter

from .config import default_fit_dir
from .fit_import import FitImporter
from .garmin import GarminFetcher
from .intervals import IntervalsImporter
from .scan import scan_quality


@dataclass
class SyncSummary:
    start: date
    end: date
    plan_end: date
    include_garmin: bool = True
    include_intervals: bool = True
    include_fit: bool = True
    include_scan: bool = True
    garmin_fetched: int = 0
    garmin_failed: int = 0
    intervals_activities: int = 0
    intervals_wellness: int = 0
    intervals_events: int = 0
    intervals_removed: int = 0
    intervals_revived: int = 0
    fit_files: int = 0
    fit_activities: int = 0
    fit_matched: int = 0
    fit_created: int = 0
    review_new: int = 0
    review_open: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def run_sync(
    connection,
    *,
    start: date,
    end: date,
    plan_end: date,
    include_garmin: bool = True,
    include_intervals: bool = True,
    include_fit: bool = True,
    include_scan: bool = True,
    full: bool = False,
    fit_dir: str | Path | None = None,
) -> SyncSummary:
    """Run the ordered incremental sync.

    Source failures are recorded and the remaining sources still run. The
    caller decides the exit status from ``summary.failures``.
    """
    summary = SyncSummary(
        start=start,
        end=end,
        plan_end=plan_end,
        include_garmin=include_garmin,
        include_intervals=include_intervals,
        include_fit=include_fit,
        include_scan=include_scan,
    )

    if include_garmin:
        try:
            garmin = GarminFetcher(connection).fetch(start, end)
            summary.garmin_fetched = garmin.downloaded
            summary.garmin_failed = garmin.failed
            if garmin.failed:
                error = (
                    garmin.errors[0]
                    if garmin.errors
                    else f"{garmin.failed} download(s) failed"
                )
                summary.failures.append(("garmin", error))
        except Exception as exc:
            summary.failures.append(("garmin", _error(exc)))

    if include_intervals:
        try:
            intervals = IntervalsImporter(connection).import_range(
                start,
                end,
                plan_end=plan_end,
            )
            summary.intervals_activities = intervals.activities_imported
            summary.intervals_wellness = intervals.wellness_imported
            summary.intervals_events = intervals.events_imported
            summary.intervals_removed = intervals.events_removed
            summary.intervals_revived = intervals.events_revived
        except Exception as exc:
            summary.failures.append(("intervals", _error(exc)))

    if include_fit:
        try:
            fit = FitImporter(connection).import_paths(
                [fit_dir or default_fit_dir()],
                recursive=True,
                skip_known=not full,
            )
            summary.fit_files = fit.files_imported
            summary.fit_activities = fit.activities_imported
            summary.fit_matched = fit.activities_matched
            summary.fit_created = fit.activities_created
        except Exception as exc:
            summary.failures.append(("fit", _error(exc)))

    if include_scan:
        try:
            scan = scan_quality(TrainingWriter(connection))
            summary.review_new = scan.recorded
        except Exception as exc:
            summary.failures.append(("review", _error(exc)))

        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM review_items WHERE status = 'open'"
            ).fetchone()
            summary.review_open = row[0] if row else 0
        except Exception:
            pass

    return summary


def format_sync_summary(summary: SyncSummary) -> str:
    lines = [
        f"Sync {summary.end} "
        f"({summary.start} .. {summary.end}, "
        f"events to {summary.plan_end})"
    ]

    if summary.include_garmin:
        lines.append(
            f"  garmin:    {summary.garmin_fetched} fetched, "
            f"{summary.garmin_failed} failed"
        )
    else:
        lines.append("  garmin:    skipped")

    if summary.include_intervals:
        lines.append(
            f"  intervals: {summary.intervals_activities} activities, "
            f"{summary.intervals_wellness} wellness, "
            f"{summary.intervals_events} events "
            f"({summary.intervals_removed} removed, "
            f"{summary.intervals_revived} revived)"
        )
    else:
        lines.append("  intervals: skipped")

    if summary.include_fit:
        lines.append(
            f"  fit:       {summary.fit_files} files, "
            f"{summary.fit_activities} activities "
            f"({summary.fit_matched} matched, "
            f"{summary.fit_created} created)"
        )
    else:
        lines.append("  fit:       skipped")

    if summary.include_scan:
        lines.append(
            f"  review:    {summary.review_new} new items, "
            f"{summary.review_open} open"
        )
    else:
        lines.append("  review:    skipped")

    for source, error in summary.failures:
        lines.append(f"Failures: {source}: {error}")

    return "\n".join(lines)


def _error(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__
