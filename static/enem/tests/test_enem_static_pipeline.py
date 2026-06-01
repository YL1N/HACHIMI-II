from __future__ import annotations

import sys
import tempfile
import unittest
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))


class EnemStaticPipelineTest(unittest.TestCase):
    def test_student_model_retries_invalid_empty_skill_lists(self) -> None:
        from src.data_loading import EnemAttempt, EnemStaticStudent
        from src.science_chain import build_student_model

        class FakeLLM:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
                self.calls.append(user_prompt)
                capability = {
                    "scientific_concept_recall": "low",
                    "phenomenon_explanation": "low",
                    "mechanism_reasoning": "low",
                    "data_evidence_interpretation": "low",
                    "model_representation_transfer": "low",
                    "scientific_inquiry_reasoning": "low",
                    "science_technology_society_reasoning": "low",
                    "quantitative_science_reasoning": "low",
                    "option_elimination": "low",
                    "hard_item_persistence": "low",
                    "guessing_tendency": "high",
                    "confidence_calibration": "medium",
                    "format_discipline": "high",
                    "common_error_families": ["weak_physics_reasoning"],
                    "capability_evidence": ["history_accuracy=0.500"],
                }
                if len(self.calls) == 1:
                    return {
                        "weak_skill_areas": ["physics_reasoning"],
                        "strong_skill_areas": [],
                        "raw_summary": "invalid because strong list is empty",
                        "science_task_capability_profile": capability,
                    }
                return {
                    "weak_skill_areas": ["physics_reasoning"],
                    "strong_skill_areas": ["biology_reasoning"],
                    "raw_summary": "repaired with a relative observed strength",
                    "science_task_capability_profile": capability,
                }

        history = [
            EnemAttempt("Q1", "CN", 91, "A", "A", True, "H1", "biology_reasoning", "1419"),
            EnemAttempt("Q2", "CN", 92, "B", "C", False, "H2", "physics_reasoning", "1419"),
        ]
        student = EnemStaticStudent(
            student_id="s1",
            target_area="CN",
            ability_level="low",
            ability_score_proxy=0.5,
            history_accuracy=0.5,
            history=history,
            test=[],
        )

        fake_llm = FakeLLM()
        model = build_student_model(student, fake_llm)  # type: ignore[arg-type]

        self.assertEqual(model.strong_skill_areas, ["biology_reasoning"])
        self.assertEqual(len(fake_llm.calls), 2)
        self.assertIn("previous StudentModel JSON failed schema validation", fake_llm.calls[1])

    def test_student_model_retries_invalid_enum_values_until_valid(self) -> None:
        from src.data_loading import EnemAttempt, EnemStaticStudent
        from src.science_chain import build_student_model

        class FakeLLM:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
                self.calls.append(user_prompt)
                capability = {
                    "scientific_concept_recall": "low",
                    "phenomenon_explanation": "low",
                    "mechanism_reasoning": "variable" if len(self.calls) == 1 else "low_to_medium" if len(self.calls) == 2 else "medium",
                    "data_evidence_interpretation": "low",
                    "model_representation_transfer": "low",
                    "scientific_inquiry_reasoning": "low",
                    "science_technology_society_reasoning": "low",
                    "quantitative_science_reasoning": "low",
                    "option_elimination": "low",
                    "hard_item_persistence": "low",
                    "guessing_tendency": "high",
                    "confidence_calibration": "medium",
                    "format_discipline": "high",
                    "common_error_families": ["weak_physics_reasoning"],
                    "capability_evidence": ["history_accuracy=0.500"],
                }
                return {
                    "weak_skill_areas": ["physics_reasoning"],
                    "strong_skill_areas": ["biology_reasoning"],
                    "raw_summary": "student model under repair",
                    "science_task_capability_profile": capability,
                }

        history = [
            EnemAttempt("Q1", "CN", 91, "A", "A", True, "H1", "biology_reasoning", "1419"),
            EnemAttempt("Q2", "CN", 92, "B", "C", False, "H2", "physics_reasoning", "1419"),
        ]
        student = EnemStaticStudent(
            student_id="s1",
            target_area="CN",
            ability_level="low",
            ability_score_proxy=0.5,
            history_accuracy=0.5,
            history=history,
            test=[],
        )

        fake_llm = FakeLLM()
        model = build_student_model(student, fake_llm)  # type: ignore[arg-type]

        self.assertEqual(model.science_task_capability_profile.mechanism_reasoning, "medium")
        self.assertEqual(len(fake_llm.calls), 3)
        self.assertIn("Allowed capability level values", fake_llm.calls[1])

    def test_cn_matrix_uses_official_skill_structure(self) -> None:
        from src.enem_matrix import science_competency_for_skill, science_skill_code

        self.assertEqual(science_skill_code(1), "H1")
        self.assertEqual(science_skill_code("30"), "H30")
        self.assertEqual(science_competency_for_skill(1).competency_id, 1)
        self.assertEqual(science_competency_for_skill(30).competency_id, 8)

    def test_cn_item_bank_and_history_split(self) -> None:
        from src.data_loading import load_area_item_bank, split_history_test_items

        dataset_root = ROOT / "enem2024"
        item_bank = load_area_item_bank(dataset_root=dataset_root, area="CN")
        self.assertEqual(len(item_bank.common_items), 44)
        self.assertEqual(set(item_bank.regular_codes), {"1419", "1420", "1421", "1422"})

        history_ids, test_ids = split_history_test_items(
            items=list(item_bank.common_items.values()),
            history_size=20,
            seed=42,
        )
        self.assertEqual(len(history_ids), 20)
        self.assertEqual(len(test_ids), 24)
        self.assertFalse(set(history_ids) & set(test_ids))
        self.assertEqual(set(history_ids) | set(test_ids), set(item_bank.common_items))

    def test_cn_item_bank_can_attach_translated_question_text(self) -> None:
        from src.data_loading import load_area_item_bank

        dataset_root = ROOT / "enem2024"
        item_bank = load_area_item_bank(
            dataset_root=dataset_root,
            area="CN",
            text_manifest={"84075": {"question_text": "Question 91 in English.", "question_text_language": "en"}},
        )

        self.assertEqual(item_bank.common_items["84075"].question_text, "Question 91 in English.")
        self.assertEqual(item_bank.common_items["84075"].question_text_language, "en")

    def test_science_capability_profile_has_no_math_specific_fields(self) -> None:
        from src.science_chain import ScienceTaskCapabilityProfile

        fields = set(ScienceTaskCapabilityProfile.__annotations__)
        forbidden = {
            "arithmetic_fluency",
            "geometry_intuition",
            "pattern_rule_detection",
            "fill_blank_precision",
            "math_anchor_profile_summary",
        }
        self.assertFalse(fields & forbidden)
        self.assertIn("phenomenon_explanation", fields)
        self.assertIn("scientific_inquiry_reasoning", fields)
        self.assertIn("data_evidence_interpretation", fields)

    def test_question_crop_plan_uses_column_bounding_boxes(self) -> None:
        from src.data_loading import load_area_item_bank
        from src.question_images import build_question_crop_plan, find_booklet_pdf

        dataset_root = ROOT / "enem2024"
        item_bank = load_area_item_bank(dataset_root=dataset_root, area="CN")
        pdf_path = find_booklet_pdf(dataset_root, "CN", item_bank.base_booklet_code)
        crop_plan = build_question_crop_plan(pdf_path, item_bank)

        self.assertEqual(len(crop_plan), 44)
        q91 = next(row for row in crop_plan if row.question_number == 91)
        q92 = next(row for row in crop_plan if row.question_number == 92)
        self.assertEqual(q91.page_number, 2)
        self.assertEqual(q91.column, "left")
        self.assertLess(q91.crop_box[2], 340)
        self.assertEqual(q92.page_number, 2)
        self.assertEqual(q92.column, "right")
        self.assertGreater(q92.crop_box[0], 290)
        self.assertLess(q92.crop_box[3], q92.page_height)
        q135 = next(row for row in crop_plan if row.question_number == 135)
        self.assertEqual(q135.page_number, 15)
        self.assertEqual(q135.column, "full_width")
        self.assertLess(q135.crop_box[0], 70)
        self.assertGreater(q135.crop_box[2], 560)

    def test_question_image_manifest_points_to_cropped_images(self) -> None:
        from src.data_loading import load_area_item_bank
        from src.question_images import build_question_page_manifest

        dataset_root = ROOT / "enem2024"
        item_bank = load_area_item_bank(dataset_root=dataset_root, area="CN")
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_path = Path(tmp_dir) / "manifest.jsonl"
            rows = build_question_page_manifest(
                dataset_root=dataset_root,
                item_bank=item_bank,
                output_path=manifest_path,
                page_image_dir=Path(tmp_dir) / "pages",
                dpi=72,
            )
            q91 = next(row for row in rows if row["item_position"] == 91)
            self.assertEqual(q91["crop_mode"], "bbox_column_crop_v1")
            self.assertEqual(q91["page_number"], 2)
            self.assertEqual(q91["column"], "left")
            self.assertIn("crop_box", q91)
            self.assertTrue(Path(str(q91["image_path"])).exists())

    def test_existing_question_image_manifest_reuses_cached_crops(self) -> None:
        from src.data_loading import load_area_item_bank
        from src.question_images import build_question_page_manifest

        dataset_root = ROOT / "enem2024"
        item_bank = load_area_item_bank(dataset_root=dataset_root, area="CN")
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_path = Path(tmp_dir) / "manifest.jsonl"
            page_dir = Path(tmp_dir) / "pages"
            rows = build_question_page_manifest(
                dataset_root=dataset_root,
                item_bank=item_bank,
                output_path=manifest_path,
                page_image_dir=page_dir,
                dpi=72,
            )
            q91 = next(row for row in rows if row["item_position"] == 91)
            crop_path = Path(str(q91["image_path"]))
            fixed_time = 1_700_000_000
            os.utime(crop_path, (fixed_time, fixed_time))

            reused_rows = build_question_page_manifest(
                dataset_root=dataset_root,
                item_bank=item_bank,
                output_path=manifest_path,
                page_image_dir=page_dir,
                dpi=72,
            )

            reused_q91 = next(row for row in reused_rows if row["item_position"] == 91)
            self.assertEqual(Path(str(reused_q91["image_path"])), crop_path)
            self.assertEqual(int(crop_path.stat().st_mtime), fixed_time)


if __name__ == "__main__":
    unittest.main()
