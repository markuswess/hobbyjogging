import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.fit import FitFileSummary, FitSession

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "activity_metrics_v1"
UTC = timezone.utc


class ActivityMetricsBackfillTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _activity(self, activity_id="a1", *, excluded=False, sport="run"):
        self.writer.upsert_activity(
            activity_id,
            {"local_date": "2024-06-01", "sport": sport},
            source="fit",
            source_record_id=None,
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _source(
        self,
        activity_id,
        source,
        payload,
        external="x1",
        *,
        raw_path=None,
        external_suffix=None,
    ):
        external_id = f"{source}-{external}"
        if external_suffix is not None:
            external_id = f"{external_id}:{external_suffix}"
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=external_id,
            checksum=f"c-{source}-{external}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
            raw_path=raw_path,
        )
        self.conn.execute(
            "INSERT INTO activity_sources "
            "(activity_id, source_record_id, match_method) VALUES (?, ?, 'test')",
            (activity_id, record_id),
        )
        self.conn.commit()
        return record_id

    def _row(self, activity_id="a1"):
        return self.conn.execute(
            "SELECT * FROM activity_metrics WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def test_fills_from_intervals_and_runalyze_in_authority_order(self):
        self._activity()
        self._source(
            "a1",
            "intervals",
            {
                "average_cadence": 86,
                "calories": 692,
                "average_altitude": 191.0,
            },
            external="i1",
        )
        self._source(
            "a1",
            "runalyze",
            {"power": 326, "gap": 13.62, "respiration": 34},
            external="r1",
        )

        result = self._run()

        self.assertEqual(1, result.counts["activities"])
        row = self._row()
        self.assertEqual(172.0, row["cadence"])
        self.assertEqual(692.0, row["calories_kcal"])
        self.assertEqual(191.0, row["altitude_avg_m"])
        self.assertEqual(326.0, row["power_w"])
        self.assertAlmostEqual(3.7833, row["gap_mps"], places=4)

    def test_second_run_is_unchanged(self):
        self._activity()
        self._source(
            "a1",
            "intervals",
            {"average_cadence": 86, "calories": 692},
            external="i1",
        )

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts["written"])
        self.assertGreaterEqual(result.counts["unchanged"], 1)

    def test_uses_a_new_stored_fit_payload_without_reparsing(self):
        self._activity()
        self._source(
            "a1",
            "fit",
            {
                "session": {
                    "cadence": 172.0,
                    "stride_m": 1.29,
                    "calories": 692.0,
                    "training_effect": 3.7,
                }
            },
            external="f1",
        )

        self._run()

        row = self._row()
        self.assertEqual(172.0, row["cadence"])
        self.assertEqual(1.29, row["stride_m"])
        self.assertEqual(692.0, row["calories_kcal"])
        self.assertEqual(3.7, row["training_effect"])

    def test_reads_an_old_fit_payload_from_the_archive(self):
        self._activity()
        self._source(
            "a1",
            "fit",
            {"session": {"calories": 692.0}},
            external="f1",
            raw_path=str(Path(__file__).resolve()),
            external_suffix="2",
        )
        session = FitSession(
            index=2,
            start_time_utc="2024-06-01T06:00:00Z",
            local_start="2024-06-01T08:00:00+02:00",
            tz_offset_min=120,
            sport="running",
            sub_sport="generic",
            canonical_sport="run",
            name="Run",
            elapsed_s=3600,
            duration_s=3500,
            distance_m=10000,
            cadence=172.0,
            stride_m=1.29,
        )
        summary = FitFileSummary(
            path=Path("x.fit"),
            file_type="activity",
            manufacturer="garmin",
            product="enduro",
            serial_number="1",
            time_created="",
            sessions=[session, session],
        )

        with patch(
            "hobbyjogging_maintenance.backfills.activity_metrics_v1."
            "parse_fit_file",
            return_value=summary,
        ):
            self._run()

        row = self._row()
        self.assertEqual(172.0, row["cadence"])
        self.assertEqual(1.29, row["stride_m"])

    def test_excluded_activities_are_skipped(self):
        self._activity(excluded=True)
        self._source(
            "a1", "intervals", {"average_cadence": 86}, external="i1"
        )

        self._run()

        self.assertIsNone(self._row())

    def test_scope_restricts_the_run(self):
        self._activity("a1")
        self._activity("a2")
        self._source(
            "a1", "intervals", {"average_cadence": 86}, external="i1"
        )
        self._source(
            "a2", "intervals", {"average_cadence": 90}, external="i2"
        )

        self._run(scope=Scope(entity_id="a1"))

        self.assertIsNotNone(self._row("a1"))
        self.assertIsNone(self._row("a2"))


if __name__ == "__main__":
    unittest.main()
