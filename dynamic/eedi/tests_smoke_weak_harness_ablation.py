from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
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
    TeachingSupportPacket,
    build_student_prior,
    build_tutor_move,
    build_visible_context,
    compile_teaching_support_packet,
    predict_support_uptake,
    resolve_local_claim_seed,
    resolve_local_error_realization,
    resolve_math_claim_affordance,
    resolve_mediated_target_availability,
    resolve_learning_access_state,
    resolve_turn_response_constraint,
    update_learning_state,
)


ABLATION_MODES = (
    "baseline",
    "protocol-light",
    "commitment-first",
)


class FakeCompilerLLMClient:
    def __init__(self, mode: str) -> None:
        if mode not in ABLATION_MODES:
            raise ValueError(f"unsupported mode: {mode}")
        self.mode = mode

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
                    "efficacy_belief_description": "The student can react to a local cue but does not yet look independently secure.",
                    "efficacy_belief_evidence": ["The student has shown local participation under tutor guidance."],
                },
                "srl_analysis": {
                    "primary_srl_vulnerability": "Performance-phase monitoring weakness",
                    "srl_process_evidence": ["The student can act locally but still needs the tutor to narrow the focus."],
                },
                "control_value_analysis": {
                    "control_appraisal_description": "The student has partial control when the tutor points to one exact comparison.",
                    "value_appraisal_description": "The student still engages with the task rather than dropping out.",
                    "control_value_evidence": ["The student keeps responding to the tutor's local prompt."],
                },
                "engagement_tendency_analysis": {
                    "engagement_level_tendency": "Active",
                    "engagement_evidence": ["The student tends to answer the current cue directly."],
                },
                "response_style_analysis": {
                    "response_directness_description": "The student is brief and local rather than polished.",
                    "response_directness_evidence": ["The student tends to answer in short local clauses."],
                },
                "evidence_trace": ["History shows local responding under tutor guidance."],
            }
        if "support_type" in required_schema:
            return {
                "instructional_intent": "The tutor is narrowing the student onto one exact local comparison.",
                "support_type": "conceptual_hint",
                "support_intensity": "medium",
                "support_granularity": "localized_step",
                "support_contingency": "tightly_contingent",
                "responsibility_shift": "shared",
                "target_of_intervention": "misconception",
                "uptake_expectation": "local_update",
                "elicited_response_process": "interpret_evaluate",
                "elicited_response_target_type": "explanation_or_judgment",
                "elicited_object_description": "which shaded part should count for the answer",
                "move_evidence": ["The tutor narrows the student onto one local visual judgment."],
            }
        if "access_zone" in required_schema:
            return {
                "access_zone": "reachable_with_current_support",
                "tutor_intent_grasp": "partial",
                "uptake_preparation": "ready_to_try",
                "turn_readiness": (
                    "explain_current_judgment"
                    if self.mode == "commitment-first"
                    else "attempt_local_step"
                ),
                "regulation_state": "shared_regulation",
                "current_engagement_mode": "Active",
                "persistent_obstacle": "missing_relation",
                "state_evidence": ["The student can likely act on one local cue but not solve the whole task."],
            }
        if "uptake_depth" in required_schema:
            if self.mode == "commitment-first":
                return {
                    "uptake_depth": "substantive_use",
                    "uptake_focus": "local_judgment",
                    "response_space": "local_explanation",
                    "likely_next_engagement_mode": "Constructive",
                    "uptake_rationale": ["The tutor cue likely supports one direct local mathematical judgment now."],
                }
            return {
                "uptake_depth": "partial_use",
                "uptake_focus": "local_judgment",
                "response_space": "partial_attempt",
                "likely_next_engagement_mode": "Constructive",
                    "uptake_rationale": ["The tutor cue likely supports one local attempt on the current comparison."],
                }
        if "claim_affordance" in required_schema:
            if self.mode == "protocol-light":
                return {
                    "claim_affordance": "math_claim_possible",
                    "error_opportunity": "unstable_local_execution",
                    "expected_claim_shape": "a tentative local claim about which shaded part counts",
                    "affordance_evidence": ["The tutor cue may support a local claim, but confusion is still plausible."],
                }
            return {
                "claim_affordance": "math_claim_expected",
                "error_opportunity": "misconception_continuity",
                "expected_claim_shape": "one local claim about which shaded part counts",
                "affordance_evidence": ["The current tutor cue elicits one direct local mathematical judgment."],
            }
        if "target_availability" in required_schema:
            if self.mode == "commitment-first":
                return {
                    "target_availability": "rule_available",
                    "success_affordance": "moderate",
                    "error_continuity_risk": "likely",
                    "availability_evidence": ["The support enables one direct local judgment, but the same misconception can still continue."],
                }
            if self.mode == "protocol-light":
                return {
                    "target_availability": "cue_only",
                    "success_affordance": "low",
                    "error_continuity_risk": "open",
                    "availability_evidence": ["The cue orients attention but does not stabilize a concrete local claim."],
                }
            return {
                "target_availability": "cue_only",
                "success_affordance": "low",
                "error_continuity_risk": "likely",
                "availability_evidence": ["The current cue does not yet interrupt the wrong local visual comparison."],
            }
        if "error_presence" in required_schema:
            if self.mode == "protocol-light":
                return {
                    "error_presence": "non_codable_confusion",
                    "newman_error_locus": None,
                    "radatz_error_mechanism": None,
                    "buggy_rule": None,
                    "wrong_claim_seed": None,
                    "realization_evidence": ["The student may still be unsure without stabilizing one concrete wrong rule."],
                }
            return {
                "error_presence": "codable_math_error",
                "newman_error_locus": "comprehension",
                "radatz_error_mechanism": "incorrect_associations",
                "buggy_rule": "Count the smaller-looking shaded piece because it seems to match the tutor's contrast.",
                "wrong_claim_seed": "this smaller shaded part is the one that counts",
                "realization_evidence": ["The student is likely to anchor on the wrong local visual comparison."],
            }
        if "claim_seed_mode" in required_schema:
            if self.mode == "protocol-light":
                return {
                    "claim_seed_mode": "insufficient_visible_basis",
                    "support_consistent_claim_seed": None,
                    "claim_seed_evidence": ["The lighter path does not stabilize a confident local claim."],
                }
            return {
                "claim_seed_mode": "use_wrong_claim_seed",
                "support_consistent_claim_seed": None,
                "claim_seed_evidence": ["The local error state already supplies the wrong-claim direction."],
            }
        if "observed_engagement_mode" in required_schema:
            if self.mode == "commitment-first":
                return {
                    "observed_engagement_mode": "Constructive",
                    "observed_uptake_depth": "substantive_use",
                    "predicted_next_readiness": "revise_prior_idea",
                    "persistent_obstacle": "missing_relation",
                    "update_evidence": ["The student made one direct local claim but still has not shown broad mastery."],
                }
            return {
                "observed_engagement_mode": "Constructive",
                "observed_uptake_depth": "partial_use",
                "predicted_next_readiness": "revise_prior_idea",
                "persistent_obstacle": "missing_relation",
                "update_evidence": ["The student used the cue locally but still did not show broad mastery."],
            }
        raise AssertionError(f"unexpected fake compiler payload for mode={self.mode}: {required_schema}")

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
    def __init__(self, mode: str) -> None:
        if mode not in ABLATION_MODES:
            raise ValueError(f"unsupported mode: {mode}")
        self.mode = mode
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
        required_schema = payload.get("required_schema", {})
        packet_version = str(payload["teaching_support_packet"]["packet_version"])
        if "response_action" in required_schema:
            if self.mode == "protocol-light":
                return {
                    "response_action": "clarification_request",
                    "local_claim": "So this smaller part is the one we are talking about?",
                    "claim_confidence": "low",
                    "uses_tutor_support": True,
                    "realizes_error": False,
                    "planning_rationale": ["The student orients to the local object but does not stabilize one concrete wrong claim."],
                }
            return {
                "response_action": (
                    "local_explanation" if self.mode == "commitment-first" else "partial_attempt"
                ),
                "local_claim": "I think this smaller shaded part is the one that counts.",
                "claim_confidence": "medium",
                "uses_tutor_support": True,
                "realizes_error": True,
                "planning_rationale": ["The student uses the tutor cue to make one local but still wrong mathematical commitment."],
            }
        if "pred_turn" not in required_schema:
            raise AssertionError(f"unexpected fake actor payload for mode={self.mode}: {required_schema}")
        if self.mode == "baseline":
            if packet_version != "eedi_weak_harness_v3.2":
                raise AssertionError(f"baseline packet version drifted: {packet_version}")
            if self.calls == 1:
                return {
                    "pred_turn": (
                        "I think this smaller part is the one that counts. "
                        "That one looks smaller to me. "
                        "So I would use this one for now."
                    ),
                    "stop_dialogue": False,
                    "turn_rationale": ["This first response is intentionally too long for retry testing."],
                }
            return {
                "pred_turn": "I think this smaller part counts, because that one looks smaller.",
                "stop_dialogue": False,
                "turn_rationale": ["The student makes one local attempt using the tutor cue."],
            }
        if self.mode == "protocol-light":
            if not packet_version.endswith("protocol_light_smoke"):
                raise AssertionError(f"protocol-light packet version drifted: {packet_version}")
            return {
                "pred_turn": "I think this part counts.",
                "stop_dialogue": False,
                "turn_rationale": ["The lighter packet still supports one short local student turn."],
            }
        if not packet_version.endswith("commitment_first_smoke"):
            raise AssertionError(f"commitment-first packet version drifted: {packet_version}")
        return {
            "pred_turn": "This smaller part counts because that is the piece we are comparing.",
            "stop_dialogue": False,
            "turn_rationale": ["The student makes one direct local mathematical commitment."],
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


def _build_task() -> TurnPredictionTask:
    return TurnPredictionTask(
        dialogue_id="q1_i1",
        question_id="q1",
        intervention_id="i1",
        question_text="Which shaded part should count for the answer?",
        subjects=[("Fractions", 2)],
        history=[
            DialogueTurn(role="tutor", content="Look at the two shaded pieces first."),
            DialogueTurn(role="student", content="I see them, but I am not sure which one matters."),
            DialogueTurn(role="tutor", content="Good. Which part are we supposed to compare here?"),
        ],
        target_turn_index=3,
    )


def _apply_packet_mode(mode: str, packet: TeachingSupportPacket) -> TeachingSupportPacket:
    if mode == "baseline":
        return packet
    if mode == "protocol-light":
        return replace(
            packet,
            packet_version=f"{packet.packet_version}__protocol_light_smoke",
            response_space="clarification_request",
            allowed_actions=[packet.allowed_actions[0]],
            disallowed_actions=[packet.disallowed_actions[0]],
            support_use_rules=[packet.support_use_rules[0]],
            packet_rationale=[packet.packet_rationale[0]],
        )
    if mode == "commitment-first":
        return replace(
            packet,
            packet_version=f"{packet.packet_version}__commitment_first_smoke",
            response_space="local_explanation",
            target_engagement_mode="Constructive",
            max_sentences=2,
            allowed_actions=[
                "Make one direct local mathematical claim about the exact object.",
                "Stay on the current comparison instead of drifting into a meta-response.",
            ],
            disallowed_actions=[
                *packet.disallowed_actions,
                "Do not retreat into pure acknowledgment or pure confusion when one local claim is reachable.",
            ],
            support_use_rules=[
                "Use the tutor support to make one explicit local judgment now.",
                "Keep the claim local rather than solving the whole problem.",
            ],
            packet_rationale=[
                "This ablation keeps the same third-person state but prefers one direct local commitment once the object is reachable."
            ],
        )
    raise ValueError(f"unsupported ablation mode: {mode}")


def _run_mode(mode: str) -> dict[str, object]:
    compiler_llm_client = FakeCompilerLLMClient(mode)
    actor_llm_client = FakeActorLLMClient(mode)
    task = _build_task()

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
    teaching_support_packet = _apply_packet_mode(
        mode,
        compile_teaching_support_packet(
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
        ),
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
    return {
        "mode": mode,
        "task": task,
        "student_context_profile": student_context_profile,
        "tutor_turn_profile": tutor_turn_profile,
        "visible_context": visible_context,
        "student_prior": student_prior,
        "tutor_move": tutor_move,
        "learning_access_state": learning_access_state,
        "support_uptake": support_uptake,
        "math_claim_affordance": math_claim_affordance,
        "mediated_target_availability": mediated_target_availability,
        "turn_response_constraint": turn_response_constraint,
        "local_error_state": local_error_state,
        "local_claim_seed": local_claim_seed,
        "teaching_support_packet": teaching_support_packet,
        "generated_turn": generated_turn,
        "learning_state_update": learning_state_update,
    }


def _assert_mode_contract(result: dict[str, object]) -> None:
    mode = str(result["mode"])
    packet = result["teaching_support_packet"]
    generated_turn = result["generated_turn"]
    learning_state_update = result["learning_state_update"]

    assert generated_turn.pred_turn
    assert generated_turn.validation.is_valid is True

    if mode == "baseline":
        assert packet.packet_version == "eedi_weak_harness_v3.2"
        assert generated_turn.retried is False
        assert packet.response_space == "partial_attempt"
        assert packet.local_error_presence == "codable_math_error"
        assert learning_state_update.observed_uptake_depth == "partial_use"
        return
    if mode == "protocol-light":
        assert packet.packet_version.endswith("protocol_light_smoke")
        assert generated_turn.retried is False
        assert packet.response_space == "clarification_request"
        assert len(packet.allowed_actions) == 1
        assert len(packet.disallowed_actions) == 1
        assert len(packet.support_use_rules) == 1
        assert len(packet.packet_rationale) == 1
        assert packet.local_error_presence == "non_codable_confusion"
        assert learning_state_update.observed_uptake_depth == "partial_use"
        return
    if mode == "commitment-first":
        assert packet.packet_version.endswith("commitment_first_smoke")
        assert packet.response_space == "local_explanation"
        assert packet.target_engagement_mode == "Constructive"
        assert generated_turn.retried is False
        assert generated_turn.turn_plan.realizes_error is True
        assert "?" not in generated_turn.pred_turn
        assert "maybe" not in generated_turn.pred_turn.lower()
        assert learning_state_update.observed_uptake_depth == "substantive_use"
        return
    raise AssertionError(f"unexpected mode in assertions: {mode}")


def main() -> None:
    results = [_run_mode(mode) for mode in ABLATION_MODES]
    for result in results:
        _assert_mode_contract(result)

    records: list[dict[str, object]] = []
    for result in results:
        task = result["task"]
        generated_turn = result["generated_turn"]
        packet = result["teaching_support_packet"]
        records.append(
            {
                "mode": result["mode"],
                "dialogue_id": task.dialogue_id,
                "question_id": task.question_id,
                "intervention_id": task.intervention_id,
                "turn_idx": task.target_turn_index,
                "question_text": task.question_text,
                "subjects": list(task.subjects),
                "history": [asdict(turn) for turn in task.history],
                "pred_turn": generated_turn.pred_turn,
                "stop_dialogue": generated_turn.stop_dialogue,
                "retried": generated_turn.retried,
                "validation": asdict(generated_turn.validation),
                "student_context_profile": asdict(result["student_context_profile"]),
                "tutor_turn_profile": asdict(result["tutor_turn_profile"]),
                "visible_context": asdict(result["visible_context"]),
                "student_prior": asdict(result["student_prior"]),
                "tutor_move": asdict(result["tutor_move"]),
                "learning_access_state": asdict(result["learning_access_state"]),
                "support_uptake": asdict(result["support_uptake"]),
                "math_claim_affordance": asdict(result["math_claim_affordance"]),
                "mediated_target_availability": asdict(
                    result["mediated_target_availability"]
                ),
                "local_error_state": asdict(result["local_error_state"]),
                "local_claim_seed": asdict(result["local_claim_seed"]),
                "teaching_support_packet": asdict(packet),
                "learning_state_update": asdict(result["learning_state_update"]),
                "turn_rationale": list(generated_turn.turn_rationale),
                "turn_plan": asdict(generated_turn.turn_plan),
            }
        )

    output_dir = EEDI_OUTPUTS_DIR / "smoke_test_weak_harness_ablation"
    output_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        append_jsonl(output_dir / "predictions.jsonl", record)
        append_jsonl(
            output_dir / "stage_traces.jsonl",
            {
                "mode": record["mode"],
                "stage": "smoke_weak_harness_ablation",
                "packet_version": record["teaching_support_packet"]["packet_version"],
            },
        )
    write_json(
        output_dir / "metrics.json",
        {
            "n_records": len(records),
            "n_failures": 0,
            "modes": list(ABLATION_MODES),
            "response_space_distribution": {
                record["mode"]: record["teaching_support_packet"]["response_space"]
                for record in records
            },
            "retried_distribution": {
                record["mode"]: bool(record["retried"])
                for record in records
            },
        },
    )
    assert (output_dir / "predictions.jsonl").exists()
    assert (output_dir / "stage_traces.jsonl").exists()
    assert (output_dir / "metrics.json").exists()

    print("EEDI weak harness ablation smoke test passed")


if __name__ == "__main__":
    main()
