"""Interactive lab bench for exploring a metric before it is promoted.

    ./lab.sh
    uv run --env-file .env python -m hobbyjogging_report.shell

Nothing here is imported by the reports: it is a scratchpad over the canonical
database. An idea that survives gets a card in ``docs/METRICS.md`` and is
promoted to ``analysis/`` plus a renderer; everything else is deleted.
"""

from __future__ import annotations

import atexit
import code
import os
from datetime import date, timedelta
from pathlib import Path

import plotly.graph_objects as go

from .analysis import RUN_TYPES
from .sources import create_source

LAB_DIR_ENV = "HOBBYJOGGING_LAB_DIR"
DEFAULT_LAB_DIR = Path("data/lab")

BANNER = """\
hobbyjogging lab
  source                                   read-only DataSource
  activities(days=90, start=, end=, sport=) -> list[Activity]
  wellness(days=90, start=, end=)           -> list[WellnessDay]
  events(days=90, start=, end=)             -> list[Event]
  intervals(activity_id)                    -> list[Interval]
  table(rows, columns=, headers=, limit=40) aligned text table
  save(fig, "name")                         PNG into data/lab/
  go                                        plotly.graph_objects
  RUN_TYPES                                 canonical run sport names

Promote only what survives: docs/METRICS.md.
"""


def lab_dir() -> Path:
    """Directory for throwaway plots (``HOBBYJOGGING_LAB_DIR`` overrides)."""
    value = os.environ.get(LAB_DIR_ENV)
    directory = Path(value).expanduser() if value else DEFAULT_LAB_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    return text if len(text) <= 38 else f"{text[:35]}..."


def _value(row, name):
    if isinstance(row, dict):
        return row.get(name)
    if isinstance(name, int):
        return row[name]
    return getattr(row, name, None)


def table(
    rows,
    *,
    columns=None,
    headers=None,
    limit: int = 40,
) -> None:
    """Print dicts or dataclass-like objects as an aligned table."""
    rows = list(rows)

    if not rows:
        print("(no rows)")
        return

    if columns is None:
        first = rows[0]
        if isinstance(first, dict):
            columns = list(first)
        elif hasattr(first, "__dict__"):
            columns = list(vars(first))
        elif headers:
            columns = list(range(len(first)))
        else:
            columns = []

    if not columns:
        for row in rows[:limit]:
            print(row)
        return

    labels = list(headers) if headers else [str(name) for name in columns]
    cells = [
        [_cell(_value(row, name)) for name in columns]
        for row in rows[:limit]
    ]
    widths = [
        max(len(labels[index]), *(len(row[index]) for row in cells))
        for index in range(len(columns))
    ]

    print(
        "  ".join(label.ljust(widths[i]) for i, label in enumerate(labels))
        .rstrip()
    )
    print("  ".join("-" * width for width in widths).rstrip())
    for row in cells:
        print(
            "  ".join(value.ljust(widths[i]) for i, value in enumerate(row))
            .rstrip()
        )

    if len(rows) > limit:
        print(f"... {len(rows) - limit} more rows")


def save(figure, name: str = "plot") -> Path:
    """Write a plotly figure to ``data/lab/<name>.png`` and return the path."""
    path = lab_dir() / f"{name}.png"
    figure.write_image(str(path), scale=2)
    print(path)
    return path


def build_namespace(source) -> dict[str, object]:
    """The objects bound in the interactive session."""

    def activities(
        days: int = 90,
        *,
        start: date | None = None,
        end: date | None = None,
        sport: str | None = None,
    ):
        end = end or date.today()
        start = start or end - timedelta(days=days - 1)
        found = source.activities(start, end)
        if sport is None:
            return found
        return [activity for activity in found if activity.type == sport]

    def wellness(
        days: int = 90,
        *,
        start: date | None = None,
        end: date | None = None,
    ):
        end = end or date.today()
        start = start or end - timedelta(days=days - 1)
        return source.wellness(start, end)

    def events(
        days: int = 90,
        *,
        start: date | None = None,
        end: date | None = None,
    ):
        end = end or date.today()
        start = start or end - timedelta(days=days - 1)
        return source.events(start, end)

    return {
        "source": source,
        "activities": activities,
        "wellness": wellness,
        "events": events,
        "intervals": source.activity_intervals,
        "table": table,
        "save": save,
        "go": go,
        "RUN_TYPES": RUN_TYPES,
        "today": date.today(),
    }


def main() -> None:
    source = create_source()
    atexit.register(source.close)
    code.interact(banner=BANNER, local=build_namespace(source))


if __name__ == "__main__":
    main()
