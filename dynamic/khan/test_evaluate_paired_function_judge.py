import unittest

from evaluate_paired_function_judge import (
    build_simulation_pairs_from_prediction_rows,
    parse_pair_judgment,
)


class PairedFunctionJudgeParserTest(unittest.TestCase):
    def test_rejects_function_label_that_conflicts_with_structured_decision(self):
        payload = {
            "tutor_request_type": "math_intermediate_step",
            "requested_local_criterion": "25 times 4 equals 100",
            "real_response_type": "answers_request",
            "candidate_response_type": "answers_request",
            "real_satisfies_criterion": True,
            "candidate_satisfies_criterion": True,
            "real_function": "incorrect",
            "candidate_function": "correct",
            "real_has_codable_error": False,
            "candidate_has_codable_error": False,
            "real_knowledge_type": None,
            "candidate_knowledge_type": None,
            "real_error_locus": None,
            "candidate_error_locus": None,
            "real_error_mechanism": None,
            "candidate_error_mechanism": None,
            "real_evidence": "The real answer satisfies the requested intermediate multiplication.",
            "candidate_evidence": "The candidate answer satisfies the requested intermediate multiplication.",
        }

        with self.assertRaises(ValueError):
            parse_pair_judgment(payload)

    def test_builds_simulation_pair_from_prediction_record(self):
        rows = [
            {
                "dialogue_id": "khan_1",
                "question_id": "1",
                "turn_idx": 2,
                "subjects": [["Khan math level: Elementary", 0]],
                "history": [
                    {"role": "student", "content": "I need help."},
                    {"role": "tutor", "content": "What is 0.2 times 0.3?"},
                ],
                "gt_turn": "0.6",
                "pred_turn": "I think it is 0.6?",
            }
        ]

        pairs = build_simulation_pairs_from_prediction_rows(rows)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["mode"], "simulation")
        self.assertEqual(pairs[0]["candidate_turn"], "I think it is 0.6?")
        self.assertEqual(pairs[0]["sample"].sample_id, "khan_1_turn_2")
        self.assertEqual(pairs[0]["sample"].math_level, "Elementary")
        self.assertEqual(pairs[0]["sample"].history[-1]["role"], "assistant")
        self.assertEqual(pairs[0]["sample"].gt_student_turn, "0.6")

    def test_accepts_empty_local_criterion_for_non_math_turn(self):
        payload = {
            "tutor_request_type": "non_math",
            "requested_local_criterion": "",
            "real_response_type": "social_or_preference",
            "candidate_response_type": "says_dont_know",
            "real_satisfies_criterion": None,
            "candidate_satisfies_criterion": None,
            "real_function": "na",
            "candidate_function": "na",
            "real_has_codable_error": False,
            "candidate_has_codable_error": False,
            "real_knowledge_type": None,
            "candidate_knowledge_type": None,
            "real_error_locus": None,
            "candidate_error_locus": None,
            "real_error_mechanism": None,
            "candidate_error_mechanism": None,
            "real_evidence": "The tutor only asked what the student wants to practice next.",
            "candidate_evidence": "The tutor only asked what the student wants to practice next.",
        }

        judgment = parse_pair_judgment(payload)

        self.assertEqual(judgment["requested_local_criterion"], "none")
        self.assertEqual(judgment["real_function"], "na")
        self.assertEqual(judgment["candidate_function"], "na")

    def test_accepts_function_label_even_when_evidence_is_imperfect(self):
        payload = {
            "tutor_request_type": "math_final_answer",
            "requested_local_criterion": "value of 3/8 + 5/8",
            "real_response_type": "answers_request",
            "candidate_response_type": "says_dont_know",
            "real_satisfies_criterion": False,
            "candidate_satisfies_criterion": None,
            "real_function": "incorrect",
            "candidate_function": "incorrect",
            "real_has_codable_error": False,
            "candidate_has_codable_error": False,
            "real_knowledge_type": None,
            "candidate_knowledge_type": None,
            "real_error_locus": None,
            "candidate_error_locus": None,
            "real_error_mechanism": None,
            "candidate_error_mechanism": None,
            "real_evidence": "The student gave the correct value but not in fraction form.",
            "candidate_evidence": "The candidate says they do not know.",
        }

        judgment = parse_pair_judgment(payload)

        self.assertEqual(judgment["real_function"], "incorrect")

    def test_accepts_social_preference_as_na_even_with_mixed_tutor_move(self):
        payload = {
            "tutor_request_type": "math_explanation",
            "requested_local_criterion": "whether to continue practicing or ask another question",
            "real_response_type": "social_or_preference",
            "candidate_response_type": "social_or_preference",
            "real_satisfies_criterion": False,
            "candidate_satisfies_criterion": False,
            "real_function": "na",
            "candidate_function": "na",
            "real_has_codable_error": False,
            "candidate_has_codable_error": False,
            "real_knowledge_type": None,
            "candidate_knowledge_type": None,
            "real_error_locus": None,
            "candidate_error_locus": None,
            "real_error_mechanism": None,
            "candidate_error_mechanism": None,
            "real_evidence": "The real turn is a preference-style continuation, not a math answer.",
            "candidate_evidence": "The candidate asks to try another problem, not a math answer.",
        }

        judgment = parse_pair_judgment(payload)

        self.assertEqual(judgment["real_function"], "na")
        self.assertEqual(judgment["candidate_function"], "na")
        self.assertIsNone(judgment["real_satisfies_criterion"])
        self.assertIsNone(judgment["candidate_satisfies_criterion"])

    def test_accepts_non_answer_to_math_request_as_incorrect(self):
        payload = {
            "tutor_request_type": "math_final_answer",
            "requested_local_criterion": "compute the local answer",
            "real_response_type": "social_or_preference",
            "candidate_response_type": "answers_request",
            "real_satisfies_criterion": False,
            "candidate_satisfies_criterion": True,
            "real_function": "incorrect",
            "candidate_function": "correct",
            "real_has_codable_error": False,
            "candidate_has_codable_error": False,
            "real_knowledge_type": None,
            "candidate_knowledge_type": None,
            "real_error_locus": None,
            "candidate_error_locus": None,
            "real_error_mechanism": None,
            "candidate_error_mechanism": None,
            "real_evidence": "The real turn avoids the requested math answer.",
            "candidate_evidence": "The candidate gives the requested answer.",
        }

        judgment = parse_pair_judgment(payload)

        self.assertEqual(judgment["real_function"], "incorrect")
        self.assertIsNone(judgment["real_satisfies_criterion"])


if __name__ == "__main__":
    unittest.main()
