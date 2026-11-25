"""Clean the historical sheet/device duplicate pairs.

A sheet-only row that mirrors a device row is removed after its description is
copied to the device row (only when the device row is blank), so the session
keeps the historical note and stops counting twice. The pair rule is the shared
``duplicates.same_session`` rule: same sport/day, distance within 2 %, duration
within 5 % and average HR within 5 bpm when both carry it.

This is a backfill, not a sync step: it rewrites an exclusion and a manual
description, so it runs deliberately, with a dry run first. It never merges.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from hobbyjogging_import.duplicates import find_duplicates

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

DEVICE_SOURCES = frozenset({"fit", "intervals"})

_COUNT_ORDER = (
    "sheet_only",
    "pairs",
    "description_filled",
    "description_kept",
    "no_text",
    "excluded",
    "ambiguous",
    "no_device",
)


@task(
    "sheet_duplicates_v1",
    kind="backfill",
    description=(
        "Copy a sheet-only duplicate's description to the device row and "
        "exclude the sheet row."
    ),
)
def sheet_duplicates(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    sources = _source_sets(context.connection)
    pairs = find_duplicates(_all_activities(context))
    pair_by_sheet: dict[str, list] = {}
    for pair in pairs:
        for side in (pair.first, pair.second):
            if sources.get(side.id) == {"sheet"}:
                pair_by_sheet.setdefault(side.id, []).append(pair)

    for sheet in activities:
        if sources.get(sheet.id) != {"sheet"}:
            continue
        context.count("sheet_only")

        candidates = []
        for pair in pair_by_sheet.get(sheet.id, []):
            other = pair.second if pair.first.id == sheet.id else pair.first
            if sources.get(other.id, set()) & DEVICE_SOURCES:
                candidates.append((pair, other))

        if not candidates:
            # A pair may still exist with a non-device activity; leave it to
            # the duplicate review item.
            context.count("no_device")
            continue
        if len(candidates) > 1:
            context.count("ambiguous")
            continue

        pair, device = candidates[0]
        _apply_pair(context, sheet, device)
        context.count("excluded")
        context.output_lines.append(
            f"{sheet.date} {sheet.id} -> {device.id} "
            f"({pair.distance_delta_m:.0f} m, "
            f"{pair.duration_delta_s:.0f} s)"
        )

    context.order_counts(_COUNT_ORDER)
    context.write_output()


def _apply_pair(context: TaskContext, sheet, device) -> None:
    context.count("pairs")
    sheet_text = str(sheet.description or "").strip()
    device_text = str(device.description or "").strip()

    if not sheet_text:
        context.count("no_text")
    elif device_text:
        context.count("description_kept")
    else:
        context.writer.set_manual_field(
            device.id,
            "description",
            sheet_text,
        )
        context.writer.record_edit_log(
            entity_kind="activity",
            entity_id=device.id,
            field="description",
            old="",
            new=sheet_text,
            source="sheet-duplicate",
            note=f"filled from sheet duplicate {sheet.id}",
        )
        context.count("description_filled")

    context.writer.exclude_activity(
        sheet.id,
        resolve_note=f"duplicate of {device.id}",
    )


def _all_activities(context: TaskContext):
    """All non-excluded activities, so a scoped sheet still finds its device."""
    row = context.connection.execute(
        "SELECT MIN(local_date), MAX(local_date) FROM activities "
        "WHERE excluded_at IS NULL"
    ).fetchone()
    if row[0] is None:
        return []
    return context.repository.activities(
        date.fromisoformat(row[0]),
        date.fromisoformat(row[1]),
    )


def _source_sets(
    connection: sqlite3.Connection,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in connection.execute(
        """
        SELECT als.activity_id, sr.source
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        JOIN activities a ON a.id = als.activity_id
        WHERE a.excluded_at IS NULL
        """
    ):
        result.setdefault(row["activity_id"], set()).add(row["source"])
    return result
