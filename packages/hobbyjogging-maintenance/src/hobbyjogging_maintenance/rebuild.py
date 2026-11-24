"""Fresh-database rebuild proof for the canonical activity layer.

The rebuild copies the *inputs* — raw source records, activity identities and
links, ownership pointers, devices, equipment — into a fresh schema, applies
the manual overlay, re-projects the key fields (``local_date`` and ``sport``)
and runs ``recompute_canonical``. It then diffs every canonical activity value
against the live database and checks the exclusion set.

It does not re-import from the network, re-match activities or re-decide
ownership. Those are recorded decisions, not projections; the proof is that
the canonical values are reproducible from the stored raw layer plus those
decisions and the overlay.
"""

from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from hobbyjogging_core import SCHEMA_VERSION, TrainingWriter, open_database
from hobbyjogging_core.db.writer import ACTIVITY_COLUMNS

from .canonical import (
    activities,
    expected,
    manual_inputs,
    owner,
    pointers,
    same,
)
from .context import Scope
from .overlay import (
    OverlayCounts,
    apply_overlay,
    iter_overlay,
    read_overlay,
)
from .registry import get_task
from .runner import run_task

MAX_DRIFTS = 20

_STRUCTURAL_TABLES = (
    "import_runs",
    "source_records",
    "devices",
    "equipment",
)


def _copy_structural(
    connection: sqlite3.Connection,
    source: Path,
) -> None:
    connection.execute("ATTACH DATABASE ? AS live", (str(source),))
    try:
        for table in _STRUCTURAL_TABLES:
            connection.execute(
                f"INSERT INTO {table} SELECT * FROM live.{table}"
            )
        connection.execute(
            """
            INSERT INTO activities (id, local_date, sport)
            SELECT id, '1970-01-01', 'other' FROM live.activities
            """
        )
        for table in ("activity_sources", "activity_field_sources"):
            connection.execute(
                f"INSERT INTO {table} SELECT * FROM live.{table}"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


@dataclass
class RebuildReport:
    """The result of one fresh-database rebuild."""

    source: Path
    target: Path
    temporary: bool
    overlay: OverlayCounts
    activities: int = 0
    values: int = 0
    drift: int = 0
    missing: int = 0
    extra: int = 0
    exclusions_live: int = 0
    exclusions_rebuilt: int = 0
    exclusions_match: bool = True
    raw_files: int = 0
    raw_missing: int = 0
    drifts: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.drift == 0
            and self.missing == 0
            and self.extra == 0
            and self.exclusions_match
            and self.raw_missing == 0
        )


def rebuild(
    source: str | Path,
    *,
    target: str | Path | None = None,
    overlay: str | Path | None = None,
) -> RebuildReport:
    """Rebuild a copy of ``source`` and return the canonical diff."""
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"source database not found: {source_path}")

    temporary = target is None
    temp_dir: tempfile.TemporaryDirectory | None = None
    if target is None:
        temp_dir = tempfile.TemporaryDirectory(
            prefix="hobbyjogging-rebuild-"
        )
        target_path = Path(temp_dir.name) / "rebuild.db"
    else:
        target_path = Path(target).expanduser().resolve()
        if target_path.exists():
            raise FileExistsError(f"target already exists: {target_path}")

    source_conn = sqlite3.connect(
        f"file:{source_path}?mode=ro",
        uri=True,
    )
    source_conn.row_factory = sqlite3.Row
    connection = open_database(target_path)

    try:
        _check_source_schema(source_conn, source_path)
        _copy_structural(connection, source_path)

        if overlay is None:
            records = list(iter_overlay(source_conn))
        else:
            records = read_overlay(overlay)

        counts = apply_overlay(connection, records)
        connection.commit()

        _project_key_fields(connection)
        connection.commit()

        result = run_task(connection, get_task("recompute_canonical"))
        if not result.ok:
            raise RuntimeError(
                result.error or "recompute_canonical failed"
            )

        report = _diff(source_conn, connection)
        report.source = source_path
        report.target = target_path
        report.temporary = temporary
        report.overlay = counts
        return report
    finally:
        source_conn.close()
        connection.close()
        if temp_dir is not None:
            temp_dir.cleanup()


def format_rebuild_report(report: RebuildReport) -> str:
    target = str(report.target)
    if report.temporary:
        target += " (temporary, removed)"
    lines = [
        "Rebuild check",
        f"  source:    {report.source}",
        f"  target:    {target}",
        f"  overlay:   {report.overlay.records} records "
        f"({report.overlay.manual_fields} manual fields, "
        f"{report.overlay.owner_patches} owner patches, "
        f"{report.overlay.workout_sets} workout sets, "
        f"{report.overlay.tag_sets} tag sets, "
        f"{report.overlay.equipment_links} equipment links, "
        f"{report.overlay.exclusions} exclusions, "
        f"{report.overlay.review_answers} review answers)",
        f"  activities: {report.activities}, values: {report.values}",
        f"  drift: {report.drift}, missing: {report.missing}, "
        f"extra: {report.extra}",
        f"  exclusions: {report.exclusions_live} live / "
        f"{report.exclusions_rebuilt} rebuilt",
        f"  raw archive: {report.raw_files} files, "
        f"{report.raw_missing} missing",
    ]
    for detail in report.drifts:
        lines.append(f"  drift: {detail}")
    for detail in report.other:
        lines.append(f"  {detail}")
    lines.append(
        "  OK: empty canonical diff"
        if report.ok
        else "  FAILED: the rebuild does not match the live database"
    )
    return "\n".join(lines)


def _check_source_schema(
    source: sqlite3.Connection,
    path: Path,
) -> None:
    version = source.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION:
        raise RuntimeError(
            f"source schema {version} does not match code schema "
            f"{SCHEMA_VERSION}; migrate {path} first"
        )


def _project_key_fields(connection: sqlite3.Connection) -> None:
    """Project local_date and sport first, so distance sees the real sport."""
    writer = TrainingWriter(connection)
    for activity in activities(connection, Scope()):
        manual = manual_inputs(connection, activity["id"])
        fields = pointers(connection, activity["id"])
        for field in ("local_date", "sport"):
            source, record_id = owner(manual, fields, field)
            if source is None:
                continue
            value, status = expected(
                connection,
                activity,
                field,
                source,
                record_id,
                manual,
            )
            if status != "ok":
                continue
            writer.project_activity_field(
                activity["id"],
                field,
                value,
                update_snapshot=source != "manual",
            )


def _diff(
    source: sqlite3.Connection,
    rebuilt: sqlite3.Connection,
) -> RebuildReport:
    columns = sorted(ACTIVITY_COLUMNS)
    select = ", ".join(columns)
    live_rows = {
        row["id"]: row
        for row in source.execute(
            f"SELECT id, {select} FROM activities "
            "WHERE excluded_at IS NULL ORDER BY id"
        )
    }
    rebuilt_rows = {
        row["id"]: row
        for row in rebuilt.execute(
            f"SELECT id, {select} FROM activities "
            "WHERE excluded_at IS NULL ORDER BY id"
        )
    }

    report = RebuildReport(
        source=Path(),
        target=Path(),
        temporary=False,
        overlay=OverlayCounts(),
    )
    report.activities = len(live_rows)
    report.missing = len(set(live_rows) - set(rebuilt_rows))
    report.extra = len(set(rebuilt_rows) - set(live_rows))
    if report.missing:
        report.other.append(
            f"activities missing from the rebuild: {report.missing}"
        )
    if report.extra:
        report.other.append(
            f"activities extra in the rebuild: {report.extra}"
        )

    common = set(live_rows) & set(rebuilt_rows)
    report.values = len(common) * len(columns)
    for activity_id in sorted(common):
        live = live_rows[activity_id]
        rebuilt_row = rebuilt_rows[activity_id]
        for field_name in columns:
            if same(live[field_name], rebuilt_row[field_name]):
                continue
            report.drift += 1
            if len(report.drifts) < MAX_DRIFTS:
                report.drifts.append(
                    f"{activity_id} {field_name}: live="
                    f"{live[field_name]!r} rebuilt="
                    f"{rebuilt_row[field_name]!r}"
                )

    live_excluded = {
        row["id"]
        for row in source.execute(
            "SELECT id FROM activities WHERE excluded_at IS NOT NULL"
        )
    }
    rebuilt_excluded = {
        row["id"]
        for row in rebuilt.execute(
            "SELECT id FROM activities WHERE excluded_at IS NOT NULL"
        )
    }
    report.exclusions_live = len(live_excluded)
    report.exclusions_rebuilt = len(rebuilt_excluded)
    report.exclusions_match = live_excluded == rebuilt_excluded
    if not report.exclusions_match:
        report.other.append(
            "exclusion set differs: "
            f"{len(live_excluded - rebuilt_excluded)} missing, "
            f"{len(rebuilt_excluded - live_excluded)} extra"
        )

    report.raw_files, report.raw_missing = _raw_archive(source)
    if report.raw_missing:
        report.other.append(
            f"raw archive files missing: {report.raw_missing}"
        )

    return report


def _raw_archive(source: sqlite3.Connection) -> tuple[int, int]:
    """Count the FIT archive files the source records point at."""
    total = 0
    missing = 0
    for row in source.execute(
        """
        SELECT raw_path FROM source_records
        WHERE source = 'fit' AND raw_path IS NOT NULL
        """
    ):
        total += 1
        try:
            if not Path(row["raw_path"]).expanduser().is_file():
                missing += 1
        except OSError:
            missing += 1
    return total, missing
