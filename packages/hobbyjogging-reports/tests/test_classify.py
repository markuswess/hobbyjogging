import unittest
from datetime import date

from hobbyjogging_core.model import Activity, Interval

from hobbyjogging_report.classify import category_breakdown

DEFAULT_DATE = date(2026, 10, 1)


def activity(**overrides):
    values = dict(
        id="a",
        date=DEFAULT_DATE,
        type="run",
        name="",
        duration_s=50 * 60,
    )
    values.update(overrides)
    return Activity(**values)


def work(*durations):
    return [
        Interval(type="WORK", group_id=str(n), duration_s=s, distance_m=s * 4)
        for n, s in enumerate(durations)
    ]


class CategoryBreakdownTests(unittest.TestCase):

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
