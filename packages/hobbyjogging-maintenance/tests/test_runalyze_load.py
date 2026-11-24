import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.sources_config import SourcesConfig, default_policies

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "runalyze_load_current"


class RunalyzeLoadTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _activity(self, *, load=None, fit_trimp=None, trimp=None):
        self.counter += 1
        activity_id = f"a{self.counter}"
        fit_record = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
        )
        values = {
            "local_date": "2026-10-01",
            "sport": "run",
            "duration_s": 3600,
        }
        if load is not None:
            values["training_load"] = load
        self.writer.upsert_activity(
            activity_id,
            values,
            source="fit",
            source_record_id=fit_record,
        )

        payload = {"duration": 3600}
        if fit_trimp is not None:
            payload["fit_trimp"] = fit_trimp
        if trimp is not None:
            payload["trimp"] = trimp
        runalyze_record = self.writer.upsert_source_record(
            source="runalyze",
            record_type="activity",
            external_id=f"r-{activity_id}",
            checksum=f"r-{activity_id}",
            payload_json=json.dumps(payload),
            import_run_id=self.run_id,
        )
        self.writer.link_activity_source(
            activity_id,
            runalyze_record,
            match_method="exact_twin",
        )
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _load(self, activity_id):
        row = self.conn.execute(
            "SELECT training_load FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        return row["training_load"]

    def _owner(self, activity_id):
        row = self.conn.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = ? AND field_name = 'training_load'
            """,
            (activity_id,),
        ).fetchone()
        return row["source"] if row else None

    def test_fills_an_empty_load_with_fit_trimp_first(self):
        activity_id = self._activity(fit_trimp=120, trimp=99)

        run = self._run()

        self.assertEqual(1, run.counts["written"])
        self.assertEqual(120.0, self._load(activity_id))
        self.assertEqual("runalyze", self._owner(activity_id))

    def test_trimp_is_the_fallback(self):
        activity_id = self._activity(fit_trimp=0, trimp=80)

        self._run()

        self.assertEqual(80.0, self._load(activity_id))

    def test_an_intervals_load_wins(self):
        activity_id = self._activity(load=150, fit_trimp=120)
        self.writer.upsert_activity(
            activity_id,
            {"training_load": 150},
            source="intervals",
            source_record_id=self.writer.upsert_source_record(
                source="intervals",
                record_type="activity",
                external_id="i1",
                checksum="i1",
                import_run_id=self.run_id,
            ),
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["kept_measured"])
        self.assertEqual(150.0, self._load(activity_id))
        self.assertEqual("intervals", self._owner(activity_id))

    def test_a_manual_load_wins(self):
        activity_id = self._activity(fit_trimp=120)
        self.writer.set_manual_field(activity_id, "training_load", 200)
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["kept_measured"])
        self.assertEqual(200.0, self._load(activity_id))

    def test_an_existing_runalyze_value_is_refreshed(self):
        activity_id = self._activity(fit_trimp=120)
        self._run()

        row = self.conn.execute(
            "SELECT id FROM source_records WHERE source = 'runalyze'"
        ).fetchone()
        self.conn.execute(
            "UPDATE source_records SET payload_json = ? WHERE id = ?",
            (json.dumps({"fit_trimp": 130}), row["id"]),
        )
        self.conn.commit()

        run = self._run(force=True)

        self.assertEqual(1, run.counts["written"])
        self.assertEqual(130.0, self._load(activity_id))

    def test_a_second_run_is_a_no_op(self):
        self._activity(fit_trimp=120)
        self._run()

        second = self._run(force=True)

        self.assertEqual(1, second.counts["unchanged"])
        self.assertEqual(0, second.counts["written"])

    def test_a_payload_without_a_value_is_counted(self):
        self._activity()

        run = self._run()

        self.assertEqual(1, run.counts["no_value"])
        self.assertEqual(0, run.counts["written"])

    def test_a_dry_run_writes_nothing(self):
        activity_id = self._activity(fit_trimp=120)

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["written"])
        self.assertIsNone(self._load(activity_id))

    def test_a_disabled_trimp_capability_skips_the_fill(self):
        activity_id = self._activity(fit_trimp=120)
        policies = dict(default_policies())
        policy = policies["runalyze"]
        policies["runalyze"] = replace(
            policy,
            capabilities=policy.capabilities - {"trimp"},
        )
        config = SourcesConfig(policies=policies)

        with patch(
            "hobbyjogging_maintenance.recompute.runalyze_load_current."
            "load_sources",
            return_value=config,
        ):
            run = self._run()

        self.assertIsNone(self._load(activity_id))
        self.assertTrue(
            any("disabled" in note for note in run.notes),
            run.notes,
        )


if __name__ == "__main__":
    unittest.main()
