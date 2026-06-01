from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

EEDI_DIR = Path(__file__).resolve().parent
if str(EEDI_DIR) not in sys.path:
    sys.path.insert(0, str(EEDI_DIR))

from src.data_loading import DialogueTurn, TurnPredictionTask
from src.dialogue_context import build_dialogue_context_state
from src.evaluation_eedi import append_jsonl, write_json
from src.runtime_paths import EEDI_OUTPUTS_DIR
from src.student_model import build_student_context_profile
from src.tutor_turn_profile import build_tutor_turn_profile
from src.weak_generation_v4 import generate_weak_student_turn_v4
from src.weak_harness import (
    build_student_prior,
    build_tutor_move,
    build_visible_context,
    predict_support_uptake,
    resolve_learning_access_state,
    resolve_local_error_realization,
    resolve_math_claim_affordance,
    resolve_mediated_target_availability,
    resolve_turn_response_constraint,
    update_learning_state,
)
from src.weak_harness_v4 import (
    compile_teaching_support_packet_v4,
    resolve_mediated_turn_plan,
)


class FakeCompilerLLMClient:
    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, object]:
        del system_prompt
        del partial_string_keys
        payload = json.loads(user_prompt)
        required_schema = payload.get("required_schema", {})
        if "self_efficacy_analysis" in required_schema:
            return {
                "self_efficacy_analysis": {
                    "efficacy_belief_description": "The student can follow one local tutor cue but does not yet look independently secure.",
                    "efficacy_belief_evidence": ["The history shows local responding under guidance."],
                },
                "srl_analysis": {
                    "primary_srl_vulnerability": "Performance-phase monitoring weakness",
                    "srl_process_evidence": ["The student still needs the tutor to narrow the focus."],
                },
                "control_value_analysis": {
                    "control_appraisal_description": "The student gains local control when the tutor highlights one exact target.",
                    "value_appraisal_description": "The student keeps engaging with the task.",
                    "control_value_evidence": ["The student keeps responding to tutor prompts."],
                },
                "engagement_tendency_analysis": {
                    "engagement_level_tendency": "Active",
                    "engagement_evidence": ["The student usually answers the current cue directly."],
                },
                "response_style_analysis": {
                    "response_directness_description": "The student is brief, local, and not polished.",
                    "response_directness_evidence": ["The student usually speaks in short local clauses."],
                },
                "evidence_trace": ["The dialogue history supports a local guided-attempt profile."],
            }
        if "support_type" in required_schema:
            return {
                "instructional_intent": "The tutor is narrowing the student to one exact local decision.",
                "support_type": "conceptual_hint",
                "support_intensity": "medium",
                "support_granularity": "localized_step",
                "support_contingency": "tightly_contingent",
                "responsibility_shift": "shared",
                "target_of_intervention": "missing_step",
                "uptake_expectation": "local_update",
                "elicited_response_process": "interpret_evaluate",
                "elicited_response_target_type": "result_or_selection",
                "elicited_object_description": "which option matches the equivalent ratio",
                "move_evidence": ["The tutor asks for one exact option judgment."],
            }
        if "access_zone" in required_schema:
            return {
                "access_zone": "reachable_with_current_support",
                "tutor_intent_grasp": "partial",
                "uptake_preparation": "ready_to_try",
                "turn_readiness": "attempt_local_step",
                "regulation_state": "shared_regulation",
                "current_engagement_mode": "Active",
                "persistent_obstacle": "missing_relation",
                "state_evidence": ["The student can probably make one local attempt with the current cue."],
            }
        if "uptake_depth" in required_schema:
            return {
                "uptake_depth": "partial_use",
                "uptake_focus": "local_judgment",
                "response_space": "partial_attempt",
                "likely_next_engagement_mode": "Constructive",
                "uptake_rationale": ["The tutor cue supports one local option judgment."],
            }
        if "claim_affordance" in required_schema:
            return {
                "claim_affordance": "math_claim_expected",
                "error_opportunity": "none",
                "expected_claim_shape": "one short local option claim",
                "affordance_evidence": ["The tutor asks for one exact option judgment."],
            }
        if "target_availability" in required_schema:
            return {
                "target_availability": "rule_available",
                "success_affordance": "high",
                "error_continuity_risk": "open",
                "availability_evidence": ["The tutor cue makes the target option locally available."],
            }
        if "error_presence" in required_schema:
            return {
                "error_presence": "no_specific_error",
                "newman_error_locus": None,
                "radatz_error_mechanism": None,
                "buggy_rule": None,
                "wrong_claim_seed": None,
                "realization_evidence": ["The smoke path does not require a codable local error."],
            }
        if "response_space" in required_schema and "content_mode" in required_schema:
            return {
                "response_space": "partial_attempt",
                "claim_requirement": "local_claim_required",
                "content_mode": "support_consistent_claim",
                "utterance_kernel": "option D matches the equivalent ratio",
                "reasoning_kernel": "both parts are scaled by the same factor",
                "claim_confidence": "medium",
                "should_mention_tutor_support": False,
                "plan_evidence": ["The tutor has made one local equivalent-ratio judgment available."],
            }
        if "observed_engagement_mode" in required_schema:
            return {
                "observed_engagement_mode": "Constructive",
                "observed_uptake_depth": "partial_use",
                "predicted_next_readiness": "revise_prior_idea",
                "persistent_obstacle": "missing_relation",
                "update_evidence": ["The student used the cue locally but still does not show broad mastery."],
            }
        raise AssertionError(f"unexpected fake compiler payload: {required_schema}")

    def retry_schema_json(
        self,
        system_prompt: str,
        user_prompt: str,
        previous_reply: object,
        validation_error: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, object]:
        del previous_reply
        del validation_error
        return self.chat_json(system_prompt, user_prompt, partial_string_keys)


class FakeActorLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, object]:
        del system_prompt
        del partial_string_keys
        self.calls += 1
        payload = json.loads(user_prompt)
        if "pred_turn" not in payload.get("required_schema", {}):
            raise AssertionError("unexpected fake actor payload")
        if self.calls == 1:
            return {
                "pred_turn": (
                    "I think it is option D because both parts are scaled by the same factor. "
                    "So I would choose D for this one. "
                    "That seems like the one that keeps the same ratio."
                ),
                "stop_dialogue": False,
                "turn_rationale": ["This first response is intentionally too long for retry testing."],
            }
        return {
            "pred_turn": "I think it's D, because both parts scale by the same factor.",
            "stop_dialogue": False,
            "turn_rationale": ["The weak actor realizes the compiler-planned local claim."],
        }

    def retry_schema_json(
        self,
        system_prompt: str,
        user_prompt: str,
        previous_reply: object,
        validation_error: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, object]:
        del previous_reply
        del validation_error
        return self.chat_json(system_prompt, user_prompt, partial_string_keys)


def main() -> None:
    compiler_llm_client = FakeCompilerLLMClient()
    actor_llm_client = FakeActorLLMClient()
    task = TurnPredictionTask(
        dialogue_id="q1_i1",
        question_id="q1",
        intervention_id="i1",
        question_text="Which option gives an equivalent ratio?",
        subjects=[("Ratio and Proportion", 2)],
        history=[
            DialogueTurn(role="tutor", content="Look at whether both parts are scaled by the same factor."),
            DialogueTurn(role="student", content="I am not sure which option keeps the same relationship."),
            DialogueTurn(role="tutor", content="Good. Which option matches the equivalent ratio?"),
        ],
        target_turn_index=3,
    )

    context = build_dialogue_context_state(task)
    student_context_profile = build_student_context_profile(context, compiler_llm_client)
    tutor_turn_profile = build_tutor_turn_profile(context, compiler_llm_client)
    visible_context = build_visible_context(context)
    student_prior = build_student_prior(student_context_profile)
    tutor_move = build_tutor_move(tutor_turn_profile)
    learning_access_state = resolve_learning_access_state(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        llm_client=compiler_llm_client,
    )
    support_uptake = predict_support_uptake(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        llm_client=compiler_llm_client,
    )
    math_claim_affordance = resolve_math_claim_affordance(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        llm_client=compiler_llm_client,
    )
    mediated_target_availability = resolve_mediated_target_availability(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        llm_client=compiler_llm_client,
    )
    turn_response_constraint = resolve_turn_response_constraint(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
    )
    local_error_state = resolve_local_error_realization(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        turn_response_constraint=turn_response_constraint,
        llm_client=compiler_llm_client,
    )
    mediated_turn_plan = resolve_mediated_turn_plan(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
        turn_response_constraint=turn_response_constraint,
        local_error_state=local_error_state,
        llm_client=compiler_llm_client,
    )
    teaching_support_packet = compile_teaching_support_packet_v4(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
        turn_response_constraint=turn_response_constraint,
        local_error_state=local_error_state,
        mediated_turn_plan=mediated_turn_plan,
        ablation_mode="commitment_first",
    )
    generated_turn = generate_weak_student_turn_v4(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        mediated_turn_plan=mediated_turn_plan,
        teaching_support_packet=teaching_support_packet,
        llm_client=actor_llm_client,
    )
    assert generated_turn.retried is True
    assert generated_turn.validation.is_valid is True
    assert teaching_support_packet.packet_version == "eedi_weak_harness_v4.0"
    assert teaching_support_packet.support_consistent_claim_seed == "option D matches the equivalent ratio"
    learning_state_update = update_learning_state(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        teaching_support_packet=teaching_support_packet,
        generated_turn=generated_turn.pred_turn,
        llm_client=compiler_llm_client,
    )

    output_dir = EEDI_OUTPUTS_DIR / "smoke_test_weak_harness_v4"
    output_dir.mkdir(parents=True, exist_ok=True)
    append_jsonl(
        output_dir / "predictions.jsonl",
        {
            "dialogue_id": task.dialogue_id,
            "turn_idx": task.target_turn_index,
            "pred_turn": generated_turn.pred_turn,
            "student_context_profile": asdict(student_context_profile),
            "tutor_turn_profile": asdict(tutor_turn_profile),
            "learning_access_state": asdict(learning_access_state),
            "support_uptake": asdict(support_uptake),
            "math_claim_affordance": asdict(math_claim_affordance),
            "mediated_target_availability": asdict(mediated_target_availability),
            "turn_response_constraint": asdict(turn_response_constraint),
            "local_error_state": asdict(local_error_state),
            "mediated_turn_plan": asdict(mediated_turn_plan),
            "teaching_support_packet": asdict(teaching_support_packet),
            "learning_state_update": asdict(learning_state_update),
        },
    )
    write_json(
        output_dir / "metrics.json",
        {
            "pred_turn": generated_turn.pred_turn,
            "packet_version": teaching_support_packet.packet_version,
            "retried": generated_turn.retried,
            "validation": asdict(generated_turn.validation),
        },
    )
    print("EEDI weak harness v4 smoke test passed")


if __name__ == "__main__":
    main()
