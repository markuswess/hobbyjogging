"""Data source adapters and selection."""

from pathlib import Path

from hobbyjogging_core.datasource import DataSource

from .database import DatabaseSource
from .intervals_api import IntervalsSource

DEFAULT_SOURCE = "database"
SOURCE_CHOICES = ("database", "intervals")


def create_source(
    name: str = DEFAULT_SOURCE,
    *,
    database_path: str | Path | None = None,
) -> DataSource:
    """Create a report data source by name."""
    if name == "database":
        return DatabaseSource(path=database_path)

    if name == "intervals":
        return IntervalsSource()

    raise ValueError(f"unknown data source: {name}")
