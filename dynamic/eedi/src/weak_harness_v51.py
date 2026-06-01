from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .llm_client import OpenAICompatClient, require_keys
from .prompts import (
    LOCAL_BELIEF_STATE_SYSTEM_PROMPT,
    STUDENT_RESPONSE_POLICY_SYSTEM_PROMPT,
    SUPPORT_TRANSFORMATION_STATE_SYSTEM_PROMPT,
)
from .weak_harness import (
    ABLATION_MODES,
    LearningAccessState,
    MathClaimAffordanceState,
    MediatedTargetAvailabilityState,
    StudentPrior,
    SupportUptake,
    TutorMove,
    VisibleContext,
    _coerce_enum,
    _coerce_nullable_text,
    _coerce_str_list,
)


POLICY_LEVELS = ("low", "medium", "high")
BELIEF_STATUSES = (
    "no_commitment",
    "tentative_guess",
    "stable_guess",
    "socially_justified_guess",
    "partial_rule_fragment",
    "refusal_or_shutdown",
)
JUSTIFICATION_BASES = (
    "none",
    "social_authority",
    "intuition",
    "surface_pattern",
    "partial_rule",
    "refusal",
)
REVISION_READINESS_STATES = ("resistant", "unstable", "open")
TRANSFORMATION_TYPES = (
    "stabilize_prior_commitment",
    "destabilize_prior_commitment",
    "redirect_to_rule",
    "ignored_support",
    "misapplied_support",
    "activate_guess",
)
RESPONSE_FAMILIES = (
    "brief_acknowledgment",
    "clarification_request",
    "direct_guess",
    "shallow_revision",
    "social_justification",
    "brief_rule_echo",
    "refusal_or_shutdown",
)
CLAIM_LIKELIHOOD_STATES = ("prohibited", "optional", "likely")


@dataclass(frozen=True)
class StudentResponsePolicyState:
    help_seeking_tendency: str
    guessing_tendency: str
    social_justification_tendency: str
    refusal_tendency: str
    revision_volatility: str
    policy_evidence: list[str]


@dataclass(frozen=True)
class LocalBeliefState:
    belief_status: str
    committed_content: str | None
    justification_basis: str
    confidence_posture: str
    revision_readiness: str
    belief_evidence: list[str]


@dataclass(frozen=True)
class SupportTransformationState:
    transformation_type: str
    preferred_response_family: str
    allowed_response_families: list[str]
    claim_likelihood: str
    transformation_evidence: list[str]


@dataclass(frozen=True)
class OpportunityConstraintBundleV51:
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
    preferred_response_family: str
    allowed_response_families: list[str]
    claim_likelihood: str
    preserve_prior_commitment: bool
    allow_social_justification: bool
    discourage_clarification: bool
    independently_available_acts: list[str]
    support_enabled_acts: list[str]
    still_unavailable_acts: list[str]
    salient_confusion_axes: list[str]
    realization_requirements: list[str]
    allowed_actions: list[str]
    disallowed_actions: list[str]
    support_use_rules: list[str]
    packet_rationale: list[str]


def resolve_student_response_policy(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    llm_client: OpenAICompatClient,
) -> StudentResponsePolicyState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "required_schema": {
            "help_seeking_tendency": list(POLICY_LEVELS),
            "guessing_tendency": list(POLICY_LEVELS),
            "social_justification_tendency": list(POLICY_LEVELS),
            "refusal_tendency": list(POLICY_LEVELS),
            "revision_volatility": list(POLICY_LEVELS),
            "policy_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=STUDENT_RESPONSE_POLICY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_student_response_policy_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=STUDENT_RESPONSE_POLICY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_student_response_policy_state(repaired)


def resolve_local_belief_state(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    llm_client: OpenAICompatClient,
) -> LocalBeliefState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "required_schema": {
            "belief_status": list(BELIEF_STATUSES),
            "committed_content": "string | null",
            "justification_basis": list(JUSTIFICATION_BASES),
            "confidence_posture": list(POLICY_LEVELS),
            "revision_readiness": list(REVISION_READINESS_STATES),
            "belief_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=LOCAL_BELIEF_STATE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["committed_content"],
    )
    try:
        return _parse_local_belief_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=LOCAL_BELIEF_STATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["committed_content"],
        )
        return _parse_local_belief_state(repaired)


def resolve_support_transformation_state(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    student_response_policy: StudentResponsePolicyState,
    local_belief_state: LocalBeliefState,
    llm_client: OpenAICompatClient,
) -> SupportTransformationState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "mediated_target_availability": asdict(mediated_target_availability),
        "student_response_policy": asdict(student_response_policy),
        "local_belief_state": asdict(local_belief_state),
        "required_schema": {
            "transformation_type": list(TRANSFORMATION_TYPES),
            "preferred_response_family": list(RESPONSE_FAMILIES),
            "allowed_response_families": ["string"],
            "claim_likelihood": list(CLAIM_LIKELIHOOD_STATES),
            "transformation_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=SUPPORT_TRANSFORMATION_STATE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_support_transformation_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=SUPPORT_TRANSFORMATION_STATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_support_transformation_state(repaired)


def compile_opportunity_constraint_bundle_v51(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    learning_opportunity_state,
    student_response_policy: StudentResponsePolicyState,
    local_belief_state: LocalBeliefState,
    support_transformation_state: SupportTransformationState,
    ablation_mode: str = "baseline",
) -> OpportunityConstraintBundleV51:
    mode = _coerce_enum(ablation_mode, ABLATION_MODES, "ablation_mode")
    response_space = _map_response_space(
        support_transformation_state.preferred_response_family
    )
    claim_requirement = _map_claim_requirement(
        support_transformation_state.claim_likelihood
    )
    max_sentences_map = {
        "brief_acknowledgment": 1,
        "clarification_request": 2,
        "partial_attempt": 2,
        "revision_attempt": 2,
        "local_explanation": 2,
    }
    max_sentences = max_sentences_map[response_space]
    if mode == "protocol_light":
        max_sentences += 1

    preserve_prior_commitment = (
        local_belief_state.belief_status
        in {
            "tentative_guess",
            "stable_guess",
            "socially_justified_guess",
            "partial_rule_fragment",
        }
        and support_transformation_state.transformation_type
        not in {"destabilize_prior_commitment", "redirect_to_rule"}
    )
    allow_social_justification = (
        student_response_policy.social_justification_tendency in {"medium", "high"}
        or local_belief_state.justification_basis == "social_authority"
        or support_transformation_state.preferred_response_family
        == "social_justification"
    )
    discourage_clarification = (
        student_response_policy.help_seeking_tendency == "low"
        and support_transformation_state.preferred_response_family
        != "clarification_request"
    )

    allowed_actions = [
        f"Stay on the exact local object: {learning_opportunity_state.required_local_focus}.",
        f"Use one response family from: {', '.join(support_transformation_state.allowed_response_families)}.",
        "Preserve visible belief continuity when the bundle says to preserve prior commitment.",
    ]
    if allow_social_justification:
        allowed_actions.append("A brief social or intuitive justification is allowed if supported by visible history.")
    if support_transformation_state.claim_likelihood == "likely":
        allowed_actions.append("A brief local guess or shallow revision is allowed.")

    disallowed_actions = [
        "Do not produce a full worked solution.",
        "Do not add new math content outside the local focus.",
        "Do not answer like a tutor or evaluator.",
        "Do not use future information or future turns.",
        "Do not use a prewritten wrong answer script.",
    ]
    if support_transformation_state.claim_likelihood == "prohibited":
        disallowed_actions.append("Do not invent a new mathematical answer.")
    if discourage_clarification:
        disallowed_actions.append("Do not default to a clarification request unless the transformation explicitly supports it.")

    support_use_rules = [
        f"Current target availability is {mediated_target_availability.target_availability}.",
        f"Success affordance is {mediated_target_availability.success_affordance}.",
        (
            "Tutor support may perturb the current belief, but does not force ideal cooperative behavior."
        ),
    ]

    realization_requirements = [
        f"Keep the turn within {max_sentences} sentence(s).",
        f"Stay on local focus: {learning_opportunity_state.required_local_focus}.",
        f"Preferred response family is {support_transformation_state.preferred_response_family}.",
        f"Claim likelihood is {support_transformation_state.claim_likelihood}.",
        f"Preserve prior commitment: {preserve_prior_commitment}.",
    ]

    packet_rationale = [
        "v5.1 compiles opportunity structure together with belief continuity and response policy.",
        (
            f"Belief status is {local_belief_state.belief_status}; "
            f"transformation type is {support_transformation_state.transformation_type}."
        ),
        (
            f"Guessing tendency is {student_response_policy.guessing_tendency}; "
            f"help-seeking tendency is {student_response_policy.help_seeking_tendency}."
        ),
        (
            "The bundle allows non-ideal responses such as guesses, shallow revisions, "
            "social reasons, or refusals when history supports them."
        ),
    ]

    return OpportunityConstraintBundleV51(
        packet_version="eedi_weak_harness_v5.1",
        architecture_version="v5_1",
        ablation_mode=mode,
        local_focus=learning_opportunity_state.required_local_focus,
        access_zone=learning_access_state.access_zone,
        response_space=response_space,
        claim_requirement=claim_requirement,
        error_pressure="deferred_to_posthoc",
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
        claim_seed_mode="none_in_v5_1",
        support_consistent_claim_seed=None,
        preferred_response_family=support_transformation_state.preferred_response_family,
        allowed_response_families=list(
            support_transformation_state.allowed_response_families
        ),
        claim_likelihood=support_transformation_state.claim_likelihood,
        preserve_prior_commitment=preserve_prior_commitment,
        allow_social_justification=allow_social_justification,
        discourage_clarification=discourage_clarification,
        independently_available_acts=list(
            learning_opportunity_state.independently_available_acts
        ),
        support_enabled_acts=list(learning_opportunity_state.support_enabled_acts),
        still_unavailable_acts=list(learning_opportunity_state.still_unavailable_acts),
        salient_confusion_axes=list(learning_opportunity_state.salient_confusion_axes),
        realization_requirements=realization_requirements,
        allowed_actions=allowed_actions,
        disallowed_actions=disallowed_actions,
        support_use_rules=support_use_rules,
        packet_rationale=packet_rationale,
    )


def _parse_student_response_policy_state(parsed: object) -> StudentResponsePolicyState:
    parsed = require_keys(
        parsed,
        (
            "help_seeking_tendency",
            "guessing_tendency",
            "social_justification_tendency",
            "refusal_tendency",
            "revision_volatility",
            "policy_evidence",
        ),
        "StudentResponsePolicyState",
    )
    return StudentResponsePolicyState(
        help_seeking_tendency=_coerce_enum(
            parsed["help_seeking_tendency"], POLICY_LEVELS, "help_seeking_tendency"
        ),
        guessing_tendency=_coerce_enum(
            parsed["guessing_tendency"], POLICY_LEVELS, "guessing_tendency"
        ),
        social_justification_tendency=_coerce_enum(
            parsed["social_justification_tendency"],
            POLICY_LEVELS,
            "social_justification_tendency",
        ),
        refusal_tendency=_coerce_enum(
            parsed["refusal_tendency"], POLICY_LEVELS, "refusal_tendency"
        ),
        revision_volatility=_coerce_enum(
            parsed["revision_volatility"], POLICY_LEVELS, "revision_volatility"
        ),
        policy_evidence=_coerce_str_list(parsed["policy_evidence"], "policy_evidence"),
    )


def _parse_local_belief_state(parsed: object) -> LocalBeliefState:
    parsed = require_keys(
        parsed,
        (
            "belief_status",
            "committed_content",
            "justification_basis",
            "confidence_posture",
            "revision_readiness",
            "belief_evidence",
        ),
        "LocalBeliefState",
    )
    return LocalBeliefState(
        belief_status=_coerce_enum(parsed["belief_status"], BELIEF_STATUSES, "belief_status"),
        committed_content=_coerce_nullable_text(parsed["committed_content"], "committed_content"),
        justification_basis=_coerce_enum(
            parsed["justification_basis"], JUSTIFICATION_BASES, "justification_basis"
        ),
        confidence_posture=_coerce_enum(
            parsed["confidence_posture"], POLICY_LEVELS, "confidence_posture"
        ),
        revision_readiness=_coerce_enum(
            parsed["revision_readiness"],
            REVISION_READINESS_STATES,
            "revision_readiness",
        ),
        belief_evidence=_coerce_str_list(parsed["belief_evidence"], "belief_evidence"),
    )


def _parse_support_transformation_state(parsed: object) -> SupportTransformationState:
    parsed = require_keys(
        parsed,
        (
            "transformation_type",
            "preferred_response_family",
            "allowed_response_families",
            "claim_likelihood",
            "transformation_evidence",
        ),
        "SupportTransformationState",
    )
    allowed_families = _coerce_str_list(
        parsed["allowed_response_families"],
        "allowed_response_families",
    )
    for family in allowed_families:
        _coerce_enum(family, RESPONSE_FAMILIES, "allowed_response_family")
    preferred = _coerce_enum(
        parsed["preferred_response_family"],
        RESPONSE_FAMILIES,
        "preferred_response_family",
    )
    if preferred not in allowed_families:
        allowed_families = [preferred] + [x for x in allowed_families if x != preferred]
    return SupportTransformationState(
        transformation_type=_coerce_enum(
            parsed["transformation_type"], TRANSFORMATION_TYPES, "transformation_type"
        ),
        preferred_response_family=preferred,
        allowed_response_families=allowed_families,
        claim_likelihood=_coerce_enum(
            parsed["claim_likelihood"], CLAIM_LIKELIHOOD_STATES, "claim_likelihood"
        ),
        transformation_evidence=_coerce_str_list(
            parsed["transformation_evidence"], "transformation_evidence"
        ),
    )


def _map_response_space(preferred_family: str) -> str:
    mapping = {
        "brief_acknowledgment": "brief_acknowledgment",
        "clarification_request": "clarification_request",
        "direct_guess": "partial_attempt",
        "shallow_revision": "revision_attempt",
        "social_justification": "partial_attempt",
        "brief_rule_echo": "local_explanation",
        "refusal_or_shutdown": "brief_acknowledgment",
    }
    return mapping[_coerce_enum(preferred_family, RESPONSE_FAMILIES, "preferred_family")]


def _map_claim_requirement(claim_likelihood: str) -> str:
    value = _coerce_enum(claim_likelihood, CLAIM_LIKELIHOOD_STATES, "claim_likelihood")
    if value == "prohibited":
        return "no_claim"
    if value == "optional":
        return "tentative_claim_allowed"
    return "local_claim_required"
