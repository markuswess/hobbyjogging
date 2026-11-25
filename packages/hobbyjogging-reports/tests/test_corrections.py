import csv
import io
import json
import unittest
from datetime import date

from hobbyjogging_core.model import ActivitySocial, ReviewItem
from hobbyjogging_report.corrections import corrections_report
from hobbyjogging_report.links import ActivityLinks
from support import FakeSource


D1 = date(2026, 10, 1)
D2 = date(2026, 9, 1)


def _conflict(
    *,
    item_id=1,
    day=D1,
    field="distance_m",
    current_source="intervals",
    current_value=10000.0,
    incoming_source="fit",
    incoming_value=10500.0,
    cause="distance_estimate",
    activity_id="a",
    activity_name="Long run",
    source="fit",
):
    return ReviewItem(
        id=item_id,
        category="field_conflict",
        activity_id=activity_id,
        activity_date=day,
        activity_name=activity_name,
        sport="run",
        source=source,
        context={
            "field": field,
            "current": {
                "source": current_source,
                "value": current_value,
            },
            "incoming": {
                "source": incoming_source,
                "value": incoming_value,
            },
            "cause": cause,
        },
    )


def _quality(*, item_id=2, day=D1, source="fit"):
    return ReviewItem(
        id=item_id,
        category="quality",
        activity_id="a",
        activity_date=day,
        activity_name="Long run",
        sport="run",
        source=source,
        detail="duration is 0 s while elapsed is 100 s",
        context={
            "rule": "zero_duration",
            "duration_s": 0,
            "elapsed_s": 100,
        },
    )


class CorrectionsReportTests(unittest.TestCase):

    def test_markdown_groups_by_the_disagreeing_source(self):
        source = FakeSource(
            review_items=[
                _conflict(incoming_source="fit"),
                _conflict(
                    item_id=2,
                    field="avg_hr",
                    current_source="fit",
                    current_value=145,
                    incoming_source="intervals",
                    incoming_value=160,
                    cause="hr_sensor_anomaly",
                ),
            ],
            links={"a": ActivityLinks(intervals="https://i/a", garmin="https://g/a")},
        )

        report = corrections_report(source)

        self.assertIn("# Corrections", report)
        self.assertIn("Open field conflicts: 2", report)
        self.assertIn("## fit", report)
        self.assertIn("## intervals", report)
        self.assertIn("| 2026-10-01 | Long run | distance_m | 10.00 km", report)
        self.assertIn("| 10.50 km | distance_estimate |", report)
        self.assertIn("[open](https://g/a)", report)
        self.assertIn("[open](https://i/a)", report)
        self.assertIn("Read-only", report)

    def test_strava_uses_the_social_url(self):
        source = FakeSource(
            review_items=[
                _conflict(
                    incoming_source="strava",
                    source="strava",
                ),
            ],
            social={
                "a": [
                    ActivitySocial(
                        activity_id="a",
                        source="strava",
                        url="https://strava/activities/1",
                    )
                ]
            },
        )

        report = corrections_report(source)

        self.assertIn("[open](https://strava/activities/1)", report)

    def test_a_source_side_quality_finding_is_included(self):
        source = FakeSource(review_items=[_quality()])

        report = corrections_report(source)

        self.assertIn("Source-side quality findings: 1", report)
        self.assertIn("## Quality findings", report)
        self.assertIn("zero_duration", report)
        self.assertIn("duration is 0 s", report)

    def test_quality_findings_without_a_source_are_skipped(self):
        source = FakeSource(review_items=[_quality(source="")])

        report = corrections_report(source)

        self.assertIn("Source-side quality findings: 0", report)

    def test_csv_output_has_one_row_per_finding(self):
        source = FakeSource(review_items=[_conflict()])

        text = corrections_report(source, fmt="csv")
        rows = list(csv.DictReader(io.StringIO(text)))

        self.assertEqual(1, len(rows))
        self.assertEqual("conflict", rows[0]["kind"])
        self.assertEqual("distance_m", rows[0]["field"])
        self.assertEqual("10.00 km", rows[0]["canonical_value"])
        self.assertEqual("10.50 km", rows[0]["source_value"])
        self.assertEqual("fit", rows[0]["source"])

    def test_json_output_matches_the_csv_fields(self):
        source = FakeSource(review_items=[_conflict()])

        rows = json.loads(corrections_report(source, fmt="json"))

        self.assertEqual(1, len(rows))
        self.assertEqual("Long run", rows[0]["activity"])
        self.assertEqual("distance_estimate", rows[0]["cause"])

    def test_the_range_filters_by_activity_date(self):
        source = FakeSource(
            review_items=[
                _conflict(item_id=1, day=D1),
                _conflict(item_id=2, day=D2),
            ]
        )

        report = corrections_report(source, D1, D1)

        self.assertIn("Open field conflicts: 1", report)
        self.assertNotIn(D2.isoformat(), report)

    def test_an_empty_queue_says_so(self):
        report = corrections_report(FakeSource())

        self.assertIn("No corrections", report)


if __name__ == "__main__":
    unittest.main()
