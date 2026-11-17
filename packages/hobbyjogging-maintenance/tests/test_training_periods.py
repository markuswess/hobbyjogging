import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "training_periods_current"


class TrainingPeriodsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _event(self, event_id, day, category, name, *, end=None):
        payload = {
            "id": event_id,
            "start_date_local": f"{day}T00:00:00",
            "category": category,
            "name": name,
        }
        if end is not None:
            payload["end_date_local"] = f"{end}T00:00:00"
        self.writer.upsert_source_record(
            source="intervals",
            record_type="event",
            external_id=str(event_id),
            checksum=f"c-{event_id}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
        )
        self.conn.commit()

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _periods(self):
        return [
            tuple(row)
            for row in self.conn.execute(
                "SELECT kind, label, start_date, end_date, source "
                "FROM training_periods ORDER BY start_date, id"
            )
        ]

    def test_seasons_end_before_the_next_one(self):
        self._event(1, "2022-12-18", "SEASON_START", "VCM 23")
        self._event(2, "2023-12-17", "SEASON_START", "VCM 24")

        self._run()

        self.assertEqual(
            [
                ("season", "VCM 23", "2022-12-18", "2023-12-16", "intervals"),
                ("season", "VCM 24", "2023-12-17", None, "intervals"),
            ],
            self._periods(),
        )

    def test_a_sick_range_keeps_the_source_end(self):
        self._event(
            1, "2026-02-08", "SICK", "Schilddrüse", end="2026-03-09"
        )

        self._run()

        self.assertEqual(
            [
                (
                    "illness",
                    "Schilddrüse",
                    "2026-02-08",
                    "2026-03-09",
                    "intervals",
                )
            ],
            self._periods(),
        )

    def test_a_sick_event_without_an_end_is_one_day(self):
        self._event(1, "2026-05-06", "SICK", "Krank")

        self._run()

        self.assertEqual(
            [("illness", "Krank", "2026-05-06", "2026-05-06", "intervals")],
            self._periods(),
        )

    def test_an_end_before_the_start_falls_back_to_the_start(self):
        self._event(1, "2026-05-06", "SICK", "Krank", end="2026-05-01")

        self._run()

        self.assertEqual(
            [("illness", "Krank", "2026-05-06", "2026-05-06", "intervals")],
            self._periods(),
        )

    def test_a_note_keeps_its_range(self):
        self._event(
            1, "2026-06-22", "NOTE", "Dienstreise", end="2026-06-24"
        )

        self._run()

        self.assertEqual(
            [("other", "Dienstreise", "2026-06-22", "2026-06-24", "intervals")],
            self._periods(),
        )

    def test_other_categories_are_ignored(self):
        self._event(1, "2026-01-01", "TARGET", "Weekly")
        self._event(2, "2026-01-02", "WORKOUT", "Easy")

        self._run()

        self.assertEqual([], self._periods())

    def test_a_manual_period_survives(self):
        self._event(1, "2026-05-06", "SICK", "Krank")
        self.writer.upsert_training_period(
            "manual:illness:2026-05-01",
            kind="illness",
            start_date="2026-05-01",
            end_date="2026-05-08",
            label="Flu",
        )

        self._run()

        sources = [row[4] for row in self._periods()]
        self.assertIn("manual", sources)
        self.assertIn("intervals", sources)

    def test_a_rerun_is_a_no_op(self):
        self._event(1, "2026-05-06", "SICK", "Krank", end="2026-05-10")

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts.get("periods", 0))
        self.assertEqual(1, len(self._periods()))


if __name__ == "__main__":
    unittest.main()
