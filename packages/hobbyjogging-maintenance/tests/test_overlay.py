import io
import json
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.overlay import (
    apply_overlay,
    format_counts,
    read_overlay,
    write_overlay,
)

SOURCE = "intervals"


class OverlayTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self._activity("a1")
        self._activity("a2")

    def _activity(self, activity_id):
        record_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "distance_m": 10000,
            },
            source=SOURCE,
            source_record_id=record_id,
        )
        self.writer.link_activity_source(activity_id, record_id)
        self.conn.commit()

    def _populate(self):
        self.writer.set_manual_field("a1", "avg_hr", 160)
        self.writer.set_manual_owner("a1", "training_load", SOURCE)
        self.writer.set_manual_activity_workout_methods(
            "a1", ["intervals"]
        )
        self.writer.set_manual_activity_workout_targets(
            "a1", ["subthreshold"]
        )
        self.writer.replace_activity_tags(
            "a1",
            ["Rucksack"],
            source="manual",
            is_manual=True,
        )
        self.writer.upsert_equipment(
            "shoe:1",
            type="shoe",
            name="Test shoe",
        )
        self.writer.link_activity_equipment(
            "a1",
            "shoe:1",
            source="manual",
            is_manual=True,
        )
        self.writer.exclude_activity("a2")
        item_id, _ = self.writer.record_review_item(
            category="field_conflict",
            detail="distance disagreement",
            fingerprint="fp-1",
            activity_id="a1",
        )
        self.writer.set_review_status(
            item_id,
            "ignored",
            note="known difference",
        )
        item_id, _ = self.writer.record_review_item(
            category="quality",
            detail="odd value",
            fingerprint="fp-2",
            activity_id="a1",
        )
        self.writer.set_review_status(
            item_id,
            "resolved",
            note="fixed",
        )
        self.conn.commit()

    def _fresh(self):
        target = connect(":memory:")
        self.addCleanup(target.close)
        migrate(target)
        target.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        target.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a2', '2026-10-01', 'run')"
        )
        TrainingWriter(target).upsert_equipment(
            "shoe:1",
            type="shoe",
            name="Test shoe",
        )
        target.commit()
        return target

    def test_export_writes_the_manual_layer_as_jsonl(self):
        self._populate()
        stream = io.StringIO()

        counts = write_overlay(self.conn, stream)

        self.assertEqual(1, counts.manual_fields)
        self.assertEqual(1, counts.owner_patches)
        self.assertEqual(2, counts.workout_sets)
        self.assertEqual(1, counts.tag_sets)
        self.assertEqual(1, counts.equipment_links)
        self.assertEqual(1, counts.exclusions)
        self.assertEqual(2, counts.review_answers)
        lines = [
            json.loads(line) for line in stream.getvalue().splitlines()
        ]
        self.assertEqual({"kind": "overlay", "version": 1}, lines[0])
        kinds = [line["kind"] for line in lines[1:]]
        self.assertEqual(
            [
                "manual_field",
                "manual_field",
                "workout",
                "workout",
                "tags",
                "equipment",
                "exclusion",
                "review",
                "review",
            ],
            kinds,
        )
        self.assertIn("manual fields", format_counts(counts))

    def test_import_reapplies_the_overlay_and_is_idempotent(self):
        self._populate()
        stream = io.StringIO()
        write_overlay(self.conn, stream)
        path = Path(tempfile.mkdtemp()) / "overlay.jsonl"
        path.write_text(stream.getvalue(), encoding="utf-8")

        target = self._fresh()
        records = read_overlay(path)
        counts = apply_overlay(target, records)
        target.commit()

        self.assertEqual(1, counts.manual_fields)
        self.assertEqual(1, counts.owner_patches)
        row = target.execute(
            "SELECT field_name, value_json, owner_source "
            "FROM activity_manual_fields ORDER BY field_name"
        ).fetchall()
        self.assertEqual(
            [
                ("avg_hr", "160", None),
                ("training_load", None, SOURCE),
            ],
            [tuple(item) for item in row],
        )
        self.assertEqual(
            ["intervals"],
            [
                item[0]
                for item in target.execute(
                    "SELECT method FROM activity_workout_methods "
                    "WHERE activity_id = 'a1'"
                )
            ],
        )
        self.assertEqual(
            ["subthreshold"],
            [
                item[0]
                for item in target.execute(
                    "SELECT target FROM activity_workout_targets "
                    "WHERE activity_id = 'a1'"
                )
            ],
        )
        self.assertEqual(
            ["Rucksack"],
            [
                item[0]
                for item in target.execute(
                    "SELECT tag FROM activity_tags "
                    "WHERE activity_id = 'a1' AND is_manual = 1"
                )
            ],
        )
        self.assertEqual(
            ["shoe:1"],
            [
                item[0]
                for item in target.execute(
                    "SELECT equipment_id FROM activity_equipment "
                    "WHERE activity_id = 'a1' AND is_manual = 1"
                )
            ],
        )
        excluded = target.execute(
            "SELECT excluded_at FROM activities WHERE id = 'a2'"
        ).fetchone()
        self.assertIsNotNone(excluded["excluded_at"])
        reviews = target.execute(
            "SELECT fingerprint, status, resolved_note "
            "FROM review_items ORDER BY fingerprint"
        ).fetchall()
        self.assertEqual(
            [
                ("fp-1", "ignored", "known difference"),
                ("fp-2", "resolved", "fixed"),
            ],
            [tuple(item) for item in reviews],
        )

        second = apply_overlay(target, records)
        target.commit()
        self.assertEqual(0, second.skipped_excluded)
        self.assertEqual(
            2,
            target.execute(
                "SELECT COUNT(*) FROM review_items"
            ).fetchone()[0],
        )

    def test_unknown_kind_and_version_fail_loudly(self):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / "bad.jsonl"
        path.write_text(
            '{"kind": "overlay", "version": 1}\n'
            '{"kind": "telepathy", "activity": "a1"}\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as raised:
            read_overlay(path)
        self.assertIn("unknown kind", str(raised.exception))

        path.write_text(
            '{"kind": "overlay", "version": 99}\n',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as raised:
            read_overlay(path)
        self.assertIn("unsupported overlay version", str(raised.exception))

    def test_an_empty_overlay_is_an_error(self):
        path = Path(tempfile.mkdtemp()) / "empty.jsonl"
        path.write_text("", encoding="utf-8")

        with self.assertRaises(ValueError):
            read_overlay(path)


if __name__ == "__main__":
    unittest.main()
