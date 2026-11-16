"""Registered backfills. Importing this package registers every task."""

from . import (
    drop_classification_tags_v1,
    drop_empty_intervals_v1,
    event_race_method_v1,
    fartlek_from_fs_v1,
    event_zones,
    remove_tempo_method_v1,
    workout_classification,
)

__all__ = [
    "drop_classification_tags_v1",
    "drop_empty_intervals_v1",
    "event_race_method_v1",
    "fartlek_from_fs_v1",
    "event_zones",
    "remove_tempo_method_v1",
    "workout_classification",
]
