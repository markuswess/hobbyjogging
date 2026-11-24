import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_import.runalyze_types import (
    audit_types,
    classification_for_payload,
    classification_for_runalyze_type,
    format_type_audit,
    type_tokens,
)


class RunalyzeTypeTests(unittest.TestCase):

    def test_the_three_decided_types(self):
        self.assertEqual(
            ({"continuous"}, {"base"}),
            classification_for_runalyze_type("Jogging"),
        )
        self.assertEqual(
            ({"long_run"}, {"base"}),
            classification_for_runalyze_type("Long Slow Distance"),
        )
        self.assertEqual(
            ({"intervals"}, {"subthreshold"}),
            classification_for_runalyze_type("SubThreshold"),
        )

    def test_abbreviations_and_spellings_match(self):
        self.assertEqual(
            ({"continuous"}, {"base"}),
            classification_for_runalyze_type("", "JOG"),
        )
        self.assertEqual(
            ({"intervals"}, {"subthreshold"}),
            classification_for_runalyze_type("Sub-Threshold"),
        )
        self.assertEqual(
            ({"intervals"}, {"subthreshold"}),
            classification_for_runalyze_type("sub threshold"),
        )
        self.assertEqual(
            ({"long_run"}, {"base"}),
            classification_for_runalyze_type("", "LSD"),
        )

    def test_an_unknown_type_is_never_guessed(self):
        self.assertEqual(
            (set(), set()),
            classification_for_runalyze_type("Trail Run", "TLR"),
        )
        self.assertEqual(
            (set(), set()),
            classification_for_runalyze_type(""),
        )

    def test_payload_tokens_ignore_a_missing_type(self):
        self.assertEqual(("", ""), type_tokens({}))
        self.assertEqual(("", ""), type_tokens({"type": "Jogging"}))
        self.assertEqual(
            ("jogging", "jog"),
            type_tokens({"type": {"name": "Jogging", "abbreviation": "JOG"}}),
        )
        self.assertEqual(
            ({"continuous"}, {"base"}),
            classification_for_payload(
                {"type": {"name": "Jogging", "abbreviation": "JOG"}}
            ),
        )


class TypeAuditTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _record(self, name, abbreviation, payload=None):
        self.counter += 1
        value = payload
        if value is None:
            value = {"type": {"name": name, "abbreviation": abbreviation}}
        self.writer.upsert_source_record(
            source="runalyze",
            record_type="activity",
            external_id=f"r{self.counter}",
            checksum=f"c{self.counter}",
            payload_json=json.dumps(value),
            import_run_id=self.run_id,
        )
        self.conn.commit()

    def test_counts_and_maps_the_stored_types(self):
        self._record("Jogging", "JOG")
        self._record("Jogging", "JOG")
        self._record("SubThreshold", "ST")
        self._record("Trail Run", "TLR")

        rows = audit_types(self.conn)

        by_name = {row.name.lower(): row for row in rows}
        self.assertEqual(2, by_name["jogging"].count)
        self.assertTrue(by_name["jogging"].mapped)
        self.assertTrue(by_name["subthreshold"].mapped)
        self.assertFalse(by_name["trail run"].mapped)

    def test_invalid_and_typeless_payloads_are_skipped(self):
        self._record("", "", payload={"note": "no type"})
        self._record("", "", payload=None)

        self.assertEqual([], audit_types(self.conn))

    def test_the_audit_names_unmapped_types(self):
        self._record("Jogging", "JOG")
        self._record("Trail Run", "TLR")

        text = format_type_audit(audit_types(self.conn))

        self.assertIn("Runalyze types", text)
        self.assertIn("JOG", text)
        self.assertIn("continuous / base", text)
        self.assertIn("unmapped", text)
        self.assertIn("Unmapped: 1 type(s)", text)

    def test_an_empty_audit_says_so(self):
        self.assertIn(
            "no stored activity payloads",
            format_type_audit([]),
        )


if __name__ == "__main__":
    unittest.main()
