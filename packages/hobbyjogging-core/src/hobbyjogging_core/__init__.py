"""Canonical training model and shared database helpers."""

from .datasource import DataSource
from .db import (
    SCHEMA_VERSION,
    TrainingRepository,
    connect,
    default_database_path,
    migrate,
    open_database,
)
from .model import (
    Activity,
    ActivityEquipment,
    Equipment,
    Event,
    Interval,
    WellnessDay,
)

__all__ = [
    "Activity",
    "ActivityEquipment",
    "DataSource",
    "Equipment",
    "Event",
    "Interval",
    "SCHEMA_VERSION",
    "TrainingRepository",
    "WellnessDay",
    "connect",
    "default_database_path",
    "migrate",
    "open_database",
]
