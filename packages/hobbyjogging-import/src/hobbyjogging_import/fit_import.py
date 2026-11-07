"""Import FIT files into the canonical database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.db.writer import CONFLICT_FIELDS
from hobbyjogging_core.model import Lap

from .fit import (
    FitFileSummary,
    FitLap,
    FitSession,
    parse_fit_file,
    read_fit_file_id,
)
from .matching import (
    ActivityMatcher,
    MatchCandidate,
    linked_activity,
    parse_utc,
)
from .quality import (
    record_ambiguous_match,
    record_field_conflicts,
    record_quality_findings,
    resolve_agreed_field_conflicts,
)

SOURCE = "fit"


@dataclass
class FitImportAction:
    """A per-session decision made during a FIT import."""

    path: Path
    session_index: int
    action: str
    activity_id: str | None = None
    match_method: str = ""
    confidence: float | None = None
    matches: list[MatchCandidate] = field(default_factory=list)


@dataclass
class FitImportSummary:
    """Results of a FIT import or dry run."""

    run_id: int | None = None
    dry_run: bool = False
    files_seen: int = 0
    files_skipped: int = 0
    files_imported: int = 0
    activities_seen: int = 0
    activities_imported: int = 0
    activities_matched: int = 0
    activities_created: int = 0
    activities_skipped: int = 0
    laps_imported: int = 0
    vo2max_imported: int = 0
    review_recorded: int = 0
    actions: list[FitImportAction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def records_seen(self) -> int:
        return self.activities_seen

    @property
    def records_imported(self) -> int:
        return self.activities_imported

    @property
    def records_skipped(self) -> int:
        return self.activities_skipped


class FitImporter:
    """Read FIT files and merge them into canonical activities."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        matcher: ActivityMatcher | None = None,
    ):
        self.connection = connection
        self.writer = TrainingWriter(connection)
        self.matcher = matcher or ActivityMatcher(connection)

    def import_paths(
        self,
        paths: list[str | Path],
        *,
        recursive: bool = False,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        skip_known: bool = False,
    ) -> FitImportSummary:
        discovered = discover_fit_files(paths, recursive=recursive)
        summary = FitImportSummary(
            dry_run=dry_run,
            files_seen=len(discovered),
        )
        known_paths = self._known_fit_paths() if skip_known else set()

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "paths": [str(path) for path in paths],
                    "recursive": recursive,
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                    "limit": limit,
                    "skip_known": skip_known,
                },
            )

        try:
            activity_files = self._prefilter(
                discovered,
                summary,
                limit,
                skip_known=skip_known,
                known_paths=known_paths,
            )

            if dry_run:
                for path in activity_files:
                    self._import_file(
                        path,
                        summary,
                        start,
                        end,
                        dry_run=True,
                        skip_known=skip_known,
                        known_paths=known_paths,
                    )
            else:
                with self.connection:
                    for path in activity_files:
                        self._import_file(
                            path,
                            summary,
                            start,
                            end,
                            dry_run=False,
                            skip_known=skip_known,
                            known_paths=known_paths,
                        )

                self.writer.finish_import_run(
                    summary.run_id,
                    "success",
                    records_seen=summary.records_seen,
                    records_imported=summary.records_imported,
                    records_skipped=summary.records_skipped,
                )

            return summary

        except Exception as exc:
            self.connection.rollback()
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.records_seen,
                    records_imported=summary.records_imported,
                    records_skipped=summary.records_skipped,
                    error=str(exc),
                )
            raise

    def _prefilter(
        self,
        paths: list[Path],
        summary: FitImportSummary,
        limit: int | None,
        *,
        skip_known: bool = False,
        known_paths: set[str] | None = None,
    ) -> list[Path]:
        if limit is not None and limit <= 0:
            return []

        activity_files: list[Path] = []

        for path in paths:
            if (
                skip_known
                and known_paths
                and _path_known(path, known_paths)
            ):
                summary.files_skipped += 1
                continue

            try:
                file_id = read_fit_file_id(path)
            except Exception as exc:
                summary.files_skipped += 1
                summary.errors.append(f"{path}: {exc}")
                continue

            if str(file_id.get("type") or "") != "activity":
                summary.files_skipped += 1
                continue

            activity_files.append(path)

            if limit is not None and len(activity_files) >= limit:
                break

        return activity_files

    def _known_fit_paths(self) -> set[str]:
        rows = self.connection.execute(
            """
            SELECT raw_path FROM source_records
            WHERE source = ? AND raw_path IS NOT NULL
            """,
            (SOURCE,),
        ).fetchall()
        return {str(row["raw_path"]) for row in rows}

    def _import_file(
        self,
        path: Path,
        summary: FitImportSummary,
        start: date | None,
        end: date | None,
        *,
        dry_run: bool,
        skip_known: bool = False,
        known_paths: set[str] | None = None,
    ) -> None:
        if (
            skip_known
            and known_paths
            and _path_known(path, known_paths)
        ):
            summary.files_skipped += 1
            return

        try:
            fit_summary = parse_fit_file(path)
        except Exception as exc:
            summary.files_skipped += 1
            summary.errors.append(f"{path}: {exc}")
            return

        if not fit_summary.sessions:
            summary.files_skipped += 1
            return

        checksum = _file_checksum(path)
        imported_any = False

        for session in fit_summary.sessions:
            local_date = _session_local_date(session)

            if local_date is None or not session.start_time_utc:
                summary.activities_skipped += 1
                summary.actions.append(
                    FitImportAction(
                        path=path,
                        session_index=session.index,
                        action="skip",
                        match_method="missing_start",
                    )
                )
                continue

            if (
                (start is not None and local_date < start)
                or (end is not None and local_date > end)
            ):
                summary.activities_skipped += 1
                summary.actions.append(
                    FitImportAction(
                        path=path,
                        session_index=session.index,
                        action="skip",
                        match_method="outside_date_range",
                    )
                )
                continue

            summary.activities_seen += 1

            if self._import_session(
                path,
                fit_summary,
                session,
                summary,
                checksum,
                dry_run=dry_run,
            ):
                imported_any = True

        if imported_any:
            summary.files_imported += 1

    def _import_session(
        self,
        path: Path,
        fit_summary: FitFileSummary,
        session: FitSession,
        summary: FitImportSummary,
        checksum: str,
        *,
        dry_run: bool,
    ) -> bool:
        external_id = _session_external_id(checksum, session)
        source_record_id: int | None = None
        existing_link = None

        if self.writer.is_source_record_excluded(
            source=SOURCE,
            record_type="activity",
            external_id=external_id,
        ):
            summary.activities_skipped += 1
            summary.actions.append(
                FitImportAction(
                    path=path,
                    session_index=session.index,
                    action="skip",
                    match_method="excluded",
                )
            )
            return False

        if not dry_run:
            source_record_id = self.writer.upsert_source_record(
                source=SOURCE,
                record_type="activity",
                external_id=external_id,
                checksum=checksum,
                payload_json=_session_payload(path, fit_summary, session),
                raw_path=str(path),
                import_run_id=summary.run_id,
            )
            existing_link = linked_activity(
                self.connection,
                source_record_id,
            )

        if existing_link is not None:
            activity_id = existing_link["activity_id"]
            match_method = existing_link["match_method"] or "external_id"
            confidence = existing_link["confidence"]
            if self.writer.is_activity_excluded(activity_id):
                summary.activities_skipped += 1
                summary.actions.append(
                    FitImportAction(
                        path=path,
                        session_index=session.index,
                        action="skip",
                        match_method="excluded",
                    )
                )
                return False
            summary.activities_matched += 1
        else:
            matches = self.matcher.find(
                started_at_utc=session.start_time_utc,
                source=SOURCE,
                elapsed_s=session.elapsed_s,
                duration_s=session.duration_s,
            )

            if len(matches) > 1:
                summary.activities_skipped += 1
                if source_record_id is not None:
                    summary.review_recorded += record_ambiguous_match(
                        self.writer,
                        source_record_id=source_record_id,
                        external_id=external_id,
                        candidates=matches,
                        import_run_id=summary.run_id,
                    )
                summary.actions.append(
                    FitImportAction(
                        path=path,
                        session_index=session.index,
                        action="ambiguous",
                        matches=matches,
                    )
                )
                return False

            if matches:
                match = matches[0]
                activity_id = match.activity_id
                match_method = match.match_method
                confidence = match.confidence
                summary.activities_matched += 1
            else:
                activity_id = _stable_activity_id(external_id)
                match_method = "created"
                confidence = None
                summary.activities_created += 1

        if dry_run:
            summary.activities_imported += 1
            if session.vo2max_garmin is not None:
                summary.vo2max_imported += 1
            summary.laps_imported += len(session.laps)
            summary.actions.append(
                FitImportAction(
                    path=path,
                    session_index=session.index,
                    action="create" if match_method == "created" else "match",
                    activity_id=activity_id,
                    match_method=match_method,
                    confidence=confidence,
                )
            )
            return True

        if source_record_id is None:
            raise RuntimeError("FIT source record was not created")

        values = _activity_values(session)
        conflicts = self.writer.upsert_activity(
            activity_id,
            values,
            source=SOURCE,
            source_record_id=source_record_id,
        )
        summary.review_recorded += record_field_conflicts(
            self.writer,
            activity_id=activity_id,
            source_record_id=source_record_id,
            import_run_id=summary.run_id,
            conflicts=conflicts,
        )
        resolve_agreed_field_conflicts(
            self.writer,
            activity_id=activity_id,
            fields=(
                (set(values) & CONFLICT_FIELDS)
                - {conflict.field_name for conflict in conflicts}
            ),
        )
        self.writer.link_activity_source(
            activity_id,
            source_record_id,
            match_method=match_method,
            confidence=confidence,
        )
        laps = [_to_lap(lap) for lap in session.laps]
        self.writer.merge_activity_laps(
            activity_id,
            laps,
            source_record_id=source_record_id,
        )

        summary.review_recorded += record_quality_findings(
            self.writer,
            activity_id=activity_id,
            source_record_id=source_record_id,
            import_run_id=summary.run_id,
            sport=str(values.get("sport") or ""),
            duration_s=float(values.get("duration_s") or 0),
            elapsed_s=float(values.get("elapsed_s") or 0),
            distance_m=float(values.get("distance_m") or 0),
            moving_s=(
                float(values["moving_s"])
                if values.get("moving_s") is not None
                else None
            ),
        )

        summary.activities_imported += 1
        if session.vo2max_garmin is not None:
            summary.vo2max_imported += 1
        summary.laps_imported += len(laps)
        summary.actions.append(
            FitImportAction(
                path=path,
                session_index=session.index,
                action="create" if match_method == "created" else "match",
                activity_id=activity_id,
                match_method=match_method,
                confidence=confidence,
            )
        )
        return True


def discover_fit_files(
    paths: list[str | Path],
    *,
    recursive: bool = False,
) -> list[Path]:
    """Expand files and directories into a sorted, de-duplicated FIT list."""
    discovered: list[Path] = []
    seen: set[Path] = set()

    for value in paths:
        path = Path(value).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"FIT path not found: {path}")

        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            candidates = (
                path.rglob("*") if recursive else path.glob("*")
            )
        else:
            candidates = []

        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() != ".fit":
                continue

            resolved = candidate.resolve()
            if resolved in seen:
                continue

            seen.add(resolved)
            discovered.append(candidate)

    return sorted(discovered, key=lambda path: str(path))


def _activity_values(session: FitSession) -> dict[str, object]:
    local_date = _session_local_date(session)
    if local_date is None:
        raise ValueError("FIT session has no local date")

    values: dict[str, object] = {
        "local_date": local_date.isoformat(),
        "started_at_utc": session.start_time_utc,
        "sport": session.canonical_sport,
        "name": session.name,
        "duration_s": session.duration_s,
        "elapsed_s": session.elapsed_s,
        "distance_m": session.distance_m,
    }

    optional = {
        "tz_offset_min": session.tz_offset_min,
        "sub_sport": (
            session.sub_sport
            if session.sub_sport and session.sub_sport != "generic"
            else None
        ),
        "moving_s": session.moving_s,
        "avg_hr": session.avg_hr,
        "vo2max_garmin": session.vo2max_garmin,
    }
    values.update(
        {
            key: value
            for key, value in optional.items()
            if value is not None
        }
    )
    return values


def _to_lap(lap: FitLap) -> Lap:
    return Lap(
        index=lap.index,
        start_time_utc=lap.start_time_utc,
        duration_s=lap.duration_s,
        distance_m=lap.distance_m,
        avg_hr=lap.avg_hr,
        max_hr=lap.max_hr,
        elevation_gain_m=lap.elevation_gain_m,
    )


def _session_local_date(session: FitSession) -> date | None:
    if len(session.local_start) >= 10:
        try:
            return date.fromisoformat(session.local_start[:10])
        except ValueError:
            pass

    start = parse_utc(session.start_time_utc)
    return start.date() if start else None


def _session_external_id(checksum: str, session: FitSession) -> str:
    return f"{checksum}:{session.index}"


def _stable_activity_id(external_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"hobbyjogging:fit:activity:{external_id}",
        )
    )


def _session_payload(
    path: Path,
    fit_summary: FitFileSummary,
    session: FitSession,
) -> str:
    return json.dumps(
        {
            "file": {
                "path": str(path),
                "file_type": fit_summary.file_type,
                "manufacturer": fit_summary.manufacturer,
                "product": fit_summary.product,
                "serial_number": fit_summary.serial_number,
                "time_created": fit_summary.time_created,
                "record_count": fit_summary.record_count,
            },
            "session": asdict(session),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _path_known(path: Path, known_paths: set[str]) -> bool:
    """True when this exact file path was already imported."""
    if str(path) in known_paths:
        return True
    try:
        return str(path.resolve()) in known_paths
    except OSError:
        return False


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()
