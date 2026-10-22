import unittest
from datetime import date

from intervals_report.analysis import subt_work_points, work_intervals
from intervals_report.model import Activity, Interval

D = date(2026, 10, 1)


def iv(
    duration_s,
    distance_m,
    type="WORK",
    group_id="reps",
    avg_hr=None,
):
    return Interval(
        type=type,
        group_id=group_id,
        duration_s=duration_s,
        distance_m=distance_m,
        avg_hr=avg_hr,
    )


class WorkIntervalsTests(unittest.TestCase):

    def test_drops_warmup_cooldown_and_recovery_jogs(self):
        intervals = [
            iv(1200, 4000, group_id="warmup"),
            *[iv(300, 1300) for _ in range(5)],
            *[iv(100, 300, group_id="jog") for _ in range(4)],
            iv(1200, 3800, group_id="cooldown"),
        ]

        reps = work_intervals(intervals)

        self.assertEqual([300] * 5, [i.duration_s for i in reps])

    def test_drops_slow_low_hr_warmup(self):
        # The warm-up pace sits just inside the work band; its heart rate
        # gives it away.
        intervals = [
            iv(328, 1198, group_id="warmup", avg_hr=140),
            iv(1140, 4851, avg_hr=166),
            iv(109, 315, group_id="jog", avg_hr=152),
            iv(1081, 4645, avg_hr=172),
            iv(65, 221, group_id="jog", avg_hr=147),
            iv(1020, 4417, avg_hr=173),
            iv(122, 357, group_id="jog", avg_hr=157),
            iv(968, 4174, avg_hr=173),
            iv(545, 1583, group_id="cooldown", avg_hr=152),
        ]

        self.assertEqual(
            [1140, 1081, 1020, 968],
            [i.duration_s for i in work_intervals(intervals)],
        )

    def test_keeps_low_hr_short_rep(self):
        # A short first rep can have heart-rate lag; pace is still fast.
        specs = [
            (62, 321, 140),
            (121, 577, 156),
            (180, 861, 161),
            (240, 1154, 164),
            (300, 1418, 168),
            (241, 1140, 167),
            (181, 861, 166),
            (122, 599, 169),
            (60, 353, 174),
        ]
        intervals = [
            iv(duration, distance, avg_hr=hr)
            for duration, distance, hr in specs
        ]

        self.assertEqual(9, len(work_intervals(intervals)))

    def test_ignores_strides(self):
        intervals = [
            *[iv(300, 1300) for _ in range(5)],
            iv(18, 80, group_id="stride"),
        ]

        self.assertEqual(
            [300] * 5,
            [i.duration_s for i in work_intervals(intervals)],
        )

    def test_keeps_all_when_pace_data_is_missing(self):
        intervals = [iv(600, 0), iv(300, 0)]

        self.assertEqual(intervals, work_intervals(intervals))

    def test_subt_points_use_only_work_reps(self):
        intervals = [
            iv(1200, 4000, group_id="warmup"),
            *[iv(300, 1300, avg_hr=160) for _ in range(5)],
            *[iv(100, 300, group_id="jog") for _ in range(4)],
            iv(1200, 3800, group_id="cooldown"),
        ]
        activity = Activity(id="a", date=D, name="5x5' subT")

        points = subt_work_points(activity, intervals)

        self.assertEqual(1, len(points))
        self.assertEqual(5, points[0].count)
        self.assertAlmostEqual(300, points[0].avg_rep_s)
        self.assertAlmostEqual(160, points[0].avg_hr)
        self.assertEqual("medium", points[0].category)


if __name__ == "__main__":
    unittest.main()
