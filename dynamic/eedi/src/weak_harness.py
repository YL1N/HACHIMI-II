from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .dialogue_context import DialogueContextState
from .error_blueprint import (
    ErrorBlueprint,
    ERROR_PRESENCE_STATES,
    NEWMAN_ERROR_LOCI,
    RADATZ_ERROR_MECHANISMS,
)
from .llm_client import OpenAICompatClient, require_keys
from .population_calibration import PopulationCalibrationSummary
from .prompts import (
    LEARNING_ACCESS_STATE_SYSTEM_PROMPT,
    LEARNING_STATE_UPDATE_SYSTEM_PROMPT,
    LOCAL_CLAIM_SEED_SYSTEM_PROMPT,
    LOCAL_ERROR_REALIZATION_SYSTEM_PROMPT,
    MATH_CLAIM_AFFORDANCE_SYSTEM_PROMPT,
    MEDIATED_TARGET_AVAILABILITY_SYSTEM_PROMPT,
    SUPPORT_UPTAKE_SYSTEM_PROMPT,
)
from .student_model import ICAP_LEVELS, StudentContextProfile
from .tutor_turn_profile import TutorTurnProfile


LEARNING_ACCESS_ZONES = (
    "already_can_do",
    "reachable_with_current_support",
    "not_reachable_this_turn",
)
TUTOR_INTENT_GRASP_LEVELS = ("clear", "partial", "misread")
UPTAKE_PREPARATION_LEVELS = (
    "not_positioned",
    "attention_oriented",
    "local_strategy_oriented",
    "ready_to_try",
)
TURN_READINESS_STATES = (
    "acknowledge_or_brief_react",
    "ask_for_clarification",
    "attempt_local_step",
    "revise_prior_idea",
    "explain_current_judgment",
)
REGULATION_STATES = (
    "tutor_regulated",
    "shared_regulation",
    "self_regulation",
)
PERSISTENT_OBSTACLE_TYPES = (
    "misconception",
    "missing_relation",
    "execution_gap",
    "expression_gap",
    "confidence_barrier",
    "no_major_obstacle",
)
UPTAKE_DEPTH_LEVELS = (
    "no_uptake",
    "noticing_only",
    "partial_use",
    "substantive_use",
)
UPTAKE_FOCUS_TYPES = (
    "social_alignment",
    "task_orientation",
    "local_representation",
    "local_relation",
    "local_procedure",
    "local_judgment",
)
RESPONSE_SPACE_TYPES = (
    "brief_acknowledgment",
    "clarification_request",
    "partial_attempt",
    "revision_attempt",
    "local_explanation",
)
MATH_CLAIM_AFFORDANCE_STATES = (
    "no_math_claim_expected",
    "math_claim_possible",
    "math_claim_expected",
)
CLAIM_REQUIREMENT_STATES = (
    "no_claim",
    "tentative_claim_allowed",
    "local_claim_required",
)
ERROR_PRESSURE_STATES = (
    "suppressed",
    "open",
    "likely",
)
TARGET_AVAILABILITY_STATES = (
    "cue_only",
    "rule_available",
    "worked_local_step_available",
    "target_almost_explicit",
)
SUCCESS_AFFORDANCE_STATES = (
    "low",
    "moderate",
    "high",
)
CLAIM_SEED_MODES = (
    "no_claim_needed",
    "use_wrong_claim_seed",
    "support_consistent_claim_available",
    "insufficient_visible_basis",
)
ERROR_OPPORTUNITY_STATES = (
    "none",
    "unstable_local_execution",
    "misconception_continuity",
)
ABLATION_MODES = (
    "baseline",
    "protocol_light",
    "commitment_first",
)


@dataclass(frozen=True)
class VisibleContext:
    dialogue_id: str
    question_id: str
    intervention_id: str
    question_text: str
    subjects: list[tuple[str, int]]
    turns_so_far: list[dict[str, str]]
    latest_tutor_turn: str
    last_student_turn: str
    turn_count_so_far: int


@dataclass(frozen=True)
class StudentPrior:
    self_efficacy_description: str
    srl_vulnerability: str
    control_value_description: str
    engagement_tendency: str
    response_style_description: str
    population_calibration_prior: list[str]
    population_calibration_cautions: list[str]
    prior_evidence: list[str]


@dataclass(frozen=True)
class TutorMove:
    instructional_intent: str
    support_type: str
    support_intensity: str
    support_granularity: str
    support_contingency: str
    responsibility_shift: str
    target_of_intervention: str
    elicited_response_process: str
    elicited_response_target_type: str
    elicited_object_description: str
    move_evidence: list[str]


@dataclass(frozen=True)
class LearningAccessState:
    access_zone: str
    tutor_intent_grasp: str
    uptake_preparation: str
    turn_readiness: str
    regulation_state: str
    current_engagement_mode: str
    persistent_obstacle: str
    state_evidence: list[str]


@dataclass(frozen=True)
class SupportUptake:
    uptake_depth: str
    uptake_focus: str
    response_space: str
    likely_next_engagement_mode: str
    uptake_rationale: list[str]


@dataclass(frozen=True)
class MathClaimAffordanceState:
    claim_affordance: str
    error_opportunity: str
    expected_claim_shape: str
    affordance_evidence: list[str]


@dataclass(frozen=True)
class MediatedTargetAvailabilityState:
    target_availability: str
    success_affordance: str
    error_continuity_risk: str
    availability_evidence: list[str]


@dataclass(frozen=True)
class TurnResponseConstraintState:
    response_space: str
    claim_requirement: str
    error_pressure: str
    constraint_evidence: list[str]


@dataclass(frozen=True)
class TeachingSupportPacket:
    packet_version: str
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
    realization_requirements: list[str]
    allowed_actions: list[str]
    disallowed_actions: list[str]
    support_use_rules: list[str]
    packet_rationale: list[str]


@dataclass(frozen=True)
class LearningStateUpdate:
    observed_engagement_mode: str
    observed_uptake_depth: str
    predicted_next_readiness: str
    persistent_obstacle: str
    update_evidence: list[str]


@dataclass(frozen=True)
class LocalErrorRealizationState:
    error_presence: str
    newman_error_locus: str | None
    radatz_error_mechanism: str | None
    buggy_rule: str | None
    wrong_claim_seed: str | None
    realization_evidence: list[str]


@dataclass(frozen=True)
class LocalClaimSeedState:
    claim_seed_mode: str
    support_consistent_claim_seed: str | None
    claim_seed_evidence: list[str]


def build_visible_context(context: DialogueContextState) -> VisibleContext:
    return VisibleContext(
        dialogue_id=context.dialogue_id,
        question_id=context.question_id,
        intervention_id=context.intervention_id,
        question_text=context.question_text,
        subjects=list(context.subjects),
        turns_so_far=list(context.turns_so_far),
        latest_tutor_turn=context.latest_tutor_turn,
        last_student_turn=context.last_student_turn,
        turn_count_so_far=context.turn_count_so_far,
    )


def build_student_prior(
    profile: StudentContextProfile,
    population_calibration_summary: PopulationCalibrationSummary | None = None,
) -> StudentPrior:
    control_text = (
        f"{profile.control_value_analysis['control_appraisal_description']} "
        f"{profile.control_value_analysis['value_appraisal_description']}"
    ).strip()
    prior_evidence = (
        list(profile.self_efficacy_analysis["efficacy_belief_evidence"])
        + list(profile.srl_analysis["srl_process_evidence"])
        + list(profile.control_value_analysis["control_value_evidence"])
        + list(profile.engagement_tendency_analysis["engagement_evidence"])
        + list(profile.response_style_analysis["response_directness_evidence"])
    )
    population_calibration_prior = (
        list(population_calibration_summary.prior_summary_lines)
        if population_calibration_summary is not None
        else []
    )
    population_calibration_cautions = (
        list(population_calibration_summary.caution_lines)
        if population_calibration_summary is not None
        else []
    )
    return StudentPrior(
        self_efficacy_description=str(
            profile.self_efficacy_analysis["efficacy_belief_description"]
        ).strip(),
        srl_vulnerability=str(
            profile.srl_analysis["primary_srl_vulnerability"]
        ).strip(),
        control_value_description=control_text,
        engagement_tendency=str(
            profile.engagement_tendency_analysis["engagement_level_tendency"]
        ).strip(),
        response_style_description=str(
            profile.response_style_analysis["response_directness_description"]
        ).strip(),
        population_calibration_prior=[
            item for item in population_calibration_prior if str(item).strip()
        ],
        population_calibration_cautions=[
            item for item in population_calibration_cautions if str(item).strip()
        ],
        prior_evidence=[item for item in prior_evidence if str(item).strip()],
    )


def build_tutor_move(profile: TutorTurnProfile) -> TutorMove:
    return TutorMove(
        instructional_intent=profile.instructional_intent,
        support_type=profile.support_type,
        support_intensity=profile.support_intensity,
        support_granularity=profile.support_granularity,
        support_contingency=profile.support_contingency,
        responsibility_shift=profile.responsibility_shift,
        target_of_intervention=profile.target_of_intervention,
        elicited_response_process=profile.elicited_response_process,
        elicited_response_target_type=profile.elicited_response_target_type,
        elicited_object_description=profile.elicited_object_description,
        move_evidence=list(profile.move_evidence),
    )


def resolve_learning_access_state(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    llm_client: OpenAICompatClient,
) -> LearningAccessState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "required_schema": {
            "access_zone": list(LEARNING_ACCESS_ZONES),
            "tutor_intent_grasp": list(TUTOR_INTENT_GRASP_LEVELS),
            "uptake_preparation": list(UPTAKE_PREPARATION_LEVELS),
            "turn_readiness": list(TURN_READINESS_STATES),
            "regulation_state": list(REGULATION_STATES),
            "current_engagement_mode": list(ICAP_LEVELS),
            "persistent_obstacle": list(PERSISTENT_OBSTACLE_TYPES),
            "state_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=LEARNING_ACCESS_STATE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_learning_access_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=LEARNING_ACCESS_STATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_learning_access_state(repaired)


def predict_support_uptake(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    llm_client: OpenAICompatClient,
) -> SupportUptake:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "required_schema": {
            "uptake_depth": list(UPTAKE_DEPTH_LEVELS),
            "uptake_focus": list(UPTAKE_FOCUS_TYPES),
            "response_space": list(RESPONSE_SPACE_TYPES),
            "likely_next_engagement_mode": list(ICAP_LEVELS),
            "uptake_rationale": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=SUPPORT_UPTAKE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_support_uptake(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=SUPPORT_UPTAKE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_support_uptake(repaired)


def resolve_math_claim_affordance(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    llm_client: OpenAICompatClient,
) -> MathClaimAffordanceState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "theory_decision_cues": {
            "tutor_is_eliciting_local_math_content": _tutor_is_eliciting_local_math_content(
                tutor_move
            ),
            "turn_readiness_allows_claim": learning_access_state.turn_readiness
            in {
                "attempt_local_step",
                "revise_prior_idea",
                "explain_current_judgment",
            },
            "uptake_allows_claim": support_uptake.uptake_depth
            in {"partial_use", "substantive_use"},
            "response_space_allows_claim": support_uptake.response_space
            in {"partial_attempt", "revision_attempt", "local_explanation"},
            "local_obstacle_can_surface_as_error": learning_access_state.persistent_obstacle
            in {"misconception", "missing_relation", "execution_gap"},
            "important_interpretation_note": (
                "A local claim affordance is not a decision that the claim is correct. "
                "It only says the weak actor should be allowed to make a local attempt."
            ),
        },
        "required_schema": {
            "claim_affordance": list(MATH_CLAIM_AFFORDANCE_STATES),
            "error_opportunity": list(ERROR_OPPORTUNITY_STATES),
            "expected_claim_shape": "string",
            "affordance_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=MATH_CLAIM_AFFORDANCE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_math_claim_affordance_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=MATH_CLAIM_AFFORDANCE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_math_claim_affordance_state(repaired)


def resolve_mediated_target_availability(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    llm_client: OpenAICompatClient,
) -> MediatedTargetAvailabilityState:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "required_schema": {
            "target_availability": list(TARGET_AVAILABILITY_STATES),
            "success_affordance": list(SUCCESS_AFFORDANCE_STATES),
            "error_continuity_risk": list(ERROR_PRESSURE_STATES),
            "availability_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=MEDIATED_TARGET_AVAILABILITY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_mediated_target_availability_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=MEDIATED_TARGET_AVAILABILITY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_mediated_target_availability_state(repaired)


def resolve_turn_response_constraint(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
) -> TurnResponseConstraintState:
    response_space = _resolve_turn_response_space(
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
    )
    claim_requirement = _resolve_claim_requirement(
        response_space=response_space,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
    )
    error_pressure = _resolve_error_pressure(
        response_space=response_space,
        claim_requirement=claim_requirement,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
    )
    constraint_evidence = [
        (
            "Tutor asks for "
            f"{tutor_move.elicited_response_target_type} on {tutor_move.elicited_object_description}; "
            f"response_space resolved to {response_space}."
        ),
        (
            "Access zone is "
            f"{learning_access_state.access_zone}; readiness is {learning_access_state.turn_readiness}; "
            f"uptake depth is {support_uptake.uptake_depth}."
        ),
        (
            "Claim affordance is "
            f"{math_claim_affordance.claim_affordance}; "
            f"claim requirement is {claim_requirement}; "
            f"error pressure is {error_pressure}."
        ),
        (
            "Mediated target availability is "
            f"{mediated_target_availability.target_availability}; "
            f"success affordance is {mediated_target_availability.success_affordance}; "
            f"error continuity risk is {mediated_target_availability.error_continuity_risk}."
        ),
    ]
    return TurnResponseConstraintState(
        response_space=response_space,
        claim_requirement=claim_requirement,
        error_pressure=error_pressure,
        constraint_evidence=constraint_evidence,
    )


def resolve_local_error_realization(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    turn_response_constraint: TurnResponseConstraintState,
    llm_client: OpenAICompatClient,
) -> LocalErrorRealizationState:
    if turn_response_constraint.error_pressure == "suppressed":
        return LocalErrorRealizationState(
            error_presence="no_specific_error",
            newman_error_locus=None,
            radatz_error_mechanism=None,
            buggy_rule=None,
            wrong_claim_seed=None,
            realization_evidence=[
                (
                    "The current response constraint keeps the turn at "
                    f"{turn_response_constraint.response_space}, so no concrete codable error should be forced."
                ),
            ],
        )
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "turn_response_constraint": asdict(turn_response_constraint),
        "required_schema": {
            "error_presence": list(ERROR_PRESENCE_STATES),
            "newman_error_locus": list(NEWMAN_ERROR_LOCI) + [None],
            "radatz_error_mechanism": list(RADATZ_ERROR_MECHANISMS) + [None],
            "buggy_rule": "string | null",
            "wrong_claim_seed": "string | null",
            "realization_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=LOCAL_ERROR_REALIZATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_local_error_realization_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=LOCAL_ERROR_REALIZATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_local_error_realization_state(repaired)


def resolve_local_claim_seed(
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
) -> LocalClaimSeedState:
    if turn_response_constraint.claim_requirement == "no_claim":
        return LocalClaimSeedState(
            claim_seed_mode="no_claim_needed",
            support_consistent_claim_seed=None,
            claim_seed_evidence=[
                "The current constraint does not require a mathematical claim."
            ],
        )
    if local_error_state.error_presence == "codable_math_error":
        return LocalClaimSeedState(
            claim_seed_mode="use_wrong_claim_seed",
            support_consistent_claim_seed=None,
            claim_seed_evidence=[
                "A codable local error already provides the required wrong-claim seed."
            ],
        )
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
            "claim_seed_mode": list(CLAIM_SEED_MODES),
            "support_consistent_claim_seed": "string | null",
            "claim_seed_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=LOCAL_CLAIM_SEED_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        partial_string_keys=["support_consistent_claim_seed"],
    )
    try:
        return _parse_local_claim_seed_state(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=LOCAL_CLAIM_SEED_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
            partial_string_keys=["support_consistent_claim_seed"],
        )
        return _parse_local_claim_seed_state(repaired)


def compile_teaching_support_packet(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
    turn_response_constraint: TurnResponseConstraintState,
    local_error_state: LocalErrorRealizationState,
    local_claim_seed: LocalClaimSeedState,
    ablation_mode: str = "baseline",
) -> TeachingSupportPacket:
    mode = _coerce_enum(
        ablation_mode,
        ABLATION_MODES,
        "ablation_mode",
    )
    response_space = turn_response_constraint.response_space
    max_sentences_map = {
        "brief_acknowledgment": 1,
        "clarification_request": 1,
        "partial_attempt": 2,
        "revision_attempt": 2,
        "local_explanation": 3,
    }
    max_sentences = max_sentences_map[response_space]
    if mode == "protocol_light":
        max_sentences += 1

    allowed_actions = _build_allowed_actions(
        response_space=response_space,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        turn_response_constraint=turn_response_constraint,
        ablation_mode=mode,
    )
    disallowed_actions = _build_disallowed_actions(
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        turn_response_constraint=turn_response_constraint,
        ablation_mode=mode,
    )
    support_use_rules = _build_support_use_rules(
        tutor_move=tutor_move,
        support_uptake=support_uptake,
        turn_response_constraint=turn_response_constraint,
        response_space=response_space,
        ablation_mode=mode,
    )
    realization_requirements = _build_realization_requirements(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        turn_response_constraint=turn_response_constraint,
        local_error_state=local_error_state,
        local_claim_seed=local_claim_seed,
    )
    packet_rationale = [
        (
            "Current local object is "
            f"{tutor_move.elicited_object_description}; "
            f"access zone is {learning_access_state.access_zone}."
        ),
        (
            "Predicted uptake depth is "
            f"{support_uptake.uptake_depth}; "
            f"compiled response space is {response_space}."
        ),
        (
            "Target overt engagement is "
            f"{support_uptake.likely_next_engagement_mode}; "
            f"ablation mode is {mode}."
        ),
        (
            "Claim requirement is "
            f"{turn_response_constraint.claim_requirement}; "
            f"error pressure is {turn_response_constraint.error_pressure}."
        ),
        (
            "Mediated target availability is "
            f"{mediated_target_availability.target_availability}; "
            f"success affordance is {mediated_target_availability.success_affordance}; "
            f"error continuity risk is {mediated_target_availability.error_continuity_risk}."
        ),
        (
            "Local claim seed mode is "
            f"{local_claim_seed.claim_seed_mode}; "
            f"support-consistent claim seed is {local_claim_seed.support_consistent_claim_seed}."
        ),
        (
            "Persistent obstacle is "
            f"{learning_access_state.persistent_obstacle}; "
            f"prior evidence count is {len(student_prior.prior_evidence)}; "
            f"population calibration prior count is {len(student_prior.population_calibration_prior)}; "
            f"history turns available are {visible_context.turn_count_so_far}."
        ),
    ]
    return TeachingSupportPacket(
        packet_version="eedi_weak_harness_v3.2",
        ablation_mode=mode,
        local_focus=tutor_move.elicited_object_description,
        access_zone=learning_access_state.access_zone,
        response_space=response_space,
        claim_requirement=turn_response_constraint.claim_requirement,
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
        claim_seed_mode=local_claim_seed.claim_seed_mode,
        support_consistent_claim_seed=local_claim_seed.support_consistent_claim_seed,
        realization_requirements=realization_requirements,
        allowed_actions=allowed_actions,
        disallowed_actions=disallowed_actions,
        support_use_rules=support_use_rules,
        packet_rationale=packet_rationale,
    )


def update_learning_state(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    teaching_support_packet: TeachingSupportPacket,
    generated_turn: str,
    llm_client: OpenAICompatClient,
) -> LearningStateUpdate:
    payload = {
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "teaching_support_packet": asdict(teaching_support_packet),
        "generated_turn": generated_turn,
        "required_schema": {
            "observed_engagement_mode": list(ICAP_LEVELS),
            "observed_uptake_depth": list(UPTAKE_DEPTH_LEVELS),
            "predicted_next_readiness": list(TURN_READINESS_STATES),
            "persistent_obstacle": list(PERSISTENT_OBSTACLE_TYPES),
            "update_evidence": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=LEARNING_STATE_UPDATE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_learning_state_update(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=LEARNING_STATE_UPDATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_learning_state_update(repaired)


def _build_allowed_actions(
    response_space: str,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    turn_response_constraint: TurnResponseConstraintState,
    ablation_mode: str,
) -> list[str]:
    focus = tutor_move.elicited_object_description
    if response_space == "brief_acknowledgment":
        actions = [
            "Briefly acknowledge the tutor's cue.",
            f"Stay on the exact local object: {focus}.",
        ]
    elif response_space == "clarification_request":
        actions = [
            f"Ask one focused question about the exact local object: {focus}.",
            "State the local point of difficulty without inventing a full solution.",
        ]
    elif response_space == "partial_attempt":
        actions = [
            f"Make one local attempt on the exact object: {focus}.",
            "Use the current tutor support on only one local relation, representation, or step.",
        ]
    elif response_space == "revision_attempt":
        actions = [
            "Revise the immediately prior idea rather than restarting the whole problem.",
            f"Keep the revision tied to the exact local object: {focus}.",
        ]
    elif response_space == "local_explanation":
        actions = [
            f"Give a short local explanation about the exact object: {focus}.",
            "Explain only the current local judgment, not a full polished solution.",
        ]
    else:
        raise ValueError(
            f"unsupported response_space={response_space}; "
            f"learning_access_state={learning_access_state!r}"
        )
    if turn_response_constraint.claim_requirement == "tentative_claim_allowed":
        actions.append(
            "A tentative local mathematical claim is allowed if it stays tied to the current object."
        )
    if turn_response_constraint.claim_requirement == "local_claim_required":
        actions.append(
            "Make one local mathematical claim on the current object instead of only acknowledging."
        )
    if (
        ablation_mode == "commitment_first"
        and turn_response_constraint.claim_requirement == "local_claim_required"
    ):
        actions.append(
            "Make one direct local mathematical claim instead of defaulting to tentative hedging."
        )
    if ablation_mode == "protocol_light":
        actions.append("Prefer plain student wording over protocol-heavy explanation.")
    return actions


def _build_disallowed_actions(
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    turn_response_constraint: TurnResponseConstraintState,
    ablation_mode: str,
) -> list[str]:
    disallowed = [
        "Do not answer like a tutor or evaluator.",
        "Do not jump to a polished full-problem solution.",
        "Do not use future information or future turns.",
    ]
    if turn_response_constraint.claim_requirement == "no_claim":
        disallowed.append(
            "Do not force a concrete mathematical claim when the current turn only affords acknowledgment or clarification."
        )
    if learning_access_state.access_zone != "already_can_do":
        disallowed.append(
            "Do not pretend the student has stable independent mastery of this local work."
        )
    if support_uptake.uptake_depth in {"no_uptake", "noticing_only"}:
        disallowed.append(
            "Do not claim that the tutor support has already been fully turned into a solid mathematical solution."
        )
    if ablation_mode == "commitment_first":
        disallowed.append(
            "Do not replace local commitment with polished full-problem mastery."
        )
    return disallowed


def _build_support_use_rules(
    tutor_move: TutorMove,
    support_uptake: SupportUptake,
    turn_response_constraint: TurnResponseConstraintState,
    response_space: str,
    ablation_mode: str,
) -> list[str]:
    focus = tutor_move.elicited_object_description
    if support_uptake.uptake_depth == "no_uptake":
        rules = [
            f"If you respond, keep it at the level of still not getting the local object: {focus}.",
            "Do not fabricate a substantive mathematical move that the support did not unlock.",
        ]
    elif support_uptake.uptake_depth == "noticing_only":
        rules = [
            "You may orient to the tutor cue.",
            f"But do not convert that cue into a full local solution about: {focus}.",
        ]
    elif support_uptake.uptake_depth == "partial_use":
        rules = [
            f"Use the support on one local target only: {focus}.",
            "Keep the uptake transitional rather than fully mastered.",
        ]
    elif support_uptake.uptake_depth == "substantive_use":
        rules = [
            f"You may use the support to make one substantive local move on: {focus}.",
            "Even so, keep the voice and scope student-like and local.",
        ]
    else:
        raise ValueError(f"unsupported uptake_depth: {support_uptake.uptake_depth}")
    if turn_response_constraint.claim_requirement == "tentative_claim_allowed":
        rules.append("A tentative local claim is allowed, but it does not have to become a polished solution.")
    elif turn_response_constraint.claim_requirement == "local_claim_required":
        rules.append("A local mathematical claim is expected if the response space already supports an attempt.")
    if ablation_mode == "commitment_first" and response_space in {
        "partial_attempt",
        "revision_attempt",
        "local_explanation",
    }:
        rules.append(
            "A committed local answer is allowed even if it is still incomplete or incorrect."
        )
    if ablation_mode == "protocol_light":
        rules.append(
            "Keep the reply locally focused, but do not spend tokens on protocol bookkeeping."
        )
    return rules


def _build_realization_requirements(
    visible_context: VisibleContext,
    student_prior: StudentPrior,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    turn_response_constraint: TurnResponseConstraintState,
    local_error_state: LocalErrorRealizationState,
    local_claim_seed: LocalClaimSeedState,
) -> list[str]:
    requirements = [
        f"Stay on the tutor's exact local object: {tutor_move.elicited_object_description}.",
        (
            "Keep continuity with the latest visible student state: "
            f"{visible_context.last_student_turn or 'no prior student turn available'}."
        ),
        (
            "Match the current regulation pattern: "
            f"{learning_access_state.regulation_state}; "
            f"uptake depth is {support_uptake.uptake_depth}."
        ),
        (
            "Claim requirement is "
            f"{turn_response_constraint.claim_requirement}; "
            f"error pressure is {turn_response_constraint.error_pressure}."
        ),
    ]
    if local_error_state.error_presence == "codable_math_error":
        requirements.extend(
            [
                "The final turn must contain one concrete local mathematical claim.",
                f"Anchor the claim to this wrong direction: {local_error_state.wrong_claim_seed}.",
                f"Keep the Newman error locus at: {local_error_state.newman_error_locus}.",
                (
                    "Keep the error mechanism consistent with: "
                    f"{local_error_state.radatz_error_mechanism}."
                ),
                f"Preserve this buggy rule: {local_error_state.buggy_rule}.",
            ]
        )
    elif local_error_state.error_presence == "non_codable_confusion":
        requirements.append(
            "Do not force a concrete mathematical claim if the next turn is only locally confused."
        )
    else:
        if turn_response_constraint.claim_requirement == "no_claim":
            requirements.append(
                "Do not invent a specific mathematical error if the local state does not support one."
            )
        elif turn_response_constraint.claim_requirement == "tentative_claim_allowed":
            requirements.append(
                "A tentative local claim is allowed, but it should not be forced into a specific error code."
            )
        else:
            requirements.append(
                "A concrete local claim is required on the current object, but do not force it into an error if the mediated state supports success."
            )
    if local_claim_seed.claim_seed_mode == "support_consistent_claim_available":
        requirements.append(
            "Use this support-consistent local claim seed when realizing a non-error mathematical claim: "
            f"{local_claim_seed.support_consistent_claim_seed}."
        )
    elif local_claim_seed.claim_seed_mode == "insufficient_visible_basis":
        requirements.append(
            "The visible support does not provide enough basis for a stable non-error claim; keep any claim cautious and local."
        )
    if student_prior.response_style_description:
        requirements.append(
            "Keep the wording compatible with the student's response style: "
            f"{student_prior.response_style_description}."
        )
    if student_prior.population_calibration_prior:
        requirements.append(
            "Treat the population calibration summary only as a weak group prior for similar students: "
            f"{student_prior.population_calibration_prior[0]}"
        )
    if student_prior.population_calibration_cautions:
        requirements.append(student_prior.population_calibration_cautions[0])
    return requirements


def _resolve_turn_response_space(
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
) -> str:
    if learning_access_state.turn_readiness == "ask_for_clarification":
        return "clarification_request"
    if learning_access_state.tutor_intent_grasp == "misread":
        return "clarification_request"
    if learning_access_state.access_zone == "not_reachable_this_turn":
        return "clarification_request"
    if learning_access_state.turn_readiness == "acknowledge_or_brief_react":
        return (
            "brief_acknowledgment"
            if support_uptake.uptake_depth in {"no_uptake", "noticing_only"}
            else "clarification_request"
        )
    if learning_access_state.turn_readiness == "revise_prior_idea":
        return "revision_attempt"
    if tutor_move.elicited_response_target_type == "explanation_or_judgment":
        if (
            learning_access_state.turn_readiness == "explain_current_judgment"
            and support_uptake.uptake_depth in {"partial_use", "substantive_use"}
        ):
            return "local_explanation"
        if support_uptake.uptake_depth in {"partial_use", "substantive_use"}:
            return "partial_attempt"
        return "clarification_request"
    if tutor_move.elicited_response_target_type in {
        "procedure_step",
        "result_or_selection",
        "representation",
    }:
        if support_uptake.uptake_depth in {"partial_use", "substantive_use"}:
            return "partial_attempt"
        if support_uptake.uptake_depth == "noticing_only":
            return "clarification_request"
        return "brief_acknowledgment"
    if math_claim_affordance.claim_affordance == "math_claim_expected":
        return "partial_attempt"
    if math_claim_affordance.claim_affordance == "math_claim_possible":
        return "clarification_request"
    return support_uptake.response_space


def _resolve_claim_requirement(
    response_space: str,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
) -> str:
    if response_space in {"brief_acknowledgment", "clarification_request"}:
        return "no_claim"
    if math_claim_affordance.claim_affordance == "no_math_claim_expected":
        return "no_claim"
    if (
        math_claim_affordance.claim_affordance == "math_claim_expected"
        and _tutor_is_eliciting_local_math_content(tutor_move)
        and learning_access_state.turn_readiness
        in {"attempt_local_step", "revise_prior_idea", "explain_current_judgment"}
        and support_uptake.uptake_depth in {"partial_use", "substantive_use"}
    ):
        return "local_claim_required"
    if math_claim_affordance.claim_affordance == "math_claim_possible":
        return "tentative_claim_allowed"
    return "no_claim"


def _resolve_error_pressure(
    response_space: str,
    claim_requirement: str,
    tutor_move: TutorMove,
    learning_access_state: LearningAccessState,
    support_uptake: SupportUptake,
    math_claim_affordance: MathClaimAffordanceState,
    mediated_target_availability: MediatedTargetAvailabilityState,
) -> str:
    if claim_requirement == "no_claim":
        return "suppressed"
    if mediated_target_availability.error_continuity_risk == "suppressed":
        return "suppressed"
    if (
        mediated_target_availability.success_affordance == "high"
        and mediated_target_availability.target_availability
        in {"worked_local_step_available", "target_almost_explicit"}
    ):
        return "suppressed"
    if (
        mediated_target_availability.success_affordance == "high"
        and support_uptake.uptake_depth == "substantive_use"
    ):
        return "open"
    if (
        mediated_target_availability.success_affordance == "moderate"
        and mediated_target_availability.target_availability
        in {"worked_local_step_available", "target_almost_explicit"}
    ):
        return "open"
    if mediated_target_availability.error_continuity_risk == "likely":
        if mediated_target_availability.success_affordance == "low":
            return "likely"
        return "open"
    if learning_access_state.access_zone == "already_can_do" and learning_access_state.persistent_obstacle in {
        "no_major_obstacle",
        "confidence_barrier",
    }:
        return "suppressed"
    if learning_access_state.persistent_obstacle in {"misconception", "missing_relation"} and support_uptake.uptake_depth in {
        "partial_use",
        "substantive_use",
    }:
        return "likely"
    if (
        learning_access_state.persistent_obstacle == "execution_gap"
        and tutor_move.elicited_response_target_type
        in {"procedure_step", "result_or_selection", "representation"}
    ):
        return "likely"
    if response_space == "local_explanation" and math_claim_affordance.error_opportunity == "misconception_continuity":
        return "likely"
    return "open"


def _parse_mediated_target_availability_state(
    parsed: object,
) -> MediatedTargetAvailabilityState:
    parsed = require_keys(
        parsed,
        (
            "target_availability",
            "success_affordance",
            "error_continuity_risk",
            "availability_evidence",
        ),
        "MediatedTargetAvailabilityState",
    )
    return MediatedTargetAvailabilityState(
        target_availability=_coerce_enum(
            parsed["target_availability"],
            TARGET_AVAILABILITY_STATES,
            "target_availability",
        ),
        success_affordance=_coerce_enum(
            parsed["success_affordance"],
            SUCCESS_AFFORDANCE_STATES,
            "success_affordance",
        ),
        error_continuity_risk=_coerce_enum(
            parsed["error_continuity_risk"],
            ERROR_PRESSURE_STATES,
            "error_continuity_risk",
        ),
        availability_evidence=_coerce_str_list(
            parsed["availability_evidence"],
            "availability_evidence",
        ),
    )


def _parse_local_claim_seed_state(parsed: object) -> LocalClaimSeedState:
    parsed = require_keys(
        parsed,
        (
            "claim_seed_mode",
            "support_consistent_claim_seed",
            "claim_seed_evidence",
        ),
        "LocalClaimSeedState",
    )
    claim_seed_mode = _coerce_enum(
        parsed["claim_seed_mode"],
        CLAIM_SEED_MODES,
        "claim_seed_mode",
    )
    support_consistent_claim_seed = _coerce_nullable_text(
        parsed["support_consistent_claim_seed"],
        "support_consistent_claim_seed",
    )
    if claim_seed_mode == "support_consistent_claim_available":
        if support_consistent_claim_seed is None:
            raise ValueError(
                "support_consistent_claim_available requires a non-empty support_consistent_claim_seed"
            )
    elif support_consistent_claim_seed is not None:
        raise ValueError(
            "support_consistent_claim_seed must be null unless claim_seed_mode is support_consistent_claim_available"
        )
    return LocalClaimSeedState(
        claim_seed_mode=claim_seed_mode,
        support_consistent_claim_seed=support_consistent_claim_seed,
        claim_seed_evidence=_coerce_str_list(
            parsed["claim_seed_evidence"],
            "claim_seed_evidence",
        ),
    )


def _tutor_is_eliciting_local_math_content(tutor_move: TutorMove) -> bool:
    return (
        tutor_move.support_type
        in {
            "conceptual_hint",
            "procedural_hint",
            "answer_elicitation",
            "error_challenge",
            "explanation_request",
        }
        and tutor_move.target_of_intervention
        in {"misconception", "missing_step", "explanation_depth", "commitment"}
    )


def error_blueprint_to_local_error_state(
    blueprint: ErrorBlueprint,
) -> LocalErrorRealizationState:
    return LocalErrorRealizationState(
        error_presence=blueprint.error_presence,
        newman_error_locus=blueprint.newman_error_locus,
        radatz_error_mechanism=blueprint.radatz_error_mechanism,
        buggy_rule=blueprint.buggy_rule,
        wrong_claim_seed=blueprint.wrong_claim_seed,
        realization_evidence=list(blueprint.blueprint_evidence),
    )


def _parse_learning_access_state(parsed: object) -> LearningAccessState:
    parsed = require_keys(
        parsed,
        (
            "access_zone",
            "tutor_intent_grasp",
            "uptake_preparation",
            "turn_readiness",
            "regulation_state",
            "current_engagement_mode",
            "persistent_obstacle",
            "state_evidence",
        ),
        "LearningAccessState",
    )
    return LearningAccessState(
        access_zone=_coerce_enum(
            parsed["access_zone"],
            LEARNING_ACCESS_ZONES,
            "access_zone",
        ),
        tutor_intent_grasp=_coerce_enum(
            parsed["tutor_intent_grasp"],
            TUTOR_INTENT_GRASP_LEVELS,
            "tutor_intent_grasp",
        ),
        uptake_preparation=_coerce_enum(
            parsed["uptake_preparation"],
            UPTAKE_PREPARATION_LEVELS,
            "uptake_preparation",
        ),
        turn_readiness=_coerce_enum(
            parsed["turn_readiness"],
            TURN_READINESS_STATES,
            "turn_readiness",
        ),
        regulation_state=_coerce_enum(
            parsed["regulation_state"],
            REGULATION_STATES,
            "regulation_state",
        ),
        current_engagement_mode=_coerce_enum(
            parsed["current_engagement_mode"],
            ICAP_LEVELS,
            "current_engagement_mode",
        ),
        persistent_obstacle=_coerce_enum(
            parsed["persistent_obstacle"],
            PERSISTENT_OBSTACLE_TYPES,
            "persistent_obstacle",
        ),
        state_evidence=_coerce_str_list(parsed["state_evidence"], "state_evidence"),
    )


def _parse_support_uptake(parsed: object) -> SupportUptake:
    parsed = require_keys(
        parsed,
        (
            "uptake_depth",
            "uptake_focus",
            "response_space",
            "likely_next_engagement_mode",
            "uptake_rationale",
        ),
        "SupportUptake",
    )
    return SupportUptake(
        uptake_depth=_coerce_enum(
            parsed["uptake_depth"],
            UPTAKE_DEPTH_LEVELS,
            "uptake_depth",
        ),
        uptake_focus=_coerce_enum(
            parsed["uptake_focus"],
            UPTAKE_FOCUS_TYPES,
            "uptake_focus",
        ),
        response_space=_coerce_enum(
            parsed["response_space"],
            RESPONSE_SPACE_TYPES,
            "response_space",
        ),
        likely_next_engagement_mode=_coerce_enum(
            parsed["likely_next_engagement_mode"],
            ICAP_LEVELS,
            "likely_next_engagement_mode",
        ),
        uptake_rationale=_coerce_str_list(
            parsed["uptake_rationale"],
            "uptake_rationale",
        ),
    )


def _parse_math_claim_affordance_state(parsed: object) -> MathClaimAffordanceState:
    parsed = require_keys(
        parsed,
        (
            "claim_affordance",
            "error_opportunity",
            "expected_claim_shape",
            "affordance_evidence",
        ),
        "MathClaimAffordanceState",
    )
    expected_claim_shape = str(parsed["expected_claim_shape"]).strip()
    if not expected_claim_shape:
        raise ValueError("expected_claim_shape cannot be empty")
    return MathClaimAffordanceState(
        claim_affordance=_coerce_enum(
            parsed["claim_affordance"],
            MATH_CLAIM_AFFORDANCE_STATES,
            "claim_affordance",
        ),
        error_opportunity=_coerce_enum(
            parsed["error_opportunity"],
            ERROR_OPPORTUNITY_STATES,
            "error_opportunity",
        ),
        expected_claim_shape=expected_claim_shape,
        affordance_evidence=_coerce_str_list(
            parsed["affordance_evidence"],
            "affordance_evidence",
        ),
    )


def _parse_learning_state_update(parsed: object) -> LearningStateUpdate:
    parsed = require_keys(
        parsed,
        (
            "observed_engagement_mode",
            "observed_uptake_depth",
            "predicted_next_readiness",
            "persistent_obstacle",
            "update_evidence",
        ),
        "LearningStateUpdate",
    )
    return LearningStateUpdate(
        observed_engagement_mode=_coerce_enum(
            parsed["observed_engagement_mode"],
            ICAP_LEVELS,
            "observed_engagement_mode",
        ),
        observed_uptake_depth=_coerce_enum(
            parsed["observed_uptake_depth"],
            UPTAKE_DEPTH_LEVELS,
            "observed_uptake_depth",
        ),
        predicted_next_readiness=_coerce_enum(
            parsed["predicted_next_readiness"],
            TURN_READINESS_STATES,
            "predicted_next_readiness",
        ),
        persistent_obstacle=_coerce_enum(
            parsed["persistent_obstacle"],
            PERSISTENT_OBSTACLE_TYPES,
            "persistent_obstacle",
        ),
        update_evidence=_coerce_str_list(parsed["update_evidence"], "update_evidence"),
    )


def _parse_local_error_realization_state(parsed: object) -> LocalErrorRealizationState:
    parsed = require_keys(
        parsed,
        (
            "error_presence",
            "newman_error_locus",
            "radatz_error_mechanism",
            "buggy_rule",
            "wrong_claim_seed",
            "realization_evidence",
        ),
        "LocalErrorRealizationState",
    )
    error_presence = _coerce_enum(
        parsed["error_presence"],
        ERROR_PRESENCE_STATES,
        "error_presence",
    )
    newman_error_locus = _coerce_nullable_enum(
        parsed["newman_error_locus"],
        NEWMAN_ERROR_LOCI,
        "newman_error_locus",
    )
    radatz_error_mechanism = _coerce_nullable_enum(
        parsed["radatz_error_mechanism"],
        RADATZ_ERROR_MECHANISMS,
        "radatz_error_mechanism",
    )
    buggy_rule = _coerce_nullable_text(parsed["buggy_rule"], "buggy_rule")
    wrong_claim_seed = _coerce_nullable_text(parsed["wrong_claim_seed"], "wrong_claim_seed")
    realization_evidence = _coerce_str_list(
        parsed["realization_evidence"],
        "realization_evidence",
    )
    if error_presence == "codable_math_error":
        if (
            newman_error_locus is None
            or radatz_error_mechanism is None
            or buggy_rule is None
            or wrong_claim_seed is None
        ):
            raise ValueError(
                "codable_math_error requires non-null newman_error_locus, "
                "radatz_error_mechanism, buggy_rule, and wrong_claim_seed"
            )
    return LocalErrorRealizationState(
        error_presence=error_presence,
        newman_error_locus=newman_error_locus,
        radatz_error_mechanism=radatz_error_mechanism,
        buggy_rule=buggy_rule,
        wrong_claim_seed=wrong_claim_seed,
        realization_evidence=realization_evidence,
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
) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed}, got {text!r}")
    return text


def _coerce_nullable_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result
