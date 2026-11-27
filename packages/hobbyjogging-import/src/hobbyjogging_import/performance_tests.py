"""Parse the ``Leistungstests`` worksheet into performance-test blocks.

The sheet has no stable table: a block starts at a ``Start`` row (or at a
date-only heading) and runs until the next block. The dashboard columns are
the main header; the ``Geschw/Puls Test`` block overrides them with
``Strecke``, ``Puls`` and ``Zeit`` in the same positions.

Each block becomes one raw input record. The backfill decides what a block
means; this module only reads the cells and records what it saw, including
the assumptions it needed to make (an inherited date or an inferred year).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .ods import Sheet

SHEET = "Leistungstests"
RECORD_TYPE = "performance_test"

DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})?\s*$")
_TITLE_SKIP = ("Ergebnis", "Ziel", "Km", "Gesamt", "Sieg", "Strecke")


@dataclass(frozen=True)
class PerformanceSplit:
    """One split row: a segment distance and its time."""

    index: int
    distance_m: float
    duration_s: float
    cumulative_m: float | None = None
    avg_hr: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "distance_m": self.distance_m,
            "duration_s": self.duration_s,
            "cumulative_m": self.cumulative_m,
            "avg_hr": self.avg_hr,
        }


@dataclass
class PerformanceTest:
    """One parsed block, before it is matched to an activity."""

    row: int
    date: date | None
    date_text: str = ""
    date_source: str = ""
    start_time: str = ""
    distance_m: float | None = None
    target_s: float | None = None
    title: str = ""
    splits: list[PerformanceSplit] = field(default_factory=list)
    official_distance_m: float | None = None
    official_time_s: float | None = None
    result_text: str = ""
    place_total: int | None = None
    place_ageclass: int | None = None
    layout: str = "standard"
    problems: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "broken" if self.problems else "complete"

    @property
    def external_id(self) -> str:
        """A content key, stable when a sheet row is inserted."""
        day = self.date.isoformat() if self.date else "undated"
        title = " ".join(self.title.strip().lower().split()).replace("|", "/")
        distance = f"{self.official_distance_m or 0:.0f}"
        start = self.start_time or "-"
        return f"{day}|{start}|{distance}|{title}"

    def payload(self) -> str:
        """Serialize the block as the stored raw input."""
        return json.dumps(
            {
                "sheet": SHEET,
                "block": {
                    "row": self.row,
                    "date": self.date.isoformat() if self.date else None,
                    "date_text": self.date_text,
                    "date_source": self.date_source,
                    "start_time": self.start_time,
                    "distance_m": self.distance_m,
                    "target_s": self.target_s,
                    "title": self.title,
                    "official_distance_m": self.official_distance_m,
                    "official_time_s": self.official_time_s,
                    "result_text": self.result_text,
                    "place_total": self.place_total,
                    "place_ageclass": self.place_ageclass,
                    "layout": self.layout,
                    "status": self.status,
                    "problems": list(self.problems),
                },
                "splits": [split.as_dict() for split in self.splits],
            },
            sort_keys=True,
            separators=(",", ":"),
        )


def parse_performance_tests(sheet: Sheet) -> list[PerformanceTest]:
    """Split a worksheet into blocks and parse each one."""
    rows = sheet.rows
    starts = _block_starts(rows)
    blocks: list[PerformanceTest] = []
    last_date: date | None = None

    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(rows)
        block, last_date = _parse_block(rows, start, end, last_date)
        blocks.append(block)

    return blocks


def from_payload(payload: dict) -> PerformanceTest:
    """Rebuild a block from a stored ``performance_test`` payload."""
    block = payload.get("block") or {}
    raw_date = block.get("date")
    day = date.fromisoformat(raw_date) if raw_date else None
    return PerformanceTest(
        row=int(block.get("row") or 0),
        date=day,
        date_text=str(block.get("date_text") or ""),
        date_source=str(block.get("date_source") or ""),
        start_time=str(block.get("start_time") or ""),
        distance_m=_number_or_none(block.get("distance_m")),
        target_s=_number_or_none(block.get("target_s")),
        title=str(block.get("title") or ""),
        splits=[
            PerformanceSplit(
                index=int(split.get("index") or 0),
                distance_m=float(split.get("distance_m") or 0),
                duration_s=float(split.get("duration_s") or 0),
                cumulative_m=_number_or_none(split.get("cumulative_m")),
                avg_hr=_number_or_none(split.get("avg_hr")),
            )
            for split in payload.get("splits") or []
        ],
        official_distance_m=_number_or_none(
            block.get("official_distance_m")
        ),
        official_time_s=_number_or_none(block.get("official_time_s")),
        result_text=str(block.get("result_text") or ""),
        place_total=_int_or_none(block.get("place_total")),
        place_ageclass=_int_or_none(block.get("place_ageclass")),
        layout=str(block.get("layout") or "standard"),
        problems=[str(item) for item in block.get("problems") or []],
    )


def parse_payload(raw: str | None) -> PerformanceTest | None:
    """Parse one stored payload, ignoring malformed JSON."""
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return from_payload(payload)
    except (TypeError, ValueError):
        return None


def is_race(
    block: PerformanceTest,
    *,
    workout_methods=(),
    workout_targets=(),
    has_result: bool = False,
) -> bool:
    """Whether a complete block is a race rather than a time trial.

    A named event or a placement makes it a race. An unnamed block is a test
    unless the matched activity is already classified as a race or carries a
    race result.
    """
    title = block.title.strip().lower()
    if "test" in title:
        return False
    if block.result_text or block.title:
        return True
    if has_result:
        return True
    return "race" in workout_methods or "race" in workout_targets


def _block_starts(rows: list[list[object]]) -> list[int]:
    starts = []
    for index in range(1, len(rows)):
        if _cell(rows, index, 4) == "Start" or _is_date_value(
            _cell(rows, index, 0)
        ):
            starts.append(index)
    return starts


def _parse_block(
    rows: list[list[object]],
    start: int,
    end: int,
    previous_date: date | None,
) -> tuple[PerformanceTest, date | None]:
    raw_date = _cell(rows, start, 0)
    day, date_text, date_source = _date_value(raw_date, previous_date)
    if _is_date_value(raw_date) and day is not None:
        previous_date = day
    elif previous_date is not None:
        # A block without its own date cell belongs to the previous date.
        day = previous_date
        date_text = day.isoformat()
        date_source = "inherited"

    layout = (
        "hr_steps"
        if any(
            _cell(rows, index, 6) == "Strecke"
            for index in range(start, min(start + 3, end))
        )
        else "standard"
    )
    block = PerformanceTest(
        row=start,
        date=day,
        date_text=date_text,
        date_source=date_source,
        start_time=_clock(_cell(rows, start, 1)),
        distance_m=_positive_number(_cell(rows, start, 2)),
        target_s=_seconds(_cell(rows, start, 3)),
        title=_title(rows, start, end),
        layout=layout,
    )

    last_cumulative = None
    last_total = None
    for index in range(start, end):
        distance = _positive_number(_cell(rows, index, 6))
        duration = _seconds(_cell(rows, index, 11))
        if distance is not None and duration is not None and duration > 0:
            block.splits.append(
                PerformanceSplit(
                    index=len(block.splits) + 1,
                    distance_m=distance,
                    duration_s=duration,
                    cumulative_m=(
                        None
                        if layout == "hr_steps"
                        else _positive_number(_cell(rows, index, 7))
                    ),
                    avg_hr=_heart_rate(
                        _cell(rows, index, 7 if layout == "hr_steps" else 14)
                    ),
                )
            )
        if layout == "standard":
            cumulative = _positive_number(_cell(rows, index, 7))
            if cumulative is not None:
                last_cumulative = cumulative
        total = _seconds(_cell(rows, index, 18))
        if total is not None and total > 0:
            last_total = total

    block.result_text = _result_text(rows, start, end)
    block.place_total = _place_total(block.result_text)
    block.place_ageclass = _place_ageclass(block.result_text)
    block.official_distance_m = _official_distance(
        block.distance_m,
        last_cumulative,
        block.splits,
    )
    block.official_time_s = _official_time(last_total, block.splits)
    block.problems = _problems(block)
    return block, previous_date


def _date_value(
    value: object,
    previous: date | None,
) -> tuple[date | None, str, str]:
    if isinstance(value, datetime):
        day = value.date()
        return day, day.isoformat(), "cell"
    if isinstance(value, date):
        return value, value.isoformat(), "cell"
    if not isinstance(value, str):
        return None, "", ""
    match = DATE_RE.match(value)
    if not match:
        return None, value, ""
    day, month, year = match.groups()
    if year:
        year_number = int(year)
        if year_number < 100:
            year_number += 2000
        return date(year_number, int(month), int(day)), value, "text"
    if previous is None:
        return None, value, ""
    return (
        date(previous.year, int(month), int(day)),
        value,
        "inferred-year",
    )


def _is_date_value(value: object) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    return isinstance(value, str) and DATE_RE.match(value) is not None


def _title(rows: list[list[object]], start: int, end: int) -> str:
    for index in range(start + 1, min(start + 5, end)):
        value = _cell(rows, index, 0)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text and not text.startswith(_TITLE_SKIP):
            return text
    return ""


def _result_text(rows: list[list[object]], start: int, end: int) -> str:
    found: list[str] = []
    for index in range(start, end):
        for column in (0, 1):
            value = _cell(rows, index, column)
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in ("ergebnis:", "ergebnis"):
                continue
            if (
                re.search(r"\b(?:gesamt|gesamtstaffel)\b", lowered)
                or lowered.startswith("ergebnis")
                or re.search(r"\bsieg\b", lowered)
            ) and text not in found:
                found.append(text)
                break
    return " | ".join(found)


def _place_total(text: str) -> int | None:
    match = re.search(r"\b(?:gesamt|gesamtstaffel)\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1))
    if re.search(r"\bsieg\b", text, re.I):
        return 1
    return None


def _place_ageclass(text: str) -> int | None:
    for pattern in (
        r"\bklasse[n]?\s*(\d+)",
        r"\bm-\d+\s*[:.]?\s*(\d+)",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return int(match.group(1))
    return None


def _official_distance(
    block_distance: float | None,
    last_cumulative: float | None,
    splits: list[PerformanceSplit],
) -> float | None:
    if block_distance is not None and block_distance > 0:
        return block_distance
    if last_cumulative is not None and last_cumulative > 0:
        return last_cumulative
    total = sum(split.distance_m for split in splits)
    return total if total > 0 else None


def _official_time(
    last_total: float | None,
    splits: list[PerformanceSplit],
) -> float | None:
    if last_total is not None and last_total > 0:
        return last_total
    total = sum(split.duration_s for split in splits)
    return total if total > 0 else None


def _problems(block: PerformanceTest) -> list[str]:
    problems = []
    if block.date is None:
        problems.append("no date")
    if block.official_distance_m is None:
        problems.append("no distance")
    if not block.splits:
        problems.append("no splits")
    if block.official_time_s is None:
        problems.append("no time")
    return problems


def _cell(rows: list[list[object]], index: int, column: int) -> object:
    row = rows[index] if index < len(rows) else []
    return row[column] if column < len(row) else None


def _positive_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number > 0 else None


def _number_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    number = _number_or_none(value)
    return None if number is None else int(number)


def _seconds(value: object) -> float | None:
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, datetime):
        return (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1_000_000
        )
    return None


def _clock(value: object) -> str:
    seconds = _seconds(value)
    if seconds is None:
        return ""
    total = int(round(seconds)) % (24 * 3600)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _heart_rate(value: object) -> float | None:
    number = _positive_number(value)
    if number is None or not 40 <= number <= 230:
        return None
    return number
