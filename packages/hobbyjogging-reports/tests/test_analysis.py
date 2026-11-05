import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import (
    daily_run_distance,
    daily_run_time,
    daily_training_load,
    distance_averages,
    is_lt1_activity,
    load_metrics,
    average_warmup_days,
    recovery_trends,
    subt_session_point,
    subt_work_points,
    time_averages,
    week_bounds,
    week_start,
    weekly_run_distance,
    weekly_time_by_zone,
    work_intervals,
    zone_time_averages,
)
from hobbyjogging_report.model import AverageWindows
from hobbyjogging_core.model import Activity, Interval, WellnessDay

D = date(2026, 10, 1)


def iv(
    duration_s,
    distance_m,
    type="WORK",
    group_id="reps",
    avg_hr=None,
    max_hr=None,
):
    return Interval(
        type=type,
        group_id=group_id,
        duration_s=duration_s,
        distance_m=distance_m,
        avg_hr=avg_hr,
        max_hr=max_hr,
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
            *[iv(300, 1300, avg_hr=160, max_hr=170) for _ in range(5)],
            *[iv(100, 300, group_id="jog") for _ in range(4)],
            iv(1200, 3800, group_id="cooldown"),
        ]
        activity = Activity(id="a", date=D, name="5x5' subT")

        points = subt_work_points(activity, intervals)

        self.assertEqual(1, len(points))
        self.assertEqual(5, points[0].count)
        self.assertAlmostEqual(300, points[0].avg_rep_s)
        self.assertAlmostEqual(160, points[0].avg_hr)
        self.assertEqual(170, points[0].max_hr)
        self.assertEqual("medium", points[0].category)

    def test_subt_session_point_aggregates_groups(self):
        intervals = [
            iv(300, 1300, group_id="ascending", max_hr=170),
            iv(300, 1300, group_id="descending", max_hr=172),
            iv(180, 850, group_id="pyramid-tip", max_hr=165),
        ]
        activity = Activity(id="a", date=D, name="subT pyramid")

        point = subt_session_point(activity, intervals)

        self.assertIsNotNone(point)
        self.assertEqual(3, point.count)
        self.assertAlmostEqual(260, point.avg_rep_s)
        self.assertEqual(172, point.max_hr)
        self.assertAlmostEqual(211.76, point.fastest_pace_s_per_km, places=2)
        self.assertAlmostEqual(230.77, point.slowest_pace_s_per_km, places=2)
        self.assertEqual("medium", point.category)

    def test_subt_session_point_accepts_category_override(self):
        activity = Activity(id="a", date=D, name="3x10' LT1")
        intervals = [iv(600, 2800) for _ in range(3)]

        point = subt_session_point(activity, intervals, category="lt1")

        self.assertIsNotNone(point)
        self.assertEqual("lt1", point.category)


class ActivityNameTests(unittest.TestCase):

    def test_lt1_name(self):
        self.assertTrue(
            is_lt1_activity(Activity(id="a", date=D, name="3x10' LT1"))
        )
        self.assertTrue(
            is_lt1_activity(Activity(id="a", date=D, name="lt 1"))
        )
        self.assertFalse(
            is_lt1_activity(Activity(id="a", date=D, name="subT"))
        )


class LoadMetricsTests(unittest.TestCase):

    def test_daily_training_load_sums_and_zero_fills(self):
        activities = [
            Activity(id="a", date=D, type="run", training_load=40),
            Activity(id="b", date=D, type="ride", training_load=20),
            Activity(
                id="c",
                date=date(2026, 10, 3),
                type="run",
                training_load=60,
            ),
        ]

        series = daily_training_load(
            activities,
            D,
            date(2026, 10, 3),
        )

        self.assertEqual(
            [60, 0, 60],
            [value for _, value in series],
        )

    def test_load_warmup_uses_longest_window(self):
        self.assertEqual(910, average_warmup_days())
        self.assertEqual(
            100,
            average_warmup_days(
                AverageWindows(base=20, fitness=10, fatigue=5)
            ),
        )

    def test_load_metrics_short_average_reacts_fastest(self):
        start = date(2026, 1, 1)
        end = date(2026, 4, 10)
        ndays = (end - start).days + 1

        activities = [
            Activity(
                id=f"a{index}",
                date=start + timedelta(days=index),
                type="run",
                training_load=100,
            )
            for index in range(ndays)
        ]

        points = load_metrics(
            activities,
            start,
            end,
            warmup_days=200,
        )

        self.assertEqual(ndays, len(points))
        self.assertEqual(start, points[0].date)
        self.assertEqual(end, points[-1].date)
        self.assertEqual(100, points[-1].load)

        first = points[0]
        self.assertLess(first.base, first.fitness)
        self.assertLess(first.fitness, first.fatigue)

        last = points[-1]
        self.assertLess(last.base, last.fitness)
        self.assertLess(last.fitness, last.fatigue)

    def test_load_metrics_can_start_with_no_history(self):
        points = load_metrics([], D, D, warmup_days=10)

        self.assertEqual(1, len(points))
        self.assertEqual(0, points[0].load)
        self.assertEqual(0, points[0].base)
        self.assertEqual(0, points[0].fitness)
        self.assertEqual(0, points[0].fatigue)


class DistanceMetricsTests(unittest.TestCase):

    def test_daily_run_distance_sums_runs_and_ignores_cross_training(self):
        activities = [
            Activity(id="a", date=D, type="run", distance_m=8000),
            Activity(id="b", date=D, type="ride", distance_m=20000),
            Activity(id="c", date=D, type="trail_run", distance_m=2000),
            Activity(
                id="d",
                date=date(2026, 10, 2),
                type="run",
                distance_m=10000,
            ),
        ]

        series = daily_run_distance(
            activities,
            D,
            date(2026, 10, 2),
        )

        self.assertEqual(
            [10.0, 10.0],
            [value for _, value in series],
        )

    def test_distance_averages_use_the_three_windows(self):
        start = date(2026, 1, 1)
        end = date(2026, 4, 10)
        ndays = (end - start).days + 1

        activities = [
            Activity(
                id=f"a{index}",
                date=start + timedelta(days=index),
                type="run",
                distance_m=10000,
            )
            for index in range(ndays)
        ]

        points = distance_averages(
            activities,
            start,
            end,
            warmup_days=200,
        )

        self.assertEqual(ndays, len(points))
        self.assertEqual(10.0, points[-1].distance_km)

        first = points[0]
        self.assertLess(first.base, first.fitness)
        self.assertLess(first.fitness, first.fatigue)

        last = points[-1]
        self.assertLess(last.base, last.fitness)
        self.assertLess(last.fitness, last.fatigue)

    def test_distance_averages_can_start_with_no_history(self):
        points = distance_averages([], D, D, warmup_days=10)

        self.assertEqual(1, len(points))
        self.assertEqual(0, points[0].distance_km)
        self.assertEqual(0, points[0].base)


class TimeMetricsTests(unittest.TestCase):

    def test_daily_run_time_sums_running_only(self):
        activities = [
            Activity(id="a", date=D, type="run", duration_s=3600),
            Activity(id="b", date=D, type="ride", duration_s=1800),
            Activity(
                id="c",
                date=date(2026, 10, 2),
                type="run",
                duration_s=1200,
            ),
        ]

        series = daily_run_time(
            activities,
            D,
            date(2026, 10, 2),
        )

        self.assertEqual(
            [3600, 1200],
            [value for _, value in series],
        )

    def test_time_averages_use_the_three_windows(self):
        start = date(2026, 1, 1)
        end = date(2026, 4, 10)
        ndays = (end - start).days + 1

        activities = [
            Activity(
                id=f"a{index}",
                date=start + timedelta(days=index),
                type="run",
                duration_s=3600,
            )
            for index in range(ndays)
        ]

        points = time_averages(
            activities,
            start,
            end,
            warmup_days=200,
        )

        self.assertEqual(ndays, len(points))
        self.assertEqual(3600, points[-1].time_s)

        first = points[0]
        self.assertLess(first.base, first.fitness)
        self.assertLess(first.fitness, first.fatigue)

        last = points[-1]
        self.assertLess(last.base, last.fitness)
        self.assertLess(last.fitness, last.fatigue)

    def test_weekly_time_by_zone_uses_hr_zones_and_monday_weeks(self):
        activities = [
            Activity(
                id="a",
                date=date(2026, 9, 28),
                type="run",
                duration_s=3600,
                hr_zone_times=[600, 1200, 1800],
            ),
            Activity(
                id="b",
                date=date(2026, 10, 4),
                type="run",
                duration_s=1800,
                hr_zone_times=[1800],
            ),
            Activity(
                id="c",
                date=date(2026, 10, 5),
                type="run",
                duration_s=1200,
            ),
            Activity(
                id="d",
                date=date(2026, 10, 5),
                type="ride",
                duration_s=5000,
                hr_zone_times=[5000],
            ),
        ]

        weeks = weekly_time_by_zone(
            activities,
            date(2026, 9, 28),
            date(2026, 10, 5),
        )

        self.assertEqual(2, len(weeks))

        first = weeks[0]
        self.assertEqual(date(2026, 9, 28), first.week)
        self.assertEqual([2400, 1200, 1800, 0], first.zones)
        self.assertEqual(0, first.unzoned)

        second = weeks[1]
        self.assertEqual(date(2026, 10, 5), second.week)
        self.assertEqual([0, 0, 0, 0], second.zones)
        self.assertEqual(1200, second.unzoned)

    def test_weekly_time_by_zone_scales_zone_overshoot(self):
        activity = Activity(
            id="a",
            date=D,
            type="run",
            duration_s=1000,
            hr_zone_times=[500, 1000],
        )

        weeks = weekly_time_by_zone([activity], D, D)

        self.assertEqual(1, len(weeks))
        self.assertAlmostEqual(1000, sum(weeks[0].zones))
        self.assertEqual(0, weeks[0].unzoned)

    def test_weekly_time_by_zone_keeps_uncovered_time(self):
        activity = Activity(
            id="a",
            date=D,
            type="run",
            duration_s=1000,
            hr_zone_times=[400],
        )

        weeks = weekly_time_by_zone([activity], D, D)

        self.assertEqual(400, weeks[0].zones[0])
        self.assertEqual(600, weeks[0].unzoned)

    def test_zone_time_averages_have_one_series_per_zone(self):
        activity = Activity(
            id="a",
            date=D,
            type="run",
            duration_s=3600,
            hr_zone_times=[900, 900, 900, 900],
        )
        ride = Activity(
            id="b",
            date=D,
            type="ride",
            duration_s=3600,
            hr_zone_times=[3600],
        )

        points = zone_time_averages(
            [activity, ride],
            D,
            D,
            window_days=7,
            warmup_days=10,
        )

        self.assertEqual(1, len(points))
        self.assertEqual(4, len(points[0].zones))
        self.assertGreater(points[0].zones[0], 0)
        self.assertAlmostEqual(
            sum(points[0].zones),
            points[0].zones[0] * 4,
        )


class WeeklyVolumeTests(unittest.TestCase):

    def test_week_start_is_monday(self):
        self.assertEqual(date(2026, 9, 28), week_start(D))

    def test_week_bounds_expand_to_full_weeks(self):
        self.assertEqual(
            (date(2026, 9, 28), date(2026, 10, 4)),
            week_bounds(D, date(2026, 10, 2)),
        )

    def test_weekly_run_distance_groups_monday_to_sunday(self):
        activities = [
            Activity(
                id="a",
                date=date(2026, 9, 28),
                type="run",
                distance_m=5000,
            ),
            Activity(
                id="b",
                date=date(2026, 10, 4),
                type="run",
                distance_m=5000,
            ),
            Activity(
                id="c",
                date=date(2026, 10, 5),
                type="run",
                distance_m=3000,
            ),
            Activity(
                id="d",
                date=date(2026, 9, 30),
                type="ride",
                distance_m=20000,
            ),
        ]

        self.assertEqual(
            [
                (date(2026, 9, 28), 10.0),
                (date(2026, 10, 5), 3.0),
            ],
            weekly_run_distance(activities),
        )


class RecoveryTrendTests(unittest.TestCase):

    def setUp(self):
        self.wellness = [
            WellnessDay(
                date=date(2026, 1, 1),
                hrv=50,
                resting_hr=45,
                sleep_s=7 * 3600,
            ),
            WellnessDay(
                date=date(2026, 1, 2),
                hrv=None,
                resting_hr=46,
                sleep_s=None,
            ),
            WellnessDay(
                date=date(2026, 1, 3),
                hrv=60,
                resting_hr=None,
                sleep_s=8 * 3600,
            ),
            WellnessDay(
                date=date(2026, 1, 6),
                hrv=70,
                resting_hr=45,
                sleep_s=7.5 * 3600,
            ),
        ]

    def test_rolls_with_calendar_days_and_skips_missing(self):
        points = recovery_trends(
            self.wellness,
            date(2026, 1, 2),
            date(2026, 1, 6),
            window_days=7,
        )

        self.assertEqual(3, len(points))

        jan2 = points[0]
        self.assertIsNone(jan2.hrv)
        self.assertEqual(50, jan2.hrv_avg)
        self.assertAlmostEqual(45.5, jan2.resting_hr_avg)
        self.assertEqual(7 * 3600, jan2.sleep_avg)

        jan3 = points[1]
        self.assertEqual(55, jan3.hrv_avg)
        self.assertAlmostEqual(45.5, jan3.resting_hr_avg)
        self.assertEqual(7.5 * 3600, jan3.sleep_avg)

        jan6 = points[2]
        self.assertEqual(60, jan6.hrv_avg)
        self.assertAlmostEqual(45.333333, jan6.resting_hr_avg, places=5)
        self.assertEqual(7.5 * 3600, jan6.sleep_avg)

    def test_empty_wellness_returns_nothing(self):
        self.assertEqual(
            [],
            recovery_trends([], D, D),
        )

    def test_rejects_non_positive_window(self):
        with self.assertRaises(ValueError):
            recovery_trends(self.wellness, D, D, window_days=0)


if __name__ == "__main__":
    unittest.main()
