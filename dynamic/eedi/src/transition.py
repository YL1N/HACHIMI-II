from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

from .dialogue_context import DialogueContextState
from .llm_client import OpenAICompatClient, require_keys
from .persona_prior import (
    PersonaPriorSummary,
    persona_prior_summary_to_dict,
)
from .prompts import STATE_TRANSITION_SYSTEM_PROMPT
from .student_model import StudentContextProfile
from .student_turn_state import (
    ATTEMPT_READINESS_STATES,
    COMPETENCE_POSITIONS,
    COMMITMENT_STATES,
    ENGAGEMENT_FORMS,
    HELP_SEEKING_STATES,
    HELP_INTERNALIZATION_STATES,
    MATURITY_CAPS,
    METACOG_STATES,
    MISCONCEPTION_STATUSES,
    TaskLocalLearnerState,
)
from .tutor_turn_profile import TutorTurnProfile

MISCONCEPTION_TRAJECTORY_SHIFTS = (
    "hold_trajectory",
    "perturb_trajectory",
    "local_repair",
    "consolidate_repair",
)


@dataclass(frozen=True)
class StateTransitionPrediction:
    predicted_next_competence_position: str
    predicted_next_misconception_status: str
    predicted_next_metacognitive_regulation_state: str
    predicted_next_help_internalization_state: str
    predicted_next_help_seeking_state: str
    predicted_next_attempt_readiness: str
    predicted_next_engagement_form: str
    predicted_next_response_commitment_state: str
    predicted_next_response_maturity_cap: str
    predicted_misconception_trajectory_shift: str
    transition_rationale: list[str]


def predict_state_transition(
    student_context_profile: StudentContextProfile,
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: TaskLocalLearnerState,
    llm_client: OpenAICompatClient,
    persona_prior_summary: PersonaPriorSummary | None = None,
) -> StateTransitionPrediction:
    payload = {
        "student_context_profile": asdict(student_context_profile),
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "interaction_state": asdict(interaction_state),
        "persona_prior_summary": persona_prior_summary_to_dict(
            persona_prior_summary
        ),
        "required_schema": {
            "predicted_next_competence_position": list(COMPETENCE_POSITIONS),
            "predicted_next_misconception_status": list(MISCONCEPTION_STATUSES),
            "predicted_next_metacognitive_regulation_state": list(METACOG_STATES),
            "predicted_next_help_internalization_state": list(HELP_INTERNALIZATION_STATES),
            "predicted_next_help_seeking_state": list(HELP_SEEKING_STATES),
            "predicted_next_attempt_readiness": list(ATTEMPT_READINESS_STATES),
            "predicted_next_engagement_form": list(ENGAGEMENT_FORMS),
            "predicted_next_response_commitment_state": list(COMMITMENT_STATES),
            "predicted_next_response_maturity_cap": list(MATURITY_CAPS),
            "predicted_misconception_trajectory_shift": list(MISCONCEPTION_TRAJECTORY_SHIFTS),
            "transition_rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=STATE_TRANSITION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        prediction = _parse_state_transition_prediction(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=STATE_TRANSITION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        prediction = _parse_state_transition_prediction(repaired)
    return _apply_transition_policies(
        context=context,
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        prediction=prediction,
    )


def state_transition_prediction_to_dict(
    prediction: StateTransitionPrediction,
) -> dict[str, object]:
    return asdict(prediction)


def _parse_state_transition_prediction(parsed: object) -> StateTransitionPrediction:
    parsed = require_keys(
        parsed,
        (
            "predicted_next_competence_position",
            "predicted_next_misconception_status",
            "predicted_next_metacognitive_regulation_state",
            "predicted_next_help_internalization_state",
            "predicted_next_help_seeking_state",
            "predicted_next_attempt_readiness",
            "predicted_next_engagement_form",
            "predicted_next_response_commitment_state",
            "predicted_next_response_maturity_cap",
            "predicted_misconception_trajectory_shift",
            "transition_rationale",
        ),
        "StateTransitionPrediction",
    )
    return StateTransitionPrediction(
        predicted_next_competence_position=_coerce_enum(
            parsed["predicted_next_competence_position"],
            COMPETENCE_POSITIONS,
            "predicted_next_competence_position",
        ),
        predicted_next_misconception_status=_coerce_enum(
            parsed["predicted_next_misconception_status"],
            MISCONCEPTION_STATUSES,
            "predicted_next_misconception_status",
        ),
        predicted_next_metacognitive_regulation_state=_coerce_enum(
            parsed["predicted_next_metacognitive_regulation_state"],
            METACOG_STATES,
            "predicted_next_metacognitive_regulation_state",
        ),
        predicted_next_help_internalization_state=_coerce_enum(
            parsed["predicted_next_help_internalization_state"],
            HELP_INTERNALIZATION_STATES,
            "predicted_next_help_internalization_state",
        ),
        predicted_next_help_seeking_state=_coerce_enum(
            parsed["predicted_next_help_seeking_state"],
            HELP_SEEKING_STATES,
            "predicted_next_help_seeking_state",
        ),
        predicted_next_attempt_readiness=_coerce_enum(
            parsed["predicted_next_attempt_readiness"],
            ATTEMPT_READINESS_STATES,
            "predicted_next_attempt_readiness",
        ),
        predicted_next_engagement_form=_coerce_enum(
            parsed["predicted_next_engagement_form"],
            ENGAGEMENT_FORMS,
            "predicted_next_engagement_form",
        ),
        predicted_next_response_commitment_state=_coerce_enum(
            parsed["predicted_next_response_commitment_state"],
            COMMITMENT_STATES,
            "predicted_next_response_commitment_state",
        ),
        predicted_next_response_maturity_cap=_coerce_enum(
            parsed["predicted_next_response_maturity_cap"],
            MATURITY_CAPS,
            "predicted_next_response_maturity_cap",
        ),
        predicted_misconception_trajectory_shift=_coerce_enum(
            parsed["predicted_misconception_trajectory_shift"],
            MISCONCEPTION_TRAJECTORY_SHIFTS,
            "predicted_misconception_trajectory_shift",
        ),
        transition_rationale=_coerce_str_list(
            parsed["transition_rationale"],
            "transition_rationale",
        ),
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


def _apply_transition_policies(
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    interaction_state: TaskLocalLearnerState,
    prediction: StateTransitionPrediction,
) -> StateTransitionPrediction:
    prediction = _apply_misconception_persistence_policy(
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        prediction=prediction,
    )
    return _apply_dialogue_management_policy(
        context=context,
        tutor_profile=tutor_profile,
        prediction=prediction,
    )


def _apply_misconception_persistence_policy(
    tutor_profile: TutorTurnProfile,
    interaction_state: TaskLocalLearnerState,
    prediction: StateTransitionPrediction,
) -> StateTransitionPrediction:
    if interaction_state.misconception_status not in {
        "active_misconception",
        "destabilizing_misconception",
    }:
        return prediction
    if prediction.predicted_misconception_trajectory_shift not in {
        "local_repair",
        "consolidate_repair",
    }:
        return prediction

    strong_restructuring_support = (
        tutor_profile.support_intensity == "strong"
        and tutor_profile.support_granularity == "multi_step_guidance"
        and tutor_profile.uptake_expectation == "strong_restructuring"
        and tutor_profile.responsibility_shift in {"tutor_led", "shared"}
    )
    if strong_restructuring_support:
        return prediction

    rationale = list(prediction.transition_rationale)
    rationale.append(
        "A live misconception should not be upgraded to local repair or consolidated repair "
        "after only limited support; keep the next state on the same misconception path unless "
        "there is strong restructuring evidence."
    )

    next_status = prediction.predicted_next_misconception_status
    if interaction_state.misconception_status == "active_misconception":
        if next_status in {"resolved_misconception", "not_salient"}:
            next_status = "destabilizing_misconception"
    else:
        if next_status in {"resolved_misconception", "not_salient"}:
            next_status = "destabilizing_misconception"

    next_shift = (
        "perturb_trajectory"
        if interaction_state.attempt_readiness in {"ready_for_local_attempt", "ready_to_revise"}
        else "hold_trajectory"
    )
    return replace(
        prediction,
        predicted_next_misconception_status=next_status,
        predicted_misconception_trajectory_shift=next_shift,
        transition_rationale=rationale,
    )


def _apply_dialogue_management_policy(
    context: DialogueContextState,
    tutor_profile: TutorTurnProfile,
    prediction: StateTransitionPrediction,
) -> StateTransitionPrediction:
    is_dialogue_management_turn = (
        tutor_profile.support_type in {"reassurance", "manage_dialogue"}
        and tutor_profile.target_of_intervention in {"confidence", "dialogue_flow"}
    )
    if not is_dialogue_management_turn:
        return prediction

    rationale = list(prediction.transition_rationale)
    rationale.append(
        "The tutor move is primarily social or dialogue-managing rather than a math reasoning request, "
        "so the next student turn should stay functionally local and non-expository."
    )
    return replace(
        prediction,
        predicted_next_engagement_form=(
            "Active"
            if not context.last_student_turn.strip()
            and prediction.predicted_next_engagement_form == "Passive"
            else "Active"
            if prediction.predicted_next_engagement_form in {"Constructive", "Interactive"}
            else prediction.predicted_next_engagement_form
        ),
        predicted_next_attempt_readiness="not_ready",
        predicted_next_response_commitment_state=(
            "tentative"
            if prediction.predicted_next_response_commitment_state == "committed"
            else prediction.predicted_next_response_commitment_state
        ),
        predicted_next_response_maturity_cap="fragment_only",
        predicted_misconception_trajectory_shift="hold_trajectory",
        transition_rationale=rationale,
    )
