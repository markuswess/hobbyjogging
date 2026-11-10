import unittest

from hobbyjogging_report.analysis import work_intervals
from hobbyjogging_report.classify import category_breakdown, classify
from hobbyjogging_core.model import Interval
from support import activity_factory, make_interval

activity = activity_factory(duration_s=50 * 60)
iv = make_interval


def work(*durations):
    return [
        Interval(type="WORK", group_id=str(n), duration_s=s, distance_m=s * 4)
        for n, s in enumerate(durations)
    ]


class ClassifyTests(unittest.TestCase):

    def test_recovery_requires_rpe_1_and_short(self):
        self.assertEqual(
            "non-quality/recovery",
            classify(activity(rpe=1, duration_s=39 * 60)).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=1, duration_s=40 * 60)).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=2, duration_s=30 * 60)).path,
        )

    def test_quality_rpe_threshold(self):
        self.assertEqual(
            "quality/intervals/other",
            classify(activity(rpe=3.5)).path,
        )
        self.assertEqual(
            "quality/intervals/other",
            classify(activity(rpe=4)).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=3, duration_s=60 * 60)).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=2, duration_s=60 * 60)).path,
        )

    def test_rpe_3_can_be_quality(self):
        self.assertEqual(
            "quality/intervals/subt-medium",
            classify(
                activity(rpe=3, name="5x5' subT"),
                work(300, 300),
            ).path,
        )
        self.assertEqual(
            "quality/intervals/lt1",
            classify(activity(rpe=3, name="3x10' LT1")).path,
        )
        self.assertEqual(
            "quality/race",
            classify(activity(rpe=3, name="10k Race")).path,
        )
        self.assertEqual(
            "quality/tempo",
            classify(activity(rpe=3, name="tempo")).path,
        )
        self.assertEqual(
            "quality/intervals/other",
            classify(activity(rpe=3, intensity=0.9)).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=3, intensity=0.6)).path,
        )
        self.assertEqual(
            "quality/intervals/other",
            classify(
                activity(
                    rpe=3,
                    intensity=0.6,
                    pace_zone_times=[0, 0, 600, 600, 0],
                ),
            ).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(
                activity(
                    rpe=3,
                    pace_zone_times=[1200, 1200, 300, 300, 0],
                ),
            ).path,
        )

    def test_rpe_2_content_is_not_quality(self):
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=2, name="5x5' subT")).path,
        )

    def test_missing_rpe_inferred_from_intensity(self):
        self.assertEqual(
            "quality/intervals/other",
            classify(activity(rpe=None, intensity=0.9)).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=None, intensity=0.6)).path,
        )
        self.assertEqual(
            "unknown",
            classify(activity(rpe=None)).path,
        )
        self.assertEqual(
            "unknown",
            classify(activity(rpe=None, name="subT")).path,
        )

    def test_subt_rep_length(self):
        self.assertEqual(
            "quality/intervals/subt-short",
            classify(activity(rpe=4, name="subT"), work(240, 240)).path,
        )
        self.assertEqual(
            "quality/intervals/subt-medium",
            classify(activity(rpe=4, name="subT"), work(241, 241)).path,
        )
        self.assertEqual(
            "quality/intervals/subt-medium",
            classify(activity(rpe=4, name="subT"), work(420, 420)).path,
        )
        self.assertEqual(
            "quality/intervals/subt-long",
            classify(activity(rpe=4, name="subT"), work(421, 421)).path,
        )

    def test_subt_ignores_strides(self):
        intervals = work(302, 300, 334, 333, 348, 12, 18, 18)
        self.assertEqual(
            "quality/intervals/subt-medium",
            classify(activity(rpe=5, name="5x5' subT medium"), intervals).path,
        )

    def test_old_style_work_labels_do_not_skew_subt(self):
        # Warm-up, cool-down and recovery jogs are all tagged WORK.
        intervals = [
            iv(1200, 4000),  # warm-up, 300 s/km
            *[iv(300, 1300) for _ in range(5)],  # reps, 231 s/km
            *[iv(100, 300) for _ in range(4)],  # recoveries, 333 s/km
            iv(1200, 3800),  # cool-down, 316 s/km
        ]

        self.assertEqual(
            "quality/intervals/subt-medium",
            classify(
                activity(rpe=5, name="5x5' subT"),
                intervals,
            ).path,
        )

    def test_old_style_slow_recovery_jogs(self):
        # Unlabeled recovery jogs are much slower than the 800 m reps.
        intervals = [
            iv(1111, 3445),  # warm-up
            *[iv(161, 780) for _ in range(8)],  # 800 m reps
            *[iv(82, 135) for _ in range(8)],  # recovery jogs
            iv(2804, 8530),  # cool-down
        ]

        self.assertEqual(
            "quality/intervals/subt-short",
            classify(
                activity(rpe=5, name="8x800m subT short"),
                intervals,
            ).path,
        )

    def test_old_style_short_surges_are_ignored(self):
        # Fast 20-26 s surges after the reps are not work reps.
        intervals = [
            iv(601, 2692),
            iv(571, 2617),
            iv(542, 2504),
            iv(26, 152),
            iv(24, 142),
            iv(20, 110),
        ]

        self.assertEqual(
            "quality/intervals/subt-long",
            classify(
                activity(rpe=6, name="3x9' subT long"),
                intervals,
            ).path,
        )

    def test_old_style_pyramid_keeps_all_reps(self):
        reps = [60, 120, 180, 240, 300, 240, 180, 120, 60]
        intervals = [
            iv(duration, duration / 210 * 1000)
            for duration in reps
        ]

        self.assertEqual(
            "quality/intervals/subt-short",
            classify(
                activity(rpe=6, name="subT pyramid"),
                intervals,
            ).path,
        )
        self.assertEqual(9, len(work_intervals(intervals)))

    def test_lt1_wins_over_subt(self):
        self.assertEqual(
            "quality/intervals/lt1",
            classify(
                activity(rpe=4, name="3x10' LT1 (subT)"),
                work(600, 600, 600),
            ).path,
        )
        self.assertEqual(
            "quality/intervals/lt1",
            classify(
                activity(rpe=4, name="3x9' LT1", description="instead of subT"),
            ).path,
        )

    def test_keywords_come_from_name_only(self):
        self.assertEqual(
            "quality/intervals/other",
            classify(
                activity(rpe=4, name="session", description="did 3x10' subT"),
            ).path,
        )

    def test_content_wins_over_longrun(self):
        self.assertEqual(
            "quality/tempo",
            classify(activity(rpe=5, name="2h with tempo", duration_s=120 * 60)).path,
        )
        self.assertEqual(
            "quality/intervals/subt-medium",
            classify(
                activity(rpe=5, name="subT", duration_s=120 * 60),
                work(300, 300),
            ).path,
        )
        self.assertEqual(
            "quality/longrun",
            classify(activity(rpe=5, name="long run", duration_s=100 * 60)).path,
        )

    def test_low_rpe_long_run_is_longrun(self):
        self.assertEqual(
            "quality/longrun",
            classify(activity(rpe=3, name="long", duration_s=100 * 60)).path,
        )

    def test_cross_training(self):
        self.assertEqual(
            "cross-training",
            classify(activity(type="hike", duration_s=103 * 60)).path,
        )
        self.assertEqual(
            "cross-training",
            classify(activity(type="ride", rpe=8)).path,
        )

    def test_race_keyword(self):
        self.assertEqual(
            "quality/race",
            classify(activity(rpe=9, name="10k Race")).path,
        )

    def test_category_breakdown(self):
        activities = [
            activity(
                id="a", rpe=5, name="subT",
                duration_s=50 * 60, training_load=50,
            ),
            activity(
                id="b", rpe=9, name="10k Race",
                duration_s=30 * 60, training_load=80,
            ),
            activity(
                id="c", rpe=1, name="Easy",
                duration_s=60 * 60, training_load=20,
            ),
            activity(
                id="d", type="ride", name="Ride",
                duration_s=40 * 60, training_load=40,
            ),
        ]

        stats = category_breakdown(
            activities,
            {"a": work(300, 300)},
        )

        self.assertEqual(
            [
                "quality/intervals/subt-medium",
                "quality/race",
                "non-quality/easy",
                "cross-training",
            ],
            [stat.path for stat in stats],
        )
        self.assertEqual([1, 1, 1, 1], [stat.sessions for stat in stats])
        self.assertAlmostEqual(1.0, sum(stat.time_share for stat in stats))
        self.assertAlmostEqual(1.0, sum(stat.load_share for stat in stats))

    def test_category_breakdown_without_intervals(self):
        stats = category_breakdown([activity(rpe=5, name="subT")])
        self.assertEqual("quality/intervals/subt", stats[0].path)

    def test_race_support(self):
        self.assertEqual(
            "quality/race-support/warmup",
            classify(activity(rpe=2, name="Race warm up", duration_s=20 * 60)).path,
        )
        self.assertEqual(
            "quality/race-support/cooldown",
            classify(activity(rpe=3, name="Race cool down", duration_s=18 * 60)).path,
        )
        # Bare names are enough, and RPE 1 no longer makes it recovery.
        self.assertEqual(
            "quality/race-support/cooldown",
            classify(activity(rpe=1, name="Cool down", duration_s=17 * 60)).path,
        )
        self.assertEqual(
            "quality/race-support/warmup",
            classify(activity(rpe=2, name="Warm up", duration_s=21 * 60)).path,
        )


if __name__ == "__main__":
    unittest.main()

class StoredClassificationTests(unittest.TestCase):
    """Reports prefer the stored classification, with a heuristic fallback."""

    def test_stored_quality_wins_over_a_plain_name(self):
        self.assertEqual(
            "quality/tempo",
            classify(
                activity(
                    name="Easy",
                    workout_methods=["tempo"],
                    workout_targets=["threshold"],
                )
            ).path,
        )

    def test_stored_non_quality_wins_over_a_quality_name(self):
        self.assertEqual(
            "non-quality/easy",
            classify(
                activity(
                    name="Tempo run",
                    workout_methods=["continuous"],
                    workout_targets=["base"],
                )
            ).path,
        )

    def test_stored_recovery_target_is_recovery(self):
        self.assertEqual(
            "non-quality/recovery",
            classify(
                activity(
                    workout_methods=["continuous"],
                    workout_targets=["recovery"],
                )
            ).path,
        )

    def test_stored_long_run_method_beats_a_short_duration(self):
        self.assertEqual(
            "quality/longrun",
            classify(
                activity(
                    duration_s=60 * 60,
                    workout_methods=["long_run"],
                    workout_targets=["base"],
                )
            ).path,
        )

    def test_stored_quality_keeps_the_heuristic_detail(self):
        self.assertEqual(
            "quality/intervals/subt",
            classify(
                activity(
                    name="subT",
                    workout_methods=["intervals"],
                    workout_targets=["subthreshold"],
                )
            ).path,
        )

    def test_race_support_still_wins(self):
        self.assertEqual(
            "quality/race-support/warmup",
            classify(
                activity(
                    name="Warm up",
                    workout_methods=["continuous"],
                    workout_targets=["base"],
                )
            ).path,
        )

    def test_unclassified_activity_uses_the_heuristic(self):
        self.assertEqual(
            "quality/race",
            classify(activity(name="Town race", intensity=0.95)).path,
        )

    def test_use_stored_false_is_the_pure_heuristic(self):
        self.assertEqual(
            "unknown",
            classify(
                activity(
                    name="",
                    workout_methods=["tempo"],
                    workout_targets=["threshold"],
                ),
                use_stored=False,
            ).path,
        )
