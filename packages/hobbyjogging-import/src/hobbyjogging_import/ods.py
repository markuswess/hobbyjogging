"""Minimal OpenDocument Spreadsheet reader.

Only the standard library is used (``zipfile`` + ``xml.etree``). The reader
returns typed cell values with cell positions preserved: missing cells and
covered (merged) cells become ``None``, repeated rows and columns are
expanded, and LibreOffice's trailing padding is dropped.

Value types:

- ``float``, ``percentage``, ``currency`` → ``float``
- ``date`` → ``date`` (or ``datetime`` when a time is attached)
- ``time`` → ``timedelta`` (ODS stores ISO durations, not clock strings)
- ``boolean`` → ``bool``
- ``string`` → ``str``
- anything else → ``None``
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"

# LibreOffice pads sheets to roughly one million rows. Expansions are capped so
# a padded sheet cannot exhaust memory.
MAX_ROWS = 200_000
MAX_COLUMNS = 1_024

_CONTENT_XML = "content.xml"

_DURATION_RE = re.compile(
    r"^(?P<sign>[+-])?P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?$"
)


class OdsError(ValueError):
    """Raised when a file is not a readable ODS workbook."""


@dataclass
class Sheet:
    """One worksheet: rows of typed values, positions preserved."""

    name: str
    rows: list[list[object]]

    def header_index(self, required: tuple[str, ...]) -> int:
        """Return the first row containing every required header."""
        for index, row in enumerate(self.rows[:20]):
            present = {value for value in row if isinstance(value, str)}
            if all(name in present for name in required):
                return index
        raise OdsError(
            f"sheet {self.name!r} has no header with {', '.join(required)}"
        )


def sheet_names(path: str | Path) -> list[str]:
    """Return the table names in workbook order."""
    return [sheet.name for sheet in read_sheets(path)]


def read_sheet(path: str | Path, name: str) -> Sheet:
    """Read one worksheet by name."""
    for sheet in read_sheets(path):
        if sheet.name == name:
            return sheet
    raise OdsError(f"sheet {name!r} not found in {path}")


def read_sheets(path: str | Path) -> list[Sheet]:
    """Read every worksheet in a workbook."""
    try:
        with zipfile.ZipFile(path) as archive:
            content = archive.read(_CONTENT_XML)
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise OdsError(f"{path} is not a readable ODS workbook") from exc

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise OdsError(f"{path} has unreadable {_CONTENT_XML}") from exc

    spreadsheet = root.find(
        f".//{{{OFFICE_NS}}}spreadsheet"
    )
    if spreadsheet is None:
        return []

    return [
        Sheet(name=name, rows=_sheet_rows(table))
        for table in spreadsheet.findall(f"{{{TABLE_NS}}}table")
        if (name := table.get(_attr(TABLE_NS, "name"))) is not None
    ]


def parse_duration(text: str) -> timedelta:
    """Parse an ISO 8601 duration as used by ODS time cells."""
    match = _DURATION_RE.match(text.strip())
    if match is None or not any(
        match.group(part)
        for part in ("days", "hours", "minutes", "seconds")
    ):
        raise OdsError(f"invalid ODS duration: {text!r}")

    value = timedelta(
        days=float(match.group("days") or 0),
        hours=float(match.group("hours") or 0),
        minutes=float(match.group("minutes") or 0),
        seconds=float(match.group("seconds") or 0),
    )
    return -value if match.group("sign") == "-" else value


def _sheet_rows(table: ET.Element) -> list[list[object]]:
    rows: list[list[object]] = []

    for row in _iter_rows(table):
        repeat = _repeat(row, "number-rows-repeated")
        cells = _row_cells(row)

        # A repeated empty row is LibreOffice's trailing padding, not data.
        if not cells:
            if repeat > 1:
                continue
            if rows:
                rows.append([])
            continue

        for _ in range(min(repeat, MAX_ROWS - len(rows))):
            rows.append(list(cells))
            if len(rows) >= MAX_ROWS:
                break
        if len(rows) >= MAX_ROWS:
            break

    while rows and not rows[-1]:
        rows.pop()
    return rows


def _iter_rows(table: ET.Element):
    """Yield top-level rows, descending only through row groups."""
    for child in table:
        if child.tag == _tag(TABLE_NS, "table-row"):
            yield child
        elif child.tag in {
            _tag(TABLE_NS, "table-header-rows"),
            _tag(TABLE_NS, "table-row-group"),
            _tag(TABLE_NS, "table-rows"),
        }:
            yield from _iter_rows(child)


def _row_cells(row: ET.Element) -> list[object]:
    cells: list[object] = []

    for cell in row:
        if cell.tag == _tag(TABLE_NS, "covered-table-cell"):
            value: object = None
        elif cell.tag == _tag(TABLE_NS, "table-cell"):
            value = _cell_value(cell)
        else:
            continue

        repeat = _repeat(cell, "number-columns-repeated")
        remaining = MAX_COLUMNS - len(cells)
        if remaining <= 0:
            break

        for _ in range(min(repeat, remaining)):
            cells.append(value)

    while cells and cells[-1] is None:
        cells.pop()
    return cells


def _cell_value(cell: ET.Element) -> object:
    value_type = cell.get(_attr(OFFICE_NS, "value-type"))

    if value_type in {"float", "percentage", "currency"}:
        return _float(cell.get(_attr(OFFICE_NS, "value")))
    if value_type == "date":
        return _date(cell.get(_attr(OFFICE_NS, "date-value")))
    if value_type == "time":
        raw = cell.get(_attr(OFFICE_NS, "time-value"))
        return parse_duration(raw) if raw is not None else None
    if value_type == "boolean":
        raw = cell.get(_attr(OFFICE_NS, "boolean-value"))
        return raw == "true" if raw is not None else None
    if value_type == "string":
        return _text(cell) or None
    if value_type is not None:
        return _text(cell) or None

    # A formula without an explicit type still carries its cached value in
    # one of the typed attributes, or failing that as text.
    for attribute, parser in (
        ("value", _float),
        ("date-value", _date),
        ("time-value", _duration),
        ("boolean-value", lambda raw: raw == "true"),
    ):
        raw = cell.get(_attr(OFFICE_NS, attribute))
        if raw is not None:
            try:
                return parser(raw)
            except (OdsError, ValueError):
                return raw
    return _text(cell) or None


def _text(cell: ET.Element) -> str:
    paragraphs = [
        "".join(paragraph.itertext())
        for paragraph in cell.iter(_tag(TEXT_NS, "p"))
    ]
    return "\n".join(paragraphs)


def _date(raw: str | None) -> date | datetime | None:
    if raw is None:
        return None
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw)
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise OdsError(f"invalid ODS date: {raw!r}") from exc


def _duration(raw: str) -> timedelta:
    return parse_duration(raw)


def _float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise OdsError(f"invalid ODS number: {raw!r}") from exc


def _repeat(element: ET.Element, attribute: str) -> int:
    raw = element.get(_attr(TABLE_NS, attribute))
    if raw is None:
        return 1
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _tag(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _attr(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"
