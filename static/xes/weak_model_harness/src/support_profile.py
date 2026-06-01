from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from src.llm_client import OpenAICompatClient

Q_MATRIX_ATTRIBUTE_VOCAB = {
    "fact_retrieval",
    "arithmetic_computation",
    "compare_quantities",
    "place_value_structure",
    "fraction_ratio_reasoning",
    "measurement_unit_reasoning",
    "geometry_visualization",
    "pattern_rule_reasoning",
    "data_table_interpretation",
    "word_problem_schema_mapping",
    "multi_step_planning",
    "equation_relation_tracking",
    "option_discrimination",
    "precision_formatting",
}

Q_MATRIX_ATTRIBUTE_ALIAS_MAP = {
    "retrieve_fact": "fact_retrieval",
    "execute_procedure": "arithmetic_computation",
    "compare_quantities": "compare_quantities",
    "plan_multi_step": "multi_step_planning",
    "integrate_conditions": "equation_relation_tracking",
    "transform_representation": "data_table_interpretation",
    "select_option": "option_discrimination",
    "construct_numeric_answer": "precision_formatting",
    "check_boundary_condition": "measurement_unit_reasoning",
}

COGNITIVE_OPERATION_VOCAB = {
    "retrieve_fact",
    "execute_procedure",
    "compare_quantities",
    "integrate_conditions",
    "transform_representation",
    "plan_multi_step",
    "check_boundary_condition",
    "select_option",
    "construct_numeric_answer",
}

COGNITIVE_OPERATION_ALIAS_MAP = {
    "identify_knowns_and_unknowns": "integrate_conditions",
    "keep_one_relation_at_a_time": "integrate_conditions",
    "convert_to_same_representation": "transform_representation",
    "verify_last_step_before_answer": "check_boundary_condition",
    "eliminate_obvious_options": "select_option",
    "focus_on_final_numeric_answer": "construct_numeric_answer",
    "check_unit_or_interval": "check_boundary_condition",
}

SCAFFOLD_VOCAB = {
    "identify_knowns_and_unknowns",
    "keep_one_relation_at_a_time",
    "convert_to_same_representation",
    "check_unit_or_interval",
    "verify_last_step_before_answer",
    "eliminate_obvious_options",
    "focus_on_final_numeric_answer",
}

SCAFFOLD_ALIAS_MAP = {
    "identify_given_and_unknown": "identify_knowns_and_unknowns",
    "one_relation_at_a_time": "keep_one_relation_at_a_time",
    "same_representation_conversion": "convert_to_same_representation",
    "check_units_or_intervals": "check_unit_or_interval",
    "final_numeric_only": "focus_on_final_numeric_answer",
    "integrate_conditions": "keep_one_relation_at_a_time",
    "transform_representation": "convert_to_same_representation",
    "check_boundary_condition": "verify_last_step_before_answer",
    "select_option": "eliminate_obvious_options",
    "construct_numeric_answer": "focus_on_final_numeric_answer",
}

SCHEMA_RETRY_SUFFIX = """

Schema correction:
- Regenerate from scratch.
- Use only values from the allowed vocabularies.
- Do not solve the item.
- Return exactly one JSON object.
"""

SCHEMA_REPAIR_SUFFIX = """

Schema repair:
- You are given a previous JSON object that failed schema validation.
- Repair that JSON instead of solving the item.
- Keep the meaning as close as possible.
- If an enum value is invalid, replace it with the nearest allowed vocabulary item.
- Return exactly one repaired JSON object.
"""


TASK_SUPPORT_PROFILE_PROMPT = f"""
Build a formal TaskSupportProfile for a weak-model math student harness.
Do NOT solve the item.
Do NOT output the answer.
Output JSON only.

Theory grounding:
- Use Q-matrix style thinking: identify only the skill attributes that are actually required.
- Use cognitive load / scaffolding logic: provide support actions that reduce irrelevant burden
  without giving away the solution.
- Use misconception analysis: describe likely error paths, not the correct answer.

Allowed q_matrix_attributes:
{sorted(Q_MATRIX_ATTRIBUTE_VOCAB)}

Allowed cognitive_operations:
{sorted(COGNITIVE_OPERATION_VOCAB)}

Allowed scaffolds:
{sorted(SCAFFOLD_VOCAB)}

Return exactly:
{{
  "q_matrix_attributes": ["..."],
  "q_matrix_rationale": ["short string"],
  "cognitive_operations": ["..."],
  "coaching_focus": ["short string"],
  "allowed_scaffolds": ["..."],
  "common_misconceptions": ["short string"],
  "format_risk_points": ["short string"]
}}
"""


@dataclass(frozen=True)
class TaskSupportProfile:
    q_matrix_attributes: list[str]
    q_matrix_rationale: list[str]
    cognitive_operations: list[str]
    coaching_focus: list[str]
    allowed_scaffolds: list[str]
    common_misconceptions: list[str]
    format_risk_points: list[str]


def _validate_enum_list(
    value: Any,
    allowed: set[str],
    field_name: str,
    alias_map: dict[str, str] | None = None,
) -> list[str]:
    normalized_allowed = {_normalize_enum_token(item) for item in allowed}
    normalized_alias_map = {
        _normalize_enum_token(key): _normalize_enum_token(mapped)
        for key, mapped in (alias_map or {}).items()
    }
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list, got {type(value).__name__}")
    out = []
    for item in value:
        text = _normalize_enum_token(str(item))
        if not text:
            continue
        if text in normalized_alias_map:
            text = normalized_alias_map[text]
        if text not in normalized_allowed:
            raise ValueError(f"invalid {field_name} value: {text!r}")
        out.append(text)
    if not out:
        raise ValueError(f"{field_name} cannot be empty")
    return out


def _normalize_enum_token(text: str) -> str:
    normalized = text.strip().lower()
    normalized = normalized.replace("-", "_").replace("/", "_")
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _validate_str_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list, got {type(value).__name__}")
    out = [str(item).strip() for item in value if str(item).strip()]
    if not out:
        raise ValueError(f"{field_name} cannot be empty")
    return out


def task_support_profile_from_dict(payload: dict[str, Any]) -> TaskSupportProfile:
    return TaskSupportProfile(
        q_matrix_attributes=_validate_enum_list(
            payload.get("q_matrix_attributes"),
            Q_MATRIX_ATTRIBUTE_VOCAB,
            "q_matrix_attributes",
            alias_map=Q_MATRIX_ATTRIBUTE_ALIAS_MAP,
        ),
        q_matrix_rationale=_validate_str_list(
            payload.get("q_matrix_rationale"),
            "q_matrix_rationale",
        ),
        cognitive_operations=_validate_enum_list(
            payload.get("cognitive_operations"),
            COGNITIVE_OPERATION_VOCAB,
            "cognitive_operations",
            alias_map=COGNITIVE_OPERATION_ALIAS_MAP,
        ),
        coaching_focus=_validate_str_list(
            payload.get("coaching_focus"),
            "coaching_focus",
        ),
        allowed_scaffolds=_validate_enum_list(
            payload.get("allowed_scaffolds"),
            SCAFFOLD_VOCAB,
            "allowed_scaffolds",
            alias_map=SCAFFOLD_ALIAS_MAP,
        ),
        common_misconceptions=_validate_str_list(
            payload.get("common_misconceptions"),
            "common_misconceptions",
        ),
        format_risk_points=_validate_str_list(
            payload.get("format_risk_points"),
            "format_risk_points",
        ),
    )


def build_task_support_profile(
    *,
    question_text: str,
    options: dict[str, str],
    question_type: str,
    problem_requirement_profile: object,
    llm_client: OpenAICompatClient,
) -> TaskSupportProfile:
    user_payload = {
        "question_text": question_text,
        "options": options,
        "question_type": question_type,
        "problem_requirement_profile": asdict(problem_requirement_profile),
        "required_output_schema": {
            "q_matrix_attributes": sorted(Q_MATRIX_ATTRIBUTE_VOCAB),
            "q_matrix_rationale": "list[str]",
            "cognitive_operations": sorted(COGNITIVE_OPERATION_VOCAB),
            "coaching_focus": "list[str]",
            "allowed_scaffolds": sorted(SCAFFOLD_VOCAB),
            "common_misconceptions": "list[str]",
            "format_risk_points": "list[str]",
        },
    }
    last_exc: ValueError | None = None
    last_parsed: dict[str, Any] | None = None
    for attempt_idx in range(3):
        system_prompt = TASK_SUPPORT_PROFILE_PROMPT
        user_prompt = json.dumps(user_payload, ensure_ascii=False)
        if attempt_idx == 1:
            system_prompt += SCHEMA_RETRY_SUFFIX
            if last_exc is not None:
                system_prompt += f"\nPrevious schema error:\n- {last_exc}\n"
        elif attempt_idx == 2:
            system_prompt += SCHEMA_REPAIR_SUFFIX
            repair_payload = {
                "schema_error": str(last_exc) if last_exc is not None else "",
                "previous_json": last_parsed,
                "allowed_vocabularies": user_payload["required_output_schema"],
            }
            user_prompt = json.dumps(repair_payload, ensure_ascii=False)
        parsed = llm_client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        last_parsed = parsed
        try:
            return task_support_profile_from_dict(parsed)
        except ValueError as exc:
            last_exc = exc
            continue
    if last_exc is None:
        raise RuntimeError("task support profile retry failed without captured exception")
    raise ValueError(
        f"task support profile schema retry failed: {last_exc}; "
        f"last_parsed={json.dumps(last_parsed, ensure_ascii=False)[:1200]}"
    ) from last_exc
