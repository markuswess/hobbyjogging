import unittest
from datetime import date, timedelta
from functools import partial

from hobbyjogging_report.analysis import (
    daily_planned_load,
    daily_planned_load_split,
    daily_planned_zone_time,
    daily_run_distance,
    daily_run_time,
    daily_training_load,
    distance_averages,
    event_zone_seconds,
    event_zone_time,
    is_lt1_activity,
    load_metrics,
    average_warmup_days,
    planned_workout_dates,
    recovery_trends,
    subt_session_point,
    subt_work_points,
    time_averages,
    effective_vo2max,
    garmin_vo2max_devices,
    official_by_activity,
    race_results,
    race_vdot,
    race_vdots,
    runalyze_vo2max_points,
    threshold_max_hr,
    vo2max_methods,
    vo2max_points,
    vo2max_samples,
    week_bounds,
    week_start,
    weekly_planned_distance,
    weekly_planned_time,
    weekly_planned_time_by_zone,
    weekly_run_distance,
    weekly_time_by_zone,
    work_intervals,
    zone_time_averages,
)
from hobbyjogging_report.model import AverageWindows, Vo2maxSample
from hobbyjogging_core.model import (
    Activity,
    AthleteThreshold,
    Device,
    Event,
    EventZoneTime,
    RaceResult as OfficialRaceResult,
    WellnessDay,
)
from support import activity_factory, make_interval

D = date(2026, 10, 1)
iv = partial(make_interval, group_id="reps")
run = activity_factory()


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

    def test_load_metrics_keep_cross_load_out_of_the_averages(self):
        activities = [
            Activity(id="run", date=D, type="run", training_load=100),
            Activity(id="ride", date=D, type="ride", training_load=50),
        ]

        points = load_metrics(
            activities,
            D,
            D,
            warmup_days=10,
        )
        run_only = load_metrics(
            [Activity(id="run", date=D, type="run", training_load=100)],
            D,
            D,
            warmup_days=10,
        )

        self.assertEqual(100, points[-1].load)
        self.assertEqual(50, points[-1].cross_load)
        self.assertAlmostEqual(
            run_only[-1].fitness,
            points[-1].fitness,
        )
        self.assertAlmostEqual(
            run_only[-1].fatigue,
            points[-1].fatigue,
        )

    def test_load_metrics_split_projected_running_and_cross(self):
        events = [
            Event(date=D + timedelta(days=1), type="run", training_load=100),
            Event(
                date=D + timedelta(days=1),
                type="ride",
                training_load=40,
            ),
        ]

        points = load_metrics(
            [Activity(id="run", date=D, type="run", training_load=100)],
            D,
            D,
            warmup_days=10,
            events=events,
            projected_end=D + timedelta(days=1),
        )

        self.assertEqual(100, points[-1].load)
        self.assertEqual(40, points[-1].cross_load)
        self.assertTrue(points[-1].projected)

    def test_load_metrics_project_planned_load(self):
        events = [
            Event(
                date=date(2026, 10, 2),
                type="run",
                training_load=100,
            ),
            Event(
                date=date(2026, 10, 3),
                type="run",
                training_load=100,
            ),
        ]

        points = load_metrics(
            [
                Activity(
                    id="a",
                    date=D,
                    type="run",
                    training_load=100,
                )
            ],
            D,
            D,
            warmup_days=10,
            events=events,
            projected_end=date(2026, 10, 3),
        )

        self.assertEqual(3, len(points))
        self.assertEqual(
            [False, True, True],
            [point.projected for point in points],
        )
        self.assertEqual(100, points[1].load)
        self.assertEqual(100, points[2].load)
        self.assertGreater(points[-1].fitness, points[0].fitness)


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

    def test_distance_averages_project_planned_distance(self):
        events = [
            Event(
                date=date(2026, 10, 2),
                type="run",
                distance_m=10000,
            ),
        ]

        points = distance_averages(
            [
                Activity(
                    id="a",
                    date=D,
                    type="run",
                    distance_m=10000,
                )
            ],
            D,
            D,
            warmup_days=10,
            events=events,
            projected_end=date(2026, 10, 2),
        )

        self.assertEqual(2, len(points))
        self.assertEqual(
            [False, True],
            [point.projected for point in points],
        )
        self.assertEqual(10.0, points[1].distance_km)
        self.assertGreater(points[-1].fitness, points[0].fitness)

    def test_distance_averages_project_from_the_requested_end(self):
        events = [
            Event(
                date=date(2026, 10, 2),
                type="run",
                distance_m=10000,
            ),
            Event(
                date=date(2026, 10, 3),
                type="run",
                distance_m=10000,
            ),
        ]

        points = distance_averages(
            [
                Activity(
                    id="a",
                    date=D,
                    type="run",
                    distance_m=10000,
                )
            ],
            D,
            date(2026, 10, 4),
            warmup_days=10,
            events=events,
            projected_end=date(2026, 10, 4),
            projection_start=D,
        )

        self.assertEqual(4, len(points))
        self.assertEqual(
            [False, True, True, True],
            [point.projected for point in points],
        )
        self.assertEqual(
            [10.0, 10.0, 10.0, 0.0],
            [point.distance_km for point in points],
        )


class TimeMetricsTests(unittest.TestCase):

    def test_time_averages_project_planned_time(self):
        events = [
            Event(
                date=date(2026, 10, 2),
                type="run",
                duration_s=3600,
            ),
        ]

        points = time_averages(
            [
                Activity(
                    id="a",
                    date=D,
                    type="run",
                    duration_s=3600,
                )
            ],
            D,
            D,
            warmup_days=10,
            events=events,
            projected_end=date(2026, 10, 2),
        )

        self.assertEqual(2, len(points))
        self.assertEqual(
            [False, True],
            [point.projected for point in points],
        )
        self.assertEqual(3600, points[1].time_s)
        self.assertGreater(points[-1].fitness, points[0].fitness)

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

    def test_time_averages_can_cover_only_hard_zones(self):
        start = date(2026, 1, 1)
        end = date(2026, 1, 3)
        activities = [
            Activity(
                id="a",
                date=day,
                type="run",
                duration_s=3600,
                pace_zone_times=[600, 900, 1200, 900],
            )
            for day in (start, start + timedelta(days=1))
        ]

        points = time_averages(
            activities,
            start,
            end,
            warmup_days=0,
            zones=(3, 4),
        )

        # Z3 + Z4 only: 1200 + 900 seconds on the session day.
        self.assertEqual(2100, points[1].time_s)
        self.assertGreater(points[1].fatigue, 0)
        self.assertGreater(points[1].fatigue, points[0].fatigue)

    def test_time_averages_project_hard_zone_time(self):
        events = [
            Event(
                date=date(2026, 10, 2),
                type="run",
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 1800, 1),
                    EventZoneTime("Z3", 3600, 3),
                ],
            ),
        ]

        points = time_averages(
            [
                Activity(
                    id="a",
                    date=D,
                    type="run",
                    duration_s=3600,
                    pace_zone_times=[600, 900, 1200, 900],
                )
            ],
            D,
            D,
            warmup_days=10,
            zones=(3, 4),
            events=events,
            projected_end=date(2026, 10, 2),
        )

        self.assertEqual(2, len(points))
        self.assertEqual(
            [False, True],
            [point.projected for point in points],
        )
        # Only the planned Z3 time counts; the easy half is ignored.
        self.assertEqual(3600, points[-1].time_s)
        self.assertGreater(points[-1].fitness, points[0].fitness)

    def test_weekly_time_by_zone_uses_pace_zones_and_monday_weeks(self):
        activities = [
            Activity(
                id="a",
                date=date(2026, 9, 28),
                type="run",
                duration_s=3600,
                pace_zone_times=[600, 1200, 1800],
            ),
            Activity(
                id="b",
                date=date(2026, 10, 4),
                type="run",
                duration_s=1800,
                pace_zone_times=[1800],
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
                pace_zone_times=[5000],
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
            pace_zone_times=[500, 1000],
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
            pace_zone_times=[400],
        )

        weeks = weekly_time_by_zone([activity], D, D)

        self.assertEqual(400, weeks[0].zones[0])
        self.assertEqual(600, weeks[0].unzoned)

    def test_event_zone_seconds_keeps_first_zones(self):
        event = Event(
            date=D,
            zone_kind="hr",
            zone_times=[
                EventZoneTime("Z1", 600, 1),
                EventZoneTime("Z2", 1200, 2),
                EventZoneTime("Z3", 1800, 3),
                EventZoneTime("Z4", 2400, 4),
            ],
        )

        self.assertEqual(
            [600, 1200, 1800, 2400],
            event_zone_seconds(event, 4),
        )

    def test_event_zone_seconds_folds_extra_zones(self):
        event = Event(
            date=D,
            zone_kind="hr",
            zone_times=[
                EventZoneTime("Z1", 100, 1),
                EventZoneTime("Z4", 400, 4),
                EventZoneTime("Z6", 600, 6),
            ],
        )

        self.assertEqual(
            [100, 0, 0, 1000],
            event_zone_seconds(event, 4),
        )

    def test_event_zone_seconds_ignores_ss(self):
        event = Event(
            date=D,
            zone_kind="power",
            zone_times=[
                EventZoneTime("SS", 900),
                EventZoneTime("Z1", 600, 1),
            ],
        )

        self.assertEqual([600, 0, 0, 0], event_zone_seconds(event, 4))

    def test_event_zone_seconds_parses_labels_without_index(self):
        event = Event(
            date=D,
            zone_kind="hr",
            zone_times=[EventZoneTime("Z2", 300)],
        )

        self.assertEqual([0, 300, 0, 0], event_zone_seconds(event, 4))

    def test_event_zone_seconds_returns_none_without_usable_zones(self):
        self.assertIsNone(event_zone_seconds(Event(date=D), 4))
        self.assertIsNone(
            event_zone_seconds(
                Event(
                    date=D,
                    zone_times=[EventZoneTime("Z1", 0, 1)],
                ),
                4,
            )
        )

    def test_event_zone_time_sums_requested_zones_only(self):
        event = Event(
            date=D,
            zone_kind="pace",
            zone_times=[
                EventZoneTime("Z1", 600, 1),
                EventZoneTime("Z3", 1500, 3),
                EventZoneTime("Z4", 300, 4),
                EventZoneTime("Z5", 900, 5),
                EventZoneTime("SS", 120),
            ],
        )

        self.assertEqual(1800, event_zone_time(event, (3, 4)))

    def test_event_zone_time_distinguishes_missing_from_empty(self):
        self.assertIsNone(event_zone_time(Event(date=D), (3, 4)))
        self.assertEqual(
            0,
            event_zone_time(
                Event(
                    date=D,
                    zone_times=[EventZoneTime("Z1", 600, 1)],
                ),
                (3, 4),
            ),
        )

    def test_weekly_planned_time_by_zone_filters_kind_and_sums(self):
        events = [
            Event(
                date=date(2026, 9, 28),
                type="run",
                zone_kind="hr",
                zone_times=[EventZoneTime("Z1", 600, 1)],
            ),
            Event(
                date=date(2026, 10, 4),
                type="run",
                zone_kind="hr",
                zone_times=[
                    EventZoneTime("Z1", 300, 1),
                    EventZoneTime("Z3", 900, 3),
                ],
            ),
            Event(
                date=date(2026, 9, 29),
                type="run",
                zone_kind="pace",
                zone_times=[EventZoneTime("Z1", 5000, 1)],
            ),
            Event(
                date=date(2026, 9, 30),
                type="ride",
                zone_kind="hr",
                zone_times=[EventZoneTime("Z1", 4000, 1)],
            ),
        ]

        weeks = weekly_planned_time_by_zone(
            events,
            date(2026, 9, 28),
            date(2026, 10, 4),
        )

        self.assertEqual(1, len(weeks))
        self.assertEqual(date(2026, 9, 28), weeks[0].week)
        self.assertEqual([900, 0, 900, 0], weeks[0].zones)

    def test_weekly_planned_time_by_zone_can_include_all_kinds(self):
        events = [
            Event(
                date=date(2026, 9, 28),
                type="run",
                zone_kind="hr",
                zone_times=[EventZoneTime("Z1", 600, 1)],
            ),
            Event(
                date=date(2026, 9, 29),
                type="run",
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 300, 1),
                    EventZoneTime("Z3", 1500, 3),
                ],
            ),
        ]

        weeks = weekly_planned_time_by_zone(
            events,
            date(2026, 9, 28),
            date(2026, 10, 4),
            kind=None,
        )

        self.assertEqual(1, len(weeks))
        self.assertEqual([900, 0, 1500, 0], weeks[0].zones)

    def test_zone_time_averages_have_one_series_per_zone(self):
        activity = Activity(
            id="a",
            date=D,
            type="run",
            duration_s=3600,
            pace_zone_times=[900, 900, 900, 900],
        )
        ride = Activity(
            id="b",
            date=D,
            type="ride",
            duration_s=3600,
            pace_zone_times=[3600],
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

    def test_daily_planned_zone_time_sums_and_filters(self):
        events = [
            Event(
                date=D,
                type="run",
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 600, 1),
                    EventZoneTime("Z3", 300, 3),
                ],
            ),
            Event(
                date=D,
                type="run",
                zone_kind="hr",
                zone_times=[EventZoneTime("Z1", 900, 1)],
            ),
            Event(
                date=D,
                type="ride",
                zone_kind="pace",
                zone_times=[EventZoneTime("Z1", 5000, 1)],
            ),
            Event(
                date=date(2026, 10, 2),
                type="run",
                zone_kind="pace",
                zone_times=[EventZoneTime("Z4", 1200, 4)],
            ),
        ]

        series = daily_planned_zone_time(
            events,
            D,
            date(2026, 10, 2),
        )

        self.assertEqual(2, len(series))
        self.assertEqual([600, 0, 300, 0], series[0][1])
        self.assertEqual([0, 0, 0, 1200], series[1][1])

    def test_zone_time_averages_project_planned_zones(self):
        events = [
            Event(
                date=date(2026, 10, 2),
                type="run",
                zone_kind="pace",
                zone_times=[EventZoneTime("Z3", 3600, 3)],
            ),
        ]

        points = zone_time_averages(
            [
                Activity(
                    id="a",
                    date=D,
                    type="run",
                    duration_s=3600,
                    pace_zone_times=[3600, 0, 0, 0],
                )
            ],
            D,
            D,
            window_days=7,
            warmup_days=10,
            events=events,
            projected_end=date(2026, 10, 2),
        )

        self.assertEqual(2, len(points))
        self.assertEqual(
            [False, True],
            [point.projected for point in points],
        )
        self.assertGreater(points[-1].zones[2], points[0].zones[2])


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


class PlannedWorkoutTests(unittest.TestCase):

    def test_weekly_planned_distance_groups_weeks_and_skips_non_runs(self):
        events = [
            Event(
                date=date(2026, 9, 28),
                type="run",
                distance_m=5000,
            ),
            Event(
                date=date(2026, 10, 4),
                type="run",
                distance_m=5000,
            ),
            Event(
                date=date(2026, 10, 5),
                type="run",
                distance_m=3000,
            ),
            Event(
                date=date(2026, 9, 30),
                type="ride",
                distance_m=20000,
            ),
            Event(
                date=date(2026, 9, 29),
                type="run",
                distance_m=None,
            ),
            Event(
                date=date(2026, 9, 29),
                type="",
                distance_m=None,
            ),
        ]

        self.assertEqual(
            [
                (date(2026, 9, 28), 10.0),
                (date(2026, 10, 5), 3.0),
            ],
            weekly_planned_distance(
                events,
                date(2026, 9, 1),
                date(2026, 10, 31),
            ),
        )

    def test_weekly_planned_time_sums_running_duration(self):
        events = [
            Event(
                date=date(2026, 9, 28),
                type="run",
                duration_s=3000,
            ),
            Event(
                date=date(2026, 9, 30),
                type="run",
                duration_s=1800,
            ),
            Event(
                date=date(2026, 9, 30),
                type="ride",
                duration_s=7200,
            ),
        ]

        self.assertEqual(
            [(date(2026, 9, 28), 4800)],
            weekly_planned_time(
                events,
                date(2026, 9, 1),
                date(2026, 10, 31),
            ),
        )

    def test_daily_planned_load_sums_all_sports(self):
        events = [
            Event(
                date=date(2026, 9, 28),
                type="run",
                training_load=34,
            ),
            Event(
                date=date(2026, 9, 28),
                type="ride",
                training_load=20,
            ),
            Event(
                date=date(2026, 9, 29),
                type="run",
                training_load=None,
            ),
            Event(
                date=date(2026, 9, 30),
                type="",
                training_load=10,
            ),
        ]

        self.assertEqual(
            [(date(2026, 9, 28), 54)],
            daily_planned_load(
                events,
                date(2026, 9, 1),
                date(2026, 10, 31),
            ),
        )

    def test_daily_planned_load_split_separates_sports(self):
        events = [
            Event(
                date=date(2026, 9, 28),
                type="run",
                training_load=34,
            ),
            Event(
                date=date(2026, 9, 28),
                type="ride",
                training_load=20,
            ),
            Event(
                date=date(2026, 9, 29),
                type="run",
                training_load=None,
            ),
            Event(
                date=date(2026, 9, 30),
                type="",
                training_load=10,
            ),
        ]

        running, cross = daily_planned_load_split(
            events,
            date(2026, 9, 1),
            date(2026, 10, 31),
        )

        self.assertEqual([(date(2026, 9, 28), 34)], running)
        self.assertEqual([(date(2026, 9, 28), 20)], cross)

    def test_planned_workout_dates_skips_notes_and_keeps_duplicates(self):
        events = [
            Event(date=date(2026, 9, 28), type="run"),
            Event(date=date(2026, 9, 29), type=""),
            Event(date=date(2026, 9, 28), type="run"),
        ]

        self.assertEqual(
            [date(2026, 9, 28), date(2026, 9, 28)],
            planned_workout_dates(
                events,
                date(2026, 9, 1),
                date(2026, 10, 31),
            ),
        )

    def test_events_outside_range_are_ignored(self):
        events = [
            Event(
                date=date(2026, 11, 5),
                type="run",
                distance_m=5000,
            ),
        ]

        self.assertEqual(
            [],
            weekly_planned_distance(events, D, date(2026, 10, 31)),
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


class EffectiveVo2maxTests(unittest.TestCase):

    def test_oxygen_cost_over_the_hr_fraction(self):
        # 10 km in 60 min is 2.7778 m/s -> 166.67 m/min.
        activity = Activity(
            id="a",
            date=D,
            type="run",
            distance_m=10000,
            duration_s=3600,
            avg_hr=150,
        )

        value = effective_vo2max(activity, 192)

        self.assertAlmostEqual(47.15, value, places=2)

    def test_guards_the_fraction_and_the_speed(self):
        base = {
            "id": "a",
            "date": D,
            "type": "run",
            "distance_m": 10000,
            "duration_s": 3600,
        }

        self.assertIsNone(
            effective_vo2max(Activity(**base, avg_hr=200), 192)
        )
        self.assertIsNone(
            effective_vo2max(Activity(**base, avg_hr=80), 192)
        )
        self.assertIsNone(
            effective_vo2max(
                Activity(**{**base, "duration_s": 1400}, avg_hr=150),
                192,
            )
        )
        self.assertIsNone(
            effective_vo2max(
                Activity(**{**base, "duration_s": 7200}, avg_hr=150),
                192,
            )
        )

    def test_needs_a_heart_rate_and_a_running_max(self):
        activity = Activity(
            id="a",
            date=D,
            type="run",
            distance_m=10000,
            duration_s=3600,
        )

        self.assertIsNone(effective_vo2max(activity, 192))
        self.assertIsNone(
            effective_vo2max(
                Activity(**{**vars(activity), "avg_hr": 150}),
                None,
            )
        )
        self.assertIsNone(
            effective_vo2max(
                Activity(
                    id="b",
                    date=D,
                    type="ride",
                    distance_m=10000,
                    duration_s=3600,
                    avg_hr=150,
                ),
                192,
            )
        )

    def test_the_running_snapshot_in_force_wins(self):
        thresholds = [
            AthleteThreshold(
                effective_from=date(2024, 1, 1),
                sport="ride",
                max_hr=200,
            ),
            AthleteThreshold(
                effective_from=date(2024, 6, 1),
                sport="run",
                max_hr=198,
            ),
            AthleteThreshold(
                effective_from=date(2025, 1, 1),
                sport="run",
                max_hr=192,
            ),
        ]

        self.assertEqual(
            198,
            threshold_max_hr(thresholds, date(2024, 7, 1)),
        )
        self.assertEqual(
            192,
            threshold_max_hr(thresholds, date(2026, 1, 1)),
        )
        # A day before the first running snapshot uses that first one.
        self.assertEqual(
            198,
            threshold_max_hr(thresholds, date(2020, 1, 1)),
        )
        self.assertIsNone(threshold_max_hr([], D))

    def test_samples_keep_qualifying_runs_only(self):
        activities = [
            run(
                id="steady",
                date=D,
                distance_m=9000,
                duration_s=45 * 60,
                avg_hr=145,
            ),
            run(
                id="recovery",
                date=D,
                distance_m=6000,
                duration_s=45 * 60,
                avg_hr=130,
                workout_targets=["recovery"],
            ),
            run(
                id="long",
                date=D,
                distance_m=20000,
                duration_s=95 * 60,
                avg_hr=150,
            ),
            run(
                id="trail",
                date=D,
                type="trail_run",
                distance_m=9000,
                duration_s=45 * 60,
                avg_hr=150,
            ),
            run(
                id="no-hr",
                date=D,
                distance_m=9000,
                duration_s=45 * 60,
            ),
        ]
        thresholds = [
            AthleteThreshold(effective_from=D, sport="run", max_hr=192)
        ]

        samples = vo2max_samples(activities, thresholds)

        self.assertEqual(4, len(samples))
        self.assertNotIn(None, [sample.value for sample in samples])


class Vo2maxPointTests(unittest.TestCase):

    def test_daily_mean_and_carry_forward(self):
        points = vo2max_points(
            [
                Vo2maxSample(D, 40),
                Vo2maxSample(D, 60),
            ],
            D,
            D + timedelta(days=1),
        )

        self.assertEqual([D, D + timedelta(days=1)], [p.date for p in points])
        self.assertEqual(50, points[0].value)
        self.assertEqual(50, points[0].avg_42)
        self.assertIsNone(points[1].value)
        self.assertEqual(50, points[1].avg_42)
        self.assertEqual(50, points[1].avg_182)

    def test_the_short_average_moves_faster_than_the_long(self):
        points = vo2max_points(
            [
                Vo2maxSample(D, 50),
                Vo2maxSample(D + timedelta(days=30), 70),
            ],
            D,
            D + timedelta(days=30),
        )

        self.assertGreater(points[-1].avg_42, points[-1].avg_182)

    def test_starts_at_start_when_history_exists(self):
        points = vo2max_points(
            [Vo2maxSample(D, 60)],
            D + timedelta(days=2),
            D + timedelta(days=3),
        )

        self.assertEqual(
            [D + timedelta(days=2), D + timedelta(days=3)],
            [point.date for point in points],
        )
        self.assertEqual(60, points[0].avg_42)

    def test_no_samples_returns_nothing(self):
        self.assertEqual([], vo2max_points([], D, D))


class Vo2maxComparisonTests(unittest.TestCase):

    def test_garmin_is_grouped_by_device_and_labels_both_shapes(self):
        fit = Device(id="w1", manufacturer="garmin", product="fr645")
        enduro = Device(id="w2", manufacturer="garmin", product="enduro")
        unused = Device(id="w3", manufacturer="garmin", product="fr945")
        activities = [
            run(
                id="a",
                date=D,
                device_id="w1",
                vo2max_garmin=60,
            ),
            run(
                id="b",
                date=D + timedelta(days=10),
                device_id="w2",
                vo2max_garmin=61,
            ),
            run(
                id="ride",
                date=D,
                type="ride",
                device_id="w1",
                vo2max_garmin=99,
            ),
        ]

        series = garmin_vo2max_devices(
            activities,
            [fit, enduro, unused],
            D,
            D + timedelta(days=10),
        )

        self.assertEqual(
            ["Garmin Forerunner 645", "Garmin Enduro"],
            [item.label for item in series],
        )
        self.assertEqual([60], [m.value for m in series[0].measurements])
        self.assertEqual((D, 60.0), series[0].avg_42[0])
        self.assertEqual((D, 60.0), series[0].avg_182[0])
        self.assertEqual(11, len(series[0].avg_42))
        self.assertEqual(11, len(series[0].avg_182))

    def test_a_device_with_no_readings_in_range_is_dropped(self):
        old_watch = Device(
            id="old",
            manufacturer="garmin",
            product="fr235",
        )
        activities = [
            run(
                id="a",
                date=D,
                device_id="old",
                vo2max_garmin=50,
            )
        ]
        start = D + timedelta(days=365)

        self.assertEqual(
            [],
            garmin_vo2max_devices(
                activities,
                [old_watch],
                start,
                start,
            ),
        )

    def test_runalyze_gets_42_and_182_day_ewmas(self):
        activities = [
            run(
                id="a",
                date=D,
                vo2max_runalyze=60,
            ),
            run(
                id="b",
                date=D + timedelta(days=2),
                vo2max_runalyze=66,
            ),
        ]

        points = runalyze_vo2max_points(
            activities,
            D,
            D + timedelta(days=2),
        )

        self.assertEqual(
            [D, D + timedelta(days=1), D + timedelta(days=2)],
            [point.date for point in points],
        )
        self.assertIsNone(points[0].value)
        self.assertEqual(60, points[0].avg_42)
        self.assertEqual(60, points[0].avg_182)
        self.assertAlmostEqual(60.14, points[-1].avg_42, places=2)
        self.assertAlmostEqual(60.03, points[-1].avg_182, places=2)
        self.assertGreater(points[-1].avg_42, points[-1].avg_182)

    def test_race_vdot_uses_official_road_results_only(self):
        self.assertIsNone(race_vdot(0, 0))
        self.assertAlmostEqual(49.8, race_vdot(5000, 1200), places=1)

        race = run(
            id="race",
            date=D,
            workout_methods=["race"],
        )
        trail = run(
            id="trail",
            date=D,
            type="trail_run",
            workout_methods=["race"],
        )
        official = {
            "race": OfficialRaceResult(
                activity_id="race",
                official_distance_m=5000,
                official_time_s=1200,
            ),
            "trail": OfficialRaceResult(
                activity_id="trail",
                official_distance_m=5000,
                official_time_s=1200,
            ),
        }
        results = race_results(
            [race, trail],
            official_by_activity(official.values()),
        )

        self.assertEqual(1, len(race_vdots(results)))

    def test_methods_assembles_every_series(self):
        methods = vo2max_methods(
            [
                run(
                    id="a",
                    date=D,
                    distance_m=10000,
                    duration_s=3600,
                    avg_hr=150,
                    vo2max_garmin=58,
                    vo2max_runalyze=61,
                )
            ],
            [AthleteThreshold(effective_from=D, sport="run", max_hr=192)],
            [],
            [],
            D,
            D,
        )

        self.assertTrue(methods.all_runs)
        self.assertEqual(1, len(methods.garmin))
        self.assertTrue(methods.runalyze)
        self.assertEqual([], methods.races)


if __name__ == "__main__":
    unittest.main()
