import unittest
from pathlib import Path

from run_khan_experiments import (
    KHAN_NO_ANCHORED_QUESTION_TEXT,
    load_khan_turn_prediction_tasks,
)


class KhanExperimentAdapterTest(unittest.TestCase):
    def test_converts_khan_dialogue_to_eedi_shaped_turn_task(self):
        dataset_path = Path(__file__).resolve().parent / "CoMTA_dataset.json"

        tasks, ground_truth = load_khan_turn_prediction_tasks(
            dataset_path=dataset_path,
            max_dialogues=1,
        )

        first_task = tasks[0]
        self.assertEqual(first_task.dialogue_id, "khan_1")
        self.assertEqual(first_task.question_id, "1")
        self.assertEqual(first_task.intervention_id, "khan")
        self.assertEqual(first_task.question_text, KHAN_NO_ANCHORED_QUESTION_TEXT)
        self.assertEqual(first_task.subjects, [("Khan math level: Elementary", 0)])
        self.assertEqual(first_task.target_turn_index, 2)
        self.assertEqual(first_task.history[-1].role, "tutor")
        self.assertEqual(ground_truth[("khan_1", 2)], "0.6")


if __name__ == "__main__":
    unittest.main()
