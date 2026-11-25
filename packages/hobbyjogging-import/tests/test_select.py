import unittest
from datetime import date

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_import.select import (
    SelectionError,
    prompt_candidate,
    resolve_activity,
    resolve_equipment,
    resolve_period,
)


class SelectionTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self._activity("a1", "2026-10-01", "06:00", "Morning run")
        self._activity("a2", "2026-10-01", "18:00", "Evening run")
        self._activity("a3", "2026-10-02", "08:00", "Long ride", sport="ride")
        self.writer.upsert_equipment(
            "e1", type="shoe", name="Pegasus 40"
        )
        self.writer.upsert_equipment(
            "e2", type="shoe", name="Pegasus 41"
        )
        self.writer.upsert_training_period(
            "p1", kind="illness", start_date="2026-03-01",
            end_date="2026-03-05", label="Flu"
        )
        self.writer.upsert_training_period(
            "p2", kind="travel", start_date="2026-04-01",
            end_date="2026-04-03", label="Trip"
        )
        self.conn.commit()

    def _activity(self, activity_id, day, clock, name, sport="run"):
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": day,
                "sport": sport,
                "name": name,
                "started_at_utc": f"{day}T{clock}:00Z",
            },
            source="fit",
            source_record_id=None,
        )

    def test_activity_id_is_exact(self):
        self.assertEqual("a1", resolve_activity(self.conn, "a1"))

    def test_last_is_the_newest_activity(self):
        self.assertEqual("a3", resolve_activity(self.conn, "last"))

    def test_iso_date_with_one_activity(self):
        self.assertEqual("a3", resolve_activity(self.conn, "2026-10-02"))

    def test_two_sessions_on_a_date_are_ambiguous(self):
        with self.assertRaises(SelectionError) as caught:
            resolve_activity(self.conn, "2026-10-01")

        self.assertEqual(["a1", "a2"], [c.id for c in caught.exception.candidates])

    def test_name_substring_is_case_insensitive(self):
        self.assertEqual("a1", resolve_activity(self.conn, "MORNING"))

    def test_ambiguous_name_lists_candidates(self):
        with self.assertRaises(SelectionError) as caught:
            resolve_activity(self.conn, "run")

        self.assertEqual(["a1", "a2"], [c.id for c in caught.exception.candidates])

    def test_unknown_selector_errors(self):
        with self.assertRaises(SelectionError):
            resolve_activity(self.conn, "2026-12-31")
        with self.assertRaises(SelectionError):
            resolve_activity(self.conn, "nothing")

    def test_choose_can_pick_an_ambiguous_candidate(self):
        self.assertEqual(
            "a2",
            resolve_activity(
                self.conn,
                "2026-10-01",
                choose=lambda candidates: candidates[1].id,
            ),
        )

    def test_equipment_id_and_name(self):
        self.assertEqual("e1", resolve_equipment(self.conn, "e1"))
        self.assertEqual("e1", resolve_equipment(self.conn, "Pegasus 40"))
        with self.assertRaises(SelectionError) as caught:
            resolve_equipment(self.conn, "pegasus")
        self.assertEqual(2, len(caught.exception.candidates))

    def test_period_id_date_and_label(self):
        self.assertEqual("p1", resolve_period(self.conn, "p1"))
        self.assertEqual("p1", resolve_period(self.conn, "2026-03-03"))
        self.assertEqual("p1", resolve_period(self.conn, "flu"))
        with self.assertRaises(SelectionError):
            resolve_period(self.conn, "2026-12-31")

    def test_prompt_candidate_reads_a_number(self):
        with self.assertRaises(SelectionError) as caught:
            resolve_activity(self.conn, "2026-10-01")
        candidates = caught.exception.candidates
        self.assertEqual(
            "a2",
            prompt_candidate(candidates, read=lambda prompt: "2"),
        )
        self.assertIsNone(
            prompt_candidate(candidates, read=lambda prompt: "")
        )


if __name__ == "__main__":
    unittest.main()
