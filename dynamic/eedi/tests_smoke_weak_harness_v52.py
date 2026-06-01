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
from src.weak_generation_v52 import generate_weak_student_turn_v52
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
from src.weak_harness_v5 import resolve_learning_opportunity_state
from src.weak_harness_v52 import (
    compile_opportunity_constraint_bundle_v52,
    resolve_claim_realization_frame,
    resolve_local_belief_state_v52,
    resolve_student_response_policy_v52,
    resolve_support_transformation_state_v52,
)


class FakeCompilerLLMClient:
    def chat_json(self, system_prompt: str, user_prompt: str, partial_string_keys=None):
        del system_prompt, partial_string_keys
        payload = json.loads(user_prompt)
        required_schema = payload.get("required_schema", {})
        if "self_efficacy_analysis" in required_schema:
            return {
                "self_efficacy_analysis": {
                    "efficacy_belief_description": "The student can make one local response under support but does not sustain full reasoning.",
                    "efficacy_belief_evidence": ["Visible history shows short guided replies."],
                },
                "srl_analysis": {
                    "primary_srl_vulnerability": "Monitoring weakness",
                    "srl_process_evidence": ["The student needs a narrow local anchor."],
                },
                "control_value_analysis": {
                    "control_appraisal_description": "Control improves only on one local target.",
                    "value_appraisal_description": "The student still wants to respond.",
                    "control_value_evidence": ["The student keeps interacting with the tutor."],
                },
                "engagement_tendency_analysis": {
                    "engagement_level_tendency": "Active",
                    "engagement_evidence": ["The student replies every turn."],
                },
                "response_style_analysis": {
                    "response_directness_description": "Brief, local, and not polished.",
                    "response_directness_evidence": ["Short local replies dominate the history."],
                },
                "evidence_trace": ["History supports weak but responsive behavior."],
            }
        if "support_type" in required_schema:
            return {
                "instructional_intent": "The tutor is challenging the student's earlier option choice.",
                "support_type": "error_challenge",
                "support_intensity": "medium",
                "support_granularity": "localized_step",
                "support_contingency": "moderately_contingent",
                "responsibility_shift": "shared",
                "target_of_intervention": "commitment",
                "uptake_expectation": "local_update",
                "elicited_response_process": "formulate",
                "elicited_response_target_type": "result_or_selection",
                "elicited_object_description": "which option is not equivalent",
                "move_evidence": ["The tutor asks the student to reconsider one local option judgment."],
            }
        if "access_zone" in required_schema:
            return {
                "access_zone": "reachable_with_current_support",
                "tutor_intent_grasp": "partial",
                "uptake_preparation": "attention_oriented",
                "turn_readiness": "revise_prior_idea",
                "regulation_state": "shared_regulation",
                "current_engagement_mode": "Active",
                "persistent_obstacle": "missing_relation",
                "state_evidence": ["The student may revise shallowly under the challenge."],
            }
        if "uptake_depth" in required_schema:
            return {
                "uptake_depth": "noticing_only",
                "uptake_focus": "local_judgment",
                "response_space": "clarification_request",
                "likely_next_engagement_mode": "Active",
                "uptake_rationale": ["The tutor has destabilized the prior guess but not taught a full rule."],
            }
        if "claim_affordance" in required_schema:
            return {
                "claim_affordance": "math_claim_possible",
                "error_opportunity": "unstable_local_execution",
                "expected_claim_shape": "a short option choice or shallow revision",
                "affordance_evidence": ["A local option claim is possible."],
            }
        if "target_availability" in required_schema:
            return {
                "target_availability": "rule_available",
                "success_affordance": "moderate",
                "error_continuity_risk": "open",
                "availability_evidence": ["One local comparison is available but not full mastery."],
            }
        if "independently_available_acts" in required_schema:
            return {
                "independently_available_acts": ["repeat a prior guess", "state uncertainty about the option"],
                "support_enabled_acts": ["revise the guess shallowly", "mention one local comparison"],
                "still_unavailable_acts": ["give a full worked explanation"],
                "salient_confusion_axes": ["which option breaks equivalence", "how to compare ratios quickly"],
                "response_space": "partial_attempt",
                "required_local_focus": "which option is not equivalent",
                "max_explanatory_depth": "brief_reason",
                "opportunity_evidence": ["The support opens shallow revision, not full explanation."],
            }
        if "help_seeking_tendency" in required_schema:
            return {
                "help_seeking_tendency": "low",
                "guessing_tendency": "high",
                "social_justification_tendency": "medium",
                "refusal_tendency": "low",
                "revision_volatility": "high",
                "policy_evidence": ["History shows quick guesses and easy answer switching."],
            }
        if "belief_status" in required_schema:
            return {
                "belief_status": "stable_guess",
                "committed_content": "maybe D",
                "justification_basis": "intuition",
                "confidence_posture": "low",
                "revision_readiness": "unstable",
                "belief_evidence": ["The prior student turn guessed D without solid justification."],
            }
        if "transformation_type" in required_schema:
            return {
                "transformation_type": "destabilize_prior_commitment",
                "preferred_response_family": "shallow_revision",
                "allowed_response_families": ["shallow_revision", "direct_guess", "social_justification"],
                "claim_likelihood": "likely",
                "transformation_evidence": ["The tutor challenge makes the prior guess unstable but does not produce full understanding."],
            }
        if "claim_state" in required_schema:
            return {
                "claim_state": "tentative_local_claim",
                "anchor_mode": "stay_with_visible_belief",
                "allowed_content_sources": ["maybe D", "which option is not equivalent"],
                "preferred_reason_mode": "intuition",
                "surface_depth": "brief_reason",
                "frame_evidence": ["The student should respond by shallowly revising the visible prior guess rather than constructing a new explanation."],
            }
        if "error_presence" in required_schema:
            return {
                "error_presence": "codable_math_error",
                "newman_error_locus": "transformation",
                "radatz_error_mechanism": "incorrect_associations",
                "buggy_rule": "switches option without valid equivalence check",
                "wrong_claim_seed": "it is A",
                "realization_evidence": ["Posthoc analysis path only."],
            }
        if "observed_engagement_mode" in required_schema:
            return {
                "observed_engagement_mode": "Active",
                "observed_uptake_depth": "noticing_only",
                "predicted_next_readiness": "revise_prior_idea",
                "persistent_obstacle": "missing_relation",
                "update_evidence": ["The student revised shallowly but did not show robust reasoning."],
            }
        raise AssertionError(f"unexpected fake compiler payload: {required_schema}")

    def retry_schema_json(self, system_prompt, user_prompt, previous_reply, validation_error, partial_string_keys=None):
        del previous_reply, validation_error
        return self.chat_json(system_prompt, user_prompt, partial_string_keys)


class FakeActorLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat_json(self, system_prompt, user_prompt, partial_string_keys=None):
        del system_prompt, partial_string_keys, user_prompt
        self.calls += 1
        if self.calls == 1:
            return {
                "pred_turn": "Maybe it's A then, because D sounds wrong now. I just think A fits better. So I'd go A.",
                "stop_dialogue": False,
                "turn_rationale": ["Too long on purpose for retry."],
            }
        return {
            "pred_turn": "Maybe it's A then, I just think A fits better.",
            "stop_dialogue": False,
            "turn_rationale": ["The weak actor makes a shallow revision inside the claim-realization frame."],
        }

    def retry_schema_json(self, system_prompt, user_prompt, previous_reply, validation_error, partial_string_keys=None):
        del previous_reply, validation_error
        return self.chat_json(system_prompt, user_prompt, partial_string_keys)


def main() -> None:
    compiler_llm_client = FakeCompilerLLMClient()
    actor_llm_client = FakeActorLLMClient()
    task = TurnPredictionTask(
        dialogue_id="q1_i1",
        question_id="q1",
        intervention_id="i1",
        question_text="Which option is not equivalent to 6:15?",
        subjects=[("Ratio", 2)],
        history=[
            DialogueTurn(role="tutor", content="Hi Joshua!"),
            DialogueTurn(role="student", content="is it d"),
            DialogueTurn(role="tutor", content="D is equivalent. Which one is not equivalent then?"),
        ],
        target_turn_index=3,
    )
    context = build_dialogue_context_state(task)
    student_context_profile = build_student_context_profile(context, compiler_llm_client)
    tutor_turn_profile = build_tutor_turn_profile(context, compiler_llm_client)
    visible_context = build_visible_context(context)
    student_prior = build_student_prior(student_context_profile)
    tutor_move = build_tutor_move(tutor_turn_profile)
    learning_access_state = resolve_learning_access_state(visible_context, student_prior, tutor_move, compiler_llm_client)
    support_uptake = predict_support_uptake(visible_context, student_prior, tutor_move, learning_access_state, compiler_llm_client)
    math_claim_affordance = resolve_math_claim_affordance(visible_context, student_prior, tutor_move, learning_access_state, support_uptake, compiler_llm_client)
    mediated_target_availability = resolve_mediated_target_availability(visible_context, student_prior, tutor_move, learning_access_state, support_uptake, math_claim_affordance, compiler_llm_client)
    turn_response_constraint = resolve_turn_response_constraint(visible_context, student_prior, tutor_move, learning_access_state, support_uptake, math_claim_affordance, mediated_target_availability)
    learning_opportunity_state = resolve_learning_opportunity_state(visible_context, student_prior, tutor_move, learning_access_state, support_uptake, math_claim_affordance, mediated_target_availability, turn_response_constraint, compiler_llm_client)
    student_response_policy = resolve_student_response_policy_v52(visible_context, student_prior, compiler_llm_client)
    local_belief_state = resolve_local_belief_state_v52(visible_context, student_prior, tutor_move, compiler_llm_client)
    support_transformation_state = resolve_support_transformation_state_v52(visible_context, student_prior, tutor_move, learning_access_state, support_uptake, math_claim_affordance, mediated_target_availability, student_response_policy, local_belief_state, compiler_llm_client)
    claim_realization_frame = resolve_claim_realization_frame(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
        learning_opportunity_state=learning_opportunity_state,
        student_response_policy=student_response_policy,
        local_belief_state=local_belief_state,
        support_transformation_state=support_transformation_state,
        llm_client=compiler_llm_client,
    )
    bundle = compile_opportunity_constraint_bundle_v52(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
        learning_opportunity_state=learning_opportunity_state,
        student_response_policy=student_response_policy,
        local_belief_state=local_belief_state,
        support_transformation_state=support_transformation_state,
        claim_realization_frame=claim_realization_frame,
        ablation_mode="commitment_first",
    )
    generated_turn = generate_weak_student_turn_v52(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        learning_opportunity_state=learning_opportunity_state,
        student_response_policy=student_response_policy,
        local_belief_state=local_belief_state,
        support_transformation_state=support_transformation_state,
        claim_realization_frame=claim_realization_frame,
        opportunity_constraint_bundle_v52=bundle,
        llm_client=actor_llm_client,
    )

    assert generated_turn.retried is True
    assert generated_turn.validation.is_valid is True
    assert bundle.packet_version == "eedi_weak_harness_v5.2"
    assert bundle.claim_state == "tentative_local_claim"

    local_error_state_for_analysis = resolve_local_error_realization(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        turn_response_constraint=turn_response_constraint,
        llm_client=compiler_llm_client,
    )
    learning_state_update = update_learning_state(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        teaching_support_packet=bundle,
        generated_turn=generated_turn.pred_turn,
        llm_client=compiler_llm_client,
    )

    output_dir = EEDI_OUTPUTS_DIR / "smoke_test_weak_harness_v52"
    output_dir.mkdir(parents=True, exist_ok=True)
    append_jsonl(output_dir / "predictions.jsonl", {
        "dialogue_id": task.dialogue_id,
        "turn_idx": task.target_turn_index,
        "pred_turn": generated_turn.pred_turn,
        "student_response_policy": asdict(student_response_policy),
        "local_belief_state": asdict(local_belief_state),
        "support_transformation_state": asdict(support_transformation_state),
        "claim_realization_frame": asdict(claim_realization_frame),
        "teaching_support_packet": asdict(bundle),
        "local_error_state_for_analysis": asdict(local_error_state_for_analysis),
        "learning_state_update": asdict(learning_state_update),
    })
    write_json(output_dir / "metrics.json", {
        "pred_turn": generated_turn.pred_turn,
        "packet_version": bundle.packet_version,
        "retried": generated_turn.retried,
        "validation": asdict(generated_turn.validation),
    })
    print("EEDI weak harness v5.2 smoke test passed")


if __name__ == "__main__":
    main()
