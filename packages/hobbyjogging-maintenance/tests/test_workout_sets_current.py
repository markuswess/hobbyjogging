import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.classify import Category
from hobbyjogging_core.sources_config import SourcesConfig, default_policies

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "workout_sets_current"
QUEUE = "workout_classification_queue"
CLASSIFY = "hobbyjogging_maintenance.workouts.classify"

UNKNOWN = Category("unknown")
LONGRUN = Category("quality", "longrun")
TEMPO = Category("quality", "tempo")
INTERVALS = Category("quality", "intervals")


class WorkoutSetsCurrentTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _activity(
        self,
        name="Easy",
        *,
        code=None,
        sheet=True,
        sport="run",
        avg_hr=None,
        intensity=None,
        rpe=None,
        description="",
        tags=None,
        runalyze_type=None,
    ):
        self.counter += 1
        activity_id = f"a{self.counter}"
        source = "sheet" if sheet else "intervals"
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            payload_json=json.dumps({"values": {"Trainigstyp": code or ""}}),
            import_run_id=self.run_id,
        )
        values = {
            "local_date": "2026-10-01",
            "sport": sport,
            "name": name,
            "duration_s": 3600,
        }
        if description:
            values["description"] = description
        if avg_hr is not None:
            values["avg_hr"] = avg_hr
        if intensity is not None:
            values["intensity"] = intensity
        if rpe is not None:
            values["rpe"] = rpe
        self.writer.upsert_activity(
            activity_id,
            values,
            source=source,
            source_record_id=record_id,
        )
        if sheet:
            self.writer.link_activity_source(activity_id, record_id)
        if tags:
            self.writer.replace_activity_tags(
                activity_id,
                tags,
                source="runalyze",
            )
        if runalyze_type is not None:
            runalyze_record = self.writer.upsert_source_record(
                source="runalyze",
                record_type="activity",
                external_id=f"r-{activity_id}",
                checksum=f"r-{activity_id}",
                payload_json=json.dumps(
                    {"type": {"name": runalyze_type, "abbreviation": ""}}
                ),
                import_run_id=self.run_id,
            )
            self.writer.link_activity_source(
                activity_id,
                runalyze_record,
                match_method="exact_twin",
            )
        self.conn.commit()
        return activity_id

    def _sets(self, activity_id):
        methods = [
            row["method"]
            for row in self.conn.execute(
                "SELECT method FROM activity_workout_methods "
                "WHERE activity_id = ? ORDER BY method",
                (activity_id,),
            )
        ]
        targets = [
            row["target"]
            for row in self.conn.execute(
                "SELECT target FROM activity_workout_targets "
                "WHERE activity_id = ? ORDER BY target",
                (activity_id,),
            )
        ]
        return methods, targets

    def _sources(self, activity_id):
        return [
            (row["method"], row["source"], row["is_manual"])
            for row in self.conn.execute(
                "SELECT method, source, is_manual "
                "FROM activity_workout_methods "
                "WHERE activity_id = ? ORDER BY method",
                (activity_id,),
            )
        ]

    def _seed_sets(
        self,
        activity_id,
        methods,
        targets,
        *,
        source,
        manual=False,
    ):
        self.writer.replace_activity_workout_methods(
            activity_id,
            methods,
            source=source,
            is_manual=manual,
        )
        self.writer.replace_activity_workout_targets(
            activity_id,
            targets,
            source=source,
            is_manual=manual,
        )
        self.conn.commit()

    def test_derives_the_classifier_sets(self):
        activity_id = self._activity(sheet=False)

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )
        self.assertEqual([("continuous", "classifier", 0)], self._sources(activity_id))

    def test_derives_the_sheet_sets_when_the_classifier_has_none(self):
        activity_id = self._activity("Sessions", code="tdl")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [("continuous", "sheet", 0)],
            self._sources(activity_id),
        )

    def test_agreeing_proposals_are_merged(self):
        activity_id = self._activity("Tempo", code="tdl")

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [("continuous", "sheet", 0)],
            self._sources(activity_id),
        )

    def test_disagreement_stays_empty_and_the_queue_records_it(self):
        activity_id = self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=LONGRUN):
            run = self._run()

        self.assertEqual(1, run.counts["conflict"])
        self.assertEqual(([], []), self._sets(activity_id))
        self.assertTrue(any("queue" in note for note in run.notes))

        with patch(CLASSIFY, return_value=LONGRUN):
            run_task(self.conn, get_task(QUEUE))

        item = self.conn.execute(
            "SELECT category, activity_id FROM review_items "
            "WHERE status = 'open' AND category = 'workout_classification'"
        ).fetchone()
        self.assertIsNotNone(item)
        self.assertEqual(activity_id, item["activity_id"])

    def test_existing_sets_are_never_touched(self):
        activity_id = self._activity(sheet=False)
        self.writer.replace_activity_workout_methods(
            activity_id, ["progression"], source="manual", is_manual=True
        )
        self.writer.replace_activity_workout_targets(
            activity_id, ["base"], source="manual", is_manual=True
        )
        self.conn.commit()

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["already_classified"])
        self.assertEqual(0, run.counts["derived"])
        self.assertEqual(
            (["progression"], ["base"]),
            self._sets(activity_id),
        )

    def test_a_classifier_sourced_set_is_re_derived_after_a_rename(self):
        activity_id = self._activity("3x9' LT1", sheet=False, rpe=5)
        self._seed_sets(
            activity_id,
            ["intervals"],
            ["subthreshold"],
            source="classifier",
        )

        run = self._run()

        self.assertEqual(1, run.counts["reclassified"])
        self.assertEqual(
            (["intervals"], ["lt1"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [("intervals", "classifier", 0)],
            self._sources(activity_id),
        )

    def test_a_classifier_set_without_current_evidence_is_kept(self):
        activity_id = self._activity("Morning Run", sheet=False)
        self._seed_sets(
            activity_id,
            ["intervals"],
            ["subthreshold"],
            source="classifier",
        )

        run = self._run()

        self.assertEqual(1, run.counts["stale_no_evidence"])
        self.assertEqual(0, run.counts["reclassified"])
        self.assertEqual(
            (["intervals"], ["subthreshold"]),
            self._sets(activity_id),
        )

    def test_a_sheet_sourced_set_is_not_re_derived(self):
        activity_id = self._activity("3x9' LT1", sheet=False, rpe=5)
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["threshold"],
            source="sheet",
        )

        run = self._run()

        self.assertEqual(1, run.counts["already_classified"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_a_runalyze_type_set_is_not_re_derived(self):
        activity_id = self._activity("3x9' LT1", sheet=False, rpe=5)
        self._seed_sets(
            activity_id,
            ["intervals"],
            ["subthreshold"],
            source="runalyze",
        )

        run = self._run()

        self.assertEqual(1, run.counts["already_classified"])
        self.assertEqual(
            (["intervals"], ["subthreshold"]),
            self._sets(activity_id),
        )

    def test_a_dry_run_does_not_reclassify(self):
        activity_id = self._activity("3x9' LT1", sheet=False, rpe=5)
        self._seed_sets(
            activity_id,
            ["intervals"],
            ["subthreshold"],
            source="classifier",
        )

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["reclassified"])
        self.assertEqual(
            (["intervals"], ["subthreshold"]),
            self._sets(activity_id),
        )

    def test_a_longjog_tag_fills_an_empty_classification(self):
        activity_id = self._activity("Easy", sheet=False, tags=["Longjog"])

        run = self._run()

        self.assertEqual(1, run.counts["from_tag"])
        self.assertEqual(
            (["long_run"], ["base"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [("long_run", "tag", 0)],
            self._sources(activity_id),
        )

    def test_a_subthreshold_tag_fills_an_empty_classification(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            tags=["sub threshold"],
        )

        run = self._run()

        self.assertEqual(1, run.counts["from_tag"])
        self.assertEqual(
            (["intervals"], ["subthreshold"]),
            self._sets(activity_id),
        )

    def test_an_explicit_interval_description_fills_an_empty_classification(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            description="5x1000 interval",
        )

        run = self._run()

        self.assertEqual(1, run.counts["from_comment"])
        self.assertEqual(
            (["intervals"], ["other"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [("intervals", "comment", 0)],
            self._sources(activity_id),
        )

    def test_a_social_comment_fills_an_empty_classification(self):
        activity_id = self._activity("Easy", sheet=False)
        self.writer.upsert_activity_social(
            activity_id,
            source="strava",
            description="5x1000 interval",
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["from_comment"])
        self.assertEqual(
            (["intervals"], ["other"]),
            self._sets(activity_id),
        )

    def test_a_ladder_description_is_recognized(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            description="Einlaufen, 3-6-9-6-3min Intervalle ~167",
        )

        run = self._run()

        self.assertEqual(1, run.counts["from_comment"])
        self.assertEqual(
            (["intervals"], ["other"]),
            self._sets(activity_id),
        )

    def test_a_tag_wins_over_a_description(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            description="Tempo run",
            tags=["LT1"],
        )

        run = self._run()

        self.assertEqual(1, run.counts["from_tag"])
        self.assertEqual(0, run.counts["from_comment"])
        self.assertEqual(
            (["intervals"], ["lt1"]),
            self._sets(activity_id),
        )

    def test_a_classifier_proposal_wins_over_evidence(self):
        activity_id = self._activity(
            "Tempo",
            sheet=False,
            rpe=4,
            tags=["Longjog"],
        )

        run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(0, run.counts["from_tag"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_ltt_no_longer_proposes_threshold(self):
        from hobbyjogging_maintenance.workouts import tag_proposal

        proposal = tag_proposal(["LTT"])

        self.assertIsNotNone(proposal)
        self.assertEqual({"drills"}, proposal.methods)
        self.assertEqual(set(), proposal.targets)

    def test_a_specific_tag_refines_a_classifier_set(self):
        activity_id = self._activity(
            "Tempo",
            sheet=False,
            tags=["LT1"],
        )
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["threshold"],
            source="classifier",
        )

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["refined"])
        self.assertEqual(
            (["intervals"], ["lt1"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [("intervals", "tag", 0)],
            self._sources(activity_id),
        )
        self.assertEqual(
            [("lt1", "tag", 0)],
            [
                (row["target"], row["source"], row["is_manual"])
                for row in self.conn.execute(
                    "SELECT target, source, is_manual "
                    "FROM activity_workout_targets WHERE activity_id = ?",
                    (activity_id,),
                )
            ],
        )

    def test_a_drills_tag_is_added_to_a_classifier_set(self):
        activity_id = self._activity(
            "Intervals",
            sheet=False,
            tags=["LTT"],
        )
        self._seed_sets(
            activity_id,
            ["intervals"],
            ["other"],
            source="classifier",
        )

        with patch(CLASSIFY, return_value=INTERVALS):
            run = self._run()

        self.assertEqual(1, run.counts["additive"])
        self.assertEqual(
            (["drills", "intervals"], ["other"]),
            self._sets(activity_id),
        )
        self.assertIn(
            ("drills", "tag", 0),
            self._sources(activity_id),
        )

    def test_a_manual_set_does_not_get_drills(self):
        activity_id = self._activity(
            "Intervals",
            sheet=False,
            tags=["LTT"],
        )
        self._seed_sets(
            activity_id,
            ["intervals"],
            ["other"],
            source="manual",
            manual=True,
        )

        self._run()

        self.assertEqual(
            (["intervals"], ["other"]),
            self._sets(activity_id),
        )

    def test_a_sheet_set_gets_drills_but_keeps_its_method(self):
        activity_id = self._activity(
            "Easy",
            code="i",
            tags=["Lauftechnik"],
        )
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["base"],
            source="sheet",
        )

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["additive"])
        self.assertEqual(
            (["continuous", "drills"], ["base"]),
            self._sets(activity_id),
        )

    def test_a_comment_does_not_refine_a_classifier_set(self):
        activity_id = self._activity(
            "Tempo",
            sheet=False,
            description="Tempo run",
        )
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["threshold"],
            source="classifier",
        )

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(0, run.counts.get("refined", 0))
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_an_unmapped_or_non_workout_tag_stays_empty(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            tags=["Wienerberg", "verkühlt"],
        )

        run = self._run()

        self.assertEqual(1, run.counts["no_proposal"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_a_strength_rep_is_not_an_interval_description(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            description="Schlosspark-Stiegen +3x15 Liegestütz",
        )

        run = self._run()

        self.assertEqual(1, run.counts["no_proposal"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_marathon_pace_in_a_description_uses_the_marathon_target(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            description="7x700 Marathontempo ohne Pausen",
        )

        run = self._run()

        self.assertEqual(1, run.counts["from_comment"])
        self.assertEqual(
            (["continuous"], ["marathon"]),
            self._sets(activity_id),
        )

    def test_a_distance_rep_is_an_interval_description(self):
        activity_id = self._activity(
            "Easy",
            sheet=False,
            description="4x400m",
        )

        run = self._run()

        self.assertEqual(1, run.counts["from_comment"])
        self.assertEqual(
            (["intervals"], ["other"]),
            self._sets(activity_id),
        )

    def test_a_non_run_tag_is_not_classified(self):
        activity_id = self._activity(
            "Swim",
            sheet=False,
            sport="swim",
            tags=["progressiv"],
        )

        run = self._run()

        self.assertEqual(1, run.counts["no_proposal"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_a_tag_sourced_set_is_an_input_on_the_second_run(self):
        activity_id = self._activity("Easy", sheet=False, tags=["Longjog"])

        self._run()
        second = self._run()

        self.assertEqual(1, second.counts["already_classified"])
        self.assertEqual(0, second.counts["from_tag"])
        self.assertEqual(
            (["long_run"], ["base"]),
            self._sets(activity_id),
        )

    def test_easy_default_for_a_low_hr_sheet_run_without_a_code(self):
        activity_id = self._activity("", avg_hr=120, code="")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["base"]),
            self._sets(activity_id),
        )

    def test_high_hr_sheet_run_without_a_code_stays_empty(self):
        activity_id = self._activity("", avg_hr=150, code="")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["no_proposal"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_second_run_is_a_no_op(self):
        self._activity(sheet=False)

        with patch(CLASSIFY, return_value=TEMPO):
            self._run()
            second = self._run()

        self.assertEqual(0, second.counts["derived"])
        self.assertEqual(0, second.counts["reclassified"])
        self.assertEqual(1, second.counts["unchanged"])

    def test_dry_run_writes_nothing(self):
        activity_id = self._activity(sheet=False)

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_scope_limits_to_one_activity(self):
        first = self._activity(sheet=False)
        second = self._activity(sheet=False)

        from hobbyjogging_maintenance.context import Scope

        with patch(CLASSIFY, return_value=TEMPO):
            self._run(scope=Scope(entity_id=second))

        self.assertEqual(([], []), self._sets(first))
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(second),
        )


    def test_runalyze_type_fills_a_gap_with_runalyze_provenance(self):
        activity_id = self._activity(
            "",
            sheet=False,
            runalyze_type="SubThreshold",
        )

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["from_runalyze_type"])
        self.assertEqual(
            (["intervals"], ["subthreshold"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [
                ("intervals", "runalyze", 0),
            ],
            [
                (method, source, manual)
                for method, source, manual in self._sources(activity_id)
                if method == "intervals"
            ],
        )

    def test_an_unknown_runalyze_type_stays_empty(self):
        activity_id = self._activity(
            "",
            sheet=False,
            runalyze_type="Trail Run",
        )

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["no_proposal"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_a_classifier_proposal_wins_over_the_runalyze_type(self):
        activity_id = self._activity(
            "Tempo",
            sheet=False,
            runalyze_type="SubThreshold",
        )

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(0, run.counts["from_runalyze_type"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_a_disabled_runalyze_type_is_not_used(self):
        activity_id = self._activity(
            "",
            sheet=False,
            runalyze_type="SubThreshold",
        )
        policies = dict(default_policies())
        policy = policies["runalyze"]
        policies["runalyze"] = replace(
            policy,
            capabilities=policy.capabilities - {"workout_type"},
        )
        config = SourcesConfig(policies=policies)

        with patch(CLASSIFY, return_value=UNKNOWN), patch(
            "hobbyjogging_maintenance.recompute.workout_sets_current."
            "load_sources",
            return_value=config,
        ):
            run = self._run()

        self.assertEqual(0, run.counts["from_runalyze_type"])
        self.assertEqual(([], []), self._sets(activity_id))


if __name__ == "__main__":
    unittest.main()
