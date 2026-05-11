from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .dialogue_context import DialogueContextState
from .llm_client import OpenAICompatClient, require_keys
from .prompts import TUTOR_TURN_PROFILE_SYSTEM_PROMPT


SUPPORT_TYPES = (
    "conceptual_hint",
    "procedural_hint",
    "answer_elicitation",
    "error_challenge",
    "explanation_request",
    "reassurance",
    "manage_dialogue",
)
SUPPORT_INTENSITIES = ("weak", "medium", "strong")
SUPPORT_GRANULARITIES = ("minimal_cue", "localized_step", "multi_step_guidance")
SUPPORT_CONTINGENCIES = (
    "weakly_contingent",
    "moderately_contingent",
    "tightly_contingent",
)
RESPONSIBILITY_SHIFTS = ("tutor_led", "shared", "student_led")
INTERVENTION_TARGETS = (
    "misconception",
    "missing_step",
    "confidence",
    "commitment",
    "explanation_depth",
    "dialogue_flow",
)
UPTAKE_EXPECTATIONS = (
    "no_change",
    "local_update",
    "partial_restructuring",
    "strong_restructuring",
)
ELICITED_RESPONSE_PROCESSES = (
    "formulate",
    "employ",
    "interpret_evaluate",
    "communicate_reasoning",
)
ELICITED_RESPONSE_TARGET_TYPES = (
    "representation",
    "procedure_step",
    "result_or_selection",
    "explanation_or_judgment",
)


@dataclass(frozen=True)
class TutorTurnProfile:
    instructional_intent: str
    support_type: str
    support_intensity: str
    support_granularity: str
    support_contingency: str
    responsibility_shift: str
    target_of_intervention: str
    uptake_expectation: str
    elicited_response_process: str
    elicited_response_target_type: str
    elicited_object_description: str
    move_evidence: list[str]


def build_tutor_turn_profile(
    context: DialogueContextState,
    llm_client: OpenAICompatClient,
) -> TutorTurnProfile:
    payload = {
        "dialogue_context": asdict(context),
        "field_notes": {
            "support_type_options": list(SUPPORT_TYPES),
            "support_intensity_options": list(SUPPORT_INTENSITIES),
            "support_granularity_options": list(SUPPORT_GRANULARITIES),
            "support_contingency_options": list(SUPPORT_CONTINGENCIES),
            "responsibility_shift_options": list(RESPONSIBILITY_SHIFTS),
            "target_of_intervention_options": list(INTERVENTION_TARGETS),
            "uptake_expectation_options": list(UPTAKE_EXPECTATIONS),
            "elicited_response_process_options": list(ELICITED_RESPONSE_PROCESSES),
            "elicited_response_target_type_options": list(ELICITED_RESPONSE_TARGET_TYPES),
        },
        "required_schema": {
            "instructional_intent": "string",
            "support_type": list(SUPPORT_TYPES),
            "support_intensity": list(SUPPORT_INTENSITIES),
            "support_granularity": list(SUPPORT_GRANULARITIES),
            "support_contingency": list(SUPPORT_CONTINGENCIES),
            "responsibility_shift": list(RESPONSIBILITY_SHIFTS),
            "target_of_intervention": list(INTERVENTION_TARGETS),
            "uptake_expectation": list(UPTAKE_EXPECTATIONS),
            "elicited_response_process": list(ELICITED_RESPONSE_PROCESSES),
            "elicited_response_target_type": list(ELICITED_RESPONSE_TARGET_TYPES),
            "elicited_object_description": "string",
            "move_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=TUTOR_TURN_PROFILE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_tutor_turn_profile(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=TUTOR_TURN_PROFILE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_tutor_turn_profile(repaired)


def tutor_turn_profile_to_dict(profile: TutorTurnProfile) -> dict[str, object]:
    return asdict(profile)


def _parse_tutor_turn_profile(parsed: object) -> TutorTurnProfile:
    parsed = require_keys(
        parsed,
        (
            "instructional_intent",
            "support_type",
            "support_intensity",
            "support_granularity",
            "support_contingency",
            "responsibility_shift",
            "target_of_intervention",
            "uptake_expectation",
            "elicited_response_process",
            "elicited_response_target_type",
            "elicited_object_description",
            "move_evidence",
        ),
        "TutorTurnProfile",
    )
    return TutorTurnProfile(
        instructional_intent=_coerce_text(parsed["instructional_intent"], "instructional_intent"),
        support_type=_coerce_enum(parsed["support_type"], SUPPORT_TYPES, "support_type"),
        support_intensity=_coerce_enum(
            parsed["support_intensity"],
            SUPPORT_INTENSITIES,
            "support_intensity",
        ),
        support_granularity=_coerce_enum(
            parsed["support_granularity"],
            SUPPORT_GRANULARITIES,
            "support_granularity",
        ),
        support_contingency=_coerce_enum(
            parsed["support_contingency"],
            SUPPORT_CONTINGENCIES,
            "support_contingency",
        ),
        responsibility_shift=_coerce_enum(
            parsed["responsibility_shift"],
            RESPONSIBILITY_SHIFTS,
            "responsibility_shift",
        ),
        target_of_intervention=_coerce_enum(
            parsed["target_of_intervention"],
            INTERVENTION_TARGETS,
            "target_of_intervention",
        ),
        uptake_expectation=_coerce_enum(
            parsed["uptake_expectation"],
            UPTAKE_EXPECTATIONS,
            "uptake_expectation",
        ),
        elicited_response_process=_coerce_enum(
            parsed["elicited_response_process"],
            ELICITED_RESPONSE_PROCESSES,
            "elicited_response_process",
        ),
        elicited_response_target_type=_coerce_enum(
            parsed["elicited_response_target_type"],
            ELICITED_RESPONSE_TARGET_TYPES,
            "elicited_response_target_type",
        ),
        elicited_object_description=_coerce_text(
            parsed["elicited_object_description"],
            "elicited_object_description",
        ),
        move_evidence=_coerce_str_list(parsed["move_evidence"], "move_evidence"),
    )


def _coerce_text(value: object, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _coerce_enum(value: object, allowed: tuple[str, ...], field_name: str) -> str:
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError(
                f"{field_name} must be one of {allowed}, got {value!r}; raw_value={value!r}"
            )
        value = value[0]
    text = _coerce_text(value, field_name)
    if text not in allowed:
        raise ValueError(
            f"{field_name} must be one of {allowed}, got {text!r}; raw_value={value!r}"
        )
    return text


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result
