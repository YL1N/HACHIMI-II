from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from typing import Any

from .data_loading import ANSWER_SPACE, EnemStaticQuestion, EnemStaticStudent, summarize_history
from .llm_client import OpenAICompatClient


SYSTEM_JSON = (
    "You are a careful educational simulation component. "
    "Return exactly one JSON object. Do not include markdown. "
    "Do not use hidden target labels, current test labels, or future student answers."
)

LEVELS = {"not_observed", "very_low", "low", "medium", "high"}
SIGNAL_LEVELS = {"low", "medium", "high"}
REACHABILITY = {"below_reach", "partial_reach", "within_reach"}
CORRECTNESS_BANDS = {"likely_correct", "uncertain", "likely_wrong"}
EXPLANATION_CAPS = {"none", "brief", "partial", "complete"}


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
class ScienceTaskCapabilityProfile:
    scientific_concept_recall: str
    phenomenon_explanation: str
    mechanism_reasoning: str
    data_evidence_interpretation: str
    model_representation_transfer: str
    scientific_inquiry_reasoning: str
    science_technology_society_reasoning: str
    quantitative_science_reasoning: str
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
    weak_skill_areas: list[str]
    strong_skill_areas: list[str]
    self_efficacy_analysis: SelfEfficacyAnalysis
    srl_analysis: SRLAnalysis
    control_value_analysis: ControlValueAnalysis
    engagement_level_tendency: str
    engagement_evidence: list[str]
    response_directness_description: str
    response_directness_evidence: list[str]
    raw_summary: str
    domain_anchor_profile_summary: str
    domain_anchor_profile_evidence: list[str]
    science_task_capability_profile: ScienceTaskCapabilityProfile
    matched_hachimi_id: str | None = None
    hachimi_profile_card: dict[str, Any] | None = None
    hachimi_match_evidence: list[str] | None = None
    hachimi_conflict_evidence: list[str] | None = None
    fusion_rule: str | None = None


@dataclass(frozen=True)
class ProblemRequirementProfile:
    question_id: str
    area: str
    enem_skill_code: str
    enem_skill_summary: str
    content_domain: str
    scientific_practice_demand: str
    core_concept_demand: list[str]
    representation_demand: str
    evidence_reasoning_demand: str
    contextualization_demand: str
    knowledge_integration_demand: str
    response_format_demand: str
    guessability: str
    likely_traps: list[str]
    answer_space: list[str]
    notes: list[str]


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


def _compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _non_empty(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _string_list(value: Any, field_name: str, allow_empty: bool = False) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    out = [str(item).strip() for item in value if str(item).strip()]
    if not out and not allow_empty:
        raise ValueError(f"{field_name} cannot be empty")
    return out


def _enum(value: Any, allowed: set[str], field_name: str) -> str:
    text = str(value or "").strip()
    if text in allowed:
        return text
    lower = {candidate.lower(): candidate for candidate in allowed}
    if text.lower() in lower:
        return lower[text.lower()]
    raise ValueError(f"invalid {field_name}: {text!r}; allowed={sorted(allowed)}")


def _level_from_accuracy(value: float) -> str:
    if value < 0.25:
        return "very_low"
    if value < 0.45:
        return "low"
    if value < 0.65:
        return "medium"
    return "high"


def _science_profile_from_history(student: EnemStaticStudent) -> ScienceTaskCapabilityProfile:
    summary = summarize_history(student)
    level = _level_from_accuracy(float(summary["history_accuracy"]))
    competency_accuracy = dict(summary["competency_accuracy"])
    weakest = sorted(competency_accuracy.items(), key=lambda item: (item[1], item[0]))[:3]
    strongest = sorted(competency_accuracy.items(), key=lambda item: (-item[1], item[0]))[:3]
    error_families = [f"weak_{name}" for name, _ in weakest] or ["uncertain_science_reasoning"]
    evidence = [
        f"history_accuracy={summary['history_accuracy']:.3f}",
        f"strongest={strongest}",
        f"weakest={weakest}",
        f"blank_or_invalid_count={summary['blank_or_invalid_count']}",
    ]
    return ScienceTaskCapabilityProfile(
        scientific_concept_recall=level,
        phenomenon_explanation=level,
        mechanism_reasoning=level,
        data_evidence_interpretation=level,
        model_representation_transfer=level,
        scientific_inquiry_reasoning=level,
        science_technology_society_reasoning=level,
        quantitative_science_reasoning=level,
        option_elimination="medium" if level in {"medium", "high"} else "low",
        hard_item_persistence="medium" if level in {"medium", "high"} else "low",
        guessing_tendency="low" if level in {"medium", "high"} else "high",
        confidence_calibration="medium",
        format_discipline="high",
        common_error_families=error_families,
        capability_evidence=evidence,
    )


def _default_student_model(student: EnemStaticStudent, hachimi_match: Any | None = None) -> StudentModel:
    summary = summarize_history(student)
    competency_accuracy = dict(summary["competency_accuracy"])
    weakest = [name for name, _ in sorted(competency_accuracy.items(), key=lambda item: (item[1], item[0]))[:3]]
    strongest = [name for name, _ in sorted(competency_accuracy.items(), key=lambda item: (-item[1], item[0]))[:3]]
    if not weakest:
        weakest = ["not_observed"]
    if not strongest:
        strongest = ["not_observed"]
    capability = _science_profile_from_history(student)
    match_card = getattr(hachimi_match, "hachimi_profile_card", None) if hachimi_match else None
    match_id = getattr(hachimi_match, "hachimi_id", None) if hachimi_match else None
    return StudentModel(
        student_id=student.student_id,
        grade="ENEM candidate",
        academic_level=student.ability_level,
        weak_skill_areas=weakest,
        strong_skill_areas=strongest,
        self_efficacy_analysis=SelfEfficacyAnalysis(
            efficacy_belief_description=f"History calibration suggests {student.ability_level} science confidence.",
            efficacy_belief_evidence=[f"history_accuracy={student.history_accuracy:.3f}"],
        ),
        srl_analysis=SRLAnalysis(
            primary_srl_vulnerability=(
                "fragile on science items" if student.ability_level in {"poor", "low"} else "mostly stable"
            ),
            srl_process_evidence=[f"blank_or_invalid_count={summary['blank_or_invalid_count']}"],
        ),
        control_value_analysis=ControlValueAnalysis(
            control_appraisal_description="Control is inferred only from observed calibration answers.",
            value_appraisal_description="ENEM is treated as a high-stakes exam context.",
            control_value_evidence=[student.target_area, student.ability_level],
        ),
        engagement_level_tendency="Constructive" if student.ability_level in {"medium", "high"} else "Active",
        engagement_evidence=["student completed enough ENEM calibration items"],
        response_directness_description="commits to one A-E option with short exam-style expression",
        response_directness_evidence=["ENEM objective-answer format"],
        raw_summary=f"ENEM {student.target_area} calibration profile: {summary}",
        domain_anchor_profile_summary=(
            "HACHIMI profile fused with ENEM science calibration history"
            if hachimi_match
            else "ENEM science calibration history only"
        ),
        domain_anchor_profile_evidence=[f"history_accuracy={student.history_accuracy:.3f}"],
        science_task_capability_profile=capability,
        matched_hachimi_id=match_id,
        hachimi_profile_card=match_card,
        hachimi_match_evidence=getattr(hachimi_match, "match_evidence", None) if hachimi_match else None,
        hachimi_conflict_evidence=getattr(hachimi_match, "conflict_evidence", None) if hachimi_match else None,
        fusion_rule=(
            "ENEM history is primary for science capability; HACHIMI fills learning-style and affective gaps."
            if hachimi_match
            else None
        ),
    )


def _parse_capability(raw: dict[str, Any]) -> ScienceTaskCapabilityProfile:
    return ScienceTaskCapabilityProfile(
        scientific_concept_recall=_enum(raw.get("scientific_concept_recall"), LEVELS, "scientific_concept_recall"),
        phenomenon_explanation=_enum(raw.get("phenomenon_explanation"), LEVELS, "phenomenon_explanation"),
        mechanism_reasoning=_enum(raw.get("mechanism_reasoning"), LEVELS, "mechanism_reasoning"),
        data_evidence_interpretation=_enum(raw.get("data_evidence_interpretation"), LEVELS, "data_evidence_interpretation"),
        model_representation_transfer=_enum(raw.get("model_representation_transfer"), LEVELS, "model_representation_transfer"),
        scientific_inquiry_reasoning=_enum(raw.get("scientific_inquiry_reasoning"), LEVELS, "scientific_inquiry_reasoning"),
        science_technology_society_reasoning=_enum(
            raw.get("science_technology_society_reasoning"),
            LEVELS,
            "science_technology_society_reasoning",
        ),
        quantitative_science_reasoning=_enum(raw.get("quantitative_science_reasoning"), LEVELS, "quantitative_science_reasoning"),
        option_elimination=_enum(raw.get("option_elimination"), LEVELS, "option_elimination"),
        hard_item_persistence=_enum(raw.get("hard_item_persistence"), LEVELS, "hard_item_persistence"),
        guessing_tendency=_enum(raw.get("guessing_tendency"), SIGNAL_LEVELS, "guessing_tendency"),
        confidence_calibration=_non_empty(raw.get("confidence_calibration"), "confidence_calibration"),
        format_discipline=_enum(raw.get("format_discipline"), LEVELS, "format_discipline"),
        common_error_families=_string_list(raw.get("common_error_families"), "common_error_families"),
        capability_evidence=_string_list(raw.get("capability_evidence"), "capability_evidence"),
    )


def _build_student_model_from_parsed(parsed: dict[str, Any], fallback: StudentModel) -> StudentModel:
    if "weak_skill_areas" not in parsed:
        raise ValueError("weak_skill_areas is required")
    if "strong_skill_areas" not in parsed:
        raise ValueError("strong_skill_areas is required")
    if "raw_summary" not in parsed:
        raise ValueError("raw_summary is required")
    if not isinstance(parsed.get("science_task_capability_profile"), dict):
        raise ValueError("science_task_capability_profile must be an object")
    capability = _parse_capability(dict(parsed["science_task_capability_profile"]))
    return replace(
        fallback,
        weak_skill_areas=_string_list(parsed["weak_skill_areas"], "weak_skill_areas"),
        strong_skill_areas=_string_list(parsed["strong_skill_areas"], "strong_skill_areas"),
        raw_summary=_non_empty(parsed["raw_summary"], "raw_summary"),
        science_task_capability_profile=capability,
    )


def _student_model_schema_instruction() -> str:
    return (
        "Allowed capability level values are exactly: high, medium, low, very_low, not_observed. "
        "Do not use blended labels such as variable, mixed, low_to_medium, moderate, or partial. "
        "guessing_tendency must be exactly one of: high, medium, low. "
        "weak_skill_areas and strong_skill_areas must both be non-empty lists."
    )


def build_student_model(
    student: EnemStaticStudent,
    llm: OpenAICompatClient | None,
    hachimi_match: Any | None = None,
) -> StudentModel:
    fallback = _default_student_model(student, hachimi_match)
    if llm is None:
        return fallback
    prompt = f"""
Build a third-person StudentModel for ENEM natural-science static simulation.
Use only non-test calibration history. Do not use current test answers, current correctness, total CN score, or future labels.

The science capability fields must be grounded in ENEM natural-science competencies, NRC/NGSS-style scientific practices, and PISA-style science reasoning.
HACHIMI may fill learning-style, affective, and self-regulation gaps, but ENEM observed history is primary for science capability.

Observed student:
{_compact_json(summarize_history(student))}

Fallback profile:
{_compact_json(asdict(fallback))}

Return JSON with the same top-level fields as Fallback profile.
weak_skill_areas and strong_skill_areas are both required non-empty lists. If the student has no absolute strong area,
choose the strongest relative area observed in calibration history and say that it is a relative strength.
{_student_model_schema_instruction()}
science_task_capability_profile must contain exactly these fields:
scientific_concept_recall, phenomenon_explanation, mechanism_reasoning, data_evidence_interpretation,
model_representation_transfer, scientific_inquiry_reasoning, science_technology_society_reasoning,
quantitative_science_reasoning, option_elimination, hard_item_persistence, guessing_tendency,
confidence_calibration, format_discipline, common_error_families, capability_evidence.
"""
    current_prompt = prompt
    last_error: ValueError | None = None
    for _ in range(4):
        parsed = llm.chat_json(SYSTEM_JSON, current_prompt)
        try:
            return _build_student_model_from_parsed(parsed, fallback)
        except ValueError as exc:
            last_error = exc
            current_prompt = f"""
The previous StudentModel JSON failed schema validation: {exc}

Previous JSON:
{_compact_json(parsed)}

Return one corrected full StudentModel JSON with the same top-level fields as Fallback profile.
Do not use test answers, current correctness, total CN score, or future labels.
{_student_model_schema_instruction()}
If no absolute strong science area is visible, use the strongest relative area from the calibration history.

Fallback profile:
{_compact_json(asdict(fallback))}
"""
    if last_error is not None:
        raise last_error
    raise ValueError("StudentModel generation failed without a validation error")
def map_student_model_to_internal_signals(
    student_model: StudentModel,
    llm: OpenAICompatClient | None,
) -> StudentInternalSignals:
    capability = student_model.science_task_capability_profile
    if llm is None:
        return StudentInternalSignals(
            efficacy_signal=student_model.self_efficacy_analysis.efficacy_belief_description,
            srl_fragility_signal=student_model.srl_analysis.primary_srl_vulnerability,
            control_signal=student_model.control_value_analysis.control_appraisal_description,
            value_signal=student_model.control_value_analysis.value_appraisal_description,
            directness_signal=student_model.response_directness_description,
        )
    prompt = f"""
Map this ENEM science StudentModel into compact internal signals.
Do not add target answer information.

StudentModel:
{_compact_json(asdict(student_model))}

Return JSON with:
efficacy_signal, srl_fragility_signal, control_signal, value_signal, directness_signal.
Capability reference: guessing_tendency={capability.guessing_tendency}, format_discipline={capability.format_discipline}.
"""
    parsed = llm.chat_json(SYSTEM_JSON, prompt)
    return StudentInternalSignals(
        efficacy_signal=_non_empty(parsed.get("efficacy_signal"), "efficacy_signal"),
        srl_fragility_signal=_non_empty(parsed.get("srl_fragility_signal"), "srl_fragility_signal"),
        control_signal=_non_empty(parsed.get("control_signal"), "control_signal"),
        value_signal=_non_empty(parsed.get("value_signal"), "value_signal"),
        directness_signal=_non_empty(parsed.get("directness_signal"), "directness_signal"),
    )


def _default_problem_profile(question: EnemStaticQuestion) -> ProblemRequirementProfile:
    return ProblemRequirementProfile(
        question_id=question.question_id,
        area=question.area,
        enem_skill_code=question.skill_code,
        enem_skill_summary=question.skill_summary,
        content_domain=question.competency_short_name,
        scientific_practice_demand=question.competency_focus,
        core_concept_demand=[question.skill_summary],
        representation_demand="requires reading the item text or image and options",
        evidence_reasoning_demand="unknown from metadata only",
        contextualization_demand="ENEM contextualized natural-science item",
        knowledge_integration_demand="single_or_limited_combination",
        response_format_demand="selection_only",
        guessability="medium",
        likely_traps=["surface-cue option selection", "misreading a graph or context"],
        answer_space=question.answer_space,
        notes=[question.image_context_note],
    )


def _has_question_text(question: EnemStaticQuestion) -> bool:
    return bool(str(question.question_text or "").strip())


def _question_text_block(question: EnemStaticQuestion) -> str:
    if not _has_question_text(question):
        return ""
    return f"""
Translated item text ({question.question_text_language or "unknown"}):
{question.question_text}
"""


def _chat_json_for_question_content(llm: OpenAICompatClient, prompt: str, question: EnemStaticQuestion) -> dict[str, Any]:
    if _has_question_text(question) and question.use_image_with_question_text:
        if not question.image_path:
            raise ValueError(f"question image_path is required when use_image_with_question_text is true: {question.question_id}")
        return llm.chat_json_with_image(SYSTEM_JSON, prompt, question.image_path)
    return (
        llm.chat_json(SYSTEM_JSON, prompt)
        if _has_question_text(question)
        else llm.chat_json_with_image(SYSTEM_JSON, prompt, question.image_path)
    )


def build_problem_profile(
    question: EnemStaticQuestion,
    llm: OpenAICompatClient | None,
) -> ProblemRequirementProfile:
    fallback = _default_problem_profile(question)
    if llm is None:
        return fallback
    if not _has_question_text(question) and not question.image_path:
        raise ValueError(f"question text or image_path is required for LLM problem profiling: {question.question_id}")
    prompt = f"""
Build a third-person ProblemRequirementProfile for this ENEM natural-science multiple-choice item.
Use the provided item content and the official ENEM skill metadata only.
If both translated text and an image are provided, use the translated text as the main language input and the image only for visual details.
Do not solve the item. Do not mention the correct answer or difficulty statistics.

Question metadata:
{_compact_json(asdict(question))}
{_question_text_block(question)}

Return JSON with:
content_domain, scientific_practice_demand, core_concept_demand, representation_demand,
evidence_reasoning_demand, contextualization_demand, knowledge_integration_demand,
guessability, likely_traps, notes.
"""
    parsed = _chat_json_for_question_content(llm, prompt, question)
    return replace(
        fallback,
        content_domain=_non_empty(parsed.get("content_domain", fallback.content_domain), "content_domain"),
        scientific_practice_demand=_non_empty(
            parsed.get("scientific_practice_demand", fallback.scientific_practice_demand),
            "scientific_practice_demand",
        ),
        core_concept_demand=_string_list(parsed.get("core_concept_demand", fallback.core_concept_demand), "core_concept_demand"),
        representation_demand=_non_empty(parsed.get("representation_demand", fallback.representation_demand), "representation_demand"),
        evidence_reasoning_demand=_non_empty(
            parsed.get("evidence_reasoning_demand", fallback.evidence_reasoning_demand),
            "evidence_reasoning_demand",
        ),
        contextualization_demand=_non_empty(
            parsed.get("contextualization_demand", fallback.contextualization_demand),
            "contextualization_demand",
        ),
        knowledge_integration_demand=_non_empty(
            parsed.get("knowledge_integration_demand", fallback.knowledge_integration_demand),
            "knowledge_integration_demand",
        ),
        guessability=_non_empty(parsed.get("guessability", fallback.guessability), "guessability"),
        likely_traps=_string_list(parsed.get("likely_traps", fallback.likely_traps), "likely_traps"),
        notes=_string_list(parsed.get("notes", fallback.notes), "notes", allow_empty=True),
    )


def _interaction_schema_instruction() -> str:
    return (
        "predicted_reachability must be below_reach, partial_reach, or within_reach. "
        "predicted_correctness_band must be likely_correct, uncertain, or likely_wrong. "
        "confidence_cap must be high, medium, or low. "
        "explanation_cap must be none, brief, partial, or complete. "
        "likely_error_family must be a non-empty string; if no error is expected, use no_error_expected. "
        "decision_rationale must be a non-empty list of strings."
    )


def _build_interaction_decision_from_parsed(parsed: dict[str, Any]) -> StudentItemInteractionDecision:
    return StudentItemInteractionDecision(
        predicted_reachability=_enum(parsed.get("predicted_reachability"), REACHABILITY, "predicted_reachability"),
        predicted_correctness_band=_enum(parsed.get("predicted_correctness_band"), CORRECTNESS_BANDS, "predicted_correctness_band"),
        likely_outcome=_non_empty(parsed.get("likely_outcome"), "likely_outcome"),
        likely_error_family=_non_empty(parsed.get("likely_error_family"), "likely_error_family"),
        confidence_cap=_enum(parsed.get("confidence_cap"), SIGNAL_LEVELS, "confidence_cap"),
        explanation_cap=_enum(parsed.get("explanation_cap"), EXPLANATION_CAPS, "explanation_cap"),
        decision_rationale=_string_list(parsed.get("decision_rationale"), "decision_rationale"),
    )


def build_student_item_interaction_decision(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    profile: ProblemRequirementProfile,
    question: EnemStaticQuestion,
    llm: OpenAICompatClient | None,
) -> StudentItemInteractionDecision:
    capability = student_model.science_task_capability_profile
    if llm is None:
        if student_model.academic_level in {"high", "medium"}:
            reach = "within_reach"
            correctness = "likely_correct" if student_model.academic_level == "high" else "uncertain"
        else:
            reach = "partial_reach"
            correctness = "likely_wrong" if student_model.academic_level == "poor" else "uncertain"
        return StudentItemInteractionDecision(
            predicted_reachability=reach,
            predicted_correctness_band=correctness,
            likely_outcome="chooses one A-E option with brief exam-style response",
            likely_error_family=capability.common_error_families[0],
            confidence_cap="medium",
            explanation_cap="brief",
            decision_rationale=["dry-run interaction decision from science capability profile"],
        )
    if not _has_question_text(question) and not question.image_path:
        raise ValueError(f"question text or image_path is required for LLM interaction decision: {question.question_id}")
    prompt = f"""
Resolve the ENEM science student-item interaction in third person.
Use the provided item content and state objects. Do not use current true answer, current correctness, or item empirical accuracy.
If both translated text and an image are provided, use the translated text as the main language input and the image only for visual details.

StudentModel:
{_compact_json(asdict(student_model))}

StudentInternalSignals:
{_compact_json(asdict(internal_signals))}

ProblemRequirementProfile:
{_compact_json(asdict(profile))}
{_question_text_block(question)}

Return JSON with predicted_reachability below_reach|partial_reach|within_reach,
predicted_correctness_band likely_correct|uncertain|likely_wrong,
likely_outcome, likely_error_family, confidence_cap low|medium|high,
explanation_cap none|brief|partial|complete, decision_rationale list[str].
{_interaction_schema_instruction()}
"""
    current_prompt = prompt
    last_error: ValueError | None = None
    for _ in range(4):
        parsed = _chat_json_for_question_content(llm, current_prompt, question)
        try:
            return _build_interaction_decision_from_parsed(parsed)
        except ValueError as exc:
            last_error = exc
            current_prompt = f"""
The previous StudentItemInteractionDecision JSON failed schema validation: {exc}

Previous JSON:
{_compact_json(parsed)}

Return one corrected full JSON object.
Do not use current true answer, current correctness, official gabarito, item empirical accuracy, or future labels.
{_interaction_schema_instruction()}
"""
    if last_error is not None:
        raise last_error
    raise ValueError("StudentItemInteractionDecision generation failed without a validation error")


def resolve_item_response_state(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    profile: ProblemRequirementProfile,
    interaction_decision: StudentItemInteractionDecision,
    llm: OpenAICompatClient | None,
) -> ItemResponseState:
    if llm is None:
        return ItemResponseState(
            prerequisite_familiarity="familiar" if interaction_decision.predicted_reachability == "within_reach" else "partial",
            response_state=interaction_decision.predicted_correctness_band,
            reachable_level=interaction_decision.predicted_reachability,
            error_path=[interaction_decision.likely_error_family],
            commitment_tendency="commit_to_one_option",
            explanation_depth_cap=interaction_decision.explanation_cap,
            response_style_guidance=["brief ENEM-style answer", "commit to one A-E option"],
        )
    prompt = f"""
Resolve ItemResponseState from the ENEM science state objects.
This is not the final answer. It is only the boundary for generation.
Do not reveal how to solve the item.

StudentModel:
{_compact_json(asdict(student_model))}
StudentInternalSignals:
{_compact_json(asdict(internal_signals))}
ProblemRequirementProfile:
{_compact_json(asdict(profile))}
StudentItemInteractionDecision:
{_compact_json(asdict(interaction_decision))}

Return JSON with prerequisite_familiarity, response_state, reachable_level, error_path,
commitment_tendency, explanation_depth_cap none|brief|partial|complete, response_style_guidance.
error_path must be a non-empty list of strings; if no error is expected, use ["no_error_expected"].
response_style_guidance must be a non-empty list of strings.
"""
    current_prompt = prompt
    last_error: ValueError | None = None
    for _ in range(4):
        parsed = llm.chat_json(SYSTEM_JSON, current_prompt)
        try:
            return ItemResponseState(
                prerequisite_familiarity=_non_empty(parsed.get("prerequisite_familiarity"), "prerequisite_familiarity"),
                response_state=_non_empty(parsed.get("response_state"), "response_state"),
                reachable_level=_non_empty(parsed.get("reachable_level"), "reachable_level"),
                error_path=_string_list(parsed.get("error_path"), "error_path"),
                commitment_tendency=_non_empty(parsed.get("commitment_tendency"), "commitment_tendency"),
                explanation_depth_cap=_enum(parsed.get("explanation_depth_cap"), EXPLANATION_CAPS, "explanation_depth_cap"),
                response_style_guidance=_string_list(parsed.get("response_style_guidance"), "response_style_guidance"),
            )
        except ValueError as exc:
            last_error = exc
            current_prompt = f"""
The previous ItemResponseState JSON failed schema validation: {exc}

Previous JSON:
{_compact_json(parsed)}

Return one corrected full JSON object.
Do not reveal how to solve the item.
error_path must be a non-empty list of strings; if no error is expected, use ["no_error_expected"].
explanation_depth_cap must be none, brief, partial, or complete.
response_style_guidance must be a non-empty list of strings.
"""
    if last_error is not None:
        raise last_error
    raise ValueError("ItemResponseState generation failed without a validation error")


def compile_constraints(item_state: ItemResponseState, max_thinking_steps: int = 4) -> ConstraintBundle:
    allow_complete = item_state.explanation_depth_cap == "complete"
    return ConstraintBundle(
        must_commit_answer=True,
        allow_complete_explanation=allow_complete,
        max_sentences=1 if item_state.explanation_depth_cap == "none" else 6,
        max_thinking_steps=max_thinking_steps,
        forbid_full_mastery=not allow_complete,
        preferred_error_path=item_state.error_path,
        style_constraints=item_state.response_style_guidance,
        allowed_commitment=item_state.commitment_tendency,
        output_answer_space=list(ANSWER_SPACE),
    )


def check_violation(predicted_answer: str, student_response: str, constraints: ConstraintBundle) -> ViolationReport:
    reasons: list[str] = []
    if predicted_answer not in constraints.output_answer_space:
        reasons.append("predicted_answer_outside_answer_space")
    if constraints.must_commit_answer and not predicted_answer:
        reasons.append("missing_committed_answer")
    if not student_response.strip():
        reasons.append("empty_student_response")
    if len([part for part in student_response.replace("!", ".").replace("?", ".").split(".") if part.strip()]) > constraints.max_sentences:
        reasons.append("too_many_sentences")
    if not reasons:
        return ViolationReport(has_violation=False, reasons=[], severity="low")
    severity = "high" if "predicted_answer_outside_answer_space" in reasons else "medium"
    return ViolationReport(has_violation=True, reasons=reasons, severity=severity)


def tighten_constraints(constraints: ConstraintBundle) -> ConstraintBundle:
    return replace(
        constraints,
        allow_complete_explanation=False,
        forbid_full_mastery=True,
        max_sentences=1,
        style_constraints=constraints.style_constraints + ["retry with only one short answer"],
    )


def _generation_prompt(
    question: EnemStaticQuestion,
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    interaction_decision: StudentItemInteractionDecision,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    retry_instruction: str = "",
) -> str:
    return f"""
Generate the student's current answer for this ENEM natural-science multiple-choice item.
Use the provided item content as the only current item content.
If the item content is an image, answer the target question identified by the metadata.
If both translated text and an image are provided, use the translated text as the main language input and the image only for figures, graphs, tables, formulas, units, and layout.
Return a brief student-like response, not a full expert solution.

Allowed information: StudentModel from history calibration, StudentInternalSignals,
ProblemRequirementProfile, StudentItemInteractionDecision, ItemResponseState, ConstraintBundle.
Forbidden information: true current answer, true current correctness, official gabarito, item difficulty/statistics.

Question metadata:
{_compact_json(asdict(question))}
{_question_text_block(question)}
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
predicted_answer: one of "A","B","C","D","E"
student_response: short student-style response within ConstraintBundle.max_sentences
"""


def _call_generator(
    question: EnemStaticQuestion,
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
        idx = (int(question.question_id) + len(student_model.weak_skill_areas)) % len(ANSWER_SPACE)
        answer = ANSWER_SPACE[idx]
        return answer, f"I think it is {answer}."
    if not _has_question_text(question) and not question.image_path:
        raise ValueError(f"question text or image_path is required for generation: {question.question_id}")
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
    parsed = (
        llm.chat_json(SYSTEM_JSON, prompt)
        if _has_question_text(question)
        else llm.chat_json_with_image(SYSTEM_JSON, prompt, question.image_path)
    )
    return _non_empty(parsed.get("predicted_answer"), "predicted_answer").upper(), _non_empty(parsed.get("student_response"), "student_response")


def generate_prediction(
    student: EnemStaticStudent,
    question: EnemStaticQuestion,
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    interaction_decision: StudentItemInteractionDecision,
    item_state: ItemResponseState,
    constraints: ConstraintBundle,
    llm: OpenAICompatClient | None,
    max_generation_attempts: int = 4,
) -> Prediction:
    final_constraints = constraints
    retry_instruction = ""
    violation = ViolationReport(False, [], "low")
    for attempt_idx in range(max_generation_attempts):
        predicted_answer, student_response = _call_generator(
            question,
            student_model,
            internal_signals,
            problem_profile,
            interaction_decision,
            item_state,
            final_constraints,
            llm,
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
        final_constraints = tighten_constraints(final_constraints)
        retry_instruction = f"Previous output violated: {violation.reasons}. Regenerate with one A-E answer."
    raise ValueError(f"generation still violates constraints: {violation}")
