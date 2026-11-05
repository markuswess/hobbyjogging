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
from .db.writer import FieldConflict
from .model import (
    Activity,
    ActivityEquipment,
    Equipment,
    Event,
    Interval,
    Lap,
    WellnessDay,
)
from .sports import (
    CANONICAL_SPORTS,
    PACE_SPORTS,
    RIDE_SPORTS,
    RUN_SPORTS,
    SPORT_LABELS,
    canonical_sport,
    is_known_sport,
)

__all__ = [
    "Activity",
    "ActivityEquipment",
    "CANONICAL_SPORTS",
    "DataSource",
    "Equipment",
    "Event",
    "FieldConflict",
    "Interval",
    "Lap",
    "PACE_SPORTS",
    "RIDE_SPORTS",
    "RUN_SPORTS",
    "SCHEMA_VERSION",
    "SPORT_LABELS",
    "TrainingRepository",
    "TrainingWriter",
    "WellnessDay",
    "canonical_sport",
    "connect",
    "default_database_path",
    "is_known_sport",
    "migrate",
    "open_database",
]
