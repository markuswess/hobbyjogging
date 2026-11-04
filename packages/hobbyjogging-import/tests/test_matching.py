import unittest
from datetime import datetime, timedelta, timezone

from hobbyjogging_core import connect, migrate
from hobbyjogging_import.matching import (
    ActivityMatcher,
    ActivityWindow,
    AmbiguousMatchError,
    find_matches,
    match_window,
    parse_utc,
    select_unique_match,
)

UTC = timezone.utc
START = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


def _window(
    activity_id: str,
    start: datetime,
    duration_minutes: float,
) -> ActivityWindow:
    return ActivityWindow(
        activity_id=activity_id,
        start=start,
        end=start + timedelta(minutes=duration_minutes),
    )


class MatchWindowTests(unittest.TestCase):

    def test_normal_overlap_uses_shorter_activity(self):
        existing = _window("existing", START, 60)
        candidate = _window("candidate", START + timedelta(minutes=40), 30)

        match = match_window(candidate, existing)

        self.assertIsNotNone(match)
        self.assertEqual("existing", match.activity_id)
        self.assertEqual("temporal_overlap", match.match_method)
        self.assertAlmostEqual(20 / 30, match.confidence, places=4)
        self.assertEqual(1200, match.overlap_s)
        self.assertIsNone(match.fit_contained_ratio)

    def test_overlap_below_two_minutes_is_rejected(self):
        existing = _window("existing", START, 60)
        candidate = _window("candidate", START + timedelta(minutes=10), 1)

        self.assertIsNone(match_window(candidate, existing))

    def test_overlap_below_sixty_percent_of_shorter_is_rejected(self):
        existing = _window("existing", START, 60)
        candidate = _window("candidate", START + timedelta(minutes=45), 30)

        self.assertIsNone(match_window(candidate, existing))

    def test_contained_fit_segment_matches_larger_activity(self):
        existing = _window("existing", START, 60)
        candidate = _window("fit", START + timedelta(minutes=20), 10)

        match = match_window(candidate, existing, candidate_is_fit=True)

        self.assertIsNotNone(match)
        self.assertEqual("contained_fit", match.match_method)
        self.assertEqual(1.0, match.confidence)
        self.assertEqual(1.0, match.fit_contained_ratio)

    def test_partially_contained_fit_segment_is_rejected(self):
        existing = _window("existing", START, 60)
        candidate = _window("fit", START + timedelta(minutes=53), 10)

        self.assertIsNone(
            match_window(candidate, existing, candidate_is_fit=True)
        )

    def test_equal_windows_use_normal_overlap(self):
        existing = _window("existing", START, 30)
        candidate = _window("fit", START, 30)

        match = match_window(candidate, existing, candidate_is_fit=True)

        self.assertIsNotNone(match)
        self.assertEqual("temporal_overlap", match.match_method)

    def test_find_matches_returns_best_first(self):
        candidate = _window("candidate", START + timedelta(minutes=10), 30)
        existing = [
            _window("partial", START + timedelta(minutes=20), 30),
            _window("full", START + timedelta(minutes=10), 30),
        ]

        matches = find_matches(candidate, existing)

        self.assertEqual(["full", "partial"], [m.activity_id for m in matches])

    def test_select_unique_match_rejects_ambiguity(self):
        candidate = _window("candidate", START, 30)
        existing = [
            _window("first", START, 30),
            _window("second", START + timedelta(minutes=1), 30),
        ]
        matches = find_matches(candidate, existing)

        with self.assertRaises(AmbiguousMatchError) as context:
            select_unique_match(matches)

        self.assertEqual(2, len(context.exception.matches))

    def test_parse_utc_handles_z_and_naive_values(self):
        self.assertEqual(
            datetime(2026, 10, 1, 6, 0, tzinfo=UTC),
            parse_utc("2026-10-01T06:00:00Z"),
        )
        self.assertEqual(
            datetime(2026, 10, 1, 6, 0, tzinfo=UTC),
            parse_utc("2026-10-01T06:00:00"),
        )
        self.assertIsNone(parse_utc("not a timestamp"))


class ActivityMatcherTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.matcher = ActivityMatcher(self.conn)
        self._seed()

    def _seed(self):
        self.conn.executemany(
            """
            INSERT INTO activities (
                id, local_date, started_at_utc, sport, elapsed_s, duration_s
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "a1", "2026-10-01", "2026-10-01T06:00:00Z",
                    "run", 3600, 3500,
                ),
                (
                    "a2", "2026-10-01", "2026-10-01T08:00:00Z",
                    "ride", 1800, 1700,
                ),
                (
                    "no-start", "2026-10-01", None, "run", 3600, 3500,
                ),
            ],
        )

    def test_finds_overlapping_activity(self):
        matches = self.matcher.find(
            started_at_utc="2026-10-01T06:10:00Z",
            source="fit",
            elapsed_s=3600,
        )

        self.assertEqual(["a1"], [match.activity_id for match in matches])
        self.assertEqual("temporal_overlap", matches[0].match_method)

    def test_uses_elapsed_time_before_duration(self):
        matches = self.matcher.find(
            started_at_utc="2026-10-01T06:30:00Z",
            source="intervals",
            elapsed_s=2400,
            duration_s=60,
        )

        self.assertEqual(["a1"], [match.activity_id for match in matches])

    def test_uses_duration_when_elapsed_is_missing(self):
        self.conn.execute(
            "UPDATE activities SET elapsed_s = 0 WHERE id = 'a1'"
        )

        matches = self.matcher.find(
            started_at_utc="2026-10-01T06:10:00Z",
            source="fit",
            elapsed_s=0,
            duration_s=1800,
        )

        self.assertEqual(["a1"], [match.activity_id for match in matches])

    def test_excludes_known_activity(self):
        matches = self.matcher.find(
            started_at_utc="2026-10-01T06:10:00Z",
            source="fit",
            elapsed_s=1800,
            exclude_activity_id="a1",
        )

        self.assertEqual([], matches)

    def test_excluded_soft_deleted_activity_is_not_matched(self):
        self.conn.execute(
            "UPDATE activities SET excluded_at = CURRENT_TIMESTAMP "
            "WHERE id = 'a1'"
        )
        self.conn.commit()

        matches = self.matcher.find(
            started_at_utc="2026-10-01T06:10:00Z",
            source="fit",
            elapsed_s=3600,
        )

        self.assertEqual([], matches)

    def test_fit_segment_can_match_larger_activity(self):
        matches = self.matcher.find(
            started_at_utc="2026-10-01T06:20:00Z",
            source="fit",
            elapsed_s=600,
        )

        self.assertEqual(1, len(matches))
        self.assertEqual("contained_fit", matches[0].match_method)

    def test_missing_start_or_duration_returns_no_matches(self):
        self.assertEqual(
            [],
            self.matcher.find(
                started_at_utc="",
                source="fit",
                elapsed_s=1800,
            ),
        )
        self.assertEqual(
            [],
            self.matcher.find(
                started_at_utc="2026-10-01T06:10:00Z",
                source="fit",
                elapsed_s=0,
                duration_s=0,
            ),
        )


if __name__ == "__main__":
    unittest.main()
