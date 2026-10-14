from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .constraint_bundle import BehaviorHarness
from .dialogue_context import DialogueContextState
from .error_blueprint import ErrorBlueprint
from .llm_client import OpenAICompatClient, require_keys
from .prompts import SEMANTIC_PRESERVATION_REVIEW_SYSTEM_PROMPT
from .student_turn_state import TaskLocalLearnerState
from .transition import StateTransitionPrediction
from .tutor_turn_profile import TutorTurnProfile


@dataclass(frozen=True)
class SemanticPreservationCheck:
    passed: bool
    fallback_to_draft: bool
    hard_fail_reasons: list[str]
    llm_fail_reasons: list[str]
    llm_review_used: bool


def review_semantic_preservation(
    draft_turn: str,
    realized_turn: str,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: TaskLocalLearnerState,
    transition_prediction: StateTransitionPrediction,
    error_blueprint: ErrorBlueprint,
    constraint_bundle: BehaviorHarness,
    llm_client: OpenAICompatClient,
) -> SemanticPreservationCheck:
    if not draft_turn.strip():
        raise ValueError("draft_turn cannot be empty")
    if not realized_turn.strip():
        raise ValueError("realized_turn cannot be empty")
    return review_semantic_preservation_with_llm(
        draft_turn=draft_turn,
        realized_turn=realized_turn,
        context=context,
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        transition_prediction=transition_prediction,
        error_blueprint=error_blueprint,
        constraint_bundle=constraint_bundle,
        llm_client=llm_client,
    )


def review_semantic_preservation_with_llm(
    draft_turn: str,
    realized_turn: str,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: TaskLocalLearnerState,
    transition_prediction: StateTransitionPrediction,
    error_blueprint: ErrorBlueprint,
    constraint_bundle: BehaviorHarness,
    llm_client: OpenAICompatClient,
) -> SemanticPreservationCheck:
    payload = {
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "interaction_state": asdict(interaction_state),
        "state_transition_prediction": asdict(transition_prediction),
        "error_blueprint": asdict(error_blueprint),
        "constraint_bundle": asdict(constraint_bundle),
        "draft_turn": draft_turn,
        "realized_turn": realized_turn,
        "required_schema": {
            "passed": "boolean",
            "changed_math_content": "boolean",
            "changed_correctness": "boolean",
            "changed_error_path": "boolean",
            "changed_uncertainty": "boolean",
            "changed_turn_function": "boolean",
            "rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=SEMANTIC_PRESERVATION_REVIEW_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_semantic_preservation_check(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=SEMANTIC_PRESERVATION_REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_semantic_preservation_check(repaired)


def semantic_preservation_check_to_dict(
    check: SemanticPreservationCheck,
) -> dict[str, object]:
    return asdict(check)


def _parse_semantic_preservation_check(parsed: object) -> SemanticPreservationCheck:
    parsed = require_keys(
        parsed,
        (
            "passed",
            "changed_math_content",
            "changed_correctness",
            "changed_error_path",
            "changed_uncertainty",
            "changed_turn_function",
            "rationale",
        ),
        "SemanticPreservationCheck",
    )
    passed = _coerce_bool(parsed["passed"], "passed")
    changed_math_content = _coerce_bool(parsed["changed_math_content"], "changed_math_content")
    changed_correctness = _coerce_bool(parsed["changed_correctness"], "changed_correctness")
    changed_error_path = _coerce_bool(parsed["changed_error_path"], "changed_error_path")
    changed_uncertainty = _coerce_bool(parsed["changed_uncertainty"], "changed_uncertainty")
    changed_turn_function = _coerce_bool(parsed["changed_turn_function"], "changed_turn_function")
    rationale = _coerce_str_list(parsed["rationale"], "rationale")

    fail_reasons: list[str] = []
    if changed_math_content:
        fail_reasons.append("math content changed")
    if changed_correctness:
        fail_reasons.append("correctness changed")
    if changed_error_path:
        fail_reasons.append("error path changed")
    if changed_uncertainty:
        fail_reasons.append("uncertainty changed")
    if changed_turn_function:
        fail_reasons.append("turn function changed")
    if passed and fail_reasons:
        raise ValueError("semantic preservation review marked passed despite semantic changes")
    if not passed and not fail_reasons:
        fail_reasons = list(rationale)
    return SemanticPreservationCheck(
        passed=passed,
        fallback_to_draft=not passed,
        hard_fail_reasons=[],
        llm_fail_reasons=fail_reasons,
        llm_review_used=True,
    )
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
