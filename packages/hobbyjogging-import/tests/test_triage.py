import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.triage import INTERVALS_URL, TriageRunner


class TriageTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)

        self.run_id = self.writer.start_import_run("test")
        self.source_record_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="run.fit:1",
            checksum="c1",
            raw_path="/tmp/run.fit",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2019-01-30",
                "sport": "run",
                "started_at_utc": "2019-01-30T18:00:00Z",
                "duration_s": 0,
                "elapsed_s": 0,
                "distance_m": 8200,
            },
            source="fit",
            source_record_id=self.source_record_id,
        )
        self.writer.link_activity_source(
            "a1", self.source_record_id, match_method="created"
        )
        self.item_id, _ = self.writer.record_review_item(
            category="quality",
            detail="no timing data: duration is 0 s",
            context={
                "rule": "zero_duration",
                "duration_s": 0,
                "elapsed_s": 0,
            },
            fingerprint="fp-zero-duration",
            activity_id="a1",
            source_record_id=self.source_record_id,
            import_run_id=self.run_id,
        )
        self.conn.commit()

        self.opened_urls = []
        self.copied_texts = []

    def _runner(self, answers, **kwargs):
        queue = list(answers)

        def read(prompt):
            if not queue:
                raise EOFError
            return queue.pop(0)

        lines = []

        def print(text=""):
            lines.append(text)

        runner = TriageRunner(
            self.writer,
            read=read,
            print=print,
            open_url=lambda url: self.opened_urls.append(url) or True,
            copy=lambda text: self.copied_texts.append(text) or "wl-copy",
            **kwargs,
        )
        out = self.writer.connection.commit
        counters = runner.run()
        out()
        return runner, lines, counters

    def _item(self):
        return self.writer.review_item(self.item_id)

    # -- resolve / ignore ---------------------------------------------------

    def test_resolve_marks_resolved(self):
        runner, lines, counters = self._runner(["r"])

        self.assertEqual(1, counters["resolved"])
        self.assertEqual("resolved", self._item()["status"])
        self.assertIn("triage: resolved", self._item()["resolved_note"])
        joined = "\n".join(lines)
        self.assertIn("Triage summary: 1 resolved", joined)
        self.assertIn("Review items left open: 0", joined)

    def test_ignore_marks_ignored(self):
        runner, lines, counters = self._runner(["x"])

        self.assertEqual(1, counters["ignored"])
        self.assertEqual("ignored", self._item()["status"])

    def test_pending_note_is_attached_to_next_close(self):
        self._runner(["n", "looks bogus", "r"])

        self.assertEqual(
            "looks bogus",
            self._item()["resolved_note"],
        )

    # -- skip / quit --------------------------------------------------------

    def test_skip_leaves_item_open(self):
        runner, lines, counters = self._runner(["s"])

        self.assertEqual(1, counters["skipped"])
        self.assertEqual("open", self._item()["status"])
        self.assertIn("Review items left open: 1", "\n".join(lines))

    def test_enter_key_skips(self):
        runner, lines, counters = self._runner([""])

        self.assertEqual(1, counters["skipped"])

    def test_quit_prints_summary_and_leaves_item_open(self):
        runner, lines, counters = self._runner(["q"])

        self.assertIn("Interrupted.", "\n".join(lines))
        self.assertEqual("open", self._item()["status"])

    def test_empty_queue(self):
        self.writer.set_review_status(self.item_id, "ignored")
        self.conn.commit()
        runner, lines, counters = self._runner([])

        self.assertIn("No open review items to triage.", lines)

    # -- inspect ------------------------------------------------------------

    def test_inspect_prints_values_sources_and_context(self):
        runner, lines, counters = self._runner(["i", "q"])

        joined = "\n".join(lines)
        self.assertIn("duration: 0:00", joined)
        self.assertIn("elapsed: 0:00", joined)
        self.assertIn("distance: 8.20 km", joined)
        self.assertIn("source fit: run.fit:1", joined)
        self.assertIn("/tmp/run.fit", joined)
        self.assertIn("zero_duration", joined)
        # inspect returns to the same item's prompt; 'q' then ends the walk

    def test_help_presents_keys(self):
        runner, lines, counters = self._runner(["h", "q"])

        joined = "\n".join(lines)
        self.assertIn("(c)opy URL", joined)
        self.assertIn("(d)elete", joined)

    def test_unknown_key_reprompts(self):
        runner, lines, counters = self._runner(["z", "q"])

        self.assertIn("unknown key", "\n".join(lines))

    # -- open / copy --------------------------------------------------------

    def _seed_intervals_link(self):
        intervals_record = self.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id="i104800507",
            checksum="c2",
            import_run_id=self.run_id,
        )
        self.writer.link_activity_source(
            "a1",
            intervals_record,
            match_method="external_id",
        )
        return intervals_record

    def test_open_opens_intervals_activity_url(self):
        self._seed_intervals_link()
        runner, lines, counters = self._runner(["o", "q"])

        self.assertEqual(
            self.opened_urls,
            [INTERVALS_URL.format("i104800507")],
        )
        self.assertIn("opened", "\n".join(lines))

    def test_copy_puts_url_on_clipboard(self):
        self._seed_intervals_link()
        runner, lines, counters = self._runner(["c", "q"])

        self.assertEqual(
            self.copied_texts[:1],
            [INTERVALS_URL.format("i104800507")],
        )
        self.assertIn("(via wl-copy)", "\n".join(lines))

    def test_fit_only_items_report_no_intervals_link(self):
        runner, lines, counters = self._runner(["o", "q"])

        self.assertEqual([], self.opened_urls)
        self.assertIn("no Intervals activity", "\n".join(lines))

    # -- edit ---------------------------------------------------------------

    def test_edit_accepts_default_field_and_value(self):
        runner, lines, counters = self._runner(["e", "", "46:20"])

        self.assertEqual(1, counters["edited"])
        row = self.conn.execute(
            "SELECT duration_s FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(2780, row["duration_s"])
        self.assertEqual(0, len(self.writer.review_items(status="open")))
        self.assertEqual("resolved", self._item()["status"])
        self.assertIn("quality: ok", "\n".join(lines))
        self.assertIn("manual edit: duration_s", self._item()["resolved_note"])

    def test_edit_field_choice_distance_for_zero_distance(self):
        self.writer.upsert_activity(
            "a1",
            {"distance_m": 0},
            source="fit",
            source_record_id=self.source_record_id,
        )
        # Replace the item with a zero_distance one.
        self.writer.set_review_status(self.item_id, "ignored")
        fresh_id, _ = self.writer.record_review_item(
            category="quality",
            detail="distance is 0 m where distance is expected",
            context={"rule": "zero_distance", "distance_m": 0, "sport": "run"},
            fingerprint="fp-zero-distance",
            activity_id="a1",
        )
        self.conn.commit()

        runner, lines, counters = self._runner(
            ["e", "", "8.2km"],
        )

        self.assertEqual(1, counters["edited"])
        row = self.conn.execute(
            "SELECT distance_m FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(8200, row["distance_m"])

        # duration is still 0 in this scenario: a zero_duration item is
        # recorded for the remaining problem, the edited one resolves.
        remaining = self.writer.review_items(status="open")
        self.assertEqual(1, len(remaining))
        self.assertIn("no timing data", remaining[0]["detail"])

    def test_edit_reports_remaining_findings(self):
        runner, lines, counters = self._runner(
            ["e", "sport", "mtb_ride"]
        )

        self.assertEqual(1, counters["edited"])
        joined = "\n".join(lines)
        self.assertIn("still flagged", joined)
        self.assertIn("zero_duration", joined)
        self.assertEqual(1, len(self.writer.review_items(status="open")))

    def test_edit_value_parse_errors_reprompt(self):
        runner, lines, counters = self._runner(
            ["e", "", "not a time", "46:20"]
        )

        self.assertEqual(1, counters["edited"])
        self.assertIn("try again", "\n".join(lines))
        self.assertEqual(2780, self.conn.execute(
            "SELECT duration_s FROM activities WHERE id = 'a1'"
        ).fetchone()["duration_s"])

    # -- field conflicts ------------------------------------------------------

    def _seed_conflict(self):
        self.writer.set_review_status(self.item_id, "ignored")
        self.conn.execute(
            "UPDATE activities SET duration_s = 3415.411 WHERE id = 'a1'"
        )
        item_id, _ = self.writer.record_review_item(
            category="field_conflict",
            detail=(
                "duration_s differs: intervals has 56:55, "
                "fit reports 17:35"
            ),
            context={
                "rule": "field_conflict",
                "field": "duration_s",
                "current": {"source": "intervals", "value": 3415.411},
                "incoming": {"source": "fit", "value": 1055.0},
            },
            fingerprint="fp-conflict-duration",
            activity_id="a1",
        )
        self.conn.commit()
        return item_id

    def test_pick_incoming_value_takes_manual_ownership(self):
        item_id = self._seed_conflict()

        runner, lines, counters = self._runner(["v", "2"])

        joined = "\n".join(lines)
        self.assertIn("(v) pick value", joined)
        self.assertIn("1) intervals: 56:55", joined)
        self.assertIn("2) fit: 17:35", joined)
        self.assertEqual(1, counters["picked_value"])

        row = self.conn.execute(
            "SELECT duration_s FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(1055.0, row["duration_s"])
        source = self.conn.execute(
            """
            SELECT source, is_manual FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = 'duration_s'
            """
        ).fetchone()
        self.assertEqual("manual", source["source"])
        self.assertEqual(1, source["is_manual"])

        item = self.writer.review_item(item_id)
        self.assertEqual("resolved", item["status"])
        self.assertEqual("triage: picked incoming value", item["resolved_note"])

    def test_pick_current_value_keeps_it_but_protects_the_decision(self):
        item_id = self._seed_conflict()

        runner, lines, counters = self._runner(["v", "1"])

        self.assertEqual(1, counters["picked_value"])
        row = self.conn.execute(
            "SELECT duration_s FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(3415.411, row["duration_s"])
        source = self.conn.execute(
            """
            SELECT is_manual FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = 'duration_s'
            """
        ).fetchone()
        self.assertEqual(1, source["is_manual"])
        self.assertEqual(
            "resolved",
            self.writer.review_item(item_id)["status"],
        )

    def test_pick_value_blank_cancels(self):
        item_id = self._seed_conflict()

        runner, lines, counters = self._runner(["v", "", "q"])

        self.assertNotIn("picked_value", counters)
        self.assertEqual("open", self.writer.review_item(item_id)["status"])
        self.assertIn("cancelled", "\n".join(lines))

    def test_pick_value_rejects_non_conflict_items(self):
        runner, lines, counters = self._runner(["v", "q"])

        self.assertIn("not a field conflict", "\n".join(lines))
        self.assertEqual("open", self._item()["status"])

    # -- delete -------------------------------------------------------------

    def test_delete_confirmed_excludes_activity(self):
        runner, lines, counters = self._runner(["d", "y"])

        self.assertEqual(1, counters["excluded"])
        row = self.conn.execute(
            "SELECT excluded_at FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertIsNotNone(row["excluded_at"])
        self.assertEqual("resolved", self._item()["status"])
        self.assertIn("excluded a1", "\n".join(lines))
        self.assertIn("review items resolved: 1", "\n".join(lines))

    def test_delete_cancelled_keeps_item_open(self):
        runner, lines, counters = self._runner(["d", "n", "s"])

        self.assertNotIn("excluded", counters)
        self.assertIsNone(
            self.conn.execute(
                "SELECT excluded_at FROM activities WHERE id = 'a1'"
            ).fetchone()["excluded_at"],
        )
        self.assertEqual("open", self._item()["status"])

    # -- ambiguous matches --------------------------------------------------

    def _seed_ambiguous_item(self):
        self.writer.upsert_activity(
            "a2",
            {
                "local_date": "2019-01-30",
                "sport": "run",
                "started_at_utc": "2019-01-30T18:05:00Z",
                "duration_s": 3600,
                "elapsed_s": 3700,
                "distance_m": 8000,
            },
            source="fit",
            source_record_id=None,
        )
        self.ambiguous_id, _ = self.writer.record_review_item(
            category="ambiguous_match",
            detail="ambiguous match: 2 candidate activities",
            context={
                "external_id": "run.fit:1",
                "candidates": [
                    {"activity_id": "a1", "match_method": "temporal_overlap",
                     "confidence": 0.9},
                    {"activity_id": "a2", "match_method": "temporal_overlap",
                     "confidence": 0.8},
                ],
            },
            fingerprint="fp-ambiguous",
            source_record_id=self.source_record_id,
        )
        self.conn.commit()
        return self.ambiguous_id

    def test_ambiguous_candidate_pick_links_and_resolves(self):
        item_id = self._seed_ambiguous_item()
        self.writer.set_review_status(self.item_id, "ignored")
        self.conn.commit()

        runner, lines, counters = self._runner(["i", "1"])

        joined = "\n".join(lines)
        self.assertIn("candidates: a1, a2", joined)
        self.assertIn("2) a2", joined)
        self.assertEqual(1, counters["linked"])
        self.assertEqual("resolved", self.writer.review_item(item_id)["status"])

        link = self.conn.execute(
            """
            SELECT match_method FROM activity_sources
            WHERE source_record_id = ?
            """,
            (self.source_record_id,),
        ).fetchall()
        self.assertEqual(1, len(link))
        self.assertEqual("review_resolved", link[0]["match_method"])

    def test_edit_on_ambiguous_item_hints_to_link_first(self):
        item_id = self._seed_ambiguous_item()
        self.writer.set_review_status(self.item_id, "ignored")
        self.conn.commit()

        runner, lines, counters = self._runner(["e", "q"])

        self.assertIn("link a candidate first", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
