from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .llm_client import OpenAICompatClient, require_keys
from .prompts import MEDIATED_TURN_PLAN_SYSTEM_PROMPT
from .weak_harness import (
    ABLATION_MODES,
    CLAIM_REQUIREMENT_STATES,
    ERROR_PRESSURE_STATES,
    LocalErrorRealizationState,
    MathClaimAffordanceState,
    MediatedTargetAvailabilityState,
    RESPONSE_SPACE_TYPES,
    StudentPrior,
    SupportUptake,
    TARGET_AVAILABILITY_STATES,
    SUCCESS_AFFORDANCE_STATES,
    TurnResponseConstraintState,
    TutorMove,
    VisibleContext,
    LearningAccessState,
    _coerce_enum,
    _coerce_nullable_text,
    _coerce_str_list,
)


TURN_PLAN_CONTENT_MODES = (
    "no_claim",
    "support_consistent_claim",
    "misconception_consistent_claim",
    "confused_partial_claim",
)
CLAIM_CONFIDENCE_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class MediatedTurnPlanState:
    response_space: str
    claim_requirement: str
    content_mode: str
    utterance_kernel: str
    reasoning_kernel: str | None
    claim_confidence: str
    should_mention_tutor_support: bool
    plan_evidence: list[str]


@dataclass(frozen=True)
class TeachingSupportPacketV4:
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
    planned_reasoning_kernel: str | None
    planned_claim_confidence: str
    planned_should_mention_tutor_support: bool
    realization_requirements: list[str]
    allowed_actions: list[str]
    disallowed_actions: list[str]
    support_use_rules: list[str]
    packet_rationale: list[str]


def resolve_mediated_turn_plan(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    turn_response_constraint: TurnResponseConstraintState,
    local_error_state: LocalErrorRealizationState,
    llm_client: OpenAICompatClient,
) -> MediatedTurnPlanState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "mediated_target_availability": asdict(mediated_target_availability),
        "turn_response_constraint": asdict(turn_response_constraint),
        "local_error_state": asdict(local_error_state),
        "required_schema": {
            "response_space": list(RESPONSE_SPACE_TYPES),
            "claim_requirement": list(CLAIM_REQUIREMENT_STATES),
            "content_mode": list(TURN_PLAN_CONTENT_MODES),
            "utterance_kernel": "string",
            "reasoning_kernel": "string | null",
            "claim_confidence": list(CLAIM_CONFIDENCE_LEVELS),
            "should_mention_tutor_support": "boolean",
            "plan_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=MEDIATED_TURN_PLAN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["utterance_kernel", "reasoning_kernel"],
    )
    try:
        return _parse_mediated_turn_plan_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=MEDIATED_TURN_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["utterance_kernel", "reasoning_kernel"],
        )
        return _parse_mediated_turn_plan_state(repaired)


def compile_teaching_support_packet_v4(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    turn_response_constraint: TurnResponseConstraintState,
    local_error_state: LocalErrorRealizationState,
    mediated_turn_plan: MediatedTurnPlanState,
    ablation_mode: str = "baseline",
) -> TeachingSupportPacketV4:
    mode = _coerce_enum(ablation_mode, ABLATION_MODES, "ablation_mode")
    max_sentences_map = {
        "brief_acknowledgment": 1,
        "clarification_request": 1,
        "partial_attempt": 2,
        "revision_attempt": 2,
        "local_explanation": 3,
    }
    max_sentences = max_sentences_map[mediated_turn_plan.response_space]
    if mode == "protocol_light":
        max_sentences += 1

    allowed_actions = [
        f"Stay on the exact local object: {tutor_move.elicited_object_description}.",
        f"Realize the planned response space: {mediated_turn_plan.response_space}.",
        f"Preserve this local utterance kernel: {mediated_turn_plan.utterance_kernel}.",
    ]
    if mediated_turn_plan.reasoning_kernel:
        allowed_actions.append(
            f"Keep this short local reason if used: {mediated_turn_plan.reasoning_kernel}."
        )
    if mediated_turn_plan.should_mention_tutor_support:
        allowed_actions.append("A brief mention of the tutor's current cue is allowed.")
    if mode == "commitment_first" and mediated_turn_plan.claim_requirement != "no_claim":
        allowed_actions.append("Prefer one direct local commitment over generic hedging.")

    disallowed_actions = [
        "Do not answer like a tutor or evaluator.",
        "Do not add a full worked solution.",
        "Do not add math content outside the planned local object.",
        "Do not use future information or future turns.",
    ]
    if mediated_turn_plan.content_mode == "no_claim":
        disallowed_actions.append("Do not invent a mathematical answer.")
    elif mediated_turn_plan.content_mode == "support_consistent_claim":
        disallowed_actions.append(
            "Do not replace the planned local claim with a different answer direction."
        )
    elif mediated_turn_plan.content_mode == "misconception_consistent_claim":
        disallowed_actions.append(
            "Do not repair the planned wrong local claim into a correct one."
        )
    else:
        disallowed_actions.append(
            "Do not turn the unstable partial claim into a polished full answer."
        )

    support_use_rules = [
        f"Use only the current mediated support level: {mediated_target_availability.target_availability}.",
        f"Target success affordance is {mediated_target_availability.success_affordance}.",
        f"Error continuity risk is {mediated_target_availability.error_continuity_risk}.",
    ]
    if mediated_turn_plan.content_mode == "support_consistent_claim":
        support_use_rules.append(
            "Treat the tutor support as making one local claim available, not the whole solution."
        )
    if mediated_turn_plan.content_mode == "misconception_consistent_claim":
        support_use_rules.append(
            "Keep the same wrong local claim direction if an error path is still live."
        )

    realization_requirements = [
        f"Keep the turn within {max_sentences} sentence(s).",
        f"Match the planned response space: {mediated_turn_plan.response_space}.",
        f"Match the planned content mode: {mediated_turn_plan.content_mode}.",
        f"Preserve the planned utterance kernel: {mediated_turn_plan.utterance_kernel}.",
        f"Claim requirement is {mediated_turn_plan.claim_requirement}.",
        f"Local error presence is {local_error_state.error_presence}.",
    ]
    if mediated_turn_plan.reasoning_kernel:
        realization_requirements.append(
            f"If a reason is given, preserve this local reason: {mediated_turn_plan.reasoning_kernel}."
        )
    if local_error_state.error_presence == "codable_math_error":
        realization_requirements.extend(
            [
                f"Keep the Newman error locus at: {local_error_state.newman_error_locus}.",
                (
                    "Keep the error mechanism consistent with: "
                    f"{local_error_state.radatz_error_mechanism}."
                ),
                f"Preserve this buggy rule: {local_error_state.buggy_rule}.",
            ]
        )

    packet_rationale = [
        f"v4 uses a compiler-planned local kernel before weak surface realization.",
        f"Access zone is {learning_access_state.access_zone}; uptake depth is {support_uptake.uptake_depth}.",
        (
            "Mediated availability is "
            f"{mediated_target_availability.target_availability} with success affordance "
            f"{mediated_target_availability.success_affordance}."
        ),
        (
            "Planned content mode is "
            f"{mediated_turn_plan.content_mode}; claim confidence is "
            f"{mediated_turn_plan.claim_confidence}."
        ),
    ]

    return TeachingSupportPacketV4(
        packet_version="eedi_weak_harness_v4.0",
        architecture_version="v4",
        ablation_mode=mode,
        local_focus=tutor_move.elicited_object_description,
        access_zone=learning_access_state.access_zone,
        response_space=mediated_turn_plan.response_space,
        claim_requirement=mediated_turn_plan.claim_requirement,
        error_pressure=turn_response_constraint.error_pressure,
        target_availability=mediated_target_availability.target_availability,
        success_affordance=mediated_target_availability.success_affordance,
        error_continuity_risk=mediated_target_availability.error_continuity_risk,
        target_engagement_mode=support_uptake.likely_next_engagement_mode,
        max_sentences=max_sentences,
        claim_affordance=math_claim_affordance.claim_affordance,
        error_opportunity=math_claim_affordance.error_opportunity,
        expected_claim_shape=math_claim_affordance.expected_claim_shape,
        local_error_presence=local_error_state.error_presence,
        local_newman_locus=local_error_state.newman_error_locus,
        local_error_mechanism=local_error_state.radatz_error_mechanism,
        buggy_rule=local_error_state.buggy_rule,
        wrong_claim_seed=local_error_state.wrong_claim_seed,
        claim_seed_mode=mediated_turn_plan.content_mode,
        support_consistent_claim_seed=(
            mediated_turn_plan.utterance_kernel
            if mediated_turn_plan.content_mode == "support_consistent_claim"
            else None
        ),
        planned_reasoning_kernel=mediated_turn_plan.reasoning_kernel,
        planned_claim_confidence=mediated_turn_plan.claim_confidence,
        planned_should_mention_tutor_support=mediated_turn_plan.should_mention_tutor_support,
        realization_requirements=realization_requirements,
        allowed_actions=allowed_actions,
        disallowed_actions=disallowed_actions,
        support_use_rules=support_use_rules,
        packet_rationale=packet_rationale,
    )


def _parse_mediated_turn_plan_state(parsed: object) -> MediatedTurnPlanState:
    parsed = require_keys(
        parsed,
        (
            "response_space",
            "claim_requirement",
            "content_mode",
            "utterance_kernel",
            "reasoning_kernel",
            "claim_confidence",
            "should_mention_tutor_support",
            "plan_evidence",
        ),
        "MediatedTurnPlanState",
    )
    utterance_kernel = str(parsed["utterance_kernel"]).strip()
    if not utterance_kernel:
        raise ValueError("utterance_kernel cannot be empty")
    content_mode = _coerce_enum(
        parsed["content_mode"],
        TURN_PLAN_CONTENT_MODES,
        "content_mode",
    )
    reasoning_kernel = _coerce_nullable_text(
        parsed["reasoning_kernel"],
        "reasoning_kernel",
    )
    if content_mode == "no_claim" and reasoning_kernel is not None:
        raise ValueError("no_claim cannot carry a reasoning_kernel")
    should_mention_tutor_support = parsed["should_mention_tutor_support"]
    if not isinstance(should_mention_tutor_support, bool):
        raise ValueError("should_mention_tutor_support must be boolean")
    return MediatedTurnPlanState(
        response_space=_coerce_enum(
            parsed["response_space"],
            RESPONSE_SPACE_TYPES,
            "response_space",
        ),
        claim_requirement=_coerce_enum(
            parsed["claim_requirement"],
            CLAIM_REQUIREMENT_STATES,
            "claim_requirement",
        ),
        content_mode=content_mode,
        utterance_kernel=utterance_kernel,
        reasoning_kernel=reasoning_kernel,
        claim_confidence=_coerce_enum(
            parsed["claim_confidence"],
            CLAIM_CONFIDENCE_LEVELS,
            "claim_confidence",
        ),
        should_mention_tutor_support=should_mention_tutor_support,
        plan_evidence=_coerce_str_list(parsed["plan_evidence"], "plan_evidence"),
    )
