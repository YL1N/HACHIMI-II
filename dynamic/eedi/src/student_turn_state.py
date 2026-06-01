from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .dialogue_context import DialogueContextState
from .llm_client import OpenAICompatClient, require_keys
from .population_calibration import (
    PopulationCalibrationSummary,
    population_calibration_summary_to_dict,
)
from .prompts import INTERACTION_STATE_SYSTEM_PROMPT
from .student_model import StudentContextProfile
from .tutor_turn_profile import TutorTurnProfile


COMPETENCE_POSITIONS = (
    "within_current_competence",
    "within_zpd",
    "beyond_zpd",
)
MISCONCEPTION_STATUSES = (
    "not_salient",
    "active_misconception",
    "destabilizing_misconception",
    "resolved_misconception",
)
METACOG_STATES = (
    "unmonitored",
    "weak_monitoring",
    "active_monitoring",
    "self_correcting",
)
HELP_INTERNALIZATION_STATES = (
    "no_uptake",
    "surface_uptake",
    "partial_internalization",
    "integrated_internalization",
)
HELP_SEEKING_STATES = (
    "help_avoidant",
    "help_ambivalent",
    "adaptive_help_seeking",
)
ATTEMPT_READINESS_STATES = (
    "not_ready",
    "ready_for_local_attempt",
    "ready_to_revise",
)
ENGAGEMENT_FORMS = ("Passive", "Active", "Constructive", "Interactive")
COMMITMENT_STATES = ("avoidant", "tentative", "committed")
MATURITY_CAPS = (
    "fragment_only",
    "brief_local_explanation",
    "limited_structured_reasoning",
    "full_student_level_reasoning",
)


@dataclass(frozen=True)
class InteractionState:
    competence_position: str
    misconception_status: str
    metacognitive_regulation_state: str
    help_internalization_state: str
    help_seeking_state: str
    attempt_readiness: str
    engagement_form: str
    response_commitment_state: str
    response_maturity_cap: str
    state_evidence: list[str]


def resolve_interaction_state(
    student_context_profile: StudentContextProfile,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    llm_client: OpenAICompatClient,
    population_calibration_summary: PopulationCalibrationSummary | None = None,
) -> InteractionState:
    payload = {
        "student_context_profile": asdict(student_context_profile),
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "population_calibration_summary": population_calibration_summary_to_dict(
            population_calibration_summary
        ),
        "state_definitions": {
            "competence_position": list(COMPETENCE_POSITIONS),
            "misconception_status": list(MISCONCEPTION_STATUSES),
            "metacognitive_regulation_state": list(METACOG_STATES),
            "help_internalization_state": list(HELP_INTERNALIZATION_STATES),
            "help_seeking_state": list(HELP_SEEKING_STATES),
            "attempt_readiness": list(ATTEMPT_READINESS_STATES),
            "engagement_form": list(ENGAGEMENT_FORMS),
            "response_commitment_state": list(COMMITMENT_STATES),
            "response_maturity_cap": list(MATURITY_CAPS),
        },
        "required_schema": {
            "competence_position": list(COMPETENCE_POSITIONS),
            "misconception_status": list(MISCONCEPTION_STATUSES),
            "metacognitive_regulation_state": list(METACOG_STATES),
            "help_internalization_state": list(HELP_INTERNALIZATION_STATES),
            "help_seeking_state": list(HELP_SEEKING_STATES),
            "attempt_readiness": list(ATTEMPT_READINESS_STATES),
            "engagement_form": list(ENGAGEMENT_FORMS),
            "response_commitment_state": list(COMMITMENT_STATES),
            "response_maturity_cap": list(MATURITY_CAPS),
            "state_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=INTERACTION_STATE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_interaction_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=INTERACTION_STATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_interaction_state(repaired)


def interaction_state_to_dict(state: InteractionState) -> dict[str, object]:
    return asdict(state)


def _parse_interaction_state(parsed: object) -> InteractionState:
    parsed = require_keys(
        parsed,
        (
            "competence_position",
            "misconception_status",
            "metacognitive_regulation_state",
            "help_internalization_state",
            "help_seeking_state",
            "attempt_readiness",
            "engagement_form",
            "response_commitment_state",
            "response_maturity_cap",
            "state_evidence",
        ),
        "InteractionState",
    )
    return InteractionState(
        competence_position=_coerce_enum(
            parsed["competence_position"],
            COMPETENCE_POSITIONS,
            "competence_position",
        ),
        misconception_status=_coerce_enum(
            parsed["misconception_status"],
            MISCONCEPTION_STATUSES,
            "misconception_status",
        ),
        metacognitive_regulation_state=_coerce_enum(
            parsed["metacognitive_regulation_state"],
            METACOG_STATES,
            "metacognitive_regulation_state",
        ),
        help_internalization_state=_coerce_enum(
            parsed["help_internalization_state"],
            HELP_INTERNALIZATION_STATES,
            "help_internalization_state",
        ),
        help_seeking_state=_coerce_enum(
            parsed["help_seeking_state"],
            HELP_SEEKING_STATES,
            "help_seeking_state",
        ),
        attempt_readiness=_coerce_enum(
            parsed["attempt_readiness"],
            ATTEMPT_READINESS_STATES,
            "attempt_readiness",
        ),
        engagement_form=_coerce_enum(
            parsed["engagement_form"],
            ENGAGEMENT_FORMS,
            "engagement_form",
        ),
        response_commitment_state=_coerce_enum(
            parsed["response_commitment_state"],
            COMMITMENT_STATES,
            "response_commitment_state",
        ),
        response_maturity_cap=_coerce_enum(
            parsed["response_maturity_cap"],
            MATURITY_CAPS,
            "response_maturity_cap",
        ),
        state_evidence=_coerce_str_list(parsed["state_evidence"], "state_evidence"),
    )


def _coerce_enum(value: object, allowed: tuple[str, ...], field_name: str) -> str:
    text = str(value).strip()
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed}, got {text!r}")
    return text


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result
