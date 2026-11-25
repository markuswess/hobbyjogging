"""The ``threshold`` command: manual max HR, LTHR and threshold pace.

Intervals stamps a threshold series on its activities; an Intervals-less
athlete has none, so zones, the effective-VO2max max-HR snapshot and
threshold-relative subT comparisons stay empty. A manual snapshot is dated and
per sport, and the automatic recompute never removes it.
"""

from __future__ import annotations

import argparse
from datetime import date

from hobbyjogging_core import TrainingRepository, TrainingWriter, open_database

from .history import history_lines, record_changes
from .values import format_duration_s, parse_pace_mps, parse_sport

SOURCE = "manual"
ENTITY = "athlete_threshold"


def run_threshold(args, parser: argparse.ArgumentParser) -> int:
    action = args.threshold_action

    if action == "add":
        return _add(args, parser)
    if action == "list":
        return _list(args, parser)
    if action == "history":
        return _history(args, parser)

    parser.error(f"unknown threshold command: {action}")
    return 1


def _add(args, parser: argparse.ArgumentParser) -> int:
    try:
        sport = parse_sport(args.sport)
    except ValueError as exc:
        parser.error(str(exc))

    values: dict[str, float] = {}
    if args.max_hr is not None:
        if args.max_hr <= 0:
            parser.error("--max-hr must be positive")
        values["max_hr"] = args.max_hr
    if args.lthr is not None:
        if args.lthr <= 0:
            parser.error("--lthr must be positive")
        values["lthr"] = args.lthr
    if args.threshold_pace is not None:
        try:
            values["threshold_pace_mps"] = parse_pace_mps(
                args.threshold_pace
            )
        except ValueError as exc:
            parser.error(str(exc))

    if not values:
        parser.error("give at least one of --max-hr, --lthr, --threshold-pace")

    connection = open_database(args.database)
    try:
        effective = _resolve_effective(
            args.effective_from,
            connection,
            sport,
            parser,
        )
        writer = TrainingWriter(connection)
        old = _row(connection, sport, effective)
        new = {
            "max_hr": values.get("max_hr"),
            "lthr": values.get("lthr"),
            "threshold_pace_mps": values.get("threshold_pace_mps"),
        }
        writer.set_manual_threshold(
            effective,
            sport,
            **values,
        )
        record_changes(
            writer,
            entity_kind=ENTITY,
            entity_id=f"{sport}:{effective.isoformat()}",
            old=old,
            new=new,
            source=SOURCE,
            note=args.note or "threshold add",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: threshold {sport} from {effective} not written.")
            return 0
        connection.commit()
        earlier = _earlier_unzoned(connection, sport, effective)
    finally:
        connection.close()

    print(f"threshold saved: {sport} from {effective}")
    if earlier:
        print(
            f"Zones apply from {effective}; {earlier} earlier {sport} "
            "activities stay unzoned (use --from first)."
        )
    else:
        print(
            f"Zones apply from {effective}; no earlier {sport} activity "
            "stays unzoned."
        )
    return 0


def _resolve_effective(
    value: str | None,
    connection,
    sport: str,
    parser: argparse.ArgumentParser,
) -> date:
    """Resolve ``--from``, including the ``first`` activity anchor."""
    if value is None:
        return date.today()
    if value.strip().lower() == "first":
        row = connection.execute(
            """
            SELECT MIN(local_date) FROM activities
            WHERE excluded_at IS NULL AND sport = ?
            """,
            (sport,),
        ).fetchone()
        if row is None or row[0] is None:
            parser.error(
                f"no {sport} activities to anchor --from first"
            )
        return date.fromisoformat(row[0])

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        parser.error(f"invalid date: {exc}")


def _earlier_unzoned(connection, sport: str, effective: date) -> int:
    """Earlier activities of this sport that still have no zone config."""
    row = connection.execute(
        """
        SELECT COUNT(*) FROM activities
        WHERE excluded_at IS NULL
          AND sport = ?
          AND local_date < ?
          AND hr_zone_config_id IS NULL
          AND pace_zone_config_id IS NULL
        """,
        (sport, effective.isoformat()),
    ).fetchone()
    return row[0] if row is not None else 0


def _history(args, parser: argparse.ArgumentParser) -> int:
    sport = None
    if args.sport:
        try:
            sport = parse_sport(args.sport)
        except ValueError as exc:
            parser.error(str(exc))

    effective = None
    if args.effective_from:
        try:
            effective = date.fromisoformat(args.effective_from)
        except ValueError as exc:
            parser.error(f"invalid date: {exc}")
        if sport is None:
            parser.error("--from needs --sport")

    connection = open_database(args.database)
    try:
        repository = TrainingRepository(connection)
        if sport is not None and effective is not None:
            entries = repository.edit_history(
                ENTITY, f"{sport}:{effective.isoformat()}"
            )
        elif sport is not None:
            entries = repository.edit_history_prefix(
                ENTITY, f"{sport}:"
            )
        else:
            entries = repository.edit_history_prefix(ENTITY)
    finally:
        connection.close()

    for line in history_lines(entries):
        print(line)
    return 0


def _row(connection, sport: str, effective: date) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT max_hr, lthr, threshold_pace_mps
        FROM athlete_thresholds
        WHERE source = 'manual' AND sport = ? AND effective_from = ?
        """,
        (sport, effective.isoformat()),
    ).fetchone()
    if row is None:
        return {}
    return {
        "max_hr": row["max_hr"],
        "lthr": row["lthr"],
        "threshold_pace_mps": row["threshold_pace_mps"],
    }


def _list(args, parser: argparse.ArgumentParser) -> int:
    sport = None
    if args.sport:
        try:
            sport = parse_sport(args.sport)
        except ValueError as exc:
            parser.error(str(exc))

    connection = open_database(args.database)
    try:
        thresholds = TrainingRepository(connection).athlete_thresholds()
    finally:
        connection.close()

    if sport is not None:
        thresholds = [row for row in thresholds if row.sport == sport]
    if args.limit is not None:
        thresholds = thresholds[: args.limit]

    if not thresholds:
        print("No threshold snapshots stored.")
        return 0

    width = max(len(row.sport) for row in thresholds)
    print(
        f"{'sport':<{width}}  {'from':<10}  {'max HR':>6}  {'LTHR':>5}  "
        f"{'threshold pace':>14}  source"
    )
    for row in thresholds:
        max_hr = f"{row.max_hr:.0f}" if row.max_hr is not None else "-"
        lthr = f"{row.lthr:.0f}" if row.lthr is not None else "-"
        pace = (
            f"{format_duration_s(1000.0 / row.threshold_pace_mps)} /km"
            if row.threshold_pace_mps
            else "-"
        )
        print(
            f"{row.sport:<{width}}  {row.effective_from.isoformat()}  "
            f"{max_hr:>6}  {lthr:>5}  {pace:>14}  {row.source}"
        )

    return 0
