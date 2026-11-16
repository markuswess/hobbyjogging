"""Registered backfills. Importing this package registers every task."""

from . import (
    activity_device_v1,
    activity_measurements_v1,
    activity_weather_v1,
    drop_classification_tags_v1,
    drop_empty_intervals_v1,
    event_race_method_v1,
    event_zones,
    fartlek_from_fs_v1,
    remove_tempo_method_v1,
    wellness_extras_v1,
    workout_classification,
)

__all__ = [
    "activity_device_v1",
    "activity_measurements_v1",
    "activity_weather_v1",
    "drop_classification_tags_v1",
    "drop_empty_intervals_v1",
    "event_race_method_v1",
    "event_zones",
    "fartlek_from_fs_v1",
    "remove_tempo_method_v1",
    "wellness_extras_v1",
    "workout_classification",
]
