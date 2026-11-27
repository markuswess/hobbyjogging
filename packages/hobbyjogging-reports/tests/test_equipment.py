import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Equipment
from hobbyjogging_report.analysis import (
    equipment_coverage,
    equipment_detail,
    equipment_usage,
    retirement_candidates,
    select_equipment,
)
from hobbyjogging_report.equipment_report import equipment_report, gear_report
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
        self.assertIn("## Shoes", report)
        self.assertIn(
            "| Gear | Sessions | km | km/month | Last used | "
            "Target | Wear | Status | Notes |",
            report,
        )
        self.assertIn("| Demo Shoe | 1 | 7 |", report)
        self.assertIn("## Coverage", report)
        self.assertIn("| 2026 | 1 | 0 |", report)
        self.assertIn("Retirement candidates", report)

    def test_report_separates_shoes_bikes_and_other(self):
        shoe = _shoe(id="shoe", name="Shoe")
        bike = Equipment(id="bike", type="bike", name="Bike")
        other = Equipment(id="other", type="other", name="Gym")
        source = FakeSource(
            [
                activity(
                    id="a",
                    date=D,
                    distance_m=10000,
                    equipment=[shoe],
                ),
                activity(
                    id="b",
                    date=D,
                    type="ride",
                    distance_m=30000,
                    equipment=[bike],
                ),
            ],
            equipment=[shoe, bike, other],
        )

        report = equipment_report(source, today=D)

        self.assertIn(
            "3 items: 3 active, 0 retired "
            "(1 shoe, 1 bike, 1 other).",
            report,
        )
        self.assertLess(report.index("## Shoes"), report.index("## Bikes"))
        self.assertLess(report.index("## Bikes"), report.index("## Other"))
        self.assertIn("| Bike | 1 | 30 |", report)
        self.assertIn("| Gym | 0 | 0 |", report)

    def test_report_without_equipment(self):
        report = equipment_report(FakeSource(), today=D)

        self.assertIn("- No equipment records", report)


class EquipmentDetailTests(unittest.TestCase):

    def test_monthly_mileage_and_activities_are_newest_first(self):
        shoe = _shoe()
        activities = [
            activity(
                id="old",
                date=date(2026, 8, 9),
                distance_m=8000,
                equipment=[shoe],
            ),
            activity(
                id="new",
                date=date(2026, 9, 1),
                distance_m=5000,
                equipment=[shoe],
            ),
            activity(
                id="other",
                date=date(2026, 9, 2),
                distance_m=9000,
                equipment=[],
            ),
        ]
        stats = equipment_usage([shoe], activities)
        detail = equipment_detail(stats[0], activities, [shoe])

        self.assertEqual(
            [("2026-08-01", 8.0), ("2026-09-01", 5.0)],
            [(str(month), km) for month, km in detail.monthly],
        )
        self.assertEqual(
            ["new", "old"],
            [entry.activity.id for entry in detail.activities],
        )
        self.assertEqual([], detail.co_used)

    def test_co_used_gear_counts_sessions(self):
        shoe = _shoe()
        other = Equipment(id="katy", type="shoe", name="Katy")
        activities = [
            activity(
                id="a",
                date=D,
                equipment=[shoe, other],
            ),
            activity(
                id="b",
                date=D + timedelta(days=1),
                equipment=[shoe, other],
            ),
            activity(
                id="c",
                date=D + timedelta(days=2),
                equipment=[shoe],
            ),
        ]
        detail = equipment_detail(
            equipment_usage([shoe], activities)[0],
            activities,
            [shoe, other],
        )

        self.assertEqual([("Katy", 2)], [(item.name, n) for item, n in detail.co_used])
        self.assertEqual(
            [(), ("katy",), ("katy",)],
            [
                tuple(item.id for item in entry.others)
                for entry in detail.activities
            ],
        )

    def test_unused_gear_has_no_monthly_series(self):
        detail = equipment_detail(
            equipment_usage([_shoe()], [])[0],
            [],
            [_shoe()],
        )

        self.assertEqual([], detail.monthly)
        self.assertEqual([], detail.activities)


class SelectEquipmentTests(unittest.TestCase):

    def test_id_and_substring_both_resolve(self):
        shoe = _shoe(id="shoe-1")
        bike = Equipment(id="bike-1", type="bike", name="Road Bike")

        self.assertIs(shoe, select_equipment([shoe, bike], "shoe-1"))
        self.assertIs(bike, select_equipment([shoe, bike], "road"))

    def test_an_ambiguous_name_lists_the_candidates(self):
        first = _shoe(id="shoe-1", name="Daily Shoe")
        second = _shoe(id="shoe-2", name="Daily Shoe Two")

        with self.assertRaises(ValueError) as caught:
            select_equipment([first, second], "daily")

        self.assertIn("ambiguous", str(caught.exception))
        self.assertIn("shoe-1", str(caught.exception))
        self.assertIn("shoe-2", str(caught.exception))

    def test_an_unknown_name_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            select_equipment([_shoe()], "nothing")

        self.assertIn("no gear matches", str(caught.exception))


class GearReportTests(unittest.TestCase):

    def _source(self, **overrides):
        shoe = _shoe(target_distance_m=5000, notes="Retired pair")
        other = Equipment(id="katy", type="shoe", name="Katy")
        activities = [
            activity(
                id="a",
                date=date(2026, 8, 9),
                name="Easy",
                distance_m=7000,
                duration_s=2100,
                equipment=[shoe, other],
            ),
            activity(
                id="b",
                date=date(2026, 9, 1),
                name="Tempo",
                distance_m=5000,
                duration_s=1200,
                equipment=[shoe],
            ),
        ]
        values = {
            "activities": activities,
            "equipment": [shoe, other],
        }
        values.update(overrides)
        return FakeSource(**values)

    def test_report_matches_the_gear_totals(self):
        report = gear_report(self._source(), "demo shoe", today=D)

        self.assertIn("# Gear — Demo Shoe", report)
        self.assertIn("| Sessions | km | km/month |", report)
        self.assertIn("| 2 | 12 |", report)
        self.assertIn("| 5 km |", report)
        self.assertIn("## Monthly mileage", report)
        self.assertIn("| 2026-08 | 7.0 | 7.0 |", report)
        self.assertIn("| 2026-09 | 5.0 | 12.0 |", report)
        self.assertIn("## Activities", report)
        self.assertIn("| 2026-09-01 | Tempo | 5.0 | 4:00/km | - |", report)
        self.assertIn("| 2026-08-09 | Easy | 7.0 | 5:00/km | Katy |", report)
        self.assertIn("## Co-used gear", report)
        self.assertIn("- Katy: 1 session", report)
        self.assertIn("## Notes", report)

    def test_report_without_sessions_has_empty_states(self):
        report = gear_report(
            self._source(activities=[]),
            "demo shoe",
            today=D,
        )

        self.assertIn("- No sessions recorded.", report)
        self.assertIn("- No co-used gear.", report)
        self.assertIn("| 0 | 0 |", report)

    def test_report_refuses_an_unknown_item(self):
        with self.assertRaises(ValueError):
            gear_report(self._source(), "nothing", today=D)


if __name__ == "__main__":
    unittest.main()
