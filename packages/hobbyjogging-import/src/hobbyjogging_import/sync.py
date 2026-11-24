"""Incremental sync job across every configured source.

The order is deliberate: fetch (Garmin, Intervals, FIT, Runalyze, Strava) →
offline derivations → quality review scan. Maintenance recomputes and the
dashboard belong to ``sync.sh``, which owns the transaction boundaries.

A missing credential is not a failed sync: an enabled source without a key is
skipped with a warning and the rest still run. Only a source that was
*configured* and then failed is a failure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.sources_config import SourcesConfig, load_sources

from .config import (
    default_fit_dir,
    garmin_api_key,
    intervals_credentials,
    runalyze_api_key,
)
from .fit_import import FitImporter
from .freshness import default_strava_dir, newest_unimported_export
from .garmin import GarminFetcher
from .garmin_wellness import GarminWellnessImporter
from .intervals import IntervalsImporter
from .runalyze import RunalyzeClient, RunalyzeRateLimitError
from .runalyze_gear import RunalyzeGearImporter
from .runalyze_import import RunalyzeEnricher
from .runalyze_races import RunalyzeRaceImporter
from .runalyze_vo2max import RunalyzeVo2maxImporter
from .scan import scan_quality
from .strava_import import StravaCsvImporter

# Runalyze's collection is filtered locally, so re-read a little before the
# last successful run to catch late uploads and edits.
RUNALYZE_OVERLAP = timedelta(days=14)


@dataclass
class SyncSummary:
    start: date
    end: date
    plan_end: date
    include_garmin: bool = True
    include_intervals: bool = True
    include_fit: bool = True
    include_runalyze: bool = True
    include_strava: bool = True
    include_derive: bool = True
    include_scan: bool = True
    garmin_fetched: int = 0
    garmin_failed: int = 0
    garmin_wellness: int = 0
    intervals_activities: int = 0
    intervals_wellness: int = 0
    intervals_events: int = 0
    intervals_removed: int = 0
    intervals_revived: int = 0
    fit_files: int = 0
    fit_activities: int = 0
    fit_matched: int = 0
    fit_created: int = 0
    runalyze_since: date | None = None
    runalyze_processed: int = 0
    runalyze_matched: int = 0
    runalyze_unmatched: int = 0
    runalyze_pending: int = 0
    runalyze_stopped: str = ""
    runalyze_gear: int = 0
    runalyze_vo2max: int = 0
    runalyze_races: int = 0
    strava_path: Path | None = None
    strava_social: int = 0
    strava_created: int = 0
    review_new: int = 0
    review_open: int = 0
    skips: list[tuple[str, str]] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    # Wall-clock seconds per phase, including a "total" entry.
    durations: dict[str, float] = field(default_factory=dict)


def run_sync(
    connection,
    *,
    start: date,
    end: date,
    plan_end: date,
    config: SourcesConfig | None = None,
    include_garmin: bool = True,
    include_intervals: bool = True,
    include_fit: bool = True,
    include_runalyze: bool = True,
    include_strava: bool = True,
    include_derive: bool = True,
    include_scan: bool = True,
    full: bool = False,
    fit_dir: str | Path | None = None,
    strava_dir: str | Path | None = None,
    runalyze_since: date | None = None,
) -> SyncSummary:
    """Run the ordered incremental sync.

    Source failures are recorded and the remaining sources still run. The
    caller decides the exit status from ``summary.failures``.
    """
    config = config or load_sources()
    summary = SyncSummary(
        start=start,
        end=end,
        plan_end=plan_end,
        include_garmin=include_garmin,
        include_intervals=include_intervals,
        include_fit=include_fit,
        include_runalyze=include_runalyze,
        include_strava=include_strava,
        include_derive=include_derive,
        include_scan=include_scan,
    )

    def skipped(name: str) -> bool:
        if not config.enabled(name):
            summary.skips.append((name, "disabled in sources.toml"))
            return True
        return False

    if include_garmin and not skipped("garmin"):
        if not garmin_api_key():
            summary.skips.append(
                ("garmin", "GARMIN_PERSONAL_API_KEY is not set")
            )
        else:
            started = time.monotonic()
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
            finally:
                summary.durations["garmin"] = time.monotonic() - started

            if not config.capability("garmin", "wellness"):
                summary.skips.append(
                    ("garmin wellness", "wellness capability disabled")
                )
            else:
                try:
                    wellness = GarminWellnessImporter(connection).import_range(
                        start,
                        end,
                    )
                    summary.garmin_wellness = wellness.written
                except Exception as exc:
                    # A missing wellness feed must not fail the activity sync.
                    summary.skips.append(("garmin wellness", _error(exc)))

    if include_intervals and not skipped("intervals"):
        athlete_id, api_key = intervals_credentials()
        if not athlete_id or not api_key:
            summary.skips.append(
                (
                    "intervals",
                    "INTERVALS_ATHLETE_ID and INTERVALS_API_KEY are not set",
                )
            )
        else:
            started = time.monotonic()
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
            finally:
                summary.durations["intervals"] = time.monotonic() - started

    if include_fit and not skipped("fit"):
        fit_path = Path(fit_dir).expanduser() if fit_dir else default_fit_dir()
        if not fit_path.is_dir():
            summary.skips.append(("fit", f"{fit_path} is not a directory"))
        else:
            started = time.monotonic()
            try:
                fit = FitImporter(connection).import_paths(
                    [fit_path],
                    recursive=True,
                    skip_known=not full,
                )
                summary.fit_files = fit.files_imported
                summary.fit_activities = fit.activities_imported
                summary.fit_matched = fit.activities_matched
                summary.fit_created = fit.activities_created
            except Exception as exc:
                summary.failures.append(("fit", _error(exc)))
            finally:
                summary.durations["fit"] = time.monotonic() - started

    if include_runalyze and not skipped("runalyze"):
        summary.runalyze_since = _runalyze_since(
            connection,
            runalyze_since,
            start,
        )
        if not runalyze_api_key():
            summary.skips.append(("runalyze", "RUNALYZE_API_KEY is not set"))
        elif not config.capability("runalyze", "tags"):
            summary.skips.append(
                (
                    "runalyze",
                    "tags capability disabled; the enrich step is skipped",
                )
            )
        else:
            started = time.monotonic()
            try:
                policy = config.policy("runalyze")
                enrich = RunalyzeEnricher(
                    connection,
                    client=RunalyzeClient(),
                    create=policy.create,
                    workout_type=config.capability(
                        "runalyze",
                        "workout_type",
                    ),
                    trimp=config.capability("runalyze", "trimp"),
                ).enrich(
                    start=summary.runalyze_since,
                    end=end,
                )
                summary.runalyze_processed = enrich.processed
                summary.runalyze_matched = enrich.matched
                summary.runalyze_unmatched = enrich.unmatched + enrich.ambiguous
                summary.runalyze_pending = enrich.not_processed
                summary.runalyze_stopped = enrich.stopped_reason
                if enrich.stopped_reason:
                    summary.skips.append(
                        (
                            "runalyze",
                            f"{enrich.not_processed} row(s) pending: "
                            f"{enrich.stopped_reason}",
                        )
                    )
            except RunalyzeRateLimitError as exc:
                summary.skips.append(("runalyze", f"rate limited: {exc}"))
            except Exception as exc:
                summary.failures.append(("runalyze", _error(exc)))
            finally:
                summary.durations["runalyze"] = time.monotonic() - started

        if include_derive:
            _derive_offline(connection, summary, config)

    if include_strava and not skipped("strava"):
        export = newest_unimported_export(connection, strava_dir)
        if export is None:
            summary.skips.append(
                ("strava", "no unimported export_*.zip in the drop directory")
            )
        else:
            started = time.monotonic()
            try:
                policy = config.policy("strava")
                strava = StravaCsvImporter(
                    connection,
                    create=policy.create,
                    title=policy.title,
                    description=policy.description,
                ).import_export(export)
                summary.strava_path = export
                summary.strava_social = strava.social_written
                summary.strava_created = strava.activities_created
            except Exception as exc:
                summary.failures.append(("strava", _error(exc)))
            finally:
                summary.durations["strava"] = time.monotonic() - started

    if include_scan:
        started = time.monotonic()
        try:
            scan = scan_quality(TrainingWriter(connection))
            summary.review_new = scan.recorded
        except Exception as exc:
            summary.failures.append(("review", _error(exc)))
        finally:
            summary.durations["review"] = time.monotonic() - started

        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM review_items WHERE status = 'open'"
            ).fetchone()
            summary.review_open = row[0] if row else 0
        except Exception:
            pass

    if summary.durations:
        summary.durations["total"] = sum(summary.durations.values())

    return summary


def _runalyze_since(
    connection,
    explicit: date | None,
    fallback: date,
) -> date:
    """The enrichment window start: last success minus the overlap."""
    if explicit is not None:
        return explicit
    from .freshness import last_success_date

    last = last_success_date(connection, "runalyze")
    if last is None:
        return fallback
    return max(fallback, last - RUNALYZE_OVERLAP)


def _derive_offline(
    connection,
    summary: SyncSummary,
    config: SourcesConfig,
) -> None:
    """Re-derive Runalyze gear, VO2max and races from stored payloads.

    The first two cost no requests. Races still reads the API; a rate limit or
    an API error is a warning, because the auxiliary metadata must not fail an
    otherwise good sync. A disabled capability skips only its own step.
    """
    started = time.monotonic()

    if not config.capability("runalyze", "gear"):
        summary.skips.append(
            ("runalyze gear", "gear capability disabled")
        )
    else:
        try:
            gear = RunalyzeGearImporter(connection).import_gear()
            summary.runalyze_gear = gear.created + gear.linked_existing
        except Exception as exc:
            summary.failures.append(("runalyze gear", _error(exc)))

    if not config.capability("runalyze", "vo2max"):
        summary.skips.append(
            ("runalyze vo2max", "vo2max capability disabled")
        )
    else:
        try:
            vo2max = RunalyzeVo2maxImporter(connection).import_vo2max()
            summary.runalyze_vo2max = vo2max.written
        except Exception as exc:
            summary.failures.append(("runalyze vo2max", _error(exc)))

    if not config.capability("runalyze", "races"):
        summary.skips.append(
            ("runalyze races", "races capability disabled")
        )
    elif runalyze_api_key():
        try:
            races = RunalyzeRaceImporter(
                connection,
                RunalyzeClient(),
            ).import_races()
            summary.runalyze_races = races.written
        except RunalyzeRateLimitError as exc:
            summary.skips.append(("runalyze races", f"rate limited: {exc}"))
        except Exception as exc:
            summary.skips.append(("runalyze races", _error(exc)))

    summary.durations["derive"] = time.monotonic() - started


def format_sync_summary(summary: SyncSummary) -> str:
    lines = [
        f"Sync {summary.end} "
        f"({summary.start} .. {summary.end}, "
        f"events to {summary.plan_end})"
    ]

    if summary.include_garmin:
        lines.append(
            f"  garmin:    {summary.garmin_fetched} fetched, "
            f"{summary.garmin_failed} failed, "
            f"{summary.garmin_wellness} wellness days"
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

    if summary.include_runalyze:
        detail = (
            f"{summary.runalyze_processed} processed, "
            f"{summary.runalyze_matched} matched, "
            f"{summary.runalyze_unmatched} unmatched"
        )
        if summary.runalyze_since is not None:
            detail = f"since {summary.runalyze_since}: {detail}"
        if summary.runalyze_stopped:
            detail += f" (stopped: {summary.runalyze_stopped})"
        lines.append(f"  runalyze:  {detail}")
    else:
        lines.append("  runalyze:  skipped")

    if summary.include_derive and summary.include_runalyze:
        lines.append(
            f"  derived:   gear {summary.runalyze_gear}, "
            f"vo2max {summary.runalyze_vo2max}, "
            f"races {summary.runalyze_races}"
        )

    if summary.include_strava:
        if summary.strava_path is None:
            lines.append("  strava:    no new export")
        else:
            lines.append(
                f"  strava:    {summary.strava_path.name}: "
                f"{summary.strava_social} social, "
                f"{summary.strava_created} created"
            )
    else:
        lines.append("  strava:    skipped")

    if summary.include_scan:
        lines.append(
            f"  review:    {summary.review_new} new items, "
            f"{summary.review_open} open"
        )
    else:
        lines.append("  review:    skipped")

    if summary.durations:
        parts = [
            f"{name} {summary.durations[name]:.1f}s"
            for name in (
                "garmin",
                "intervals",
                "fit",
                "runalyze",
                "derive",
                "strava",
                "review",
            )
            if name in summary.durations
        ]
        if "total" in summary.durations:
            parts.append(f"total {summary.durations['total']:.1f}s")
        if parts:
            lines.append(f"  timing:    {', '.join(parts)}")

    for source, reason in summary.skips:
        lines.append(f"Skipped: {source}: {reason}")

    for source, error in summary.failures:
        lines.append(f"Failures: {source}: {error}")

    return "\n".join(lines)


def _error(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__
