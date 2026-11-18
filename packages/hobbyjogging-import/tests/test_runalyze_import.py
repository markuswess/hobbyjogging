import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.runalyze import (
    RunalyzeRateLimitError,
    RunalyzeResponse,
)
from hobbyjogging_import.runalyze_import import (
    RunalyzeEnricher,
    apply_stored_enrichment,
    format_enrich_summary,
)

FIXTURES = Path(__file__).parent / "fixtures" / "runalyze"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text("utf-8"))


class FakeRunalyze:
    def __init__(self, activities, details, rate_limited=()):
        self.activities_payload = activities
        self.details = details
        self.rate_limited = set(rate_limited)
        self.detail_calls = []
        self.activity_calls = 0

    def activities(self, start, end, *, per_page=100):
        self.activity_calls += 1
        return list(self.activities_payload)

    def get(self, path, params=None):
        assert path.startswith("activity/"), path
        external_id = path.split("/", 1)[1]
        self.detail_calls.append(external_id)
        if external_id in self.rate_limited:
            self.rate_limited.discard(external_id)
            raise RunalyzeRateLimitError(
                retry_after_s=1,
                limit=240,
            )
        payload = self.details.get(external_id)
        if payload is None:
            return RunalyzeResponse(404, {}, {"detail": "missing"})
        return RunalyzeResponse(200, {}, payload)


class RunalyzeEnrichTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)

        self._activity(
            "a1",
            "2024-03-01",
            "2024-03-01T07:00:00Z",
            3600,
            3700,
            10000,
            name="Canonical A",
        )
        self._activity(
            "a2",
            "2024-03-02",
            "2024-03-02T07:00:00Z",
            1800,
            1800,
            5000,
            name="Canonical B",
            description="Intervals note",
        )

        self.details = {
            "201": _fixture("enrich_detail_201.json"),
            "202": _fixture("enrich_detail_202.json"),
        }
        # A row that goes to review still needs its detail: the review item
        # stores it so a resolution can apply its note and tags.
        for row in _fixture("enrich_collection.json"):
            self.details.setdefault(str(row["id"]), dict(row))
        self.client = FakeRunalyze(
            _fixture("enrich_collection.json"),
            self.details,
        )
        self.enricher = RunalyzeEnricher(self.conn, client=self.client)

    def _activity(
        self,
        activity_id,
        local_date,
        started_at,
        duration_s,
        elapsed_s,
        distance_m,
        *,
        name="Run",
        description="",
    ):
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": local_date,
                "started_at_utc": started_at,
                "sport": "run",
                "name": name,
                "description": description,
                "duration_s": duration_s,
                "elapsed_s": elapsed_s,
                "distance_m": distance_m,
            },
            source="fit",
            source_record_id=None,
        )

    def _row(self, activity_id):
        return self.conn.execute(
            "SELECT * FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

    def _tags(self, activity_id):
        return {
            (row["tag"], row["source"], row["is_manual"])
            for row in self.conn.execute(
                "SELECT tag, source, is_manual FROM activity_tags "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        }

    def _sources(self, activity_id):
        return [
            (row["source"], row["external_id"])
            for row in self.conn.execute(
                """
                SELECT r.source, r.external_id
                FROM activity_sources s
                JOIN source_records r ON r.id = s.source_record_id
                WHERE s.activity_id = ?
                ORDER BY r.source, r.external_id
                """,
                (activity_id,),
            )
        ]

    def test_fills_blank_description_and_imports_tags(self):
        summary = self.enricher.enrich()

        self.assertEqual(4, summary.activities_seen)
        self.assertEqual(4, summary.processed)
        self.assertEqual(0, summary.not_processed)
        self.assertEqual(2, summary.matched)
        self.assertEqual(0, summary.already_enriched)
        self.assertEqual(2, summary.unmatched)
        self.assertEqual(0, summary.ambiguous)
        self.assertEqual(2, summary.reviews_recorded)
        self.assertEqual(4, summary.detail_fetches)
        self.assertEqual(1, summary.comments_filled)
        self.assertEqual(1, summary.comments_kept)
        self.assertEqual(2, summary.activities_tagged)
        self.assertEqual(3, summary.tags_written)
        self.assertEqual(
            ["201", "202", "203", "204"],
            self.client.detail_calls,
        )

        self.assertEqual("Runalyze comment", self._row("a1")["description"])
        self.assertEqual(
            "Intervals note",
            self._row("a2")["description"],
        )
        self.assertEqual(
            {("Race", "runalyze", 0), ("Hilly", "runalyze", 0)},
            self._tags("a1"),
        )
        self.assertEqual(
            {("Easy", "runalyze", 0)},
            self._tags("a2"),
        )

        # Runalyze never writes name, timing, or distance.
        row = self._row("a1")
        self.assertEqual("Canonical A", row["name"])
        self.assertEqual(3600, row["duration_s"])
        self.assertEqual(3700, row["elapsed_s"])
        self.assertEqual(10000, row["distance_m"])
        self.assertIsNone(row["rpe"])

        self.assertEqual([("runalyze", "201")], self._sources("a1"))

    def test_manual_tags_survive(self):
        self.writer.replace_activity_tags(
            "a1",
            ["Manual"],
            source="manual",
            is_manual=True,
        )

        self.enricher.enrich()

        self.assertEqual(
            {
                ("Manual", "manual", 1),
                ("Hilly", "runalyze", 0),
                ("Race", "runalyze", 0),
            },
            self._tags("a1"),
        )

    def test_reimport_replaces_only_runalyze_tags(self):
        self.enricher.enrich()
        self.details["201"]["tags"] = [
            {"id": 2, "tag": "Hilly"},
            {"id": 4, "tag": "New"},
        ]

        summary = self.enricher.enrich(refresh=True)

        self.assertEqual(0, summary.comments_filled)
        self.assertEqual(2, summary.comments_kept)
        self.assertEqual(1, summary.activities_tagged)
        self.assertEqual(0, summary.already_enriched)
        self.assertEqual(4, summary.detail_fetches)
        self.assertEqual(
            {("Hilly", "runalyze", 0), ("New", "runalyze", 0)},
            self._tags("a1"),
        )

    def test_stored_details_are_not_refetched_without_refresh(self):
        self.enricher.enrich()
        self.details["201"]["note"] = "changed on Runalyze"

        summary = self.enricher.enrich()

        self.assertEqual(2, summary.already_enriched)
        self.assertEqual(0, summary.detail_fetches)
        self.assertEqual("Runalyze comment", self._row("a1")["description"])

    def test_dry_run_writes_nothing(self):
        summary = self.enricher.enrich(dry_run=True)

        self.assertEqual(4, summary.processed)
        self.assertEqual(0, summary.not_processed)
        self.assertEqual(1, summary.comments_filled)
        self.assertEqual(2, summary.activities_tagged)
        self.assertIsNone(summary.run_id)
        self.assertEqual("", self._row("a1")["description"])
        self.assertEqual(set(), self._tags("a1"))
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records "
                "WHERE source = 'runalyze'"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM import_runs"
            ).fetchone()[0],
        )

    def test_writes_the_unmatched_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "unmatched.json"
            self.enricher.enrich(output=output)
            payload = json.loads(output.read_text("utf-8"))

        reasons = {
            str(row["id"]): row["reason"]
            for row in payload["unmatched"]
        }
        self.assertEqual(
            {
                "203": "no_temporal_match",
                "204": "distance_mismatch",
            },
            reasons,
        )

    # -- the exact-twin rule ------------------------------------------------

    def _linked_activity(
        self,
        activity_id,
        local_date,
        duration_s,
        distance_m,
        *,
        source,
        name="",
    ):
        """An activity with a real source link, so its provenance is known."""
        record = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=f"{source}:{activity_id}",
            checksum=activity_id,
            payload_json="{}",
            import_run_id=None,
        )
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": local_date,
                "started_at_utc": f"{local_date}T07:00:00Z",
                "sport": "run",
                "name": name,
                "duration_s": duration_s,
                "elapsed_s": duration_s,
                "distance_m": distance_m,
            },
            source=source,
            source_record_id=record,
        )
        self.writer.link_activity_source(
            activity_id,
            record,
            match_method=source,
        )

    def _runalyze_row(
        self,
        external_id,
        local_date,
        duration_s,
        distance_km,
        *,
        hour="23",
    ):
        return {
            "id": external_id,
            "date_time": f"{local_date}T{hour}:00:00+02:00",
            "duration": duration_s,
            "elapsed_time": duration_s,
            "distance": distance_km,
        }

    def _review_items(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM review_items WHERE category = 'ambiguous_match'"
            )
        ]

    def test_exact_twin_links_even_when_the_start_times_differ(self):
        self._linked_activity(
            "d1", "2024-05-01", 3600, 10000, source="fit", name="Morning Run"
        )
        row = self._runalyze_row(301, "2024-05-01", 3601, 10.005)
        client = FakeRunalyze([row], {"301": dict(row)})

        summary = RunalyzeEnricher(self.conn, client=client).enrich()

        self.assertEqual(1, summary.matched)
        self.assertEqual(0, summary.reviews_recorded)
        self.assertEqual([], self._review_items())
        link = self.conn.execute(
            """
            SELECT match_method FROM activity_sources
            WHERE activity_id = 'd1'
            """
        ).fetchall()
        self.assertIn("exact_twin", [row["match_method"] for row in link])

    def test_a_sheet_duplicate_is_reviewed_and_suggests_the_device_row(self):
        self._linked_activity("s1", "2024-05-02", 3600, 10000, source="sheet")
        self._linked_activity(
            "d2", "2024-05-02", 3610, 9400, source="fit", name="Morning Run"
        )
        row = self._runalyze_row(302, "2024-05-02", 3600, 10.0)
        client = FakeRunalyze([row], {"302": dict(row)})

        summary = RunalyzeEnricher(self.conn, client=client).enrich()

        self.assertEqual(0, summary.matched)
        self.assertEqual(1, summary.reviews_recorded)
        self.assertEqual(1, summary.unmatched)
        self.assertEqual(
            "exact_sheet_duplicate",
            summary.unmatched_rows[0]["reason"],
        )
        item = self._review_items()[0]
        context = json.loads(item["context_json"])
        self.assertEqual("d2", context["suggested_activity_id"])
        linked = self.conn.execute(
            """
            SELECT 1 FROM activity_sources als
            JOIN source_records sr ON sr.id = als.source_record_id
            WHERE sr.external_id = '302'
            """
        ).fetchone()
        self.assertIsNone(linked)

    def test_distance_mismatch_opens_a_review_with_its_day_candidates(self):
        self._linked_activity(
            "d3", "2024-05-03", 3600, 10000, source="fit", name="Morning Run"
        )
        row = self._runalyze_row(303, "2024-05-03", 3600, 12.0, hour="09")
        client = FakeRunalyze([row], {"303": dict(row)})

        summary = RunalyzeEnricher(self.conn, client=client).enrich()

        self.assertEqual(1, summary.unmatched)
        self.assertEqual(
            "distance_mismatch",
            summary.unmatched_rows[0]["reason"],
        )
        context = json.loads(self._review_items()[0]["context_json"])
        self.assertEqual(
            ["d3"],
            [candidate["activity_id"] for candidate in context["candidates"]],
        )
        self.assertIsNone(context["suggested_activity_id"])

    def test_no_temporal_match_opens_a_review_and_creates_nothing(self):
        before = self.conn.execute(
            "SELECT COUNT(*) FROM activities"
        ).fetchone()[0]
        row = self._runalyze_row(304, "2024-05-04", 1800, 5.0)
        client = FakeRunalyze([row], {"304": dict(row)})

        summary = RunalyzeEnricher(self.conn, client=client).enrich()

        self.assertEqual(1, summary.unmatched)
        self.assertEqual(
            "no_temporal_match",
            summary.unmatched_rows[0]["reason"],
        )
        context = json.loads(self._review_items()[0]["context_json"])
        self.assertEqual([], context["candidates"])
        self.assertEqual(
            before,
            self.conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0],
        )

    def test_a_reviewed_row_is_not_fetched_again(self):
        row = self._runalyze_row(305, "2024-05-05", 1800, 5.0)
        client = FakeRunalyze([row], {"305": dict(row)})
        enricher = RunalyzeEnricher(self.conn, client=client)

        first = enricher.enrich()
        second = enricher.enrich()

        self.assertEqual(1, first.reviews_recorded)
        self.assertEqual(0, second.reviews_recorded)
        self.assertEqual(1, second.already_reviewed)
        self.assertEqual(1, len(client.detail_calls))
        self.assertEqual(1, len(self._review_items()))

    def test_resolving_a_review_applies_the_stored_detail(self):
        self._linked_activity(
            "d6", "2024-05-06", 3600, 10000, source="fit", name="Morning Run"
        )
        row = self._runalyze_row(306, "2024-05-06", 3600, 12.0)
        row["note"] = "Runalyze comment"
        row["tags"] = [{"id": 9, "tag": "Raceday"}]
        client = FakeRunalyze([row], {"306": dict(row)})
        RunalyzeEnricher(self.conn, client=client).enrich()

        item = self._review_items()[0]
        self.writer.resolve_review_match(item["id"], "d6")
        filled, kept, tags = apply_stored_enrichment(
            self.conn,
            item["source_record_id"],
        )

        self.assertEqual((1, 0, 1), (filled, kept, tags))
        self.assertEqual("Runalyze comment", self._row("d6")["description"])
        self.assertEqual({("Raceday", "runalyze", 0)}, self._tags("d6"))
        self.assertEqual(
            "resolved",
            self.conn.execute(
                "SELECT status FROM review_items WHERE id = ?",
                (item["id"],),
            ).fetchone()["status"],
        )

    def test_ambiguous_match_stores_the_detail_and_opens_an_item(self):
        self._activity(
            "a3",
            "2024-04-01",
            "2024-04-01T06:00:00Z",
            1800,
            1800,
            5000,
        )
        self._activity(
            "a4",
            "2024-04-01",
            "2024-04-01T06:00:00Z",
            1800,
            1800,
            5000,
        )
        row = {
            "id": 205,
            "date_time": "2024-04-01T08:00:00+02:00",
            "duration": 1800,
            "elapsed_time": 1800,
            "distance": 5.0,
        }
        client = FakeRunalyze([row], {"205": dict(row)})
        enricher = RunalyzeEnricher(self.conn, client=client)

        summary = enricher.enrich()

        self.assertEqual(1, summary.ambiguous)
        self.assertEqual(0, summary.unmatched)
        self.assertEqual(["205"], client.detail_calls)
        self.assertEqual(
            "several_exact",
            summary.unmatched_rows[0]["reason"],
        )

        item = self.conn.execute(
            "SELECT * FROM review_items WHERE category = 'ambiguous_match'"
        ).fetchone()
        self.assertIsNotNone(item)
        self.assertEqual("open", item["status"])
        self.assertIsNotNone(item["source_record_id"])
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_sources als "
                "JOIN source_records sr ON sr.id = als.source_record_id "
                "WHERE sr.external_id = '205'"
            ).fetchone()[0],
        )

    def test_rate_limit_mid_run_keeps_processed_rows(self):
        client = FakeRunalyze(
            _fixture("enrich_collection.json"),
            {"201": self.details["201"]},
            rate_limited={"202"},
        )
        enricher = RunalyzeEnricher(self.conn, client=client)

        summary = enricher.enrich()

        self.assertEqual(1, summary.matched)
        self.assertEqual(1, summary.detail_fetches)
        self.assertEqual(2, summary.processed)
        self.assertEqual(2, summary.not_processed)
        self.assertTrue(summary.stopped_reason)
        self.assertEqual("Runalyze comment", self._row("a1")["description"])
        self.assertEqual(
            "Intervals note",
            self._row("a2")["description"],
        )
        self.assertEqual(
            {("Race", "runalyze", 0), ("Hilly", "runalyze", 0)},
            self._tags("a1"),
        )
        self.assertEqual(set(), self._tags("a2"))
        status = self.conn.execute(
            "SELECT status FROM import_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()["status"]
        self.assertEqual("partial", status)

    def test_resumes_after_a_rate_limit(self):
        first_client = FakeRunalyze(
            _fixture("enrich_collection.json"),
            {"201": self.details["201"]},
            rate_limited={"202"},
        )
        first = RunalyzeEnricher(
            self.conn,
            client=first_client,
        ).enrich()
        self.assertEqual(1, first.matched)
        self.assertEqual(2, first.not_processed)

        second_client = FakeRunalyze(
            _fixture("enrich_collection.json"),
            self.details,
        )
        second = RunalyzeEnricher(
            self.conn,
            client=second_client,
        ).enrich()

        self.assertEqual(1, second.already_enriched)
        self.assertEqual(0, second.already_reviewed)
        self.assertEqual(2, second.reviews_recorded)
        self.assertEqual(3, second.detail_fetches)
        self.assertEqual(["202", "203", "204"], second_client.detail_calls)
        self.assertEqual(4, second.processed)
        self.assertEqual(0, second.not_processed)
        self.assertEqual(1, second.matched)
        self.assertEqual(
            {("Easy", "runalyze", 0)},
            self._tags("a2"),
        )

    def test_refresh_re_fetches_current_details(self):
        self.enricher.enrich()

        summary = self.enricher.enrich(refresh=True)

        self.assertEqual(0, summary.already_enriched)
        self.assertEqual(4, summary.detail_fetches)
        self.assertEqual(
            ["201", "202", "203", "204"],
            self.client.detail_calls[-4:],
        )

    def test_wait_sleeps_and_resumes_until_complete(self):
        client = FakeRunalyze(
            _fixture("enrich_collection.json"),
            self.details,
            rate_limited={"201"},
        )
        enricher = RunalyzeEnricher(self.conn, client=client)

        with patch(
            "hobbyjogging_import.runalyze_import.time.sleep"
        ) as sleep:
            summary = enricher.enrich(wait=True)

        sleep.assert_called_once_with(6.0)
        self.assertEqual(1, client.activity_calls)
        self.assertEqual(0, summary.not_processed)
        self.assertEqual(2, summary.matched)
        self.assertEqual(4, summary.detail_fetches)
        self.assertEqual("", summary.stopped_reason)
        self.assertEqual(
            ["201", "201", "202", "203", "204"],
            client.detail_calls,
        )
        self.assertEqual("Runalyze comment", self._row("a1")["description"])
        self.assertEqual(
            {("Easy", "runalyze", 0)},
            self._tags("a2"),
        )

    def test_wait_rejects_dry_run_and_refresh(self):
        with self.assertRaises(ValueError):
            self.enricher.enrich(wait=True, dry_run=True)
        with self.assertRaises(ValueError):
            self.enricher.enrich(wait=True, refresh=True)

    def test_missing_edited_at_still_skips_the_stored_detail(self):
        self.enricher.enrich()
        for row in self.client.activities_payload:
            row["edited_at"] = None

        summary = self.enricher.enrich()

        self.assertEqual(2, summary.already_enriched)
        self.assertEqual(2, summary.already_reviewed)
        self.assertEqual(0, summary.detail_fetches)
        self.assertEqual(0, summary.matched)

    def test_ids_repair_skips_the_collection(self):
        summary = self.enricher.enrich(ids=["201"])

        self.assertEqual(0, self.client.activity_calls)
        self.assertEqual(["201"], self.client.detail_calls)
        self.assertEqual(1, summary.detail_fetches)
        self.assertEqual(1, summary.processed)
        self.assertEqual(1, summary.matched)
        self.assertEqual("Runalyze comment", self._row("a1")["description"])
        self.assertEqual(2, len(self._tags("a1")))

    def test_ids_refresh_re_applies_a_stored_row(self):
        self.enricher.enrich(ids=["201"])

        summary = self.enricher.enrich(ids=["201"], refresh=True)

        self.assertEqual(0, summary.already_enriched)
        self.assertEqual(1, summary.detail_fetches)
        self.assertEqual(1, summary.matched)

    def test_ids_cannot_be_combined_with_wait(self):
        with self.assertRaises(ValueError):
            self.enricher.enrich(ids=["201"], wait=True)

    def test_summary_format(self):
        summary = self.enricher.enrich(dry_run=True)

        text = format_enrich_summary(summary)

        self.assertIn("Runalyze enrich dry run", text)
        self.assertIn("matched: 2", text)
        self.assertIn("comments filled: 1", text)
        self.assertIn("activities tagged: 2", text)


class RunalyzeEnrichCliTests(unittest.TestCase):

    def test_parser_accepts_enrich_options(self):
        args = build_parser().parse_args(
            [
                "runalyze",
                "enrich",
                "--dry-run",
                "--since",
                "2024-01-01",
                "--to",
                "2024-12-31",
                "--limit",
                "10",
                "--refresh",
                "--wait",
                "--output",
                "/tmp/unmatched.json",
            ]
        )

        self.assertEqual("runalyze", args.command)
        self.assertEqual("enrich", args.runalyze_action)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.refresh)
        self.assertTrue(args.wait)
        self.assertEqual(date(2024, 1, 1), args.start)
        self.assertEqual(date(2024, 12, 31), args.end)
        self.assertEqual(10, args.limit)
        self.assertEqual(Path("/tmp/unmatched.json"), args.output)


if __name__ == "__main__":
    unittest.main()
