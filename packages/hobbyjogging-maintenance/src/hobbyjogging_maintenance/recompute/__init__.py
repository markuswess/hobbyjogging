"""Registered recompute tasks. Importing this package registers them."""

from . import (
    activity_zone_configs_current,
    athlete_thresholds_current,
    race_links_current,
    training_periods_current,
    workout_classification_queue,
    workout_sets_current,
)

__all__ = [
    "activity_zone_configs_current",
    "athlete_thresholds_current",
    "race_links_current",
    "training_periods_current",
    "workout_classification_queue",
    "workout_sets_current",
]
