import unittest
from datetime import date

from hobbyjogging_core import Activity, ActivityEquipment, Equipment, Lap


class EquipmentModelTests(unittest.TestCase):

    def test_equipment_defaults(self):
        shoe = Equipment(id="shoe-1", type="shoe", name="Pegasus 40")

        self.assertEqual("", shoe.brand)
        self.assertEqual("", shoe.model)
        self.assertIsNone(shoe.acquired_on)
        self.assertIsNone(shoe.retired_on)
        self.assertIsNone(shoe.target_distance_m)

    def test_activity_equipment_defaults_to_empty_list(self):
        first = Activity(id="a1", date=date(2026, 10, 1))
        second = Activity(id="a2", date=date(2026, 10, 2))

        first.equipment.append(Equipment(id="shoe-1", type="shoe", name="Pegasus 40"))

        self.assertEqual(1, len(first.equipment))
        self.assertEqual([], second.equipment)

    def test_activity_equipment_link_defaults(self):
        link = ActivityEquipment(activity_id="a1", equipment_id="shoe-1")

        self.assertEqual("primary", link.role)
        self.assertEqual("manual", link.source)
        self.assertFalse(link.is_manual)

    def test_started_local_uses_the_recorded_offset(self):
        activity = Activity(
            id="a1",
            date=date(2026, 10, 1),
            started_at_utc="2026-10-01T06:00:00Z",
            tz_offset_min=120,
        )

        self.assertEqual(
            "2026-10-01T08:00:00+02:00",
            activity.started_local,
        )

    def test_started_local_falls_back_to_utc_without_an_offset(self):
        activity = Activity(
            id="a1",
            date=date(2026, 10, 1),
            started_at_utc="2026-10-01T06:00:00Z",
        )

        self.assertEqual("2026-10-01T06:00:00Z", activity.started_local)

    def test_started_local_keeps_the_utc_string_when_unparseable(self):
        activity = Activity(
            id="a1",
            date=date(2026, 10, 1),
            started_at_utc="not-a-timestamp",
            tz_offset_min=60,
        )

        self.assertEqual("not-a-timestamp", activity.started_local)

    def test_lap_defaults(self):
        lap = Lap(index=1)

        self.assertEqual("", lap.start_time_utc)
        self.assertEqual(0, lap.duration_s)
        self.assertEqual(0, lap.distance_m)
        self.assertIsNone(lap.avg_hr)
        self.assertIsNone(lap.max_hr)
        self.assertIsNone(lap.elevation_gain_m)


if __name__ == "__main__":
    unittest.main()
