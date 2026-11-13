import math
import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Event, EventZoneTime, Lap
from hobbyjogging_report.analysis import (
    RaceFilter,
    equivalent_times,
    fit_riegel,
    half_split,
    personal_bests,
    race_bucket,
    race_results,
    upcoming_races,
)
from hobbyjogging_report.race_report import race_report, races_report
from support import FakeSource, activity_factory

D = date(2026, 10, 1)
activity = activity_factory()


def _race(**overrides):
    values = {
        "type": "run",
        "workout_methods": ["race"],
        "workout_targets": ["speed"],
    }
    values.update(overrides)
    return activity(**values)


class RaceAnalysisTests(unittest.TestCase):

    def test_race_detection_uses_methods_or_targets(self):
        results = race_results(
            [
                _race(id="a", date=D, distance_m=5000, duration_s=1200),
                activity(id="b", date=D, distance_m=5000),
            ]
        )

        self.assertEqual(["a"], [result.activity.id for result in results])

    def test_distance_buckets_accept_short_courses(self):
        self.assertEqual(
            "5k",
            race_bucket(_race(distance_m=4200)),
        )
        self.assertEqual(
            "5k",
            race_bucket(_race(distance_m=4910)),
        )
        self.assertEqual(
            "10k",
            race_bucket(_race(distance_m=9880)),
        )
        self.assertEqual(
            "Trail",
            race_bucket(_race(type="trail_run", distance_m=6360)),
        )

    def test_personal_bests_pick_the_fastest_per_bucket(self):
        results = race_results(
            [
                _race(id="slow", date=D, distance_m=5000, duration_s=1300),
                _race(
                    id="fast",
                    date=D + timedelta(days=1),
                    distance_m=5000,
                    duration_s=1200,
                ),
            ]
        )

        pbs = personal_bests(results)

        self.assertEqual(["5k"], [result.bucket for result in pbs])
        self.assertEqual("fast", pbs[0].activity.id)

    def test_upcoming_races_are_future_and_bounded(self):
        events = [
            Event(date=D, name="Today", workout_methods=["race"]),
            Event(
                date=D + timedelta(days=10),
                name="Soon",
                workout_methods=["race"],
            ),
            Event(
                date=D + timedelta(days=400),
                name="Far",
                workout_methods=["race"],
            ),
            Event(date=D + timedelta(days=11), name="Training"),
        ]

        upcoming = upcoming_races(events, D, days=180)

        self.assertEqual(["Today", "Soon"], [event.name for event in upcoming])

    def test_riegel_fit_recovers_a_synthetic_exponent(self):
        results = race_results(
            [
                _race(
                    id=str(distance),
                    date=D,
                    distance_m=distance,
                    duration_s=60 * (distance / 1000) ** 1.06 * 4,
                )
                for distance in (5000, 10000, 21097, 42195)
            ]
        )

        fit = fit_riegel(results)

        self.assertIsNotNone(fit)
        self.assertAlmostEqual(1.06, fit.exponent, places=2)
        self.assertAlmostEqual(1.0, fit.r2, places=3)
        self.assertAlmostEqual(
            60 * (10 ** 1.06) * 4,
            fit.duration_s(10000),
            places=4,
        )

    def test_equivalent_times_use_the_latest_10k(self):
        results = race_results(
            [
                _race(
                    id="10k",
                    date=D,
                    distance_m=10000,
                    duration_s=2400,
                ),
                _race(
                    id="5k",
                    date=D,
                    distance_m=5000,
                    duration_s=1200,
                ),
                _race(
                    id="hm",
                    date=D - timedelta(days=10),
                    distance_m=21097,
                    duration_s=5400,
                ),
            ]
        )
        fit = fit_riegel(results)

        rows = equivalent_times(results, fit)

        self.assertEqual(["5k", "10k", "HM", "M"], [row[0] for row in rows])
        self.assertAlmostEqual(2400 * (0.5) ** fit.exponent, rows[0][1])

    def test_half_split_uses_lap_midpoint(self):
        split = half_split(
            [
                Lap(index=1, duration_s=600, distance_m=2500),
                Lap(index=2, duration_s=660, distance_m=2500),
            ]
        )

        self.assertAlmostEqual(240, split.first_pace_s_per_km)
        self.assertAlmostEqual(264, split.second_pace_s_per_km)
        self.assertAlmostEqual(24, split.delta_s_per_km)


class RaceReportTests(unittest.TestCase):

    def _source(self):
        return FakeSource(
            [
                _race(
                    id="a",
                    date=D,
                    name="Spring 5k",
                    distance_m=5000,
                    duration_s=1200,
                    avg_hr=175,
                    pace_zone_times=[0, 0, 300, 900],
                ),
                _race(
                    id="b",
                    date=D - timedelta(days=5),
                    name="Autumn 10k",
                    distance_m=10000,
                    duration_s=2400,
                ),
                _race(
                    id="c",
                    date=D - timedelta(days=15),
                    name="Half",
                    distance_m=21097,
                    duration_s=5400,
                ),
                _race(
                    id="d",
                    date=date(2025, 10, 1),
                    name="Old 5k",
                    distance_m=5000,
                    duration_s=1250,
                ),
            ],
            events=[
                Event(
                    date=D,
                    name="Future 5k",
                    type="run",
                    duration_s=1150,
                    distance_m=5000,
                    workout_methods=["race"],
                    zone_kind="pace",
                    zone_times=[
                        EventZoneTime("Z1", 0, 1),
                        EventZoneTime("Z2", 0, 2),
                        EventZoneTime("Z3", 300, 3),
                        EventZoneTime("Z4", 900, 4),
                    ],
                )
            ],
        )

    def test_races_report_renders_bests_and_estimates(self):
        report = races_report(self._source(), today=D)

        self.assertIn("# Races", report)
        self.assertIn("## Results", report)
        self.assertIn("Spring 5k", report)
        self.assertIn("20:00", report)
        self.assertIn("## Personal bests", report)
        self.assertIn("Riegel estimate", report)

    def test_bucket_filter_applies_to_results_and_pbs(self):
        report = races_report(
            self._source(),
            filters=RaceFilter(bucket="10k"),
            today=D,
        )
        results = report.split("## Personal bests")[0]
        pbs = report.split("## Personal bests")[1]

        self.assertIn("Filter: bucket 10k", report)
        self.assertIn("Autumn 10k", results)
        self.assertNotIn("Spring 5k", results)
        self.assertNotIn("Half", results)
        self.assertIn("| 10k |", pbs)
        self.assertNotIn("| 5k |", pbs)
        # The upcoming list is not bucket-filtered.
        self.assertIn("Future 5k", results)

    def test_year_filter_scopes_results_and_upcoming(self):
        report = races_report(
            self._source(),
            filters=RaceFilter(
                start=date(2025, 1, 1),
                end=date(2025, 12, 31),
            ),
            today=D,
        )

        self.assertIn("Old 5k", report)
        self.assertNotIn("Autumn 10k", report)
        self.assertNotIn("Future 5k", report)
        self.assertIn("Filter: 2025-01-01 → 2025-12-31", report)

    def test_limit_caps_rows_but_pbs_use_all_matches(self):
        report = races_report(
            self._source(),
            filters=RaceFilter(limit=2),
            today=D,
        )
        results = report.split("## Personal bests")[0]
        pbs = report.split("## Personal bests")[1]

        self.assertIn("Spring 5k", results)
        self.assertIn("Autumn 10k", results)
        self.assertNotIn("Half", results)
        self.assertIn("Showing the latest 2 of 4 matching races.", report)
        self.assertIn("| HM |", pbs)

    def test_empty_filter_still_shows_upcoming(self):
        report = races_report(
            self._source(),
            filters=RaceFilter(bucket="M"),
            today=D,
        )

        self.assertIn("Filter: bucket M", report)
        self.assertIn("No race results found.", report)
        self.assertNotIn("## Personal bests", report)
        self.assertIn("Future 5k", report)

    def test_empty_year_filter_hides_upcoming(self):
        report = races_report(
            self._source(),
            filters=RaceFilter(
                start=date(2024, 1, 1),
                end=date(2024, 12, 31),
            ),
            today=D,
        )

        self.assertIn("- No races found", report)
        self.assertNotIn("Future 5k", report)

    def test_race_report_includes_plan_and_execution(self):
        report = race_report("a", self._source(), today=D)

        self.assertIn("# Race 2026-10-01", report)
        self.assertIn("Spring 5k", report)
        self.assertIn("- Time: 20:00", report)
        self.assertIn("### Planned vs actual zones", report)
        self.assertIn("### Plan", report)


if __name__ == "__main__":
    unittest.main()
