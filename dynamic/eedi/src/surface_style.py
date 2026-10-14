from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .constraint_bundle import BehaviorHarness
from .dialogue_context import DialogueContextState
from .error_blueprint import ErrorBlueprint
from .llm_client import OpenAICompatClient, require_keys
from .prompts import SURFACE_REALIZER_SYSTEM_PROMPT
from .student_model import StudentContextProfile
from .student_turn_state import TaskLocalLearnerState
from .transition import StateTransitionPrediction
from .tutor_turn_profile import TutorTurnProfile


@dataclass(frozen=True)
class SurfaceRealizedTurn:
    realized_turn: str
    realization_rationale: list[str]


def realize_student_surface_turn(
    student_context_profile: StudentContextProfile,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: TaskLocalLearnerState,
    transition_prediction: StateTransitionPrediction,
    error_blueprint: ErrorBlueprint,
    constraint_bundle: BehaviorHarness,
    draft_turn: str,
    llm_client: OpenAICompatClient,
) -> SurfaceRealizedTurn:
    payload = {
        "student_context_profile": asdict(student_context_profile),
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "interaction_state": asdict(interaction_state),
        "state_transition_prediction": asdict(transition_prediction),
        "error_blueprint": asdict(error_blueprint),
        "constraint_bundle": asdict(constraint_bundle),
        "draft_turn": draft_turn,
        "required_schema": {
            "realized_turn": "string",
            "realization_rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=SURFACE_REALIZER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["realized_turn"],
    )
    try:
        return _parse_surface_realized_turn(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=SURFACE_REALIZER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["realized_turn"],
        )
        return _parse_surface_realized_turn(repaired)


def surface_realized_turn_to_dict(turn: SurfaceRealizedTurn) -> dict[str, object]:
    return asdict(turn)


def _parse_surface_realized_turn(parsed: object) -> SurfaceRealizedTurn:
    parsed = require_keys(
        parsed,
        (
            "realized_turn",
            "realization_rationale",
        ),
        "SurfaceRealizedTurn",
    )
    realized_turn = str(parsed["realized_turn"]).strip()
    if not realized_turn:
        raise ValueError("realized_turn cannot be empty")
    rationale = _coerce_str_list(parsed["realization_rationale"], "realization_rationale")
    return SurfaceRealizedTurn(
        realized_turn=realized_turn,
        realization_rationale=rationale,
    )


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result
