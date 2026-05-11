from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .constraint_bundle import ConstraintBundle
from .dialogue_context import DialogueContextState
from .error_blueprint import ErrorBlueprint
from .llm_client import OpenAICompatClient, require_keys
from .prompts import (
    DYNAMIC_VIOLATION_REVIEW_SYSTEM_PROMPT,
    STUDENT_TURN_FINAL_SYSTEM_PROMPT,
    STUDENT_TURN_STEP_SYSTEM_PROMPT,
)
from .semantic_preservation import (
    SemanticPreservationCheck,
    review_semantic_preservation,
)
from .surface_style import SurfaceRealizedTurn, realize_student_surface_turn
from .student_model import StudentContextProfile
from .student_turn_state import InteractionState
from .transition import StateTransitionPrediction
from .tutor_turn_profile import TutorTurnProfile


@dataclass(frozen=True)
class TurnStepTrace:
    step_index: int
    step_kind: str
    step_text: str


@dataclass(frozen=True)
class DynamicViolationCheck:
    has_violation: bool
    violation_types: list[str]
    rationale: list[str]
    llm_review_used: bool


@dataclass(frozen=True)
class GeneratedStudentTurn:
    pred_turn: str
    draft_turn: str
    stop_dialogue: bool
    step_traces: list[TurnStepTrace]
    violation_check: DynamicViolationCheck
    retried: bool
    surface_realization: SurfaceRealizedTurn | None
    semantic_preservation: SemanticPreservationCheck | None


def generate_student_turn(
    student_context_profile: StudentContextProfile,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: InteractionState,
    transition_prediction: StateTransitionPrediction,
    error_blueprint: ErrorBlueprint,
    constraint_bundle: ConstraintBundle,
    llm_client: OpenAICompatClient,
) -> GeneratedStudentTurn:
    initial = _generate_once(
        student_context_profile=student_context_profile,
        context=context,
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        transition_prediction=transition_prediction,
        error_blueprint=error_blueprint,
        constraint_bundle=constraint_bundle,
        llm_client=llm_client,
        retry_note="",
    )
    hard_violation = check_hard_dynamic_violations(
        generated_turn=initial.pred_turn,
        transition_prediction=transition_prediction,
        constraint_bundle=constraint_bundle,
    )
    if not hard_violation.has_violation:
        reviewed = review_dynamic_violation_with_llm(
            student_context_profile=student_context_profile,
            context=context,
            tutor_profile=tutor_profile,
            interaction_state=interaction_state,
            transition_prediction=transition_prediction,
            error_blueprint=error_blueprint,
            constraint_bundle=constraint_bundle,
            generated_turn=initial.pred_turn,
            llm_client=llm_client,
        )
    else:
        reviewed = hard_violation
    if not reviewed.has_violation:
        return GeneratedStudentTurn(
            pred_turn=initial.pred_turn,
            draft_turn=initial.draft_turn,
            stop_dialogue=initial.stop_dialogue,
            step_traces=initial.step_traces,
            violation_check=reviewed,
            retried=False,
            surface_realization=initial.surface_realization,
            semantic_preservation=initial.semantic_preservation,
        )

    tightened = retry_with_tighter_constraints(constraint_bundle, reviewed)
    retried = _generate_once(
        student_context_profile=student_context_profile,
        context=context,
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        transition_prediction=transition_prediction,
        error_blueprint=error_blueprint,
        constraint_bundle=tightened,
        llm_client=llm_client,
        retry_note=(
            "Previous attempt violated the predicted state. "
            f"Violation types: {reviewed.violation_types}."
        ),
    )
    retry_hard_violation = check_hard_dynamic_violations(
        generated_turn=retried.pred_turn,
        transition_prediction=transition_prediction,
        constraint_bundle=tightened,
    )
    final_violation = (
        retry_hard_violation
        if retry_hard_violation.has_violation
        else review_dynamic_violation_with_llm(
            student_context_profile=student_context_profile,
            context=context,
            tutor_profile=tutor_profile,
            interaction_state=interaction_state,
            transition_prediction=transition_prediction,
            error_blueprint=error_blueprint,
            constraint_bundle=tightened,
            generated_turn=retried.pred_turn,
            llm_client=llm_client,
        )
    )
    return GeneratedStudentTurn(
        pred_turn=retried.pred_turn,
        draft_turn=retried.draft_turn,
        stop_dialogue=retried.stop_dialogue,
        step_traces=retried.step_traces,
        violation_check=final_violation,
        retried=True,
        surface_realization=retried.surface_realization,
        semantic_preservation=retried.semantic_preservation,
    )


def check_hard_dynamic_violations(
    generated_turn: str,
    transition_prediction: StateTransitionPrediction,
    constraint_bundle: ConstraintBundle,
) -> DynamicViolationCheck:
    text = generated_turn.strip()
    if not text:
        return DynamicViolationCheck(
            has_violation=True,
            violation_types=["empty_output"],
            rationale=["Generated student turn is empty."],
            llm_review_used=False,
        )

    sentence_count = _count_sentences(text)
    violations: list[str] = []
    rationale: list[str] = []
    if sentence_count > constraint_bundle.max_sentences:
        violations.append("over_mature_response")
        rationale.append(
            f"Sentence count {sentence_count} exceeds max_sentences={constraint_bundle.max_sentences}."
        )
    if not constraint_bundle.allow_full_reasoning and _looks_like_full_reasoning(text):
        violations.append("over_mature_response")
        rationale.append("Output contains over-complete reasoning beyond allowed maturity.")
    if (
        transition_prediction.predicted_next_response_commitment_state != "committed"
        and _looks_like_final_answer_commitment(text)
    ):
        violations.append("over_fast_transition")
        rationale.append("Output is too fully committed for the predicted commitment state.")
    if (
        transition_prediction.predicted_next_misconception_status == "active_misconception"
        and _looks_like_sudden_mastery(text)
    ):
        violations.append("error_path_discontinuity")
        rationale.append("Active misconception disappeared too abruptly in the reply.")
    if (
        constraint_bundle.must_preserve_local_confusion
        and not constraint_bundle.allow_direct_answer
        and _looks_like_sudden_mastery(text)
    ):
        violations.append("over_fast_transition")
        rationale.append(
            "A locally unresolved non-attempt/help-seeking state was replaced too abruptly by a fully resolved answer."
        )
    if (
        constraint_bundle.must_preserve_misconception_continuity
        and _looks_like_sudden_mastery(text)
    ):
        violations.append("error_path_discontinuity")
        rationale.append("The reply breaks misconception continuity more abruptly than allowed.")
    return DynamicViolationCheck(
        has_violation=bool(violations),
        violation_types=_dedupe_keep_order(violations),
        rationale=rationale or ["No hard dynamic violation triggered."],
        llm_review_used=False,
    )


def review_dynamic_violation_with_llm(
    student_context_profile: StudentContextProfile,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: InteractionState,
    transition_prediction: StateTransitionPrediction,
    error_blueprint: ErrorBlueprint,
    constraint_bundle: ConstraintBundle,
    generated_turn: str,
    llm_client: OpenAICompatClient,
) -> DynamicViolationCheck:
    payload = {
        "student_context_profile": asdict(student_context_profile),
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "interaction_state": asdict(interaction_state),
        "transition_prediction": asdict(transition_prediction),
        "error_blueprint": asdict(error_blueprint),
        "constraint_bundle": asdict(constraint_bundle),
        "generated_turn": generated_turn,
        "review_notice": (
            "If this is a social opening/check-in turn, a brief acknowledgment or help-request "
            "should not be treated as over-mature academic reasoning."
        ),
        "required_schema": {
            "has_violation": "boolean",
            "violation_types": [
                "over_fast_transition",
                "error_path_discontinuity",
                "over_mature_response",
            ],
            "rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=DYNAMIC_VIOLATION_REVIEW_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_dynamic_violation_check(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=DYNAMIC_VIOLATION_REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_dynamic_violation_check(repaired)


def retry_with_tighter_constraints(
    constraint_bundle: ConstraintBundle,
    violation_check: DynamicViolationCheck,
) -> ConstraintBundle:
    violation_types = set(violation_check.violation_types)
    max_sentences = constraint_bundle.max_sentences
    max_step_budget = constraint_bundle.max_step_budget
    style_constraints = list(constraint_bundle.style_constraints)
    forbidden_patterns = list(constraint_bundle.forbidden_patterns)
    allow_direct_answer = constraint_bundle.allow_direct_answer
    allow_full_reasoning = constraint_bundle.allow_full_reasoning
    allow_help_seeking_language = constraint_bundle.allow_help_seeking_language
    must_preserve_local_confusion = constraint_bundle.must_preserve_local_confusion
    must_preserve_misconception_continuity = (
        constraint_bundle.must_preserve_misconception_continuity
    )
    required_commitment_style = constraint_bundle.required_commitment_style
    if "over_mature_response" in violation_types:
        max_sentences = max(1, constraint_bundle.max_sentences - 1)
        max_step_budget = max(1, constraint_bundle.max_step_budget - 1)
        allow_full_reasoning = False
        style_constraints.append(
            "Remove any extra explanatory structure that exceeds the predicted maturity."
        )
        forbidden_patterns.append(
            "Do not add extra justificatory or tutorial-style structure beyond the predicted maturity."
        )
    if "over_fast_transition" in violation_types:
        style_constraints.append(
            "Keep the same local mathematical direction, but avoid making the reply sound fully resolved or tutor-like."
        )
        forbidden_patterns.append(
            "Do not convert a partial learner state into a polished mastered answer."
        )
    if "error_path_discontinuity" in violation_types:
        style_constraints.append(
            "Preserve local continuity with the prior confusion or misconception unless the predicted state already supports a shift."
        )
        if constraint_bundle.must_realize_specific_error:
            style_constraints.append(
                "Do not erase the concrete buggy rule into generic confusion; restore the same local wrong-claim direction."
            )
        if constraint_bundle.must_anchor_to_local_wrong_claim:
            style_constraints.append(
                "Restore the error on the exact local object the tutor is currently eliciting, not on a different step or answer type."
            )
    return ConstraintBundle(
        max_sentences=max_sentences,
        max_step_budget=max_step_budget,
        allow_direct_answer=allow_direct_answer,
        allow_full_reasoning=allow_full_reasoning,
        allow_help_seeking_language=allow_help_seeking_language,
        must_preserve_local_confusion=must_preserve_local_confusion,
        must_preserve_misconception_continuity=must_preserve_misconception_continuity,
        expected_error_presence=constraint_bundle.expected_error_presence,
        expected_newman_error_locus=constraint_bundle.expected_newman_error_locus,
        expected_radatz_error_mechanism=constraint_bundle.expected_radatz_error_mechanism,
        buggy_rule=constraint_bundle.buggy_rule,
        wrong_claim_seed=constraint_bundle.wrong_claim_seed,
        must_realize_specific_error=constraint_bundle.must_realize_specific_error,
        must_anchor_to_local_wrong_claim=constraint_bundle.must_anchor_to_local_wrong_claim,
        required_commitment_style=required_commitment_style,
        forbidden_patterns=_dedupe_keep_order(forbidden_patterns),
        style_constraints=_dedupe_keep_order(style_constraints),
    )


def _generate_once(
    student_context_profile: StudentContextProfile,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: InteractionState,
    transition_prediction: StateTransitionPrediction,
    error_blueprint: ErrorBlueprint,
    constraint_bundle: ConstraintBundle,
    llm_client: OpenAICompatClient,
    retry_note: str,
) -> GeneratedStudentTurn:
    step_traces: list[TurnStepTrace] = []
    for step_index in range(1, constraint_bundle.max_step_budget + 1):
        payload = {
            "step_index": step_index,
            "step_budget": constraint_bundle.max_step_budget,
            "student_context_profile": asdict(student_context_profile),
            "dialogue_context": asdict(context),
            "tutor_turn_profile": asdict(tutor_profile),
            "interaction_state": asdict(interaction_state),
            "transition_prediction": asdict(transition_prediction),
            "error_blueprint": asdict(error_blueprint),
            "constraint_bundle": asdict(constraint_bundle),
            "existing_step_traces": [asdict(step) for step in step_traces],
            "retry_note": retry_note,
            "required_schema": {
                "step_kind": "internal_step | finalize_turn",
                "step_text": "string",
                "stop_dialogue": "boolean",
            },
        }
        user_prompt = json.dumps(payload, ensure_ascii=False)
        parsed = llm_client.chat_json(
            system_prompt=(
                STUDENT_TURN_FINAL_SYSTEM_PROMPT
                if step_index == constraint_bundle.max_step_budget
                else STUDENT_TURN_STEP_SYSTEM_PROMPT
            ),
            user_prompt=user_prompt,
            partial_string_keys=["step_text"],
        )
        try:
            step_kind, step_text, stop_dialogue = _parse_student_turn_step(
                parsed,
                step_index=step_index,
                final_step_index=constraint_bundle.max_step_budget,
            )
        except (KeyError, ValueError) as exc:
            repaired = llm_client.retry_schema_json(
                system_prompt=(
                    STUDENT_TURN_FINAL_SYSTEM_PROMPT
                    if step_index == constraint_bundle.max_step_budget
                    else STUDENT_TURN_STEP_SYSTEM_PROMPT
                ),
                user_prompt=user_prompt,
                previous_reply=parsed,
                validation_error=str(exc),
                partial_string_keys=["step_text"],
            )
            step_kind, step_text, stop_dialogue = _parse_student_turn_step(
                repaired,
                step_index=step_index,
                final_step_index=constraint_bundle.max_step_budget,
            )
        step_traces.append(
            TurnStepTrace(
                step_index=step_index,
                step_kind=step_kind,
                step_text=step_text,
            )
        )
        if step_kind == "finalize_turn":
            draft_turn = step_text
            surface_realization = realize_student_surface_turn(
                student_context_profile=student_context_profile,
                context=context,
                tutor_profile=tutor_profile,
                interaction_state=interaction_state,
                transition_prediction=transition_prediction,
                error_blueprint=error_blueprint,
                constraint_bundle=constraint_bundle,
                draft_turn=draft_turn,
                llm_client=llm_client,
            )
            semantic_preservation = review_semantic_preservation(
                draft_turn=draft_turn,
                realized_turn=surface_realization.realized_turn,
                context=context,
                tutor_profile=tutor_profile,
                interaction_state=interaction_state,
                transition_prediction=transition_prediction,
                error_blueprint=error_blueprint,
                constraint_bundle=constraint_bundle,
                llm_client=llm_client,
            )
            pred_turn = (
                draft_turn
                if semantic_preservation.fallback_to_draft
                else surface_realization.realized_turn
            )
            return GeneratedStudentTurn(
                pred_turn=pred_turn,
                draft_turn=draft_turn,
                stop_dialogue=stop_dialogue,
                step_traces=step_traces,
                violation_check=DynamicViolationCheck(
                    has_violation=False,
                    violation_types=[],
                    rationale=["not reviewed yet"],
                    llm_review_used=False,
                ),
                retried=False,
                surface_realization=surface_realization,
                semantic_preservation=semantic_preservation,
            )
    raise ValueError(
        "step budget exhausted before a final student turn was produced; "
        f"step_traces={[asdict(step) for step in step_traces]!r}"
    )


def _count_sentences(text: str) -> int:
    normalized = re.sub(r"(?<=\d)\.(?=\d)", "<DECIMAL>", text)
    normalized = normalized.replace("...", ".")
    parts = [
        part.strip()
        for part in re.split(r"[.!?]+", normalized)
        if part.strip()
    ]
    return max(1, len(parts))


def _looks_like_full_reasoning(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "because",
        "therefore",
        "so the answer is",
        "first",
        "then",
        "finally",
    )
    return sum(1 for marker in markers if marker in lowered) >= 2


def _looks_like_final_answer_commitment(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "the answer is",
        "it is definitely",
        "i'm sure",
        "it must be",
    )
    return any(marker in lowered for marker in markers)


def _looks_like_sudden_mastery(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "i understand now",
        "that makes perfect sense",
        "i get it completely",
        "so it's obvious",
    )
    return any(marker in lowered for marker in markers)


def _coerce_violation_types(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("violation_types must be a list")
    allowed = {
        "over_fast_transition",
        "error_path_discontinuity",
        "over_mature_response",
    }
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text not in allowed:
            raise ValueError(f"invalid violation type: {text!r}")
        result.append(text)
    return _dedupe_keep_order(result)


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result


def _coerce_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean, got {type(value).__name__}: {value!r}")
    return value


def _parse_dynamic_violation_check(parsed: object) -> DynamicViolationCheck:
    parsed = require_keys(
        parsed,
        (
            "has_violation",
            "violation_types",
            "rationale",
        ),
        "DynamicViolationCheck",
    )
    violation_types = _coerce_violation_types(parsed.get("violation_types", []))
    has_violation = _coerce_bool(parsed["has_violation"], "has_violation")
    if has_violation and not violation_types:
        raise ValueError("LLM violation review marked violation but returned no violation_types")
    return DynamicViolationCheck(
        has_violation=has_violation,
        violation_types=violation_types,
        rationale=_coerce_str_list(parsed["rationale"], "rationale"),
        llm_review_used=True,
    )


def _parse_student_turn_step(
    parsed: object,
    step_index: int,
    final_step_index: int,
) -> tuple[str, str, bool]:
    parsed = require_keys(
        parsed,
        (
            "step_kind",
            "step_text",
            "stop_dialogue",
        ),
        "StudentTurnStep",
    )
    step_kind = str(parsed["step_kind"]).strip()
    step_text = str(parsed["step_text"]).strip()
    stop_dialogue = _coerce_bool(parsed["stop_dialogue"], "stop_dialogue")
    if step_kind not in {"internal_step", "finalize_turn"}:
        raise ValueError(f"invalid step_kind: {step_kind}")
    if not step_text:
        raise ValueError("step_text cannot be empty")
    if step_kind == "finalize_turn" and step_index != final_step_index:
        raise ValueError("finalize_turn appeared before the final allowed step")
    return step_kind, step_text, stop_dialogue


def _dedupe_keep_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
