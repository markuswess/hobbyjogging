import unittest
from datetime import date

from hobbyjogging_core import TrainingRepository, connect, migrate


class TrainingRepositoryTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.repository = TrainingRepository(self.conn)
        self._seed()

    def _seed(self):
        self.conn.executemany(
            """
            INSERT INTO activities (
                id, local_date, sport, name, description,
                duration_s, distance_m, avg_hr, training_load,
                rpe, feel, intensity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "a1", "2026-10-01", "run", "Morning run", "Easy",
                    3600, 10000, 140, 50, 4, 2, 0.8,
                ),
                (
                    "a2", "2026-10-02", "ride", "Evening ride", "",
                    1800, 20000, 130, 30, None, None, 0.6,
                ),
                (
                    "a3", "2026-10-05", "run", "Weekend run", "",
                    5400, 15000, 145, 70, 5, 3, 0.85,
                ),
            ],
        )
        self.conn.executemany(
            "INSERT INTO zone_configs (id, kind, boundaries_json) "
            "VALUES (?, ?, ?)",
            [
                ("pace-zones", "pace", "[]"),
                ("hr-zones", "hr", "[]"),
            ],
        )
        self.conn.execute(
            "UPDATE activities SET pace_zone_config_id = 'pace-zones', "
            "hr_zone_config_id = 'hr-zones' WHERE id = 'a1'"
        )
        self.conn.executemany(
            "INSERT INTO activity_zone_times "
            "(activity_id, kind, zone_index, seconds) VALUES (?, ?, ?, ?)",
            [
                ("a1", "pace", 1, 600),
                ("a1", "pace", 3, 30),
                ("a1", "hr", 1, 1800),
                ("a1", "hr", 2, 1800),
            ],
        )
        self.conn.executemany(
            "INSERT INTO equipment "
            "(id, type, name, brand, model, acquired_on, retired_on, "
            "target_distance_m) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("shoe-1", "shoe", "Pegasus 40", "Nike", "Pegasus 40",
                 "2026-01-01", None, 800000),
                ("shoe-2", "shoe", "Boston 12", "Adidas", "Boston 12",
                 None, None, 700000),
                ("bike-1", "bike", "Road bike", "", "", None, None, None),
            ],
        )
        self.conn.executemany(
            "INSERT INTO activity_equipment "
            "(activity_id, equipment_id, role) VALUES (?, ?, ?)",
            [
                ("a1", "shoe-1", "primary"),
                ("a1", "shoe-2", "secondary"),
                ("a2", "bike-1", "primary"),
            ],
        )
        self.conn.executemany(
            "INSERT INTO activity_intervals "
            "(activity_id, interval_index, group_id, type, start_time, "
            "duration_s, distance_m, avg_hr, max_hr) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("a1", 2, "g2", "RECOVERY", "00:10:00", 120, 300, 120, 130),
                ("a1", 1, "g1", "WORK", "00:05:00", 60, 200, 150, 160),
            ],
        )
        self.conn.executemany(
            "INSERT INTO wellness_days "
            "(local_date, hrv, resting_hr, sleep_s) VALUES (?, ?, ?, ?)",
            [
                ("2026-10-01", 60, 50, 28800),
                ("2026-10-03", 55, 52, 25200),
            ],
        )
        self.conn.executemany(
            "INSERT INTO events "
            "(id, local_date, name, type, description, duration_s, distance_m) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("e1", "2026-10-02", "Town race", "race", "", 1800, 5000),
                ("e2", "2026-10-06", "Long run", "training", "", None, 30000),
            ],
        )

    def test_activities_are_filtered_and_mapped(self):
        activities = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )

        self.assertEqual(["a1", "a2"], [activity.id for activity in activities])
        first = activities[0]
        self.assertEqual(date(2026, 10, 1), first.date)
        self.assertEqual("run", first.type)
        self.assertEqual("Morning run", first.name)
        self.assertEqual(3600, first.duration_s)
        self.assertEqual(10000, first.distance_m)
        self.assertEqual(140, first.avg_hr)
        self.assertEqual(50, first.training_load)
        self.assertEqual(4, first.rpe)
        self.assertEqual(2, first.feel)
        self.assertEqual(0.8, first.intensity)
        self.assertEqual([600, 0, 30], first.pace_zone_times)
        self.assertEqual([1800, 1800], first.hr_zone_times)
        self.assertEqual(
            ["shoe-1", "shoe-2"],
            [item.id for item in first.equipment],
        )

    def test_activities_are_ordered_by_start_time_within_a_day(self):
        self.conn.executemany(
            "INSERT INTO activities "
            "(id, local_date, started_at_utc, sport) VALUES (?, ?, ?, ?)",
            [
                ("late", "2026-10-03", "2026-10-03T17:00:00", "run"),
                ("early", "2026-10-03", "2026-10-03T08:00:00", "run"),
            ],
        )

        activities = self.repository.activities(
            date(2026, 10, 3),
            date(2026, 10, 3),
        )

        self.assertEqual(["early", "late"], [a.id for a in activities])
        self.assertEqual(
            "2026-10-03T08:00:00",
            activities[0].started_at_utc,
        )

    def test_empty_activity_range_returns_empty_list(self):
        self.assertEqual(
            [],
            self.repository.activities(date(2025, 1, 1), date(2025, 1, 2)),
        )

    def test_wellness_is_filtered_and_mapped(self):
        wellness = self.repository.wellness(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )

        self.assertEqual(1, len(wellness))
        self.assertEqual(date(2026, 10, 1), wellness[0].date)
        self.assertEqual(60, wellness[0].hrv)
        self.assertEqual(50, wellness[0].resting_hr)
        self.assertEqual(28800, wellness[0].sleep_s)

    def test_events_are_filtered_and_mapped(self):
        events = self.repository.events(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )

        self.assertEqual(1, len(events))
        self.assertEqual(date(2026, 10, 2), events[0].date)
        self.assertEqual("Town race", events[0].name)
        self.assertEqual("race", events[0].type)
        self.assertEqual(1800, events[0].duration_s)
        self.assertEqual(5000, events[0].distance_m)

    def test_activity_intervals_are_ordered_by_index(self):
        intervals = self.repository.activity_intervals("a1")

        self.assertEqual(2, len(intervals))
        self.assertEqual("WORK", intervals[0].type)
        self.assertEqual("g1", intervals[0].group_id)
        self.assertEqual(60, intervals[0].duration_s)
        self.assertEqual("RECOVERY", intervals[1].type)

    def test_equipment_is_sorted_and_mapped(self):
        equipment = self.repository.equipment()

        self.assertEqual(
            ["bike-1", "shoe-2", "shoe-1"],
            [item.id for item in equipment],
        )
        shoe = equipment[2]
        self.assertEqual("shoe", shoe.type)
        self.assertEqual("Nike", shoe.brand)
        self.assertEqual(date(2026, 1, 1), shoe.acquired_on)
        self.assertIsNone(shoe.retired_on)
        self.assertEqual(800000, shoe.target_distance_m)


if __name__ == "__main__":
    unittest.main()
