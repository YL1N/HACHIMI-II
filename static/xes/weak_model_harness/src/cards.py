from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudentState:
    student_id: str
    grade: str
    academic_level: str
    arithmetic_fluency: str
    word_problem_transfer: str
    multi_step_stability: str
    geometry_intuition: str
    pattern_rule_detection: str
    option_elimination: str
    fill_blank_precision: str
    hard_item_persistence: str
    guessing_tendency: str
    confidence_calibration: str
    format_discipline: str
    primary_error_family: str
    raw_summary: str
    attribute_mastery: dict[str, str]
    regulation_signals: dict[str, str]


@dataclass(frozen=True)
class TaskState:
    question_id: str
    question_type: str
    prerequisite_knowledge: list[str]
    operation_complexity: str
    abstraction_level: str
    knowledge_integration_demand: str
    representation_shift_required: str
    response_format_demand: str
    guessability: str
    perceived_difficulty: str | None
    difficulty_anchor_context: dict[str, object] | None
    notes: list[str]
    q_matrix_attributes: list[str]
    q_matrix_rationale: list[str]
    cognitive_operations: list[str]
    format_risk_points: list[str]


@dataclass(frozen=True)
class ScaffoldBudget:
    target_attributes: list[str]
    attribute_readiness: dict[str, str]
    demand_pressure: str
    max_support_level: str
    support_focus: list[str]
    allowed_scaffolds: list[str]
    forbidden_help: list[str]
    evidence_rationale: list[str]


@dataclass(frozen=True)
class PromptLadderCard:
    level0_instruction: str
    level1_hints: list[str]
    level2_hints: list[str]
    level3_hints: list[str]
    release_rule: str


@dataclass(frozen=True)
class RiskCard:
    likely_pitfalls: list[str]
    self_check_targets: list[str]
    guardrails: list[str]


@dataclass(frozen=True)
class ResponseProtocol:
    answer_mode: str
    max_tokens: int
    response_style: str
    max_support_level: str
    boundary_reminders: list[str]


@dataclass(frozen=True)
class ValidationReport:
    is_valid: bool
    issues: list[str]
