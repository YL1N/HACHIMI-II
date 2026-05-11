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
from src.weak_generation import generate_weak_student_turn
from src.weak_harness import (
    build_student_prior,
    build_tutor_move,
    build_visible_context,
    compile_teaching_support_packet,
    resolve_local_claim_seed,
    resolve_math_claim_affordance,
    resolve_mediated_target_availability,
    predict_support_uptake,
    resolve_local_error_realization,
    resolve_learning_access_state,
    resolve_turn_response_constraint,
    update_learning_state,
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
                    "efficacy_belief_description": "The student is cautious and does not act like an independent solver yet.",
                    "efficacy_belief_evidence": ["The student hesitates before committing to a local claim."],
                },
                "srl_analysis": {
                    "primary_srl_vulnerability": "Performance-phase monitoring weakness",
                    "srl_process_evidence": ["The student notices uncertainty but cannot fully regulate it alone."],
                },
                "control_value_analysis": {
                    "control_appraisal_description": "The student has partial control only when the tutor narrows the focus.",
                    "value_appraisal_description": "The student still engages with the task when prompted.",
                    "control_value_evidence": ["The student keeps responding rather than dropping out."],
                },
                "engagement_tendency_analysis": {
                    "engagement_level_tendency": "Active",
                    "engagement_evidence": ["The student tends to respond directly to the tutor cue."],
                },
                "response_style_analysis": {
                    "response_directness_description": "The student is brief and local rather than polished.",
                    "response_directness_evidence": ["The student tends to answer in short local clauses."],
                },
                "evidence_trace": ["History shows cautious local responding under tutor guidance."],
            }
        if "support_type" in required_schema:
            return {
                "instructional_intent": "The tutor is focusing the student on one exact local comparison.",
                "support_type": "conceptual_hint",
                "support_intensity": "medium",
                "support_granularity": "localized_step",
                "support_contingency": "tightly_contingent",
                "responsibility_shift": "shared",
                "target_of_intervention": "misconception",
                "uptake_expectation": "local_update",
                "elicited_response_process": "interpret_evaluate",
                "elicited_response_target_type": "explanation_or_judgment",
                "elicited_object_description": "which visual part should count for the answer",
                "move_evidence": ["The tutor narrows the student's attention to one comparison."],
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
                "state_evidence": ["The student can probably act on one local cue but not solve the whole task."],
            }
        if "uptake_depth" in required_schema:
            return {
                "uptake_depth": "partial_use",
                "uptake_focus": "local_judgment",
                "response_space": "partial_attempt",
                "likely_next_engagement_mode": "Constructive",
                "uptake_rationale": ["The tutor cue likely supports one local attempt on the current comparison."],
            }
        if "claim_affordance" in required_schema:
            return {
                "claim_affordance": "math_claim_expected",
                "error_opportunity": "unstable_local_execution",
                "expected_claim_shape": "one short local math claim about which part counts",
                "affordance_evidence": ["The tutor cue makes one local mathematical claim likely."],
            }
        if "target_availability" in required_schema:
            return {
                "target_availability": "rule_available",
                "success_affordance": "moderate",
                "error_continuity_risk": "open",
                "availability_evidence": ["The tutor cue gives enough structure for one local attempt, but not a full solved answer."],
            }
        if "error_presence" in required_schema:
            return {
                "error_presence": "no_specific_error",
                "newman_error_locus": None,
                "radatz_error_mechanism": None,
                "buggy_rule": None,
                "wrong_claim_seed": None,
                "realization_evidence": ["The smoke path allows a local claim without forcing a specific error."],
            }
        if "claim_seed_mode" in required_schema:
            return {
                "claim_seed_mode": "support_consistent_claim_available",
                "support_consistent_claim_seed": "this part is the one we should compare",
                "claim_seed_evidence": ["The tutor has narrowed the student to the relevant local comparison."],
            }
        if "observed_engagement_mode" in required_schema:
            return {
                "observed_engagement_mode": "Constructive",
                "observed_uptake_depth": "partial_use",
                "predicted_next_readiness": "revise_prior_idea",
                "persistent_obstacle": "missing_relation",
                "update_evidence": ["The student used the cue locally but still did not show broad mastery."],
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
        self._calls = 0

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, object]:
        del system_prompt
        del partial_string_keys
        self._calls += 1
        payload = json.loads(user_prompt)
        required_schema = payload.get("required_schema", {})
        if "response_action" in required_schema:
            return {
                "response_action": "partial_attempt",
                "local_claim": "I think it's this part because that one looks smaller.",
                "claim_confidence": "medium",
                "uses_tutor_support": True,
                "realizes_error": False,
                "planning_rationale": ["The student makes one local claim using the tutor cue."],
            }
        if "pred_turn" not in required_schema:
            raise AssertionError(f"unexpected fake actor payload: {required_schema}")
        if self._calls == 2:
            return {
                "pred_turn": (
                    "I think maybe this part is it because it looks smaller. "
                    "And maybe that means this is the one. "
                    "So I would pick this one for now."
                ),
                "stop_dialogue": False,
                "turn_rationale": ["This first response is intentionally too long for retry testing."],
            }
        return {
            "pred_turn": "I think it's this part, because that one looks smaller.",
            "stop_dialogue": False,
            "turn_rationale": ["The student makes one local attempt using the tutor cue."],
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
        question_text="Which part should count for the answer?",
        subjects=[("Fractions", 2)],
        history=[
            DialogueTurn(role="tutor", content="Look at the two shaded pieces first."),
            DialogueTurn(role="student", content="I see them, but I am not sure which one matters."),
            DialogueTurn(role="tutor", content="Good. Which part are we supposed to compare here?"),
        ],
        target_turn_index=3,
    )
    ground_truth_student_turn = "Maybe the smaller one?"

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
    local_claim_seed = resolve_local_claim_seed(
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
    teaching_support_packet = compile_teaching_support_packet(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
        turn_response_constraint=turn_response_constraint,
        local_error_state=local_error_state,
        local_claim_seed=local_claim_seed,
    )
    generated_turn = generate_weak_student_turn(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        local_error_state=local_error_state,
        teaching_support_packet=teaching_support_packet,
        llm_client=actor_llm_client,
    )
    assert generated_turn.pred_turn
    assert generated_turn.retried is True
    assert generated_turn.validation.is_valid is True
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
    assert learning_state_update.observed_uptake_depth == "partial_use"

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
        "stop_dialogue": generated_turn.stop_dialogue,
        "retried": generated_turn.retried,
        "validation": asdict(generated_turn.validation),
        "student_context_profile": asdict(student_context_profile),
        "tutor_turn_profile": asdict(tutor_turn_profile),
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "mediated_target_availability": asdict(mediated_target_availability),
        "turn_response_constraint": asdict(turn_response_constraint),
        "local_error_state": asdict(local_error_state),
        "local_claim_seed": asdict(local_claim_seed),
        "teaching_support_packet": asdict(teaching_support_packet),
        "learning_state_update": asdict(learning_state_update),
        "turn_rationale": list(generated_turn.turn_rationale),
    }

    output_dir = EEDI_OUTPUTS_DIR / "smoke_test_weak_harness"
    output_dir.mkdir(parents=True, exist_ok=True)
    append_jsonl(output_dir / "stage_traces.jsonl", {"stage": "smoke_weak_harness", "payload": "ok"})
    append_jsonl(output_dir / "predictions.jsonl", record)
    write_json(
        output_dir / "metrics.json",
        {
            "n_records": 1,
            "n_failures": 0,
            "response_space_distribution": {
                teaching_support_packet.response_space: 1,
            },
        },
    )
    assert (output_dir / "stage_traces.jsonl").exists()
    assert (output_dir / "predictions.jsonl").exists()
    assert (output_dir / "metrics.json").exists()

    print("EEDI weak harness smoke test passed")


if __name__ == "__main__":
    main()
