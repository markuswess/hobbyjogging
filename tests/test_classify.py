import unittest
from datetime import date

from intervals_report.classify import category_breakdown, classify
from intervals_report.model import Activity, Interval

D = date(2026, 10, 1)


def activity(**overrides):
    values = dict(id="a", date=D, type="run", name="", duration_s=50 * 60)
    values.update(overrides)
    return Activity(**values)


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

    def test_quality_requires_rpe_4(self):
        self.assertEqual(
            "quality/intervals/other",
            classify(activity(rpe=4)).path,
        )
        self.assertEqual(
            "non-quality/easy",
            classify(activity(rpe=3, duration_s=60 * 60)).path,
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
            "quality/intervals/subt-long",
            classify(activity(rpe=4, name="subT"), work(351, 351)).path,
        )

    def test_subt_ignores_strides(self):
        intervals = work(302, 300, 334, 333, 348, 12, 18, 18)
        self.assertEqual(
            "quality/intervals/subt-medium",
            classify(activity(rpe=5, name="5x5' subT medium"), intervals).path,
        )

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
