"""Stamp the pre-column interval rows with their source.

Every interval row stored before schema v25 came from Intervals.icu; the
column was added so a derived set from device laps can coexist without
overwriting measured reps. This backfill records the provenance once.
"""

from __future__ import annotations

from ..context import TaskContext
from ..registry import task

SOURCE = "intervals"


@task(
    "interval_source_v1",
    kind="backfill",
    description=(
        "Stamp the existing interval rows with source='intervals'."
    ),
)
def interval_source(context: TaskContext) -> None:
    rows = context.connection.execute(
        "SELECT COUNT(*) FROM activity_intervals WHERE source = ''"
    ).fetchone()[0]
    context.count("rows", rows)
    context.count(
        "stamped",
        context.writer.stamp_interval_source(SOURCE),
    )
