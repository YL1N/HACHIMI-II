from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loading import build_dataset  # noqa: E402


class EediStaticDataLoadingTest(unittest.TestCase):
    def test_build_small_fixed_dataset(self) -> None:
        config_path = ROOT / "configs" / "eedi_static_common_test_676x265_text_only_clean_20260520.json"
        dataset = build_dataset(
            config_path=config_path,
            history_size=30,
            max_students=4,
            max_questions=5,
        )
        self.assertEqual(len(dataset.students), 4)
        self.assertEqual(len(dataset.questions), 5)
        for question in dataset.questions.values():
            self.assertEqual(Path(question.image_path).name, f"{question.question_id}.jpg")
            self.assertTrue(Path(question.image_path).exists())
        for student in dataset.students:
            self.assertEqual(len(student.history), 30)
            self.assertEqual(len(student.test), 5)
            self.assertFalse({attempt.question_id for attempt in student.history} & set(dataset.questions))


if __name__ == "__main__":
    unittest.main()
