import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "activity_weather_v1"


class ActivityWeatherBackfillTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _activity(self, activity_id="a1", *, excluded=False):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, ?)",
            (activity_id, "2024-06-01", "run"),
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _source(self, activity_id, source, payload, external="x1"):
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=f"{source}-{external}",
            checksum=f"c-{source}-{external}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
        )
        self.conn.execute(
            "INSERT INTO activity_sources "
            "(activity_id, source_record_id, match_method) VALUES (?, ?, 'test')",
            (activity_id, record_id),
        )
        self.conn.commit()

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _temp(self, activity_id="a1"):
        row = self.conn.execute(
            "SELECT temp_c, source FROM activity_weather WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
        return None if row is None else (row["temp_c"], row["source"])

    def test_fills_temperature_from_intervals(self):
        self._activity()
        self._source("a1", "intervals", {"average_temp": 19.5})

        result = self._run()

        self.assertEqual(1, result.counts["written"])
        self.assertEqual((19.5, "intervals"), self._temp())

    def test_fills_temperature_from_the_sheet(self):
        self._activity()
        self._source("a1", "sheet", {"values": {"Temperatur in °C": 8.0}})

        self._run()

        self.assertEqual((8.0, "sheet"), self._temp())

    def test_excluded_activities_are_skipped(self):
        self._activity(excluded=True)
        self._source("a1", "intervals", {"average_temp": 19.5})

        self._run()

        self.assertIsNone(self._temp())

    def test_a_forced_rerun_is_a_no_op(self):
        self._activity()
        self._source("a1", "intervals", {"average_temp": 19.5})

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts.get("written", 0))
        self.assertEqual(1, result.counts["unchanged"])

    def test_dry_run_writes_nothing(self):
        self._activity()
        self._source("a1", "intervals", {"average_temp": 19.5})

        self._run(dry_run=True)

        self.assertIsNone(self._temp())


class ActivityWeatherWriterTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2024-06-01', 'run')"
        )
        self.conn.commit()

    def test_the_first_source_owns_the_row(self):
        self.writer.upsert_activity_weather(
            "a1", source="intervals", temp_c=19.5
        )
        self.writer.upsert_activity_weather(
            "a1", source="runalyze", temp_c=21.0, humidity_pct=60.0
        )

        row = self.conn.execute(
            "SELECT source, temp_c, humidity_pct FROM activity_weather"
        ).fetchone()
        self.assertEqual(("intervals", 19.5, 60.0), tuple(row))

    def test_the_same_source_refreshes(self):
        self.writer.upsert_activity_weather(
            "a1", source="intervals", temp_c=19.5
        )
        self.writer.upsert_activity_weather(
            "a1", source="intervals", temp_c=22.0
        )

        row = self.conn.execute(
            "SELECT temp_c FROM activity_weather"
        ).fetchone()
        self.assertEqual(22.0, row["temp_c"])

    def test_an_empty_payload_writes_nothing(self):
        self.assertFalse(
            self.writer.upsert_activity_weather("a1", source="intervals")
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_weather"
            ).fetchone()[0],
        )


if __name__ == "__main__":
    unittest.main()
