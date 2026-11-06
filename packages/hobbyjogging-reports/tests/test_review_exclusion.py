import unittest
from datetime import date

from hobbyjogging_core import connect, migrate
from hobbyjogging_report.daily import daily
from hobbyjogging_report.period_report import period_report
from hobbyjogging_report.sessions import session_report
from hobbyjogging_report.review import exclude_review, review_note


class ReviewExclusionTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.conn.execute(
            "INSERT INTO activities "
            "(id, local_date, sport, name, duration_s, elapsed_s, distance_m) "
            "VALUES ('a1', '2026-10-01', 'run', 'Odd one', 3600, 3700, 10000)"
        )
        self.conn.execute(
            "INSERT INTO review_items "
            "(activity_id, category, detail, context_json, fingerprint) "
            "VALUES ('a1', 'quality', 'distance is 0 m', '{}', 'fp-1')"
        )

    def _all(self):
        from hobbyjogging_report.sources.database import DatabaseSource

        source = DatabaseSource(connection=self.conn)
        return source.activities(date(2026, 10, 1), date(2026, 10, 1))

    def _activities(self):
        from hobbyjogging_report.sources.database import DatabaseSource

        source = DatabaseSource(connection=self.conn)
        return [
            a.id
            for a in source.activities(date(2026, 10, 1), date(2026, 10, 1))
            if a.needs_review
        ]

    def test_excludes_open_review_items_by_default(self):
        self.assertEqual(["a1"], self._activities())

    def test_open_items_are_resolved_and_shown_again(self):
        self.conn.execute(
            "UPDATE review_items SET status = 'resolved' "
            "WHERE activity_id = 'a1'"
        )
        flag = self._activities()
        self.assertEqual([], flag)
        a1 = self._all()[0]
        self.assertEqual("a1", a1.id)
        self.assertFalse(a1.needs_review)

    def test_excluded_activity_leaves_report_note(self):
        kept, excluded = exclude_review(
            [
                type("A", (), {"needs_review": False})(),
                type("A", (), {"needs_review": True})(),
            ]
        )

        self.assertEqual(1, len(kept))
        self.assertEqual(1, excluded)
        self.assertEqual("1 activity excluded (import review)", review_note(1))
        self.assertEqual(
            "2 activities excluded (import review)",
            review_note(2),
        )

    def test_session_report_notes_excluded_activity(self):
        source = self._source()

        report = session_report(date(2026, 10, 1), source)

        self.assertIn("1 activity excluded (import review)", report)
        self.assertNotIn("Odd one", report)

        report = session_report(date(2026, 10, 1), source, include_review=True)
        self.assertIn("Odd one", report)
        self.assertNotIn("excluded (import review)", report)

    def test_period_report_notes_excluded_activity(self):
        source = self._source()

        report = period_report(
            date(2026, 10, 1),
            date(2026, 10, 2),
            "Test Report",
            source,
        )

        self.assertIn("1 activity excluded (import review)", report)
        self.assertNotIn("Odd one", report)

    def test_daily_report_notes_excluded_activity(self):
        source = self._source()
        today = date.today()

        self.conn.execute(
            f"""
            INSERT INTO activities (
                id, local_date, sport, name,
                duration_s, elapsed_s, distance_m
            ) VALUES ('a2', '{today.isoformat()}', 'run', 'Today odd one',
                      3600, 3700, 10000)
            """
        )
        self.conn.execute(
            f"""
            INSERT INTO review_items (
                activity_id, category, detail, context_json, fingerprint
            ) VALUES ('a2', 'quality', 'distance is 0 m', '{{}}', 'fp-2')
            """
        )

        report = daily(source)

        self.assertIn("1 activity excluded (import review)", report)
        self.assertNotIn("odd one", report)

    def _source(self):
        from hobbyjogging_report.sources.database import DatabaseSource

        return DatabaseSource(connection=self.conn)


if __name__ == "__main__":
    unittest.main()
