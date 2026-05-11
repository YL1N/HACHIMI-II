from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from src.constraint_bundle import compile_constraints
from src.data_loading import DialogueTurn, TurnPredictionTask
from src.dialogue_context import build_dialogue_context_state
from src.error_blueprint import build_error_blueprint
from src.evaluation_eedi import append_jsonl, write_turn_level_outputs
from src.generation import generate_student_turn
from src.student_model import build_student_context_profile
from src.student_turn_state import resolve_interaction_state
from src.transition import predict_state_transition
from src.tutor_turn_profile import build_tutor_turn_profile
from src.runtime_paths import EEDI_OUTPUTS_DIR


class FakeLLMClient:
    def __init__(self) -> None:
        self._calls = 0

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, object]:
        _ = partial_string_keys
        self._calls += 1
        payload = json.loads(user_prompt)
        required_schema = payload.get("required_schema", {})
        if "self_efficacy_analysis" in required_schema:
            return {
                "self_efficacy_analysis": {
                    "efficacy_belief_description": "The student shows uneven confidence and often checks before committing.",
                    "efficacy_belief_evidence": ["The student asks for confirmation before answering."],
                },
                "srl_analysis": {
                    "primary_srl_vulnerability": "Performance-phase monitoring weakness",
                    "srl_process_evidence": ["The student notices confusion but does not fully self-correct alone."],
                },
                "control_value_analysis": {
                    "control_appraisal_description": "The student has partial control but is not fully secure.",
                    "value_appraisal_description": "The student stays engaged with the math task.",
                    "control_value_evidence": ["The student keeps responding to the tutor's prompt."],
                },
                "engagement_tendency_analysis": {
                    "engagement_level_tendency": "Active",
                    "engagement_evidence": ["The student responds directly to the tutor prompt."],
                },
                "response_style_analysis": {
                    "response_directness_description": "The student is direct but still cautious.",
                    "response_directness_evidence": ["The student answers without sounding fully committed."],
                },
                "evidence_trace": ["History shows cautious engagement with tutor guidance."],
            }
        if "support_type" in required_schema:
            return {
                "instructional_intent": "The tutor is checking whether the student can apply the hint.",
                "support_type": "conceptual_hint",
                "support_intensity": "medium",
                "support_granularity": "localized_step",
                "support_contingency": "tightly_contingent",
                "responsibility_shift": "shared",
                "target_of_intervention": "misconception",
                "uptake_expectation": "local_update",
                "elicited_response_process": "formulate",
                "elicited_response_target_type": "representation",
                "elicited_object_description": "which parts are shaded",
                "move_evidence": ["The tutor narrows attention to the key comparison."],
            }
        if "competence_position" in required_schema:
            return {
                "competence_position": "within_zpd",
                "misconception_status": "destabilizing_misconception",
                "metacognitive_regulation_state": "weak_monitoring",
                "help_internalization_state": "surface_uptake",
                "help_seeking_state": "help_ambivalent",
                "attempt_readiness": "ready_for_local_attempt",
                "engagement_form": "Active",
                "response_commitment_state": "tentative",
                "response_maturity_cap": "brief_local_explanation",
                "state_evidence": ["The student is moving but still uncertain."],
            }
        if "predicted_next_competence_position" in required_schema:
            return {
                "predicted_next_competence_position": "within_zpd",
                "predicted_next_misconception_status": "destabilizing_misconception",
                "predicted_next_metacognitive_regulation_state": "active_monitoring",
                "predicted_next_help_internalization_state": "partial_internalization",
                "predicted_next_help_seeking_state": "adaptive_help_seeking",
                "predicted_next_attempt_readiness": "ready_to_revise",
                "predicted_next_engagement_form": "Constructive",
                "predicted_next_response_commitment_state": "tentative",
                "predicted_next_response_maturity_cap": "brief_local_explanation",
                "predicted_misconception_trajectory_shift": "local_repair",
                "transition_rationale": ["The tutor hint supports a small local update, not full mastery."],
            }
        if "error_presence" in required_schema:
            return {
                "error_presence": "codable_math_error",
                "newman_error_locus": "transformation",
                "radatz_error_mechanism": "deficient_prerequisites",
                "buggy_rule": "The student treats the visual comparison as supporting the wrong option.",
                "wrong_claim_seed": "Point to the smaller-looking part as the answer.",
                "blueprint_evidence": [
                    "The student is ready for a local attempt but still on a shaky misconception path."
                ],
            }
        if "realized_turn" in required_schema:
            return {
                "realized_turn": "Maybe this one? That part looks smaller, but I'm not fully sure.",
                "realization_rationale": [
                    "The wording keeps the same uncertainty and math content while sounding less expert-like."
                ],
            }
        if "changed_math_content" in required_schema:
            return {
                "passed": True,
                "changed_math_content": False,
                "changed_correctness": False,
                "changed_error_path": False,
                "changed_uncertainty": False,
                "changed_turn_function": False,
                "rationale": [
                    "The realized turn keeps the same local mathematical idea, uncertainty, and turn function."
                ],
            }
        if "step_kind" in required_schema:
            if payload["step_index"] < payload["step_budget"]:
                return {
                    "step_kind": "internal_step",
                    "step_text": "The student narrows down the idea but is still checking.",
                    "stop_dialogue": False,
                }
            return {
                "step_kind": "finalize_turn",
                "step_text": "I think it might be this one because that part looks smaller, but I'm not fully sure.",
                "stop_dialogue": False,
            }
        if "has_violation" in required_schema:
            return {
                "has_violation": False,
                "violation_types": [],
                "rationale": ["The reply matches the tentative local-update state."],
            }
        raise AssertionError(f"unexpected fake LLM payload: {required_schema}")


class FailingSemanticFakeLLMClient(FakeLLMClient):
    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, object]:
        payload = json.loads(user_prompt)
        required_schema = payload.get("required_schema", {})
        if "realized_turn" in required_schema:
            return {
                "realized_turn": "The answer is definitely 3.",
                "realization_rationale": [
                    "This intentionally changes the certainty and answer for fallback testing."
                ],
            }
        if "changed_math_content" in required_schema:
            return {
                "passed": False,
                "changed_math_content": True,
                "changed_correctness": True,
                "changed_error_path": False,
                "changed_uncertainty": True,
                "changed_turn_function": False,
                "rationale": [
                    "The realized turn changed the answer and removed the uncertainty."
                ],
            }
        return super().chat_json(system_prompt, user_prompt, partial_string_keys)


def main() -> None:
    llm_client = FakeLLMClient()
    task = TurnPredictionTask(
        dialogue_id="q1_i1",
        question_id="q1",
        intervention_id="i1",
        question_text="What fraction is shaded?",
        subjects=[("Fractions", 2)],
        history=[
            DialogueTurn(role="tutor", content="Can you tell me what you notice first?"),
            DialogueTurn(role="student", content="I think there are four parts."),
            DialogueTurn(role="tutor", content="Good. Which parts are shaded?"),
        ],
        target_turn_index=3,
    )
    ground_truth_student_turn = "Two of them are shaded, I think."
    context = build_dialogue_context_state(task)
    student_context_profile = build_student_context_profile(context, llm_client)
    tutor_profile = build_tutor_turn_profile(context, llm_client)
    interaction_state = resolve_interaction_state(
        student_context_profile,
        context,
        tutor_profile,
        llm_client,
    )
    transition_prediction = predict_state_transition(
        student_context_profile,
        context,
        tutor_profile,
        interaction_state,
        llm_client,
    )
    error_blueprint = build_error_blueprint(
        student_context_profile,
        context,
        tutor_profile,
        interaction_state,
        transition_prediction,
        llm_client,
    )
    constraint_bundle = compile_constraints(transition_prediction, error_blueprint)
    generated_turn = generate_student_turn(
        student_context_profile=student_context_profile,
        context=context,
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        transition_prediction=transition_prediction,
        error_blueprint=error_blueprint,
        constraint_bundle=constraint_bundle,
        llm_client=llm_client,
    )
    assert generated_turn.pred_turn
    assert generated_turn.step_traces
    assert generated_turn.step_traces[-1].step_kind == "finalize_turn"
    assert generated_turn.violation_check.has_violation is False
    assert generated_turn.semantic_preservation is not None
    assert generated_turn.semantic_preservation.passed is True
    assert error_blueprint.error_presence == "codable_math_error"
    assert constraint_bundle.must_realize_specific_error is True

    record = {
        "dialogue_id": task.dialogue_id,
        "question_id": task.question_id,
        "intervention_id": task.intervention_id,
        "turn_idx": task.target_turn_index,
        "question_text": task.question_text,
        "subjects": list(task.subjects),
        "history": [asdict(turn) for turn in task.history],
        "gt_turn": ground_truth_student_turn,
        "pred_turn": generated_turn.pred_turn,
        "draft_turn": generated_turn.draft_turn,
        "stop_dialogue": generated_turn.stop_dialogue,
        "retried": generated_turn.retried,
        "student_context_profile": asdict(student_context_profile),
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "interaction_state": asdict(interaction_state),
        "state_transition_prediction": asdict(transition_prediction),
        "error_blueprint": asdict(error_blueprint),
        "constraint_bundle": asdict(constraint_bundle),
        "step_traces": [asdict(step) for step in generated_turn.step_traces],
        "violation_check": asdict(generated_turn.violation_check),
        "semantic_preservation": (
            asdict(generated_turn.semantic_preservation)
            if generated_turn.semantic_preservation
            else None
        ),
        "surface_realization": (
            asdict(generated_turn.surface_realization)
            if generated_turn.surface_realization
            else None
        ),
    }

    output_dir = EEDI_OUTPUTS_DIR / "smoke_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    append_jsonl(output_dir / "stage_traces.jsonl", {"stage": "smoke", "payload": "ok"})
    write_turn_level_outputs(output_dir, [record])
    assert (output_dir / "stage_traces.jsonl").exists()
    assert (output_dir / "predictions.jsonl").exists()
    assert (output_dir / "turn_level_predictions.csv").exists()
    assert (output_dir / "metrics.json").exists()

    fallback_client = FailingSemanticFakeLLMClient()
    fallback_generated_turn = generate_student_turn(
        student_context_profile=student_context_profile,
        context=context,
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        transition_prediction=transition_prediction,
        error_blueprint=error_blueprint,
        constraint_bundle=constraint_bundle,
        llm_client=fallback_client,
    )
    assert fallback_generated_turn.semantic_preservation is not None
    assert fallback_generated_turn.semantic_preservation.passed is False
    assert fallback_generated_turn.semantic_preservation.fallback_to_draft is True
    assert fallback_generated_turn.pred_turn == fallback_generated_turn.draft_turn

    print("EEDI smoke test passed")


if __name__ == "__main__":
    main()
