import os
import unittest
from unittest.mock import patch

from hobbyjogging_report.api import Intervals
from hobbyjogging_report.sources.intervals_api import (
    IntervalsSource,
    to_activity,
    to_event,
)


class IntervalsSourceTests(unittest.TestCase):

    def test_maps_feel(self):
        raw = {
            "id": "a",
            "start_date_local": "2026-10-01T08:00:00",
            "feel": 4,
        }

        self.assertEqual(4, to_activity(raw).feel)

    def test_missing_feel_is_none(self):
        raw = {
            "id": "a",
            "start_date_local": "2026-10-01T08:00:00",
        }

        self.assertIsNone(to_activity(raw).feel)

    def test_maps_start_timestamp(self):
        raw = {
            "id": "a",
            "start_date": "2026-10-01T06:00:00Z",
            "start_date_local": "2026-10-01T08:00:00",
        }

        self.assertEqual(
            "2026-10-01T06:00:00Z",
            to_activity(raw).started_at_utc,
        )

    def test_maps_elapsed_time(self):
        raw = {
            "id": "a",
            "start_date_local": "2026-10-01T08:00:00",
            "elapsed_time": 3900,
        }

        self.assertEqual(3900, to_activity(raw).elapsed_s)

    def test_prefers_recording_time_for_duration(self):
        raw = {
            "id": "a",
            "start_date_local": "2026-10-01T08:00:00",
            "icu_recording_time": 2774,
            "moving_time": 2765,
            "elapsed_time": 2845,
        }

        activity = to_activity(raw)

        self.assertEqual(2774, activity.duration_s)
        self.assertEqual(2765, activity.moving_s)
        self.assertEqual(2845, activity.elapsed_s)

    def test_falls_back_to_moving_time_for_duration(self):
        raw = {
            "id": "a",
            "start_date_local": "2026-10-01T08:00:00",
            "moving_time": 2765,
        }

        activity = to_activity(raw)

        self.assertEqual(2765, activity.duration_s)
        self.assertEqual(2765, activity.moving_s)

    def test_maps_event_plan_fields(self):
        raw = {
            "start_date_local": "2026-10-01T00:00:00",
            "name": "Easy",
            "type": "Run",
            "moving_time": 3000,
            "distance": 9320.4,
            "icu_training_load": 34,
        }

        event = to_event(raw)

        self.assertEqual(3000, event.duration_s)
        self.assertEqual(9320.4, event.distance_m)
        self.assertEqual(34, event.training_load)

    def test_event_duration_falls_back_to_duration(self):
        raw = {
            "start_date_local": "2026-10-01T00:00:00",
            "duration": 1800,
        }

        self.assertEqual(1800, to_event(raw).duration_s)

    def test_equipment_not_exposed_yet(self):
        source = IntervalsSource(client=object())

        self.assertEqual([], source.equipment())

    def test_api_requires_credentials_at_construction(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                Intervals()


if __name__ == "__main__":
    unittest.main()
