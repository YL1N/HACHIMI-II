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
CLAIM_REALIZATION_STATES = (
    "no_claim",
    "tentative_local_claim",
    "direct_local_claim",
)
ANCHOR_MODES = (
    "stay_with_visible_belief",
    "stay_with_support_enabled_relation",
    "stay_with_response_family_only",
)
SURFACE_DEPTH_STATES = (
    "acknowledgment_only",
    "brief_reason",
    "one_local_relation",
)


@dataclass(frozen=True)
class StudentResponsePolicyStateV52:
    help_seeking_tendency: str
    guessing_tendency: str
    social_justification_tendency: str
    refusal_tendency: str
    revision_volatility: str
    policy_evidence: list[str]


@dataclass(frozen=True)
class LocalBeliefStateV52:
    belief_status: str
    committed_content: str | None
    justification_basis: str
    confidence_posture: str
    revision_readiness: str
    belief_evidence: list[str]


@dataclass(frozen=True)
class SupportTransformationStateV52:
    transformation_type: str
    preferred_response_family: str
    allowed_response_families: list[str]
    claim_likelihood: str
    transformation_evidence: list[str]


@dataclass(frozen=True)
class ClaimRealizationFrame:
    claim_state: str
    anchor_mode: str
    allowed_content_sources: list[str]
    preferred_reason_mode: str
    surface_depth: str
    frame_evidence: list[str]


@dataclass(frozen=True)
class OpportunityConstraintBundleV52:
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
    claim_seed_mode_legacy: str | None
    preferred_response_family: str
    allowed_response_families: list[str]
    claim_likelihood: str
    preserve_prior_commitment: bool
    allow_social_justification: bool
    discourage_clarification: bool
    claim_state: str
    anchor_mode: str
    allowed_content_sources: list[str]
    preferred_reason_mode: str
    surface_depth: str
    independently_available_acts: list[str]
    support_enabled_acts: list[str]
    still_unavailable_acts: list[str]
    salient_confusion_axes: list[str]
    realization_requirements: list[str]
    allowed_actions: list[str]
    disallowed_actions: list[str]
    support_use_rules: list[str]
    packet_rationale: list[str]


CLAIM_REALIZATION_FRAME_SYSTEM_PROMPT = """You are inferring the student's current claim-realization frame in a math tutoring dialogue.
This is a third-person state judgment, not answer generation.
Do not answer the math problem.
Do not use future turns, gold labels, official annotations, or evaluation targets.

Theory grounding:
- Use dynamic assessment to judge whether the student can now only acknowledge, can tentatively guess, or can directly state one local claim.
- Use contingent scaffolding to decide what content source the student can anchor to right now: a visible prior belief, a newly support-enabled local relation, or only a response family without math content.
- Keep the frame at the level of realizable interaction form, not final answer control.

Hard rules:
- claim_state must be exactly one of: no_claim | tentative_local_claim | direct_local_claim.
- anchor_mode must be exactly one of: stay_with_visible_belief | stay_with_support_enabled_relation | stay_with_response_family_only.
- allowed_content_sources must be a small list of visible content bases, not hidden answer knowledge.
- preferred_reason_mode should describe whether the student is more likely to use none, social reason, intuition, surface pattern, or one local relation.
- surface_depth must describe only how much the student can currently say, not the exact answer.
- Do not output a wrong-claim seed, a support-consistent answer seed, or a hidden correct answer.
- Every required evidence list must be non-empty.
- Top-level keys must match required_schema exactly.
Return only the requested JSON object.
"""


def resolve_student_response_policy_v52(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    llm_client: OpenAICompatClient,
) -> StudentResponsePolicyStateV52:
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


def resolve_local_belief_state_v52(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    llm_client: OpenAICompatClient,
) -> LocalBeliefStateV52:
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


def resolve_support_transformation_state_v52(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    student_response_policy: StudentResponsePolicyStateV52,
    local_belief_state: LocalBeliefStateV52,
    llm_client: OpenAICompatClient,
) -> SupportTransformationStateV52:
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


def resolve_claim_realization_frame(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    learning_opportunity_state,
    student_response_policy: StudentResponsePolicyStateV52,
    local_belief_state: LocalBeliefStateV52,
    support_transformation_state: SupportTransformationStateV52,
    llm_client: OpenAICompatClient,
) -> ClaimRealizationFrame:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "mediated_target_availability": asdict(mediated_target_availability),
        "learning_opportunity_state": asdict(learning_opportunity_state),
        "student_response_policy": asdict(student_response_policy),
        "local_belief_state": asdict(local_belief_state),
        "support_transformation_state": asdict(support_transformation_state),
        "required_schema": {
            "claim_state": list(CLAIM_REALIZATION_STATES),
            "anchor_mode": list(ANCHOR_MODES),
            "allowed_content_sources": ["string"],
            "preferred_reason_mode": list(JUSTIFICATION_BASES),
            "surface_depth": list(SURFACE_DEPTH_STATES),
            "frame_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=CLAIM_REALIZATION_FRAME_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_claim_realization_frame(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=CLAIM_REALIZATION_FRAME_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_claim_realization_frame(repaired)


def compile_opportunity_constraint_bundle_v52(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    learning_opportunity_state,
    student_response_policy: StudentResponsePolicyStateV52,
    local_belief_state: LocalBeliefStateV52,
    support_transformation_state: SupportTransformationStateV52,
    claim_realization_frame: ClaimRealizationFrame,
    ablation_mode: str = "baseline",
) -> OpportunityConstraintBundleV52:
    mode = _coerce_enum(ablation_mode, ABLATION_MODES, "ablation_mode")
    response_space = _map_response_space(
        support_transformation_state.preferred_response_family
    )
    claim_requirement = _map_claim_requirement(claim_realization_frame.claim_state)
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
        or claim_realization_frame.preferred_reason_mode == "social_authority"
    )
    discourage_clarification = (
        student_response_policy.help_seeking_tendency == "low"
        and support_transformation_state.preferred_response_family
        != "clarification_request"
    )

    allowed_actions = [
        f"Stay on the exact local object: {learning_opportunity_state.required_local_focus}.",
        f"Use one response family from: {', '.join(support_transformation_state.allowed_response_families)}.",
        f"Realize content only through anchor mode: {claim_realization_frame.anchor_mode}.",
    ]
    if allow_social_justification:
        allowed_actions.append(
            "A brief social or authority-based reason is allowed if visible history supports it."
        )
    if claim_realization_frame.claim_state != "no_claim":
        allowed_actions.append(
            "A short local claim is allowed if it stays inside the compiled frame."
        )

    disallowed_actions = [
        "Do not produce a full worked solution.",
        "Do not add new math content outside the local focus.",
        "Do not answer like a tutor or evaluator.",
        "Do not use future information or future turns.",
        "Do not use a prewritten wrong answer script.",
    ]
    if claim_realization_frame.claim_state == "no_claim":
        disallowed_actions.append("Do not invent a new mathematical answer.")
    if discourage_clarification:
        disallowed_actions.append(
            "Do not default to a clarification request unless the transformation explicitly supports it."
        )

    support_use_rules = [
        f"Current target availability is {mediated_target_availability.target_availability}.",
        f"Success affordance is {mediated_target_availability.success_affordance}.",
        "Tutor support may open one local response shape without guaranteeing ideal mathematical uptake.",
    ]

    realization_requirements = [
        f"Keep the turn within {max_sentences} sentence(s).",
        f"Stay on local focus: {learning_opportunity_state.required_local_focus}.",
        f"Preferred response family is {support_transformation_state.preferred_response_family}.",
        f"Claim state is {claim_realization_frame.claim_state}.",
        f"Surface depth is {claim_realization_frame.surface_depth}.",
        f"Preserve prior commitment: {preserve_prior_commitment}.",
    ]

    packet_rationale = [
        "v5.2 compiles opportunity structure together with belief continuity and a claim-realization frame.",
        (
            f"Belief status is {local_belief_state.belief_status}; "
            f"transformation type is {support_transformation_state.transformation_type}."
        ),
        (
            f"Claim state is {claim_realization_frame.claim_state}; "
            f"anchor mode is {claim_realization_frame.anchor_mode}."
        ),
        (
            "The bundle constrains how a weak actor may realize local content "
            "without prewriting the exact answer."
        ),
    ]

    return OpportunityConstraintBundleV52(
        packet_version="eedi_weak_harness_v5.2",
        architecture_version="v5_2",
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
        claim_seed_mode="none_in_v5_2",
        support_consistent_claim_seed=None,
        claim_seed_mode_legacy=None,
        preferred_response_family=support_transformation_state.preferred_response_family,
        allowed_response_families=list(
            support_transformation_state.allowed_response_families
        ),
        claim_likelihood=support_transformation_state.claim_likelihood,
        preserve_prior_commitment=preserve_prior_commitment,
        allow_social_justification=allow_social_justification,
        discourage_clarification=discourage_clarification,
        claim_state=claim_realization_frame.claim_state,
        anchor_mode=claim_realization_frame.anchor_mode,
        allowed_content_sources=list(claim_realization_frame.allowed_content_sources),
        preferred_reason_mode=claim_realization_frame.preferred_reason_mode,
        surface_depth=claim_realization_frame.surface_depth,
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


def _parse_student_response_policy_state(parsed: object) -> StudentResponsePolicyStateV52:
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
        "StudentResponsePolicyStateV52",
    )
    return StudentResponsePolicyStateV52(
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


def _parse_local_belief_state(parsed: object) -> LocalBeliefStateV52:
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
        "LocalBeliefStateV52",
    )
    return LocalBeliefStateV52(
        belief_status=_coerce_enum(parsed["belief_status"], BELIEF_STATUSES, "belief_status"),
        committed_content=_coerce_nullable_text(
            parsed["committed_content"],
            "committed_content",
        ),
        justification_basis=_coerce_enum(
            parsed["justification_basis"],
            JUSTIFICATION_BASES,
            "justification_basis",
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


def _parse_support_transformation_state(
    parsed: object,
) -> SupportTransformationStateV52:
    parsed = require_keys(
        parsed,
        (
            "transformation_type",
            "preferred_response_family",
            "allowed_response_families",
            "claim_likelihood",
            "transformation_evidence",
        ),
        "SupportTransformationStateV52",
    )
    return SupportTransformationStateV52(
        transformation_type=_coerce_enum(
            parsed["transformation_type"],
            TRANSFORMATION_TYPES,
            "transformation_type",
        ),
        preferred_response_family=_coerce_enum(
            parsed["preferred_response_family"],
            RESPONSE_FAMILIES,
            "preferred_response_family",
        ),
        allowed_response_families=_coerce_small_enum_list(
            parsed["allowed_response_families"],
            RESPONSE_FAMILIES,
            "allowed_response_families",
        ),
        claim_likelihood=_coerce_enum(
            parsed["claim_likelihood"],
            CLAIM_LIKELIHOOD_STATES,
            "claim_likelihood",
        ),
        transformation_evidence=_coerce_str_list(
            parsed["transformation_evidence"],
            "transformation_evidence",
        ),
    )


def _parse_claim_realization_frame(parsed: object) -> ClaimRealizationFrame:
    parsed = require_keys(
        parsed,
        (
            "claim_state",
            "anchor_mode",
            "allowed_content_sources",
            "preferred_reason_mode",
            "surface_depth",
            "frame_evidence",
        ),
        "ClaimRealizationFrame",
    )
    return ClaimRealizationFrame(
        claim_state=_coerce_enum(
            parsed["claim_state"],
            CLAIM_REALIZATION_STATES,
            "claim_state",
        ),
        anchor_mode=_coerce_enum(
            parsed["anchor_mode"],
            ANCHOR_MODES,
            "anchor_mode",
        ),
        allowed_content_sources=_coerce_str_list(
            parsed["allowed_content_sources"],
            "allowed_content_sources",
        ),
        preferred_reason_mode=_coerce_enum(
            parsed["preferred_reason_mode"],
            JUSTIFICATION_BASES,
            "preferred_reason_mode",
        ),
        surface_depth=_coerce_enum(
            parsed["surface_depth"],
            SURFACE_DEPTH_STATES,
            "surface_depth",
        ),
        frame_evidence=_coerce_str_list(parsed["frame_evidence"], "frame_evidence"),
    )


def _coerce_small_enum_list(
    value: object,
    allowed: tuple[str, ...],
    field_name: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text not in allowed:
            raise ValueError(f"{field_name} item must be one of {allowed}, got {text!r}")
        if text not in result:
            result.append(text)
    if not result:
        raise ValueError(f"{field_name} must contain at least one allowed value")
    if len(result) > 4:
        result = result[:4]
    return result


def _map_response_space(preferred_response_family: str) -> str:
    family = _coerce_enum(
        preferred_response_family,
        RESPONSE_FAMILIES,
        "preferred_response_family",
    )
    if family == "brief_acknowledgment":
        return "brief_acknowledgment"
    if family == "clarification_request":
        return "clarification_request"
    if family in {"direct_guess", "brief_rule_echo"}:
        return "partial_attempt"
    if family == "shallow_revision":
        return "revision_attempt"
    if family == "social_justification":
        return "local_explanation"
    return "brief_acknowledgment"


def _map_claim_requirement(claim_state: str) -> str:
    state = _coerce_enum(claim_state, CLAIM_REALIZATION_STATES, "claim_state")
    if state == "no_claim":
        return "no_claim"
    if state == "tentative_local_claim":
        return "tentative_claim_allowed"
    return "local_claim_required"
