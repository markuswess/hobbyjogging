"""Session selection and the detailed single-session report."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import (
    Activity,
    Device,
    Event,
    Interval,
    Lap,
    ReviewItem,
    WellnessDay,
)

from .analysis import activity_sort_key
from .classify import classify
from .command_support import resting_hr_lookup
from .format import format_session_activity
from .links import resolve_activity_links
from .recent import search_recent
from .review import exclude_review, review_note
from .sources import create_source

LAST_SELECTORS = {"last", "latest"}


class RestingHrLookup(Protocol):
    """The callable returned by :func:`resting_hr_lookup`."""

    def __call__(self, day: date) -> float | None: ...

    def estimated(self, day: date) -> bool: ...


@dataclass
class SessionRenderContext:
    """Source lookups shared by the CLI and the dashboard pages.

    ``day_events`` and ``day_wellness`` are filled lazily so a dashboard
    build asks once per date instead of once per activity.
    """

    baseline: RestingHrLookup
    open_review: list[ReviewItem]
    devices: dict[str, Device]
    day_events: dict[date, list[Event]] = field(default_factory=dict)
    day_wellness: dict[date, WellnessDay | None] = field(default_factory=dict)

    def events_for(self, source: DataSource, day: date) -> list[Event]:
        if day not in self.day_events:
            self.day_events[day] = source.events(day, day)

        return self.day_events[day]

    def wellness_for(
        self,
        source: DataSource,
        day: date,
    ) -> WellnessDay | None:
        if day not in self.day_wellness:
            rows = source.wellness(day, day)
            self.day_wellness[day] = rows[0] if rows else None

        return self.day_wellness[day]


def build_session_context(
    source: DataSource,
    *,
    start: date,
    end: date,
) -> SessionRenderContext:
    """Preload the lookups one session render needs."""
    return SessionRenderContext(
        baseline=resting_hr_lookup(source, start, end, backfill=True),
        open_review=source.review_items(status="open"),
        devices={device.id: device for device in source.devices()},
    )


def session_activity_lines(
    source: DataSource,
    activity: Activity,
    context: SessionRenderContext,
    *,
    intervals: list[Interval],
    laps: list[Lap],
    planned_events: list[Event],
    planned_hrefs: dict[str, str] | None = None,
) -> list[str]:
    """Render one activity's detailed Markdown block.

    The CLI session report, the dashboard activity page and the race page use
    this one path, so source lookups and fields cannot drift between them.
    """
    return format_session_activity(
        activity,
        intervals,
        category=classify(activity, intervals).path,
        links=resolve_activity_links(source, activity.id),
        resting_hr=context.baseline(activity.date),
        resting_hr_estimated=context.baseline.estimated(activity.date),
        planned_events=planned_events,
        planned_hrefs=planned_hrefs,
        weather=source.activity_weather(activity.id),
        metrics=source.activity_metrics(activity.id),
        device=context.devices.get(activity.device_id),
        wellness=context.wellness_for(source, activity.date),
        review_items=[
            item
            for item in context.open_review
            if item.activity_id == activity.id
        ],
        laps=laps,
        social=source.activity_social(activity.id),
    )


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

    session_day = day or activities[0].date
    context = build_session_context(
        source,
        start=session_day,
        end=session_day,
    )

    for activity in activities:
        try:
            intervals = source.activity_intervals(activity.id)
        except Exception:
            intervals = []

        lines.extend(
            session_activity_lines(
                source,
                activity,
                context,
                intervals=intervals,
                laps=source.activity_laps(activity.id),
                planned_events=context.events_for(
                    source,
                    activity.date,
                ),
            )
        )

    return "\n".join(lines)
