import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.audit import build_audit


class AuditTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self._build()

    def _record(self, source, external_id, payload, record_type="activity"):
        return self.writer.upsert_source_record(
            source=source,
            record_type=record_type,
            external_id=external_id,
            checksum=f"c-{source}-{external_id}",
            payload_json=json.dumps(payload),
            import_run_id=self.run_id,
        )

    def _activity(
        self,
        activity_id,
        day,
        sport="run",
        *,
        distance=10000,
        elevation=None,
        description="",
        source="intervals",
        record_id=None,
    ):
        values = {
            "local_date": day,
            "sport": sport,
            "distance_m": distance,
            "duration_s": 3600,
            "avg_hr": 145,
            "max_hr": 170,
            "training_load": 80,
            "description": description,
        }
        if elevation is not None:
            values["elevation_gain_m"] = elevation
        self.writer.upsert_activity(
            activity_id,
            values,
            source=source,
            source_record_id=record_id or self._record(
                source, activity_id, {"distance": distance}
            ),
        )
        self.conn.commit()

    def _build(self):
        intervals = self._record(
            "intervals",
            "i1",
            {
                "distance": 10000,
                "average_cadence": 82,
                "icu_intervals": [],
            },
        )
        self._activity(
            "a1",
            "2024-05-01",
            distance=10000,
            elevation=500,
            description="5x1000 interval",
            record_id=intervals,
        )
        self._activity(
            "a2",
            "2024-06-01",
            sport="trail_run",
            distance=8000,
            elevation=400,
        )
        self._activity(
            "a3",
            "2025-03-01",
            sport="ride",
            distance=40000,
        )
        self._activity(
            "a4",
            "2025-02-01",
            description="3-6-9-6-3min Intervalle",
        )
        self._activity(
            "a5",
            "2024-11-20",
            description="outside illness",
        )
        self._record(
            "runalyze",
            "r1",
            {
                "type": {"name": "Jogging", "abbreviation": "JOG"},
                "tags": ["Custom"],
                "device_name": "Runalyze",
                "kcal": 700,
            },
        )
        self._record(
            "fit",
            "f1",
            {"file": {"product": "enduro"}, "session": {"distance_m": 10000}},
        )
        self._record(
            "strava",
            "s1",
            {"commute": False},
            record_type="social",
        )
        self._record(
            "sheet",
            "sh1",
            {
                "row": 1,
                "sheet": "Rohdaten",
                "values": {
                    "Datum": "2024-05-01",
                    "Distanz in m": "10000",
                    "Gmap Pedometer Link": "https://example.invalid",
                    "Schrittfrequenz": "82",
                },
            },
        )

        for activity_id, tag in (
            ("a1", "sub threshold"),
            ("a1", "Custom"),
            ("a2", "Trail"),
            ("a5", "krank"),
        ):
            self.conn.execute(
                "INSERT INTO activity_tags (activity_id, tag, source) "
                "VALUES (?, ?, 'runalyze')",
                (activity_id, tag),
            )
        self.writer.replace_activity_workout_methods(
            "a1", ["intervals"], source="intervals"
        )
        self.conn.execute(
            "INSERT INTO training_periods "
            "(id, kind, label, start_date, end_date) "
            "VALUES ('p1', 'illness', 'krank', '2024-11-01', '2024-11-10')"
        )
        self.conn.execute(
            "INSERT INTO race_results "
            "(activity_id, name, official_distance_m, official_time_s, source) "
            "VALUES ('a1', 'Test race', 10000, 2400, 'runalyze')"
        )
        self.writer.record_review_item(
            category="ambiguous_match",
            detail="test",
            fingerprint="fp1",
            activity_id="a1",
        )
        self.conn.commit()

    def _section(self, text, start, end):
        match = text.split(start, 1)[1]
        return match.split(end, 1)[0]

    def test_audit_has_the_major_sections(self):
        text = build_audit(self.conn, database="test.db")

        for section in (
            "# Historical data audit",
            "## Field coverage",
            "## Raw payload keys without a canonical home",
            "## Tags",
            "## Interval-like descriptions",
            "## Elevation and trail evidence",
            "## Race evidence",
            "## Classification coverage",
            "## Periods and illness evidence",
            "## Review queue",
            "## Summary",
            "Database: `test.db`",
        ):
            self.assertIn(section, text)

    def test_raw_keys_show_unmapped_fields_and_skip_child_columns(self):
        text = build_audit(self.conn)
        raw = self._section(
            text,
            "## Raw payload keys without a canonical home",
            "## Tags",
        )

        self.assertIn("average_cadence", raw)
        self.assertIn("device_name", raw)
        self.assertIn("commute", raw)
        self.assertIn("Schrittfrequenz", raw)
        self.assertNotIn("Datum", raw)
        self.assertNotIn("Gmap Pedometer Link", raw)

    def test_tags_distinguish_known_and_unmapped(self):
        text = build_audit(self.conn)
        tags = self._section(text, "## Tags", "## Interval-like descriptions")

        self.assertIn("Unmapped tags", tags)
        self.assertIn("`Custom`", tags)
        self.assertIn("Known tags", tags)
        self.assertIn("sub threshold", tags)
        self.assertIn("subT / LT1", tags)

    def test_interval_and_trail_evidence(self):
        text = build_audit(self.conn)

        self.assertIn("| reps NxM | 1 |", text)
        self.assertIn("| ladder | 1 |", text)
        self.assertIn("1 run candidates with trail evidence", text)
        self.assertIn("2024-05-01", text)
        self.assertIn("| official race results | 1 |", text)

    def test_illness_and_review_counts(self):
        text = build_audit(self.conn)

        self.assertIn("`krank`: 1 days", text)
        self.assertIn("1 tagged days fall outside an illness period", text)
        self.assertIn("| `ambiguous_match` | 1 |", text)

    def test_summary_names_the_gaps(self):
        text = build_audit(self.conn)
        summary = text.split("## Summary", 1)[1]

        self.assertIn("5 activities", summary)
        self.assertIn("unmapped", summary)
        self.assertIn("NxM", summary)


if __name__ == "__main__":
    unittest.main()
