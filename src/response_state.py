from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .llm_client import OpenAICompatClient
from .problem_profile import ProblemRequirementProfile
from .prompts import ITEM_RESPONSE_STATE_PROMPT, VIOLATION_REVIEW_PROMPT
from .student_model import StudentInternalSignals, StudentModel

SENTENCE_SPLIT_RE = re.compile(r"[.!?\u3002\uff01\uff1f]+")
REASONING_CUES = ["because", "therefore", "first", "then", "so that", "\u56e0\u4e3a", "\u6240\u4ee5"]
HIGH_COMMITMENT_CUES = ["definitely", "certainly", "for sure", "obviously", "\u80af\u5b9a", "\u4e00\u5b9a"]


@dataclass(frozen=True)
class ItemResponseState:
    prerequisite_familiarity: str
    response_state: str
    reachable_level: str
    error_path: list[str]
    commitment_tendency: str
    explanation_depth_cap: str
    response_style_guidance: list[str]


@dataclass(frozen=True)
class ConstraintBundle:
    must_commit_answer: bool
    allow_complete_explanation: bool
    max_sentences: int
    max_thinking_steps: int
    forbid_full_mastery: bool
    preferred_error_path: list[str]
    style_constraints: list[str]
    allowed_commitment: str


@dataclass(frozen=True)
class ViolationReport:
    has_violation: bool
    reasons: list[str]
    severity: str


def _validate_enum(
    value: Any,
    allowed: set[str],
    field_name: str,
    alias_map: dict[str, str] | None = None,
) -> str:
    text = str(value).strip()
    if text in allowed:
        return text
    lower_to_allowed = {candidate.lower(): candidate for candidate in allowed}
    if text.lower() in lower_to_allowed:
        return lower_to_allowed[text.lower()]
    if alias_map is not None:
        mapped = alias_map.get(text.lower())
        if mapped in allowed:
            return mapped
    raise ValueError(f"invalid {field_name}: {text!r}, allowed={sorted(allowed)}")


def _validate_list(value: Any, field_name: str, allow_empty: bool = False) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list, got {type(value).__name__}")
    out = [str(item).strip() for item in value if str(item).strip()]
    if not out and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return out


def _validate_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    raise ValueError(f"invalid {field_name}: {value!r}, expected bool")


def _resolve_item_response_state_with_llm(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    profile: ProblemRequirementProfile,
    question_text: str,
    llm_client: OpenAICompatClient,
) -> ItemResponseState:
    user_payload = {
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
            "prerequisite_knowledge": profile.prerequisite_knowledge,
            "operation_complexity": profile.operation_complexity,
            "operation_complexity_justification": profile.operation_complexity_justification,
            "abstraction_level": profile.abstraction_level,
            "abstraction_level_justification": profile.abstraction_level_justification,
            "knowledge_integration_demand": profile.knowledge_integration_demand,
            "representation_shift_required": profile.representation_shift_required,
            "response_format_demand": profile.response_format_demand,
            "guessability": profile.guessability,
            "notes": profile.notes,
        },
        "question_text": question_text,
        "required_output_schema": {
            "prerequisite_familiarity": "familiar|partially_familiar|mostly_unfamiliar",
            "response_state": "mastered|partial|guessable|unreachable",
            "reachable_level": "short string",
            "error_path": "list[str]",
            "commitment_tendency": "low|medium|high",
            "explanation_depth_cap": "answer_only|short_reason|limited_reason|full_reason",
            "response_style_guidance": "list[str]",
        },
    }
    parsed = llm_client.chat_json(
        system_prompt=ITEM_RESPONSE_STATE_PROMPT,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
    )
    reachable_level = str(parsed.get("reachable_level", "")).strip()
    if not reachable_level:
        raise ValueError("reachable_level is empty in llm item response state output")
    return ItemResponseState(
        prerequisite_familiarity=_validate_enum(
            parsed.get("prerequisite_familiarity"),
            {"familiar", "partially_familiar", "mostly_unfamiliar"},
            "prerequisite_familiarity",
        ),
        response_state=_validate_enum(
            parsed.get("response_state"),
            {"mastered", "partial", "guessable", "unreachable"},
            "response_state",
        ),
        reachable_level=reachable_level,
        error_path=_validate_list(parsed.get("error_path"), "error_path", allow_empty=True),
        commitment_tendency=_validate_enum(
            parsed.get("commitment_tendency"),
            {"low", "medium", "high"},
            "commitment_tendency",
        ),
        explanation_depth_cap=_validate_enum(
            parsed.get("explanation_depth_cap"),
            {"answer_only", "short_reason", "limited_reason", "full_reason"},
            "explanation_depth_cap",
        ),
        response_style_guidance=_validate_list(
            parsed.get("response_style_guidance"), "response_style_guidance"
        ),
    )


def resolve_item_response_state(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    profile: ProblemRequirementProfile,
    question_text: str,
    llm_client: OpenAICompatClient | None = None,
) -> ItemResponseState:
    if llm_client is None:
        raise ValueError(
            "resolve_item_response_state requires llm_client; semantic inference cannot use heuristic fallback"
        )
    return _resolve_item_response_state_with_llm(
        student_model=student_model,
        internal_signals=internal_signals,
        profile=profile,
        question_text=question_text,
        llm_client=llm_client,
    )


def build_forced_item_response_state(response_state: str) -> ItemResponseState:
    if response_state == "mastered":
        return ItemResponseState(
            prerequisite_familiarity="familiar",
            response_state="mastered",
            reachable_level="The student can likely solve the item relatively stably.",
            error_path=[],
            commitment_tendency="high",
            explanation_depth_cap="full_reason",
            response_style_guidance=["stay concise", "answer directly"],
        )
    if response_state == "partial":
        return ItemResponseState(
            prerequisite_familiarity="partially_familiar",
            response_state="partial",
            reachable_level="The student can get part of the way but is not stable to the end.",
            error_path=["partial_procedure_breakdown", "incomplete_integration"],
            commitment_tendency="medium",
            explanation_depth_cap="limited_reason",
            response_style_guidance=["keep the explanation limited", "allow uncertainty"],
        )
    if response_state == "guessable":
        return ItemResponseState(
            prerequisite_familiarity="partially_familiar",
            response_state="guessable",
            reachable_level="The student may guess from surface cues but does not truly master the item.",
            error_path=["surface_cue_guess", "partial_elimination_without_stable_reasoning"],
            commitment_tendency="low",
            explanation_depth_cap="short_reason",
            response_style_guidance=["do not sound fully competent", "keep reasoning shallow"],
        )
    if response_state == "unreachable":
        return ItemResponseState(
            prerequisite_familiarity="mostly_unfamiliar",
            response_state="unreachable",
            reachable_level="The item is beyond the student's workable boundary, so only a forced guess is plausible.",
            error_path=["blind_guess", "off_target_attempt"],
            commitment_tendency="low",
            explanation_depth_cap="answer_only",
            response_style_guidance=["do not sound like full mastery", "keep to a bare answer"],
        )
    raise ValueError(
        "response_state must be one of mastered/partial/guessable/unreachable, "
        f"got {response_state!r}"
    )


def compile_constraints(item_state: ItemResponseState) -> ConstraintBundle:
    if item_state.response_state == "mastered":
        allow_complete_explanation = item_state.explanation_depth_cap == "full_reason"
        max_sentences = 3 if allow_complete_explanation else 2
        max_thinking_steps = 4 if allow_complete_explanation else 3
        forbid_full_mastery = False
    elif item_state.response_state == "partial":
        allow_complete_explanation = False
        max_sentences = 2
        max_thinking_steps = 2
        forbid_full_mastery = True
    else:
        allow_complete_explanation = False
        max_sentences = 1
        max_thinking_steps = 1
        forbid_full_mastery = True

    return ConstraintBundle(
        must_commit_answer=True,
        allow_complete_explanation=allow_complete_explanation,
        max_sentences=max_sentences,
        max_thinking_steps=max_thinking_steps,
        forbid_full_mastery=forbid_full_mastery,
        preferred_error_path=item_state.error_path,
        style_constraints=item_state.response_style_guidance,
        allowed_commitment=item_state.commitment_tendency,
    )


def _count_sentences(text: str) -> int:
    parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(text.strip()) if part.strip()]
    return len(parts)


def check_hard_violation_rules(
    predicted_answer: str,
    student_response: str,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
) -> ViolationReport:
    reasons: list[str] = []
    answer_text = (predicted_answer or "").strip()
    response_text = (student_response or "").strip()
    response_text_lower = response_text.lower()

    if constraints.must_commit_answer and not answer_text:
        reasons.append("missing_predicted_answer")

    sentence_count = _count_sentences(response_text) if response_text else 0
    if sentence_count > constraints.max_sentences:
        reasons.append(
            f"response_too_long(sentence_count={sentence_count}, allowed={constraints.max_sentences})"
        )

    reasoning_hits = sum(1 for cue in REASONING_CUES if cue in response_text_lower)
    if not constraints.allow_complete_explanation and reasoning_hits >= 2:
        reasons.append("explanation_depth_exceeds_cap")

    commitment_hits = sum(1 for cue in HIGH_COMMITMENT_CUES if cue in response_text_lower)
    if constraints.allowed_commitment == "low" and commitment_hits > 0:
        reasons.append("commitment_too_high_for_state")

    if item_state.response_state in {"guessable", "unreachable"} and reasoning_hits >= 2:
        reasons.append("mature_reasoning_in_low_reach_state")

    if item_state.explanation_depth_cap == "answer_only" and sentence_count > 1:
        reasons.append("answer_only_cap_violated")

    if not reasons:
        return ViolationReport(has_violation=False, reasons=[], severity="low")

    if "missing_predicted_answer" in reasons or "mature_reasoning_in_low_reach_state" in reasons:
        severity = "high"
    elif len(reasons) >= 2:
        severity = "medium"
    else:
        severity = "low"
    return ViolationReport(has_violation=True, reasons=reasons, severity=severity)


def _is_boundary_sample(item_state: ItemResponseState, hard_report: ViolationReport) -> bool:
    # LLM boundary review is only for ambiguous hard-rule violations.
    if not hard_report.has_violation:
        return False
    if hard_report.severity != "low":
        return False
    if item_state.response_state == "unreachable":
        return False
    return True


def review_violation_with_llm(
    predicted_answer: str,
    student_response: str,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    llm_client: OpenAICompatClient,
) -> ViolationReport:
    user_payload = {
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
            "max_thinking_steps": constraints.max_thinking_steps,
            "forbid_full_mastery": constraints.forbid_full_mastery,
            "preferred_error_path": constraints.preferred_error_path,
            "style_constraints": constraints.style_constraints,
            "allowed_commitment": constraints.allowed_commitment,
        },
        "model_output": {
            "predicted_answer": str(predicted_answer or ""),
            "student_response": str(student_response or ""),
        },
        "required_output_schema": {
            "has_violation": "true|false",
            "reasons": "list[str]",
            "severity": "low|medium|high",
        },
    }
    parsed = llm_client.chat_json(
        system_prompt=VIOLATION_REVIEW_PROMPT,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
    )
    has_violation = _validate_bool(parsed.get("has_violation"), "has_violation")
    reasons = _validate_list(parsed.get("reasons"), "reasons", allow_empty=True)
    if not has_violation and reasons:
        reasons = []
    severity = _validate_enum(
        parsed.get("severity"),
        {"low", "medium", "high"},
        "severity",
    )
    return ViolationReport(
        has_violation=has_violation,
        reasons=reasons,
        severity=severity,
    )


def _merge_violation_reports(
    hard_report: ViolationReport,
    llm_report: ViolationReport,
) -> ViolationReport:
    if not hard_report.has_violation and not llm_report.has_violation:
        return ViolationReport(has_violation=False, reasons=[], severity="low")

    merged_reasons: list[str] = []
    for reason in hard_report.reasons:
        if reason not in merged_reasons:
            merged_reasons.append(reason)
    for reason in llm_report.reasons:
        tagged = f"llm_review:{reason}"
        if tagged not in merged_reasons:
            merged_reasons.append(tagged)

    rank = {"low": 1, "medium": 2, "high": 3}
    severity = hard_report.severity
    if rank.get(llm_report.severity, 1) > rank.get(severity, 1):
        severity = llm_report.severity

    return ViolationReport(
        has_violation=True,
        reasons=merged_reasons,
        severity=severity,
    )


def check_violation(
    predicted_answer: str,
    student_response: str,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    llm_client: OpenAICompatClient | None = None,
    enable_llm_boundary_review: bool = True,
) -> ViolationReport:
    hard_report = check_hard_violation_rules(
        predicted_answer=predicted_answer,
        student_response=student_response,
        item_state=item_state,
        constraints=constraints,
    )
    if not enable_llm_boundary_review:
        return hard_report
    if llm_client is None:
        return hard_report
    if not _is_boundary_sample(item_state=item_state, hard_report=hard_report):
        return hard_report
    llm_report = review_violation_with_llm(
        predicted_answer=predicted_answer,
        student_response=student_response,
        item_state=item_state,
        constraints=constraints,
        llm_client=llm_client,
    )
    return _merge_violation_reports(hard_report=hard_report, llm_report=llm_report)


def tighten_constraints(item_state: ItemResponseState, constraints: ConstraintBundle) -> ConstraintBundle:
    style_constraints = list(constraints.style_constraints)
    if "strict_retry_mode" not in style_constraints:
        style_constraints.append("strict_retry_mode")

    if item_state.response_state == "mastered":
        # Do not over-tighten mastered states; only reduce over-assertive style.
        allowed_commitment = (
            "medium" if constraints.allowed_commitment == "high" else constraints.allowed_commitment
        )
        return ConstraintBundle(
            must_commit_answer=True,
            allow_complete_explanation=constraints.allow_complete_explanation,
            max_sentences=max(1, constraints.max_sentences),
            max_thinking_steps=max(1, constraints.max_thinking_steps - 1),
            forbid_full_mastery=False,
            preferred_error_path=constraints.preferred_error_path,
            style_constraints=style_constraints,
            allowed_commitment=allowed_commitment,
        )

    if item_state.response_state == "partial":
        allowed_commitment = (
            "low" if constraints.allowed_commitment == "high" else constraints.allowed_commitment
        )
        return ConstraintBundle(
            must_commit_answer=True,
            allow_complete_explanation=False,
            max_sentences=max(1, constraints.max_sentences - 1),
            max_thinking_steps=max(1, constraints.max_thinking_steps - 1),
            forbid_full_mastery=True,
            preferred_error_path=constraints.preferred_error_path,
            style_constraints=style_constraints,
            allowed_commitment=allowed_commitment,
        )

    # guessable / unreachable remain strict.
    return ConstraintBundle(
        must_commit_answer=True,
        allow_complete_explanation=False,
        max_sentences=1,
        max_thinking_steps=1,
        forbid_full_mastery=True,
        preferred_error_path=constraints.preferred_error_path,
        style_constraints=style_constraints,
        allowed_commitment="low",
    )
