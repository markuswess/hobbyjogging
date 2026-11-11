"""Table of recent activities with selectable columns."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import Activity

from .analysis import (
    activity_efficiency,
    activity_sort_key,
    is_lt1_activity,
    is_subt_activity,
)
from .classify import classify
from .cli import range_parser, resolve_range
from .format import (
    fmt_time,
    format_feel,
    format_methods,
    format_targets,
    pace,
    sport_label,
    table_text,
)
from .review import exclude_review, review_note
from .recent import search_recent

DEFAULT_LIMIT = 20
DEFAULT_RANGE_DAYS = 30


@dataclass(frozen=True)
class Column:
    header: str
    value: Callable[[Activity, str], str]
    numeric: bool = False


def _plain(header: str, fn: Callable[[Activity], str], numeric: bool = False):
    return Column(header, lambda activity, _category: fn(activity), numeric)


def _optional(value, fmt: Callable[[object], str]) -> str:
    return "-" if value is None else fmt(value)


def _started(activity: Activity) -> str:
    text = activity.started_at_utc
    return text[11:16] if len(text) >= 16 else "-"


def _distance(activity: Activity) -> str:
    if not activity.distance_m:
        return "-"
    return f"{activity.distance_m / 1000:.2f} km"


COLUMNS = {
    "id": _plain("id", lambda a: a.id),
    "date": _plain("date", lambda a: str(a.date)),
    "started": _plain("started (UTC)", _started),
    "sport": _plain("sport", sport_label),
    "name": _plain("name", lambda a: a.name or "-"),
    "duration": _plain("duration", lambda a: fmt_time(a.duration_s), True),
    "elapsed": _plain("elapsed", lambda a: fmt_time(a.elapsed_s), True),
    "distance": _plain("distance", _distance, True),
    "pace": _plain("pace", pace, True),
    "avg_hr": _plain(
        "avg HR",
        lambda a: _optional(a.avg_hr, lambda v: f"{v:.0f}"),
        True,
    ),
    "load": _plain(
        "load",
        lambda a: _optional(a.training_load, lambda v: f"{v:.0f}"),
        True,
    ),
    "rpe": _plain(
        "RPE",
        lambda a: _optional(a.rpe, lambda v: f"{v:g}"),
        True,
    ),
    "feel": _plain("feel", lambda a: format_feel(a.feel)),
    "intensity": _plain(
        "intensity",
        lambda a: _optional(a.intensity, lambda v: f"{v:.0%}"),
        True,
    ),
    "eff": _plain(
        "eff",
        lambda a: _optional(activity_efficiency(a), lambda v: f"{v:.2f}"),
    ),
    "category": Column(
        "category",
        lambda _activity, category: category or "-",
    ),
    "methods": _plain("methods", format_methods),
    "targets": _plain("targets", format_targets),
}

DEFAULT_COLUMNS = (
    "date",
    "sport",
    "name",
    "duration",
    "distance",
    "pace",
    "avg_hr",
    "load",
    "rpe",
    "feel",
    "methods",
    "targets",
)


@dataclass(frozen=True)
class ActivityQuery:
    """Selection and column choice for the activities table."""

    start: date | None = None
    end: date | None = None
    limit: int | None = None
    columns: tuple[str, ...] = DEFAULT_COLUMNS


def _split(text: str | None) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def resolve_columns(columns: str | None, add: str | None) -> tuple[str, ...]:
    """Return the requested columns: ``--columns`` replaces, ``--add`` appends."""
    if columns is not None and add is not None:
        raise ValueError("use either --columns or --add, not both")

    if columns is not None:
        names = _split(columns)
    else:
        names = [*DEFAULT_COLUMNS, *_split(add)]

    if not names:
        raise ValueError("no columns selected")

    unknown = [name for name in names if name not in COLUMNS]
    if unknown:
        raise ValueError(
            f"unknown column(s): {', '.join(unknown)} "
            f"(available: {', '.join(COLUMNS)})"
        )

    return tuple(dict.fromkeys(names))


def parse_activities_args(
    argv: list[str],
    today: date | None = None,
) -> ActivityQuery:
    """Parse range, limit, and column options for the activities table."""
    parser = range_parser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--columns")
    parser.add_argument("--add")
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")

    columns = resolve_columns(args.columns, args.add)

    if args.days_option is None and args.start is None and args.end is None:
        return ActivityQuery(limit=args.limit, columns=columns)

    days = (
        args.days_option
        if args.days_option is not None
        else DEFAULT_RANGE_DAYS
    )
    start, end = resolve_range(days, args.start, args.end, today=today)

    return ActivityQuery(start, end, args.limit, columns)


def select_activities(
    source: DataSource,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    include_review: bool = False,
    today: date | None = None,
) -> tuple[list[Activity], int]:
    """Return activities newest first, and the review-excluded count.

    Without a range, look back in widening windows until ``limit`` (default
    20) activities are found.
    """
    if start is None:
        limit = limit or DEFAULT_LIMIT
        today = today or date.today()

        activities, excluded = search_recent(
            source,
            include_review=include_review,
            today=today,
            enough=lambda found: len(found) >= limit,
        )
    else:
        activities, excluded = exclude_review(
            source.activities(start, end),
            include_review=include_review,
        )

    activities = sorted(activities, key=activity_sort_key, reverse=True)

    if limit is not None:
        activities = activities[:limit]

    return activities, excluded


def _category_path(source: DataSource, activity: Activity) -> str:
    intervals = []

    if is_subt_activity(activity) or is_lt1_activity(activity):
        try:
            intervals = source.activity_intervals(activity.id)
        except Exception:
            intervals = []

    return classify(activity, intervals).path


def activities_report(
    source: DataSource,
    query: ActivityQuery,
    *,
    include_review: bool = False,
    today: date | None = None,
) -> str:
    """Render a Markdown table of activities with the requested columns."""
    activities, excluded = select_activities(
        source,
        start=query.start,
        end=query.end,
        limit=query.limit,
        include_review=include_review,
        today=today,
    )

    if query.start is None:
        scope = f"last {query.limit or DEFAULT_LIMIT} activities"
    else:
        scope = f"{query.start} → {query.end}"
        if query.limit:
            scope += f", at most {query.limit}"

    lines = ["# Activities", scope]

    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    if not activities:
        lines.append("\n- No activities")
        return "\n".join(lines)

    headers = [COLUMNS[name].header for name in query.columns]
    alignment = [
        "---:" if COLUMNS[name].numeric else "---"
        for name in query.columns
    ]

    lines.append("")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(alignment) + "|")

    for activity in activities:
        category = (
            _category_path(source, activity)
            if "category" in query.columns
            else ""
        )
        cells = [
            table_text(COLUMNS[name].value(activity, category))
            for name in query.columns
        ]
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)
