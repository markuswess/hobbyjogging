import unittest
from datetime import date

from hobbyjogging_core.model import Interval
from hobbyjogging_report.reports import select_session, session_report
from support import FakeSource, activity_factory

D1 = date(2026, 10, 1)
D2 = date(2026, 10, 3)

activity = activity_factory(
    name="Easy",
    duration_s=2400,
    distance_m=8000,
    rpe=2,
    feel=2,
)


def work_intervals(count=5):
    return [
        Interval(
            group_id="g",
            type="WORK",
            duration_s=300,
            distance_m=1000,
            avg_hr=160,
            max_hr=170,
        )
        for _ in range(count)
    ]


class SessionSelectionTests(unittest.TestCase):

    def setUp(self):
        self.latest = activity(
            id="b",
            date=D2,
            name="5x5' subT medium",
            duration_s=3000,
            distance_m=8000,
            rpe=4,
            description="# Warm up\n- 10 min easy",
        )
        self.first = activity(id="a", date=D1)
        self.source = FakeSource(
            [self.latest, self.first],
            {"b": work_intervals()},
        )
        self.today = date(2026, 10, 5)

    def test_default_is_latest(self):
        day, activities, excluded = select_session(
            self.source,
            today=self.today,
        )

        self.assertEqual(D2, day)
        self.assertEqual(["b"], [a.id for a in activities])
        self.assertEqual(0, excluded)

    def test_last_alias(self):
        _, activities, _ = select_session(
            self.source,
            "last",
            today=self.today,
        )

        self.assertEqual(["b"], [a.id for a in activities])

    def test_date_selects_that_day(self):
        day, activities, _ = select_session(
            self.source,
            "2026-10-01",
            today=self.today,
        )

        self.assertEqual(D1, day)
        self.assertEqual(["a"], [a.id for a in activities])

    def test_id_selects_one_activity(self):
        day, activities, _ = select_session(
            self.source,
            "a",
            today=self.today,
        )

        self.assertEqual(D1, day)
        self.assertEqual(["a"], [a.id for a in activities])

    def test_unknown_id_returns_nothing(self):
        day, activities, _ = select_session(
            self.source,
            "missing",
            today=self.today,
        )

        self.assertIsNone(day)
        self.assertEqual([], activities)

    def test_latest_skips_reviewed_activity(self):
        flagged = activity(
            id="flagged",
            date=date(2026, 10, 4),
            name="Flagged",
            needs_review=True,
        )
        source = FakeSource([self.first, flagged])

        day, activities, excluded = select_session(
            source,
            today=self.today,
        )

        self.assertEqual(D1, day)
        self.assertEqual(["a"], [a.id for a in activities])
        self.assertEqual(1, excluded)


class SessionReportTests(unittest.TestCase):

    def setUp(self):
        self.latest = activity(
            id="b",
            date=D2,
            name="5x5' subT medium",
            duration_s=3000,
            distance_m=8000,
            rpe=4,
            description="# Warm up\n- 10 min easy",
        )
        self.source = FakeSource(
            [activity(id="a", date=D1), self.latest],
            {"b": work_intervals()},
        )
        self.today = date(2026, 10, 5)

    def test_default_report_is_latest_session(self):
        report = session_report(
            None,
            self.source,
            today=self.today,
        )

        self.assertIn("# Session 2026-10-03", report)
        self.assertIn("## Run — 5x5' subT medium", report)
        self.assertIn("- ID: b", report)
        self.assertNotIn("- ID: a", report)

    def test_detailed_report_has_intervals_and_description(self):
        report = session_report("b", self.source)

        self.assertIn("- Category: quality/intervals/subt-medium", report)
        self.assertIn("### Description", report)
        self.assertIn("```", report)
        self.assertIn("# Warm up", report)
        self.assertIn("### Intervals", report)
        self.assertIn(
            "| # | Type | Time | Distance | Pace | Avg HR | Max HR |",
            report,
        )
        self.assertIn(
            "| 1 | Work | 5:00 | 1.00 km | 5:00/km | 160 | 170 |",
            report,
        )
        self.assertIn("### Work reps", report)
        self.assertIn(
            "5x5:00 subT-medium: 5:00/km, 160 avg / 170 max bpm",
            report,
        )

    def test_unknown_id_suggests_include_review(self):
        report = session_report("missing", self.source)

        self.assertIn("No activity found for `missing`", report)
        self.assertIn("--include-review", report)

    def test_date_without_activity(self):
        report = session_report("2026-10-02", self.source)

        self.assertIn("# Session 2026-10-02", report)
        self.assertIn("No activity", report)

    def test_include_review_shows_flagged_activity(self):
        flagged = activity(
            id="flagged",
            date=D2,
            name="Flagged",
            needs_review=True,
        )
        source = FakeSource([flagged])

        report = session_report(
            "flagged",
            source,
            include_review=True,
        )

        self.assertIn("- ID: flagged", report)
        self.assertNotIn("No activity found", report)


if __name__ == "__main__":
    unittest.main()
