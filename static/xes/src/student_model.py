from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .data_loading import MathTaskCapabilityAnchor, PersonaRecord
from .llm_client import OpenAICompatClient
from .prompts import STUDENT_INTERNAL_SIGNALS_PROMPT, STUDENT_MODEL_PROMPT

SCHEMA_RETRY_SUFFIX = """

Schema correction:
- Your previous reply omitted or malformed one or more required fields.
- Regenerate from scratch.
- Every required key must be present.
- Every required nested object must be a real JSON object, not null.
- Return exactly one complete JSON object.
"""


@dataclass(frozen=True)
class SelfEfficacyAnalysis:
    efficacy_belief_description: str
    efficacy_belief_evidence: list[str]


@dataclass(frozen=True)
class SRLAnalysis:
    primary_srl_vulnerability: str
    srl_process_evidence: list[str]


@dataclass(frozen=True)
class ControlValueAnalysis:
    control_appraisal_description: str
    value_appraisal_description: str
    control_value_evidence: list[str]


@dataclass(frozen=True)
class StudentInternalSignals:
    efficacy_signal: str
    srl_fragility_signal: str
    control_signal: str
    value_signal: str
    directness_signal: str


@dataclass(frozen=True)
class MathTaskCapabilityProfile:
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
    common_error_families: list[str]
    capability_evidence: list[str]


@dataclass(frozen=True)
class StudentModel:
    student_id: str
    grade: str
    academic_level: str
    weak_subjects: list[str]
    strong_subjects: list[str]
    self_efficacy_analysis: SelfEfficacyAnalysis
    srl_analysis: SRLAnalysis
    control_value_analysis: ControlValueAnalysis
    engagement_level_tendency: str
    engagement_evidence: list[str]
    response_directness_description: str
    response_directness_evidence: list[str]
    raw_summary: str
    math_anchor_profile_summary: str = ""
    math_anchor_profile_evidence: list[str] = field(default_factory=list)
    math_task_capability_profile: MathTaskCapabilityProfile | None = None


def _capability_profile_from_anchor(
    anchor: MathTaskCapabilityAnchor,
) -> MathTaskCapabilityProfile:
    return MathTaskCapabilityProfile(
        arithmetic_fluency=anchor.arithmetic_fluency,
        word_problem_transfer=anchor.word_problem_transfer,
        multi_step_stability=anchor.multi_step_stability,
        geometry_intuition=anchor.geometry_intuition,
        pattern_rule_detection=anchor.pattern_rule_detection,
        option_elimination=anchor.option_elimination,
        fill_blank_precision=anchor.fill_blank_precision,
        hard_item_persistence=anchor.hard_item_persistence,
        guessing_tendency=anchor.guessing_tendency,
        confidence_calibration="calibrated",
        format_discipline=(
            "high"
            if anchor.option_elimination == "high" and anchor.fill_blank_precision == "high"
            else ("low" if anchor.fill_blank_precision == "low" else "medium")
        ),
        common_error_families=["support_anchor_based_capability_boundary"],
        capability_evidence=list(anchor.capability_evidence),
    )


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


def _validate_str(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _validate_str_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list, got {type(value).__name__}")
    out = [str(item).strip() for item in value if str(item).strip()]
    if not out:
        raise ValueError(f"{field_name} must contain at least one non-empty item")
    return out


def _validate_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be object/dict, got {type(value).__name__}")
    return value


def _build_student_model_with_llm(
    persona: PersonaRecord, llm_client: OpenAICompatClient
) -> StudentModel:
    user_payload = {
        "student_id": persona.student_id,
        "grade": persona.grade,
        "academic_level": persona.academic_level,
        "strong_subjects": persona.strong_subjects,
        "weak_subjects": persona.weak_subjects,
        "learning_profile_text": persona.learning_profile_text,
        "raw_hachimi_persona": persona.raw_persona,
        "math_anchor_profile": (
            {
                "summary": persona.math_anchor_profile.summary,
                "evidence": persona.math_anchor_profile.evidence,
                "within_level_strength": persona.math_anchor_profile.within_level_strength,
                "support_item_count": persona.math_anchor_profile.support_item_count,
                "support_accuracy": persona.math_anchor_profile.support_accuracy,
                "support_accuracy_percentile_within_level": (
                    persona.math_anchor_profile.support_accuracy_percentile_within_level
                ),
                "easy_accuracy": persona.math_anchor_profile.easy_accuracy,
                "medium_accuracy": persona.math_anchor_profile.medium_accuracy,
                "hard_accuracy": persona.math_anchor_profile.hard_accuracy,
                "excluded_question_count": persona.math_anchor_profile.excluded_question_count,
            }
            if persona.math_anchor_profile is not None
            else None
        ),
        "math_task_capability_anchor": (
            asdict(persona.math_task_capability_anchor)
            if persona.math_task_capability_anchor is not None
            else None
        ),
        "required_output_schema": {
            "self_efficacy_analysis": {
                "efficacy_belief_description": "string",
                "efficacy_belief_evidence": "list[str]",
            },
            "srl_analysis": {
                "primary_srl_vulnerability": "string",
                "srl_process_evidence": "list[str]",
            },
            "control_value_analysis": {
                "control_appraisal_description": "string",
                "value_appraisal_description": "string",
                "control_value_evidence": "list[str]",
            },
            "engagement_level_tendency": "Passive|Active|Constructive|Interactive",
            "engagement_evidence": "list[str]",
            "response_directness_description": "string",
            "response_directness_evidence": "list[str]",
            "math_task_capability_profile": {
                "arithmetic_fluency": "high|medium|low",
                "word_problem_transfer": "high|medium|low",
                "multi_step_stability": "high|medium|low",
                "geometry_intuition": "high|medium|low",
                "pattern_rule_detection": "high|medium|low",
                "option_elimination": "high|medium|low",
                "fill_blank_precision": "high|medium|low",
                "hard_item_persistence": "high|medium|low",
                "guessing_tendency": "high|medium|low",
                "confidence_calibration": "over_confident|calibrated|under_confident",
                "format_discipline": "high|medium|low",
                "common_error_families": "list[str]",
                "capability_evidence": "list[str]",
            },
            "raw_summary": "short string",
        },
    }
    last_exc: ValueError | None = None
    last_parsed: dict[str, Any] | None = None
    for attempt_idx in range(2):
        system_prompt = STUDENT_MODEL_PROMPT
        if attempt_idx == 1:
            system_prompt += SCHEMA_RETRY_SUFFIX
        parsed = llm_client.chat_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False),
        )
        last_parsed = parsed
        try:
            return _parse_student_model(parsed=parsed, persona=persona)
        except ValueError as exc:
            last_exc = exc
            continue
    if last_exc is None:
        raise RuntimeError("student model schema retry failed without captured exception")
    raise ValueError(
        f"student model schema retry failed: {last_exc}; "
        f"last_parsed={json.dumps(last_parsed, ensure_ascii=False)[:1200]}"
    ) from last_exc


def _parse_student_model(parsed: dict[str, Any], persona: PersonaRecord) -> StudentModel:
    self_efficacy_obj = _validate_dict(
        parsed.get("self_efficacy_analysis"), "self_efficacy_analysis"
    )
    srl_obj = _validate_dict(parsed.get("srl_analysis"), "srl_analysis")
    control_value_obj = _validate_dict(
        parsed.get("control_value_analysis"), "control_value_analysis"
    )

    self_efficacy_analysis = SelfEfficacyAnalysis(
        efficacy_belief_description=_validate_str(
            self_efficacy_obj.get("efficacy_belief_description"),
            "self_efficacy_analysis.efficacy_belief_description",
        ),
        efficacy_belief_evidence=_validate_str_list(
            self_efficacy_obj.get("efficacy_belief_evidence"),
            "self_efficacy_analysis.efficacy_belief_evidence",
        ),
    )
    srl_analysis = SRLAnalysis(
        primary_srl_vulnerability=_validate_str(
            srl_obj.get("primary_srl_vulnerability"),
            "srl_analysis.primary_srl_vulnerability",
        ),
        srl_process_evidence=_validate_str_list(
            srl_obj.get("srl_process_evidence"),
            "srl_analysis.srl_process_evidence",
        ),
    )
    control_value_analysis = ControlValueAnalysis(
        control_appraisal_description=_validate_str(
            control_value_obj.get("control_appraisal_description"),
            "control_value_analysis.control_appraisal_description",
        ),
        value_appraisal_description=_validate_str(
            control_value_obj.get("value_appraisal_description"),
            "control_value_analysis.value_appraisal_description",
        ),
        control_value_evidence=_validate_str_list(
            control_value_obj.get("control_value_evidence"),
            "control_value_analysis.control_value_evidence",
        ),
    )

    engagement_level_tendency = _validate_enum(
        parsed.get("engagement_level_tendency"),
        {"Passive", "Active", "Constructive", "Interactive"},
        "engagement_level_tendency",
        alias_map={
            "passive": "Passive",
            "active": "Active",
            "constructive": "Constructive",
            "interactive": "Interactive",
        },
    )
    engagement_evidence = _validate_str_list(
        parsed.get("engagement_evidence"), "engagement_evidence"
    )
    response_directness_description = _validate_str(
        parsed.get("response_directness_description"), "response_directness_description"
    )
    response_directness_evidence = _validate_str_list(
        parsed.get("response_directness_evidence"), "response_directness_evidence"
    )
    raw_summary = _validate_str(parsed.get("raw_summary"), "raw_summary")
    if persona.math_task_capability_anchor is not None:
        math_task_capability_profile = _capability_profile_from_anchor(
            persona.math_task_capability_anchor
        )
    else:
        math_task_capability_obj = _validate_dict(
            parsed.get("math_task_capability_profile"),
            "math_task_capability_profile",
        )
        math_task_capability_profile = MathTaskCapabilityProfile(
            arithmetic_fluency=_validate_enum(
                math_task_capability_obj.get("arithmetic_fluency"),
                {"low", "medium", "high"},
                "math_task_capability_profile.arithmetic_fluency",
            ),
            word_problem_transfer=_validate_enum(
                math_task_capability_obj.get("word_problem_transfer"),
                {"low", "medium", "high"},
                "math_task_capability_profile.word_problem_transfer",
            ),
            multi_step_stability=_validate_enum(
                math_task_capability_obj.get("multi_step_stability"),
                {"low", "medium", "high"},
                "math_task_capability_profile.multi_step_stability",
            ),
            geometry_intuition=_validate_enum(
                math_task_capability_obj.get("geometry_intuition"),
                {"low", "medium", "high"},
                "math_task_capability_profile.geometry_intuition",
            ),
            pattern_rule_detection=_validate_enum(
                math_task_capability_obj.get("pattern_rule_detection"),
                {"low", "medium", "high"},
                "math_task_capability_profile.pattern_rule_detection",
            ),
            option_elimination=_validate_enum(
                math_task_capability_obj.get("option_elimination"),
                {"low", "medium", "high"},
                "math_task_capability_profile.option_elimination",
            ),
            fill_blank_precision=_validate_enum(
                math_task_capability_obj.get("fill_blank_precision"),
                {"low", "medium", "high"},
                "math_task_capability_profile.fill_blank_precision",
            ),
            hard_item_persistence=_validate_enum(
                math_task_capability_obj.get("hard_item_persistence"),
                {"low", "medium", "high"},
                "math_task_capability_profile.hard_item_persistence",
            ),
            guessing_tendency=_validate_enum(
                math_task_capability_obj.get("guessing_tendency"),
                {"low", "medium", "high"},
                "math_task_capability_profile.guessing_tendency",
            ),
            confidence_calibration=_validate_enum(
                math_task_capability_obj.get("confidence_calibration"),
                {"over_confident", "calibrated", "under_confident"},
                "math_task_capability_profile.confidence_calibration",
            ),
            format_discipline=_validate_enum(
                math_task_capability_obj.get("format_discipline"),
                {"low", "medium", "high"},
                "math_task_capability_profile.format_discipline",
            ),
            common_error_families=_validate_str_list(
                math_task_capability_obj.get("common_error_families"),
                "math_task_capability_profile.common_error_families",
            ),
            capability_evidence=_validate_str_list(
                math_task_capability_obj.get("capability_evidence"),
                "math_task_capability_profile.capability_evidence",
            ),
        )

    strong_subjects = persona.strong_subjects or ["unknown"]
    weak_subjects = persona.weak_subjects or ["unknown"]

    return StudentModel(
        student_id=persona.student_id,
        grade=persona.grade,
        academic_level=persona.academic_level,
        weak_subjects=weak_subjects,
        strong_subjects=strong_subjects,
        self_efficacy_analysis=self_efficacy_analysis,
        srl_analysis=srl_analysis,
        control_value_analysis=control_value_analysis,
        engagement_level_tendency=engagement_level_tendency,
        engagement_evidence=engagement_evidence,
        response_directness_description=response_directness_description,
        response_directness_evidence=response_directness_evidence,
        raw_summary=raw_summary,
        math_anchor_profile_summary=(
            persona.math_anchor_profile.summary if persona.math_anchor_profile is not None else ""
        ),
        math_anchor_profile_evidence=(
            list(persona.math_anchor_profile.evidence)
            if persona.math_anchor_profile is not None
            else []
        ),
        math_task_capability_profile=math_task_capability_profile,
    )


def _build_internal_signals_with_llm(
    student_model: StudentModel,
    llm_client: OpenAICompatClient,
) -> StudentInternalSignals:
    user_payload = {
        "student_model": {
            "student_id": student_model.student_id,
            "grade": student_model.grade,
            "academic_level": student_model.academic_level,
            "weak_subjects": student_model.weak_subjects,
            "strong_subjects": student_model.strong_subjects,
            "self_efficacy_analysis": {
                "efficacy_belief_description": (
                    student_model.self_efficacy_analysis.efficacy_belief_description
                ),
                "efficacy_belief_evidence": (
                    student_model.self_efficacy_analysis.efficacy_belief_evidence
                ),
            },
            "srl_analysis": {
                "primary_srl_vulnerability": student_model.srl_analysis.primary_srl_vulnerability,
                "srl_process_evidence": student_model.srl_analysis.srl_process_evidence,
            },
            "control_value_analysis": {
                "control_appraisal_description": (
                    student_model.control_value_analysis.control_appraisal_description
                ),
                "value_appraisal_description": (
                    student_model.control_value_analysis.value_appraisal_description
                ),
                "control_value_evidence": student_model.control_value_analysis.control_value_evidence,
            },
            "engagement_level_tendency": student_model.engagement_level_tendency,
            "engagement_evidence": student_model.engagement_evidence,
            "response_directness_description": student_model.response_directness_description,
            "response_directness_evidence": student_model.response_directness_evidence,
            "raw_summary": student_model.raw_summary,
            "math_anchor_profile_summary": student_model.math_anchor_profile_summary,
            "math_anchor_profile_evidence": student_model.math_anchor_profile_evidence,
            "math_task_capability_profile": (
                asdict(student_model.math_task_capability_profile)
                if student_model.math_task_capability_profile is not None
                else None
            ),
        },
        "required_output_schema": {
            "efficacy_signal": "low|medium|high",
            "srl_fragility_signal": "low|medium|high",
            "control_signal": "low|medium|high",
            "value_signal": "low|medium|high",
            "directness_signal": "low|medium|high",
        },
    }
    last_exc: ValueError | None = None
    for attempt_idx in range(2):
        system_prompt = STUDENT_INTERNAL_SIGNALS_PROMPT
        if attempt_idx == 1:
            system_prompt += SCHEMA_RETRY_SUFFIX
        parsed = llm_client.chat_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False),
        )
        try:
            return _parse_internal_signals(parsed=parsed)
        except ValueError as exc:
            last_exc = exc
            continue
    if last_exc is None:
        raise RuntimeError("internal signals schema retry failed without captured exception")
    raise last_exc


def _parse_internal_signals(parsed: dict[str, Any]) -> StudentInternalSignals:
    return StudentInternalSignals(
        efficacy_signal=_validate_enum(
            parsed.get("efficacy_signal"),
            {"low", "medium", "high"},
            "efficacy_signal",
        ),
        srl_fragility_signal=_validate_enum(
            parsed.get("srl_fragility_signal"),
            {"low", "medium", "high"},
            "srl_fragility_signal",
        ),
        control_signal=_validate_enum(
            parsed.get("control_signal"),
            {"low", "medium", "high"},
            "control_signal",
        ),
        value_signal=_validate_enum(
            parsed.get("value_signal"),
            {"low", "medium", "high"},
            "value_signal",
        ),
        directness_signal=_validate_enum(
            parsed.get("directness_signal"),
            {"low", "medium", "high"},
            "directness_signal",
        ),
    )


def map_student_model_to_internal_signals(
    student_model: StudentModel,
    llm_client: OpenAICompatClient | None = None,
) -> StudentInternalSignals:
    if llm_client is None:
        raise ValueError(
            "map_student_model_to_internal_signals requires llm_client; semantic mapping cannot use heuristic fallback"
        )
    return _build_internal_signals_with_llm(student_model=student_model, llm_client=llm_client)


def build_student_model(
    persona: PersonaRecord,
    llm_client: OpenAICompatClient | None = None,
) -> StudentModel:
    if llm_client is None:
        raise ValueError(
            "build_student_model requires llm_client; semantic inference cannot use heuristic fallback"
        )
    return _build_student_model_with_llm(persona, llm_client)
