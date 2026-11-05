import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.quality import (
    CONFLICT,
    MANUAL_FLAG,
    QUALITY,
    quality_findings,
    record_field_conflicts,
    record_manual_flag,
    record_quality_findings,
    refresh_activity_quality,
    review_fingerprint,
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

    def test_source_record_does_not_create_a_duplicate(self):
        source_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="f1",
            checksum="c1",
            import_run_id=self.run_id,
            payload_json="{}",
            raw_path="f1.fit",
        )

        self._record(
            activity_id="a1",
            source_record_id=source_id,
            duration_s=0,
            elapsed_s=0,
        )
        self._record(activity_id="a1", duration_s=0, elapsed_s=0)

        items = self.writer.review_items(status="open")
        self.assertEqual(1, len(items))
        self.assertEqual(source_id, items[0]["source_record_id"])

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


class RefreshActivityQualityTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "duration_s": 0,
                "elapsed_s": 0,
                "distance_m": 8200,
            },
            source="test",
            source_record_id=None,
        )
        self.item_id, _ = self.writer.record_review_item(
            category=QUALITY,
            detail="no timing data: duration is 0 s",
            context={"rule": "zero_duration", "duration_s": 0, "elapsed_s": 0},
            fingerprint=review_fingerprint(
                ["zero_duration", "a1",
                 {"rule": "zero_duration", "duration_s": 0, "elapsed_s": 0}],
            ),
            activity_id="a1",
        )

    def test_fixed_finding_is_resolved_and_activity_is_clean(self):
        self.writer.set_manual_field("a1", "duration_s", 2780)

        findings = refresh_activity_quality(
            self.writer,
            activity_id="a1",
            resolve_item_id=self.item_id,
            resolve_note="manual edit: duration_s",
        )

        self.assertEqual([], findings)
        item = self.writer.review_item(self.item_id)
        self.assertEqual("resolved", item["status"])
        self.assertEqual(
            "manual edit: duration_s",
            item["resolved_note"],
        )
        self.assertEqual(0, len(self.writer.review_items(status="open")))

    def test_superseded_finding_is_resolved_and_replaced(self):
        # Add an implied_pace item computed from the old 0/8.2 km values.
        old_context = {
            "rule": "implied_pace",
            "pace_s_per_km": 0.0,
            "duration_s": 0,
            "distance_m": 8200,
            "sport": "run",
        }
        self.writer.record_review_item(
            category=QUALITY,
            detail="old pace",
            context=old_context,
            fingerprint=review_fingerprint(
                ["implied_pace", "a1", None, old_context],
            ),
            activity_id="a1",
        )

        self.writer.set_manual_field("a1", "duration_s", 2780)
        findings = refresh_activity_quality(
            self.writer,
            activity_id="a1",
            resolve_note="manual edit",
        )

        # 2780 s over 8.2 km = 5:39 /km: healthy, everything resolves.
        self.assertEqual([], findings)
        self.assertEqual(0, len(self.writer.review_items(status="open")))

    def test_still_valid_scan_item_stays_open(self):
        # Make distance wrong: an in-window pace and zero distance coexist.
        self.writer.set_manual_field("a1", "duration_s", 2780)
        fresh = refresh_activity_quality(
            self.writer,
            activity_id="a1",
            resolve_item_id=self.item_id,
        )
        self.assertEqual([], fresh)
        self.assertEqual(0, len(self.writer.review_items(status="open")))

        # Now the activity becomes out of window; a new item is recorded.
        self.writer.set_manual_field("a1", "distance_m", 820000)
        findings = refresh_activity_quality(
            self.writer,
            activity_id="a1",
            resolve_note="manual edit",
        )
        self.assertEqual(1, len(findings))
        self.assertEqual("implied_pace", findings[0].rule)
        self.assertEqual(1, len(self.writer.review_items(status="open")))

    def test_unknown_activity_raises(self):
        with self.assertRaises(ValueError):
            refresh_activity_quality(self.writer, activity_id="nope")


class RecordFieldConflictsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.source_record_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="fit-1",
            checksum="c1",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "duration_s": 3415.411,
                "distance_m": 3734.23,
            },
            source="intervals",
            source_record_id=self.source_record_id,
        )

    def _conflicts(self, **overrides):
        from hobbyjogging_core import FieldConflict

        values = {
            "activity_id": "a1",
            "field_name": "duration_s",
            "current_value": 3415.411,
            "incoming_value": 1055,
            "current_source": "intervals",
            "incoming_source": "fit",
            "source_record_id": self.source_record_id,
        }
        values.update(overrides)
        return [FieldConflict(**values)]

    def _record(self, conflicts):
        return record_field_conflicts(
            self.writer,
            activity_id="a1",
            source_record_id=self.source_record_id,
            import_run_id=self.run_id,
            conflicts=conflicts,
        )

    def test_records_one_item_per_conflict(self):
        conflicts = self._conflicts() + self._conflicts(
            field_name="distance_m",
            current_value=3734.23,
            incoming_value=3210.99,
        )

        recorded = self._record(conflicts)

        self.assertEqual(2, recorded)
        items = self.writer.review_items(category=CONFLICT, status="open")
        self.assertEqual(2, len(items))
        details = " | ".join(item["detail"] for item in items)
        self.assertIn("duration_s differs", details)
        self.assertIn("56:55", details)
        self.assertIn("17:35", details)
        self.assertIn("distance_m differs", details)

        context = json.loads(items[0]["context_json"])
        self.assertEqual("field_conflict", context["rule"])
        self.assertEqual("intervals", context["current"]["source"])
        self.assertEqual("fit", context["incoming"]["source"])

    def test_repeated_import_is_idempotent(self):
        self.assertEqual(1, self._record(self._conflicts()))
        self.assertEqual(0, self._record(self._conflicts()))

        self.assertEqual(
            1,
            len(self.writer.review_items(category=CONFLICT, status="all")),
        )

    def test_changed_values_supersede_the_open_item(self):
        self._record(self._conflicts())
        self._record(self._conflicts(incoming_value=1200))

        open_items = self.writer.review_items(category=CONFLICT, status="open")
        all_items = self.writer.review_items(category=CONFLICT, status="all")
        self.assertEqual(1, len(open_items))
        self.assertEqual(2, len(all_items))
        self.assertEqual(1200, json.loads(open_items[0]["context_json"])
                         ["incoming"]["value"])
        superseded = [
            item for item in all_items if item["status"] == "resolved"
        ]
        self.assertEqual(1, len(superseded))
        self.assertIn("superseded", superseded[0]["resolved_note"])

    def test_different_fields_keep_separate_items(self):
        self._record(
            self._conflicts()
            + self._conflicts(
                field_name="distance_m",
                current_value=3734.23,
                incoming_value=3210.99,
            )
        )
        self._record(self._conflicts(incoming_value=1200))

        open_items = self.writer.review_items(category=CONFLICT, status="open")
        self.assertEqual(2, len(open_items))
        self.assertEqual(
            {"duration_s", "distance_m"},
            {json.loads(item["context_json"])["field"]
             for item in open_items},
        )

    def test_no_conflicts_records_nothing(self):
        self.assertEqual(0, self._record([]))
        self.assertEqual([], self.writer.review_items(category=CONFLICT))


if __name__ == "__main__":
    unittest.main()
