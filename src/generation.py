from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .llm_client import OpenAICompatClient
from .problem_profile import ProblemRequirementProfile
from .prompts import get_answer_generator_prompt, get_direct_answer_prompt
from .response_state import (
    ConstraintBundle,
    ItemResponseState,
    ViolationReport,
    check_violation as check_violation_rules,
    tighten_constraints,
)
from .student_model import StudentInternalSignals, StudentModel

TERMINAL_STEP_PROTOCOL_SUFFIX = """

Terminal-step protocol:
- must_finish_now = true
- remaining_step_budget = 1
- This is the last allowed step.
- next_action MUST be "final_answer".
- predicted_answer MUST be non-empty.
- student_response MUST be non-empty.
- Do not output "continue".
"""

TERMINAL_STEP_PROTOCOL_RETRY_SUFFIX = """

Protocol correction:
- Your previous reply violated the last-step protocol.
- Regenerate from scratch.
- This final step must end with next_action = "final_answer".
- predicted_answer and student_response must both be non-empty.
"""


@dataclass(frozen=True)
class ThinkingStep:
    step_index: int
    internal_thought: str
    next_action: str
    decision_reason: str
    predicted_answer: str
    student_response: str


@dataclass(frozen=True)
class AnswerOutput:
    predicted_answer: str
    student_response: str
    thinking_trace: list[ThinkingStep]


def _validate_enum(value: Any, allowed: set[str], field_name: str) -> str:
    text = str(value).strip()
    if text not in allowed:
        raise ValueError(f"invalid {field_name}: {text!r}, allowed={sorted(allowed)}")
    return text


def _validate_non_empty_string(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _parse_thinking_step(
    parsed: dict[str, Any],
    step_index: int,
    require_final_answer: bool = False,
) -> ThinkingStep:
    next_action = _validate_enum(
        parsed.get("next_action"),
        {"continue", "final_answer"},
        "next_action",
    )
    if require_final_answer and next_action != "final_answer":
        raise ValueError("last allowed step must be final_answer")
    internal_thought = _validate_non_empty_string(
        parsed.get("internal_thought"),
        "internal_thought",
    )
    decision_reason = _validate_non_empty_string(
        parsed.get("decision_reason"),
        "decision_reason",
    )
    predicted_answer = str(parsed.get("predicted_answer", "")).strip()
    student_response = str(parsed.get("student_response", "")).strip()
    if next_action == "continue":
        if predicted_answer or student_response:
            raise ValueError(
                "continue step must keep predicted_answer and student_response empty"
            )
    else:
        if not predicted_answer:
            raise ValueError("final_answer step must provide predicted_answer")
        if not student_response:
            raise ValueError("final_answer step must provide student_response")
    return ThinkingStep(
        step_index=step_index,
        internal_thought=internal_thought,
        next_action=next_action,
        decision_reason=decision_reason,
        predicted_answer=predicted_answer,
        student_response=student_response,
    )


def _build_thinking_payload(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    question_id: str,
    question_text: str,
    options: dict[str, str],
    thinking_trace: list[ThinkingStep],
    step_index: int,
    remaining_step_budget: int,
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "question_text": question_text,
        "options": options,
        "student_model": {
            "student_id": student_model.student_id,
            "grade": student_model.grade,
            "academic_level": student_model.academic_level,
            "weak_subjects": student_model.weak_subjects,
            "strong_subjects": student_model.strong_subjects,
            "self_efficacy_analysis": asdict(student_model.self_efficacy_analysis),
            "srl_analysis": asdict(student_model.srl_analysis),
            "control_value_analysis": asdict(student_model.control_value_analysis),
            "engagement_level_tendency": student_model.engagement_level_tendency,
            "engagement_evidence": student_model.engagement_evidence,
            "response_directness_description": student_model.response_directness_description,
            "response_directness_evidence": student_model.response_directness_evidence,
            "raw_summary": student_model.raw_summary,
        },
        "implementation_derived_signals": asdict(internal_signals),
        "problem_requirement_profile": {
            "prerequisite_knowledge": problem_profile.prerequisite_knowledge,
            "operation_complexity": problem_profile.operation_complexity,
            "operation_complexity_justification": problem_profile.operation_complexity_justification,
            "abstraction_level": problem_profile.abstraction_level,
            "abstraction_level_justification": problem_profile.abstraction_level_justification,
            "knowledge_integration_demand": problem_profile.knowledge_integration_demand,
            "representation_shift_required": problem_profile.representation_shift_required,
            "response_format_demand": problem_profile.response_format_demand,
            "guessability": problem_profile.guessability,
        },
        "item_response_state": {
            "prerequisite_familiarity": item_state.prerequisite_familiarity,
            "response_state": item_state.response_state,
            "reachable_level": item_state.reachable_level,
            "error_path": item_state.error_path,
            "commitment_tendency": item_state.commitment_tendency,
            "explanation_depth_cap": item_state.explanation_depth_cap,
            "response_style_guidance": item_state.response_style_guidance,
        },
        "constraint_bundle": {
            "must_commit_answer": constraints.must_commit_answer,
            "allow_complete_explanation": constraints.allow_complete_explanation,
            "max_sentences": constraints.max_sentences,
            "forbid_full_mastery": constraints.forbid_full_mastery,
            "preferred_error_path": constraints.preferred_error_path,
            "style_constraints": constraints.style_constraints,
            "allowed_commitment": constraints.allowed_commitment,
        },
        "thinking_history": [asdict(step) for step in thinking_trace],
        "current_step_index": step_index,
        "remaining_step_budget": remaining_step_budget,
        "must_finish_now": remaining_step_budget == 1,
        "required_output_schema": {
            "internal_thought": "string",
            "next_action": "continue|final_answer",
            "decision_reason": "string",
            "predicted_answer": "string",
            "student_response": "string",
        },
    }


def _request_thinking_step(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    question_id: str,
    question_text: str,
    options: dict[str, str],
    thinking_trace: list[ThinkingStep],
    step_index: int,
    remaining_step_budget: int,
    response_persona: str,
    llm_client: OpenAICompatClient,
) -> ThinkingStep:
    user_payload = _build_thinking_payload(
        student_model=student_model,
        internal_signals=internal_signals,
        problem_profile=problem_profile,
        item_state=item_state,
        constraints=constraints,
        question_id=question_id,
        question_text=question_text,
        options=options,
        thinking_trace=thinking_trace,
        step_index=step_index,
        remaining_step_budget=remaining_step_budget,
    )
    require_final_answer = remaining_step_budget == 1
    system_prompt = get_answer_generator_prompt(response_persona)
    if require_final_answer:
        system_prompt += TERMINAL_STEP_PROTOCOL_SUFFIX
    partial_keys = [
        "internal_thought",
        "next_action",
        "decision_reason",
        "predicted_answer",
        "student_response",
    ]
    parsed = llm_client.chat_json(
        system_prompt=system_prompt,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
        partial_string_keys=partial_keys,
    )
    try:
        return _parse_thinking_step(
            parsed,
            step_index=step_index,
            require_final_answer=require_final_answer,
        )
    except ValueError:
        if not require_final_answer:
            raise
    retry_parsed = llm_client.chat_json(
        system_prompt=system_prompt + TERMINAL_STEP_PROTOCOL_RETRY_SUFFIX,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
        partial_string_keys=partial_keys,
    )
    return _parse_thinking_step(
        retry_parsed,
        step_index=step_index,
        require_final_answer=True,
    )


def _build_direct_answer_payload(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    question_id: str,
    question_text: str,
    options: dict[str, str],
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "question_text": question_text,
        "options": options,
        "student_model": {
            "student_id": student_model.student_id,
            "grade": student_model.grade,
            "academic_level": student_model.academic_level,
            "weak_subjects": student_model.weak_subjects,
            "strong_subjects": student_model.strong_subjects,
            "self_efficacy_analysis": asdict(student_model.self_efficacy_analysis),
            "srl_analysis": asdict(student_model.srl_analysis),
            "control_value_analysis": asdict(student_model.control_value_analysis),
            "engagement_level_tendency": student_model.engagement_level_tendency,
            "engagement_evidence": student_model.engagement_evidence,
            "response_directness_description": student_model.response_directness_description,
            "response_directness_evidence": student_model.response_directness_evidence,
            "raw_summary": student_model.raw_summary,
        },
        "implementation_derived_signals": asdict(internal_signals),
        "problem_requirement_profile": {
            "prerequisite_knowledge": problem_profile.prerequisite_knowledge,
            "operation_complexity": problem_profile.operation_complexity,
            "operation_complexity_justification": problem_profile.operation_complexity_justification,
            "abstraction_level": problem_profile.abstraction_level,
            "abstraction_level_justification": problem_profile.abstraction_level_justification,
            "knowledge_integration_demand": problem_profile.knowledge_integration_demand,
            "representation_shift_required": problem_profile.representation_shift_required,
            "response_format_demand": problem_profile.response_format_demand,
            "guessability": problem_profile.guessability,
            "notes": problem_profile.notes,
        },
        "required_output_schema": {
            "predicted_answer": "string",
            "student_response": "string",
        },
    }


def generate_student_answer_direct(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    question_id: str,
    question_text: str,
    options: dict[str, str],
    response_persona: str = "first",
    llm_client: OpenAICompatClient | None = None,
) -> AnswerOutput:
    if llm_client is None:
        raise ValueError(
            "generate_student_answer_direct requires llm_client; answer generation cannot use heuristic fallback"
        )
    if response_persona not in {"first", "third"}:
        raise ValueError(
            f"invalid response_persona: {response_persona!r}, expected 'first' or 'third'"
        )

    user_payload = _build_direct_answer_payload(
        student_model=student_model,
        internal_signals=internal_signals,
        problem_profile=problem_profile,
        question_id=question_id,
        question_text=question_text,
        options=options,
    )
    parsed = llm_client.chat_json(
        system_prompt=get_direct_answer_prompt(response_persona),
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
        partial_string_keys=["predicted_answer", "student_response"],
    )
    predicted_answer = _validate_non_empty_string(
        parsed.get("predicted_answer"),
        "predicted_answer",
    )
    student_response = _validate_non_empty_string(
        parsed.get("student_response"),
        "student_response",
    )
    return AnswerOutput(
        predicted_answer=predicted_answer,
        student_response=student_response,
        thinking_trace=[],
    )


def generate_student_answer(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    question_id: str,
    question_text: str,
    options: dict[str, str],
    response_persona: str = "first",
    max_thinking_steps: int = 12,
    llm_client: OpenAICompatClient | None = None,
) -> AnswerOutput:
    if llm_client is None:
        raise ValueError(
            "generate_student_answer requires llm_client; answer generation cannot use heuristic fallback"
        )
    if response_persona not in {"first", "third"}:
        raise ValueError(
            f"invalid response_persona: {response_persona!r}, expected 'first' or 'third'"
        )
    if max_thinking_steps <= 0:
        raise ValueError("max_thinking_steps must be positive")
    if constraints.max_thinking_steps <= 0:
        raise ValueError("constraints.max_thinking_steps must be positive")

    effective_max_thinking_steps = min(max_thinking_steps, constraints.max_thinking_steps)

    thinking_trace: list[ThinkingStep] = []
    for step_index in range(1, effective_max_thinking_steps + 1):
        remaining_step_budget = effective_max_thinking_steps - step_index + 1
        step = _request_thinking_step(
            student_model=student_model,
            internal_signals=internal_signals,
            problem_profile=problem_profile,
            item_state=item_state,
            constraints=constraints,
            question_id=question_id,
            question_text=question_text,
            options=options,
            thinking_trace=thinking_trace,
            step_index=step_index,
            remaining_step_budget=remaining_step_budget,
            response_persona=response_persona,
            llm_client=llm_client,
        )
        thinking_trace.append(step)
        if step.next_action == "final_answer":
            return AnswerOutput(
                predicted_answer=step.predicted_answer,
                student_response=step.student_response,
                thinking_trace=thinking_trace,
            )

    raise RuntimeError(
        "model did not terminate within effective_max_thinking_steps="
        f"{effective_max_thinking_steps}; no fallback is allowed"
    )


def check_violation(
    answer_output: AnswerOutput,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    llm_client: OpenAICompatClient | None = None,
    enable_llm_boundary_review: bool = True,
) -> ViolationReport:
    return check_violation_rules(
        predicted_answer=answer_output.predicted_answer,
        student_response=answer_output.student_response,
        item_state=item_state,
        constraints=constraints,
        llm_client=llm_client,
        enable_llm_boundary_review=enable_llm_boundary_review,
    )


def should_retry_once(item_state: ItemResponseState, violation: ViolationReport) -> bool:
    if not violation.has_violation:
        return False
    # Unreachable states and high-severity cases are unlikely to benefit from one more try.
    if item_state.response_state == "unreachable":
        return False
    if violation.severity == "high":
        return False
    return True


def retry_with_tighter_constraints(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    question_id: str,
    question_text: str,
    options: dict[str, str],
    response_persona: str = "first",
    max_thinking_steps: int = 12,
    llm_client: OpenAICompatClient | None = None,
) -> tuple[AnswerOutput, ConstraintBundle]:
    tightened = tighten_constraints(item_state=item_state, constraints=constraints)
    retried_output = generate_student_answer(
        student_model=student_model,
        internal_signals=internal_signals,
        problem_profile=problem_profile,
        item_state=item_state,
        constraints=tightened,
        question_id=question_id,
        question_text=question_text,
        options=options,
        response_persona=response_persona,
        max_thinking_steps=max_thinking_steps,
        llm_client=llm_client,
    )
    return retried_output, tightened
