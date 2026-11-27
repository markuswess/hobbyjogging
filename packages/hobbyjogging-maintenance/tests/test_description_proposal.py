import unittest

from hobbyjogging_maintenance.workouts import description_proposal


def _sets(text):
    proposal = description_proposal(text)
    if proposal is None:
        return None
    return sorted(proposal.methods), sorted(proposal.targets)


class DescriptionProposalTests(unittest.TestCase):

    def test_structured_interval_with_a_target_is_an_interval_session(self):
        self.assertEqual(
            (["intervals"], ["threshold"]),
            _sets("3x1.6 Threshold hopping + 4x(400+200)"),
        )
        self.assertEqual(
            (["intervals"], ["threshold"]),
            _sets("5x3x1min je M-HM-10K Tempo"),
        )

    def test_a_generic_interval_pattern_is_other_target(self):
        self.assertEqual(
            (["intervals"], ["other"]),
            _sets("12x200m in 33-35''"),
        )

    def test_marathon_pace_without_pauses_stays_continuous(self):
        self.assertEqual(
            (["continuous"], ["marathon"]),
            _sets("7x700 Marathontempo ohne Pausen"),
        )

    def test_wechseltempo_is_fartlek_not_threshold(self):
        self.assertEqual(
            (["fartlek"], []),
            _sets("Wechseltempo, ziemlich gegenwindig im Süden"),
        )

    def test_a_positive_tempo_before_statt_is_kept(self):
        self.assertEqual(
            (["continuous"], ["threshold"]),
            _sets("Tempo am Kanal statt Kabelkanal"),
        )

    def test_an_alternative_clause_is_ignored(self):
        self.assertEqual(
            (["progression"], ["base"]),
            _sets("progressiver TDL statt Wettkampfmodus"),
        )

    def test_a_negative_tempo_sentence_proposes_nothing(self):
        self.assertIsNone(_sets("zu hügelig für gleichmäßiges Tempo"))
        self.assertIsNone(_sets("not quite my tempo"))

    def test_a_negated_clause_does_not_hide_a_real_interval(self):
        self.assertEqual(
            (["intervals"], ["other"]),
            _sets("not overcooking. Mit Crew 20x400m"),
        )

    def test_recap_and_rhetorical_sentences_propose_nothing(self):
        self.assertIsNone(
            _sets(
                "2025 Highlights: - Marathon and 10k PBs - "
                "Three Peaks Bike Race win"
            )
        )
        self.assertIsNone(
            _sets("train your weaknesses - race your weaknesses?")
        )

    def test_race_atmosphere_is_not_a_race_method(self):
        self.assertIsNone(
            _sets(
                "endlich wieder Wettkampfluft schnuppern... 10km im MT"
            )
        )

    def test_compound_tempo_words_need_a_real_target(self):
        self.assertIsNone(_sets("Wohlfühltempo, wie manche sagen"))
        self.assertEqual(
            (["continuous"], ["threshold"]),
            _sets("Tempogefühl schulen"),
        )
        self.assertEqual(
            (["continuous"], ["threshold"]),
            _sets("Tempospielereien am Kanal"),
        )


if __name__ == "__main__":
    unittest.main()
