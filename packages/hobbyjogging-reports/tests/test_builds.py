import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Event, EventZoneTime
from hobbyjogging_report.analysis import (
    MARATHON_WEEKS,
    RaceResult,
    marathon_builds,
    week_start,
)
from hobbyjogging_report.builds_report import (
    marathon_builds_report,
    marathon_builds_table,
)
from support import FakeSource, activity_factory

RACE_DAY = date(2026, 10, 4)  # Sunday
TODAY = date(2026, 11, 24)
UPCOMING = date(2027, 1, 3)  # Sunday, 40 days out

run = activity_factory()


def marathon_activity(**overrides):
    values = dict(
        id="marathon",
        date=RACE_DAY,
        name="",
        distance_m=42195,
        duration_s=3 * 3600 + 600,
        pace_zone_times=[600, 900, 1200, 900],
        workout_methods=["race"],
    )
    values.update(overrides)
    return run(**values)


def marathon_result(activity=None):
    activity = activity or marathon_activity()

    return RaceResult(
        activity=activity,
        bucket="M",
        pace_s_per_km=300,
        distance_m=42195,
        time_s=activity.duration_s,
    )


class MarathonBuildTests(unittest.TestCase):

    def test_only_marathon_results_and_the_next_event_are_built(self):
        half = run(
            id="half",
            date=RACE_DAY - timedelta(days=90),
            distance_m=21097.5,
            duration_s=5400,
            workout_methods=["race"],
        )
        results = [
            RaceResult(
                activity=half,
                bucket="HM",
                pace_s_per_km=255,
                distance_m=21097.5,
                time_s=5400,
            ),
            marathon_result(),
        ]
        upcoming = Event(
            id="next",
            date=UPCOMING,
            name="Spring Marathon",
            type="run",
            distance_m=42195,
            workout_methods=["race"],
        )

        builds = marathon_builds(
            [half, marathon_activity()],
            results,
            [upcoming],
            TODAY,
        )

        self.assertEqual(
            ["Marathon", "Spring Marathon"],
            [build.name for build in builds],
        )
        self.assertFalse(builds[0].planned)
        self.assertTrue(builds[1].planned)

    def test_each_build_has_the_default_eighteen_weeks(self):
        builds = marathon_builds(
            [marathon_activity()],
            [marathon_result()],
            [],
            TODAY,
        )
        weeks = builds[0].weeks

        self.assertEqual(MARATHON_WEEKS, len(weeks))
        self.assertEqual("T-17", weeks[0].label)
        self.assertEqual("T-0", weeks[-1].label)
        self.assertEqual(
            week_start(RACE_DAY) - timedelta(days=7 * 17),
            weeks[0].week_start,
        )

    def test_weekly_actual_volume_time_fast_and_quality(self):
        previous = RACE_DAY - timedelta(days=8)
        activities = [
            marathon_activity(),
            run(
                id="easy",
                date=previous,
                name="Easy",
                distance_m=10000,
                duration_s=3600,
                pace_zone_times=[1800, 1200, 600, 0],
                workout_targets=["base"],
            ),
            run(
                id="quality",
                date=previous + timedelta(days=1),
                name="Intervals",
                distance_m=8000,
                duration_s=2400,
                pace_zone_times=[600, 300, 1200, 300],
                workout_methods=["intervals"],
                workout_targets=["vo2max"],
            ),
        ]

        builds = marathon_builds(
            activities,
            [marathon_result()],
            [],
            TODAY,
        )
        weeks = {week.label: week for week in builds[0].weeks}

        self.assertEqual(42.195, weeks["T-0"].distance_km)
        self.assertEqual(3 * 3600 + 600, weeks["T-0"].time_s)
        self.assertEqual(2100, weeks["T-0"].fast_s)
        self.assertEqual(1, weeks["T-0"].quality)

        self.assertEqual(18.0, weeks["T-1"].distance_km)
        self.assertEqual(6000, weeks["T-1"].time_s)
        self.assertEqual(2100, weeks["T-1"].fast_s)
        self.assertEqual(1, weeks["T-1"].quality)

    def test_a_future_week_with_a_plan_shows_planned_values(self):
        planned_day = date(2026, 12, 7)
        events = [
            Event(
                id="planned",
                date=planned_day,
                name="Threshold",
                type="run",
                distance_m=15000,
                duration_s=4500,
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 600, 1),
                    EventZoneTime("Z2", 600, 2),
                    EventZoneTime("Z3", 900, 3),
                    EventZoneTime("Z4", 300, 4),
                ],
                workout_methods=["intervals"],
                workout_targets=["threshold"],
            ),
            Event(
                id="race",
                date=UPCOMING,
                name="Spring Marathon",
                type="run",
                distance_m=42195,
                workout_methods=["race"],
            ),
        ]

        builds = marathon_builds(
            [],
            [],
            events,
            TODAY,
        )
        weeks = {week.label: week for week in builds[0].weeks}
        week = weeks["T-3"]

        self.assertTrue(week.planned)
        self.assertEqual(15.0, week.planned_distance_km)
        self.assertEqual(4500, week.planned_time_s)
        self.assertEqual(1200, week.planned_fast_s)
        self.assertEqual(1, week.planned_quality)

    def test_a_past_week_of_the_upcoming_build_shows_actual_values(self):
        past = run(
            id="past",
            date=TODAY - timedelta(days=2),
            distance_m=12000,
            duration_s=4200,
            workout_targets=["base"],
        )
        events = [
            Event(
                id="race",
                date=UPCOMING,
                name="Spring Marathon",
                type="run",
                distance_m=42195,
                workout_methods=["race"],
            )
        ]

        builds = marathon_builds([past], [], events, TODAY)
        weeks = {week.label: week for week in builds[0].weeks}
        current = weeks["T-6"]

        self.assertFalse(current.planned)
        self.assertTrue(current.has_data)
        self.assertEqual(12.0, current.distance_km)

    def test_a_long_run_plan_is_not_an_upcoming_race(self):
        events = [
            Event(
                id="long",
                date=UPCOMING,
                name="Long run",
                type="run",
                distance_m=42195,
                workout_methods=["long_run"],
            )
        ]

        self.assertEqual([], marathon_builds([], [], events, TODAY))

    def test_weeks_must_be_positive(self):
        with self.assertRaises(ValueError):
            marathon_builds([], [], [], TODAY, weeks=0)

    def test_the_table_has_one_row_per_week_plus_a_total(self):
        builds = marathon_builds(
            [marathon_activity()],
            [marathon_result()],
            [],
            TODAY,
        )
        headers, rows = marathon_builds_table(builds)

        self.assertEqual("Week", headers[0])
        self.assertIn("Marathon", headers[1])
        self.assertEqual(19, len(rows))
        self.assertEqual("T-17", rows[0][0])
        self.assertEqual("T-0", rows[-2][0])
        self.assertEqual("Total", rows[-1][0])
        self.assertIn("42 · 3h10 · 35min · 1", rows[-2][1])

    def test_the_table_marks_planned_cells(self):
        events = [
            Event(
                id="race",
                date=UPCOMING,
                name="Spring Marathon",
                type="run",
                distance_m=42195,
                duration_s=3 * 3600,
                workout_methods=["race"],
            )
        ]
        builds = marathon_builds([], [], events, TODAY)
        headers, rows = marathon_builds_table(builds)

        self.assertIn("(planned)", headers[1])
        self.assertIn("42 · 3h00 · - · 1 *", rows[-1][1])


class MarathonBuildReportTests(unittest.TestCase):

    def test_the_report_renders_the_build_table(self):
        source = FakeSource(
            [marathon_activity()],
            events=[
                Event(
                    id="race",
                    date=UPCOMING,
                    name="Spring Marathon",
                    type="run",
                    distance_m=42195,
                    workout_methods=["race"],
                )
            ],
        )

        report = marathon_builds_report(source, today=TODAY)

        self.assertIn("# Marathon builds", report)
        self.assertIn("18-week blocks", report)
        self.assertIn("| Week |", report)
        self.assertIn("| T-17 |", report)
        self.assertIn("| Total |", report)
        self.assertIn("(planned)", report)
        self.assertIn("quality sessions", report)

    def test_the_report_handles_no_builds(self):
        report = marathon_builds_report(FakeSource([]), today=TODAY)

        self.assertIn("No marathon results or upcoming marathon.", report)
        self.assertNotIn("| Week |", report)

    def test_the_report_rejects_a_bad_window(self):
        with self.assertRaises(ValueError):
            marathon_builds_report(FakeSource([]), weeks=0)


if __name__ == "__main__":
    unittest.main()
