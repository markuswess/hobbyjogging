import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_import.cli import build_parser, run_runalyze
from hobbyjogging_import.runalyze import (
    RunalyzeClient,
    RunalyzeRateLimitError,
    RunalyzeResponse,
    _year_from_value,
    format_inventory,
    run_inventory,
)

FIXTURES = Path(__file__).parent / "fixtures" / "runalyze"
BLOCKED = {"sport", "recurring-route", "planned-race", "device-profile"}


def _fixture(name):
    return json.loads((FIXTURES / name).read_text("utf-8"))


class FakeApi:
    """Recorded-fixture Runalyze API, no network."""

    def __init__(self, pages, detail):
        self.pages = pages
        self.detail = detail
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == "activity":
            page = int((params or {}).get("page", 1))
            payload = (
                self.pages[page - 1]
                if page - 1 < len(self.pages)
                else []
            )
            return RunalyzeResponse(200, {}, payload)
        if path.startswith("activity/"):
            return RunalyzeResponse(200, {}, self.detail)
        if path in BLOCKED:
            return RunalyzeResponse(403, {}, {"detail": "forbidden"})
        if path == "ping":
            return RunalyzeResponse(200, {}, {"message": "pong"})
        if path == "equipment":
            return RunalyzeResponse(200, {}, [])
        return RunalyzeResponse(200, {}, {})

    def activities(self, start, end, *, per_page=100):
        items = []
        page = 1
        while True:
            batch = (
                self.pages[page - 1]
                if page - 1 < len(self.pages)
                else []
            )
            if not batch:
                break
            items.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return items


class FakeResponse:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        return self.handler(url, params)


class RunalyzeClientTests(unittest.TestCase):

    def test_sends_the_token_header_and_paginates(self):
        pages = {
            1: _fixture("activities_page1.json"),
            2: _fixture("activities_page2.json"),
        }

        def handler(url, params):
            page = int((params or {}).get("page", 1))
            return FakeResponse(200, pages.get(page, []))

        session = FakeSession(handler)
        client = RunalyzeClient(
            api_key="secret",
            base_url="https://example.test/api/v1",
            session=session,
        )

        items = client.activities(
            date(2023, 1, 1),
            date(2024, 12, 31),
            per_page=2,
        )

        self.assertEqual(3, len(items))
        self.assertEqual(2, len(session.calls))
        self.assertEqual(
            "https://example.test/api/v1/activity",
            session.calls[0]["url"],
        )
        self.assertEqual("secret", session.calls[0]["headers"]["token"])
        self.assertEqual(1, session.calls[0]["params"]["page"])
        self.assertEqual(2, session.calls[0]["params"]["itemsPerPage"])
        self.assertEqual(2, session.calls[1]["params"]["page"])

    def test_range_is_filtered_locally(self):
        pages = {
            1: _fixture("activities_page1.json"),
            2: _fixture("activities_page2.json"),
        }

        def handler(url, params):
            page = int((params or {}).get("page", 1))
            return FakeResponse(200, pages.get(page, []))

        client = RunalyzeClient(
            api_key="secret",
            base_url="https://example.test/api/v1",
            session=FakeSession(handler),
        )

        items = client.activities(
            date(2024, 1, 1),
            date(2024, 12, 31),
            per_page=2,
        )

        self.assertEqual([101, 102], [item["id"] for item in items])

    def test_pagination_stops_when_the_server_repeats_a_page(self):
        page = _fixture("activities_page1.json")

        session = FakeSession(
            lambda url, params: FakeResponse(200, page)
        )
        client = RunalyzeClient(
            api_key="secret",
            base_url="https://example.test/api/v1",
            session=session,
        )

        items = client.activities(None, None, per_page=2)

        self.assertEqual(2, len(items))
        self.assertEqual(2, len(session.calls))

    def test_rate_limit_raises_with_the_reset(self):
        session = FakeSession(
            lambda url, params: FakeResponse(
                429,
                {"detail": "Too many requests"},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Reset": "1700000000",
                    "X-RateLimit-Limit": "240",
                },
            )
        )
        client = RunalyzeClient(
            api_key="secret",
            base_url="https://example.test/api/v1",
            session=session,
        )

        with self.assertRaises(RunalyzeRateLimitError) as caught:
            client.get("ping")

        self.assertEqual(60, caught.exception.retry_after_s)
        self.assertEqual(240, caught.exception.limit)
        self.assertIn("rate limit", str(caught.exception))

    def test_missing_token_raises(self):
        with patch(
            "hobbyjogging_import.runalyze.runalyze_api_key",
            return_value=None,
        ):
            with self.assertRaises(RuntimeError):
                RunalyzeClient()


class InventoryTests(unittest.TestCase):

    def _summary(self, **kwargs):
        api = FakeApi(
            [
                _fixture("activities_page1.json"),
                _fixture("activities_page2.json"),
            ],
            _fixture("activity.json"),
        )
        summary = run_inventory(
            api,
            start=date(2023, 1, 1),
            end=date(2024, 12, 31),
            per_page=2,
            dry_run=True,
            base_url="https://example.test/api/v1",
            **kwargs,
        )
        return summary, api

    def test_reports_endpoint_availability(self):
        summary, _ = self._summary()

        statuses = {
            endpoint.label: endpoint.status
            for endpoint in summary.endpoints
        }
        self.assertEqual(200, statuses["ping"])
        self.assertEqual(200, statuses["activities"])
        self.assertEqual(403, statuses["sport"])
        self.assertEqual(403, statuses["recurring-route"])
        self.assertEqual(403, statuses["planned-race"])
        self.assertEqual(403, statuses["device-profile"])
        self.assertEqual(200, statuses["activity detail"])

    def test_tallies_fields_per_year(self):
        summary, _ = self._summary()

        self.assertEqual(3, summary.activity_count)
        self.assertEqual([2023, 2024], summary.years)
        self.assertEqual({2023: 1, 2024: 2}, summary.activities_by_year)
        self.assertEqual(2, summary.fields["distance"][2024])
        self.assertEqual(1, summary.fields["vo2max"][2024])
        self.assertEqual(1, summary.fields["distance"][2023])

        detail = next(
            endpoint
            for endpoint in summary.endpoints
            if endpoint.label == "activity detail"
        )
        self.assertEqual("6 fields", detail.note)

    def test_limit_caps_the_activity_sample(self):
        summary, _ = self._summary(limit=1)

        self.assertEqual(1, summary.activity_count)
        self.assertEqual({2024: 1}, summary.activities_by_year)

    def test_formatter_shows_blocked_endpoints_and_fields(self):
        summary, _ = self._summary()

        text = format_inventory(summary)

        self.assertIn("Runalyze inventory (dry run)", text)
        self.assertIn("blocked:", text)
        self.assertIn("sport", text)
        self.assertIn("vo2max", text)
        self.assertIn("Counts are activities with a non-null value", text)

    def test_year_from_value_handles_the_known_shapes(self):
        self.assertEqual(2024, _year_from_value("2024-03-01 08:00:00"))
        self.assertEqual(2023, _year_from_value(1_700_000_000))
        self.assertEqual(2024, _year_from_value(20240301))
        self.assertIsNone(_year_from_value(None))


class RunalyzeCliTests(unittest.TestCase):

    def test_parser_accepts_inventory_options(self):
        args = build_parser().parse_args(
            [
                "runalyze",
                "inventory",
                "--dry-run",
                "--since",
                "2024-01-01",
                "--to",
                "2024-12-31",
                "--limit",
                "10",
            ]
        )

        self.assertEqual("runalyze", args.command)
        self.assertEqual("inventory", args.runalyze_action)
        self.assertTrue(args.dry_run)
        self.assertEqual(date(2024, 1, 1), args.start)
        self.assertEqual(date(2024, 12, 31), args.end)
        self.assertEqual(10, args.limit)

    def test_missing_token_exits_cleanly(self):
        args = build_parser().parse_args(
            ["runalyze", "inventory", "--dry-run"]
        )

        with patch(
            "hobbyjogging_import.cli.RunalyzeClient",
            side_effect=RuntimeError("RUNALYZE_API_KEY must be set"),
        ):
            with self.assertRaises(SystemExit) as caught:
                run_runalyze(args, build_parser())

        self.assertIn("RUNALYZE_API_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
