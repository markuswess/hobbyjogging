import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate


class ActivityMetricsWriterTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run"},
            source="fit",
            source_record_id=None,
        )
        self.conn.commit()

    def _row(self):
        return self.conn.execute(
            "SELECT * FROM activity_metrics WHERE activity_id = 'a1'"
        ).fetchone()

    def test_first_source_owns_the_row_and_fit_replaces_its_fields(self):
        self.writer.upsert_activity_metrics(
            "a1",
            source="intervals",
            cadence=172.5,
            stride_m=1.31,
            altitude_avg_m=191.0,
        )
        self.writer.upsert_activity_metrics(
            "a1",
            source="fit",
            cadence=172.0,
            stride_m=1.29,
            calories_kcal=692.0,
        )
        self.conn.commit()

        row = self._row()
        self.assertEqual("intervals", row["source"])
        self.assertEqual(172.0, row["cadence"])
        self.assertEqual(1.29, row["stride_m"])
        self.assertEqual(191.0, row["altitude_avg_m"])
        self.assertEqual(692.0, row["calories_kcal"])

    def test_same_source_refresh_does_not_undo_a_higher_authority(self):
        self.writer.upsert_activity_metrics(
            "a1",
            source="intervals",
            cadence=172.5,
            altitude_avg_m=191.0,
        )
        self.writer.upsert_activity_metrics(
            "a1",
            source="fit",
            cadence=172.0,
        )
        self.writer.upsert_activity_metrics(
            "a1",
            source="intervals",
            cadence=171.0,
            altitude_avg_m=190.0,
        )
        self.conn.commit()

        row = self._row()
        self.assertEqual(172.0, row["cadence"])
        self.assertEqual(190.0, row["altitude_avg_m"])

    def test_lower_authority_fills_only_gaps(self):
        self.writer.upsert_activity_metrics(
            "a1",
            source="fit",
            cadence=172.0,
        )
        self.writer.upsert_activity_metrics(
            "a1",
            source="runalyze",
            cadence=170.0,
            power_w=326.0,
            gap_mps=3.78,
        )
        self.conn.commit()

        row = self._row()
        self.assertEqual(172.0, row["cadence"])
        self.assertEqual(326.0, row["power_w"])
        self.assertEqual(3.78, row["gap_mps"])

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.writer.upsert_activity_metrics(
                "a1", source="fit", not_a_metric=1
            )

    def test_empty_values_are_a_noop(self):
        self.assertFalse(
            self.writer.upsert_activity_metrics(
                "a1", source="fit", cadence=None
            )
        )
        self.assertIsNone(self._row())


if __name__ == "__main__":
    unittest.main()
