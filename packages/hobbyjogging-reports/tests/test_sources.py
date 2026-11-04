import os
import unittest
from unittest.mock import patch

from hobbyjogging_report.api import Intervals
from hobbyjogging_report.sources.intervals_api import IntervalsSource, to_activity


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

    def test_equipment_not_exposed_yet(self):
        source = IntervalsSource(client=object())

        self.assertEqual([], source.equipment())

    def test_api_requires_credentials_at_construction(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                Intervals()


if __name__ == "__main__":
    unittest.main()
