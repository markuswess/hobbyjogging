"""Registered backfills. Importing this package registers every task."""

from . import event_zones, remove_tempo_method_v1, workout_classification

__all__ = [
    "event_zones",
    "remove_tempo_method_v1",
    "workout_classification",
]
