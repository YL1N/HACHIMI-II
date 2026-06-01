import unittest

from correct_paired_judge_results import correct_row, summarize_rows


class CorrectPairedJudgeResultsTest(unittest.TestCase):
    def test_equivalent_answer_is_not_codable_error(self):
        row = {
            "real_function": "incorrect",
            "candidate_function": "correct",
            "real_response_type": "answers_request",
            "candidate_response_type": "answers_request",
            "real_satisfies_criterion": False,
            "candidate_satisfies_criterion": True,
            "real_has_codable_error": True,
            "candidate_has_codable_error": False,
            "real_knowledge_type": "procedural",
            "real_error_locus": "encoding",
            "real_error_mechanism": "incorrect_associations",
            "candidate_knowledge_type": None,
            "candidate_error_locus": None,
            "candidate_error_mechanism": None,
            "real_evidence": (
                "Student answered 1, but 3/8 + 5/8 = 8/8 = 1; "
                "answer is correct in value but not in expected fraction form."
            ),
            "candidate_evidence": "Student answered 8/8 correctly.",
        }

        corrected = correct_row(row)

        self.assertEqual(corrected["real_function"], "correct")
        self.assertIs(corrected["real_has_codable_error"], False)
        self.assertIsNone(corrected["real_knowledge_type"])
        self.assertIn("real:equivalent_or_correct_value", corrected["correction_reasons"])

    def test_final_answer_instead_of_step_is_not_codable_error(self):
        row = {
            "real_function": "incorrect",
            "candidate_function": "correct",
            "real_response_type": "answers_request",
            "candidate_response_type": "answers_request",
            "real_satisfies_criterion": False,
            "candidate_satisfies_criterion": True,
            "real_has_codable_error": True,
            "candidate_has_codable_error": False,
            "real_knowledge_type": "procedural",
            "real_error_locus": "transformation",
            "real_error_mechanism": "incorrect_associations",
            "candidate_knowledge_type": None,
            "candidate_error_locus": None,
            "candidate_error_mechanism": None,
            "real_evidence": "Student gave the final answer instead of the requested first step.",
            "candidate_evidence": "Student correctly identified the first step.",
        }

        corrected = correct_row(row)

        self.assertEqual(corrected["real_function"], "incorrect")
        self.assertIs(corrected["real_has_codable_error"], False)
        self.assertIsNone(corrected["real_knowledge_type"])
        self.assertIn(
            "real:local_protocol_mismatch_not_codable_math_error",
            corrected["correction_reasons"],
        )

    def test_summary_uses_corrected_codable_fields(self):
        rows = [
            {
                "mode": "simulation",
                "real_function": "incorrect",
                "candidate_function": "incorrect",
                "same_function": True,
                "real_has_codable_error": True,
                "candidate_has_codable_error": True,
                "both_have_codable_error": True,
                "same_knowledge": True,
                "same_locus": False,
                "same_mechanism": True,
            },
            {
                "mode": "simulation",
                "real_function": "incorrect",
                "candidate_function": "correct",
                "same_function": False,
                "real_has_codable_error": True,
                "candidate_has_codable_error": False,
                "both_have_codable_error": False,
                "same_knowledge": None,
                "same_locus": None,
                "same_mechanism": None,
            },
        ]

        summary = summarize_rows(rows)

        self.assertEqual(summary["by_mode"]["simulation"]["real_codable_error_n"], 2)
        self.assertEqual(summary["by_mode"]["simulation"]["both_codable_error_n"], 1)
        self.assertEqual(summary["by_mode"]["simulation"]["error_realization_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
