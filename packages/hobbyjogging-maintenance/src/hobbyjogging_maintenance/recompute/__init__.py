"""Registered recompute tasks. Importing this package registers them."""

from __future__ import annotations

from . import (
    activity_zone_configs_current,
    athlete_thresholds_current,
    race_links_current,
    recompute_canonical,
    training_periods_current,
    verify_canonical,
    workout_classification_queue,
    workout_sets_current,
)

__all__ = [
    "activity_zone_configs_current",
    "athlete_thresholds_current",
    "race_links_current",
    "recompute_canonical",
    "training_periods_current",
    "verify_canonical",
    "workout_classification_queue",
    "workout_sets_current",
]
