"""Read a Strava bulk export (activities.csv, bikes.csv, shoes.csv).

The export is a ZIP or an extracted directory. Only the manifest and the two
gear files are read: the activity files duplicate the FIT archive, and the
social layer is the point of this source.

Column names are not stable across export versions or account languages, so
the reader looks headers up through aliases and fails with a useful message
when a required column is missing.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

STRAVA_URL = "https://www.strava.com/activities/{external_id}"

_ACTIVITY_ID = ("Activity ID", "Aktivitäts-ID", "Aktivitaets-ID")
_ACTIVITY_DATE = ("Activity Date", "Aktivitätsdatum", "Aktivitaetsdatum")
_ACTIVITY_NAME = ("Activity Name", "Aktivitätsname", "Aktivitaetsname")
_ACTIVITY_TYPE = ("Activity Type", "Aktivitätstyp", "Aktivitaetstyp")
_ACTIVITY_DESCRIPTION = (
    "Activity Description",
    "Aktivitätsbeschreibung",
    "Aktivitaetsbeschreibung",
)
_ELAPSED = ("Elapsed Time", "Verstrichene Zeit")
_MOVING = ("Moving Time", "Bewegungszeit")
_AVG_HR = ("Average Heart Rate", "Durchschnittliche Herzfrequenz")
_MAX_HR = ("Max Heart Rate", "Maximale Herzfrequenz")
_ELEVATION = ("Elevation Gain", "Höhenmeter")
_GEAR = ("Activity Gear", "Gear", "Ausrüstung")
_FILENAME = ("Filename", "Dateiname")
_PRIVATE = ("Private", "Privat")
_COMMUTE = ("Commute", "Pendeln")

_BIKE_NAME = ("Bike Name", "Fahrradname")
_BIKE_BRAND = ("Bike Brand", "Fahrradmarke")
_BIKE_MODEL = ("Bike Model", "Fahrradmodell")
_SHOE_NAME = ("Shoe Name", "Schuhname")
_SHOE_BRAND = ("Shoe Brand", "Schuhmarke")
_SHOE_MODEL = ("Shoe Model", "Schuhmodell")

_DATE_FORMATS = (
    "%b %d, %Y, %I:%M:%S %p",
    "%b %d, %Y %I:%M:%S %p",
    "%d.%m.%Y, %H:%M:%S",
    "%d.%m.%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%d.%m.%Y",
)


@dataclass(frozen=True)
class StravaActivity:
    external_id: str
    started_at_local: datetime | None
    name: str = ""
    sport: str = ""
    description: str = ""
    elapsed_s: float = 0
    moving_s: float = 0
    distance_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    gear: str = ""
    filename: str = ""
    private: bool = False
    commute: bool = False

    @property
    def local_date(self) -> str | None:
        if self.started_at_local is None:
            return None
        return self.started_at_local.date().isoformat()

    @property
    def url(self) -> str:
        return STRAVA_URL.format(external_id=self.external_id)


@dataclass(frozen=True)
class StravaGear:
    external_id: str
    type: str
    name: str
    brand: str = ""
    model: str = ""


@dataclass
class StravaExport:
    activities: list[StravaActivity] = field(default_factory=list)
    gear: list[StravaGear] = field(default_factory=list)


def read_export(path: str | Path, *, distance_unit: str = "km") -> StravaExport:
    """Read a Strava export ZIP or directory."""
    if distance_unit not in ("km", "m"):
        raise ValueError("distance_unit must be 'km' or 'm'")

    path = Path(path)
    if path.is_dir():
        activities_csv = path / "activities.csv"
        if not activities_csv.is_file():
            raise ValueError(f"activities.csv not found in {path}")
        text = activities_csv.read_text(encoding="utf-8-sig")
        gear_files = {
            "bike": _read_optional(path / "bikes.csv"),
            "shoe": _read_optional(path / "shoes.csv"),
        }
    elif path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            activities_csv = _member(archive, "activities.csv")
            if activities_csv is None:
                raise ValueError(f"activities.csv not found in {path}")
            text = _read_member(archive, activities_csv)
            gear_files = {
                "bike": _read_optional_member(archive, "bikes.csv"),
                "shoe": _read_optional_member(archive, "shoes.csv"),
            }
    else:
        raise ValueError(f"not a Strava export ZIP or directory: {path}")

    activities = _parse_activities(text, distance_unit=distance_unit)
    gear = []
    for kind, rows in gear_files.items():
        if rows:
            gear.extend(_parse_gear(rows, kind))
    return StravaExport(activities=activities, gear=gear)


def _parse_activities(text: str, *, distance_unit: str) -> list[StravaActivity]:
    header, values_list = _csv(text)
    first = _first_index(header)
    distance_columns = [
        index
        for index, name in enumerate(header)
        if _header(name) == _header("Distance")
    ]

    rows = []
    for values in values_list:
        raw = _row_map(values, first)
        external_id = _pick(raw, _ACTIVITY_ID).strip()
        if not external_id:
            continue

        elapsed = _float(_pick(raw, _ELAPSED)) or 0.0
        moving = _float(_pick(raw, _MOVING)) or elapsed
        distance = _distance_m_from_columns(
            values,
            distance_columns,
            distance_unit,
        )
        avg_hr = _float(_pick(raw, _AVG_HR))
        max_hr = _float(_pick(raw, _MAX_HR))
        elevation = _float(_pick(raw, _ELEVATION))

        rows.append(
            StravaActivity(
                external_id=external_id,
                started_at_local=_date(_pick(raw, _ACTIVITY_DATE)),
                name=_pick(raw, _ACTIVITY_NAME).strip(),
                sport=_pick(raw, _ACTIVITY_TYPE).strip(),
                description=_pick(raw, _ACTIVITY_DESCRIPTION).strip(),
                elapsed_s=elapsed,
                moving_s=moving,
                distance_m=distance,
                avg_hr=avg_hr,
                max_hr=max_hr,
                elevation_gain_m=elevation,
                gear=_pick(raw, _GEAR).strip(),
                filename=_pick(raw, _FILENAME).strip(),
                private=_bool(_pick(raw, _PRIVATE)),
                commute=_bool(_pick(raw, _COMMUTE)),
            )
        )
    return rows


def _parse_gear(rows: str, kind: str) -> list[StravaGear]:
    name_headers = _BIKE_NAME if kind == "bike" else _SHOE_NAME
    brand_headers = _BIKE_BRAND if kind == "bike" else _SHOE_BRAND
    model_headers = _BIKE_MODEL if kind == "bike" else _SHOE_MODEL

    gear = []
    for raw in _rows(rows):
        name = _pick(raw, name_headers).strip()
        if not name:
            continue
        gear.append(
            StravaGear(
                external_id=gear_key(name),
                type=kind,
                name=name,
                brand=_pick(raw, brand_headers).strip(),
                model=_pick(raw, model_headers).strip(),
            )
        )
    return gear


def gear_key(name: str) -> str:
    """Stable CSV gear identity: the normalized display name.

    The export has no gear id in bikes.csv/shoes.csv, so the name is the
    identity. An API import later can attach the real id as a second source
    link without rewriting the equipment row.
    """
    return "name:" + re.sub(r"\s+", " ", name.strip().casefold())


def gear_slug(name: str) -> str:
    """A readable equipment-id suffix for a CSV gear name."""
    normalized = gear_key(name).split(":", 1)[1]
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "gear"


def gear_ref_key(value: str) -> str:
    """Normalize a gear reference from activities.csv."""
    value = value.strip()
    return gear_key(value) if value else ""


def _csv(text: str) -> tuple[list[str], list[list[str]]]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    return header, list(reader)


def _first_index(header: list[str]) -> dict[str, int]:
    """Header name -> first column, so duplicate columns do not overwrite."""
    first: dict[str, int] = {}
    for index, name in enumerate(header):
        first.setdefault(name, index)
    return first


def _row_map(values: list[str], first: dict[str, int]) -> dict[str, str]:
    return {
        name: values[index] if index < len(values) else ""
        for name, index in first.items()
    }


def _rows(text: str) -> list[dict[str, str]]:
    """Parse a CSV with first-occurrence header semantics (for gear files)."""
    header, values_list = _csv(text)
    first = _first_index(header)
    return [_row_map(values, first) for values in values_list]


def _distance_m_from_columns(
    values: list[str],
    columns: list[int],
    unit: str,
) -> float | None:
    """Read the distance, preferring the wide export's metres column.

    The 2026 export repeats ``Distance``: the first copy is the display unit
    (km for runs and rides, metres for swims and rowing) and the second is
    always metres. A single-column export uses ``--distance-unit``.
    """
    if len(columns) > 1:
        index = columns[1]
        metres = _float(values[index]) if index < len(values) else None
        if metres is not None:
            return metres

    if not columns:
        return None
    index = columns[0]
    return _distance_m(values[index] if index < len(values) else "", unit)


def _pick(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        for header, value in row.items():
            if header is not None and _header(header) == _header(alias):
                return value or ""
    return ""


def _header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().casefold())


def _date(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _distance_m(value: str, unit: str) -> float | None:
    number = _float(value)
    if number is None:
        return None
    return number * 1000.0 if unit == "km" else number


def _bool(value: str) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "ja"}


def _member(archive: zipfile.ZipFile, name: str) -> str | None:
    for member in archive.namelist():
        if member.rsplit("/", 1)[-1] == name:
            return member
    return None


def _read_member(archive: zipfile.ZipFile, member: str) -> str:
    with archive.open(member) as handle:
        return handle.read().decode("utf-8-sig")


def _read_optional_member(archive: zipfile.ZipFile, name: str) -> str | None:
    member = _member(archive, name)
    return _read_member(archive, member) if member else None


def _read_optional(path: Path) -> str | None:
    return path.read_text(encoding="utf-8-sig") if path.is_file() else None


def payload_json(
    activity: StravaActivity,
    *,
    started_at_utc: str | None = None,
    tz_offset_min: int | None = None,
) -> str:
    """The source-record payload: the fields the manifest actually carries."""
    return json.dumps(
        {
            "external_id": activity.external_id,
            "date": (
                activity.started_at_local.isoformat()
                if activity.started_at_local
                else None
            ),
            "started_at_utc": started_at_utc,
            "tz_offset_min": tz_offset_min,
            "name": activity.name,
            "sport": activity.sport,
            "description": activity.description,
            "elapsed_s": activity.elapsed_s,
            "moving_s": activity.moving_s,
            "distance_m": activity.distance_m,
            "avg_hr": activity.avg_hr,
            "max_hr": activity.max_hr,
            "elevation_gain_m": activity.elevation_gain_m,
            "gear": activity.gear,
            "filename": activity.filename,
            "private": activity.private,
            "commute": activity.commute,
        },
        sort_keys=True,
    )
