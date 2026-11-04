import unittest
from datetime import date

from hobbyjogging_core.model import Activity, Interval
from hobbyjogging_report.analysis import (
    subt_blocks,
    subt_report_blocks,
    subt_report_summary,
)
from hobbyjogging_report.reports import subt_report

D1 = date(2026, 10, 1)
D2 = date(2026, 10, 3)


def activity(**overrides):
    values = dict(
        id="a",
        date=D1,
        type="run",
        name="5x5' subT medium",
        duration_s=3000,
        distance_m=8000,
        rpe=4,
    )
    values.update(overrides)
    return Activity(**values)


def iv(
    duration_s,
    distance_m,
    group_id="g",
    avg_hr=None,
    max_hr=None,
):
    return Interval(
        type="WORK",
        group_id=group_id,
        duration_s=duration_s,
        distance_m=distance_m,
        avg_hr=avg_hr,
        max_hr=max_hr,
    )


def mixed_intervals():
    """Five medium reps plus one short rep, all at 5:00/km."""
    return [
        iv(300, 1000, group_id="medium", avg_hr=160, max_hr=170)
        for _ in range(5)
    ] + [
        iv(180, 600, group_id="short", avg_hr=150, max_hr=165),
    ]


class FakeSource:

    def __init__(self, activities, intervals=None):
        self._activities = activities
        self._intervals = intervals or {}

    def activities(self, start, end):
        return [
            activity
            for activity in self._activities
            if start <= activity.date <= end
        ]

    def activity_intervals(self, activity_id):
        return self._intervals.get(activity_id, [])


class SubtBlockTests(unittest.TestCase):

    def test_splits_categories_and_aggregates_totals(self):
        blocks = subt_blocks(
            activity(name="5x5' + 1x3' subT"),
            mixed_intervals(),
        )

        by_category = {block.category: block for block in blocks}

        self.assertEqual({"medium", "short"}, set(by_category))

        medium = by_category["medium"]
        self.assertEqual(5, medium.count)
        self.assertEqual(1500, medium.total_time_s)
        self.assertEqual(5000, medium.total_distance_m)
        self.assertAlmostEqual(300, medium.pace_s_per_km)
        self.assertAlmostEqual(300, medium.avg_rep_s)
        self.assertAlmostEqual(160, medium.avg_hr)
        self.assertEqual(170, medium.max_hr)

        short = by_category["short"]
        self.assertEqual(1, short.count)
        self.assertEqual(180, short.total_time_s)
        self.assertEqual(600, short.total_distance_m)
        self.assertAlmostEqual(300, short.pace_s_per_km)
        self.assertAlmostEqual(150, short.avg_hr)
        self.assertEqual(165, short.max_hr)

    def test_merges_same_category_groups(self):
        intervals = [
            iv(300, 1000, group_id="set-a", avg_hr=160, max_hr=170)
            for _ in range(2)
        ] + [
            iv(300, 1000, group_id="set-b", avg_hr=160, max_hr=172)
            for _ in range(3)
        ]

        blocks = subt_blocks(activity(), intervals)

        self.assertEqual(1, len(blocks))
        self.assertEqual("medium", blocks[0].category)
        self.assertEqual(5, blocks[0].count)
        self.assertEqual(1500, blocks[0].total_time_s)
        self.assertEqual(172, blocks[0].max_hr)

    def test_lt1_wins_over_rep_length(self):
        intervals = [
            iv(180, 600, group_id="short", avg_hr=150, max_hr=165),
            *[
                iv(600, 2000, group_id="long", avg_hr=160, max_hr=172)
                for _ in range(3)
            ],
        ]

        blocks = subt_blocks(activity(name="3x10' LT1"), intervals)

        self.assertEqual(1, len(blocks))
        self.assertEqual("lt1", blocks[0].category)
        self.assertEqual(4, blocks[0].count)
        self.assertEqual(1980, blocks[0].total_time_s)
        self.assertEqual(6600, blocks[0].total_distance_m)

    def test_no_work_reps_are_omitted(self):
        self.assertEqual([], subt_blocks(activity(name="subT"), []))

    def test_non_subt_activity_is_ignored(self):
        self.assertEqual(
            [],
            subt_blocks(activity(name="Easy"), mixed_intervals()),
        )


class SubtReportBlocksAndSummaryTests(unittest.TestCase):

    def setUp(self):
        self.mixed = activity(
            id="mixed",
            date=D1,
            name="5x5' + 1x3' subT",
        )
        self.medium = activity(
            id="medium",
            date=D2,
            name="2x5' subT medium",
        )
        self.blocks = subt_report_blocks(
            [self.medium, self.mixed],
            {
                "mixed": mixed_intervals(),
                "medium": [
                    iv(300, 1000, group_id="g", avg_hr=164, max_hr=170)
                    for _ in range(2)
                ],
            },
        )

    def test_blocks_are_sorted_by_category_then_date(self):
        self.assertEqual(
            ["short", "medium", "medium"],
            [block.category for block in self.blocks],
        )
        self.assertEqual(
            [D1, D1, D2],
            [block.date for block in self.blocks],
        )

    def test_summary_counts_sessions_reps_and_totals(self):
        summaries, total = subt_report_summary(self.blocks)
        by_category = {summary.category: summary for summary in summaries}

        self.assertEqual(1, by_category["short"].sessions)
        self.assertEqual(2, by_category["medium"].sessions)
        self.assertEqual(0, by_category["long"].sessions)
        self.assertEqual(0, by_category["lt1"].sessions)

        medium = by_category["medium"]
        self.assertEqual(7, medium.reps)
        self.assertEqual(2100, medium.total_time_s)
        self.assertEqual(7000, medium.total_distance_m)
        self.assertAlmostEqual(300, medium.pace_s_per_km)
        self.assertAlmostEqual(161.14, medium.avg_hr, places=2)
        self.assertEqual(170, medium.max_hr)

        # A session with short and medium work is counted once in Total.
        self.assertEqual(2, total.sessions)
        self.assertEqual(8, total.reps)
        self.assertEqual(2280, total.total_time_s)
        self.assertEqual(7600, total.total_distance_m)
        self.assertAlmostEqual(300, total.pace_s_per_km)


class SubtReportRenderingTests(unittest.TestCase):

    def setUp(self):
        self.activity = activity(
            id="mixed",
            date=D1,
            name="5x5' + 1x3' subT",
        )
        self.source = FakeSource(
            [self.activity],
            {"mixed": mixed_intervals()},
        )

    def test_report_has_summary_and_group_tables(self):
        report = subt_report(
            D1,
            D1,
            "subT Report",
            self.source,
        )

        self.assertIn("# subT Report", report)
        self.assertIn("2026-10-01 → 2026-10-01", report)
        self.assertIn("## Summary", report)
        self.assertIn(
            "| Category | Sessions | Reps | Work time | Work km | "
            "Avg pace | Avg HR | Max HR |",
            report,
        )
        self.assertIn("## Short", report)
        self.assertIn("## Medium", report)
        self.assertNotIn("## Long", report)
        self.assertNotIn("## LT1", report)
        self.assertIn(
            "| Date | Session | Reps | Work time | Work km | Pace | "
            "Fastest | Slowest | Avg HR | Max HR |",
            report,
        )
        self.assertIn("5 × 5:00", report)
        self.assertIn("1 × 3:00", report)
        self.assertIn(
            "Sessions with work in more than one category",
            report,
        )
        self.assertEqual(2, report.count("5x5' + 1x3' subT"))

    def test_lt1_session_gets_its_own_table(self):
        lt1 = activity(
            id="lt1",
            date=D1,
            name="3x10' LT1",
            duration_s=3600,
        )
        source = FakeSource(
            [lt1],
            {
                "lt1": [
                    iv(600, 2000, group_id="g", avg_hr=160, max_hr=172)
                    for _ in range(3)
                ]
            },
        )

        report = subt_report(D1, D1, "subT Report", source)

        self.assertIn("## LT1", report)
        self.assertIn("3 × 10:00", report)
        self.assertNotIn("## Long", report)

    def test_empty_range_message(self):
        source = FakeSource(
            [activity(id="easy", name="Easy")],
            {"easy": mixed_intervals()},
        )

        report = subt_report(D1, D1, "subT Report", source)

        self.assertIn("# subT Report", report)
        self.assertIn("- No subT or LT1 sessions with work data", report)
        self.assertNotIn("## Summary", report)

    def test_reviewed_session_is_excluded_with_note(self):
        flagged = activity(
            id="flagged",
            date=D1,
            name="Flagged subT",
            needs_review=True,
        )
        source = FakeSource(
            [self.activity, flagged],
            {
                "mixed": mixed_intervals(),
                "flagged": mixed_intervals(),
            },
        )

        report = subt_report(D1, D1, "subT Report", source)

        self.assertIn("1 activity excluded (import review)", report)
        self.assertNotIn("Flagged subT", report)

    def test_pipe_in_name_does_not_break_table(self):
        named = activity(
            id="mixed",
            date=D1,
            name="5x5' subT | test",
        )
        source = FakeSource(
            [named],
            {"mixed": mixed_intervals()},
        )

        report = subt_report(D1, D1, "subT Report", source)

        self.assertIn("5x5' subT / test", report)
        self.assertNotIn("5x5' subT | test", report)


if __name__ == "__main__":
    unittest.main()
