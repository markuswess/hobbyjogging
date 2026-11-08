import unittest
from datetime import date

from hobbyjogging_core.model import Event, EventZoneTime
from hobbyjogging_report.planned import planned_report
from support import FakeSource

D1 = date(2026, 11, 6)
D2 = date(2026, 11, 8)


class PlannedReportTests(unittest.TestCase):

    def test_renders_one_row_per_planned_workout(self):
        source = FakeSource(
            events=[
                Event(
                    date=D2,
                    name="Long run",
                    type="run",
                    distance_m=21000,
                    duration_s=7200,
                    training_load=120,
                ),
                Event(
                    date=D1,
                    name="Easy",
                    type="run",
                    distance_m=8000,
                    duration_s=3000,
                    training_load=40,
                ),
            ]
        )

        report = planned_report(D1, D2, source)

        self.assertIn("# Planned Workouts", report)
        self.assertIn(
            "| Date | Day | Workout | Sport | Distance | Time | Z3+4 | Load |",
            report,
        )
        self.assertIn(
            "| 2026-11-06 | Fri | Easy | Run | 8.0 km | 50min | - | 40 |",
            report,
        )
        self.assertIn(
            "| 2026-11-08 | Sun | Long run | Run | 21.0 km | 2h00 | - | 120 |",
            report,
        )
        self.assertLess(report.index("Easy"), report.index("Long run"))
        self.assertNotIn("Z3+4 uses", report)

    def test_skips_notes_without_a_sport(self):
        source = FakeSource(
            events=[Event(date=D1, name="Travel", description="Away")]
        )

        report = planned_report(D1, D1, source)

        self.assertIn("- No planned sessions", report)
        self.assertNotIn("Travel", report)
        self.assertNotIn("| Date |", report)

    def test_empty_range_has_no_table(self):
        report = planned_report(D1, D2, FakeSource())

        self.assertIn("- No planned sessions", report)
        self.assertNotIn("| Date |", report)

    def test_missing_facts_are_dashes_and_pipes_are_escaped(self):
        source = FakeSource(
            events=[Event(date=D1, name="A | B", type="ride")]
        )

        report = planned_report(D1, D1, source)

        self.assertIn(
            "| 2026-11-06 | Fri | A / B | Ride | - | - | - | - |",
            report,
        )

    def test_z3_plus_z4_column_sums_only_those_zones(self):
        source = FakeSource(
            events=[
                Event(
                    date=D1,
                    name="5x5 subT",
                    type="run",
                    zone_kind="pace",
                    zone_times=[
                        EventZoneTime("Z1", 600, 1),
                        EventZoneTime("Z3", 1500, 3),
                        EventZoneTime("Z4", 300, 4),
                        EventZoneTime("Z5", 900, 5),
                        EventZoneTime("SS", 120, None),
                    ],
                )
            ]
        )

        report = planned_report(D1, D1, source)

        self.assertIn(
            "| 2026-11-06 | Fri | 5x5 subT | Run | - | - | 30min | - |",
            report,
        )
        self.assertIn(
            "Z3+4 uses each event's planned zone kind "
            "(pace, HR, or power).",
            report,
        )

    def test_zone_column_shows_zero_when_z3_plus_z4_is_empty(self):
        source = FakeSource(
            events=[
                Event(
                    date=D1,
                    name="Easy",
                    type="run",
                    zone_kind="pace",
                    zone_times=[
                        EventZoneTime("Z1", 3000, 1),
                    ],
                )
            ]
        )

        report = planned_report(D1, D1, source)

        self.assertIn(
            "| 2026-11-06 | Fri | Easy | Run | - | - | 0min | - |",
            report,
        )


if __name__ == "__main__":
    unittest.main()
