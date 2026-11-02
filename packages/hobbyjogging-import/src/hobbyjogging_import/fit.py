"""FIT file parsing and inspection.

This module is the only place that knows raw FIT field names. It produces
small, normalized summaries that can later be mapped to canonical activities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import fitdecode


SPORT_ALIASES = {
    "running": "run",
    "trail_running": "trail_run",
    "cycling": "ride",
    "walking": "walk",
    "hiking": "hike",
    "swimming": "swim",
    "rowing": "row",
    "stand_up_paddleboarding": "sup",
}

SPORT_LABELS = {
    "run": "Run",
    "trail_run": "Trail Run",
    "ride": "Ride",
    "walk": "Walk",
    "hike": "Hike",
    "swim": "Swim",
    "row": "Row",
    "sup": "SUP",
}

RUN_SPORTS = {"run", "trail_run"}


@dataclass
class FitLap:
    """A FIT lap summary."""

    index: int
    start_time_utc: str
    duration_s: float
    distance_m: float
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None


@dataclass
class FitSession:
    """A normalized FIT session."""

    index: int
    start_time_utc: str
    local_start: str
    tz_offset_min: int | None
    sport: str
    sub_sport: str
    canonical_sport: str
    name: str
    elapsed_s: float
    duration_s: float
    distance_m: float
    avg_hr: float | None = None
    max_hr: float | None = None
    ascent_m: float | None = None
    calories: float | None = None
    laps: list[FitLap] = field(default_factory=list)


@dataclass
class FitFileSummary:
    """A normalized FIT file and its activity sessions."""

    path: Path
    file_type: str
    manufacturer: str
    product: str
    serial_number: str
    time_created: str
    record_count: int = 0
    sessions: list[FitSession] = field(default_factory=list)


def canonical_sport(sport: object, sub_sport: object = None) -> str:
    """Map a FIT sport/sub-sport pair to the canonical sport name."""
    raw_sport = str(sport or "").strip().lower()
    raw_sub = str(sub_sport or "").strip().lower()

    if raw_sport == "running" and raw_sub in {"trail", "trail_running"}:
        return "trail_run"

    return SPORT_ALIASES.get(raw_sport, raw_sport)


def parse_fit_file(path: str | Path) -> FitFileSummary:
    """Parse a FIT file into a compact summary without writing anything."""
    file_path = Path(path).expanduser()

    file_id: dict[str, Any] = {}
    activity: dict[str, Any] = {}
    sessions: list[dict[str, Any]] = []
    laps: list[dict[str, Any]] = []
    record_count = 0

    with fitdecode.FitReader(str(file_path)) as fit:
        for frame in fit:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue

            values = {field.name: field.value for field in frame.fields}

            if frame.name == "file_id":
                file_id = values
            elif frame.name == "activity":
                activity = values
            elif frame.name == "session":
                sessions.append(values)
            elif frame.name == "lap":
                laps.append(values)
            elif frame.name == "record":
                record_count += 1

    return summarize_fit_messages(
        file_path,
        file_id,
        activity,
        sessions,
        laps,
        record_count=record_count,
    )


def summarize_fit_messages(
    path: str | Path,
    file_id: dict[str, Any],
    activity: dict[str, Any],
    sessions: list[dict[str, Any]],
    laps: list[dict[str, Any]],
    *,
    record_count: int = 0,
) -> FitFileSummary:
    """Build normalized summaries from decoded FIT messages."""
    tz_offset = _tz_offset_min(activity)

    summary = FitFileSummary(
        path=Path(path),
        file_type=str(file_id.get("type") or ""),
        manufacturer=str(file_id.get("manufacturer") or ""),
        product=str(
            file_id.get("garmin_product")
            or file_id.get("product")
            or ""
        ),
        serial_number=str(file_id.get("serial_number") or ""),
        time_created=_iso_utc(file_id.get("time_created")),
        record_count=record_count,
    )

    for index, session in enumerate(sessions, start=1):
        start = _as_datetime(session.get("start_time"))
        if start is None:
            continue

        first_lap = _int(session.get("first_lap_index"), default=0)
        lap_count = _int(session.get("num_laps"), default=0)

        if lap_count:
            session_laps = laps[first_lap:first_lap + lap_count]
        elif len(sessions) == 1:
            session_laps = laps
        else:
            session_laps = []

        sport = str(session.get("sport") or "")
        sub_sport = str(session.get("sub_sport") or "")
        canonical = canonical_sport(sport, sub_sport)
        profile_name = str(session.get("sport_profile_name") or "").strip()

        summary.sessions.append(
            FitSession(
                index=index,
                start_time_utc=_iso_utc(start),
                local_start=_local_start(start, tz_offset),
                tz_offset_min=tz_offset,
                sport=sport,
                sub_sport=sub_sport,
                canonical_sport=canonical,
                name=profile_name or SPORT_LABELS.get(
                    canonical,
                    canonical.replace("_", " ").title(),
                ),
                elapsed_s=_number(session.get("total_elapsed_time")) or 0.0,
                duration_s=_number(session.get("total_timer_time")) or 0.0,
                distance_m=_number(session.get("total_distance")) or 0.0,
                avg_hr=_number(session.get("avg_heart_rate")),
                max_hr=_number(session.get("max_heart_rate")),
                ascent_m=_number(session.get("total_ascent")),
                calories=_number(session.get("total_calories")),
                laps=[
                    _lap_from_message(lap, lap_index)
                    for lap_index, lap in enumerate(
                        session_laps,
                        start=first_lap + 1,
                    )
                ],
            )
        )

    return summary


def fit_file_to_dict(summary: FitFileSummary) -> dict[str, Any]:
    """Return a JSON-serializable representation of a FIT summary."""
    return {
        "path": str(summary.path),
        "file_type": summary.file_type,
        "manufacturer": summary.manufacturer,
        "product": summary.product,
        "serial_number": summary.serial_number,
        "time_created": summary.time_created,
        "record_count": summary.record_count,
        "sessions": [asdict(session) for session in summary.sessions],
    }


def format_fit_file(summary: FitFileSummary) -> str:
    """Format a FIT summary for terminal inspection."""
    lines = [
        f"FIT file: {summary.path}",
        f"Type: {summary.file_type or '-'}",
        f"Device: {_device_label(summary)}",
    ]

    if summary.time_created:
        lines.append(f"Created: {summary.time_created}")

    lines.append(f"Records: {summary.record_count}")

    if not summary.sessions:
        lines.append("")
        lines.append("No activity session found.")
        return "\n".join(lines)

    multiple = len(summary.sessions) > 1

    for session in summary.sessions:
        lines.append("")
        if multiple:
            lines.append(
                f"Session {session.index}/{len(summary.sessions)}"
            )

        lines.extend(
            [
                f"Sport: {session.sport or '-'}"
                f" / {session.sub_sport or '-'}"
                f" -> {session.canonical_sport or '-'}",
                f"Name: {session.name}",
                f"Start: {session.start_time_utc}",
                f"Local start: {session.local_start or '-'}",
                f"Elapsed: {format_duration(session.elapsed_s)}",
                f"Moving: {format_duration(session.duration_s)}",
                f"Distance: {session.distance_m / 1000:.2f} km",
            ]
        )

        if session.canonical_sport in RUN_SPORTS:
            lines.append(
                f"Pace: {format_pace(session.duration_s, session.distance_m)}"
            )

        if session.avg_hr is not None or session.max_hr is not None:
            lines.append(
                f"HR: {_fmt_number(session.avg_hr)} avg, "
                f"{_fmt_number(session.max_hr)} max"
            )

        if session.ascent_m is not None:
            lines.append(f"Ascent: {_fmt_number(session.ascent_m)} m")

        if session.calories is not None:
            lines.append(f"Calories: {_fmt_number(session.calories)}")

        lines.append(f"Laps: {len(session.laps)}")

        if session.laps:
            lines.extend(
                _format_laps(session.laps, session.canonical_sport)
            )

    return "\n".join(lines)


def _lap_from_message(lap: dict[str, Any], index: int) -> FitLap:
    return FitLap(
        index=index,
        start_time_utc=_iso_utc(lap.get("start_time")),
        duration_s=_number(lap.get("total_timer_time")) or 0.0,
        distance_m=_number(lap.get("total_distance")) or 0.0,
        avg_hr=_number(lap.get("avg_heart_rate")),
        max_hr=_number(lap.get("max_heart_rate")),
        elevation_gain_m=_number(lap.get("total_ascent")),
    )


def _format_laps(laps: list[FitLap], sport: str) -> list[str]:
    is_run = sport in RUN_SPORTS
    pace_label = "Pace" if is_run else "Speed"

    lines = [
        f"  #  Start                      Duration  Distance  {pace_label:<9}  "
        "AvgHR  MaxHR  Ascent"
    ]

    for lap in laps:
        pace = (
            format_pace(lap.duration_s, lap.distance_m)
            if is_run
            else format_speed(lap.duration_s, lap.distance_m)
        )
        lines.append(
            f"  {lap.index:>2}  {lap.start_time_utc:<24}  "
            f"{format_duration(lap.duration_s):>8}  "
            f"{lap.distance_m / 1000:>7.2f}km  "
            f"{pace:>9}  "
            f"{_fmt_number(lap.avg_hr):>5}  "
            f"{_fmt_number(lap.max_hr):>5}  "
            f"{_fmt_number(lap.elevation_gain_m):>5}m"
        )

    return lines


def format_duration(seconds: float) -> str:
    """Format seconds as ``H:MM:SS`` or ``M:SS``."""
    total = int(round(seconds or 0))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


def format_pace(duration_s: float, distance_m: float) -> str:
    """Format pace as ``M:SS/km``."""
    if not duration_s or not distance_m:
        return "-"

    seconds_per_km = duration_s / (distance_m / 1000)
    total = int(round(seconds_per_km))
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}/km"


def format_speed(duration_s: float, distance_m: float) -> str:
    """Format speed as ``KM/H``."""
    if not duration_s or not distance_m:
        return "-"

    speed_kmh = (distance_m / 1000) / (duration_s / 3600)
    return f"{speed_kmh:.1f} km/h"


def _device_label(summary: FitFileSummary) -> str:
    parts = [
        value
        for value in (
            summary.manufacturer.title(),
            str(summary.product).replace("_", " ").title(),
        )
        if value
    ]
    label = " ".join(parts) or "-"

    if summary.serial_number:
        label += f" (serial {summary.serial_number})"

    return label


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    return None


def _iso_utc(value: object) -> str:
    moment = _as_datetime(value)
    if moment is None:
        return ""

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _local_start(start: datetime, offset_min: int | None) -> str:
    if offset_min is None:
        return ""

    local = (start + timedelta(minutes=offset_min)).replace(tzinfo=None)
    sign = "+" if offset_min >= 0 else "-"
    hours, minutes = divmod(abs(offset_min), 60)
    return (
        f"{local.isoformat(timespec='seconds')}"
        f"{sign}{hours:02d}:{minutes:02d}"
    )


def _tz_offset_min(activity: dict[str, Any]) -> int | None:
    timestamp = _as_datetime(activity.get("timestamp"))
    local_timestamp = _as_datetime(activity.get("local_timestamp"))

    if timestamp is None or local_timestamp is None:
        return None

    return int(round((local_timestamp - timestamp).total_seconds() / 60))


def _number(value: object) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: object, *, default: int) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _fmt_number(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"
