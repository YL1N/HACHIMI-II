from __future__ import annotations

from src.dialogue_context import DialogueContextState
from src.population_calibration import (
    PopulationCalibrationExemplar,
    build_population_calibration_summary,
)
from src.tutor_turn_profile import TutorTurnProfile


def main() -> None:
    context = DialogueContextState(
        dialogue_id="d1",
        question_id="q1",
        intervention_id="i1",
        question_text="What is 10 less than 18,703?",
        subjects=[("Number", 1)],
        turns_so_far=[
            {"role": "student", "content": "i dont get it"},
            {"role": "tutor", "content": "What operation would you use to find 10 less?"},
        ],
        latest_tutor_turn="What operation would you use to find 10 less?",
        last_student_turn="i dont get it",
        turn_count_so_far=2,
    )
    tutor_profile = TutorTurnProfile(
        instructional_intent="Elicit the local operation.",
        support_type="answer_elicitation",
        support_intensity="medium",
        support_granularity="localized_step",
        support_contingency="tightly_contingent",
        responsibility_shift="shared",
        target_of_intervention="missing_step",
        uptake_expectation="local_update",
        elicited_response_process="formulate",
        elicited_response_target_type="result_or_selection",
        elicited_object_description="the operation to use to find 10 less",
        move_evidence=["Tutor asks for the operation directly."],
    )
    bank = [
        PopulationCalibrationExemplar(
            dialogue_id="d_cal_1",
            question_id="q_cal_1",
            intervention_id="i_cal_1",
            turn_idx=3,
            subjects=[("Number", 1)],
            history_turn_count=3,
            latest_tutor_turn="What operation would you use?",
            last_student_turn="i am confused",
            tutor_profile={
                "support_type": "answer_elicitation",
                "elicited_response_process": "formulate",
                "elicited_response_target_type": "result_or_selection",
                "target_of_intervention": "missing_step",
                "elicited_object_description": "the operation to use to find 10 less",
            },
            has_codable_math_error=False,
            knowledge_type=None,
            error_locus=None,
            error_mechanism=None,
            error_evidence=["Student gave the correct local operation."],
        ),
        PopulationCalibrationExemplar(
            dialogue_id="d_cal_2",
            question_id="q_cal_2",
            intervention_id="i_cal_2",
            turn_idx=5,
            subjects=[("Number", 1)],
            history_turn_count=5,
            latest_tutor_turn="Which operation should we use?",
            last_student_turn="maybe add",
            tutor_profile={
                "support_type": "answer_elicitation",
                "elicited_response_process": "formulate",
                "elicited_response_target_type": "result_or_selection",
                "target_of_intervention": "missing_step",
                "elicited_object_description": "the operation to use to find 10 less",
            },
            has_codable_math_error=True,
            knowledge_type="conceptual",
            error_locus="transformation",
            error_mechanism="incorrect_associations",
            error_evidence=["Student maps '10 less' to addition rather than subtraction."],
        ),
    ]
    summary = build_population_calibration_summary(
        context=context,
        tutor_profile=tutor_profile,
        exemplar_bank=bank,
        top_k=2,
    )
    if summary is None:
        raise AssertionError("summary should not be None")
    assert summary.n_retrieved == 2
    assert any("codable math errors appear in 1/2 cases" in line for line in summary.prior_summary_lines)
    summary_dict = summary.__dict__
    assert "top_response_families" not in summary_dict
    assert "exemplar_snippets" not in summary_dict
    print("population calibration smoke test passed")


if __name__ == "__main__":
    main()
