"""Registered backfills. Importing this package registers every task."""

from . import (
    event_race_method_v1,
    event_zones,
    remove_tempo_method_v1,
    workout_classification,
)

__all__ = [
    "event_race_method_v1",
    "event_zones",
    "remove_tempo_method_v1",
    "workout_classification",
]
