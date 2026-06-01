from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loading import MathAnchorProfile, PersonaRecord  # noqa: E402
from src.student_conditioned_benchmark import (  # noqa: E402
    HistorySummary,
    attach_personas_to_rows_with_optional_llm,
    rank_persona_candidates,
    select_persona_match_with_llm,
)


def make_summary() -> HistorySummary:
    return HistorySummary(
        student_id="xes_s1",
        total_history_items=30,
        history_accuracy=0.2,
        easy_accuracy=None,
        medium_accuracy=None,
        hard_accuracy=None,
        module_accuracy={"整数计算": 0.2, "图形": 0.0},
        type_accuracy={"填空题": 0.2},
        answer_format_accuracy={"numeric": 0.2},
        capability_metric_accuracy={"arithmetic_fluency": 0.2},
        history_level="poor",
        history_level_percentile=0.1,
        within_level_strength="below_level_average",
        guessed_error_tendencies=["计算不稳定", "容易猜测"],
    )


def make_persona(persona_id: str, text: str, level: str = "poor") -> PersonaRecord:
    return PersonaRecord(
        student_id=persona_id,
        grade="三年级",
        academic_level=level,
        strong_subjects=["数学"],
        weak_subjects=["语文"],
        learning_profile_text=text,
        math_anchor_profile=MathAnchorProfile(
            anchor_student_id=persona_id,
            support_item_count=10,
            support_accuracy=0.2,
            support_accuracy_percentile_within_level=0.1,
            support_level=level,
            within_level_strength="below_level_average",
            easy_accuracy=None,
            medium_accuracy=None,
            hard_accuracy=None,
            summary="HACHIMI anchor summary",
            evidence=["anchor evidence"],
            excluded_question_count=0,
        ),
        math_task_capability_anchor=None,
        raw_persona={
            "id": persona_id,
            "姓名": "测试画像",
            "人格": text,
            "价值观": "完整价值观字段",
            "社交关系": "完整社交关系字段",
            "创造力": "完整创造力字段",
            "心理健康": "完整心理健康字段",
        },
    )


class RecordingMatcherLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat_json(self, system_prompt: str, user_prompt: str, **_kwargs) -> dict[str, object]:
        self.prompts.append(system_prompt + "\n" + user_prompt)
        return {
            "selected_persona_id": "p1",
            "match_evidence": ["完整画像和 XES 历史都显示低自信与数学脆弱"],
            "conflict_evidence": ["HACHIMI 写数学擅长，但 XES 历史正确率很低"],
            "fusion_rule": "XES 历史决定数学能力，HACHIMI 补充学习风格、情绪和表达。",
        }


class XesPersonaLLMMatchTest(unittest.TestCase):
    def test_llm_matcher_receives_full_candidate_personas(self) -> None:
        summary = make_summary()
        personas = [
            make_persona("p1", "完整人格文本：退缩、焦虑、低自信，但愿意完成任务。"),
            make_persona("p2", "完整人格文本：外向、稳定、自信。", level="high"),
        ]
        candidates = rank_persona_candidates(summary, personas, top_k=2)
        llm = RecordingMatcherLLM()
        match = select_persona_match_with_llm(summary, candidates, llm)  # type: ignore[arg-type]

        prompt = llm.prompts[0]
        self.assertEqual(match.persona.student_id, "p1")
        self.assertEqual(match.matcher_version, "llm_profile_matcher_v1")
        self.assertEqual(match.candidate_persona_ids, ["p1", "p2"])
        self.assertIn("xes_observed_profile", prompt)
        self.assertIn("candidate_hachimi_profiles", prompt)
        self.assertIn("完整人格文本：退缩、焦虑、低自信", prompt)
        self.assertIn("完整价值观字段", prompt)
        self.assertIn("完整社交关系字段", prompt)
        self.assertIn("完整创造力字段", prompt)
        self.assertIn("完整心理健康字段", prompt)
        self.assertIn("XES 历史决定数学能力", match.fusion_rule)

    def test_attach_personas_uses_llm_match_for_final_selection(self) -> None:
        summary = make_summary()
        llm = RecordingMatcherLLM()
        students = attach_personas_to_rows_with_optional_llm(
            selected_rows=[("xes_s1", [("q1", True)], [("q2", False)])],
            history_summaries={"xes_s1": summary},
            candidate_personas=[
                make_persona("p1", "完整人格文本：退缩、焦虑、低自信。"),
                make_persona("p2", "完整人格文本：外向、稳定、自信。", level="high"),
            ],
            persona_source_mode="xes_history_plus_hachimi",
            llm_client=llm,  # type: ignore[arg-type]
        )

        self.assertEqual(students[0].matched_persona_id, "p1")
        self.assertIn("XES 历史决定数学能力", students[0].enhanced_persona.learning_profile_text)
        self.assertIn("完整人格文本：退缩", llm.prompts[0])


if __name__ == "__main__":
    unittest.main()
