"""The corrections export: a source-side checklist from the review queue.

Open ``field_conflict`` items already name the owner, the disagreeing source,
both values and an advisory cause. This module turns them into a read-only
list grouped by the platform that needs correcting, plus the open quality
findings that can be attributed to one source. It never writes, never calls a
source API and never resolves an item.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import date

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import ReviewItem

from .format import format_canonical_value
from .links import resolve_activity_links

FORMATS = ("markdown", "csv", "json")

CAUSE_ACTIONS = {
    "activity_trimmed": (
        "Fix the trimmed upload at the source; keep the canonical span"
    ),
    "elapsed_definition": (
        "Bulk-resolvable: accept the elapsed-time definition"
    ),
    "moving_estimate": "Bulk-resolvable: accept the moving-time estimate",
    "small_difference": "Bulk-resolvable: accept the small difference",
    "hr_sensor_anomaly": (
        "Check the strap/recording; prefer the plausible heart rate"
    ),
    "sport_vocabulary": (
        "Fix the platform's sport mapping, then re-sync"
    ),
    "distance_estimate": (
        "Check the platform's distance; fix it there if wrong"
    ),
    "duration_estimate": (
        "Check the platform's recording time; fix it there if wrong"
    ),
    "unknown": "Inspect the source and choose a value in triage",
    "quality": "Check the source's recording, then re-sync",
}

QUALITY_FIELDS = {
    "zero_duration": "duration_s",
    "zero_distance": "distance_m",
    "moving_time_mismatch": "moving_s",
    "implied_pace": "pace_s_per_km",
    "local_date_mismatch": "local_date",
    "tz_offset_out_of_range": "tz_offset_min",
    "started_at_invalid": "started_at_utc",
}


@dataclass(frozen=True)
class CorrectionRow:
    """One source-side row, shared by Markdown, CSV and JSON."""

    kind: str
    date: str
    activity: str
    activity_id: str
    field: str
    canonical_source: str
    canonical_value: str
    source: str
    source_value: str
    cause: str
    action: str
    link: str


def corrections_report(
    source: DataSource,
    start: date | None = None,
    end: date | None = None,
    *,
    fmt: str = "markdown",
) -> str:
    """Render open conflicts and source-side quality findings."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown corrections format: {fmt}")

    rows = _correction_rows(source, start=start, end=end)

    if fmt == "json":
        return json.dumps(
            [asdict(row) for row in rows],
            indent=2,
            ensure_ascii=False,
        ) + "\n"

    if fmt == "csv":
        return _csv(rows)

    return _markdown(rows, start=start, end=end)


def _correction_rows(
    source: DataSource,
    *,
    start: date | None,
    end: date | None,
) -> list[CorrectionRow]:
    rows: list[CorrectionRow] = []

    for item in source.review_items(
        status="open",
        category="field_conflict",
    ):
        if not _in_range(item.activity_date, start, end):
            continue

        context = item.context or {}
        field = str(context.get("field") or "")
        if not field:
            continue

        current = context.get("current") or {}
        incoming = context.get("incoming") or {}
        incoming_source = str(
            incoming.get("source") or item.source or "unknown"
        )
        cause = str(context.get("cause") or "unknown")

        rows.append(
            CorrectionRow(
                kind="conflict",
                date=_iso(item.activity_date),
                activity=_activity_label(item),
                activity_id=item.activity_id or "",
                field=field,
                canonical_source=str(current.get("source") or ""),
                canonical_value=format_canonical_value(
                    field,
                    current.get("value"),
                ),
                source=incoming_source,
                source_value=format_canonical_value(
                    field,
                    incoming.get("value"),
                ),
                cause=cause,
                action=CAUSE_ACTIONS.get(cause, CAUSE_ACTIONS["unknown"]),
                link=_best_link(source, item, incoming_source),
            )
        )

    for item in source.review_items(status="open", category="quality"):
        if not item.source or not _in_range(item.activity_date, start, end):
            continue

        context = item.context or {}
        rule = str(context.get("rule") or "quality")
        field = QUALITY_FIELDS.get(rule, "")
        canonical = (
            format_canonical_value(field, context.get(field))
            if field
            else "-"
        )
        rows.append(
            CorrectionRow(
                kind="quality",
                date=_iso(item.activity_date),
                activity=_activity_label(item),
                activity_id=item.activity_id or "",
                field=rule,
                canonical_source="",
                canonical_value=canonical,
                source=item.source,
                source_value=item.detail or "-",
                cause="quality",
                action=CAUSE_ACTIONS["quality"],
                link=_best_link(source, item, item.source),
            )
        )

    rows.sort(
        key=lambda row: (
            row.source,
            row.date,
            row.activity,
            row.field,
        )
    )
    return rows


def _markdown(
    rows: list[CorrectionRow],
    *,
    start: date | None,
    end: date | None,
) -> str:
    window = _window(start, end)
    lines = ["# Corrections", ""]

    if window:
        lines.append(f"- Window: {window}")

    conflict_count = sum(row.kind == "conflict" for row in rows)
    quality_count = sum(row.kind == "quality" for row in rows)
    lines.append(f"- Open field conflicts: {conflict_count}")
    lines.append(f"- Source-side quality findings: {quality_count}")
    lines.append(
        "- Read-only: this list never writes, calls a source API or "
        "resolves an item."
    )

    if not rows:
        lines.append("\nNo corrections in this window.")
        return "\n".join(lines)

    groups: dict[str, list[CorrectionRow]] = {}
    for row in rows:
        if row.kind == "conflict":
            groups.setdefault(row.source, []).append(row)

    for source_name in sorted(groups):
        lines.append(f"\n## {source_name}")
        lines.append(
            "| Date | Activity | Field | Canonical | "
            f"{_cell(source_name)} | Cause | Action | Link |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in groups[source_name]:
            canonical = (
                f"{row.canonical_value} ({row.canonical_source})"
                if row.canonical_source
                else row.canonical_value
            )
            lines.append(
                "| "
                + " | ".join(
                    _cell(part)
                    for part in (
                        row.date,
                        row.activity,
                        row.field,
                        canonical,
                        row.source_value,
                        row.cause,
                        row.action,
                        _link_cell(row.link),
                    )
                )
                + " |"
            )

    quality_rows = [row for row in rows if row.kind == "quality"]
    if quality_rows:
        lines.append("\n## Quality findings")
        lines.append(
            "| Date | Activity | Rule | Stored / detail | Source | "
            "Action | Link |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for row in quality_rows:
            lines.append(
                "| "
                + " | ".join(
                    _cell(part)
                    for part in (
                        row.date,
                        row.activity,
                        row.field,
                        f"{row.canonical_value} / {row.source_value}",
                        row.source,
                        row.action,
                        _link_cell(row.link),
                    )
                )
                + " |"
            )

    return "\n".join(lines)


def _csv(rows: list[CorrectionRow]) -> str:
    buffer = io.StringIO()
    fieldnames = list(CorrectionRow.__dataclass_fields__)
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(asdict(row))
    return buffer.getvalue()


def _best_link(
    source: DataSource,
    item: ReviewItem,
    preferred_source: str,
) -> str:
    activity_id = item.activity_id
    if not activity_id:
        return ""

    if preferred_source == "strava":
        social = getattr(source, "activity_social", None)
        if social is not None:
            for entry in social(activity_id):
                if entry.source == "strava" and entry.url:
                    return entry.url

    links = resolve_activity_links(source, activity_id)

    if preferred_source in ("fit", "garmin"):
        return links.garmin or links.intervals or ""
    if preferred_source == "intervals":
        return links.intervals or links.garmin or ""
    return links.intervals or links.garmin or ""


def _activity_label(item: ReviewItem) -> str:
    return (
        item.activity_name
        or item.sport
        or item.activity_id
        or "-"
    )


def _in_range(
    day: date | None,
    start: date | None,
    end: date | None,
) -> bool:
    if day is None:
        return start is None and end is None
    if start is not None and day < start:
        return False
    if end is not None and day > end:
        return False
    return True


def _window(start: date | None, end: date | None) -> str:
    if start is None and end is None:
        return "all open items"
    return f"{start or '...'} .. {end or '...'}"


def _iso(day: date | None) -> str:
    return day.isoformat() if day else "-"


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _link_cell(link: str) -> str:
    if not link:
        return "-"
    return f"[open]({link})"
