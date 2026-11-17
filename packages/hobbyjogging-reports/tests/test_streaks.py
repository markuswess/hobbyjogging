import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import (
    MIN_STREAK_RUN_S,
    is_streak_run,
    run_streaks,
    streak_summary,
)
from hobbyjogging_report.streak_report import streaks_report
from support import FakeSource, activity_factory

D = date(2026, 11, 9)
activity = activity_factory()


def run(day, *, minutes=40, km=8.0, activity_id=None, **overrides):
    return activity(
        id=activity_id or f"run-{day}",
        date=day,
        duration_s=minutes * 60,
        distance_m=km * 1000,
        **overrides,
    )


class StreakTests(unittest.TestCase):

    def test_consecutive_days_form_one_streak(self):
        streaks = run_streaks(
            [run(D + timedelta(days=offset)) for offset in range(4)]
        )

        self.assertEqual(1, len(streaks))
        streak = streaks[0]
        self.assertEqual(D, streak.start)
        self.assertEqual(D + timedelta(days=3), streak.end)
        self.assertEqual(4, streak.days)
        self.assertAlmostEqual(32_000, streak.distance_m)
        self.assertAlmostEqual(4 * 40 * 60, streak.duration_s)

    def test_a_gap_splits_streaks(self):
        streaks = run_streaks([
            run(D),
            run(D + timedelta(days=1)),
            run(D + timedelta(days=3)),
            run(D + timedelta(days=4)),
        ])

        self.assertEqual(2, len(streaks))
        self.assertEqual([2, 2], [streak.days for streak in streaks])

    def test_a_ride_does_not_extend_a_streak(self):
        streaks = run_streaks([
            run(D),
            run(D + timedelta(days=1), type="ride", km=30),
            run(D + timedelta(days=2)),
        ])

        self.assertEqual(2, len(streaks))
        self.assertEqual([1, 1], [streak.days for streak in streaks])

    def test_a_short_run_does_not_count(self):
        self.assertFalse(
            is_streak_run(run(D, minutes=MIN_STREAK_RUN_S // 60 - 1))
        )
        self.assertTrue(
            is_streak_run(run(D, minutes=MIN_STREAK_RUN_S // 60))
        )
        self.assertEqual([], run_streaks([run(D, minutes=2)]))

    def test_two_runs_on_one_day_are_one_day(self):
        streaks = run_streaks([
            run(D, minutes=20, km=5),
            run(D, minutes=30, km=6, activity_id="second"),
        ])

        self.assertEqual(1, len(streaks))
        self.assertEqual(1, streaks[0].days)
        self.assertAlmostEqual(11_000, streaks[0].distance_m)
        self.assertAlmostEqual(50 * 60, streaks[0].duration_s)

    def test_current_streak_ends_today(self):
        today = D + timedelta(days=1)
        summary = streak_summary([run(D), run(today)], today)

        self.assertIsNotNone(summary.current)
        self.assertEqual(2, summary.current.days)
        self.assertTrue(summary.today_run)

    def test_current_streak_survives_a_day_without_a_run_yet(self):
        today = D + timedelta(days=2)
        summary = streak_summary(
            [run(D), run(D + timedelta(days=1))],
            today,
        )

        self.assertIsNotNone(summary.current)
        self.assertEqual(2, summary.current.days)
        self.assertFalse(summary.today_run)

    def test_no_current_streak_after_a_gap(self):
        today = D + timedelta(days=2)
        summary = streak_summary([run(D)], today)

        self.assertIsNone(summary.current)
        self.assertEqual(D, summary.last_run)
        self.assertFalse(summary.today_run)

    def test_longest_are_cut_and_ordered(self):
        schedule = (
            [D + timedelta(days=offset) for offset in range(5)]
            + [
                D + timedelta(days=10 + offset)
                for offset in range(3)
            ]
            + [
                D + timedelta(days=20 + offset)
                for offset in range(4)
            ]
        )
        summary = streak_summary(
            [run(day) for day in schedule],
            D + timedelta(days=23),
            limit=2,
        )

        self.assertEqual([5, 4], [streak.days for streak in summary.longest])
        self.assertEqual(3, summary.streak_count)

    def test_a_tie_is_broken_by_distance(self):
        short = [
            run(D + timedelta(days=offset), km=4)
            for offset in range(2)
        ]
        long = [
            run(D + timedelta(days=10 + offset), km=6)
            for offset in range(2)
        ]

        summary = streak_summary(short + long, D + timedelta(days=11))

        self.assertEqual(2, len(summary.longest))
        self.assertGreater(
            summary.longest[0].distance_m,
            summary.longest[1].distance_m,
        )


class StreakReportTests(unittest.TestCase):

    def _source(self):
        return FakeSource(
            activities=[
                run(D),
                run(D + timedelta(days=1)),
                run(D + timedelta(days=2)),
                run(D + timedelta(days=10)),
                run(D + timedelta(days=11)),
                run(D + timedelta(days=20)),
            ]
        )

    def test_report_lists_the_current_and_longest_streaks(self):
        report = streaks_report(
            self._source(),
            today=D + timedelta(days=20),
            limit=2,
        )

        current = D + timedelta(days=20)

        self.assertIn("# Running streaks", report)
        self.assertIn("- Current: 1 day (today run)", report)
        self.assertIn("- 3 streaks, 6 run days across all history.", report)
        self.assertIn("at least 10 minutes", report)
        self.assertIn("Bold marks the current streak.", report)
        self.assertIn("## Longest streaks", report)
        self.assertIn(
            "| Start | End | Days | Distance | Time |",
            report,
        )
        self.assertIn(
            f"| {D} | {D + timedelta(days=2)} | 3 | 24.0 km | 2h00 |",
            report,
        )
        # The current streak falls outside the two longest, so an ellipsis
        # separates it from the list and its open end prints as a question
        # mark in bold.
        self.assertIn("| ⋮ | | | | |", report)
        self.assertIn(
            f"| **{current}** | **?** | **1** | **8.0 km** | **40min** |",
            report,
        )
        self.assertIn("Showing the 2 longest of 3 streaks.", report)

    def test_current_streak_in_the_top_is_bold_without_an_ellipsis(self):
        source = FakeSource(
            activities=[
                run(D),
                run(D + timedelta(days=1)),
                run(D + timedelta(days=2)),
                run(D + timedelta(days=10)),
                run(D + timedelta(days=11)),
            ]
        )
        today = D + timedelta(days=11)

        report = streaks_report(source, today=today, limit=2)

        self.assertIn("- Current: 2 days (today run)", report)
        self.assertIn(
            f"| **{D + timedelta(days=10)}** | **?** | **2** | "
            "**16.0 km** | **1h20** |",
            report,
        )
        self.assertNotIn("⋮", report)
        self.assertIn(
            f"| {D} | {D + timedelta(days=2)} | 3 | 24.0 km | 2h00 |",
            report,
        )

    def test_report_without_runs_says_so(self):
        report = streaks_report(FakeSource(), today=D)

        self.assertIn("- No runs yet", report)
        self.assertNotIn("## Longest streaks", report)


if __name__ == "__main__":
    unittest.main()
