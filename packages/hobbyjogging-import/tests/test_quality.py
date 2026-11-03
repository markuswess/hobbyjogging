import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.quality import (
    MANUAL_FLAG,
    quality_findings,
    record_manual_flag,
    record_quality_findings,
)


def _findings(
    *,
    sport="run",
    duration_s=3600,
    elapsed_s=3700,
    distance_m=10000,
):
    return quality_findings(
        sport=sport,
        duration_s=duration_s,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
    )


class QualityRuleTests(unittest.TestCase):

    def test_healthy_activity_has_no_findings(self):
        self.assertEqual([], _findings())

    def test_zero_duration_with_elapsed_time(self):
        findings = _findings(duration_s=0, elapsed_s=600)

        self.assertEqual(1, len(findings))
        self.assertEqual("zero_duration", findings[0].rule)
        self.assertIn("600", findings[0].detail)

    def test_zero_duration_without_elapsed_time(self):
        findings = _findings(duration_s=0, elapsed_s=0)

        self.assertEqual(1, len(findings))
        self.assertEqual("zero_duration", findings[0].rule)

    def test_zero_distance_only_for_pace_sports(self):
        findings = _findings(distance_m=0)

        self.assertEqual(1, len(findings))
        self.assertEqual("zero_distance", findings[0].rule)

        # Sports without distance requirements are not flagged.
        self.assertEqual(
            [], _findings(sport="training", distance_m=0)
        )
        self.assertEqual(
            [], _findings(sport="racket", distance_m=0)
        )

    def test_normal_cycling_pace_is_not_flagged(self):
        # ~31 km/h is a normal road-bike pace.
        self.assertEqual(
            [], _findings(sport="ride", duration_s=1505, distance_m=13132)
        )
        self.assertEqual(
            [], _findings(sport="mtb_ride", duration_s=669, distance_m=6239)
        )
        # Slow riding (pushing the bike, unicycle) is real data, not junk.
        self.assertEqual(
            [], _findings(sport="ride", duration_s=2310, distance_m=3601)
        )
        # Absurd mismatch (21 km in 2 minutes) gets flagged.
        self.assertEqual(
            1,
            len(
                _findings(sport="ride", duration_s=120, distance_m=21000)
            ),
        )

    def test_too_fast_pace_within_pace_sports(self):
        findings = _findings(duration_s=1100, distance_m=10000)

        self.assertEqual(1, len(findings))
        self.assertEqual("implied_pace", findings[0].rule)
        self.assertIn("1:50", findings[0].detail)

    def test_too_slow_pace(self):
        findings = _findings(duration_s=7200, distance_m=5000)

        self.assertEqual(1, len(findings))
        self.assertEqual("implied_pace", findings[0].rule)
        self.assertIn("24:00", findings[0].detail)

    def test_pace_boundaries_are_inclusive(self):
        self.assertEqual([], _findings(duration_s=600, distance_m=5000))
        self.assertEqual([], _findings(duration_s=3000, distance_m=5000))
        # Ride window boundaries.
        self.assertEqual(
            [], _findings(sport="ride", duration_s=900, distance_m=1000)
        )
        self.assertEqual(
            [], _findings(sport="ride", duration_s=180, distance_m=5000)
        )
        self.assertEqual(
            1,
            len(
                _findings(sport="ride", duration_s=990, distance_m=1000)
            ),
        )

    def test_non_pace_sports_skip_pace_rule(self):
        self.assertEqual(
            [], _findings(sport="swim", duration_s=7200, distance_m=5000)
        )
        self.assertEqual(
            [], _findings(sport="", duration_s=7200, distance_m=5000)
        )


class RecordQualityFindingsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run"},
            source="test",
            source_record_id=None,
        )

    def _record(self, **overrides):
        kwargs = {
            "activity_id": "a1",
            "source_record_id": None,
            "import_run_id": self.run_id,
            "sport": "run",
            "duration_s": 3600,
            "elapsed_s": 3700,
            "distance_m": 10000,
        }
        kwargs.update(overrides)
        return record_quality_findings(self.writer, **kwargs)

    def test_records_findings_once_and_is_idempotent(self):
        recorded = self._record(activity_id="a1", duration_s=0, elapsed_s=0)

        self.assertEqual(1, recorded)

        again = self._record(activity_id="a1", duration_s=0, elapsed_s=0)
        self.assertEqual(0, again)

        items = self.writer.review_items(status="open")
        self.assertEqual(1, len(items))
        self.assertEqual("quality", items[0]["category"])
        self.assertEqual("a1", items[0]["activity_id"])

    def test_changed_values_create_a_new_finding(self):
        self._record(activity_id="a1", distance_m=0)

        recorded = self._record(
            activity_id="a1",
            duration_s=0,
            elapsed_s=0,
        )

        self.assertEqual(1, recorded)
        items = self.writer.review_items(status="all")
        self.assertEqual(2, len(items))

    def test_manual_flag_is_idempotent(self):
        created = record_manual_flag(
            self.writer,
            activity_id="a1",
            category=MANUAL_FLAG,
            detail="suspect gps trace",
            severity="warn",
        )
        repeat = record_manual_flag(
            self.writer,
            activity_id="a1",
            category=MANUAL_FLAG,
            detail="suspect gps trace",
            severity="warn",
        )

        self.assertEqual(1, created)
        self.assertEqual(0, repeat)

        other = record_manual_flag(
            self.writer,
            activity_id="a1",
            category=MANUAL_FLAG,
            detail="different reason",
            severity="info",
        )
        self.assertEqual(1, other)

        items = self.writer.review_items()
        self.assertEqual(2, len(items))


if __name__ == "__main__":
    unittest.main()
