from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.image_direct_solve import compute_metrics, count_unresolved_failure_ids, extract_prediction_payload  # noqa: E402


class ImageDirectSolveTest(unittest.TestCase):
    def test_extracts_numeric_choice_from_json(self) -> None:
        payload = extract_prediction_payload('{"selected_answer": "3", "confidence": "high", "reason": "ok"}')

        self.assertEqual(payload["selected_answer"], "3")
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["reason"], "ok")

    def test_maps_letter_choice_to_answer_value(self) -> None:
        payload = extract_prediction_payload('{"selected_answer": "B", "confidence": "medium", "reason": "ok"}')

        self.assertEqual(payload["selected_answer"], "2")

    def test_rejects_invalid_choice(self) -> None:
        with self.assertRaises(ValueError):
            extract_prediction_payload('{"selected_answer": "E", "confidence": "low", "reason": "bad"}')

    def test_computes_direct_accuracy_metrics(self) -> None:
        rows = [
            {"question_id": "10", "gold_answer": "1", "selected_answer": "1"},
            {"question_id": "11", "gold_answer": "2", "selected_answer": "3"},
            {"question_id": "12", "gold_answer": "3", "selected_answer": "3"},
        ]

        metrics = compute_metrics(rows, n_questions=3, n_failures=1)

        self.assertEqual(metrics["n_questions"], 3)
        self.assertEqual(metrics["n_predictions"], 3)
        self.assertEqual(metrics["n_failures"], 1)
        self.assertEqual(metrics["correct"], 2)
        self.assertAlmostEqual(metrics["accuracy"], 2 / 3)
        self.assertEqual(metrics["selected_answer_counts"], {"1": 1, "3": 2})

    def test_counts_only_failures_without_later_prediction(self) -> None:
        predictions = [
            {"question_id": "1", "selected_answer": "1"},
            {"question_id": "2", "selected_answer": "2"},
        ]
        failures = [
            {"question_id": "2", "error": "temporary"},
            {"question_id": "3", "error": "still failed"},
        ]

        self.assertEqual(count_unresolved_failure_ids(predictions, failures), {"3"})


if __name__ == "__main__":
    unittest.main()
