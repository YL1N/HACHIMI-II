from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .llm_client import OpenAICompatClient, require_keys
from .prompts import LEARNING_OPPORTUNITY_STATE_SYSTEM_PROMPT
from .weak_harness import (
    ABLATION_MODES,
    CLAIM_REQUIREMENT_STATES,
    LearningAccessState,
    MathClaimAffordanceState,
    MediatedTargetAvailabilityState,
    RESPONSE_SPACE_TYPES,
    StudentPrior,
    SupportUptake,
    SUCCESS_AFFORDANCE_STATES,
    TARGET_AVAILABILITY_STATES,
    TurnResponseConstraintState,
    TutorMove,
    VisibleContext,
    _coerce_enum,
    _coerce_nullable_text,
    _coerce_str_list,
)


EXPLANATORY_DEPTH_LEVELS = (
    "acknowledgment_only",
    "brief_reason",
    "one_local_relation",
)
CLAIM_PERMISSION_STATES = (
    "no_new_math_claim",
    "tentative_local_claim",
    "direct_local_claim",
)
SUPPORT_VISIBILITY_STATES = (
    "implicit_only",
    "brief_reference_allowed",
)


@dataclass(frozen=True)
class LearningOpportunityState:
    independently_available_acts: list[str]
    support_enabled_acts: list[str]
    still_unavailable_acts: list[str]
    salient_confusion_axes: list[str]
    response_space: str
    required_local_focus: str
    max_explanatory_depth: str
    opportunity_evidence: list[str]


@dataclass(frozen=True)
class OpportunityConstraintBundle:
    packet_version: str
    architecture_version: str
    ablation_mode: str
    local_focus: str
    access_zone: str
    response_space: str
    claim_requirement: str
    error_pressure: str
    target_availability: str
    success_affordance: str
    error_continuity_risk: str
    target_engagement_mode: str
    max_sentences: int
    claim_affordance: str
    error_opportunity: str
    expected_claim_shape: str
    local_error_presence: str
    local_newman_locus: str | None
    local_error_mechanism: str | None
    buggy_rule: str | None
    wrong_claim_seed: str | None
    claim_seed_mode: str
    support_consistent_claim_seed: str | None
    independently_available_acts: list[str]
    support_enabled_acts: list[str]
    still_unavailable_acts: list[str]
    salient_confusion_axes: list[str]
    claim_permission: str
    max_explanatory_depth: str
    tutor_support_visibility: str
    realization_requirements: list[str]
    allowed_actions: list[str]
    disallowed_actions: list[str]
    support_use_rules: list[str]
    packet_rationale: list[str]


def resolve_learning_opportunity_state(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    turn_response_constraint: TurnResponseConstraintState,
    llm_client: OpenAICompatClient,
) -> LearningOpportunityState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "mediated_target_availability": asdict(mediated_target_availability),
        "turn_response_constraint": asdict(turn_response_constraint),
        "required_schema": {
            "independently_available_acts": ["string"],
            "support_enabled_acts": ["string"],
            "still_unavailable_acts": ["string"],
            "salient_confusion_axes": ["string"],
            "response_space": list(RESPONSE_SPACE_TYPES),
            "required_local_focus": "string",
            "max_explanatory_depth": list(EXPLANATORY_DEPTH_LEVELS),
            "opportunity_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=LEARNING_OPPORTUNITY_STATE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["required_local_focus"],
    )
    try:
        return _parse_learning_opportunity_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=LEARNING_OPPORTUNITY_STATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["required_local_focus"],
        )
        return _parse_learning_opportunity_state(repaired)


def compile_opportunity_constraint_bundle(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    turn_response_constraint: TurnResponseConstraintState,
    learning_opportunity_state: LearningOpportunityState,
    ablation_mode: str = "baseline",
) -> OpportunityConstraintBundle:
    mode = _coerce_enum(ablation_mode, ABLATION_MODES, "ablation_mode")
    max_sentences_map = {
        "brief_acknowledgment": 1,
        "clarification_request": 2,
        "partial_attempt": 2,
        "revision_attempt": 2,
        "local_explanation": 3,
    }
    max_sentences = max_sentences_map[learning_opportunity_state.response_space]
    if mode == "protocol_light":
        max_sentences += 1

    claim_permission = _resolve_claim_permission(
        turn_response_constraint.claim_requirement
    )
    tutor_support_visibility = (
        "brief_reference_allowed"
        if support_uptake.uptake_depth in {"partial_use", "substantive_use"}
        else "implicit_only"
    )

    allowed_actions = [
        f"Stay on the exact local object: {learning_opportunity_state.required_local_focus}.",
        f"Use only independently available or support-enabled acts for this turn.",
        f"Realize the compiled response space: {learning_opportunity_state.response_space}.",
    ]
    if claim_permission != "no_new_math_claim":
        allowed_actions.append(
            "A short local mathematical attempt is allowed if it stays within the current opportunity."
        )
    if tutor_support_visibility == "brief_reference_allowed":
        allowed_actions.append("A brief reference to the tutor's cue is allowed.")

    disallowed_actions = [
        "Do not produce a full worked solution.",
        "Do not add new math content outside the local focus.",
        "Do not use acts listed as still unavailable this turn.",
        "Do not answer like a tutor or evaluator.",
        "Do not use future information or future turns.",
        "Do not use a prewritten wrong answer script.",
    ]
    if claim_permission == "no_new_math_claim":
        disallowed_actions.append("Do not invent a new standalone mathematical answer.")

    support_use_rules = [
        f"Current target availability is {mediated_target_availability.target_availability}.",
        f"Success affordance is {mediated_target_availability.success_affordance}.",
        (
            "Use tutor support only to unlock one local step, not to jump to full mastery."
        ),
    ]

    realization_requirements = [
        f"Keep the turn within {max_sentences} sentence(s).",
        f"Stay on local focus: {learning_opportunity_state.required_local_focus}.",
        f"Response space must be {learning_opportunity_state.response_space}.",
        f"Claim requirement is {turn_response_constraint.claim_requirement}.",
        f"Max explanatory depth is {learning_opportunity_state.max_explanatory_depth}.",
    ]

    packet_rationale = [
        "v5 compiles opportunity structure rather than a prewritten answer script.",
        (
            f"Access zone is {learning_access_state.access_zone}; "
            f"uptake depth is {support_uptake.uptake_depth}."
        ),
        (
            "The bundle exposes what is independently available, support-enabled, "
            "and still unavailable this turn."
        ),
        (
            "Current opportunity keeps the tutor-local focus at "
            f"{learning_opportunity_state.required_local_focus}."
        ),
    ]

    return OpportunityConstraintBundle(
        packet_version="eedi_weak_harness_v5.0",
        architecture_version="v5",
        ablation_mode=mode,
        local_focus=learning_opportunity_state.required_local_focus,
        access_zone=learning_access_state.access_zone,
        response_space=learning_opportunity_state.response_space,
        claim_requirement=turn_response_constraint.claim_requirement,
        error_pressure=turn_response_constraint.error_pressure,
        target_availability=mediated_target_availability.target_availability,
        success_affordance=mediated_target_availability.success_affordance,
        error_continuity_risk=mediated_target_availability.error_continuity_risk,
        target_engagement_mode=support_uptake.likely_next_engagement_mode,
        max_sentences=max_sentences,
        claim_affordance=math_claim_affordance.claim_affordance,
        error_opportunity="deferred_to_weak_actor",
        expected_claim_shape=math_claim_affordance.expected_claim_shape,
        local_error_presence="deferred_to_posthoc",
        local_newman_locus=None,
        local_error_mechanism=None,
        buggy_rule=None,
        wrong_claim_seed=None,
        claim_seed_mode="none_in_v5",
        support_consistent_claim_seed=None,
        independently_available_acts=list(
            learning_opportunity_state.independently_available_acts
        ),
        support_enabled_acts=list(learning_opportunity_state.support_enabled_acts),
        still_unavailable_acts=list(learning_opportunity_state.still_unavailable_acts),
        salient_confusion_axes=list(learning_opportunity_state.salient_confusion_axes),
        claim_permission=claim_permission,
        max_explanatory_depth=learning_opportunity_state.max_explanatory_depth,
        tutor_support_visibility=tutor_support_visibility,
        realization_requirements=realization_requirements,
        allowed_actions=allowed_actions,
        disallowed_actions=disallowed_actions,
        support_use_rules=support_use_rules,
        packet_rationale=packet_rationale,
    )


def _parse_learning_opportunity_state(parsed: object) -> LearningOpportunityState:
    parsed = require_keys(
        parsed,
        (
            "independently_available_acts",
            "support_enabled_acts",
            "still_unavailable_acts",
            "salient_confusion_axes",
            "response_space",
            "required_local_focus",
            "max_explanatory_depth",
            "opportunity_evidence",
        ),
        "LearningOpportunityState",
    )
    return LearningOpportunityState(
        independently_available_acts=_coerce_str_list(
            parsed["independently_available_acts"],
            "independently_available_acts",
        ),
        support_enabled_acts=_coerce_str_list(
            parsed["support_enabled_acts"],
            "support_enabled_acts",
        ),
        still_unavailable_acts=_coerce_str_list(
            parsed["still_unavailable_acts"],
            "still_unavailable_acts",
        ),
        salient_confusion_axes=_coerce_str_list(
            parsed["salient_confusion_axes"],
            "salient_confusion_axes",
        ),
        response_space=_coerce_enum(
            parsed["response_space"],
            RESPONSE_SPACE_TYPES,
            "response_space",
        ),
        required_local_focus=(
            _coerce_nullable_text(parsed["required_local_focus"], "required_local_focus")
            or ""
        ),
        max_explanatory_depth=_coerce_enum(
            parsed["max_explanatory_depth"],
            EXPLANATORY_DEPTH_LEVELS,
            "max_explanatory_depth",
        ),
        opportunity_evidence=_coerce_str_list(
            parsed["opportunity_evidence"],
            "opportunity_evidence",
        ),
    )


def _resolve_claim_permission(claim_requirement: str) -> str:
    requirement = _coerce_enum(
        claim_requirement,
        CLAIM_REQUIREMENT_STATES,
        "claim_requirement",
    )
    if requirement == "no_claim":
        return "no_new_math_claim"
    if requirement == "tentative_claim_allowed":
        return "tentative_local_claim"
    return "direct_local_claim"
