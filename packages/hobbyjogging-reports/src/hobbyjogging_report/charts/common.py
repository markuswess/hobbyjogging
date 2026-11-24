"""Shared Plotly helpers, tokens and import-time setup for the charts."""

from __future__ import annotations

from datetime import date, timedelta
import math
import warnings

import plotly.graph_objects as go

from hobbyjogging_core.model import TrainingPeriod

from ..analysis import SUBT_CATEGORIES
from ..defaults import COMPARE_COLOR_ANCHOR_YEAR
from ..model import AverageWindows
from ..style import (
    AXIS_HEADROOM,
    AXIS_TAIL,
    CLIPPED_COLOR,
    LINE_STYLES,
    PROJECTED_OPACITY,
    PERIOD_LABEL_COLOR,
    SPIKE_COLOR,
)

warnings.filterwarnings(
    "ignore",
    message=r"(?s).*Kaleido versions less than 1\.0\.0.*",
    category=DeprecationWarning,
)

PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
}

AVERAGE_COLORS = {
    "base": "#1f77b4",
    "fitness": "#ff7f0e",
    "fatigue": "#d62728",
}

VOLUME_BAR_COLOR = "lightgrey"
LOAD_BAR_COLOR = "#b0bec5"
CROSS_LOAD_COLOR = "#d8cfc2"

ZONE_COLORS = (
    "#8ecae6",
    "#219ebc",
    "#ffb3b3",
    "#ff6b6b",
    "#e63946",
)
ZONE_LINE_COLORS = (
    "#0077b6",
    "#023e8a",
    "#d00000",
    "#9d0208",
    "#6a040f",
)
SUBT_COLORS = {
    "short": "#1f77b4",
    "medium": "#ff7f0e",
    "long": "#2ca02c",
    "lt1": "#9467bd",
}
CHART_CATEGORIES = (*SUBT_CATEGORIES, "lt1")
WEEK_MS = 7 * 24 * 60 * 60 * 1000

COMPARE_COLORS = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
    "#c49c94",
    "#f7b6d2",
    "#c7c7c7",
    "#dbdb8d",
    "#9edae5",
)

VO2MAX_DEVICE_COLORS = (
    "#e45756",
    "#4c78a8",
    "#9467bd",
    "#8c564b",
    "#bcbd22",
)

PACE_HR_SYMBOLS = {
    "easy": "circle",
    "recovery": "diamond",
    "intervals": "square",
    "longrun": "triangle-up",
    "race": "star",
    "tempo": "cross",
    "fartlek": "pentagon",
    "race-support": "triangle-down",
    "other": "x",
}

PACE_HR_CATEGORY_ORDER = tuple(PACE_HR_SYMBOLS)

PACE_HR_SYMBOL_TEXT = {
    "easy": "○",
    "recovery": "◇",
    "intervals": "□",
    "longrun": "△",
    "race": "★",
    "tempo": "+",
    "fartlek": "⬟",
    "race-support": "▽",
    "other": "×",
}

PB_COLORS = {
    "5k": "#1f77b4",
    "10k": "#ff7f0e",
    "HM": "#2ca02c",
    "M": "#d62728",
}

def compare_color(year: int) -> str:
    """A stable per-year compare colour, strongest contrast for recent years.

    The palette runs backwards from the anchor year, so the newest years get
    the saturated colours and old years fade out. A year keeps one colour
    across every compare chart and the colour does not depend on the plotted
    range. Move the anchor forward when the data does; each year beyond it
    takes the next (lighter) colour, so bump it before the palette wraps.
    """
    return COMPARE_COLORS[
        (COMPARE_COLOR_ANCHOR_YEAR - year) % len(COMPARE_COLORS)
    ]


def _fade(color: str, alpha: float) -> str:
    """The same colour at reduced opacity, for planned or ghost marks."""
    if not color.startswith("#") or len(color) != 7:
        return color

    return "rgba({}, {}, {}, {})".format(
        *(int(color[index:index + 2], 16) for index in (1, 3, 5)),
        alpha,
    )


def _darker(color: str, factor: float = 0.6) -> str:
    """Darken a hex colour so a line stays legible over pale markers."""
    if not color.startswith("#") or len(color) != 7:
        return color

    return "rgb({}, {}, {})".format(
        *(
            int(int(color[index:index + 2], 16) * factor)
            for index in (1, 3, 5)
        )
    )


def _require_data(*series) -> None:
    if not any(series):
        raise ValueError("no data to plot")


def _two_decimal_hover(figure: go.Figure) -> None:
    """Keep hover values compact; the default shows full float precision."""
    for key in figure.layout:
        if key.startswith("yaxis"):
            figure.layout[key].hoverformat = ".2f"


def _render(
    figure: go.Figure,
    output: str,
    *,
    as_html: bool,
    width: int,
    height: int,
) -> str:
    figure.update_xaxes(automargin=True)
    figure.update_yaxes(automargin=True)
    _two_decimal_hover(figure)

    if as_html:
        return figure.to_html(
            full_html=False,
            include_plotlyjs=False,
            config=PLOTLY_CONFIG,
        )

    figure.write_image(output, width=width, height=height)
    return output


def _add(figure, trace, *, row: int | None = None, col: int | None = None):
    if row is None:
        figure.add_trace(trace)
    else:
        figure.add_trace(trace, row=row, col=col)


def _legend_below(
    *,
    font_size: int | None = None,
    columns: int | None = None,
) -> dict:
    legend = {
        "orientation": "h",
        "y": -0.07,
        "yanchor": "top",
        "x": 0,
    }

    if font_size is not None:
        legend["font"] = {"size": font_size}
    if columns:
        legend["entrywidth"] = round(1 / columns, 4)
        legend["entrywidthmode"] = "fraction"
        # A wrapped horizontal legend otherwise fills in reverse trace order.
        legend["traceorder"] = "normal"

    return legend


def _crosshair(figure, *, second_y: bool = False) -> None:
    """A vertical guide on the nearest day and a horizontal one at the cursor."""
    spikes = {
        "showspikes": True,
        "spikemode": "across",
        "spikethickness": 1,
        "spikecolor": SPIKE_COLOR,
        "spikedash": "dot",
    }

    # x snaps to the data so a day stays marked; y follows the pointer so a
    # value can be read anywhere, not only at a plotted point.
    figure.update_xaxes(**spikes, spikesnap="data")
    figure.update_yaxes(**spikes, spikesnap="cursor")

    if second_y:
        figure.update_layout(
            yaxis2={**spikes, "spikesnap": "cursor"},
        )


def _base_layout(figure, *, title: str, xlabel: str, ylabel: str):
    figure.update_layout(
        template="plotly_white",
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        # Planned bars stack on the actual bar of the same week; the grouped
        # default would place them side by side instead.
        barmode="overlay",
        height=800,
        margin={"l": 60, "r": 30, "t": 60, "b": 100},
        legend=_legend_below(),
        hovermode="x unified",
    )


def _plot_average_lines(
    figure,
    points,
    windows: AverageWindows,
    *,
    scale: float = 1.0,
    label,
    colors: dict[str, str] | None = None,
    dash: dict[str, str] | None = None,
    row: int | None = None,
    col: int | None = None,
    yaxis: str | None = None,
    projection_label: str = "avg projection",
):
    actual = [point for point in points if not point.projected]
    projected = [point for point in points if point.projected]
    colors = colors or AVERAGE_COLORS
    dash = {
        attribute: LINE_STYLES[getattr(windows, attribute)]
        for attribute in ("base", "fitness", "fatigue")
    } | (dash or {})

    series = []

    # Shortest window first, so the smoothest line ends up on top.
    for attribute in ("fatigue", "fitness", "base"):
        style = {
            "color": colors[attribute],
            "width": 2,
        }

        if attribute in dash:
            style["dash"] = dash[attribute]

        if actual:
            series.append((
                [point.date for point in actual],
                [getattr(point, attribute) * scale for point in actual],
                style,
                1.0,
                label(attribute, getattr(windows, attribute)),
                True,
            ))

        if projected:
            bridge = actual[-1:] + projected
            series.append((
                [point.date for point in bridge],
                [
                    getattr(point, attribute) * scale
                    for point in bridge
                ],
                {**style, "dash": "dash"},
                PROJECTED_OPACITY,
                label(attribute, getattr(windows, attribute)),
                False,
            ))

    # All halos go down before any line, so a later halo cannot cut an
    # earlier line at a crossing; the pale halo is what keeps a line legible
    # over the bars.
    for x, y, style, _opacity, _name, _show in series:
        _outline(
            figure,
            x,
            y,
            style["width"],
            row=row,
            col=col,
            yaxis=yaxis,
        )

    for x, y, style, opacity, name, showlegend in series:
        _add(
            figure,
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=name,
                line=style,
                opacity=opacity,
                showlegend=showlegend,
                yaxis=yaxis,
            ),
            row=row,
            col=col,
        )

    if projected:
        _add(
            figure,
            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name=projection_label,
                line={
                    "color": AVERAGE_COLORS["base"],
                    "width": 2,
                    "dash": "dash",
                },
            ),
            row=row,
            col=col,
        )


def _bulk_range(values, *, step: float) -> list[float] | None:
    """Round a range around the bulk, so an extreme value cannot flatten it."""
    ordered = sorted(value for value in values if value is not None)

    if not ordered:
        return None

    dropped = max(1, round(AXIS_TAIL * (len(ordered) - 1)))
    low = ordered[min(dropped, len(ordered) - 1)]
    high = ordered[max(0, len(ordered) - 1 - dropped)]

    return [
        step * math.floor(low / AXIS_HEADROOM / step),
        step * math.ceil(high * AXIS_HEADROOM / step),
    ]


def _axis_ceiling(
    values,
    *,
    step: float,
    floor: float,
    tail: float = AXIS_TAIL,
) -> float:
    """Round an axis ceiling up from the bulk of the values, not the peak.

    The top ``tail`` share of the values is dropped (always at least one), so a
    single ultra week or long day cannot set the axis; what is left gets a
    little headroom and rounds up to ``step``, which leaves the typical bar
    comfortably inside the frame. Later values above the result are drawn
    clipped and marked.
    """
    ordered = sorted(value for value in values if value is not None)

    if not ordered:
        return floor

    dropped = max(1, round(tail * (len(ordered) - 1)))
    upper = ordered[max(0, len(ordered) - 1 - dropped)]

    return max(floor, step * math.ceil(upper * AXIS_HEADROOM / step))


def _clipped_markers(
    figure,
    points: list[tuple[object, float]],
    limit: float,
    unit: str,
    *,
    row: int | None = None,
    col: int | None = None,
    number: str = ".2f",
):
    """Mark values that exceed the axis ceiling instead of hiding them."""
    clipped = [
        (where, value)
        for where, value in points
        if value > limit
    ]

    if not clipped:
        return

    _add(
        figure,
        go.Scatter(
            x=[where for where, _ in clipped],
            y=[limit * 0.98] * len(clipped),
            mode="markers",
            marker={
                "symbol": "triangle-up",
                "size": 9,
                "color": CLIPPED_COLOR,
            },
            name=f"clipped above {limit:g} {unit}",
            hovertext=[
                f"{value:{number}} {unit} (bar clipped)"
                for _, value in clipped
            ],
            hoverinfo="text",
        ),
        row=row,
        col=col,
    )


def _period_bands(
    figure,
    periods: list[TrainingPeriod] | None,
    *,
    kind: str,
    color: str,
    start: date,
    end: date,
    bottom: float,
    top: float,
    labels: bool = False,
    mark_start: bool = False,
    start_color: str = PERIOD_LABEL_COLOR,
    row: int | None = None,
    col: int | None = None,
) -> None:
    """Shade training periods of one kind behind a date-axis chart.

    ``mark_start`` adds a faint vertical line where a period begins, but only
    when the beginning is inside the visible range; a band already underway at
    the left edge gets no marker.
    """
    for period in periods or []:
        if period.kind != kind or period.start_date is None:
            continue

        first = max(period.start_date, start)
        last = min(period.end_date or end, end)

        if last < first:
            continue

        label = period.label.strip() or period.kind.title()
        span = (
            f"{period.start_date} \u2192 {period.end_date}"
            if period.end_date
            else f"{period.start_date} \u2192 ongoing"
        )
        hover = f"{label}: {span}"
        trace = go.Scatter(
            x=[
                first,
                first,
                last + timedelta(days=1),
                last + timedelta(days=1),
            ],
            y=[bottom, top, top, bottom],
            fill="toself",
            mode="lines",
            line={"width": 0},
            fillcolor=color,
            hoveron="fills",
            hoverinfo="text",
            name=hover,
            text=hover,
            showlegend=False,
        )
        _add(figure, trace, row=row, col=col)

        if mark_start and start <= period.start_date <= end:
            marker = {
                "type": "line",
                "x0": period.start_date,
                "x1": period.start_date,
                "y0": bottom,
                "y1": top,
                "line": {
                    "color": start_color,
                    "width": 1,
                    "dash": "dot",
                },
                "layer": "below",
            }
            if row is None:
                figure.add_shape(**marker)
            else:
                figure.add_shape(**marker, row=row, col=col)

        if labels:
            annotation = {
                "x": first,
                "y": top,
                "text": label,
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "top",
                "font": {"size": 10, "color": PERIOD_LABEL_COLOR},
            }
            if row is None:
                figure.add_annotation(**annotation)
            else:
                figure.add_annotation(**annotation, row=row, col=col)

def _outline(
    figure,
    x: list,
    y: list,
    width: float,
    *,
    row: int | None = None,
    col: int | None = None,
    yaxis: str | None = None,
) -> None:
    """A pale halo under an EWMA line so it reads over the bars."""
    _add(
        figure,
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            line={"color": "rgba(255, 255, 255, 0.85)", "width": width + 2.5},
            hoverinfo="skip",
            showlegend=False,
            yaxis=yaxis,
        ),
        row=row,
        col=col,
    )
