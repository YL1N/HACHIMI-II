from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_loading import EediStaticQuestion, EediStaticStudent  # noqa: E402
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
    generate_prediction,
    tighten_constraints,
    _sentence_count,
)


class FakeLLM:
    def __init__(self, responses: list[dict[str, str]]) -> None:
        self._responses = list(responses)

    def chat_json(self, _system_prompt: str, _user_prompt: str) -> dict[str, str]:
        return self._pop_response()

    def chat_json_with_image(self, _system_prompt: str, _user_prompt: str, _image_path: str) -> dict[str, str]:
        return self._pop_response()

    def _pop_response(self) -> dict[str, str]:
        if not self._responses:
            raise AssertionError("FakeLLM received more calls than expected")
        return self._responses.pop(0)


def make_student_model() -> StudentModel:
    return StudentModel(
        student_id="s1",
        grade="unknown",
        academic_level="medium",
        weak_subjects=["algebra"],
        strong_subjects=["arithmetic"],
        self_efficacy_analysis=SelfEfficacyAnalysis(
            efficacy_belief_description="moderate confidence",
            efficacy_belief_evidence=["history shows mixed results"],
        ),
        srl_analysis=SRLAnalysis(
            primary_srl_vulnerability="checks work inconsistently",
            srl_process_evidence=["sometimes changes answer"],
        ),
        control_value_analysis=ControlValueAnalysis(
            control_appraisal_description="routine tasks feel controllable",
            value_appraisal_description="values concrete number work",
            control_value_evidence=["stronger on arithmetic"],
        ),
        engagement_level_tendency="medium",
        engagement_evidence=["answers most items"],
        response_directness_description="brief and direct",
        response_directness_evidence=["short option choices"],
        raw_summary="synthetic test model",
        math_anchor_profile_summary="synthetic anchor",
        math_anchor_profile_evidence=["no test labels used"],
        math_task_capability_profile=MathTaskCapabilityProfile(
            arithmetic_fluency="medium",
            word_problem_transfer="low",
            multi_step_stability="low",
            geometry_intuition="not_observed",
            pattern_rule_detection="medium",
            option_elimination="low",
            hard_item_persistence="low",
            guessing_tendency="medium",
            confidence_calibration="low",
            format_discipline="medium",
            common_error_families=["premature guessing"],
            capability_evidence=["synthetic evidence"],
        ),
    )


class StaticChainRetryTest(unittest.TestCase):
    def test_sentence_count_does_not_split_decimal_numbers(self) -> None:
        self.assertEqual(_sentence_count("I think it is 2.4"), 1)
        self.assertEqual(_sentence_count("I think it is 2.4. Not totally sure."), 2)

    def test_retry_constraints_do_not_shrink_sentence_budget_to_one(self) -> None:
        constraints = ConstraintBundle(
            must_commit_answer=True,
            allow_complete_explanation=False,
            max_sentences=5,
            max_thinking_steps=4,
            forbid_full_mastery=True,
            preferred_error_path=["premature guessing"],
            style_constraints=["brief and hesitant"],
            allowed_commitment="hesitant",
            output_answer_space=["1", "2", "3", "4"],
        )

        tightened = tighten_constraints(constraints)

        self.assertEqual(tightened.max_sentences, 5)
        self.assertTrue(tightened.forbid_full_mastery)

    def test_generation_retries_until_valid_without_over_tightening(self) -> None:
        student_model = make_student_model()
        student = EediStaticStudent(
            student_id="s1",
            ability_level="medium",
            ability_score_proxy=0.5,
            history=[],
            test=[],
        )
        question = EediStaticQuestion(
            question_id="1",
            question_text="Which option is correct?",
            image_path="raw_data/data/images/1.jpg",
            ocr_answer="",
            subject_names=["Maths"],
            subject_top="Maths",
            subject_leaf="Arithmetic",
            empirical_accuracy=0.0,
            all_train_response_count=0,
        )
        internal_signals = StudentInternalSignals(
            efficacy_signal="moderate",
            srl_fragility_signal="checks inconsistently",
            control_signal="routine controllable",
            value_signal="concrete tasks valued",
            directness_signal="brief",
        )
        problem_profile = ProblemRequirementProfile(
            question_id="1",
            subject_path=["Maths"],
            prerequisite_knowledge=["arithmetic"],
            operation_complexity="low",
            operation_complexity_justification="single step",
            abstraction_level="low",
            abstraction_level_justification="concrete",
            knowledge_integration_demand="single concept",
            representation_shift_required="text to option",
            response_format_demand="choose one",
            guessability="medium",
            likely_traps=["surface matching"],
            notes=["synthetic"],
            answer_space=["1", "2", "3", "4"],
        )
        interaction = StudentItemInteractionDecision(
            predicted_reachability="partial_reach",
            predicted_correctness_band="uncertain",
            likely_outcome="short uncertain answer",
            likely_error_family="premature guessing",
            confidence_cap="medium",
            explanation_cap="brief",
            decision_rationale=["synthetic rationale"],
        )
        response_state = ItemResponseState(
            prerequisite_familiarity="partial",
            response_state="uncertain",
            reachable_level="surface",
            error_path=["premature guessing"],
            commitment_tendency="hesitant",
            explanation_depth_cap="brief",
            response_style_guidance=["brief and hesitant"],
        )
        constraints = ConstraintBundle(
            must_commit_answer=True,
            allow_complete_explanation=False,
            max_sentences=5,
            max_thinking_steps=4,
            forbid_full_mastery=True,
            preferred_error_path=["premature guessing"],
            style_constraints=["brief and hesitant"],
            allowed_commitment="hesitant",
            output_answer_space=["1", "2", "3", "4"],
        )
        llm = FakeLLM(
            [
                {
                    "predicted_answer": "1",
                    "student_response": "A. B. C. D. E. F.",
                },
                {
                    "predicted_answer": "2",
                    "student_response": "I think it is 2. Not totally sure.",
                },
            ]
        )

        prediction = generate_prediction(
            student=student,
            question=question,
            student_model=student_model,
            internal_signals=internal_signals,
            problem_profile=problem_profile,
            interaction_decision=interaction,
            item_state=response_state,
            constraints=constraints,
            llm=llm,  # type: ignore[arg-type]
            max_generation_attempts=2,
        )

        self.assertEqual(prediction.predicted_answer, "2")
        self.assertEqual(prediction.retry_count, 1)
        self.assertFalse(prediction.violation_report.has_violation)


if __name__ == "__main__":
    unittest.main()
