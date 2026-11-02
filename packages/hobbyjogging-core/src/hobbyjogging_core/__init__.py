"""Canonical training model and shared database helpers."""

from .datasource import DataSource
from .db import (
    SCHEMA_VERSION,
    TrainingRepository,
    TrainingWriter,
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
    Lap,
    WellnessDay,
)

__all__ = [
    "Activity",
    "ActivityEquipment",
    "DataSource",
    "Equipment",
    "Event",
    "Interval",
    "Lap",
    "SCHEMA_VERSION",
    "TrainingRepository",
    "TrainingWriter",
    "WellnessDay",
    "connect",
    "default_database_path",
    "migrate",
    "open_database",
]
