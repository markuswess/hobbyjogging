"""Data source adapters."""

from pathlib import Path

from hobbyjogging_core.datasource import DataSource

from .database import DatabaseSource


def create_source(*, database_path: str | Path | None = None) -> DataSource:
    """Create the canonical-database data source."""
    return DatabaseSource(path=database_path)
