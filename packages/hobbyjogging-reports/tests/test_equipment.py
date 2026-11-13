import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Equipment
from hobbyjogging_report.analysis import (
    equipment_coverage,
    equipment_usage,
    retirement_candidates,
)
from hobbyjogging_report.equipment_report import equipment_report
from support import FakeSource, activity_factory

D = date(2026, 10, 1)
activity = activity_factory()


def _shoe(**overrides):
    values = {
        "id": "shoe-1",
        "type": "shoe",
        "name": "Demo Shoe",
    }
    values.update(overrides)
    return Equipment(**values)


class EquipmentUsageTests(unittest.TestCase):

    def test_mileage_and_sessions_sum_per_item(self):
        shoe = _shoe()
        activities = [
            activity(
                id="a",
                date=D,
                distance_m=7000,
                equipment=[shoe],
            ),
            activity(
                id="b",
                date=D + timedelta(days=20),
                distance_m=5000,
                equipment=[shoe],
            ),
        ]

        stats = equipment_usage([shoe], activities)

        self.assertEqual(1, len(stats))
        self.assertEqual(2, stats[0].sessions)
        self.assertEqual(12000, stats[0].distance_m)
        self.assertEqual(D, stats[0].first_used)
        self.assertEqual(D + timedelta(days=20), stats[0].last_used)
        self.assertAlmostEqual(12000 / 1000 / 0.69, stats[0].km_per_month, places=1)

    def test_shoe_gets_the_default_target_unless_overridden(self):
        default = equipment_usage([_shoe()], [])[0]
        custom = equipment_usage(
            [_shoe(id="shoe-2", target_distance_m=500000)],
            [],
        )[0]

        self.assertEqual(800000, default.target_distance_m)
        self.assertTrue(default.target_is_default)
        self.assertEqual(500000, custom.target_distance_m)
        self.assertFalse(custom.target_is_default)

    def test_gear_without_usage_stays_in_the_table(self):
        stats = equipment_usage([_shoe()], [])

        self.assertEqual(0, stats[0].sessions)
        self.assertIsNone(stats[0].last_used)
        self.assertIsNone(stats[0].km_per_month)
        self.assertEqual(0, stats[0].wear)

    def test_coverage_counts_gear_by_year(self):
        shoe = _shoe()
        activities = [
            activity(id="a", date=D, equipment=[shoe]),
            activity(id="b", date=D, equipment=[]),
            activity(
                id="c",
                date=date(2025, 6, 1),
                equipment=[shoe],
            ),
        ]

        coverage = equipment_coverage(activities)

        self.assertEqual((1, 1), coverage[2026])
        self.assertEqual((1, 0), coverage[2025])

    def test_retirement_candidates_are_active_only(self):
        active = _shoe(id="active", target_distance_m=10000)
        retired = _shoe(
            id="retired",
            retired_on=D,
            target_distance_m=10000,
        )
        stats = equipment_usage(
            [active, retired],
            [
                activity(
                    id="a",
                    date=D,
                    distance_m=12000,
                    equipment=[active],
                ),
                activity(
                    id="b",
                    date=D,
                    distance_m=12000,
                    equipment=[retired],
                ),
            ],
        )

        candidates = retirement_candidates(stats, D)

        self.assertEqual(["active"], [stat.equipment.id for stat, _ in candidates])
        self.assertIn("over target", candidates[0][1])


class EquipmentReportTests(unittest.TestCase):

    def test_report_renders_mileage_and_coverage(self):
        shoe = _shoe(target_distance_m=5000)
        source = FakeSource(
            [activity(id="a", date=D, distance_m=7000, equipment=[shoe])],
            equipment=[shoe],
        )

        report = equipment_report(source, today=D)

        self.assertIn("# Gear", report)
        self.assertIn("| Gear | Type | Sessions | km |", report)
        self.assertIn("| Demo Shoe | shoe | 1 | 7 |", report)
        self.assertIn("## Coverage", report)
        self.assertIn("| 2026 | 1 | 0 |", report)
        self.assertIn("Retirement candidates", report)

    def test_report_without_equipment(self):
        report = equipment_report(FakeSource(), today=D)

        self.assertIn("- No equipment records", report)


if __name__ == "__main__":
    unittest.main()
