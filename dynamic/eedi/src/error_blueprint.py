from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .dialogue_context import DialogueContextState
from .llm_client import OpenAICompatClient, require_keys
from .population_calibration import (
    PopulationCalibrationSummary,
    population_calibration_summary_to_dict,
)
from .prompts import ERROR_BLUEPRINT_SYSTEM_PROMPT
from .student_model import StudentContextProfile
from .student_turn_state import InteractionState
from .transition import StateTransitionPrediction
from .tutor_turn_profile import TutorTurnProfile


ERROR_PRESENCE_STATES = (
    "no_specific_error",
    "non_codable_confusion",
    "codable_math_error",
)
NEWMAN_ERROR_LOCI = (
    "reading",
    "comprehension",
    "transformation",
    "process_skills",
    "encoding",
)
RADATZ_ERROR_MECHANISMS = (
    "language_difficulty",
    "spatial_information_difficulty",
    "deficient_prerequisites",
    "incorrect_associations",
    "irrelevant_rules",
)


@dataclass(frozen=True)
class ErrorBlueprint:
    error_presence: str
    newman_error_locus: str | None
    radatz_error_mechanism: str | None
    buggy_rule: str | None
    wrong_claim_seed: str | None
    blueprint_evidence: list[str]


def build_error_blueprint(
    student_context_profile: StudentContextProfile,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: InteractionState,
    transition_prediction: StateTransitionPrediction,
    llm_client: OpenAICompatClient,
    population_calibration_summary: PopulationCalibrationSummary | None = None,
) -> ErrorBlueprint:
    payload = {
        "student_context_profile": asdict(student_context_profile),
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "interaction_state": asdict(interaction_state),
        "state_transition_prediction": asdict(transition_prediction),
        "population_calibration_summary": population_calibration_summary_to_dict(
            population_calibration_summary
        ),
        "theory_decision_cues": {
            "tutor_is_eliciting_local_math_content": _tutor_is_eliciting_local_math_content(
                tutor_profile
            ),
            "elicited_response_process": tutor_profile.elicited_response_process,
            "elicited_response_target_type": tutor_profile.elicited_response_target_type,
            "elicited_object_description": tutor_profile.elicited_object_description,
            "student_is_expected_to_attempt_math_now": (
                transition_prediction.predicted_next_attempt_readiness
                in {"ready_for_local_attempt", "ready_to_revise"}
            ),
            "misconception_continuity_is_live": (
                transition_prediction.predicted_next_misconception_status
                in {"active_misconception", "destabilizing_misconception"}
                or transition_prediction.predicted_misconception_trajectory_shift
                in {"hold_trajectory", "perturb_trajectory"}
            ),
            "important_interpretation_note": (
                "Tentative wording does not by itself cancel a concrete mathematical error."
            ),
        },
        "required_schema": {
            "error_presence": list(ERROR_PRESENCE_STATES),
            "newman_error_locus": list(NEWMAN_ERROR_LOCI) + [None],
            "radatz_error_mechanism": list(RADATZ_ERROR_MECHANISMS) + [None],
            "buggy_rule": "string | null",
            "wrong_claim_seed": "string | null",
            "blueprint_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=ERROR_BLUEPRINT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_error_blueprint(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=ERROR_BLUEPRINT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_error_blueprint(repaired)


def error_blueprint_to_dict(blueprint: ErrorBlueprint) -> dict[str, object]:
    return asdict(blueprint)


def _tutor_is_eliciting_local_math_content(profile: TutorTurnProfile) -> bool:
    return (
        profile.support_type
        in {
            "conceptual_hint",
            "procedural_hint",
            "answer_elicitation",
            "error_challenge",
            "explanation_request",
        }
        and profile.target_of_intervention
        in {"misconception", "missing_step", "explanation_depth", "commitment"}
    )


def _parse_error_blueprint(parsed: object) -> ErrorBlueprint:
    parsed = require_keys(
        parsed,
        (
            "error_presence",
            "newman_error_locus",
            "radatz_error_mechanism",
            "buggy_rule",
            "wrong_claim_seed",
            "blueprint_evidence",
        ),
        "ErrorBlueprint",
    )
    error_presence = _coerce_enum(
        parsed["error_presence"],
        ERROR_PRESENCE_STATES,
        "error_presence",
    )
    blueprint_evidence = _coerce_str_list(
        parsed["blueprint_evidence"],
        "blueprint_evidence",
    )
    if error_presence == "codable_math_error":
        return ErrorBlueprint(
            error_presence=error_presence,
            newman_error_locus=_coerce_nullable_enum(
                parsed["newman_error_locus"],
                NEWMAN_ERROR_LOCI,
                "newman_error_locus",
                allow_null=False,
            ),
            radatz_error_mechanism=_coerce_nullable_enum(
                parsed["radatz_error_mechanism"],
                RADATZ_ERROR_MECHANISMS,
                "radatz_error_mechanism",
                allow_null=False,
            ),
            buggy_rule=_coerce_nullable_text(
                parsed["buggy_rule"],
                "buggy_rule",
                allow_null=False,
            ),
            wrong_claim_seed=_coerce_nullable_text(
                parsed["wrong_claim_seed"],
                "wrong_claim_seed",
                allow_null=False,
            ),
            blueprint_evidence=blueprint_evidence,
        )
    return ErrorBlueprint(
        error_presence=error_presence,
        newman_error_locus=_coerce_nullable_enum(
            parsed["newman_error_locus"],
            NEWMAN_ERROR_LOCI,
            "newman_error_locus",
            allow_null=True,
        ),
        radatz_error_mechanism=_coerce_nullable_enum(
            parsed["radatz_error_mechanism"],
            RADATZ_ERROR_MECHANISMS,
            "radatz_error_mechanism",
            allow_null=True,
        ),
        buggy_rule=_coerce_nullable_text(
            parsed["buggy_rule"],
            "buggy_rule",
            allow_null=True,
        ),
        wrong_claim_seed=_coerce_nullable_text(
            parsed["wrong_claim_seed"],
            "wrong_claim_seed",
            allow_null=True,
        ),
        blueprint_evidence=blueprint_evidence,
    )


def _coerce_enum(value: object, allowed: tuple[str, ...], field_name: str) -> str:
    text = str(value).strip()
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed}, got {text!r}")
    return text


def _coerce_nullable_enum(
    value: object,
    allowed: tuple[str, ...],
    field_name: str,
    allow_null: bool,
) -> str | None:
    if value is None:
        if allow_null:
            return None
        raise ValueError(f"{field_name} cannot be null")
    text = str(value).strip()
    if not text:
        if allow_null:
            return None
        raise ValueError(f"{field_name} cannot be empty")
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed}, got {text!r}")
    return text


def _coerce_nullable_text(
    value: object,
    field_name: str,
    allow_null: bool,
) -> str | None:
    if value is None:
        if allow_null:
            return None
        raise ValueError(f"{field_name} cannot be null")
    text = str(value).strip()
    if not text:
        if allow_null:
            return None
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result
