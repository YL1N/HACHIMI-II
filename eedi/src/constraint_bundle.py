from __future__ import annotations

from dataclasses import asdict, dataclass

from .error_blueprint import ErrorBlueprint
from .transition import StateTransitionPrediction


@dataclass(frozen=True)
class ConstraintBundle:
    max_sentences: int
    max_step_budget: int
    allow_direct_answer: bool
    allow_full_reasoning: bool
    allow_help_seeking_language: bool
    must_preserve_local_confusion: bool
    must_preserve_misconception_continuity: bool
    expected_error_presence: str
    expected_newman_error_locus: str | None
    expected_radatz_error_mechanism: str | None
    buggy_rule: str | None
    wrong_claim_seed: str | None
    must_realize_specific_error: bool
    must_anchor_to_local_wrong_claim: bool
    required_commitment_style: str
    forbidden_patterns: list[str]
    style_constraints: list[str]


def compile_constraints(
    prediction: StateTransitionPrediction,
    error_blueprint: ErrorBlueprint,
) -> ConstraintBundle:
    maturity = prediction.predicted_next_response_maturity_cap
    commitment = prediction.predicted_next_response_commitment_state
    engagement = prediction.predicted_next_engagement_form
    misconception = prediction.predicted_next_misconception_status
    internalization = prediction.predicted_next_help_internalization_state
    help_seeking = prediction.predicted_next_help_seeking_state
    attempt_readiness = prediction.predicted_next_attempt_readiness
    trajectory_shift = prediction.predicted_misconception_trajectory_shift

    if maturity == "fragment_only":
        max_sentences = 1
        max_step_budget = 1
        allow_full_reasoning = False
    elif maturity == "brief_local_explanation":
        max_sentences = 2
        max_step_budget = 2
        allow_full_reasoning = False
    elif maturity == "limited_structured_reasoning":
        max_sentences = 3
        max_step_budget = 3
        allow_full_reasoning = False
    elif maturity == "full_student_level_reasoning":
        max_sentences = 4
        max_step_budget = 4
        allow_full_reasoning = True
    else:
        raise ValueError(f"unsupported maturity cap: {maturity}")

    # A student can state a direct answer while still being locally uncertain or wrong.
    # Directness should depend primarily on whether the student is ready to attempt,
    # not on whether the student sounds fully resolved.
    allow_direct_answer = (
        attempt_readiness != "not_ready" and commitment != "avoidant"
    )
    required_commitment_style = commitment
    allow_help_seeking_language = help_seeking != "help_avoidant"
    must_preserve_local_confusion = (
        attempt_readiness == "not_ready"
        and help_seeking in {"help_ambivalent", "adaptive_help_seeking"}
    )
    must_preserve_misconception_continuity = (
        misconception in {"active_misconception", "destabilizing_misconception"}
        and trajectory_shift in {"hold_trajectory", "perturb_trajectory"}
    )
    must_realize_specific_error = (
        error_blueprint.error_presence == "codable_math_error"
        and attempt_readiness in {"ready_for_local_attempt", "ready_to_revise"}
        and commitment != "avoidant"
    )
    must_anchor_to_local_wrong_claim = (
        must_realize_specific_error
        and misconception in {"active_misconception", "destabilizing_misconception"}
        and trajectory_shift in {"hold_trajectory", "perturb_trajectory"}
        and commitment != "avoidant"
    )

    forbidden_patterns = [
        "Do not speak like a tutor.",
        "Do not mention future turns or future plans.",
        "Do not claim certainty beyond the predicted state.",
    ]
    if maturity != "full_student_level_reasoning":
        forbidden_patterns.append(
            "Do not provide a complete polished full-solution explanation."
        )
    if misconception == "active_misconception":
        forbidden_patterns.append(
            "Do not suddenly switch to fully correct mature understanding without local transition."
        )
    if internalization in {"no_uptake", "surface_uptake"}:
        forbidden_patterns.append(
            "Do not act as if the tutor hint has already been deeply internalized."
        )
    if must_preserve_local_confusion:
        forbidden_patterns.append(
            "Do not erase the student's local uncertainty or monitoring struggle too abruptly."
        )
    if must_preserve_misconception_continuity:
        forbidden_patterns.append(
            "Do not replace the current misconception path with a fully corrected or unrelated line of reasoning."
        )
    if must_realize_specific_error:
        forbidden_patterns.append(
            "Do not replace the predicted concrete math error with generic confusion, generic hedging, or a generic help request."
        )
    if must_anchor_to_local_wrong_claim:
        forbidden_patterns.append(
            "Do not replace the local wrong-claim target with a different subproblem, a different answer type, or a broader earlier-stage mistake."
        )

    style_constraints = [
        f"Stay within {max_sentences} sentence(s).",
        f"Engagement form should look like {engagement}.",
        _commitment_style_instruction(required_commitment_style),
        "Prefer in-the-moment student wording over polished exposition.",
    ]
    if maturity == "fragment_only":
        style_constraints.append(
            "Use only a fragment, short acknowledgment, short question, or short local answer shape, not a neat full explanation."
        )
    elif maturity == "brief_local_explanation":
        style_constraints.append(
            "At most give one local reason or local step, and keep it rough rather than fully organized."
        )
    elif maturity == "limited_structured_reasoning":
        style_constraints.append(
            "A couple of linked clauses are allowed, but the turn should still sound like a student thinking in the moment."
        )
    elif maturity == "full_student_level_reasoning":
        style_constraints.append(
            "A fuller explanation is allowed, but it must still sound like a student rather than a tutor or analyst."
        )
    if attempt_readiness == "not_ready":
        style_constraints.append(
            "The student is not ready for a substantive attempt yet; keep the turn local or support-oriented without inventing a full solution."
        )
    elif attempt_readiness == "ready_for_local_attempt":
        style_constraints.append(
            "A local attempt is allowed, but keep it partial rather than fully worked out."
        )
    elif attempt_readiness == "ready_to_revise":
        style_constraints.append(
            "A local revision of the student's prior idea is allowed, but do not jump to a polished full solution."
        )
    if allow_help_seeking_language:
        style_constraints.append(
            "A brief request for help, clarification, or confirmation is allowed only if it fits the local state."
        )
    else:
        style_constraints.append(
            "If the student is confused, express it locally without shifting into an explicit help-seeking turn."
        )
    if must_preserve_misconception_continuity:
        style_constraints.append(
            "Keep continuity with the student's current misconception trajectory even if the error is starting to wobble."
        )
    elif trajectory_shift == "local_repair":
        style_constraints.append(
            "A small local repair is allowed, but the turn should still sound transitional rather than suddenly mastered."
        )
    elif trajectory_shift == "consolidate_repair":
        style_constraints.append(
            "A stronger repair is allowed, but the student should still sound like a learner rather than a tutor."
        )
    if not allow_direct_answer:
        style_constraints.append(
            "Do not force a fully direct final answer when the local state only supports a fragment, clarification, or partial attempt."
        )
    if not allow_full_reasoning:
        style_constraints.append("Reasoning must stay local and incomplete.")
    if must_realize_specific_error:
        style_constraints.append(
            "Realize one concrete local incorrect mathematical claim in the utterance."
        )
        style_constraints.append(
            f"Keep the error at Newman locus: {error_blueprint.newman_error_locus}."
        )
        style_constraints.append(
            f"Keep the error mechanism consistent with: {error_blueprint.radatz_error_mechanism}."
        )
        style_constraints.append(
            f"Preserve this buggy rule: {error_blueprint.buggy_rule}."
        )
        style_constraints.append(
            f"Use this wrong-claim direction as the local target: {error_blueprint.wrong_claim_seed}."
        )
        if must_anchor_to_local_wrong_claim:
            style_constraints.append(
                "Keep the error tied to the exact local object the tutor is currently asking about."
            )
            style_constraints.append(
                "Do not drift to another answer type, another step, or another earlier misconception if the current tutor move is asking for a more local target."
            )
    elif error_blueprint.error_presence == "non_codable_confusion":
        style_constraints.append(
            "The turn may stay confused or incomplete, but do not invent a fully specific math error that is not supported by the visible state."
        )

    return ConstraintBundle(
        max_sentences=max_sentences,
        max_step_budget=max_step_budget,
        allow_direct_answer=allow_direct_answer,
        allow_full_reasoning=allow_full_reasoning,
        allow_help_seeking_language=allow_help_seeking_language,
        must_preserve_local_confusion=must_preserve_local_confusion,
        must_preserve_misconception_continuity=must_preserve_misconception_continuity,
        expected_error_presence=error_blueprint.error_presence,
        expected_newman_error_locus=error_blueprint.newman_error_locus,
        expected_radatz_error_mechanism=error_blueprint.radatz_error_mechanism,
        buggy_rule=error_blueprint.buggy_rule,
        wrong_claim_seed=error_blueprint.wrong_claim_seed,
        must_realize_specific_error=must_realize_specific_error,
        must_anchor_to_local_wrong_claim=must_anchor_to_local_wrong_claim,
        required_commitment_style=required_commitment_style,
        forbidden_patterns=forbidden_patterns,
        style_constraints=style_constraints,
    )


def constraint_bundle_to_dict(bundle: ConstraintBundle) -> dict[str, object]:
    return asdict(bundle)


def _commitment_style_instruction(commitment: str) -> str:
    if commitment == "avoidant":
        return (
            "The turn may stay minimal or avoid a substantive attempt; do not invent a settled mathematical claim."
        )
    if commitment == "tentative":
        return (
            "The turn may be partial, revising, or locally exploratory, but a concrete mathematical claim is still allowed when the student is attempting."
        )
    if commitment == "committed":
        return (
            "The turn may state a clear local claim directly, but still stay within the predicted maturity."
        )
    raise ValueError(f"unsupported commitment style: {commitment}")
