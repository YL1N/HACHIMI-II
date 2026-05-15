from __future__ import annotations

from .error_blueprint import ErrorBlueprint
from .student_model import StudentContextProfile
from .student_turn_state import InteractionState
from .transition import StateTransitionPrediction
from .tutor_turn_profile import TutorTurnProfile


def apply_student_context_profile_revisit(
    profile: StudentContextProfile,
    mode: str,
) -> StudentContextProfile:
    if mode == "full":
        return profile
    if mode != "behavioral_only":
        raise ValueError(f"unsupported student_context_profile_mode: {mode}")
    return StudentContextProfile(
        self_efficacy_analysis={
            "efficacy_belief_description": "masked in this revisit variant",
            "efficacy_belief_evidence": ["masked in this revisit variant"],
        },
        srl_analysis={
            "primary_srl_vulnerability": "masked in this revisit variant",
            "srl_process_evidence": ["masked in this revisit variant"],
        },
        control_value_analysis={
            "control_appraisal_description": "masked in this revisit variant",
            "value_appraisal_description": "masked in this revisit variant",
            "control_value_evidence": ["masked in this revisit variant"],
        },
        engagement_tendency_analysis=dict(profile.engagement_tendency_analysis),
        response_style_analysis=dict(profile.response_style_analysis),
        evidence_trace=list(profile.evidence_trace)
        + ["revisit: masked self_efficacy_analysis / srl_analysis / control_value_analysis"],
    )


def apply_tutor_turn_profile_revisit(
    profile: TutorTurnProfile,
    mode: str,
) -> TutorTurnProfile:
    if mode == "full":
        return profile
    if mode != "core":
        raise ValueError(f"unsupported tutor_turn_profile_mode: {mode}")
    return TutorTurnProfile(
        instructional_intent="coarsened tutor move summary for revisit",
        support_type=profile.support_type,
        support_intensity="medium",
        support_granularity="localized_step",
        support_contingency="moderately_contingent",
        responsibility_shift="shared",
        target_of_intervention=profile.target_of_intervention,
        uptake_expectation="local_update",
        elicited_response_process=profile.elicited_response_process,
        elicited_response_target_type=profile.elicited_response_target_type,
        elicited_object_description=profile.elicited_object_description,
        move_evidence=list(profile.move_evidence)
        + ["revisit: coarsened support intensity / granularity / contingency / responsibility"],
    )


def apply_interaction_state_revisit(
    state: InteractionState,
    mode: str,
) -> InteractionState:
    if mode == "full":
        return state
    if mode != "core":
        raise ValueError(f"unsupported interaction_state_mode: {mode}")
    return InteractionState(
        competence_position="within_zpd",
        misconception_status=state.misconception_status,
        metacognitive_regulation_state="weak_monitoring",
        help_internalization_state="surface_uptake",
        help_seeking_state="help_ambivalent",
        attempt_readiness=state.attempt_readiness,
        engagement_form=state.engagement_form,
        response_commitment_state=state.response_commitment_state,
        response_maturity_cap=state.response_maturity_cap,
        state_evidence=list(state.state_evidence)
        + ["revisit: coarsened competence / metacognition / help uptake / help seeking"],
    )


def apply_transition_prediction_revisit(
    prediction: StateTransitionPrediction,
    mode: str,
) -> StateTransitionPrediction:
    if mode == "full":
        return prediction
    if mode != "core":
        raise ValueError(f"unsupported transition_prediction_mode: {mode}")
    return StateTransitionPrediction(
        predicted_next_competence_position="within_zpd",
        predicted_next_misconception_status=prediction.predicted_next_misconception_status,
        predicted_next_metacognitive_regulation_state="weak_monitoring",
        predicted_next_help_internalization_state="surface_uptake",
        predicted_next_help_seeking_state="help_ambivalent",
        predicted_next_attempt_readiness=prediction.predicted_next_attempt_readiness,
        predicted_next_engagement_form=prediction.predicted_next_engagement_form,
        predicted_next_response_commitment_state=prediction.predicted_next_response_commitment_state,
        predicted_next_response_maturity_cap=prediction.predicted_next_response_maturity_cap,
        predicted_misconception_trajectory_shift=prediction.predicted_misconception_trajectory_shift,
        transition_rationale=list(prediction.transition_rationale)
        + ["revisit: coarsened competence / metacognition / help uptake / help seeking"],
    )


def apply_error_blueprint_revisit(
    blueprint: ErrorBlueprint,
    mode: str,
) -> ErrorBlueprint:
    if mode == "full":
        return blueprint
    supported_modes = {
        "structure_only",
        "structure_plus_wrong_claim_seed",
        "structure_plus_buggy_rule",
        "structure_no_mechanism",
    }
    if mode not in supported_modes:
        raise ValueError(f"unsupported error_blueprint_mode: {mode}")
    if blueprint.error_presence != "codable_math_error":
        return ErrorBlueprint(
            error_presence=blueprint.error_presence,
            newman_error_locus=blueprint.newman_error_locus,
            radatz_error_mechanism=blueprint.radatz_error_mechanism,
            buggy_rule=blueprint.buggy_rule,
            wrong_claim_seed=blueprint.wrong_claim_seed,
            blueprint_evidence=list(blueprint.blueprint_evidence)
            + ["revisit: non-codable blueprint left unchanged"],
        )

    newman_error_locus = blueprint.newman_error_locus
    radatz_error_mechanism = blueprint.radatz_error_mechanism
    buggy_rule = "a locally incorrect mathematical rule or relation"
    wrong_claim_seed = "the locally relevant wrong claim under discussion"
    evidence_note = "revisit: specific buggy_rule / wrong_claim_seed replaced by structural placeholders"

    if mode == "structure_plus_wrong_claim_seed":
        wrong_claim_seed = blueprint.wrong_claim_seed
        evidence_note = "revisit: preserved wrong_claim_seed but replaced buggy_rule with structural placeholder"
    elif mode == "structure_plus_buggy_rule":
        buggy_rule = blueprint.buggy_rule
        evidence_note = "revisit: preserved buggy_rule but replaced wrong_claim_seed with structural placeholder"
    elif mode == "structure_no_mechanism":
        radatz_error_mechanism = "deficient_prerequisites"
        evidence_note = "revisit: preserved error presence / locus but coarsened mechanism and concrete seeds"

    return ErrorBlueprint(
        error_presence=blueprint.error_presence,
        newman_error_locus=newman_error_locus,
        radatz_error_mechanism=radatz_error_mechanism,
        buggy_rule=buggy_rule,
        wrong_claim_seed=wrong_claim_seed,
        blueprint_evidence=list(blueprint.blueprint_evidence)
        + [evidence_note],
    )
