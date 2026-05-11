from __future__ import annotations

from dataclasses import dataclass

from .problem_profile import ProblemRequirementProfile
from .student_model import StudentModel


_LEVEL_TO_SCORE = {"low": 0, "medium": 1, "high": 2}
_DEMAND_TO_SCORE = {"none": 0, "low": 0, "medium": 1, "high": 2}
_DIFFICULTY_TO_SCORE = {"easy": 0, "medium": 1, "hard": 2}


@dataclass(frozen=True)
class StudentItemInteractionDecision:
    predicted_reachability: str
    predicted_correctness_band: str
    likely_outcome: str
    likely_error_family: str
    confidence_cap: str
    explanation_cap: str
    decision_rationale: list[str]


def _capability_score(value: str) -> int:
    text = str(value).strip().lower()
    if text not in _LEVEL_TO_SCORE:
        raise ValueError(f"unsupported capability level: {value!r}")
    return _LEVEL_TO_SCORE[text]


def _difficulty_score(profile: ProblemRequirementProfile) -> int:
    difficulty = profile.real_difficulty_band or profile.perceived_difficulty_for_target_grade
    if difficulty is None:
        return 1
    text = str(difficulty).strip().lower()
    if text not in _DIFFICULTY_TO_SCORE:
        return 1
    return _DIFFICULTY_TO_SCORE[text]


def _operation_load(profile: ProblemRequirementProfile) -> int:
    mapping = {
        "Level 1 Recall and Reproduction": 0,
        "Level 2 Skills and Concepts": 1,
        "Level 3 Strategic Thinking": 2,
        "Level 4 Extended Thinking": 3,
    }
    return mapping.get(profile.operation_complexity, 1)


def _abstraction_load(profile: ProblemRequirementProfile) -> int:
    mapping = {
        "Memorization": 0,
        "Procedures Without Connections": 1,
        "Procedures With Connections": 2,
        "Doing Mathematics": 3,
    }
    return mapping.get(profile.abstraction_level, 1)


def _format_load(profile: ProblemRequirementProfile) -> int:
    mapping = {
        "selection_only": 0,
        "short_fill": 1,
        "constructed_numeric": 2,
        "constructed_explanation": 3,
    }
    return mapping.get(profile.response_format_demand, 1)


def _guessability_load(profile: ProblemRequirementProfile) -> int:
    return _DEMAND_TO_SCORE.get(str(profile.guessability).strip().lower(), 1)


def build_student_item_interaction_decision(
    student_model: StudentModel,
    profile: ProblemRequirementProfile,
) -> StudentItemInteractionDecision:
    capability = student_model.math_task_capability_profile
    if capability is None:
        raise ValueError(
            "student_model.math_task_capability_profile is required for interaction decision"
        )

    arithmetic = _capability_score(capability.arithmetic_fluency)
    transfer = _capability_score(capability.word_problem_transfer)
    multi_step = _capability_score(capability.multi_step_stability)
    pattern = _capability_score(capability.pattern_rule_detection)
    geometry = _capability_score(capability.geometry_intuition)
    option_elimination = _capability_score(capability.option_elimination)
    fill_blank = _capability_score(capability.fill_blank_precision)
    persistence = _capability_score(capability.hard_item_persistence)

    operation_load = _operation_load(profile)
    abstraction_load = _abstraction_load(profile)
    format_load = _format_load(profile)
    difficulty_load = _difficulty_score(profile)
    guessability_load = _guessability_load(profile)

    if profile.response_format_demand == "selection_only":
        format_capability = option_elimination
    else:
        format_capability = fill_blank

    integration_load = 1 if profile.knowledge_integration_demand == "multiple_knowledge_combination" else 0
    representation_load = _DEMAND_TO_SCORE.get(
        str(profile.representation_shift_required).strip().lower(),
        1,
    )
    prerequisite_load = min(2, max(0, len(profile.prerequisite_knowledge) - 1))

    average_capability = (
        arithmetic
        + transfer
        + multi_step
        + pattern
        + geometry
        + format_capability
        + persistence
    ) / 7.0
    total_load = (
        operation_load
        + abstraction_load
        + format_load
        + difficulty_load
        + integration_load
        + representation_load
        + prerequisite_load
    ) / 7.0
    margin = average_capability - total_load

    if margin >= 0.8:
        predicted_reachability = "mastered"
        predicted_correctness_band = "0.8-1.0"
        likely_outcome = "correct"
        confidence_cap = "high"
        explanation_cap = "full_reason"
        likely_error_family = "none"
    elif margin >= 0.2:
        predicted_reachability = "partial"
        predicted_correctness_band = "0.6-0.8"
        likely_outcome = "correct"
        confidence_cap = "medium"
        explanation_cap = "limited_reason"
        likely_error_family = capability.common_error_families[0]
    elif margin >= -0.4:
        predicted_reachability = "guessable"
        predicted_correctness_band = "0.4-0.6"
        likely_outcome = "near_miss"
        confidence_cap = "low"
        explanation_cap = "short_reason"
        likely_error_family = capability.common_error_families[0]
    else:
        predicted_reachability = "unreachable"
        predicted_correctness_band = "0.0-0.4"
        likely_outcome = "wrong"
        confidence_cap = "low"
        explanation_cap = "answer_only"
        if guessability_load >= 1 and _capability_score(capability.guessing_tendency) >= 1:
            likely_error_family = "blind_guess"
        else:
            likely_error_family = capability.common_error_families[0]

    rationale = [
        f"average_capability={average_capability:.2f}",
        f"total_load={total_load:.2f}",
        f"margin={margin:.2f}",
        f"format_capability={'option_elimination' if profile.response_format_demand == 'selection_only' else 'fill_blank_precision'}={format_capability}",
        f"operation_load={operation_load}",
        f"difficulty_load={difficulty_load}",
        f"likely_error_family={likely_error_family}",
    ]

    return StudentItemInteractionDecision(
        predicted_reachability=predicted_reachability,
        predicted_correctness_band=predicted_correctness_band,
        likely_outcome=likely_outcome,
        likely_error_family=likely_error_family,
        confidence_cap=confidence_cap,
        explanation_cap=explanation_cap,
        decision_rationale=rationale,
    )
