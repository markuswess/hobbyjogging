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

from .values import format_duration_s, parse_pace_mps, parse_sport


def run_threshold(args, parser: argparse.ArgumentParser) -> int:
    action = args.threshold_action

    if action == "add":
        return _add(args, parser)
    if action == "list":
        return _list(args, parser)

    parser.error(f"unknown threshold command: {action}")
    return 1


def _add(args, parser: argparse.ArgumentParser) -> int:
    try:
        sport = parse_sport(args.sport)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        effective = date.fromisoformat(
            args.effective_from or date.today().isoformat()
        )
    except ValueError as exc:
        parser.error(f"invalid date: {exc}")

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
        TrainingWriter(connection).set_manual_threshold(
            effective,
            sport,
            **values,
        )
        connection.commit()
    finally:
        connection.close()

    print(f"threshold saved: {sport} from {effective}")
    return 0


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
