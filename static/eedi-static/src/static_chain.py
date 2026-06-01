from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any

from .data_loading import EediStaticQuestion, EediStaticStudent, summarize_history
from .hachimi import HachimiMatch
from .llm_client import OpenAICompatClient


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
    math_anchor_profile_summary: str
    math_anchor_profile_evidence: list[str]
    math_task_capability_profile: MathTaskCapabilityProfile
    matched_hachimi_id: str | None = None
    hachimi_profile_card: dict[str, Any] | None = None
    hachimi_match_evidence: list[str] | None = None
    hachimi_conflict_evidence: list[str] | None = None
    fusion_rule: str | None = None


@dataclass(frozen=True)
class ProblemRequirementProfile:
    question_id: str
    subject_path: list[str]
    prerequisite_knowledge: list[str]
    operation_complexity: str
    operation_complexity_justification: str
    abstraction_level: str
    abstraction_level_justification: str
    knowledge_integration_demand: str
    representation_shift_required: str
    response_format_demand: str
    guessability: str
    likely_traps: list[str]
    notes: list[str]
    answer_space: list[str]


@dataclass(frozen=True)
class StudentItemInteractionDecision:
    predicted_reachability: str
    predicted_correctness_band: str
    likely_outcome: str
    likely_error_family: str
    confidence_cap: str
    explanation_cap: str
    decision_rationale: list[str]


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
    output_answer_space: list[str]


@dataclass(frozen=True)
class ViolationReport:
    has_violation: bool
    reasons: list[str]
    severity: str


@dataclass(frozen=True)
class Prediction:
    student_id: str
    question_id: str
    predicted_answer: str
    student_response: str
    student_model: StudentModel
    internal_signals: StudentInternalSignals
    problem_profile: ProblemRequirementProfile
    interaction_decision: StudentItemInteractionDecision
    response_state: ItemResponseState
    constraint_bundle: ConstraintBundle
    violation_report: ViolationReport
    retry_count: int


SYSTEM_JSON = (
    "You are a careful educational simulation component. "
    "Return exactly one JSON object. Do not include markdown. "
    "Do not use hidden target labels, current test labels, or future student answers."
)

LEVELS = {"very_low", "low", "medium", "high"}
CAPABILITY_LEVELS = {"not_observed", "very_low", "low", "medium", "high"}
COMPLEXITY = {"low", "medium", "high"}
CORRECTNESS_BANDS = {"likely_correct", "uncertain", "likely_wrong"}
REACHABILITY = {"below_reach", "partial_reach", "within_reach"}
CONFIDENCE_CAPS = {"low", "medium", "high"}
EXPLANATION_CAPS = {"none", "brief", "partial", "complete"}


def _compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _non_empty(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _string_list(value: Any, field_name: str, min_len: int = 1) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) < min_len:
        raise ValueError(f"{field_name} must contain at least {min_len} non-empty item(s)")
    return result


def _validate_response_style_guidance(guidance: list[str]) -> list[str]:
    forbidden_patterns = [
        r"\bemphasiz(e|ing)\b",
        r"\breinforce\b",
        r"\bprompt\b",
        r"\bteach\b",
        r"\bguide\b",
        r"\bshow\b",
        r"\bexplain\b",
        r"\bcorrect answer\b",
        r"\bcorrect option\b",
        r"\bright answer\b",
        r"\bprove\b",
    ]
    joined = " ".join(guidance).lower()
    if any(re.search(pattern, joined) for pattern in forbidden_patterns):
        raise ValueError(
            "response_style_guidance must describe student expression style only, "
            "not tutoring hints or correct-solution instructions"
        )
    return guidance


def _enum(value: Any, allowed: set[str], field_name: str) -> str:
    text = str(value).strip()
    canonical = text.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "poor": "very_low",
        "verylow": "very_low",
        "very_low": "very_low",
        "notobserved": "not_observed",
        "unobserved": "not_observed",
        "unknown": "not_observed",
        "moderate": "medium",
        "med": "medium",
        "short": "brief",
        "full": "complete",
    }
    if canonical == "none" and "not_observed" in allowed:
        text = "not_observed"
    elif canonical in aliases:
        text = aliases[canonical]
    else:
        text = canonical
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}, got {text!r}")
    return text


def _choice(value: Any, field_name: str) -> str:
    return _enum(value, {"1", "2", "3", "4"}, field_name)


def _chat_and_parse_with_retry(
    llm: OpenAICompatClient,
    prompt: str,
    parser,
    object_name: str,
    max_attempts: int = 4,
):
    current_prompt = prompt
    last_error: ValueError | None = None
    for attempt_idx in range(max_attempts):
        parsed = llm.chat_json(SYSTEM_JSON, current_prompt)
        try:
            return parser(parsed)
        except ValueError as exc:
            last_error = exc
            current_prompt = (
                prompt
                + "\n\nSchema correction:\n"
                + f"Attempt {attempt_idx + 1} failed because the previous {object_name} JSON violated the schema: {exc}.\n"
                + "Regenerate from scratch. Return exactly one complete JSON object.\n"
                + "If a field is specified as list[str], it must be a JSON array, never a plain string or object.\n"
            )
    raise ValueError(f"{object_name} failed schema validation after {max_attempts} attempts: {last_error}")


def _chat_image_and_parse_with_retry(
    llm: OpenAICompatClient,
    prompt: str,
    image_path: str,
    parser,
    object_name: str,
    max_attempts: int = 4,
):
    current_prompt = prompt
    last_error: ValueError | None = None
    for attempt_idx in range(max_attempts):
        parsed = llm.chat_json_with_image(SYSTEM_JSON, current_prompt, image_path)
        try:
            return parser(parsed)
        except ValueError as exc:
            last_error = exc
            current_prompt = (
                prompt
                + "\n\nSchema correction:\n"
                + f"Attempt {attempt_idx + 1} failed because the previous {object_name} JSON violated the schema: {exc}.\n"
                + "Regenerate from scratch from the attached image. Return exactly one complete JSON object.\n"
                + "If a field is specified as list[str], it must be a JSON array, never a plain string or object.\n"
            )
    raise ValueError(f"{object_name} failed schema validation after {max_attempts} attempts: {last_error}")


def _sentence_count(text: str) -> int:
    parts = [part for part in re.split(r"\.(?!\d)|[!?。！？]+", text) if part.strip()]
    return max(1, len(parts)) if text.strip() else 0


def _capability_from_history(
    history_accuracy: float,
    subject_accuracy: dict[str, float],
) -> MathTaskCapabilityProfile:
    def band(score: float) -> str:
        if score >= 0.75:
            return "high"
        if score >= 0.55:
            return "medium"
        if score >= 0.35:
            return "low"
        return "very_low"

    geometry_scores = [
        score
        for subject, score in subject_accuracy.items()
        if any(token in subject.lower() for token in ["angle", "shape", "geometry", "transform", "area"])
    ]
    arithmetic_scores = [
        score
        for subject, score in subject_accuracy.items()
        if any(token in subject.lower() for token in ["arithmetic", "multiplication", "division", "negative"])
    ]
    pattern_scores = [
        score
        for subject, score in subject_accuracy.items()
        if any(token in subject.lower() for token in ["sequence", "pattern", "expression", "factor"])
    ]

    geometry_score = sum(geometry_scores) / len(geometry_scores) if geometry_scores else history_accuracy
    arithmetic_score = sum(arithmetic_scores) / len(arithmetic_scores) if arithmetic_scores else history_accuracy
    pattern_score = sum(pattern_scores) / len(pattern_scores) if pattern_scores else history_accuracy
    common_errors = [
        subject
        for subject, score in sorted(subject_accuracy.items(), key=lambda item: (item[1], item[0]))[:4]
    ] or ["unknown"]
    return MathTaskCapabilityProfile(
        arithmetic_fluency=band(arithmetic_score),
        word_problem_transfer=band(history_accuracy),
        multi_step_stability=band(history_accuracy),
        geometry_intuition=band(geometry_score),
        pattern_rule_detection=band(pattern_score),
        option_elimination=band(history_accuracy),
        hard_item_persistence=band(history_accuracy),
        guessing_tendency="high" if history_accuracy < 0.40 else "medium" if history_accuracy < 0.65 else "low",
        confidence_calibration="medium",
        format_discipline="high",
        common_error_families=common_errors,
        capability_evidence=[
            f"history_accuracy={history_accuracy:.3f}",
            f"weakest_subjects={', '.join(common_errors[:3])}",
        ],
    )


def _deterministic_student_model(student: EediStaticStudent) -> StudentModel:
    summary = summarize_history(student)
    history_accuracy = float(summary["history_accuracy"])
    weak_subjects = list(summary["weakest_subjects"])
    strong_subjects = list(summary["strongest_subjects"])
    subject_accuracy = {str(k): float(v) for k, v in summary["subject_accuracy"].items()}
    capability = _capability_from_history(history_accuracy, subject_accuracy)
    if history_accuracy >= 0.67:
        academic_level = "high"
        efficacy = "generally confident on familiar diagnostic questions"
        control = "usually expects effort to translate into success"
    elif history_accuracy >= 0.50:
        academic_level = "medium"
        efficacy = "mixed confidence, stronger on familiar procedures"
        control = "can control routine items but becomes fragile on weak topics"
    elif history_accuracy >= 0.35:
        academic_level = "low"
        efficacy = "fragile confidence with frequent uncertainty"
        control = "often unsure whether effort will produce the right option"
    else:
        academic_level = "poor"
        efficacy = "low confidence across many topics"
        control = "often guesses because the task feels hard to control"

    return StudentModel(
        student_id=student.student_id,
        grade="UK Primary/Secondary/Sixth Form",
        academic_level=academic_level,
        weak_subjects=weak_subjects,
        strong_subjects=strong_subjects,
        self_efficacy_analysis=SelfEfficacyAnalysis(
            efficacy_belief_description=efficacy,
            efficacy_belief_evidence=[f"history_accuracy={history_accuracy:.3f}"],
        ),
        srl_analysis=SRLAnalysis(
            primary_srl_vulnerability=(
                "may choose quickly without checking options"
                if history_accuracy < 0.65
                else "usually stable but can still rely on shortcuts"
            ),
            srl_process_evidence=[f"weak_subjects={', '.join(weak_subjects[:3])}"],
        ),
        control_value_analysis=ControlValueAnalysis(
            control_appraisal_description=control,
            value_appraisal_description="treats short diagnostic questions as answer-selection tasks",
            control_value_evidence=[student.ability_level, f"ability_score_proxy={student.ability_score_proxy:.3f}"],
        ),
        engagement_level_tendency="medium",
        engagement_evidence=["completed enough EEDI diagnostic questions for common-test selection"],
        response_directness_description="likely to give a short option-level answer",
        response_directness_evidence=["EEDI task format is 4-option diagnostic selection"],
        raw_summary=(
            f"Student {student.student_id} is in {student.ability_level}; "
            f"history_accuracy={history_accuracy:.3f}; weak={weak_subjects[:3]}; strong={strong_subjects[:3]}."
        ),
        math_anchor_profile_summary=(
            f"EEDI history anchor: {len(student.history)} non-test history answers, "
            f"accuracy={history_accuracy:.3f}."
        ),
        math_anchor_profile_evidence=[
            f"ability_level={student.ability_level}",
            f"ability_score_proxy={student.ability_score_proxy:.3f}",
        ],
        math_task_capability_profile=capability,
    )


def _parse_student_model(
    parsed: dict[str, Any],
    student: EediStaticStudent,
    hachimi_match: HachimiMatch | None = None,
) -> StudentModel:
    fallback = _deterministic_student_model(student)
    capability_raw = parsed.get("math_task_capability_profile", {})
    if not isinstance(capability_raw, dict):
        raise ValueError("math_task_capability_profile must be an object")
    capability = MathTaskCapabilityProfile(
        arithmetic_fluency=_enum(capability_raw.get("arithmetic_fluency"), CAPABILITY_LEVELS, "arithmetic_fluency"),
        word_problem_transfer=_enum(capability_raw.get("word_problem_transfer"), CAPABILITY_LEVELS, "word_problem_transfer"),
        multi_step_stability=_enum(capability_raw.get("multi_step_stability"), CAPABILITY_LEVELS, "multi_step_stability"),
        geometry_intuition=_enum(capability_raw.get("geometry_intuition"), CAPABILITY_LEVELS, "geometry_intuition"),
        pattern_rule_detection=_enum(capability_raw.get("pattern_rule_detection"), CAPABILITY_LEVELS, "pattern_rule_detection"),
        option_elimination=_enum(capability_raw.get("option_elimination"), CAPABILITY_LEVELS, "option_elimination"),
        hard_item_persistence=_enum(capability_raw.get("hard_item_persistence"), CAPABILITY_LEVELS, "hard_item_persistence"),
        guessing_tendency=_enum(capability_raw.get("guessing_tendency"), CAPABILITY_LEVELS, "guessing_tendency"),
        confidence_calibration=_enum(capability_raw.get("confidence_calibration"), CAPABILITY_LEVELS, "confidence_calibration"),
        format_discipline=_enum(capability_raw.get("format_discipline"), CAPABILITY_LEVELS, "format_discipline"),
        common_error_families=_string_list(capability_raw.get("common_error_families"), "common_error_families"),
        capability_evidence=_string_list(capability_raw.get("capability_evidence"), "capability_evidence"),
    )
    return StudentModel(
        student_id=student.student_id,
        grade="UK Primary/Secondary/Sixth Form",
        academic_level=_non_empty(parsed.get("academic_level", fallback.academic_level), "academic_level"),
        weak_subjects=_string_list(parsed.get("weak_subjects", fallback.weak_subjects), "weak_subjects"),
        strong_subjects=_string_list(parsed.get("strong_subjects", fallback.strong_subjects), "strong_subjects"),
        self_efficacy_analysis=SelfEfficacyAnalysis(
            efficacy_belief_description=_non_empty(
                parsed.get("self_efficacy_analysis", {}).get("efficacy_belief_description"),
                "efficacy_belief_description",
            ),
            efficacy_belief_evidence=_string_list(
                parsed.get("self_efficacy_analysis", {}).get("efficacy_belief_evidence"),
                "efficacy_belief_evidence",
            ),
        ),
        srl_analysis=SRLAnalysis(
            primary_srl_vulnerability=_non_empty(
                parsed.get("srl_analysis", {}).get("primary_srl_vulnerability"),
                "primary_srl_vulnerability",
            ),
            srl_process_evidence=_string_list(
                parsed.get("srl_analysis", {}).get("srl_process_evidence"),
                "srl_process_evidence",
            ),
        ),
        control_value_analysis=ControlValueAnalysis(
            control_appraisal_description=_non_empty(
                parsed.get("control_value_analysis", {}).get("control_appraisal_description"),
                "control_appraisal_description",
            ),
            value_appraisal_description=_non_empty(
                parsed.get("control_value_analysis", {}).get("value_appraisal_description"),
                "value_appraisal_description",
            ),
            control_value_evidence=_string_list(
                parsed.get("control_value_analysis", {}).get("control_value_evidence"),
                "control_value_evidence",
            ),
        ),
        engagement_level_tendency=_non_empty(parsed.get("engagement_level_tendency"), "engagement_level_tendency"),
        engagement_evidence=_string_list(parsed.get("engagement_evidence"), "engagement_evidence"),
        response_directness_description=_non_empty(
            parsed.get("response_directness_description"),
            "response_directness_description",
        ),
        response_directness_evidence=_string_list(
            parsed.get("response_directness_evidence"),
            "response_directness_evidence",
        ),
        raw_summary=_non_empty(parsed.get("raw_summary"), "raw_summary"),
        math_anchor_profile_summary=fallback.math_anchor_profile_summary,
        math_anchor_profile_evidence=fallback.math_anchor_profile_evidence,
        math_task_capability_profile=capability,
        matched_hachimi_id=hachimi_match.hachimi_id if hachimi_match is not None else None,
        hachimi_profile_card=hachimi_match.hachimi_profile_card if hachimi_match is not None else None,
        hachimi_match_evidence=hachimi_match.match_evidence if hachimi_match is not None else None,
        hachimi_conflict_evidence=hachimi_match.conflict_evidence if hachimi_match is not None else None,
        fusion_rule=hachimi_match.fusion_rule if hachimi_match is not None else None,
    )


def build_student_model(
    student: EediStaticStudent,
    llm: OpenAICompatClient | None,
    hachimi_match: HachimiMatch | None = None,
) -> StudentModel:
    summary = summarize_history(student)
    fallback = _deterministic_student_model(student)
    if llm is None:
        if hachimi_match is None:
            return fallback
        return replace(
            fallback,
            matched_hachimi_id=hachimi_match.hachimi_id,
            hachimi_profile_card=hachimi_match.hachimi_profile_card,
            hachimi_match_evidence=hachimi_match.match_evidence,
            hachimi_conflict_evidence=hachimi_match.conflict_evidence,
            fusion_rule=hachimi_match.fusion_rule,
        )

    hachimi_block = (
        "No HACHIMI match is attached for this run."
        if hachimi_match is None
        else _compact_json(
            {
                "eedi_observed_profile": hachimi_match.eedi_observed_profile,
                "raw_hachimi_persona": hachimi_match.raw_hachimi_persona,
                "hachimi_profile_card": hachimi_match.hachimi_profile_card,
                "match_evidence": hachimi_match.match_evidence,
                "conflict_evidence": hachimi_match.conflict_evidence,
                "fusion_rule": hachimi_match.fusion_rule,
            }
        )
    )

    prompt = f"""
Build a third-person StudentModel for EEDI-static student simulation.

Use only the non-test history summary. Do not use current test answers, current correctness, future answers, or evaluation metrics.
This is the same object role as XES StudentModel, adapted to EEDI-static 4-option diagnostic questions.
If a HACHIMI match is provided, use it as an external student-profile prior. The complete raw_hachimi_persona is supplied for audit and must be considered, including development stage, personality, values, social relationship, creativity, and mental health fields.
Fusion rule: EEDI observed math history is stronger evidence for math capability; HACHIMI fills learning-style, affective, self-regulation, and response-expression gaps. If EEDI and HACHIMI conflict, keep the conflict visible in the resulting profile rather than letting HACHIMI overwrite EEDI evidence.

History summary:
{_compact_json(summary)}

HACHIMI fusion input:
{hachimi_block}

Return JSON in exactly this object shape:
{{
  "academic_level": "string",
  "weak_subjects": ["string"],
  "strong_subjects": ["string"],
  "self_efficacy_analysis": {{
    "efficacy_belief_description": "string",
    "efficacy_belief_evidence": ["string"]
  }},
  "srl_analysis": {{
    "primary_srl_vulnerability": "string",
    "srl_process_evidence": ["string"]
  }},
  "control_value_analysis": {{
    "control_appraisal_description": "string",
    "value_appraisal_description": "string",
    "control_value_evidence": ["string"]
  }},
  "engagement_level_tendency": "string",
  "engagement_evidence": ["string"],
  "response_directness_description": "string",
  "response_directness_evidence": ["string"],
  "raw_summary": "string",
  "math_task_capability_profile": {{
    "arithmetic_fluency": "not_observed|very_low|low|medium|high",
    "word_problem_transfer": "not_observed|very_low|low|medium|high",
    "multi_step_stability": "not_observed|very_low|low|medium|high",
    "geometry_intuition": "not_observed|very_low|low|medium|high",
    "pattern_rule_detection": "not_observed|very_low|low|medium|high",
    "option_elimination": "not_observed|very_low|low|medium|high",
    "hard_item_persistence": "not_observed|very_low|low|medium|high",
    "guessing_tendency": "not_observed|very_low|low|medium|high",
    "confidence_calibration": "not_observed|very_low|low|medium|high",
    "format_discipline": "not_observed|very_low|low|medium|high",
    "common_error_families": ["string"],
    "capability_evidence": ["string"]
  }}
}}

Strict schema rules:
- Every field ending in _evidence must be a JSON array of strings.
- weak_subjects, strong_subjects, math_task_capability_profile.common_error_families, and math_task_capability_profile.capability_evidence must be JSON arrays of strings.
- common_error_families and capability_evidence must be inside math_task_capability_profile, not top-level.
- Do not return a string where an array is required.
- Keep each string short enough for the full object to fit in one response.
"""
    return _chat_and_parse_with_retry(
        llm,
        prompt,
        lambda parsed: _parse_student_model(parsed, student, hachimi_match),
        "StudentModel",
    )


def map_student_model_to_internal_signals(
    student_model: StudentModel,
    llm: OpenAICompatClient | None,
) -> StudentInternalSignals:
    if llm is None:
        capability = student_model.math_task_capability_profile
        return StudentInternalSignals(
            efficacy_signal=student_model.self_efficacy_analysis.efficacy_belief_description,
            srl_fragility_signal=student_model.srl_analysis.primary_srl_vulnerability,
            control_signal=student_model.control_value_analysis.control_appraisal_description,
            value_signal=student_model.control_value_analysis.value_appraisal_description,
            directness_signal=(
                f"{student_model.response_directness_description}; "
                f"guessing_tendency={capability.guessing_tendency}; format_discipline={capability.format_discipline}"
            ),
        )
    prompt = f"""
Map this full StudentModel into compact internal signals for downstream state resolution.
The signals must be short, concrete, and usable in generation boundaries.

StudentModel:
{_compact_json(asdict(student_model))}

Return JSON with:
- efficacy_signal
- srl_fragility_signal
- control_signal
- value_signal
- directness_signal
"""
    def parse(parsed: dict[str, Any]) -> StudentInternalSignals:
        return StudentInternalSignals(
            efficacy_signal=_non_empty(parsed.get("efficacy_signal"), "efficacy_signal"),
            srl_fragility_signal=_non_empty(parsed.get("srl_fragility_signal"), "srl_fragility_signal"),
            control_signal=_non_empty(parsed.get("control_signal"), "control_signal"),
            value_signal=_non_empty(parsed.get("value_signal"), "value_signal"),
            directness_signal=_non_empty(parsed.get("directness_signal"), "directness_signal"),
        )

    return _chat_and_parse_with_retry(llm, prompt, parse, "StudentInternalSignals")


def build_problem_profile(question: EediStaticQuestion, llm: OpenAICompatClient | None) -> ProblemRequirementProfile:
    if llm is None:
        return ProblemRequirementProfile(
            question_id=question.question_id,
            subject_path=question.subject_names,
            prerequisite_knowledge=[question.subject_leaf],
            operation_complexity="medium",
            operation_complexity_justification="dry-run default for EEDI diagnostic item",
            abstraction_level="medium",
            abstraction_level_justification="dry-run default from subject label",
            knowledge_integration_demand="single_topic",
            representation_shift_required="text_to_option",
            response_format_demand="choose_one_of_1_2_3_4",
            guessability="medium",
            likely_traps=["surface option matching", "calculation slip"],
            notes=["dry-run profile"],
            answer_space=["1", "2", "3", "4"],
        )

    prompt = f"""
Build a third-person ProblemRequirementProfile for this EEDI-static 4-option math item from the attached image only.
Do not use the correct answer or item empirical accuracy.
Do not identify the correct option, compute the final solution, or include answer-determining conclusions.
Describe only what knowledge and representation demands the item places on a student.
The image is the complete current item visible to the student.
Do not rely on any external transcription.

Subject path:
{_compact_json(question.subject_names)}

Return JSON with:
- prerequisite_knowledge: list[str]
- operation_complexity: one of ["low","medium","high"]
- operation_complexity_justification: string
- abstraction_level: one of ["low","medium","high"]
- abstraction_level_justification: string
- knowledge_integration_demand: string
- representation_shift_required: string
- response_format_demand: string
- guessability: one of ["low","medium","high"]
- likely_traps: list[str]
- notes: list[str]. Use only image-visible wording or format notes; do not include the solution.
"""
    def parse(parsed: dict[str, Any]) -> ProblemRequirementProfile:
        return ProblemRequirementProfile(
            question_id=question.question_id,
            subject_path=question.subject_names,
            prerequisite_knowledge=_string_list(parsed.get("prerequisite_knowledge"), "prerequisite_knowledge"),
            operation_complexity=_enum(parsed.get("operation_complexity"), COMPLEXITY, "operation_complexity"),
            operation_complexity_justification=_non_empty(
                parsed.get("operation_complexity_justification"),
                "operation_complexity_justification",
            ),
            abstraction_level=_enum(parsed.get("abstraction_level"), COMPLEXITY, "abstraction_level"),
            abstraction_level_justification=_non_empty(
                parsed.get("abstraction_level_justification"),
                "abstraction_level_justification",
            ),
            knowledge_integration_demand=_non_empty(
                parsed.get("knowledge_integration_demand"),
                "knowledge_integration_demand",
            ),
            representation_shift_required=_non_empty(
                parsed.get("representation_shift_required"),
                "representation_shift_required",
            ),
            response_format_demand=_non_empty(parsed.get("response_format_demand"), "response_format_demand"),
            guessability=_enum(parsed.get("guessability"), COMPLEXITY, "guessability"),
            likely_traps=_string_list(parsed.get("likely_traps"), "likely_traps"),
            notes=_string_list(parsed.get("notes"), "notes"),
            answer_space=["1", "2", "3", "4"],
        )

    return _chat_image_and_parse_with_retry(llm, prompt, question.image_path, parse, "ProblemRequirementProfile")


def build_student_item_interaction_decision(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    profile: ProblemRequirementProfile,
    question: EediStaticQuestion,
    llm: OpenAICompatClient | None,
) -> StudentItemInteractionDecision:
    if llm is None:
        capability = student_model.math_task_capability_profile
        reach = "within_reach" if capability.format_discipline in {"medium", "high"} else "partial_reach"
        correctness = "likely_correct" if student_model.academic_level == "high" else "uncertain"
        return StudentItemInteractionDecision(
            predicted_reachability=reach,
            predicted_correctness_band=correctness,
            likely_outcome="chooses an option with brief reasoning",
            likely_error_family=capability.common_error_families[0],
            confidence_cap="medium",
            explanation_cap="brief",
            decision_rationale=["dry-run interaction decision from capability profile"],
        )

    prompt = f"""
Resolve the student-item interaction in third person from the attached image and state objects.
Do not use current true answer, current correctness, current student choice, or item empirical accuracy.
The image is the complete current item visible to the student.
Do not rely on any external transcription.

StudentModel:
{_compact_json(asdict(student_model))}

StudentInternalSignals:
{_compact_json(asdict(internal_signals))}

ProblemRequirementProfile:
{_compact_json(asdict(profile))}

Return JSON with:
- predicted_reachability: one of ["below_reach","partial_reach","within_reach"]
- predicted_correctness_band: one of ["likely_correct","uncertain","likely_wrong"]
- likely_outcome: string
- likely_error_family: string
- confidence_cap: one of ["low","medium","high"]
- explanation_cap: one of ["none","brief","partial","complete"]
- decision_rationale: list[str]
"""
    def parse(parsed: dict[str, Any]) -> StudentItemInteractionDecision:
        return StudentItemInteractionDecision(
            predicted_reachability=_enum(parsed.get("predicted_reachability"), REACHABILITY, "predicted_reachability"),
            predicted_correctness_band=_enum(
                parsed.get("predicted_correctness_band"),
                CORRECTNESS_BANDS,
                "predicted_correctness_band",
            ),
            likely_outcome=_non_empty(parsed.get("likely_outcome"), "likely_outcome"),
            likely_error_family=_non_empty(parsed.get("likely_error_family"), "likely_error_family"),
            confidence_cap=_enum(parsed.get("confidence_cap"), CONFIDENCE_CAPS, "confidence_cap"),
            explanation_cap=_enum(parsed.get("explanation_cap"), EXPLANATION_CAPS, "explanation_cap"),
            decision_rationale=_string_list(parsed.get("decision_rationale"), "decision_rationale"),
        )

    return _chat_image_and_parse_with_retry(llm, prompt, question.image_path, parse, "StudentItemInteractionDecision")


def resolve_item_response_state(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    profile: ProblemRequirementProfile,
    interaction_decision: StudentItemInteractionDecision,
    llm: OpenAICompatClient | None,
) -> ItemResponseState:
    if llm is None:
        if interaction_decision.predicted_reachability == "within_reach":
            familiarity = "familiar"
            reachable = "can_attempt_core"
        elif interaction_decision.predicted_reachability == "partial_reach":
            familiarity = "partial"
            reachable = "can_attempt_surface"
        else:
            familiarity = "weak"
            reachable = "mostly_guessing"
        return ItemResponseState(
            prerequisite_familiarity=familiarity,
            response_state=interaction_decision.predicted_correctness_band,
            reachable_level=reachable,
            error_path=[interaction_decision.likely_error_family],
            commitment_tendency="commit_to_one_option",
            explanation_depth_cap=interaction_decision.explanation_cap,
            response_style_guidance=[
                "answer as a student choosing one diagnostic option",
                "keep explanation short",
            ],
        )

    prompt = f"""
Resolve ItemResponseState from the third-person student model, internal signals, problem profile, and interaction decision.
This is still not the final answer. It is the boundary for generation.
The boundary must describe how this student is likely to express an answer.
Do not write tutoring advice, hints, correct-solution steps, or instructions that reveal how to solve the item.
Do not include verbs like teach, guide, explain, show, reveal, or prompt.
The output should sound like a brief description of student expression style, not advice to the student.

StudentModel:
{_compact_json(asdict(student_model))}

StudentInternalSignals:
{_compact_json(asdict(internal_signals))}

ProblemRequirementProfile:
{_compact_json(asdict(profile))}

StudentItemInteractionDecision:
{_compact_json(asdict(interaction_decision))}

Return JSON with:
- prerequisite_familiarity: string
- response_state: string
- reachable_level: string
- error_path: non-empty list[str]. If the student is likely correct, use a short path such as "no major error path".
- commitment_tendency: string
- explanation_depth_cap: one of ["none","brief","partial","complete"]
- response_style_guidance: list[str]. Only expression-style constraints, such as brevity, hesitation, directness, or example-based wording. Valid examples: "brief and hesitant", "direct but uncertain", "short example-driven phrasing". Invalid examples: "explain the rule", "show the correct method", "guide the student to notice the pattern".
"""

    def parse(parsed: dict[str, Any]) -> ItemResponseState:
        return ItemResponseState(
            prerequisite_familiarity=_non_empty(parsed.get("prerequisite_familiarity"), "prerequisite_familiarity"),
            response_state=_non_empty(parsed.get("response_state"), "response_state"),
            reachable_level=_non_empty(parsed.get("reachable_level"), "reachable_level"),
            error_path=_string_list(parsed.get("error_path"), "error_path"),
            commitment_tendency=_non_empty(parsed.get("commitment_tendency"), "commitment_tendency"),
            explanation_depth_cap=_enum(parsed.get("explanation_depth_cap"), EXPLANATION_CAPS, "explanation_depth_cap"),
            response_style_guidance=_validate_response_style_guidance(
                _string_list(parsed.get("response_style_guidance"), "response_style_guidance")
            ),
        )

    return _chat_and_parse_with_retry(llm, prompt, parse, "ItemResponseState")


def compile_constraints(item_state: ItemResponseState, max_thinking_steps: int = 4) -> ConstraintBundle:
    allow_complete = item_state.explanation_depth_cap == "complete"
    max_sentences = 1 if item_state.explanation_depth_cap == "none" else 8
    return ConstraintBundle(
        must_commit_answer=True,
        allow_complete_explanation=allow_complete,
        max_sentences=max_sentences,
        max_thinking_steps=max_thinking_steps,
        forbid_full_mastery=not allow_complete,
        preferred_error_path=item_state.error_path,
        style_constraints=item_state.response_style_guidance,
        allowed_commitment=item_state.commitment_tendency,
        output_answer_space=["1", "2", "3", "4"],
    )


def check_violation(
    predicted_answer: str,
    student_response: str,
    constraints: ConstraintBundle,
) -> ViolationReport:
    reasons: list[str] = []
    if predicted_answer not in constraints.output_answer_space:
        reasons.append("predicted_answer_outside_answer_space")
    if constraints.must_commit_answer and not predicted_answer:
        reasons.append("missing_committed_answer")
    if not student_response.strip():
        reasons.append("empty_student_response")
    if _sentence_count(student_response) > constraints.max_sentences:
        reasons.append("too_many_sentences")
    mastery_markers = ["therefore", "in general", "proof", "the theorem", "formally", "we can derive"]
    if constraints.forbid_full_mastery and any(marker in student_response.lower() for marker in mastery_markers):
        reasons.append("overly_masterful_explanation")
    severity = "high" if any(reason in reasons for reason in ["predicted_answer_outside_answer_space", "missing_committed_answer"]) else "medium"
    if not reasons:
        return ViolationReport(has_violation=False, reasons=[], severity="low")
    return ViolationReport(has_violation=True, reasons=reasons, severity=severity)


def tighten_constraints(constraints: ConstraintBundle) -> ConstraintBundle:
    return replace(
        constraints,
        allow_complete_explanation=False,
        forbid_full_mastery=True,
        style_constraints=constraints.style_constraints
        + [f"regenerate within {constraints.max_sentences} sentence(s), without a full solution proof"],
    )


def _generation_prompt(
    question: EediStaticQuestion,
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    interaction_decision: StudentItemInteractionDecision,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    retry_instruction: str = "",
) -> str:
    return f"""
Generate the student's current answer for this EEDI-static 4-option diagnostic item.
Respect ConstraintBundle.max_sentences.
Keep the answer brief and student-like.
Do not write a full solution proof.
Use the attached image as the only current item content.
Do not rely on any external transcription.

Allowed information:
- StudentModel from non-test history
- StudentInternalSignals
- ProblemRequirementProfile from current item image and subject labels
- StudentItemInteractionDecision
- ItemResponseState
- ConstraintBundle

Forbidden information:
- true current AnswerValue
- true current IsCorrect
- current CorrectAnswer
- future responses or evaluation labels
- item empirical accuracy

StudentModel:
{_compact_json(asdict(student_model))}

StudentInternalSignals:
{_compact_json(asdict(internal_signals))}

ProblemRequirementProfile:
{_compact_json(asdict(problem_profile))}

StudentItemInteractionDecision:
{_compact_json(asdict(interaction_decision))}

ItemResponseState:
{_compact_json(asdict(item_state))}

ConstraintBundle:
{_compact_json(asdict(constraints))}

{retry_instruction}

Return JSON with:
- predicted_answer: one of "1","2","3","4"
- student_response: short student-style response within ConstraintBundle.max_sentences, not a full solution proof
"""


def _call_generator(
    question: EediStaticQuestion,
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    interaction_decision: StudentItemInteractionDecision,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    llm: OpenAICompatClient | None,
    retry_instruction: str = "",
) -> tuple[str, str]:
    if llm is None:
        choices = ["1", "2", "3", "4"]
        idx = (
            int(question.question_id)
            + len(student_model.weak_subjects)
            + len(interaction_decision.likely_error_family)
        ) % len(choices)
        predicted_answer = choices[idx]
        return predicted_answer, f"I think it is option {predicted_answer}."

    prompt = _generation_prompt(
        question=question,
        student_model=student_model,
        internal_signals=internal_signals,
        problem_profile=problem_profile,
        interaction_decision=interaction_decision,
        item_state=item_state,
        constraints=constraints,
        retry_instruction=retry_instruction,
    )
    parsed = llm.chat_json_with_image(SYSTEM_JSON, prompt, question.image_path)
    try:
        return _choice(parsed.get("predicted_answer"), "predicted_answer"), _non_empty(
            parsed.get("student_response"),
            "student_response",
        )
    except ValueError as exc:
        repair_prompt = (
            prompt
            + "\n\nGeneration correction:\n"
            + f"Your previous JSON violated the schema: {exc}.\n"
            + "Regenerate from scratch. predicted_answer must be exactly one of 1, 2, 3, or 4. "
            + f"student_response must be within {constraints.max_sentences} sentence(s).\n"
        )
        parsed = llm.chat_json_with_image(SYSTEM_JSON, repair_prompt, question.image_path)
        return _choice(parsed.get("predicted_answer"), "predicted_answer"), _non_empty(
            parsed.get("student_response"),
            "student_response",
        )


def generate_prediction(
    student: EediStaticStudent,
    question: EediStaticQuestion,
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    interaction_decision: StudentItemInteractionDecision,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    llm: OpenAICompatClient | None,
    max_generation_attempts: int = 4,
) -> Prediction:
    if max_generation_attempts < 1:
        raise ValueError("max_generation_attempts must be >= 1")

    final_constraints = constraints
    retry_instruction = ""
    violation = ViolationReport(has_violation=False, reasons=[], severity="low")
    violation_history: list[str] = []

    for attempt_idx in range(max_generation_attempts):
        predicted_answer, student_response = _call_generator(
            question=question,
            student_model=student_model,
            internal_signals=internal_signals,
            problem_profile=problem_profile,
            interaction_decision=interaction_decision,
            item_state=item_state,
            constraints=final_constraints,
            llm=llm,
            retry_instruction=retry_instruction,
        )
        violation = check_violation(predicted_answer, student_response, final_constraints)
        if not violation.has_violation:
            return Prediction(
                student_id=student.student_id,
                question_id=question.question_id,
                predicted_answer=predicted_answer,
                student_response=student_response,
                student_model=student_model,
                internal_signals=internal_signals,
                problem_profile=problem_profile,
                interaction_decision=interaction_decision,
                response_state=item_state,
                constraint_bundle=final_constraints,
                violation_report=violation,
                retry_count=attempt_idx,
            )

        violation_history.append(",".join(violation.reasons))
        final_constraints = tighten_constraints(constraints)
        retry_instruction = (
            "Previous output violated constraints: "
            f"{', '.join(violation.reasons)}. "
            f"Regenerate from scratch. Attempt {attempt_idx + 2}/{max_generation_attempts}. "
            f"predicted_answer must be one of 1, 2, 3, 4. "
            f"student_response must be within {final_constraints.max_sentences} sentence(s), "
            "brief, and not a full solution proof."
        )

    raise ValueError(
        "generation still violates constraints after "
        f"{max_generation_attempts} attempt(s): {violation}; history={violation_history}"
    )
