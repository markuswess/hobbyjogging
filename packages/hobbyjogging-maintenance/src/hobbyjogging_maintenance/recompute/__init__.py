"""Registered recompute tasks. Importing this package registers them."""

from . import workout_classification_queue, workout_sets_current

__all__ = ["workout_classification_queue", "workout_sets_current"]
