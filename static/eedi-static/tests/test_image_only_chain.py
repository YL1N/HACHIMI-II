from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loading import EediStaticQuestion, EediStaticStudent  # noqa: E402
from src.llm_client import LLMConfig, OpenAICompatClient  # noqa: E402
from src.static_chain import (  # noqa: E402
    ConstraintBundle,
    ControlValueAnalysis,
    ItemResponseState,
    MathTaskCapabilityProfile,
    ProblemRequirementProfile,
    SRLAnalysis,
    SelfEfficacyAnalysis,
    StudentInternalSignals,
    StudentItemInteractionDecision,
    StudentModel,
    build_problem_profile,
    generate_prediction,
)


OCR_SENTINEL = "OCR_TEXT_MUST_NOT_APPEAR"


class RecordingVisionLLM:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.image_calls: list[tuple[str, str]] = []

    def chat_json_with_image(self, _system_prompt: str, user_prompt: str, image_path: str) -> dict[str, object]:
        self.image_calls.append((user_prompt, image_path))
        if not self.responses:
            raise AssertionError("RecordingVisionLLM received more calls than expected")
        return self.responses.pop(0)


def make_question() -> EediStaticQuestion:
    return EediStaticQuestion(
        question_id="39",
        question_text=OCR_SENTINEL,
        image_path="raw_data/data/images/39.jpg",
        ocr_answer="2",
        subject_names=["Maths", "Geometry and Measure"],
        subject_top="Geometry and Measure",
        subject_leaf="Angle Facts with Parallel Lines",
        empirical_accuracy=0.0,
        all_train_response_count=0,
    )


def make_student_model() -> StudentModel:
    return StudentModel(
        student_id="s1",
        grade="unknown",
        academic_level="medium",
        weak_subjects=["geometry"],
        strong_subjects=["number"],
        self_efficacy_analysis=SelfEfficacyAnalysis(
            efficacy_belief_description="moderate confidence",
            efficacy_belief_evidence=["history shows mixed results"],
        ),
        srl_analysis=SRLAnalysis(
            primary_srl_vulnerability="rushes visual items",
            srl_process_evidence=["short responses"],
        ),
        control_value_analysis=ControlValueAnalysis(
            control_appraisal_description="visual items feel less controllable",
            value_appraisal_description="values concrete tasks",
            control_value_evidence=["synthetic"],
        ),
        engagement_level_tendency="medium",
        engagement_evidence=["synthetic"],
        response_directness_description="brief",
        response_directness_evidence=["synthetic"],
        raw_summary="synthetic",
        math_anchor_profile_summary="synthetic",
        math_anchor_profile_evidence=["synthetic"],
        math_task_capability_profile=MathTaskCapabilityProfile(
            arithmetic_fluency="medium",
            word_problem_transfer="low",
            multi_step_stability="low",
            geometry_intuition="low",
            pattern_rule_detection="medium",
            option_elimination="low",
            hard_item_persistence="low",
            guessing_tendency="medium",
            confidence_calibration="low",
            format_discipline="medium",
            common_error_families=["visual angle confusion"],
            capability_evidence=["synthetic"],
        ),
    )


class ImageOnlyChainTest(unittest.TestCase):
    def test_vision_payload_disables_thinking_and_uses_image_content(self) -> None:
        client = OpenAICompatClient(
            LLMConfig(
                base_url="https://example.test/v1",
                model="vision-model",
                api_key="secret",
            )
        )

        payload = client.build_chat_payload(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Use image only."},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
                    ],
                }
            ]
        )

        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(payload["messages"][0]["content"][1]["type"], "image_url")

    def test_problem_profile_uses_image_without_ocr_text(self) -> None:
        llm = RecordingVisionLLM(
            [
                {
                    "prerequisite_knowledge": ["parallel line angle facts"],
                    "operation_complexity": "medium",
                    "operation_complexity_justification": "requires visual angle relation reading",
                    "abstraction_level": "medium",
                    "abstraction_level_justification": "diagram to option mapping",
                    "knowledge_integration_demand": "single visual geometry concept",
                    "representation_shift_required": "image_diagram_to_option",
                    "response_format_demand": "choose_one_of_1_2_3_4",
                    "guessability": "medium",
                    "likely_traps": ["misreading corresponding angles"],
                    "notes": ["image-only profile"],
                }
            ]
        )

        profile = build_problem_profile(make_question(), llm)  # type: ignore[arg-type]

        self.assertEqual(profile.question_id, "39")
        self.assertEqual(llm.image_calls[0][1], "raw_data/data/images/39.jpg")
        self.assertNotIn(OCR_SENTINEL, llm.image_calls[0][0])

    def test_generation_uses_image_without_ocr_text(self) -> None:
        question = make_question()
        llm = RecordingVisionLLM(
            [
                {
                    "predicted_answer": "2",
                    "student_response": "I think it is option 2.",
                }
            ]
        )

        prediction = generate_prediction(
            student=EediStaticStudent("s1", "medium", 0.5, [], []),
            question=question,
            student_model=make_student_model(),
            internal_signals=StudentInternalSignals(
                efficacy_signal="moderate",
                srl_fragility_signal="rushed",
                control_signal="uncertain on diagrams",
                value_signal="tries the task",
                directness_signal="brief",
            ),
            problem_profile=ProblemRequirementProfile(
                question_id="39",
                subject_path=["Maths", "Geometry and Measure"],
                prerequisite_knowledge=["parallel line angle facts"],
                operation_complexity="medium",
                operation_complexity_justification="visual relation",
                abstraction_level="medium",
                abstraction_level_justification="diagram to option",
                knowledge_integration_demand="single concept",
                representation_shift_required="image_diagram_to_option",
                response_format_demand="choose one",
                guessability="medium",
                likely_traps=["misread corresponding angle"],
                notes=["synthetic"],
                answer_space=["1", "2", "3", "4"],
            ),
            interaction_decision=StudentItemInteractionDecision(
                predicted_reachability="partial_reach",
                predicted_correctness_band="uncertain",
                likely_outcome="brief uncertain answer",
                likely_error_family="visual angle confusion",
                confidence_cap="medium",
                explanation_cap="brief",
                decision_rationale=["synthetic"],
            ),
            item_state=ItemResponseState(
                prerequisite_familiarity="partial",
                response_state="uncertain",
                reachable_level="surface",
                error_path=["visual angle confusion"],
                commitment_tendency="commit_to_one_option",
                explanation_depth_cap="brief",
                response_style_guidance=["brief"],
            ),
            constraints=ConstraintBundle(
                must_commit_answer=True,
                allow_complete_explanation=False,
                max_sentences=3,
                max_thinking_steps=4,
                forbid_full_mastery=True,
                preferred_error_path=["visual angle confusion"],
                style_constraints=["brief"],
                allowed_commitment="commit_to_one_option",
                output_answer_space=["1", "2", "3", "4"],
            ),
            llm=llm,  # type: ignore[arg-type]
        )

        self.assertEqual(prediction.predicted_answer, "2")
        self.assertEqual(llm.image_calls[0][1], "raw_data/data/images/39.jpg")
        self.assertNotIn(OCR_SENTINEL, llm.image_calls[0][0])


if __name__ == "__main__":
    unittest.main()
