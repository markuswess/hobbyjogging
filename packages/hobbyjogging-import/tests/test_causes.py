import json
import unittest

from hobbyjogging_core import FieldConflict, TrainingWriter, connect, migrate

from hobbyjogging_import.causes import (
    ACTIVITY_TRIMMED,
    CAUSES,
    DISTANCE_ESTIMATE,
    ELAPSED_DEFINITION,
    HR_SENSOR_ANOMALY,
    MOVING_ESTIMATE,
    SMALL_DIFFERENCE,
    SPORT_VOCABULARY,
    START_OFFSET,
    UNCLASSIFIED,
    UNKNOWN,
    annotate_conflicts,
    cause_counts,
    classify_conflict,
    resolve_by_cause,
)


class CauseTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.activity_id = "a1"

    # -- fixtures -----------------------------------------------------------

    def _seed(self, intervals_payload, fit_payload, values):
        self.intervals_record = self.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id="i1",
            checksum="ci",
            payload_json=json.dumps(intervals_payload),
            import_run_id=self.run_id,
        )
        self.fit_record = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="f1",
            checksum="cf",
            payload_json=json.dumps(fit_payload),
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            self.activity_id,
            {
                "local_date": "2022-05-17",
                "sport": "run",
                **values,
            },
            source="intervals",
            source_record_id=self.intervals_record,
        )
        self.writer.link_activity_source(
            self.activity_id,
            self.intervals_record,
            match_method="created",
        )
        self.writer.link_activity_source(
            self.activity_id,
            self.fit_record,
            match_method="created",
        )
        self.conn.commit()

    def _elapsed_fixture(self):
        self._seed(
            {
                "icu_recording_time": 1699,
                "elapsed_time": 2365,
                "moving_time": 1679,
                "distance": 4777.07,
                "average_heartrate": 114,
                "max_heartrate": 130,
            },
            {
                "session": {
                    "duration_s": 1690.66,
                    "elapsed_s": 4854.235,
                    "moving_s": None,
                    "distance_m": 4777.07,
                    "avg_hr": 115,
                    "max_hr": 130,
                }
            },
            {
                "duration_s": 1699,
                "elapsed_s": 2365,
                "moving_s": 1679,
                "distance_m": 4777.07,
                "avg_hr": 114,
            },
        )

    def _classify(self, field_name, current_value, incoming_value):
        return classify_conflict(
            self.conn,
            activity_id=self.activity_id,
            field_name=field_name,
            current_source="intervals",
            current_value=current_value,
            incoming_source="fit",
            incoming_value=incoming_value,
            incoming_source_record_id=self.fit_record,
        )

    def _item(self, *, field_name, cause, fingerprint, detail="differs"):
        item_id, _ = self.writer.record_review_item(
            category="field_conflict",
            detail=f"{field_name} {detail}",
            context={
                "rule": "field_conflict",
                "field": field_name,
                "current": {"source": "intervals", "value": 1},
                "incoming": {"source": "fit", "value": 2},
                **({"cause": cause} if cause else {}),
            },
            fingerprint=fingerprint,
            activity_id=self.activity_id,
            source_record_id=self.fit_record,
            import_run_id=self.run_id,
        )
        self.conn.commit()
        return item_id

    # -- classification -----------------------------------------------------

    def test_elapsed_conflict_is_the_definition_difference(self):
        self._elapsed_fixture()

        cause, note = self._classify("elapsed_s", 2365, 4854.235)

        self.assertEqual(ELAPSED_DEFINITION, cause)
        self.assertIn("last-record offset", note)
        self.assertEqual("info", CAUSES[cause].severity)
        self.assertTrue(CAUSES[cause].resolvable)

    def test_trimmed_activity_wins_over_field_specific_causes(self):
        self._seed(
            {
                "icu_recording_time": 1185,
                "elapsed_time": 1252,
                "moving_time": 1132,
                "distance": 2223.6,
                "average_heartrate": 99,
                "max_heartrate": 120,
            },
            {
                "session": {
                    "duration_s": 2226.108,
                    "elapsed_s": 2654.411,
                    "moving_s": None,
                    "distance_m": 5481.93,
                    "avg_hr": 106,
                    "max_hr": 127,
                }
            },
            {
                "duration_s": 1185,
                "elapsed_s": 1252,
                "moving_s": 1132,
                "distance_m": 2223.6,
                "avg_hr": 99,
            },
        )

        for field_name, current, incoming in (
            ("duration_s", 1185, 2226.108),
            ("elapsed_s", 1252, 2654.411),
            ("avg_hr", 99, 106),
        ):
            cause, _ = self._classify(field_name, current, incoming)
            self.assertEqual(ACTIVITY_TRIMMED, cause, field_name)

    def test_implausible_max_hr_is_a_sensor_anomaly(self):
        self._seed(
            {
                "icu_recording_time": 4706,
                "elapsed_time": 4909,
                "moving_time": 4610,
                "distance": 22100.45,
                "average_heartrate": 137,
                "max_heartrate": 190,
            },
            {
                "session": {
                    "duration_s": 4648.868,
                    "elapsed_s": 4908.844,
                    "moving_s": None,
                    "distance_m": 22100.45,
                    "avg_hr": 191,
                    "max_hr": 230,
                }
            },
            {
                "duration_s": 4706,
                "elapsed_s": 4909,
                "moving_s": 4610,
                "distance_m": 22100.45,
                "avg_hr": 137,
            },
        )

        cause, note = self._classify("avg_hr", 137, 191)

        self.assertEqual(HR_SENSOR_ANOMALY, cause)
        self.assertIn("230 bpm", note)
        self.assertFalse(CAUSES[cause].resolvable)

    def test_small_difference_is_advisory(self):
        self._elapsed_fixture()

        cause, _ = self._classify("duration_s", 1506.44, 1539)

        self.assertEqual(SMALL_DIFFERENCE, cause)
        self.assertTrue(CAUSES[cause].resolvable)

    def test_moving_time_is_an_estimate(self):
        self._elapsed_fixture()

        cause, _ = self._classify("moving_s", 1679, 1705)

        self.assertEqual(MOVING_ESTIMATE, cause)
        self.assertTrue(CAUSES[cause].resolvable)

    def test_sport_and_start_have_their_own_causes(self):
        self._elapsed_fixture()

        sport, _ = self._classify("sport", "run", "trail_run")
        start, _ = self._classify(
            "started_at_utc",
            "2022-05-17T12:56:32Z",
            "2022-05-17T12:56:45Z",
        )

        self.assertEqual(SPORT_VOCABULARY, sport)
        self.assertEqual(START_OFFSET, start)
        self.assertFalse(CAUSES[sport].resolvable)
        self.assertTrue(CAUSES[start].resolvable)

    def test_distance_beyond_five_percent_is_an_estimate(self):
        self._elapsed_fixture()

        cause, _ = self._classify("distance_m", 4777.07, 5300.0)

        self.assertEqual(DISTANCE_ESTIMATE, cause)

    def test_plausible_hr_shift_without_a_summary_signal_is_unknown(self):
        self._seed(
            {
                "icu_recording_time": 983,
                "elapsed_time": 984,
                "moving_time": 982,
                "distance": 4961.4,
                "average_heartrate": 174,
                "max_heartrate": 189,
            },
            {
                "session": {
                    "duration_s": 984.224,
                    "elapsed_s": 984.224,
                    "moving_s": None,
                    "distance_m": 4961.4,
                    "avg_hr": 152,
                    "max_hr": 173,
                }
            },
            {
                "duration_s": 983,
                "elapsed_s": 984,
                "moving_s": 982,
                "distance_m": 4961.4,
                "avg_hr": 174,
            },
        )

        cause, _ = self._classify("avg_hr", 174, 152)

        self.assertEqual(UNKNOWN, cause)
        self.assertFalse(CAUSES[cause].resolvable)

    # -- recording and backfill ---------------------------------------------

    def test_record_field_conflicts_stores_the_cause(self):
        from hobbyjogging_import.quality import record_field_conflicts

        self._elapsed_fixture()

        recorded = record_field_conflicts(
            self.writer,
            activity_id=self.activity_id,
            source_record_id=self.fit_record,
            import_run_id=self.run_id,
            conflicts=[
                FieldConflict(
                    activity_id=self.activity_id,
                    field_name="elapsed_s",
                    current_value=2365,
                    incoming_value=4854.235,
                    current_source="intervals",
                    incoming_source="fit",
                    source_record_id=self.fit_record,
                )
            ],
        )

        self.assertEqual(1, recorded)
        item = self.writer.review_items(
            category="field_conflict",
            status="open",
        )[0]
        context = json.loads(item["context_json"])
        self.assertEqual(ELAPSED_DEFINITION, context["cause"])
        self.assertTrue(context["cause_note"])
        self.assertEqual("info", item["severity"])

    def test_annotate_backfills_unclassified_items_idempotently(self):
        self._elapsed_fixture()
        self._item(
            field_name="elapsed_s",
            cause=None,
            fingerprint="fp-old",
        )

        first = annotate_conflicts(self.writer)
        second = annotate_conflicts(self.writer)

        self.assertEqual(1, first.checked)
        self.assertEqual(1, first.updated)
        self.assertEqual(0, second.updated)
        self.assertEqual(1, second.unchanged)

        item = self.writer.review_items(
            category="field_conflict",
            status="open",
        )[0]
        self.assertEqual(
            ELAPSED_DEFINITION,
            json.loads(item["context_json"])["cause"],
        )
        self.assertEqual("info", item["severity"])

    def test_annotate_dry_run_writes_nothing(self):
        self._elapsed_fixture()
        self._item(field_name="elapsed_s", cause=None, fingerprint="fp-old")

        summary = annotate_conflicts(self.writer, dry_run=True)

        self.assertEqual(1, summary.updated)
        item = self.writer.review_items(
            category="field_conflict",
            status="open",
        )[0]
        self.assertNotIn("cause", json.loads(item["context_json"]))
        self.assertEqual("warn", item["severity"])

    # -- bulk resolve -------------------------------------------------------

    def test_resolve_by_cause_only_allows_advisory_causes(self):
        with self.assertRaises(ValueError):
            resolve_by_cause(self.writer, ACTIVITY_TRIMMED)
        with self.assertRaises(ValueError):
            resolve_by_cause(self.writer, "not_a_cause")

    def test_resolve_by_cause_and_dry_run(self):
        self._elapsed_fixture()
        self._item(
            field_name="elapsed_s",
            cause=ELAPSED_DEFINITION,
            fingerprint="fp-1",
        )
        self._item(
            field_name="avg_hr",
            cause=HR_SENSOR_ANOMALY,
            fingerprint="fp-2",
        )

        dry = resolve_by_cause(
            self.writer,
            ELAPSED_DEFINITION,
            dry_run=True,
        )
        self.assertEqual(1, dry.resolved)
        self.assertEqual(
            2,
            len(
                self.writer.review_items(
                    category="field_conflict",
                    status="open",
                )
            ),
        )

        real = resolve_by_cause(self.writer, ELAPSED_DEFINITION)
        self.assertEqual(1, real.resolved)

        open_items = self.writer.review_items(
            category="field_conflict",
            status="open",
        )
        self.assertEqual(1, len(open_items))
        self.assertEqual(
            HR_SENSOR_ANOMALY,
            json.loads(open_items[0]["context_json"])["cause"],
        )

    # -- summary ------------------------------------------------------------

    def test_cause_counts_groups_by_cause_and_field(self):
        self._elapsed_fixture()
        self._item(
            field_name="elapsed_s",
            cause=ELAPSED_DEFINITION,
            fingerprint="fp-1",
        )
        self._item(
            field_name="elapsed_s",
            cause=ELAPSED_DEFINITION,
            fingerprint="fp-2",
        )
        self._item(
            field_name="duration_s",
            cause=ACTIVITY_TRIMMED,
            fingerprint="fp-3",
        )
        self._item(field_name="duration_s", cause=None, fingerprint="fp-4")

        counts = {entry.cause: entry for entry in cause_counts(self.writer)}

        self.assertEqual(2, counts[ELAPSED_DEFINITION].count)
        self.assertEqual({"elapsed_s": 2}, counts[ELAPSED_DEFINITION].fields)
        self.assertEqual(1, counts[ACTIVITY_TRIMMED].count)
        self.assertEqual(1, counts[UNCLASSIFIED].count)
        self.assertFalse(counts[UNCLASSIFIED].resolvable)


if __name__ == "__main__":
    unittest.main()
