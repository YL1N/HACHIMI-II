from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loading import EediStaticAttempt, EediStaticStudent  # noqa: E402
from src.hachimi import (  # noqa: E402
    build_eedi_observed_profile,
    load_hachimi_personas,
    rank_hachimi_candidates,
    select_hachimi_match_with_llm,
)
from src.static_chain import build_student_model  # noqa: E402


def make_attempt(question_id: str, subject_leaf: str, is_correct: bool) -> EediStaticAttempt:
    return EediStaticAttempt(
        question_id=question_id,
        answer_id=f"a{question_id}",
        answer_value="1",
        correct_answer="1",
        is_correct=is_correct,
        subject_leaf=subject_leaf,
        date_answered=f"2020-01-{int(question_id):02d}",
    )


def make_student() -> EediStaticStudent:
    return EediStaticStudent(
        student_id="s1",
        ability_level="high",
        ability_score_proxy=0.82,
        history=[
            make_attempt("1", "Angles", True),
            make_attempt("2", "Angles", True),
            make_attempt("3", "Algebraic Expressions", False),
            make_attempt("4", "Negative Numbers", True),
        ],
        test=[],
        age_floor=12,
        age_group="12",
    )


def write_hachimi_file(path: Path) -> None:
    rows = [
        {
            "id": 101,
            "姓名": "高数同学",
            "年龄": 12,
            "性别": "女",
            "年级": "六年级",
            "发展阶段": {"皮亚杰认知发展阶段": "具体运算阶段"},
            "代理名": "gao1_shu4",
            "擅长科目": ["数学", "科学"],
            "薄弱科目": ["英语"],
            "学术水平": "高：成绩全校排名前10%",
            "人格": "完整人格文本：自信，愿意挑战数学难题，会主动复盘。",
            "价值观": "完整价值观文本：重视规则和责任。",
            "社交关系": "完整社交文本：能和同学讨论解题。",
            "创造力": "完整创造力文本：会尝试多种解法。",
            "心理健康": "完整心理健康文本：遇到错题能恢复。",
            "_采样约束": {"年级": "六年级", "目标学术水平": "高"},
        },
        {
            "id": 202,
            "姓名": "低数同学",
            "年龄": 12,
            "性别": "男",
            "年级": "六年级",
            "发展阶段": {"皮亚杰认知发展阶段": "具体运算阶段"},
            "代理名": "di1_shu4",
            "擅长科目": ["语文"],
            "薄弱科目": ["数学"],
            "学术水平": "差：成绩全校排名后50%",
            "人格": "容易回避数学挑战。",
            "价值观": "需要外部鼓励。",
            "社交关系": "较少讨论数学。",
            "创造力": "解法较固定。",
            "心理健康": "遇到学业压力容易紧张。",
            "_采样约束": {"年级": "六年级", "目标学术水平": "差"},
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


class RecordingMatcherLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat_json(self, _system_prompt: str, user_prompt: str) -> dict[str, object]:
        self.prompts.append(user_prompt)
        return {
            "selected_hachimi_id": "101",
            "match_evidence": [
                "EEDI observed profile is high on Angles and the full HACHIMI persona shows confident math persistence.",
            ],
            "conflict_evidence": [
                "EEDI math history remains the authority if HACHIMI affective priors overstate ability.",
            ],
            "fusion_rule": (
                "Use EEDI non-test math history for math capability; use the full raw HACHIMI persona "
                "for affect, learning style, social expression, creativity, mental health, and response style."
            ),
        }


class RecordingStudentModelLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat_json(self, _system_prompt: str, user_prompt: str) -> dict[str, object]:
        self.prompts.append(user_prompt)
        return {
            "academic_level": "high",
            "weak_subjects": ["Algebraic Expressions"],
            "strong_subjects": ["Angles"],
            "self_efficacy_analysis": {
                "efficacy_belief_description": "confident but not perfect",
                "efficacy_belief_evidence": ["EEDI history and HACHIMI both show persistence"],
            },
            "srl_analysis": {
                "primary_srl_vulnerability": "may rush familiar-looking items",
                "srl_process_evidence": ["HACHIMI reflection evidence is available"],
            },
            "control_value_analysis": {
                "control_appraisal_description": "mostly feels in control",
                "value_appraisal_description": "values math tasks",
                "control_value_evidence": ["raw HACHIMI value text was supplied"],
            },
            "engagement_level_tendency": "high",
            "engagement_evidence": ["history and HACHIMI match"],
            "response_directness_description": "direct",
            "response_directness_evidence": ["HACHIMI expression prior"],
            "raw_summary": "fused from EEDI observed history and raw HACHIMI persona",
            "math_task_capability_profile": {
                "arithmetic_fluency": "high",
                "word_problem_transfer": "medium",
                "multi_step_stability": "medium",
                "geometry_intuition": "high",
                "pattern_rule_detection": "medium",
                "option_elimination": "high",
                "hard_item_persistence": "high",
                "guessing_tendency": "low",
                "confidence_calibration": "medium",
                "format_discipline": "high",
                "common_error_families": ["symbol manipulation slip"],
                "capability_evidence": ["EEDI observed profile overrides conflicts"],
            },
        }


class HachimiProfileFusionTest(unittest.TestCase):
    def test_llm_matcher_receives_full_candidate_profiles_and_preserves_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "hachimi.jsonl"
            write_hachimi_file(path)

            personas = load_hachimi_personas([path])
            observed = build_eedi_observed_profile(make_student(), age=12)
            candidates = rank_hachimi_candidates(observed, personas, top_k=2)
            llm = RecordingMatcherLLM()
            match = select_hachimi_match_with_llm(observed, candidates, llm)  # type: ignore[arg-type]

        prompt = llm.prompts[0]
        self.assertEqual(match.hachimi_id, "101")
        self.assertEqual(match.matcher_version, "llm_profile_matcher_v1")
        self.assertEqual(match.candidate_hachimi_ids, ["101", "202"])
        self.assertEqual(match.raw_hachimi_persona["人格"], "完整人格文本：自信，愿意挑战数学难题，会主动复盘。")
        self.assertIn("candidate_hachimi_profiles", prompt)
        self.assertIn("raw_hachimi_persona", prompt)
        self.assertIn("hachimi_profile_card", prompt)
        self.assertIn("完整人格文本", prompt)
        self.assertIn("完整价值观文本", prompt)
        self.assertIn("完整社交文本", prompt)
        self.assertIn("完整创造力文本", prompt)
        self.assertIn("完整心理健康文本", prompt)

    def test_student_model_prompt_receives_selected_raw_hachimi_and_fusion_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "hachimi.jsonl"
            write_hachimi_file(path)
            personas = load_hachimi_personas([path])
            observed = build_eedi_observed_profile(make_student(), age=12)
            candidates = rank_hachimi_candidates(observed, personas, top_k=2)
            match = select_hachimi_match_with_llm(observed, candidates, RecordingMatcherLLM())  # type: ignore[arg-type]

        llm = RecordingStudentModelLLM()
        model = build_student_model(make_student(), llm, hachimi_match=match)  # type: ignore[arg-type]
        prompt = llm.prompts[0]

        self.assertEqual(model.matched_hachimi_id, "101")
        self.assertIn("raw_hachimi_persona", prompt)
        self.assertIn("hachimi_profile_card", prompt)
        self.assertIn("fusion_rule", prompt)
        self.assertIn("完整人格文本", prompt)
        self.assertIn("完整价值观文本", prompt)
        self.assertIn("完整社交文本", prompt)
        self.assertIn("完整创造力文本", prompt)
        self.assertIn("完整心理健康文本", prompt)


if __name__ == "__main__":
    unittest.main()
