"""Historical ambient weather from the Open-Meteo archive.

Runalyze has no weather here, Intervals' ``has_weather`` is false, and the
sheet stops in 2021. Open-Meteo's archive is the free, keyless historical
source. One request serves every activity in the same rounded coordinate cell
and UTC hour; the response is stored as a ``source_records`` row
(``record_type='weather'``) so a rebuild reproduces the weather without the
network.

The importer never guesses a coordinate: it reads the FIT session's start
position (or re-reads the linked FIT file), and a missing coordinate is a
reported gap.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from hobbyjogging_core import (
    TrainingRepository,
    TrainingWriter,
    default_database_path,
    open_database,
)
from hobbyjogging_core.sources_config import load_sources

from .fit import parse_fit_file

SOURCE = "open-meteo"
RECORD_TYPE = "weather"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "pressure_msl",
    "cloud_cover",
    "weather_code",
    "is_day",
)

# A treadmill or trainer activity has no outdoor weather even when the file
# carries a stale start position.
INDOOR_SPORTS = frozenset(
    {
        "treadmill_run",
        "virtual_run",
        "virtual_ride",
        "training",
        "other",
        "workout",
    }
)


@dataclass(frozen=True)
class WeatherReading:
    """One hour of ambient weather, in canonical metric units."""

    temp_c: float | None = None
    feels_like_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    wind_gust_ms: float | None = None
    wind_degree: float | None = None
    pressure_hpa: float | None = None
    clouds_pct: float | None = None
    condition: str = ""
    is_night: bool | None = None

    @property
    def fields(self) -> dict[str, object]:
        return {
            "temp_c": self.temp_c,
            "feels_like_c": self.feels_like_c,
            "humidity_pct": self.humidity_pct,
            "wind_speed_ms": self.wind_speed_ms,
            "wind_gust_ms": self.wind_gust_ms,
            "wind_degree": self.wind_degree,
            "pressure_hpa": self.pressure_hpa,
            "clouds_pct": self.clouds_pct,
            "condition": self.condition,
            "is_night": self.is_night,
        }


@dataclass
class WeatherSummary:
    start: date
    end: date
    activities: int = 0
    outdoor: int = 0
    missing_start: int = 0
    missing_coordinate: int = 0
    skipped_existing: int = 0
    cached: int = 0
    fetched: int = 0
    would_fetch: int = 0
    written: int = 0
    would_write: int = 0
    no_hour: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class OpenMeteoClient:
    """Small client for the Open-Meteo historical archive."""

    def __init__(self, session=None, timeout: float = 30.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch(
        self,
        latitude: float,
        longitude: float,
        day: date,
    ) -> dict:
        params = {
            "latitude": round(latitude, 2),
            "longitude": round(longitude, 2),
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "hourly": ",".join(HOURLY_FIELDS),
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }
        response = self.session.get(
            ARCHIVE_URL,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


class OpenMeteoImporter:
    """Fetch and store ambient weather for a date range."""

    def __init__(self, connection, *, client=None):
        self.connection = connection
        self.writer = TrainingWriter(connection)
        self.repository = TrainingRepository(connection)
        self.client = client or OpenMeteoClient()
        self._fit_positions: dict[str, dict[int, tuple[float, float]]] = {}

    def import_range(
        self,
        start: date,
        end: date,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        refresh: bool = False,
    ) -> WeatherSummary:
        summary = WeatherSummary(start=start, end=end)
        activities = self.repository.activities(start, end)
        if limit is not None:
            activities = activities[:limit]

        run_id = None
        if not dry_run:
            run_id = self.writer.start_import_run(
                SOURCE,
                {"start": start.isoformat(), "end": end.isoformat()},
            )

        seen_keys: set[str] = set()
        try:
            for activity in activities:
                summary.activities += 1
                if activity.type in INDOOR_SPORTS:
                    continue
                summary.outdoor += 1

                moment = _utc_hour(activity.started_at_utc)
                if moment is None:
                    summary.missing_start += 1
                    continue

                coordinate = self.activity_coordinate(activity.id)
                if coordinate is None:
                    summary.missing_coordinate += 1
                    continue

                if not refresh and self._has_open_meteo(activity.id):
                    summary.skipped_existing += 1
                    continue

                latitude, longitude = coordinate
                key = cache_key(latitude, longitude, moment)
                record = self._cached_record(key)
                if key in seen_keys:
                    if dry_run:
                        continue
                    # The first activity in this run stored the record.
                    record = self._cached_record(key)
                elif record is not None and not refresh:
                    summary.cached += 1
                else:
                    if dry_run:
                        summary.would_fetch += 1
                        seen_keys.add(key)
                        continue
                    try:
                        payload = self.client.fetch(
                            latitude,
                            longitude,
                            moment.date(),
                        )
                    except Exception as exc:  # network and API errors
                        summary.failed += 1
                        summary.errors.append(
                            f"{activity.id}: {_error(exc)}"
                        )
                        continue
                    summary.fetched += 1
                    record_id = self._store_record(key, payload, run_id)
                    record = {"id": record_id, "payload": payload}
                    seen_keys.add(key)

                if record is None:
                    summary.no_hour += 1
                    continue
                reading = _reading(record["payload"], moment)
                if reading is None:
                    summary.no_hour += 1
                    continue
                self._write(
                    activity.id,
                    reading,
                    record["id"],
                    summary,
                    dry_run=dry_run,
                )

            if dry_run:
                self.connection.rollback()
            else:
                self.connection.commit()
                self.writer.finish_import_run(
                    run_id,
                    "ok" if not summary.failed else "partial",
                    records_seen=summary.activities,
                    records_imported=summary.written,
                    records_skipped=summary.skipped_existing,
                )
                self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        return summary

    def activity_coordinate(
        self,
        activity_id: str,
    ) -> tuple[float, float] | None:
        rows = self.connection.execute(
            """
            SELECT sr.source, sr.payload_json
            FROM activity_sources als
            JOIN source_records sr ON sr.id = als.source_record_id
            WHERE als.activity_id = ? AND sr.record_type = 'activity'
            ORDER BY
                CASE sr.source WHEN 'fit' THEN 0 WHEN 'intervals' THEN 1
                     ELSE 2 END,
                sr.id DESC
            """,
            (activity_id,),
        ).fetchall()

        for row in rows:
            payload = _payload(row["payload_json"])
            if payload is None:
                continue
            if row["source"] == "fit":
                return self._fit_coordinate(payload)
            position = _latlng(payload.get("start_latlng"))
            if position is not None:
                return position
        return None

    def _fit_coordinate(self, payload: dict) -> tuple[float, float] | None:
        session = payload.get("session") or {}
        position = _pair(
            session.get("start_latitude"),
            session.get("start_longitude"),
        )
        if position is not None:
            return position

        path = (payload.get("file") or {}).get("path")
        index = session.get("index")
        if not path:
            return None
        positions = self._fit_positions_for(str(path))
        if not positions:
            return None
        if index in positions:
            return positions[index]
        return next(iter(positions.values()), None)

    def _fit_positions_for(
        self,
        path: str,
    ) -> dict[int, tuple[float, float]]:
        if path in self._fit_positions:
            return self._fit_positions[path]
        positions: dict[int, tuple[float, float]] = {}
        try:
            summary = parse_fit_file(Path(path))
        except Exception:
            summary = None
        if summary is not None:
            for session in summary.sessions:
                position = _pair(
                    session.start_latitude,
                    session.start_longitude,
                )
                if position is not None:
                    positions[session.index] = position
        self._fit_positions[path] = positions
        return positions

    def _has_open_meteo(self, activity_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM activity_weather
            WHERE activity_id = ? AND source = ?
            """,
            (activity_id, SOURCE),
        ).fetchone()
        return row is not None

    def _cached_record(self, key: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, payload_json FROM source_records
            WHERE source = ? AND record_type = ? AND external_id = ?
            """,
            (SOURCE, RECORD_TYPE, key),
        ).fetchone()
        if row is None:
            return None
        payload = _payload(row["payload_json"])
        if payload is None:
            return None
        return {"id": row["id"], "payload": payload}

    def _store_record(
        self,
        key: str,
        payload: dict,
        run_id: int | None,
    ) -> int:
        body = json.dumps(payload, sort_keys=True)
        return self.writer.upsert_source_record(
            source=SOURCE,
            record_type=RECORD_TYPE,
            external_id=key,
            checksum=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            import_run_id=run_id,
            payload_json=body,
        )

    def _write(
        self,
        activity_id: str,
        reading: WeatherReading,
        source_record_id: int,
        summary: WeatherSummary,
        *,
        dry_run: bool,
    ) -> None:
        if reading.temp_c is None:
            summary.no_hour += 1
            return
        if not dry_run:
            self.writer.replace_activity_weather(
                activity_id,
                source=SOURCE,
                source_record_id=source_record_id,
                **reading.fields,
            )
            summary.written += 1
        else:
            summary.would_write += 1


def run_weather(args, parser) -> int:
    """CLI entry point for ``hobbyjogging-import weather``."""
    from .cli import resolve_range

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be greater than zero")

    try:
        start, end = resolve_range(args.days, args.start, args.end)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        config = load_sources()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not config.enabled(SOURCE):
        parser.error("open-meteo is disabled in sources.toml")

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    try:
        importer = OpenMeteoImporter(connection)
        summary = importer.import_range(
            start,
            end,
            dry_run=args.dry_run,
            limit=args.limit,
            refresh=args.refresh,
        )
    finally:
        connection.close()

    print(format_weather_summary(summary, dry_run=args.dry_run))
    print(f"Database: {args.database or default_database_path()}")
    return 0


def format_weather_summary(
    summary: WeatherSummary,
    *,
    dry_run: bool = False,
) -> str:
    lines = [
        "Open-Meteo weather",
        f"Range: {summary.start} .. {summary.end}",
        f"Activities: {summary.activities}",
        f"Outdoor: {summary.outdoor}",
        f"Missing start: {summary.missing_start}",
        f"Missing coordinate: {summary.missing_coordinate}",
        f"Skipped existing: {summary.skipped_existing}",
        f"Cached: {summary.cached}",
    ]
    if dry_run:
        lines.append(f"Would fetch: {summary.would_fetch}")
        lines.append(f"Would write: {summary.would_write}")
    else:
        lines.append(f"Fetched: {summary.fetched}")
        lines.append(f"Written: {summary.written}")
    if summary.no_hour:
        lines.append(f"No matching hour: {summary.no_hour}")
    if summary.failed:
        lines.append(f"Failed: {summary.failed}")
        for error in summary.errors[:5]:
            lines.append(f"  {error}")
    if dry_run:
        lines.append("Dry run: no requests or writes.")
    return "\n".join(lines)


def cache_key(
    latitude: float,
    longitude: float,
    moment: datetime,
) -> str:
    return (
        f"{latitude:.2f},{longitude:.2f},"
        f"{moment.strftime('%Y-%m-%dT%H')}"
    )


def _reading(payload: dict, moment: datetime) -> WeatherReading | None:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    target = moment.strftime("%Y-%m-%dT%H:00")
    try:
        index = times.index(target)
    except ValueError:
        return None

    def value(name: str):
        values = hourly.get(name) or []
        return values[index] if index < len(values) else None

    is_day = value("is_day")
    return WeatherReading(
        temp_c=_number(value("temperature_2m")),
        feels_like_c=_number(value("apparent_temperature")),
        humidity_pct=_number(value("relative_humidity_2m")),
        wind_speed_ms=_number(value("wind_speed_10m")),
        wind_gust_ms=_number(value("wind_gusts_10m")),
        wind_degree=_number(value("wind_direction_10m")),
        pressure_hpa=_number(value("pressure_msl")),
        clouds_pct=_number(value("cloud_cover")),
        condition=condition_label(value("weather_code")),
        is_night=(
            None if is_day is None else not bool(is_day)
        ),
    )


def condition_label(code: object) -> str:
    number = _number(code)
    if number is None:
        return ""
    code = int(number)
    if code == 0:
        return "clear"
    if code == 1:
        return "mainly clear"
    if code == 2:
        return "partly cloudy"
    if code == 3:
        return "overcast"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57):
        return "drizzle"
    if code in (61, 63, 65, 66, 67):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (80, 81, 82):
        return "showers"
    if code in (95, 96, 99):
        return "thunderstorm"
    return "unsettled"


def _utc_hour(value: str) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _pair(
    latitude: object,
    longitude: object,
) -> tuple[float, float] | None:
    lat = _number(latitude)
    lon = _number(longitude)
    if lat is None or lon is None:
        return None
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        return None
    if abs(lat) < 1e-6 and abs(lon) < 1e-6:
        return None
    return lat, lon


def _latlng(value: object) -> tuple[float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return _pair(value[0], value[1])
    if isinstance(value, str) and "," in value:
        left, right = value.split(",", 1)
        return _pair(left, right)
    return None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
