import os
import unittest

# The API client reads credentials at import time; no requests are made here.
os.environ.setdefault("INTERVALS_ATHLETE_ID", "test")
os.environ.setdefault("INTERVALS_API_KEY", "test")

from intervals_report.sources.intervals_api import IntervalsSource, to_activity


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

    def test_equipment_not_exposed_yet(self):
        source = IntervalsSource(client=object())

        self.assertEqual([], source.equipment())


if __name__ == "__main__":
    unittest.main()
