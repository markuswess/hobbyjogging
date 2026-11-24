"""Fill ``training_load`` from Runalyze's TRIMP when Intervals has none.

Intervals' ``icu_training_load`` is the reference. An Intervals-less athlete
still has ``fit_trimp`` (device) or ``trimp`` on every Runalyze payload, so
that value fills an empty load under ``source='runalyze'``. ``training_load``
declares the ranked authority Intervals → Runalyze: in a mixed database an
Intervals value always wins, and this task never blends the two scales.

TRIMP is a vendor scale, not the same number as an Intervals load; the field
source records which one filled it.
"""

from __future__ import annotations

import json

from ..context import TaskContext
from ..registry import task

SOURCE = "runalyze"
FIELD = "training_load"

_COUNT_ORDER = (
    "rows",
    "written",
    "unchanged",
    "kept_measured",
    "no_value",
    "missing_activity",
)


@task(
    "runalyze_load_current",
    kind="recompute",
    description=(
        "Fill an empty training_load from Runalyze's fit_trimp/trimp."
    ),
)
def runalyze_load_current(context: TaskContext) -> None:
    rows = context.connection.execute(
        """
        SELECT als.activity_id AS activity_id,
               sr.id AS source_record_id,
               sr.payload_json AS payload_json
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE sr.source = ? AND sr.record_type = 'activity'
        ORDER BY als.activity_id
        """,
        (SOURCE,),
    ).fetchall()

    for row in rows:
        context.count("rows")
        activity_id = row["activity_id"]

        activity = context.connection.execute(
            """
            SELECT training_load, excluded_at FROM activities WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        if activity is None:
            context.count("missing_activity")
            continue
        if activity["excluded_at"]:
            context.count("kept_measured")
            continue

        owner_row = context.connection.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = ? AND field_name = ?
            """,
            (activity_id, FIELD),
        ).fetchone()
        owner = owner_row["source"] if owner_row is not None else None

        if owner not in (None, SOURCE):
            context.count("kept_measured")
            continue
        if owner is None and activity["training_load"] is not None:
            # A load without a recorded owner predates the manual layer; do
            # not guess that it is a fallback.
            context.count("kept_measured")
            continue

        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            context.count("no_value")
            continue

        value = _trimp(payload)
        if value is None:
            context.count("no_value")
            continue
        if activity["training_load"] is not None and _close(
            activity["training_load"], value
        ):
            context.count("unchanged")
            continue

        context.writer.upsert_activity(
            activity_id,
            {FIELD: value},
            source=SOURCE,
            source_record_id=row["source_record_id"],
        )
        context.count("written")

    context.order_counts(_COUNT_ORDER)


def _trimp(payload: dict) -> float | None:
    for key in ("fit_trimp", "trimp"):
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def _close(current: object, value: float) -> bool:
    try:
        return abs(float(current) - value) < 0.01
    except (TypeError, ValueError):
        return False
