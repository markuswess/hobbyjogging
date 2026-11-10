"""Session selection and the detailed single-session report."""

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import activity_sort_key
from .classify import classify
from .format import format_session_activity
from .links import resolve_activity_links
from .recent import search_recent
from .review import exclude_review, review_note
from .sources import create_source

LAST_SELECTORS = {"last", "latest"}


def select_session(
    source,
    selector=None,
    *,
    include_review: bool = False,
    today: date | None = None,
):
    """Resolve a date, activity id, or ``last`` selector.

    Returns ``(day, activities, excluded)``. The selector may be a ``date``,
    a ``YYYY-MM-DD`` string, an activity id, ``last``/``latest``, or ``None``
    for the most recent session.
    """
    today = today or date.today()

    if isinstance(selector, date):
        activities, excluded = exclude_review(
            source.activities(selector, selector),
            include_review=include_review,
        )
        return selector, sorted(activities, key=activity_sort_key), excluded

    text = str(selector).strip() if selector is not None else ""

    if not text or text.lower() in LAST_SELECTORS:
        activities, excluded = search_recent(
            source,
            include_review=include_review,
            today=today,
            enough=bool,
        )

        if activities:
            latest = max(activities, key=activity_sort_key)
            return latest.date, [latest], excluded

        return today, [], excluded

    try:
        day = date.fromisoformat(text)
    except ValueError:
        day = None

    if day is not None:
        activities, excluded = exclude_review(
            source.activities(day, day),
            include_review=include_review,
        )
        return day, sorted(activities, key=activity_sort_key), excluded

    activities, _ = search_recent(
        source,
        include_review=include_review,
        today=today,
        enough=lambda found: any(a.id == text for a in found),
    )

    for activity in activities:
        if activity.id == text:
            return activity.date, [activity], 0

    return None, [], 0


def session_report(
    selector=None,
    source: DataSource | None = None,
    *,
    include_review: bool = False,
    today: date | None = None,
) -> str:
    """Render a detailed report for one date or session.

    ``selector`` accepts a date, an activity id, ``last``, or ``None`` for the
    most recent session.
    """
    if source is None:
        with create_source() as source:
            return session_report(
                selector,
                source,
                include_review=include_review,
                today=today,
            )

    day, activities, excluded = select_session(
        source,
        selector,
        include_review=include_review,
        today=today,
    )

    lines = [f"# Session {day}" if day else "# Session"]

    note = review_note(excluded)
    if note:
        lines.append(note)

    if not activities:
        if (
            isinstance(selector, str)
            and selector.strip().lower() not in LAST_SELECTORS
        ):
            lines.append(
                f"\n- No activity found for `{selector.strip()}`"
            )
            if not include_review:
                lines.append(
                    "- An open import review item may hide it; retry with "
                    "`--include-review`."
                )
        else:
            lines.append("\n- No activity")
        return "\n".join(lines)

    for activity in activities:
        try:
            intervals = source.activity_intervals(activity.id)
        except Exception:
            intervals = []

        category = classify(activity, intervals)

        lines.extend(
            format_session_activity(
                activity,
                intervals,
                category=category.path,
                links=resolve_activity_links(source, activity.id),
            )
        )

    return "\n".join(lines)
