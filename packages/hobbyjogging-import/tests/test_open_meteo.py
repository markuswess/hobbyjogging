import json
import unittest
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_import.open_meteo import (
    OpenMeteoImporter,
    cache_key,
    condition_label,
)

SAMPLE_FIT = Path(__file__).resolve().parent / "fixtures" / "sample-run.fit"


def _response(day="2026-05-27", hour="07", temp=18.0):
    return {
        "hourly": {
            "time": [f"{day}T{hour}:00"],
            "temperature_2m": [temp],
            "apparent_temperature": [17.0],
            "relative_humidity_2m": [61.0],
            "wind_speed_10m": [3.4],
            "wind_gusts_10m": [5.1],
            "wind_direction_10m": [270.0],
            "pressure_msl": [1012.0],
            "cloud_cover": [40.0],
            "weather_code": [2],
            "is_day": [1],
        }
    }


class FakeClient:

    def __init__(self, response=None):
        self.response = response or _response()
        self.calls = []

    def fetch(self, latitude, longitude, day):
        self.calls.append((round(latitude, 2), round(longitude, 2), day))
        return self.response


class OpenMeteoImportTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.client = FakeClient()

    def _activity(
        self,
        activity_id="a1",
        *,
        sport="run",
        start="2026-05-27T07:28:18Z",
        day="2026-05-27",
        coordinate=(48.11, 16.32),
        path=None,
        excluded=False,
    ):
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": day,
                "started_at_utc": start,
                "sport": sport,
                "duration_s": 3600,
                "distance_m": 10000,
            },
            source="fit",
            source_record_id=None,
        )
        session = {"index": 1}
        if coordinate is not None:
            session["start_latitude"], session["start_longitude"] = coordinate
        payload = {
            "file": {"path": str(path or "/nonexistent.fit")},
            "session": session,
        }
        record_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id=f"fit-{activity_id}",
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
        )
        self.writer.link_activity_source(activity_id, record_id)
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return OpenMeteoImporter(
            self.conn,
            client=self.client,
        ).import_range(
            date(2026, 5, 27),
            date(2026, 5, 27),
            **kwargs,
        )

    def _weather(self, activity_id="a1"):
        row = self.conn.execute(
            "SELECT * FROM activity_weather WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def test_fetches_and_writes_ambient_weather(self):
        self._activity()

        summary = self._run()

        self.assertEqual(1, summary.fetched)
        self.assertEqual(1, summary.written)
        self.assertEqual(1, len(self.client.calls))
        row = self._weather()
        self.assertEqual("open-meteo", row["source"])
        self.assertEqual(18.0, row["temp_c"])
        self.assertEqual(17.0, row["feels_like_c"])
        self.assertEqual(61.0, row["humidity_pct"])
        self.assertEqual(3.4, row["wind_speed_ms"])
        self.assertEqual("partly cloudy", row["condition"])
        self.assertEqual(0, row["is_night"])
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records WHERE source='open-meteo'"
            ).fetchone()[0],
        )

    def test_the_cache_avoids_a_second_fetch(self):
        self._activity()
        self._run()
        self.conn.execute(
            "DELETE FROM activity_weather WHERE activity_id = 'a1'"
        )
        self.conn.commit()
        calls = len(self.client.calls)

        summary = self._run()

        self.assertEqual(calls, len(self.client.calls))
        self.assertEqual(1, summary.cached)
        self.assertEqual(1, summary.written)
        self.assertEqual("open-meteo", self._weather()["source"])

    def test_two_activities_in_one_cell_and_hour_share_a_request(self):
        self._activity("a1", coordinate=(48.111, 16.321))
        self._activity("a2", coordinate=(48.114, 16.324))

        summary = self._run()

        self.assertEqual(1, len(self.client.calls))
        self.assertEqual(2, summary.written)

    def test_a_dry_run_makes_no_request_or_write(self):
        self._activity()

        summary = self._run(dry_run=True)

        self.assertEqual(1, summary.would_fetch)
        self.assertEqual(0, summary.fetched)
        self.assertEqual(0, summary.written)
        self.assertEqual([], self.client.calls)
        self.assertIsNone(self._weather())
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records WHERE source='open-meteo'"
            ).fetchone()[0],
        )

    def test_a_missing_coordinate_is_a_gap(self):
        self._activity(coordinate=None)

        summary = self._run()

        self.assertEqual(1, summary.missing_coordinate)
        self.assertEqual(0, summary.written)
        self.assertEqual([], self.client.calls)

    def test_an_indoor_sport_is_skipped(self):
        self._activity(sport="treadmill_run")

        summary = self._run()

        self.assertEqual(0, summary.outdoor)
        self.assertEqual(0, summary.written)
        self.assertEqual([], self.client.calls)

    def test_the_fit_file_is_the_coordinate_fallback(self):
        self._activity(
            start="2020-09-09T07:39:48Z",
            day="2020-09-09",
            coordinate=None,
            path=SAMPLE_FIT,
        )
        self.client.response = _response(
            day="2020-09-09",
            hour="07",
            temp=11.0,
        )

        summary = OpenMeteoImporter(
            self.conn,
            client=self.client,
        ).import_range(
            date(2020, 9, 9),
            date(2020, 9, 9),
        )

        self.assertEqual(1, summary.fetched)
        self.assertEqual(1, summary.written)
        self.assertEqual(11.0, self._weather()["temp_c"])

    def test_refresh_refetches_a_cached_cell(self):
        self._activity()
        self._run()
        self.client.response = _response(temp=9.0)

        summary = self._run(refresh=True)

        self.assertEqual(2, len(self.client.calls))
        self.assertEqual(1, summary.written)
        self.assertEqual(9.0, self._weather()["temp_c"])

    def test_an_existing_weather_row_is_skipped_without_refresh(self):
        self._activity()
        self._run()
        calls = len(self.client.calls)

        summary = self._run()

        self.assertEqual(1, summary.skipped_existing)
        self.assertEqual(calls, len(self.client.calls))

    def test_the_cache_key_rounds_the_coordinate_and_hour(self):
        from datetime import datetime, timezone

        moment = datetime(2026, 5, 27, 7, 45, tzinfo=timezone.utc)
        self.assertEqual(
            "48.12,16.33,2026-05-27T07",
            cache_key(48.116, 16.327, moment.replace(minute=0)),
        )

    def test_condition_labels_cover_the_common_codes(self):
        self.assertEqual("clear", condition_label(0))
        self.assertEqual("rain", condition_label(61))
        self.assertEqual("snow", condition_label(71))
        self.assertEqual("thunderstorm", condition_label(95))


if __name__ == "__main__":
    unittest.main()
