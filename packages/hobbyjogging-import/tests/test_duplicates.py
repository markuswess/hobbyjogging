import unittest
from datetime import date

from hobbyjogging_core.model import Activity

from hobbyjogging_import.duplicates import (
    find_duplicates,
    preferred_activity,
    same_session,
)

DAY = date(2026, 10, 1)


def activity(
    activity_id,
    *,
    day=DAY,
    sport="run",
    distance=10000.0,
    duration=3600.0,
    start="2026-10-01T08:00:00Z",
    hr=None,
):
    return Activity(
        id=activity_id,
        date=day,
        type=sport,
        distance_m=distance,
        duration_s=duration,
        started_at_utc=start,
        avg_hr=hr,
    )


class DuplicateRuleTests(unittest.TestCase):

    def test_same_day_sport_distance_duration_is_a_pair(self):
        pair = same_session(activity("a"), activity("b"))

        self.assertIsNotNone(pair)
        self.assertEqual(("a", "b"), pair.ids)
        self.assertEqual(0.0, pair.distance_delta_m)

    def test_a_start_difference_beyond_fifteen_minutes_is_not_a_pair(self):
        pair = same_session(
            activity("a", start="2026-10-01T08:00:00Z"),
            activity("b", start="2026-10-01T08:16:00Z"),
        )

        self.assertIsNone(pair)

    def test_a_start_difference_within_fifteen_minutes_is_a_pair(self):
        pair = same_session(
            activity("a", start="2026-10-01T08:00:00Z"),
            activity("b", start="2026-10-01T08:15:00Z"),
        )

        self.assertIsNotNone(pair)
        self.assertEqual(900.0, pair.start_delta_s)

    def test_a_missing_start_keeps_the_same_day_fallback(self):
        pair = same_session(
            activity("a", start="2026-10-01T08:00:00Z"),
            activity("b", start=""),
        )

        self.assertIsNotNone(pair)
        self.assertIsNone(pair.start_delta_s)

    def test_two_missing_starts_still_pair(self):
        pair = same_session(
            activity("a", start=""),
            activity("b", start=""),
        )

        self.assertIsNotNone(pair)
        self.assertIsNone(pair.start_delta_s)

    def test_sport_day_distance_duration_and_hr_must_agree(self):
        base = activity("a", hr=150)
        self.assertIsNone(
            same_session(base, activity("b", sport="ride", hr=150))
        )
        self.assertIsNone(
            same_session(base, activity("b", day=date(2026, 10, 2), hr=150))
        )
        self.assertIsNone(
            same_session(base, activity("b", distance=11000.0, hr=150))
        )
        self.assertIsNone(
            same_session(base, activity("b", duration=3900.0, hr=150))
        )
        self.assertIsNone(
            same_session(base, activity("b", hr=160))
        )

    def test_missing_hr_is_allowed(self):
        pair = same_session(activity("a"), activity("b"))

        self.assertIsNotNone(pair)
        self.assertIsNone(pair.hr_delta)

    def test_find_duplicates_returns_each_pair_once(self):
        pairs = find_duplicates(
            [activity("a"), activity("b"), activity("c", distance=5000.0)]
        )

        self.assertEqual(1, len(pairs))
        self.assertEqual(("a", "b"), pairs[0].ids)

    def test_find_duplicates_skips_a_far_apart_same_day_pair(self):
        pairs = find_duplicates(
            [
                activity("morning", start="2026-10-01T06:00:00Z"),
                activity("evening", start="2026-10-01T18:00:00Z"),
            ]
        )

        self.assertEqual([], pairs)

    def test_find_duplicates_keeps_a_sheet_row_without_a_start(self):
        pairs = find_duplicates(
            [
                activity("device", start="2026-10-01T08:00:00Z"),
                activity("sheet", start=""),
            ]
        )

        self.assertEqual(1, len(pairs))
        self.assertEqual(("device", "sheet"), pairs[0].ids)

    def test_preferred_activity_is_the_sheet_only_copy(self):
        pair = same_session(activity("device"), activity("sheet"))
        sources = {"device": {"fit", "intervals"}, "sheet": {"sheet"}}

        self.assertEqual("sheet", preferred_activity(pair, sources).id)

    def test_preferred_activity_prefers_fewer_sources(self):
        pair = same_session(activity("one"), activity("two"))
        sources = {"one": {"fit"}, "two": {"fit", "intervals", "runalyze"}}

        self.assertEqual("one", preferred_activity(pair, sources).id)


if __name__ == "__main__":
    unittest.main()
