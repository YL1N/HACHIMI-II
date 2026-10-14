from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .dialogue_context import DialogueContextState
from .llm_client import OpenAICompatClient, require_keys
from .persona_prior import (
    PersonaPriorSummary,
    persona_prior_summary_to_dict,
)
from .prompts import STUDENT_CONTEXT_PROFILE_SYSTEM_PROMPT


ICAP_LEVELS = ("Passive", "Active", "Constructive", "Interactive")


@dataclass(frozen=True)
class StudentContextProfile:
    self_efficacy_analysis: dict[str, object]
    srl_analysis: dict[str, object]
    control_value_analysis: dict[str, object]
    engagement_tendency_analysis: dict[str, object]
    response_style_analysis: dict[str, object]
    evidence_trace: list[str]


def build_student_context_profile(
    context: DialogueContextState,
    llm_client: OpenAICompatClient,
    persona_prior_summary: PersonaPriorSummary | None = None,
) -> StudentContextProfile:
    payload = {
        "dialogue_context": asdict(context),
        "persona_prior_summary": persona_prior_summary_to_dict(
            persona_prior_summary
        ),
        "instructions": {
            "bandura_rule": (
                "Self-efficacy is descriptive. Do not compress it into low/medium/high."
            ),
            "zimmerman_rule": (
                "SRL analysis is descriptive. Use process weaknesses such as "
                "Forethought vulnerability, Performance-phase monitoring weakness, "
                "or Self-reflection weakness."
            ),
            "pekrun_rule": (
                "Control-value analysis is descriptive. Do not compress it into low/medium/high."
            ),
            "icap_rule": f"ICAP must be exactly one of {list(ICAP_LEVELS)}.",
            "persona_prior_rule": (
                "If a persona prior summary is provided, use it only as a background prior "
                "for the current learner. Do not treat it as the answer "
                "script for the current turn."
            ),
        },
        "required_schema": {
            "self_efficacy_analysis": {
                "efficacy_belief_description": "string",
                "efficacy_belief_evidence": ["string"],
            },
            "srl_analysis": {
                "primary_srl_vulnerability": "string",
                "srl_process_evidence": ["string"],
            },
            "control_value_analysis": {
                "control_appraisal_description": "string",
                "value_appraisal_description": "string",
                "control_value_evidence": ["string"],
            },
            "engagement_tendency_analysis": {
                "engagement_level_tendency": "Passive | Active | Constructive | Interactive",
                "engagement_evidence": ["string"],
            },
            "response_style_analysis": {
                "response_directness_description": "string",
                "response_directness_evidence": ["string"],
            },
            "evidence_trace": ["string"],
        },
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    parsed = llm_client.chat_json(
        system_prompt=STUDENT_CONTEXT_PROFILE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _parse_student_context_profile(parsed)
    except (KeyError, ValueError) as exc:
        repaired = llm_client.retry_schema_json(
            system_prompt=STUDENT_CONTEXT_PROFILE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=parsed,
            validation_error=str(exc),
        )
        return _parse_student_context_profile(repaired)


def student_context_profile_to_dict(
    student_context_profile: StudentContextProfile,
) -> dict[str, object]:
    return asdict(student_context_profile)


def _parse_student_context_profile(parsed: object) -> StudentContextProfile:
    parsed = require_keys(
        parsed,
        (
            "self_efficacy_analysis",
            "srl_analysis",
            "control_value_analysis",
            "engagement_tendency_analysis",
            "response_style_analysis",
            "evidence_trace",
        ),
        "StudentContextProfile",
    )
    engagement_module = require_keys(
        parsed["engagement_tendency_analysis"],
        (
            "engagement_level_tendency",
            "engagement_evidence",
        ),
        "StudentContextProfile.engagement_tendency_analysis",
    )
    engagement_level = str(engagement_module["engagement_level_tendency"]).strip()
    if engagement_level not in ICAP_LEVELS:
        raise ValueError(f"invalid ICAP category: {engagement_level}")
    return StudentContextProfile(
        self_efficacy_analysis=_coerce_dict_with_list_values(
            parsed["self_efficacy_analysis"],
            field_name="self_efficacy_analysis",
            required_list_keys=("efficacy_belief_evidence",),
        ),
        srl_analysis=_coerce_dict_with_list_values(
            parsed["srl_analysis"],
            field_name="srl_analysis",
            required_list_keys=("srl_process_evidence",),
        ),
        control_value_analysis=_coerce_dict_with_list_values(
            parsed["control_value_analysis"],
            field_name="control_value_analysis",
            required_list_keys=("control_value_evidence",),
        ),
        engagement_tendency_analysis=_coerce_dict_with_list_values(
            parsed["engagement_tendency_analysis"],
            field_name="engagement_tendency_analysis",
            required_list_keys=("engagement_evidence",),
        ),
        response_style_analysis=_coerce_dict_with_list_values(
            parsed["response_style_analysis"],
            field_name="response_style_analysis",
            required_list_keys=("response_directness_evidence",),
        ),
        evidence_trace=_coerce_str_list(parsed["evidence_trace"], "evidence_trace"),
    )


def _coerce_str_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if not result:
        raise ValueError(f"{field_name} must contain non-empty strings")
    return result


def _coerce_dict_with_list_values(
    value: object,
    field_name: str,
    required_list_keys: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be dict, got {type(value).__name__}: {value!r}")
    result: dict[str, object] = {}
    for key, item in value.items():
        if key in required_list_keys:
            result[str(key)] = _coerce_str_list(item, str(key))
        else:
            text = str(item).strip()
            if not text:
                raise ValueError(
                    f"empty text field in {field_name}.{key}; raw_module_value={value!r}"
                )
            result[str(key)] = text
    for key in required_list_keys:
        if key not in result:
            raise ValueError(
                f"missing required key in {field_name}: {key}; raw_module_value={value!r}"
            )
    return result
