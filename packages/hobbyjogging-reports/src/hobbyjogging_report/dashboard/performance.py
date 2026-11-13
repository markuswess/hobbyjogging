"""Dashboard Performance tab: results, PBs, upcoming races, and trend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import quote

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    RaceFilter,
    equivalent_times,
    fit_riegel,
    personal_bests,
    race_results,
    upcoming_races,
)
from ..charts import plot_races
from ..command_support import activity_start
from ..format import fmt_clock, format_pace
from ..html import esc, table
from ..review import exclude_review


@dataclass(frozen=True)
class PerformanceSection:
    """Rendered performance cards for the dashboard."""

    summary_html: str
    upcoming_html: str
    results_html: str
    pbs_html: str
    chart_html: str
    equivalent_html: str
    race_ids: tuple[str, ...] = ()


def race_href(activity_id: str) -> str:
    return f"race/{quote(str(activity_id), safe='')}.html"


def _pace(value: float | None) -> str:
    return "-" if value is None else f"{format_pace(value)}/km"


def _distance(value: float | None) -> str:
    return "-" if not value else f"{value / 1000:.2f} km"


def _time(value: float | None) -> str:
    return "-" if not value else fmt_clock(value)


def build_performance_section(
    source: DataSource,
    *,
    today: date,
    include_review: bool = False,
    future_days: int = 180,
    race_filter: RaceFilter | None = None,
) -> PerformanceSection:
    """Build race results, personal bests, upcoming races, and the chart."""
    race_filter = race_filter or RaceFilter()
    activities, excluded = exclude_review(
        source.activities(activity_start(source, today), today),
        include_review=include_review,
    )
    results = race_filter.filter_results(race_results(activities))
    shown = race_filter.shown(results)
    upcoming = race_filter.filter_upcoming(
        upcoming_races(
            source.events(today, today + timedelta(days=future_days)),
            today,
            days=future_days,
        )
    )
    fit = fit_riegel(results)
    pbs = personal_bests(results)
    predictions = equivalent_times(results, fit)

    summary = (
        f"<p>{len(results)} races, {len(pbs)} distance buckets, "
        f"{len(upcoming)} upcoming.</p>"
    )
    active = race_filter.summary()

    if active:
        summary += f'<p class="muted">Filter: {esc(active)}</p>'
    if len(shown) < len(results):
        summary += (
            f'<p class="muted">Showing the latest {len(shown)} of '
            f"{len(results)} matching races.</p>"
        )
    if excluded:
        summary += (
            f'<p class="muted">{excluded} activities are hidden by import '
            "review.</p>"
        )

    upcoming_html = table(
        ["Date", "Days", "Race", "Distance", "Load"],
        [
            [
                esc(event.date),
                str((event.date - today).days),
                esc(event.name or "-"),
                _distance(event.distance_m),
                "-" if event.training_load is None else f"{event.training_load:.0f}",
            ]
            for event in upcoming
        ],
        numeric=(1, 3, 4),
        empty="No upcoming races.",
    )

    results_html = table(
        ["Date", "Race", "Bucket", "Distance", "Time", "Pace", "HR", "Load"],
        [
            [
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.date)}</a>",
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.name or '-')}</a>",
                esc(result.bucket),
                _distance(result.activity.distance_m),
                _time(result.activity.duration_s),
                _pace(result.pace_s_per_km),
                "-" if result.activity.avg_hr is None
                else f"{result.activity.avg_hr:.0f}",
                "-" if result.activity.training_load is None
                else f"{result.activity.training_load:.0f}",
            ]
            for result in shown
        ],
        numeric=(3, 4, 5, 6, 7),
        empty="No race results.",
    )

    pbs_html = table(
        ["Bucket", "Date", "Race", "Distance", "Time", "Pace"],
        [
            [
                esc(result.bucket),
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.date)}</a>",
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.name or '-')}</a>",
                _distance(result.activity.distance_m),
                _time(result.activity.duration_s),
                _pace(result.pace_s_per_km),
            ]
            for result in pbs
        ],
        numeric=(3, 4, 5),
        empty="No personal bests yet.",
    )

    chart_html = (
        plot_races(results, fit, "", as_html=True)
        if results
        else '<p class="muted">No races to plot.</p>'
    )

    equivalent_html = ""
    if predictions:
        equivalent_html = (
            (
                f"<p>Riegel exponent {fit.exponent:.2f} "
                f"(R² = {fit.r2:.2f}, n={fit.points}).</p>"
            )
            if fit
            else ""
        ) + table(
            ["Distance", "Predicted", "PB"],
            [
                [label, _time(predicted), _time(pb)]
                for label, predicted, pb in predictions
            ],
            numeric=(1, 2),
        )
    else:
        equivalent_html = (
            '<p class="muted">Not enough races for a Riegel estimate.</p>'
        )

    return PerformanceSection(
        summary_html=summary,
        upcoming_html=upcoming_html,
        results_html=results_html,
        pbs_html=pbs_html,
        chart_html=chart_html,
        equivalent_html=equivalent_html,
        race_ids=tuple(result.activity.id for result in results),
    )
