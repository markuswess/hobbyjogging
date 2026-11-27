"""Project the historical ``Leistungstests`` blocks into the canonical DB.

The sheet importer stores one raw ``sheet`` ``performance_test`` record per
block. This backfill matches a block to an activity by local date and distance
(3 % or 250 m), never guessing when the match is ambiguous. A race block
creates or completes a ``race_results`` row and stores its per-split rows as
``activity_laps`` with ``source='sheet_test'``; a non-race test tags the
matched activity ``time trial`` and stores only the splits. A Runalyze or
manual race result is never overwritten.

Unmatched, ambiguous and broken blocks are reported, not invented.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from hobbyjogging_core.model import Lap, TEST_SPLIT_SOURCE
from hobbyjogging_import.performance_tests import (
    RECORD_TYPE,
    PerformanceTest,
    is_race,
    parse_payload,
)

from ..context import TaskContext
from ..registry import task

SOURCE = "sheet"
TIME_TRIAL_TAG = "time trial"
DISTANCE_RATIO = 0.03
DISTANCE_M = 250.0

_COUNT_ORDER = (
    "blocks",
    "complete",
    "broken",
    "matched",
    "unmatched",
    "ambiguous",
    "race_results",
    "results_kept",
    "split_rows",
    "tags",
    "conflicts",
)


@dataclass(frozen=True)
class _Candidate:
    activity_id: str
    started_at_utc: str | None
    tz_offset_min: int | None


@task(
    "leistungstests_v1",
    kind="backfill",
    description=(
        "Match the Leistungstests blocks to activities, write their race "
        "results, map their splits to activity laps and tag the time trials."
    ),
)
def leistungstests(context: TaskContext) -> None:
    records = _records(context)
    if not records:
        context.note("No Leistungstests blocks in scope.")
        return

    written: set[str] = set()
    for record_id, payload in records:
        context.count("blocks")
        block = parse_payload(payload)
        if block is None:
            context.count("broken")
            context.output_lines.append(
                f"broken: malformed payload in source record {record_id}"
            )
            continue
        _report_assumption(context, block)
        if context.scope.entity_id is not None and block.problems:
            continue
        if block.problems:
            context.count("broken")
            context.output_lines.append(
                f"broken: {_label(block)} ({', '.join(block.problems)})"
            )
            continue
        context.count("complete")
        _project_block(context, block, record_id, written)

    context.order_counts(_COUNT_ORDER)
    context.write_output()


def _project_block(
    context: TaskContext,
    block: PerformanceTest,
    record_id: int,
    written: set[str],
) -> None:
    candidates = _candidates(context, block)
    if context.scope.entity_id is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.activity_id == context.scope.entity_id
        ]
    if not candidates:
        if context.scope.entity_id is not None:
            return
        context.count("unmatched")
        context.output_lines.append(
            f"unmatched: {_label(block)} (no activity within "
            f"{_tolerance(block.official_distance_m or 0):.0f} m)"
        )
        return
    selected = _select(candidates, block)
    if selected is None:
        context.count("ambiguous")
        context.output_lines.append(
            f"ambiguous: {_label(block)} -> "
            + ", ".join(candidate.activity_id for candidate in candidates)
        )
        return

    activity_id = selected.activity_id
    if activity_id in written:
        context.count("conflicts")
        context.output_lines.append(
            f"conflict: {_label(block)} and another block both match "
            f"{activity_id}; the first was kept"
        )
        return
    written.add(activity_id)
    context.count("matched")

    if block.splits:
        laps = [
            Lap(
                index=split.index,
                duration_s=split.duration_s,
                distance_m=split.distance_m,
                avg_hr=split.avg_hr,
            )
            for split in block.splits
        ]
        context.writer.replace_activity_laps(
            activity_id,
            laps,
            source_record_id=record_id,
            source=TEST_SPLIT_SOURCE,
        )
        context.count("split_rows", len(laps))

    methods, targets, has_result = _classification(
        context.connection,
        activity_id,
    )
    race = is_race(
        block,
        workout_methods=methods,
        workout_targets=targets,
        has_result=has_result,
    )
    if race:
        _write_race_result(context, block, activity_id, record_id)
    else:
        context.writer.add_activity_tag(
            activity_id,
            TIME_TRIAL_TAG,
            source=TEST_SPLIT_SOURCE,
            source_record_id=record_id,
        )
        context.count("tags")


def _write_race_result(
    context: TaskContext,
    block: PerformanceTest,
    activity_id: str,
    record_id: int,
) -> None:
    row = context.connection.execute(
        "SELECT source FROM race_results "
        "WHERE activity_id = ? AND excluded_at IS NULL",
        (activity_id,),
    ).fetchone()
    if row is not None and row["source"] != SOURCE:
        context.count("results_kept")
        return

    fields = {
        "official_distance_m": block.official_distance_m,
        "official_time_s": block.official_time_s,
        "officially_measured": 0,
        "place_total": block.place_total,
        "place_ageclass": block.place_ageclass,
        "status": "completed",
        "notes": block.result_text,
    }
    if block.title:
        fields["name"] = block.title
    if context.writer.upsert_race_result(
        activity_id,
        source=SOURCE,
        source_record_id=record_id,
        **fields,
    ):
        context.count("race_results")


def _records(context: TaskContext) -> list[tuple[int, str]]:
    rows = context.connection.execute(
        """
        SELECT id, payload_json
        FROM source_records
        WHERE source = ? AND record_type = ? AND excluded_at IS NULL
        ORDER BY id
        """,
        (SOURCE, RECORD_TYPE),
    ).fetchall()
    records = []
    for row in rows:
        if row["payload_json"] is None:
            continue
        block = parse_payload(row["payload_json"])
        if block is None:
            records.append((row["id"], ""))
            continue
        if context.scope.start is not None and (
            block.date is None or block.date < context.scope.start
        ):
            continue
        if context.scope.end is not None and (
            block.date is None or block.date > context.scope.end
        ):
            continue
        records.append((row["id"], row["payload_json"]))
    if context.scope.limit is not None:
        records = records[: context.scope.limit]
    return records


def _candidates(
    context: TaskContext,
    block: PerformanceTest,
) -> list[_Candidate]:
    if block.date is None or block.official_distance_m is None:
        return []
    tolerance = _tolerance(block.official_distance_m)
    rows = context.connection.execute(
        """
        SELECT id, name, distance_m, started_at_utc, tz_offset_min
        FROM activities
        WHERE local_date = ? AND excluded_at IS NULL
        """,
        (block.date.isoformat(),),
    ).fetchall()
    candidates = []
    for row in rows:
        distance = float(row["distance_m"] or 0)
        if abs(distance - block.official_distance_m) > tolerance:
            continue
        candidates.append(
            _Candidate(
                activity_id=row["id"],
                started_at_utc=row["started_at_utc"],
                tz_offset_min=row["tz_offset_min"],
            )
        )
    return candidates


def _select(
    candidates: list[_Candidate],
    block: PerformanceTest,
) -> _Candidate | None:
    if len(candidates) == 1:
        return candidates[0]
    start_s = _clock_seconds(block.start_time)
    if start_s is None:
        return None
    scored = []
    for candidate in candidates:
        local = _local_seconds(candidate)
        if local is None:
            return None
        scored.append((abs(local - start_s), candidate))
    scored.sort(key=lambda item: item[0])
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def _classification(
    connection: sqlite3.Connection,
    activity_id: str,
) -> tuple[set[str], set[str], bool]:
    methods = {
        row["method"]
        for row in connection.execute(
            "SELECT method FROM activity_workout_methods WHERE activity_id = ?",
            (activity_id,),
        )
    }
    targets = {
        row["target"]
        for row in connection.execute(
            "SELECT target FROM activity_workout_targets WHERE activity_id = ?",
            (activity_id,),
        )
    }
    has_result = (
        connection.execute(
            "SELECT 1 FROM race_results "
            "WHERE activity_id = ? AND excluded_at IS NULL",
            (activity_id,),
        ).fetchone()
        is not None
    )
    return methods, targets, has_result


def _tolerance(distance_m: float) -> float:
    return max(DISTANCE_M, DISTANCE_RATIO * distance_m)


def _local_seconds(candidate: _Candidate) -> int | None:
    if not candidate.started_at_utc or candidate.tz_offset_min is None:
        return None
    try:
        moment = datetime.fromisoformat(
            str(candidate.started_at_utc).replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(
        timezone(timedelta(minutes=candidate.tz_offset_min))
    )
    return local.hour * 3600 + local.minute * 60 + local.second


def _clock_seconds(value: str) -> int | None:
    if not value:
        return None
    try:
        hours, minutes, seconds = (int(part) for part in value.split(":"))
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def _report_assumption(
    context: TaskContext,
    block: PerformanceTest,
) -> None:
    label = _label(block)
    if block.date_source == "inferred-year":
        context.note(
            f"{label}: year inferred from the neighboring block"
        )
    elif block.date_source == "inherited":
        context.note(f"{label}: date inherited from the previous block")


def _label(block: PerformanceTest) -> str:
    day = block.date.isoformat() if block.date else "undated"
    title = block.title or "unnamed block"
    distance = (
        f" {block.official_distance_m / 1000:.1f} km"
        if block.official_distance_m
        else ""
    )
    return f"{day} {title}{distance} (row {block.row + 1})"
