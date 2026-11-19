"""Dashboard Performance tab: results, PBs, upcoming races, and trend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import quote

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    bucket_label,
    equivalent_times,
    fit_riegel,
    official_by_activity,
    pb_progressions,
    personal_bests,
    race_results,
    upcoming_races,
    vo2max_methods,
)
from ..charts import plot_pb_progressions, plot_races, plot_vo2max_methods
from ..command_support import activity_start
from ..format import fmt_clock, format_pace, format_place
from ..html import esc, table
from ..review import exclude_review


@dataclass(frozen=True)
class PerformanceSection:
    """Rendered performance cards for the dashboard."""

    summary_html: str
    upcoming_html: str
    results_html: str
    pbs_html: str
    pb_html: str
    chart_html: str
    equivalent_html: str
    vo2max_html: str
    race_ids: tuple[str, ...] = ()


def race_href(activity_id: str) -> str:
    return f"race/{quote(str(activity_id), safe='')}.html"


def _pace(value: float | None) -> str:
    return "-" if value is None else f"{format_pace(value)}/km"


def _distance(value: float | None) -> str:
    return "-" if not value else f"{value / 1000:.2f} km"


def _time(value: float | None) -> str:
    return "-" if not value else fmt_clock(value)


def _measured(value: str, *, official: bool) -> str:
    """Italicise a measured value; an official value stays plain."""
    return value if official else f"<em>{value}</em>"


def build_performance_section(
    source: DataSource,
    *,
    today: date,
    include_review: bool = False,
    future_days: int = 180,
) -> PerformanceSection:
    """Build race results, personal bests, upcoming races, and the charts."""
    start = activity_start(source, today)
    activities, excluded = exclude_review(
        source.activities(start, today),
        include_review=include_review,
    )
    results = race_results(
        activities,
        official_by_activity(source.race_results()),
    )
    upcoming = upcoming_races(
        source.events(today, today + timedelta(days=future_days)),
        today,
        days=future_days,
    )
    fit = fit_riegel(results)
    pbs = personal_bests(results)
    progressions = pb_progressions(results)
    predictions = equivalent_times(results, fit)

    summary = (
        f"<p>{len(results)} races, {len(pbs)} distance buckets, "
        f"{len(upcoming)} upcoming.</p>"
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
        [
            "Date",
            "Session",
            "Race",
            "Bucket",
            "Distance",
            "Time",
            "Pace",
            "Place",
            "AG",
        ],
        [
            [
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.date)}</a>",
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.name or '-')}</a>",
                esc(result.official_name or "-"),
                esc(result.bucket),
                _measured(
                    _distance(result.distance_m),
                    official=result.official_used,
                ),
                _measured(
                    _time(result.time_s),
                    official=result.official_used,
                ),
                _pace(result.pace_s_per_km),
                format_place(
                    result.place_overall,
                    result.participants_overall,
                ),
                format_place(
                    result.place_ageclass,
                    result.participants_ageclass,
                ),
            ]
            for result in results
        ],
        numeric=(4, 5, 6, 7, 8),
        empty="No race results.",
        collapse="races",
    )

    if any(not result.official_used for result in results):
        results_html += (
            '<p class="muted">Values in italics are measured, not official; '
            "the rest use the official race result.</p>"
        )

    pbs_html = table(
        [
            "Bucket",
            "Date",
            "Session",
            "Race",
            "Distance",
            "Time",
            "Pace",
        ],
        [
            [
                esc(bucket_label(result.bucket)),
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.date)}</a>",
                f'<a href="{race_href(result.activity.id)}">'
                f"{esc(result.activity.name or '-')}</a>",
                esc(result.official_name or "-"),
                _measured(
                    _distance(result.distance_m),
                    official=result.official_used,
                ),
                _measured(
                    _time(result.time_s),
                    official=result.official_used,
                ),
                _pace(result.pace_s_per_km),
            ]
            for result in pbs
        ],
        numeric=(4, 5, 6),
        empty="No personal bests yet.",
        collapse="pbs",
    )

    if any(not result.official_used for result in pbs):
        pbs_html += (
            '<p class="muted">Values in italics are measured, not '
            "official.</p>"
        )

    chart_html = (
        plot_races(results, fit, "", as_html=True)
        if results
        else '<p class="muted">No races to plot.</p>'
    )
    pb_html = (
        plot_pb_progressions(progressions, "", as_html=True)
        if progressions
        else '<p class="muted">No PB progression yet.</p>'
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
            ["Distance", "Predicted", "Pace", "PB", "PB pace"],
            [
                [
                    row.label,
                    _time(row.predicted_s),
                    _pace(row.predicted_pace_s_per_km),
                    _time(row.pb_s),
                    _pace(row.pb_pace_s_per_km),
                ]
                for row in predictions
            ],
            numeric=(1, 2, 3, 4),
        ) + (
            '<p class="muted">PB paces use the official distance where a '
            "race result provides one, otherwise the measured activity "
            "distance.</p>"
        )
    else:
        equivalent_html = (
            '<p class="muted">Not enough races for a Riegel estimate.</p>'
        )

    methods = vo2max_methods(
        activities,
        source.athlete_thresholds(),
        source.devices(),
        results,
        start,
        today,
    )
    has_vo2max = any(
        (
            methods.all_runs,
            methods.steady,
            methods.garmin,
            methods.runalyze,
            methods.races,
        )
    )
    if has_vo2max:
        vo2max_html = plot_vo2max_methods(methods, "", as_html=True) + (
            '<p class="muted">All runs use pace and HR/max HR; the steady '
            "40–75 min series drops quality work, recovery jogs and trail "
            "runs. Garmin stays one series per recording device (the latest "
            "device also gets its 42-day line), Runalyze keeps its stored "
            "0.93 correction, and race VDOT uses official road results.</p>"
        )
    else:
        vo2max_html = (
            '<p class="muted">No pace and heart-rate data for the '
            "estimate.</p>"
        )

    return PerformanceSection(
        summary_html=summary,
        upcoming_html=upcoming_html,
        results_html=results_html,
        pbs_html=pbs_html,
        pb_html=pb_html,
        chart_html=chart_html,
        equivalent_html=equivalent_html,
        vo2max_html=vo2max_html,
        race_ids=tuple(result.activity.id for result in results),
    )
