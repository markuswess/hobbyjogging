"""Synthetic ODS workbooks for the spreadsheet-import tests."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


class _Covered:
    pass


COVERED = _Covered()


@dataclass(frozen=True)
class RawCell:
    """Inject a cell's XML verbatim for type/formula edge cases."""

    xml: str


@dataclass(frozen=True)
class ColumnRepeat:
    value: object
    count: int


@dataclass(frozen=True)
class RowRepeat:
    cells: list[object]
    count: int


def write_ods(
    path: str | Path,
    sheets: list[tuple[str, list[list[object]]]],
) -> Path:
    """Write a minimal ODS workbook with the given sheets and rows."""
    tables = []
    for name, rows in sheets:
        tables.append(
            f'<table:table table:name="{_escape(name)}">'
            + "".join(_row_xml(row) for row in rows)
            + "</table:table>"
        )

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<office:document-content xmlns:office="{OFFICE_NS}" '
        f'xmlns:table="{TABLE_NS}" xmlns:text="{TEXT_NS}">'
        "<office:body><office:spreadsheet>"
        + "".join(tables)
        + "</office:spreadsheet></office:body></office:document-content>"
    )

    path = Path(path)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("content.xml", content)
    return path


def _row_xml(row: list[object]) -> str:
    if isinstance(row, RowRepeat):
        cells = "".join(_cell_xml(cell) for cell in row.cells)
        return (
            f'<table:table-row table:number-rows-repeated="{row.count}">'
            f"{cells}</table:table-row>"
        )
    return "<table:table-row>" + "".join(
        _cell_xml(cell) for cell in row
    ) + "</table:table-row>"


def _cell_xml(cell: object) -> str:
    if isinstance(cell, RawCell):
        return cell.xml
    if isinstance(cell, ColumnRepeat):
        return _cell_xml(cell.value).replace(
            "<table:table-cell",
            f'<table:table-cell table:number-columns-repeated="{cell.count}"',
            1,
        )
    if cell is COVERED:
        return "<table:covered-table-cell/>"
    if cell is None:
        return "<table:table-cell/>"
    if isinstance(cell, bool):
        return (
            '<table:table-cell office:value-type="boolean" '
            f'office:boolean-value="{str(cell).lower()}"/>'
        )
    if isinstance(cell, (int, float)):
        return (
            '<table:table-cell office:value-type="float" '
            f'office:value="{cell}"/>'
        )
    if isinstance(cell, date):
        return (
            '<table:table-cell office:value-type="date" '
            f'office:date-value="{cell.isoformat()}"/>'
        )
    if isinstance(cell, timedelta):
        return (
            '<table:table-cell office:value-type="time" '
            f'office:time-value="{_iso_duration(cell)}"/>'
        )
    return (
        '<table:table-cell office:value-type="string"><text:p>'
        f"{_escape(str(cell))}</text:p></table:table-cell>"
    )


def _iso_duration(value: timedelta) -> str:
    seconds = value.total_seconds()
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"PT{int(hours)}H{int(minutes)}M{seconds:g}S"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
