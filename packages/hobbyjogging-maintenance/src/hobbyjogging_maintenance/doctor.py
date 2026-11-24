"""Fresh-install setup: ``init`` and ``doctor``.

``init`` is the explicit, idempotent first step: create the database, apply
every schema migration and make sure the FIT directory exists. ``doctor``
answers "can this installation run, and what is missing" without writing:
paths and permissions, schema version, credentials per configured source, a
bounded liveness probe where the API allows one, pending backfills, source
freshness and the next command.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Literal

from hobbyjogging_core import (
    SCHEMA_VERSION,
    default_database_path,
    open_database,
)
from hobbyjogging_core.sources_config import SourcesConfig, load_sources

from hobbyjogging_import.config import (
    default_fit_dir,
    garmin_api_key,
    intervals_credentials,
    runalyze_api_key,
)
from hobbyjogging_import.freshness import (
    STALE_AFTER_DAYS,
    default_strava_dir,
    last_success_date,
    strava_exports,
    newest_unimported_export,
)

from .registry import all_tasks
from .store import applied_ids

Status = Literal["ok", "warn", "fail", "skip"]

SHEET_DEFAULT = Path("data/laufen.ods")
NETWORK_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class Check:
    """One doctor line."""

    name: str
    status: Status
    detail: str
    hint: str = ""


@dataclass(frozen=True)
class DoctorReport:
    checks: list[Check]
    next_command: str
    database_empty: bool = False

    @property
    def failed(self) -> bool:
        return any(check.status == "fail" for check in self.checks)

    @property
    def warned(self) -> bool:
        return any(check.status == "warn" for check in self.checks)


def initialize(
    database: str | Path | None = None,
    *,
    fit_dir: str | Path | None = None,
) -> tuple[Path, int, bool]:
    """Create and migrate the database; return ``(path, version, created)``.

    A second run is a no-op beyond checking the schema. The FIT directory is
    created when it is missing, so the first sync has a place to read.
    """
    path = Path(database).expanduser() if database else default_database_path()
    path = path.resolve()
    existed = path.exists()

    connection = open_database(path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    directory = Path(fit_dir).expanduser() if fit_dir else default_fit_dir()
    directory.mkdir(parents=True, exist_ok=True)

    return path, version, not existed


def _database_check(
    path: Path,
    connection: sqlite3.Connection | None,
) -> Check:
    parent = path.parent
    if not parent.exists():
        return Check(
            "database",
            "fail",
            f"{path}: parent directory does not exist",
            "run ./init.sh to create it",
        )
    if not os.access(parent, os.W_OK):
        return Check(
            "database",
            "fail",
            f"{path}: parent directory is not writable",
            "fix the permissions or choose another HOBBYJOGGING_DB",
        )
    if connection is None:
        return Check(
            "database",
            "warn",
            f"{path}: not created yet",
            "run ./init.sh",
        )
    size = path.stat().st_size if path.exists() else 0
    return Check("database", "ok", f"{path} ({size // 1024} KiB, writable)")


def _schema_check(
    connection: sqlite3.Connection | None,
) -> Check:
    if connection is None:
        return Check("schema", "skip", "no database yet")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return Check("schema", "ok", f"{version} (current)")
    if version > SCHEMA_VERSION:
        return Check(
            "schema",
            "fail",
            f"{version} is newer than the code supports ({SCHEMA_VERSION})",
            "use the code that built this database",
        )
    return Check(
        "schema",
        "warn",
        f"{version} (pending: {SCHEMA_VERSION})",
        "run ./init.sh to migrate",
    )


def _sources_check(config: SourcesConfig) -> Check:
    enabled = [name for name in config.policies if config.enabled(name)]
    if config.path is None:
        location = "code defaults"
    else:
        location = str(config.path)
    if not enabled:
        return Check(
            "sources",
            "warn",
            f"{location}: no source enabled",
            "enable at least one source in sources.toml",
        )
    return Check(
        "sources",
        "ok",
        f"{location}: {', '.join(enabled)}",
    )


def _credential_checks(
    config: SourcesConfig,
    *,
    fit_dir: Path,
    strava_dir: Path,
) -> list[Check]:
    checks: list[Check] = []

    if config.enabled("fit"):
        if fit_dir.is_dir():
            checks.append(
                Check("fit", "ok", f"{fit_dir} (FIT archive)")
            )
        else:
            checks.append(
                Check(
                    "fit",
                    "warn",
                    f"{fit_dir} does not exist",
                    "run ./init.sh or set HOBBYJOGGING_FIT_DIR",
                )
            )

    if config.enabled("garmin"):
        if garmin_api_key():
            checks.append(
                Check("garmin", "ok", "GARMIN_PERSONAL_API_KEY is set")
            )
        else:
            checks.append(
                Check(
                    "garmin",
                    "warn",
                    "GARMIN_PERSONAL_API_KEY is not set",
                    "set it in .env, or disable garmin in sources.toml",
                )
            )

    if config.enabled("intervals"):
        athlete_id, api_key = intervals_credentials()
        if athlete_id and api_key:
            checks.append(
                Check("intervals", "ok", "athlete id and API key are set")
            )
        else:
            missing = []
            if not athlete_id:
                missing.append("INTERVALS_ATHLETE_ID")
            if not api_key:
                missing.append("INTERVALS_API_KEY")
            checks.append(
                Check(
                    "intervals",
                    "warn",
                    f"{' and '.join(missing)} not set",
                    "set it in .env, or disable intervals in sources.toml",
                )
            )

    if config.enabled("runalyze"):
        if runalyze_api_key():
            checks.append(
                Check("runalyze", "ok", "RUNALYZE_API_KEY is set")
            )
        else:
            checks.append(
                Check(
                    "runalyze",
                    "warn",
                    "RUNALYZE_API_KEY is not set",
                    "set it in .env, or disable runalyze in sources.toml",
                )
            )

    if config.enabled("strava"):
        exports = strava_exports(strava_dir)
        if not strava_dir.is_dir():
            checks.append(
                Check(
                    "strava",
                    "warn",
                    f"{strava_dir} does not exist",
                    "drop an export_*.zip there, or disable strava",
                )
            )
        elif exports:
            checks.append(
                Check(
                    "strava",
                    "ok",
                    f"{len(exports)} export(s) in {strava_dir} "
                    "(newest unimported is picked up)",
                )
            )
        else:
            checks.append(
                Check(
                    "strava",
                    "warn",
                    f"no export_*.zip in {strava_dir}",
                    "the Strava download stays manual; or disable strava",
                )
            )

    if config.enabled("sheet"):
        if SHEET_DEFAULT.is_file():
            checks.append(Check("sheet", "ok", str(SHEET_DEFAULT)))
        else:
            checks.append(
                Check(
                    "sheet",
                    "warn",
                    f"sheet enabled but {SHEET_DEFAULT} is missing",
                    "add the workbook or disable sheet in sources.toml",
                )
            )

    return checks


def _liveness_checks(
    config: SourcesConfig,
    *,
    timeout: float,
    probe: Callable[[str, float], tuple[bool, str]] | None,
) -> list[Check]:
    if probe is None:
        return [
            Check(
                "liveness",
                "skip",
                "network probes disabled (--no-network)",
            )
        ]

    checks: list[Check] = []
    for source in ("garmin", "intervals", "runalyze"):
        if not config.enabled(source):
            continue
        started = datetime.now()
        try:
            ok, detail = probe(source, timeout)
        except Exception as exc:  # a probe never crashes the doctor
            ok, detail = False, str(exc) or exc.__class__.__name__
        elapsed = (datetime.now() - started).total_seconds()
        status: Status = "ok" if ok else "warn"
        checks.append(
            Check(
                f"{source} api",
                status,
                f"{detail} ({elapsed:.1f}s)",
            )
        )
    if not checks:
        checks.append(Check("liveness", "skip", "no online source enabled"))
    return checks


def _migration_check(
    connection: sqlite3.Connection | None,
) -> Check:
    if connection is None:
        return Check("backfills", "skip", "no database yet")
    applied = applied_ids(connection)
    pending = [
        item for item in all_tasks()
        if item.applied_once and item.id not in applied
    ]
    if not pending:
        return Check(
            "backfills",
            "ok",
            f"all applied ({len(applied)} recorded)",
        )
    names = ", ".join(item.id for item in pending)
    return Check(
        "backfills",
        "warn",
        f"pending: {names}",
        "run hobbyjogging-maintenance run --all",
    )


def _freshness_check(
    connection: sqlite3.Connection | None,
    config: SourcesConfig,
    *,
    today: date,
    strava_dir: Path,
) -> Check:
    if connection is None:
        return Check("freshness", "skip", "no database yet")

    problems: list[str] = []
    for source in ("fit", "intervals", "garmin", "runalyze"):
        if not config.enabled(source):
            continue
        last = last_success_date(connection, source)
        if last is None:
            problems.append(f"{source} never")
        elif (today - last).days > STALE_AFTER_DAYS:
            problems.append(f"{source} {(today - last).days} d")

    if config.enabled("strava"):
        exports = strava_exports(strava_dir)
        if exports and newest_unimported_export(connection, strava_dir):
            problems.append("strava export waiting")

    if not problems:
        return Check(
            "freshness",
            "ok",
            f"every configured source ran in the last {STALE_AFTER_DAYS} d",
        )
    return Check(
        "freshness",
        "warn",
        ", ".join(problems),
        "run ./sync.sh",
    )


def _next_command(
    checks: list[Check],
    *,
    database_empty: bool,
) -> str:
    statuses = {check.name: check.status for check in checks}
    if statuses.get("database") == "warn":
        return "./init.sh"
    if statuses.get("schema") == "warn":
        return "./init.sh"
    if any(check.status == "fail" for check in checks):
        return "fix the failures above"
    if database_empty:
        return "./sync.sh"
    if statuses.get("backfills") == "warn":
        return "uv run python -m hobbyjogging_maintenance run --all"
    if statuses.get("freshness") == "warn":
        return "./sync.sh"
    return "./dashboard.sh"


def run_doctor(
    *,
    database: str | Path | None = None,
    fit_dir: str | Path | None = None,
    strava_dir: str | Path | None = None,
    sources_path: str | Path | None = None,
    today: date | None = None,
    network: bool = True,
    timeout: float = NETWORK_TIMEOUT_S,
    probe: Callable[[str, float], tuple[bool, str]] | None = None,
) -> DoctorReport:
    """Collect every check. The caller prints and decides the exit code."""
    path = Path(database).expanduser() if database else default_database_path()
    path = path.resolve()
    directory = Path(fit_dir).expanduser() if fit_dir else default_fit_dir()
    strava = (
        Path(strava_dir).expanduser()
        if strava_dir
        else default_strava_dir()
    )
    today = today or date.today()

    config = load_sources(sources_path)

    connection: sqlite3.Connection | None = None
    database_empty = False
    if path.is_file():
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT COUNT(*) FROM activities"
        ).fetchone()
        database_empty = (row[0] if row else 0) == 0

    try:
        checks: list[Check] = [
            Check(
                "python",
                "ok",
                f"{sys.version.split()[0]} "
                f"({sys.executable})",
            ),
        ]

        uv = shutil.which("uv")
        checks.append(
            Check("uv", "ok", uv) if uv else Check(
                "uv",
                "fail",
                "uv is not on PATH",
                "install uv: https://docs.astral.sh/uv/",
            )
        )

        checks.append(_database_check(path, connection))
        checks.append(_schema_check(connection))
        checks.append(_sources_check(config))
        checks.extend(
            _credential_checks(
                config,
                fit_dir=directory,
                strava_dir=strava,
            )
        )
        checks.extend(
            _liveness_checks(
                config,
                timeout=timeout,
                probe=(probe or default_probe) if network else None,
            )
        )
        checks.append(_migration_check(connection))
        checks.append(
            _freshness_check(
                connection,
                config,
                today=today,
                strava_dir=strava,
            )
        )
    finally:
        if connection is not None:
            connection.close()

    return DoctorReport(
        checks=checks,
        next_command=_next_command(checks, database_empty=database_empty),
        database_empty=database_empty,
    )


def format_doctor(report: DoctorReport) -> str:
    width = max(len(check.name) for check in report.checks)
    lines = ["hobbyjogging doctor", ""]
    for check in report.checks:
        lines.append(
            f"  {check.status:<4}  {check.name:<{width}}  {check.detail}"
        )
        if check.hint and check.status in ("warn", "fail"):
            lines.append(f"        {'':<{width}}  -> {check.hint}")
    lines.append("")
    lines.append(f"Next: {report.next_command}")
    return "\n".join(lines)


def default_probe(
    source: str,
    timeout: float,
    *,
    today: date | None = None,
) -> tuple[bool, str]:
    """One bounded request that proves the credential still works."""
    day = today or date.today()

    if source == "garmin":
        from hobbyjogging_import.garmin import GarminClient

        client = GarminClient(timeout=timeout)
        client.list_activities(day, day)
        return True, "token exchange ok"

    if source == "intervals":
        from hobbyjogging_import.client import IntervalsClient

        client = IntervalsClient(timeout=int(timeout))
        client.activities(day, day)
        return True, "activities endpoint ok"

    if source == "runalyze":
        from hobbyjogging_import.runalyze import RunalyzeClient

        client = RunalyzeClient(timeout=int(timeout))
        response = client.get("activity", {"page": 1, "itemsPerPage": 1})
        if response.status in (401, 403):
            return False, f"the API rejected the token (HTTP {response.status})"
        if response.status == 429:
            return True, "reachable, rate limited"
        if response.status >= 400:
            return False, f"HTTP {response.status}"
        return True, "activity endpoint ok"

    return False, f"no probe for {source}"
