"""Planned-workout zone parsing for Intervals events.

Intervals stores a planned workout's zone distribution in
``workout_doc.zoneTimes`` as ``[{"id": "Z1", "secs": 1650}, ...]``. The kind
of zones is not stored on the event; it is implied by the workout's step
targets, so this module derives it from the step tree.

The parsing and inference functions are pure. :func:`backfill_event_zones`
repairs already-stored events from their saved payloads without touching the
network.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass

from hobbyjogging_core import EventZoneTime, TrainingWriter
from hobbyjogging_core.sports import RIDE_SPORTS, RUN_SPORTS
from .numeric import number as _number

PACE = "pace"
HR = "hr"
POWER = "power"
UNKNOWN = "unknown"

ZONE_LABELS = frozenset({f"Z{index}" for index in range(1, 8)} | {"SS"})
_LABEL_ORDER = tuple(f"Z{index}" for index in range(1, 8)) + ("SS",)
_TARGET_KINDS = (PACE, HR, POWER)
_ZONE_INDEX = re.compile(r"^Z([1-7])$")


@dataclass
class ZoneBackfillSummary:
    """Result of rewriting stored event zone times from saved payloads."""

    dry_run: bool = False
    events: int = 0
    updated: int = 0
    cleared: int = 0
    unchanged: int = 0
    skipped: int = 0


def parse_zone_times(workout_doc: object) -> list[EventZoneTime]:
    """Return the planned zone buckets from one workout document.

    Zero-second buckets are kept: they are part of the plan's shape. Labels
    outside ``Z1``-``Z7``/``SS`` and entries without a usable duration are
    ignored. ``SS`` has no numeric index.
    """
    if not isinstance(workout_doc, dict):
        return []
    rows = workout_doc.get("zoneTimes")
    if not isinstance(rows, list):
        return []

    parsed: dict[str, EventZoneTime] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("id") or "").strip().upper()
        if label not in ZONE_LABELS:
            continue
        seconds = _number(row.get("secs"))
        if seconds is None or seconds < 0:
            continue
        parsed[label] = EventZoneTime(
            zone_label=label,
            seconds=seconds,
            zone_index=_zone_index(label),
        )

    order = {label: index for index, label in enumerate(_LABEL_ORDER)}
    return sorted(
        parsed.values(),
        key=lambda zone: order.get(zone.zone_label, len(order)),
    )


def infer_zone_kind(workout_doc: object, sport: str) -> str:
    """Return the zone kind implied by a workout's step targets.

    The target kind with the most planned seconds wins. Ties prefer the
    sport's natural kind, then pace, HR, and power. Without any step target
    the sport decides; sports without pace or power zones are ``unknown``.
    """
    weights, counts = _target_totals(workout_doc)

    winners = _winners(weights)
    if not winners:
        winners = _winners(counts)
    if winners:
        return _break_tie(winners, sport)

    return _sport_kind(sport)


def event_zone_data(
    raw: dict,
    sport: str,
) -> tuple[str, list[EventZoneTime]]:
    """Return the zone kind and buckets for one Intervals event payload.

    An event without a workout document has no planned zones at all, so its
    kind is cleared rather than inferred from the sport.
    """
    workout_doc = raw.get("workout_doc")
    if not isinstance(workout_doc, dict):
        return "", []
    return infer_zone_kind(workout_doc, sport), parse_zone_times(workout_doc)


def backfill_event_zones(
    connection: sqlite3.Connection,
    *,
    dry_run: bool = False,
) -> ZoneBackfillSummary:
    """Rewrite stored event zone kinds/times from saved Intervals payloads.

    Only events linked to an Intervals event source record are considered.
    Soft-excluded events and malformed payloads are skipped. Writes happen
    only when the stored kind or distribution differs, so repeated runs are
    idempotent and do not touch ``updated_at``.
    """
    rows = connection.execute(
        """
        SELECT e.id, e.name, e.type, e.local_date, e.zone_kind,
               e.excluded_at, sr.payload_json
        FROM events e
        JOIN source_records sr ON sr.id = e.source_record_id
        WHERE sr.source = 'intervals' AND sr.record_type = 'event'
        ORDER BY e.local_date, e.name
        """
    ).fetchall()

    current = current_zone_times(connection, [row["id"] for row in rows])
    summary = ZoneBackfillSummary(dry_run=dry_run)
    writer = TrainingWriter(connection)

    try:
        for row in rows:
            summary.events += 1

            if row["excluded_at"]:
                summary.skipped += 1
                continue

            payload = _payload(row["payload_json"])
            if payload is None:
                summary.skipped += 1
                continue

            kind, zones = event_zone_data(payload, row["type"])
            desired = _zone_map(zones)
            existing = current.get(row["id"], {})

            if row["zone_kind"] == kind and existing == desired:
                summary.unchanged += 1
                continue

            summary.updated += 1
            if not kind and not zones and (row["zone_kind"] or existing):
                summary.cleared += 1

            if not dry_run:
                writer.set_event_zone_times(row["id"], kind, zones)

        if not dry_run:
            connection.commit()
    except Exception:
        if not dry_run:
            connection.rollback()
        raise

    return summary


def _target_totals(
    workout_doc: object,
) -> tuple[Counter[str], Counter[str]]:
    weights: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    if not isinstance(workout_doc, dict):
        return weights, counts
    _accumulate_steps(workout_doc.get("steps"), 1, weights, counts)
    return weights, counts


def _accumulate_steps(
    steps: object,
    multiplier: int,
    weights: Counter[str],
    counts: Counter[str],
) -> None:
    if not isinstance(steps, list):
        return

    for step in steps:
        if not isinstance(step, dict):
            continue

        reps = _positive_int(step.get("reps")) or 1
        nested = step.get("steps")
        if isinstance(nested, list) and nested:
            _accumulate_steps(nested, multiplier * reps, weights, counts)
            continue

        duration = _number(step.get("duration")) or 0.0
        for kind in _TARGET_KINDS:
            if isinstance(step.get(kind), dict):
                weights[kind] += duration * multiplier * reps
                counts[kind] += multiplier * reps


def _winners(totals: Counter[str]) -> list[str]:
    if not totals:
        return []
    best = max(totals.values())
    if best <= 0:
        return []
    return [kind for kind in _TARGET_KINDS if totals.get(kind) == best]


def _break_tie(kinds: list[str], sport: str) -> str:
    if len(kinds) == 1:
        return kinds[0]

    natural = _sport_kind(sport)
    if natural in kinds:
        return natural

    for kind in _TARGET_KINDS:
        if kind in kinds:
            return kind
    return UNKNOWN


def _sport_kind(sport: str) -> str:
    if sport in RUN_SPORTS:
        return PACE
    if sport in RIDE_SPORTS:
        return POWER
    return UNKNOWN


def _zone_index(label: str) -> int | None:
    match = _ZONE_INDEX.match(label)
    return int(match.group(1)) if match else None


def current_zone_times(
    connection: sqlite3.Connection,
    event_ids: list[str],
) -> dict[str, dict[str, float]]:
    """Return ``{event_id: {zone_label: seconds}}`` for the given events."""
    if not event_ids:
        return {}

    placeholders = ", ".join("?" for _ in event_ids)
    rows = connection.execute(
        f"""
        SELECT event_id, zone_label, seconds
        FROM event_zone_times
        WHERE event_id IN ({placeholders})
        """,
        event_ids,
    ).fetchall()

    result: dict[str, dict[str, float]] = {}
    for row in rows:
        result.setdefault(row["event_id"], {})[row["zone_label"]] = row[
            "seconds"
        ]
    return result


def _zone_map(zones: list[EventZoneTime]) -> dict[str, float]:
    return {zone.zone_label: float(zone.seconds) for zone in zones}


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _positive_int(value: object) -> int | None:
    number = _number(value)
    if number is None or number < 1:
        return None
    return int(number)
