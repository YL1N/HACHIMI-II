from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .difficulty_anchor_bank import DifficultyAnchorContext
from .llm_client import OpenAICompatClient
from .prompts import PROBLEM_PROFILE_PROMPT, PROBLEM_PROFILE_WITH_DIFFICULTY_ANALYSIS_PROMPT


@dataclass(frozen=True)
class ProblemRequirementProfile:
    prerequisite_knowledge: list[str]
    operation_complexity: str
    operation_complexity_justification: str
    abstraction_level: str
    abstraction_level_justification: str
    knowledge_integration_demand: str
    representation_shift_required: str
    response_format_demand: str
    guessability: str
    notes: list[str]
    perceived_difficulty_for_target_grade: str | None = None
    perceived_difficulty_justification: str | None = None
    real_difficulty_band: str | None = None  # For H2 experiment: directly pass real difficulty
    difficulty_anchor_context: dict[str, Any] | None = None


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
    canonical = _canonicalize_enum_token(text)
    canonical_to_allowed = {
        _canonicalize_enum_token(candidate): candidate for candidate in allowed
    }
    if canonical in canonical_to_allowed:
        return canonical_to_allowed[canonical]
    if alias_map is not None:
        mapped = alias_map.get(canonical) or alias_map.get(text.lower())
        if mapped in allowed:
            return mapped
    raise ValueError(f"invalid {field_name}: {text!r}, allowed={sorted(allowed)}")


def _canonicalize_enum_token(value: Any) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _validate_str_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list, got {type(value).__name__}")
    out = [str(item).strip() for item in value if str(item).strip()]
    if not out:
        raise ValueError(f"{field_name} cannot be empty")
    return out


def _validate_str(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _build_problem_requirement_profile_with_llm(
    question_text: str,
    options: dict[str, str],
    question_type: str,
    llm_client: OpenAICompatClient,
    target_grade: str | None = None,
    enable_difficulty_analysis: bool = False,
    difficulty_anchor_context: DifficultyAnchorContext | None = None,
) -> ProblemRequirementProfile:
    knowledge_integration_aliases = {
        "single_knowledge_combination": "single_knowledge",
    }

    # Choose prompt based on whether difficulty analysis is enabled
    system_prompt = (
        PROBLEM_PROFILE_WITH_DIFFICULTY_ANALYSIS_PROMPT
        if enable_difficulty_analysis
        else PROBLEM_PROFILE_PROMPT
    )

    user_payload = {
        "question_text": question_text,
        "options": options,
        "question_type": question_type,
        "required_output_schema": {
            "prerequisite_knowledge": "list[str]",
            "operation_complexity": (
                "Level 1 Recall and Reproduction|Level 2 Skills and Concepts|"
                "Level 3 Strategic Thinking|Level 4 Extended Thinking"
            ),
            "operation_complexity_justification": "string",
            "abstraction_level": (
                "Memorization|Procedures Without Connections|"
                "Procedures With Connections|Doing Mathematics"
            ),
            "abstraction_level_justification": "string",
            "knowledge_integration_demand": "single_knowledge|multiple_knowledge_combination",
            "representation_shift_required": "none|low|high",
            "response_format_demand": (
                "selection_only|short_fill|constructed_numeric|constructed_explanation"
            ),
            "guessability": "unknown|low|medium",
            "notes": "list[str]",
        },
    }
    anchor_context_payload = (
        asdict(difficulty_anchor_context)
        if difficulty_anchor_context is not None
        else None
    )
    if anchor_context_payload is not None:
        user_payload["difficulty_anchor_context"] = anchor_context_payload

    # Add target_grade and difficulty fields if enabled
    if enable_difficulty_analysis and target_grade:
        user_payload["target_grade"] = target_grade
        user_payload["required_output_schema"]["perceived_difficulty_for_target_grade"] = "easy|medium|hard"
        user_payload["required_output_schema"]["perceived_difficulty_justification"] = "string"

    parsed = llm_client.chat_json(
        system_prompt=system_prompt,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
    )
    # notes is optional, allow empty list
    notes_raw = parsed.get("notes")
    if notes_raw is None or notes_raw == []:
        notes = []
    else:
        notes = _validate_str_list(notes_raw, "notes")

    # Extract difficulty fields if present
    perceived_difficulty = None
    perceived_difficulty_justification = None
    if enable_difficulty_analysis:
        if "perceived_difficulty_for_target_grade" in parsed:
            perceived_difficulty = _validate_enum(
                parsed.get("perceived_difficulty_for_target_grade"),
                {"easy", "medium", "hard"},
                "perceived_difficulty_for_target_grade",
            )
        if "perceived_difficulty_justification" in parsed:
            perceived_difficulty_justification = _validate_str(
                parsed.get("perceived_difficulty_justification"),
                "perceived_difficulty_justification",
            )

    return ProblemRequirementProfile(
        prerequisite_knowledge=_validate_str_list(
            parsed.get("prerequisite_knowledge"), "prerequisite_knowledge"
        ),
        operation_complexity=_validate_enum(
            parsed.get("operation_complexity"),
            {
                "Level 1 Recall and Reproduction",
                "Level 2 Skills and Concepts",
                "Level 3 Strategic Thinking",
                "Level 4 Extended Thinking",
            },
            "operation_complexity",
        ),
        operation_complexity_justification=_validate_str(
            parsed.get("operation_complexity_justification"),
            "operation_complexity_justification",
        ),
        abstraction_level=_validate_enum(
            parsed.get("abstraction_level"),
            {
                "Memorization",
                "Procedures Without Connections",
                "Procedures With Connections",
                "Doing Mathematics",
            },
            "abstraction_level",
        ),
        abstraction_level_justification=_validate_str(
            parsed.get("abstraction_level_justification"),
            "abstraction_level_justification",
        ),
        knowledge_integration_demand=_validate_enum(
            parsed.get("knowledge_integration_demand"),
            {"single_knowledge", "multiple_knowledge_combination"},
            "knowledge_integration_demand",
            alias_map=knowledge_integration_aliases,
        ),
        representation_shift_required=_validate_enum(
            parsed.get("representation_shift_required"),
            {"none", "low", "high"},
            "representation_shift_required",
        ),
        response_format_demand=_validate_enum(
            parsed.get("response_format_demand"),
            {"selection_only", "short_fill", "constructed_numeric", "constructed_explanation"},
            "response_format_demand",
        ),
        guessability=_validate_enum(
            parsed.get("guessability"),
            {"unknown", "low", "medium"},
            "guessability",
        ),
        notes=notes,
        perceived_difficulty_for_target_grade=perceived_difficulty,
        perceived_difficulty_justification=perceived_difficulty_justification,
        real_difficulty_band=None,
        difficulty_anchor_context=anchor_context_payload,
    )


def build_problem_requirement_profile(
    question_text: str,
    options: dict[str, str],
    question_type: str,
    llm_client: OpenAICompatClient | None = None,
    target_grade: str | None = None,
    enable_difficulty_analysis: bool = False,
    real_difficulty_band: str | None = None,
    difficulty_anchor_context: DifficultyAnchorContext | None = None,
) -> ProblemRequirementProfile:
    if llm_client is None:
        raise ValueError(
            "build_problem_requirement_profile requires llm_client; semantic analysis cannot use heuristic fallback"
        )

    profile = _build_problem_requirement_profile_with_llm(
        question_text=question_text,
        options=options,
        question_type=question_type,
        llm_client=llm_client,
        target_grade=target_grade,
        enable_difficulty_analysis=enable_difficulty_analysis,
        difficulty_anchor_context=difficulty_anchor_context,
    )

    # For H2 experiment: directly inject real difficulty band
    if real_difficulty_band is not None:
        profile = ProblemRequirementProfile(
            prerequisite_knowledge=profile.prerequisite_knowledge,
            operation_complexity=profile.operation_complexity,
            operation_complexity_justification=profile.operation_complexity_justification,
            abstraction_level=profile.abstraction_level,
            abstraction_level_justification=profile.abstraction_level_justification,
            knowledge_integration_demand=profile.knowledge_integration_demand,
            representation_shift_required=profile.representation_shift_required,
            response_format_demand=profile.response_format_demand,
            guessability=profile.guessability,
            notes=profile.notes,
            perceived_difficulty_for_target_grade=profile.perceived_difficulty_for_target_grade,
            perceived_difficulty_justification=profile.perceived_difficulty_justification,
            real_difficulty_band=real_difficulty_band,
            difficulty_anchor_context=profile.difficulty_anchor_context,
        )

    return profile
