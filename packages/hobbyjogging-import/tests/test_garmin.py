import base64
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core import connect, migrate
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.garmin import (
    GarminClient,
    GarminFetcher,
    extract_fit,
)


def _zip(*members) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


def _activity(activity_id: int, **overrides):
    item = {
        "activityId": activity_id,
        "startTimeLocal": "2026-10-01T08:00:00",
        "activityName": "Run",
    }
    item.update(overrides)
    return item


def _jwt(expires_at: float) -> str:
    header = base64.urlsafe_b64encode(
        b'{"alg":"none"}'
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": expires_at}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.signature"


class FakeGarminApi:

    def __init__(self, activities=None, downloads=None):
        self.activities = activities or []
        self.downloads = downloads or {}
        self.list_calls = []
        self.download_calls = []

    def list_activities(self, start, end):
        self.list_calls.append((start, end))
        return self.activities

    def download_activity(self, activity_id):
        self.download_calls.append(activity_id)
        value = self.downloads[activity_id]
        if isinstance(value, Exception):
            raise value
        return value


class GarminFetcherTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.fit_dir = Path(self.temp_dir.name) / "garmin"
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)

    def _fetcher(self, api):
        return GarminFetcher(
            self.conn,
            client=api,
            fit_dir=self.fit_dir,
        )

    def _fetch(self, api, **kwargs):
        return self._fetcher(api).fetch(
            date(2026, 10, 1),
            date(2026, 10, 1),
            **kwargs,
        )

    def _manifest(self):
        return self.conn.execute(
            "SELECT * FROM source_records WHERE source = 'garmin'"
        ).fetchall()

    def test_fetch_writes_fit_and_manifest(self):
        api = FakeGarminApi(
            [_activity(1001)],
            {"1001": _zip(("1001_ACTIVITY.fit", b"fit-bytes"))},
        )

        summary = self._fetch(api)

        self.assertEqual(1, summary.listed)
        self.assertEqual(1, summary.new)
        self.assertEqual(1, summary.downloaded)
        self.assertEqual(0, summary.failed)
        self.assertEqual(["1001"], summary.new_ids)

        destination = self.fit_dir / "1001.fit"
        self.assertEqual(b"fit-bytes", destination.read_bytes())

        rows = self._manifest()
        self.assertEqual(1, len(rows))
        self.assertEqual("activity-file", rows[0]["record_type"])
        self.assertEqual("1001", rows[0]["external_id"])
        self.assertEqual(str(destination), rows[0]["raw_path"])
        self.assertIn('"activityId":1001', rows[0]["payload_json"])

        run = self.conn.execute(
            "SELECT status, records_seen, records_imported "
            "FROM import_runs WHERE id = ?",
            (summary.run_id,),
        ).fetchone()
        self.assertEqual("success", run["status"])
        self.assertEqual(1, run["records_seen"])
        self.assertEqual(1, run["records_imported"])

    def test_second_fetch_skips_known_activity(self):
        api = FakeGarminApi(
            [_activity(1001)],
            {"1001": _zip(("1001_ACTIVITY.fit", b"fit-bytes"))},
        )
        self._fetch(api)
        api.download_calls.clear()

        summary = self._fetch(api)

        self.assertEqual(1, summary.listed)
        self.assertEqual(0, summary.new)
        self.assertEqual(1, summary.skipped_known)
        self.assertEqual(0, summary.downloaded)
        self.assertEqual([], api.download_calls)
        self.assertEqual(1, len(self._manifest()))

    def test_force_redownloads_known_activity(self):
        api = FakeGarminApi(
            [_activity(1001)],
            {"1001": _zip(("1001_ACTIVITY.fit", b"fit-bytes"))},
        )
        self._fetch(api)
        api.download_calls.clear()

        summary = self._fetch(api, force=True)

        self.assertEqual(1, summary.downloaded)
        self.assertEqual(["1001"], api.download_calls)
        self.assertEqual(1, len(self._manifest()))

    def test_dry_run_writes_nothing(self):
        api = FakeGarminApi(
            [_activity(1001)],
            {"1001": _zip(("1001_ACTIVITY.fit", b"fit-bytes"))},
        )

        summary = self._fetch(api, dry_run=True)

        self.assertEqual(0, summary.downloaded)
        self.assertEqual(1, summary.new)
        self.assertEqual(["1001"], summary.new_ids)
        self.assertEqual([], api.download_calls)
        self.assertFalse((self.fit_dir / "1001.fit").exists())
        self.assertEqual(0, len(self._manifest()))
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM import_runs"
            ).fetchone()[0],
        )

    def test_limit_stops_after_new_activities(self):
        api = FakeGarminApi(
            [_activity(1001), _activity(1002)],
            {
                "1001": _zip(("1001_ACTIVITY.fit", b"one")),
                "1002": _zip(("1002_ACTIVITY.fit", b"two")),
            },
        )

        summary = self._fetch(api, limit=1)

        self.assertEqual(1, summary.new)
        self.assertEqual(1, summary.downloaded)
        self.assertEqual(1, summary.skipped_limit)
        self.assertEqual(["1001"], api.download_calls)

    def test_failed_download_is_reported_and_partial(self):
        api = FakeGarminApi(
            [_activity(1001)],
            {"1001": RuntimeError("network down")},
        )

        summary = self._fetch(api)

        self.assertEqual(1, summary.new)
        self.assertEqual(0, summary.downloaded)
        self.assertEqual(1, summary.failed)
        self.assertIn("1001", summary.errors[0])
        self.assertIn("network down", summary.errors[0])
        self.assertFalse((self.fit_dir / "1001.fit").exists())

        run = self.conn.execute(
            "SELECT status, error FROM import_runs WHERE id = ?",
            (summary.run_id,),
        ).fetchone()
        self.assertEqual("partial", run["status"])
        self.assertIn("network down", run["error"])

    def test_activity_without_id_is_reported(self):
        api = FakeGarminApi([{"activityName": "broken"}])

        summary = self._fetch(api)

        self.assertEqual(1, summary.failed)
        self.assertEqual(0, summary.new)
        self.assertEqual(1, len(summary.errors))


class ExtractFitTests(unittest.TestCase):

    def test_prefers_activity_member(self):
        name, data = extract_fit(
            _zip(
                ("meta.fit", b"meta"),
                ("1001_ACTIVITY.fit", b"activity"),
            )
        )

        self.assertEqual("1001_ACTIVITY.fit", name)
        self.assertEqual(b"activity", data)

    def test_rejects_zip_without_fit(self):
        with self.assertRaises(ValueError):
            extract_fit(_zip(("readme.txt", b"nope")))

    def test_rejects_non_zip(self):
        with self.assertRaises(ValueError):
            extract_fit(b"not a zip")


class FakeResponse:

    def __init__(
        self,
        status_code=200,
        *,
        content=b"",
        text="",
        json_data=None,
    ):
        self.status_code = status_code
        self.content = content
        self.text = text
        self._json = json_data

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json


class FakeSession:

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


class GarminClientTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache = Path(self.temp_dir.name) / "token.json"
        self.base_url = "https://garmin.test"
        self.start = date(2026, 10, 1)
        self.end = date(2026, 10, 1)

    def _client(self, session, *, api_key="key", clock=lambda: 1000.0):
        return GarminClient(
            api_key,
            base_url=self.base_url,
            session=session,
            token_cache_path=self.cache,
            clock=clock,
        )

    def test_list_activities_uses_bearer_token_and_caches_it(self):
        token = _jwt(10_000)
        session = FakeSession(
            [
                FakeResponse(text=token),
                FakeResponse(content=b"x", json_data=[_activity(1)]),
            ]
        )

        activities = self._client(session).list_activities(
            self.start,
            self.end,
        )

        self.assertEqual([_activity(1)], activities)
        self.assertEqual("POST", session.calls[0][0])
        self.assertEqual("ApiKey key", session.calls[0][2]["headers"]["Authorization"])
        self.assertEqual("GET", session.calls[1][0])
        self.assertEqual(
            f"Bearer {token}",
            session.calls[1][2]["headers"]["Authorization"],
        )
        self.assertEqual("2026-10-01", session.calls[1][2]["params"]["startDate"])

        cached = json.loads(self.cache.read_text())
        self.assertEqual(token, cached["access_token"])
        self.assertEqual(10_000, cached["expires_at"])

    def test_cached_token_is_reused(self):
        token = _jwt(10_000)
        first = FakeSession(
            [
                FakeResponse(text=token),
                FakeResponse(content=b"x", json_data=[]),
            ]
        )
        self._client(first).list_activities(self.start, self.end)

        second = FakeSession(
            [FakeResponse(content=b"x", json_data=[])]
        )
        self._client(second).list_activities(self.start, self.end)

        self.assertEqual(
            ["GET"],
            [call[0] for call in second.calls],
        )

    def test_401_forces_a_new_token(self):
        first_token = _jwt(10_000)
        second_token = _jwt(20_000)
        session = FakeSession(
            [
                FakeResponse(text=first_token),
                FakeResponse(status_code=401, text="expired"),
                FakeResponse(text=second_token),
                FakeResponse(content=b"x", json_data=[_activity(1)]),
            ]
        )

        activities = self._client(session).list_activities(
            self.start,
            self.end,
        )

        self.assertEqual(1, len(activities))
        self.assertEqual(
            ["POST", "GET", "POST", "GET"],
            [call[0] for call in session.calls],
        )
        self.assertEqual(
            f"Bearer {second_token}",
            session.calls[3][2]["headers"]["Authorization"],
        )

    def test_missing_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                GarminClient(session=FakeSession([]))

    def test_invalid_token_response_raises(self):
        session = FakeSession([FakeResponse(text="not-a-jwt")])

        with self.assertRaises(RuntimeError):
            self._client(session).list_activities(self.start, self.end)

    def test_paginates_until_short_page(self):
        token = _jwt(10_000)
        first_page = [_activity(index) for index in range(100)]
        second_page = [_activity(100)]
        session = FakeSession(
            [
                FakeResponse(text=token),
                FakeResponse(content=b"x", json_data=first_page),
                FakeResponse(content=b"x", json_data=second_page),
            ]
        )

        activities = self._client(session).list_activities(
            self.start,
            self.end,
        )

        self.assertEqual(101, len(activities))
        self.assertEqual(0, session.calls[1][2]["params"]["start"])
        self.assertEqual(100, session.calls[2][2]["params"]["start"])

    def test_empty_page_stops(self):
        token = _jwt(10_000)
        session = FakeSession(
            [
                FakeResponse(text=token),
                FakeResponse(content=b"x", json_data=[]),
            ]
        )

        self.assertEqual(
            [],
            self._client(session).list_activities(self.start, self.end),
        )


class GarminCliTests(unittest.TestCase):

    def test_fetch_arguments(self):
        args = build_parser().parse_args(
            [
                "garmin",
                "fetch",
                "--since",
                "2026-01-01",
                "--to",
                "2026-02-01",
                "--fit-dir",
                "/tmp/garmin",
                "--limit",
                "5",
                "--force",
                "--dry-run",
            ]
        )

        self.assertEqual("garmin", args.command)
        self.assertEqual("fetch", args.garmin_action)
        self.assertEqual("2026-01-01", args.start.isoformat())
        self.assertEqual("2026-02-01", args.end.isoformat())
        self.assertEqual(Path("/tmp/garmin"), args.fit_dir)
        self.assertEqual(5, args.limit)
        self.assertTrue(args.force)
        self.assertTrue(args.dry_run)

    def test_fetch_defaults(self):
        args = build_parser().parse_args(["garmin", "fetch"])

        self.assertEqual(30, args.days)
        self.assertIsNone(args.start)
        self.assertIsNone(args.end)
        self.assertIsNone(args.fit_dir)
        self.assertIsNone(args.limit)
        self.assertFalse(args.force)
        self.assertFalse(args.dry_run)


if __name__ == "__main__":
    unittest.main()
