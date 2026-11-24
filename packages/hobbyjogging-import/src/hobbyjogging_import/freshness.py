"""Import-run freshness and the Strava export drop.

Both ``doctor`` and the source-freshness report answer "is it current", not
"can it run": the last successful run per source, the age of that run, and
whether a newer Strava export is waiting. The data already lives in
``import_runs``; nothing here writes.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

STRAVA_DIR_ENV = "HOBBYJOGGING_STRAVA_DIR"
DEFAULT_STRAVA_DIR = Path("data/strava")
STRAVA_EXPORT_GLOB = "export_*.zip"

# A source that has not had a successful run for this many days is stale. It
# is a warning, never an error: a deliberate pause is a valid state.
STALE_AFTER_DAYS = 30


def default_strava_dir() -> Path:
    value = os.environ.get(STRAVA_DIR_ENV)
    return Path(value).expanduser() if value else DEFAULT_STRAVA_DIR


@dataclass(frozen=True)
class SourceRun:
    """One import run, as the freshness view needs it."""

    source: str
    started_at: str
    status: str
    records_imported: int
    parameters: dict

    @property
    def date(self) -> date | None:
        return _date(self.started_at)


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def latest_runs(connection: sqlite3.Connection) -> dict[str, SourceRun]:
    """Return the newest run per source, whatever its status."""
    rows = connection.execute(
        """
        SELECT source, started_at, status, records_imported, parameters_json
        FROM import_runs
        WHERE id IN (
            SELECT MAX(id) FROM import_runs GROUP BY source
        )
        ORDER BY source
        """
    ).fetchall()

    runs: dict[str, SourceRun] = {}
    for row in rows:
        try:
            parameters = json.loads(row["parameters_json"] or "{}")
        except ValueError:
            parameters = {}
        if not isinstance(parameters, dict):
            parameters = {}
        runs[row["source"]] = SourceRun(
            source=row["source"],
            started_at=row["started_at"],
            status=row["status"],
            records_imported=row["records_imported"],
            parameters=parameters,
        )
    return runs


def last_success(
    connection: sqlite3.Connection,
    source: str,
) -> SourceRun | None:
    """Return the most recent successful run for one source."""
    row = connection.execute(
        """
        SELECT source, started_at, status, records_imported, parameters_json
        FROM import_runs
        WHERE source = ? AND status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (source,),
    ).fetchone()
    if row is None:
        return None
    try:
        parameters = json.loads(row["parameters_json"] or "{}")
    except ValueError:
        parameters = {}
    if not isinstance(parameters, dict):
        parameters = {}
    return SourceRun(
        source=row["source"],
        started_at=row["started_at"],
        status=row["status"],
        records_imported=row["records_imported"],
        parameters=parameters,
    )


def last_success_date(
    connection: sqlite3.Connection,
    source: str,
) -> date | None:
    run = last_success(connection, source)
    return run.date if run is not None else None


def imported_strava_exports(connection: sqlite3.Connection) -> set[Path]:
    """Return every Strava export path a successful run already read."""
    rows = connection.execute(
        """
        SELECT parameters_json FROM import_runs
        WHERE source = 'strava' AND status = 'success'
        """
    ).fetchall()

    paths: set[Path] = set()
    for row in rows:
        try:
            parameters = json.loads(row["parameters_json"] or "{}")
        except ValueError:
            continue
        if not isinstance(parameters, dict):
            continue
        value = parameters.get("path")
        if value:
            paths.add(Path(value).expanduser().resolve())
    return paths


def strava_exports(directory: str | Path | None = None) -> list[Path]:
    """Return every Strava export ZIP in the drop directory, newest first."""
    path = Path(directory).expanduser() if directory else default_strava_dir()
    if not path.is_dir():
        return []
    return sorted(
        path.glob(STRAVA_EXPORT_GLOB),
        key=lambda item: (item.stat().st_mtime, item.name),
        reverse=True,
    )


def newest_unimported_export(
    connection: sqlite3.Connection,
    directory: str | Path | None = None,
) -> Path | None:
    """The newest export no successful run has read, or ``None``."""
    imported = imported_strava_exports(connection)
    for path in strava_exports(directory):
        if path.resolve() not in imported:
            return path
    return None


def stale_sources(
    connection: sqlite3.Connection,
    *,
    today: date,
    sources: tuple[str, ...] = (
        "fit",
        "intervals",
        "garmin",
        "runalyze",
        "strava",
    ),
    threshold_days: int = STALE_AFTER_DAYS,
) -> list[tuple[str, int | None]]:
    """Return ``(source, days_since_success)`` for stale or never-run sources.

    ``None`` means the source has no successful run at all. Sources that were
    never configured have no rows and are reported here as never-run; the
    caller decides whether that source is enabled.
    """
    stale: list[tuple[str, int | None]] = []
    for source in sources:
        last = last_success_date(connection, source)
        if last is None:
            stale.append((source, None))
        elif (today - last).days > threshold_days:
            stale.append((source, (today - last).days))
    return stale
