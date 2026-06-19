from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .data_loading import (
    LEVEL_NAMES,
    MathAnchorProfile,
    MathTaskCapabilityAnchor,
    PersonaRecord,
    QuestionRecord,
    _normalize_academic_level,
    _to_subject_list,
    load_personas,
    load_questions,
)
from .difficulty_anchor_bank import _latest_rasch_item_map
from .evaluation import (
    _pearson_corr,
    _spearman_corr,
    apply_official_correctness_labels,
)
from .generation import (
    generate_student_answer,
)
from .irt_support import _band_students
from .llm_client import OpenAICompatClient
from .problem_profile import ProblemRequirementProfile, build_problem_requirement_profile
from .response_state import (
    ConstraintBundle,
    ItemResponseState,
    build_default_item_response_state_for_ablation,
    build_format_only_constraints,
    compile_constraints,
    resolve_item_response_state,
)
from .runtime_paths import XES_OUTPUTS_DIR
from .student_item_interaction import (
    StudentItemInteractionDecision,
    build_student_item_interaction_decision,
)
from .student_model import StudentInternalSignals, StudentModel, build_student_model, map_student_model_to_internal_signals
from .persona_anchoring import _load_support_question_profiles
from .rasch_fit import filter_extreme_scores, fit_rasch_jml


@dataclass(frozen=True)
class BenchmarkSettings:
    eligible_question_path: str
    response_csv_path: str
    persona_path: str
    question_path: str
    target_grade: str = "三年级"
    min_student_history: int = 20
    min_student_test: int = 10
    max_students: int = 1000
    history_size: int = 20
    test_size: int = 10
    sampling_seed: int = 42
    strict_same_grade_persona: bool = True
    official_correctness_mode: str = "rules_only"
    max_thinking_steps: int = 12
    persona_source_mode: str = "xes_history_plus_hachimi"
    fixed_cohort_path: str | None = None


@dataclass(frozen=True)
class HistorySummary:
    student_id: str
    total_history_items: int
    history_accuracy: float
    easy_accuracy: float | None
    medium_accuracy: float | None
    hard_accuracy: float | None
    module_accuracy: dict[str, float]
    type_accuracy: dict[str, float]
    answer_format_accuracy: dict[str, float]
    capability_metric_accuracy: dict[str, float]
    history_level: str
    history_level_percentile: float
    within_level_strength: str
    guessed_error_tendencies: list[str]


@dataclass(frozen=True)
class BenchmarkStudent:
    student_id: str
    history: list[tuple[str, bool]]
    test: list[tuple[str, bool]]
    history_summary: HistorySummary
    matched_persona_id: str
    matched_persona_score: float
    enhanced_persona: PersonaRecord
    persona_matcher_version: str = ""
    candidate_persona_ids: list[str] | None = None
    persona_match_evidence: list[str] | None = None
    persona_conflict_evidence: list[str] | None = None
    persona_fusion_rule: str = ""


@dataclass(frozen=True)
class PersonaCandidate:
    rank_score: float
    rank_evidence: list[str]
    rank_conflicts: list[str]
    persona: PersonaRecord


@dataclass(frozen=True)
class PersonaMatch:
    persona: PersonaRecord
    match_score: float
    matcher_version: str
    candidate_persona_ids: list[str]
    match_evidence: list[str]
    conflict_evidence: list[str]
    fusion_rule: str


def loosen_constraint_bundle(
    constraints: ConstraintBundle,
) -> ConstraintBundle:
    return ConstraintBundle(
        must_commit_answer=True,
        allow_complete_explanation=True,
        max_sentences=3,
        max_thinking_steps=max(1, constraints.max_thinking_steps),
        forbid_full_mastery=False,
        preferred_error_path=[],
        style_constraints=[],
        allowed_commitment="high",
    )


def build_default_interaction_decision_for_ablation() -> StudentItemInteractionDecision:
    return StudentItemInteractionDecision(
        predicted_reachability="partial",
        predicted_correctness_band="0.4-0.7",
        likely_outcome="generic partial attempt without task-local learner-state inference",
        likely_error_family="generic_uncertainty",
        confidence_cap="medium",
        explanation_cap="short_reason",
        decision_rationale=[
            "ablation=without_task_local_state",
            "neutral task-format decision; no current-item learner state inferred",
        ],
    )


def _load_json(path: str | Path) -> object:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_eligible_question_rows(path: str | Path) -> list[dict[str, object]]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError("eligible question file must be a JSON list")
    rows = [row for row in payload if isinstance(row, dict)]
    if not rows:
        raise ValueError("eligible question file is empty")
    return rows


def _question_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def _load_fixed_cohort_config(path: str | Path) -> dict[str, object]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("fixed cohort config must be a JSON object")
    test_question_ids = payload.get("test_question_ids")
    if not isinstance(test_question_ids, list) or not test_question_ids:
        raise ValueError("fixed cohort config requires non-empty test_question_ids")
    normalized_test_ids = [str(question_id).strip() for question_id in test_question_ids]
    if any(not question_id for question_id in normalized_test_ids):
        raise ValueError("fixed cohort config contains empty test question id")
    if len(set(normalized_test_ids)) != len(normalized_test_ids):
        raise ValueError("fixed cohort config contains duplicate test question ids")

    students_by_level = payload.get("students_by_level")
    if not isinstance(students_by_level, dict):
        raise ValueError("fixed cohort config requires students_by_level object")
    normalized_students_by_level: dict[str, list[str]] = {}
    seen_students: set[str] = set()
    for level in ("poor", "low", "medium", "high"):
        raw_students = students_by_level.get(level)
        if not isinstance(raw_students, list) or not raw_students:
            raise ValueError(f"fixed cohort config requires non-empty students_by_level.{level}")
        student_ids = [str(student_id).strip() for student_id in raw_students]
        if any(not student_id for student_id in student_ids):
            raise ValueError(f"fixed cohort config contains empty student id in level={level}")
        repeated = seen_students.intersection(student_ids)
        if repeated:
            raise ValueError(f"fixed cohort config contains duplicate students across levels: {sorted(repeated)}")
        seen_students.update(student_ids)
        normalized_students_by_level[level] = student_ids

    history_size = int(payload.get("history_size", 0))
    if history_size <= 0:
        raise ValueError("fixed cohort config requires positive history_size")
    history_policy = str(payload.get("history_policy", "")).strip()
    if history_policy != "non_test_time_order_even_3_segments":
        raise ValueError(
            "fixed cohort config history_policy must be non_test_time_order_even_3_segments"
        )

    return {
        **payload,
        "history_size": history_size,
        "history_policy": history_policy,
        "test_question_ids": normalized_test_ids,
        "students_by_level": normalized_students_by_level,
    }


def _select_fixed_history_attempts(
    attempts: list[tuple[str, bool]],
    test_question_ids: set[str],
    history_size: int,
    history_policy: str,
) -> list[tuple[str, bool]]:
    if history_policy != "non_test_time_order_even_3_segments":
        raise ValueError(f"unsupported fixed history policy: {history_policy}")
    candidates = [
        (question_id, is_correct)
        for question_id, is_correct in attempts
        if question_id not in test_question_ids
    ]
    if len(candidates) < history_size:
        raise ValueError(
            "not enough non-test history attempts: "
            f"required={history_size}, available={len(candidates)}"
        )
    segment_count = 3
    base_take = history_size // segment_count
    remainder = history_size % segment_count
    selected: list[tuple[int, tuple[str, bool]]] = []
    for segment_index in range(segment_count):
        start = segment_index * len(candidates) // segment_count
        end = (segment_index + 1) * len(candidates) // segment_count
        segment = candidates[start:end]
        take_n = base_take + (1 if segment_index < remainder else 0)
        if len(segment) < take_n:
            raise ValueError(
                "history segment is too small for fixed policy: "
                f"segment={segment_index}, required={take_n}, available={len(segment)}"
            )
        selected.extend((start + local_index, row) for local_index, row in enumerate(segment[:take_n]))
    selected.sort(key=lambda item: item[0])
    history = [row for _, row in selected]
    if len(history) != history_size:
        raise ValueError(f"fixed history selection failed: expected={history_size}, got={len(history)}")
    overlap = sorted({question_id for question_id, _ in history}.intersection(test_question_ids), key=_question_sort_key)
    if overlap:
        raise ValueError(f"fixed history overlaps test questions: {overlap}")
    return history


def _iter_first_attempts_by_student(
    response_csv_path: str | Path,
    allowed_question_ids: set[str],
) -> list[tuple[str, list[tuple[str, bool]]]]:
    source = Path(response_csv_path)
    if not source.exists():
        raise FileNotFoundError(f"response csv not found: {source}")

    attempts_by_student: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    seen_question_by_student: dict[str, set[str]] = defaultdict(set)

    with source.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        required = {"uid", "questions", "responses"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError(
                f"response csv missing required columns: expected {required}, got {reader.fieldnames}"
            )
        for row in reader:
            student_id = str(row.get("uid") or "").strip()
            if not student_id:
                raise ValueError("found row with empty uid")
            question_ids = [question_id.strip() for question_id in (row.get("questions") or "").split(",")]
            responses = [response.strip() for response in (row.get("responses") or "").split(",")]
            for question_id, response in zip(question_ids, responses):
                if not question_id or response not in {"0", "1"}:
                    continue
                if question_id not in allowed_question_ids:
                    continue
                if question_id in seen_question_by_student[student_id]:
                    continue
                seen_question_by_student[student_id].add(question_id)
                attempts_by_student[student_id].append((question_id, response == "1"))

    rows = sorted(attempts_by_student.items(), key=lambda item: item[0])
    if not rows:
        raise ValueError("no usable first-attempt rows found for benchmark")
    return rows


def _difficulty_band_from_b_hat(b_hat: float | None) -> str | None:
    if b_hat is None:
        return None
    if b_hat <= -0.5:
        return "easy"
    if b_hat >= 0.5:
        return "hard"
    return "medium"


def _build_question_lookup_with_metadata(
    question_path: str | Path,
    eligible_rows: list[dict[str, object]],
) -> dict[str, QuestionRecord]:
    question_records = load_questions(question_path, skip_image_questions=True)
    lookup = {question.question_id: question for question in question_records}
    rasch_map = _latest_rasch_item_map(XES_OUTPUTS_DIR / "rasch_module_fits")
    enriched: dict[str, QuestionRecord] = {}
    for row in eligible_rows:
        question_id = str(row.get("question_id", "")).strip()
        question = lookup.get(question_id)
        if question is None:
            continue
        rasch_meta = rasch_map.get(question_id, {})
        difficulty_band_raw = str(row.get("difficulty_band", "")).strip()
        difficulty_band = difficulty_band_raw or _difficulty_band_from_b_hat(
            (
                float(row["paper_b_hat"])
                if row.get("paper_b_hat") is not None
                else (
                    float(rasch_meta["b_hat"])
                    if rasch_meta.get("b_hat") is not None
                    else None
                )
            )
        )
        paper_b_hat = None
        if row.get("paper_b_hat") is not None and str(row.get("paper_b_hat")).strip():
            paper_b_hat = float(row["paper_b_hat"])
        elif rasch_meta.get("b_hat") is not None:
            paper_b_hat = float(rasch_meta["b_hat"])
        paper_module_name = str(
            row.get("paper_module_name")
            or row.get("primary_route_module")
            or rasch_meta.get("module_name")
            or ""
        ).strip() or None
        enriched[question_id] = QuestionRecord(
            question_id=question.question_id,
            question_text=question.question_text,
            question_type=question.question_type,
            options=question.options,
            answer=question.answer,
            has_image_marker=question.has_image_marker,
            difficulty_band=difficulty_band,
            paper_slot_id=None,
            paper_module_name=paper_module_name,
            paper_b_hat=paper_b_hat,
        )
    if not enriched:
        raise ValueError("no eligible questions matched question metadata")
    return enriched


def _safe_rate(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    return correct / total


def _score_to_strength(percentile: float) -> str:
    if percentile >= 0.67:
        return "above_level_average"
    if percentile < 0.33:
        return "below_level_average"
    return "near_level_average"


def _guess_error_tendencies(
    answer_format_accuracy: dict[str, float],
    hard_accuracy: float | None,
    medium_accuracy: float | None,
) -> list[str]:
    tendencies: list[str] = []
    fill_acc = answer_format_accuracy.get("fill")
    option_acc = answer_format_accuracy.get("option")
    if fill_acc is not None and option_acc is not None and option_acc - fill_acc >= 0.15:
        tendencies.append("格式精度不足，填空题更容易失分")
    if hard_accuracy is not None and medium_accuracy is not None and hard_accuracy + 0.15 < medium_accuracy:
        tendencies.append("难题稳定性不足，题目变难时正确率下降明显")
    if not tendencies:
        tendencies.append("历史作答中没有单一特别突出的错误趋势")
    return tendencies


def _build_history_summaries(
    student_rows: list[tuple[str, list[tuple[str, bool]]]],
    question_lookup: dict[str, QuestionRecord],
    history_size: int,
    response_csv_path: str | Path,
    fixed_student_levels: dict[str, str] | None = None,
) -> dict[str, HistorySummary]:
    support_question_profiles = _load_support_question_profiles(response_csv_path)
    history_rows = [
        (student_id, attempts[:history_size])
        for student_id, attempts in student_rows
        if len(attempts) >= history_size
    ]
    if fixed_student_levels is None:
        banding = _band_students(
            student_rows=history_rows,
            min_student_unique_items=history_size,
        )
        student_levels = dict(banding.student_level)
    else:
        missing_levels = sorted(
            student_id for student_id, _ in history_rows if student_id not in fixed_student_levels
        )
        if missing_levels:
            raise ValueError(f"missing fixed levels for students: {missing_levels}")
        invalid_levels = sorted(
            {
                level
                for student_id, level in fixed_student_levels.items()
                if student_id in {row_student_id for row_student_id, _ in history_rows}
                and level not in LEVEL_NAMES
            }
        )
        if invalid_levels:
            raise ValueError(f"invalid fixed student levels: {invalid_levels}")
        student_levels = {
            student_id: fixed_student_levels[student_id]
            for student_id, _ in history_rows
        }
    by_level: dict[str, list[tuple[str, float]]] = defaultdict(list)
    raw_scores: dict[str, float] = {}
    for student_id, attempts in history_rows:
        score = sum(1 for _, is_correct in attempts if is_correct) / len(attempts)
        raw_scores[student_id] = score
        level = student_levels[student_id]
        by_level[level].append((student_id, score))

    percentile_by_student: dict[str, float] = {}
    for level in LEVEL_NAMES:
        pairs = sorted(by_level[level], key=lambda item: (item[1], item[0]))
        if not pairs:
            continue
        n = len(pairs)
        for index, (student_id, _) in enumerate(pairs):
            percentile_by_student[student_id] = 0.5 if n == 1 else index / (n - 1)

    summaries: dict[str, HistorySummary] = {}
    for student_id, attempts in history_rows:
        difficulty_total = Counter()
        difficulty_correct = Counter()
        module_total = Counter()
        module_correct = Counter()
        type_total = Counter()
        type_correct = Counter()
        answer_format_total = Counter()
        answer_format_correct = Counter()
        capability_total = Counter()
        capability_correct = Counter()

        correct_n = 0
        for question_id, is_correct in attempts:
            question = question_lookup.get(question_id)
            if question is None:
                continue
            support_profile = support_question_profiles.get(question_id)
            correct_n += int(is_correct)
            if question.difficulty_band:
                difficulty_total[question.difficulty_band] += 1
                if is_correct:
                    difficulty_correct[question.difficulty_band] += 1
            if question.paper_module_name:
                module_total[question.paper_module_name] += 1
                if is_correct:
                    module_correct[question.paper_module_name] += 1
            type_total[question.question_type] += 1
            if is_correct:
                type_correct[question.question_type] += 1
            answer_key = "option" if question.options else "fill"
            answer_format_total[answer_key] += 1
            if is_correct:
                answer_format_correct[answer_key] += 1
            if support_profile is not None:
                active_metrics: list[str] = []
                if support_profile.arithmetic:
                    active_metrics.append("arithmetic")
                if support_profile.application:
                    active_metrics.append("application")
                if support_profile.geometry:
                    active_metrics.append("geometry")
                if support_profile.pattern:
                    active_metrics.append("pattern")
                if support_profile.multi_step:
                    active_metrics.append("multi_step")
                if question.options:
                    active_metrics.append("selection")
                else:
                    active_metrics.append("fill")
                if question.difficulty_band == "hard":
                    active_metrics.append("hard")
                for metric_name in active_metrics:
                    capability_total[metric_name] += 1
                    if is_correct:
                        capability_correct[metric_name] += 1

        module_accuracy = {
            key: module_correct[key] / module_total[key]
            for key in sorted(module_total)
            if module_total[key] > 0
        }
        type_accuracy = {
            key: type_correct[key] / type_total[key]
            for key in sorted(type_total)
            if type_total[key] > 0
        }
        answer_format_accuracy = {
            key: answer_format_correct[key] / answer_format_total[key]
            for key in sorted(answer_format_total)
            if answer_format_total[key] > 0
        }
        capability_metric_accuracy = {
            key: capability_correct[key] / capability_total[key]
            for key in sorted(capability_total)
            if capability_total[key] > 0
        }

        history_level = student_levels[student_id]
        percentile = percentile_by_student[student_id]
        easy_accuracy = _safe_rate(difficulty_correct["easy"], difficulty_total["easy"])
        medium_accuracy = _safe_rate(difficulty_correct["medium"], difficulty_total["medium"])
        hard_accuracy = _safe_rate(difficulty_correct["hard"], difficulty_total["hard"])
        summaries[student_id] = HistorySummary(
            student_id=student_id,
            total_history_items=len(attempts),
            history_accuracy=correct_n / len(attempts),
            easy_accuracy=easy_accuracy,
            medium_accuracy=medium_accuracy,
            hard_accuracy=hard_accuracy,
            module_accuracy=module_accuracy,
            type_accuracy=type_accuracy,
            answer_format_accuracy=answer_format_accuracy,
            capability_metric_accuracy=capability_metric_accuracy,
            history_level=history_level,
            history_level_percentile=percentile,
            within_level_strength=_score_to_strength(percentile),
            guessed_error_tendencies=_guess_error_tendencies(
                answer_format_accuracy=answer_format_accuracy,
                hard_accuracy=hard_accuracy,
                medium_accuracy=medium_accuracy,
            ),
        )
    return summaries


def _history_summary_to_math_anchor(summary: HistorySummary) -> MathAnchorProfile:
    module_hints = []
    for module_name, accuracy in sorted(summary.module_accuracy.items(), key=lambda item: item[1], reverse=True)[:2]:
        module_hints.append(f"{module_name}正确率={accuracy:.3f}")
    error_hints = list(summary.guessed_error_tendencies)
    evidence = [
        f"history_item_count={summary.total_history_items}",
        f"history_accuracy={summary.history_accuracy:.3f}",
        f"history_level_percentile={summary.history_level_percentile:.3f}",
        f"easy_accuracy={'NA' if summary.easy_accuracy is None else f'{summary.easy_accuracy:.3f}'}",
        f"medium_accuracy={'NA' if summary.medium_accuracy is None else f'{summary.medium_accuracy:.3f}'}",
        f"hard_accuracy={'NA' if summary.hard_accuracy is None else f'{summary.hard_accuracy:.3f}'}",
    ]
    evidence.extend(module_hints[:2])
    evidence.extend(error_hints[:2])
    summary_text = (
        "这是一名来自真实 XES 历史作答的三年级学生数学画像："
        f"历史 {summary.total_history_items} 题正确率 {summary.history_accuracy:.3f}，"
        f"在同层学生中处于 {summary.within_level_strength}。"
    )
    return MathAnchorProfile(
        anchor_student_id=summary.student_id,
        support_item_count=summary.total_history_items,
        support_accuracy=summary.history_accuracy,
        support_accuracy_percentile_within_level=summary.history_level_percentile,
        support_level=summary.history_level,
        within_level_strength=summary.within_level_strength,
        easy_accuracy=summary.easy_accuracy,
        medium_accuracy=summary.medium_accuracy,
        hard_accuracy=summary.hard_accuracy,
        summary=summary_text,
        evidence=evidence,
        excluded_question_count=0,
    )


def _level_bucket_from_accuracy(
    accuracy: float | None,
    fallback_level: str,
) -> str:
    fallback_map = {
        "high": "high",
        "medium": "medium",
        "low": "low",
        "poor": "low",
    }
    fallback = fallback_map.get(fallback_level, "medium")
    if accuracy is None:
        return fallback
    if accuracy >= 0.80:
        return "high"
    if accuracy >= 0.55:
        return "medium"
    return "low"


def _history_summary_to_capability_anchor(summary: HistorySummary) -> MathTaskCapabilityAnchor:
    capability_acc = summary.capability_metric_accuracy
    format_acc = summary.answer_format_accuracy
    arithmetic = _level_bucket_from_accuracy(
        accuracy=capability_acc.get("arithmetic"),
        fallback_level=summary.history_level,
    )
    transfer = _level_bucket_from_accuracy(
        accuracy=capability_acc.get("application"),
        fallback_level=summary.history_level,
    )
    multi_step = _level_bucket_from_accuracy(capability_acc.get("multi_step"), summary.history_level)
    geometry = _level_bucket_from_accuracy(capability_acc.get("geometry"), summary.history_level)
    pattern = _level_bucket_from_accuracy(capability_acc.get("pattern"), summary.history_level)
    option_elimination = _level_bucket_from_accuracy(capability_acc.get("selection"), summary.history_level)
    fill_precision = _level_bucket_from_accuracy(capability_acc.get("fill"), summary.history_level)
    hard_persistence = _level_bucket_from_accuracy(capability_acc.get("hard"), summary.history_level)
    guessing = "high"
    if format_acc.get("option") is not None and format_acc.get("fill") is not None:
        gap = format_acc["option"] - format_acc["fill"]
        if gap <= 0.03:
            guessing = "low"
        elif gap < 0.15:
            guessing = "medium"
    evidence = [
        f"history_accuracy={summary.history_accuracy:.3f}",
        f"module_count={len(summary.module_accuracy)}",
        f"type_count={len(summary.type_accuracy)}",
    ]
    for metric_name in sorted(capability_acc):
        evidence.append(f"{metric_name}_accuracy={capability_acc[metric_name]:.3f}")
    evidence.extend(summary.guessed_error_tendencies[:2])
    return MathTaskCapabilityAnchor(
        arithmetic_fluency=arithmetic,
        word_problem_transfer=transfer,
        multi_step_stability=multi_step,
        geometry_intuition=geometry,
        pattern_rule_detection=pattern,
        option_elimination=option_elimination,
        fill_blank_precision=fill_precision,
        hard_item_persistence=hard_persistence,
        guessing_tendency=guessing,
        capability_evidence=evidence,
        support_anchor_ids=[summary.student_id],
        support_level=summary.history_level,
        support_aggregation_size=1,
    )


def _persona_match_score(persona: PersonaRecord, summary: HistorySummary) -> float:
    score = 0.0
    if persona.academic_level == summary.history_level:
        score += 3.0
    elif persona.academic_level in LEVEL_NAMES:
        level_gap = abs(LEVEL_NAMES.index(persona.academic_level) - LEVEL_NAMES.index(summary.history_level))
        score += max(0.0, 1.5 - level_gap)

    math_in_strong = "数学" in persona.strong_subjects
    math_in_weak = "数学" in persona.weak_subjects
    if math_in_strong and summary.history_accuracy >= 0.70:
        score += 2.0
    if math_in_weak and summary.history_accuracy < 0.50:
        score += 2.0
    if not math_in_strong and not math_in_weak and 0.45 <= summary.history_accuracy < 0.75:
        score += 1.0

    if "格式精度不足" in " ".join(summary.guessed_error_tendencies) and math_in_weak:
        score += 0.5
    if summary.within_level_strength == "above_level_average" and math_in_strong:
        score += 0.5
    if summary.within_level_strength == "below_level_average" and math_in_weak:
        score += 0.5
    return score


def _compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _history_summary_to_observed_profile(summary: HistorySummary) -> dict[str, object]:
    return {
        "student_id": summary.student_id,
        "history_size": summary.total_history_items,
        "history_accuracy": summary.history_accuracy,
        "ability_level": summary.history_level,
        "history_level_percentile": summary.history_level_percentile,
        "within_level_strength": summary.within_level_strength,
        "module_accuracy": summary.module_accuracy,
        "type_accuracy": summary.type_accuracy,
        "answer_format_accuracy": summary.answer_format_accuracy,
        "capability_metric_accuracy": summary.capability_metric_accuracy,
        "guessed_error_tendencies": summary.guessed_error_tendencies,
    }


def rank_persona_candidates(
    summary: HistorySummary,
    candidate_personas: list[PersonaRecord],
    top_k: int = 8,
) -> list[PersonaCandidate]:
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    ranked: list[PersonaCandidate] = []
    for persona in candidate_personas:
        score = _persona_match_score(persona, summary)
        math_in_strong = "数学" in persona.strong_subjects
        math_in_weak = "数学" in persona.weak_subjects
        conflicts: list[str] = []
        if summary.history_accuracy < 0.45 and math_in_strong:
            conflicts.append("XES observed math performance is weak but HACHIMI marks mathematics as strong")
        if summary.history_accuracy >= 0.70 and math_in_weak:
            conflicts.append("XES observed math performance is strong but HACHIMI marks mathematics as weak")
        ranked.append(
            PersonaCandidate(
                rank_score=score,
                rank_evidence=[
                    f"ability_level={summary.history_level}, hachimi_academic_level={persona.academic_level}",
                    f"history_accuracy={summary.history_accuracy:.3f}",
                    f"within_level_strength={summary.within_level_strength}",
                ],
                rank_conflicts=conflicts,
                persona=persona,
            )
        )
    ranked.sort(key=lambda candidate: (-candidate.rank_score, candidate.persona.student_id))
    return ranked[:top_k]


def _persona_to_prompt_row(candidate: PersonaCandidate) -> dict[str, object]:
    persona = candidate.persona
    return {
        "persona_id": persona.student_id,
        "rank_score": candidate.rank_score,
        "rank_evidence": candidate.rank_evidence,
        "rank_conflicts": candidate.rank_conflicts,
            "raw_hachimi_persona": {
                "source_raw_persona": persona.raw_persona,
                "student_id": persona.student_id,
                "grade": persona.grade,
                "academic_level": persona.academic_level,
                "strong_subjects": persona.strong_subjects,
                "weak_subjects": persona.weak_subjects,
            "learning_profile_text": persona.learning_profile_text,
            "math_anchor_profile": asdict(persona.math_anchor_profile) if persona.math_anchor_profile else None,
            "math_task_capability_anchor": (
                asdict(persona.math_task_capability_anchor)
                if persona.math_task_capability_anchor
                else None
            ),
        },
    }


def _string_list(value: object, field_name: str, min_len: int = 1) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) < min_len:
        raise ValueError(f"{field_name} must contain at least {min_len} non-empty item(s)")
    return result


def _non_empty_string(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def select_persona_match_with_llm(
    summary: HistorySummary,
    candidates: list[PersonaCandidate],
    llm_client: OpenAICompatClient,
) -> PersonaMatch:
    if not candidates:
        raise ValueError("candidates cannot be empty")
    candidate_by_id = {candidate.persona.student_id: candidate for candidate in candidates}
    if len(candidate_by_id) != len(candidates):
        raise ValueError("candidate persona ids must be unique")

    prompt = f"""
Select the best HACHIMI persona for this XES static student.

Use only the XES observed profile built from non-test history and the candidate HACHIMI profiles below.
Do not use current test answers, current correctness, item empirical accuracy, future answers, or evaluation metrics.

Decision rule:
- XES observed math history is stronger evidence for math capability.
- HACHIMI is an external prior for affect, learning style, self-regulation, expression style, and non-math background.
- Consider the complete raw_hachimi_persona for every candidate. Do not ignore fields just because ranking scores exist.
- If XES and HACHIMI conflict, select the most plausible overall persona and keep the conflict explicit.

xes_observed_profile:
{_compact_json(_history_summary_to_observed_profile(summary))}

candidate_hachimi_profiles:
{_compact_json([_persona_to_prompt_row(candidate) for candidate in candidates])}

Return JSON with:
- selected_persona_id: one of the candidate persona_id values
- match_evidence: non-empty list[str]
- conflict_evidence: list[str]. Use [] only if there is no meaningful conflict.
- fusion_rule: string describing how XES evidence and HACHIMI persona should be fused downstream
"""
    parsed = llm_client.chat_json(
        system_prompt="You are a careful educational profile matching component. Return exactly one JSON object.",
        user_prompt=prompt,
    )
    selected_id = str(parsed.get("selected_persona_id", "")).strip()
    if selected_id not in candidate_by_id:
        raise ValueError(
            "selected_persona_id must be one of "
            f"{sorted(candidate_by_id)}, got {selected_id!r}"
        )
    selected = candidate_by_id[selected_id]
    return PersonaMatch(
        persona=selected.persona,
        match_score=selected.rank_score,
        matcher_version="llm_profile_matcher_v1",
        candidate_persona_ids=[candidate.persona.student_id for candidate in candidates],
        match_evidence=_string_list(parsed.get("match_evidence"), "match_evidence"),
        conflict_evidence=_string_list(parsed.get("conflict_evidence", []), "conflict_evidence", min_len=0),
        fusion_rule=_non_empty_string(parsed.get("fusion_rule"), "fusion_rule"),
    )


def _augment_persona_with_match_context(
    persona: PersonaRecord,
    match: PersonaMatch,
) -> PersonaRecord:
    context_parts = [
        persona.learning_profile_text.strip(),
        "HACHIMI匹配依据：" + "；".join(match.match_evidence[:3]),
        "HACHIMI冲突依据：" + ("；".join(match.conflict_evidence[:3]) if match.conflict_evidence else "无显著冲突"),
        "画像融合规则：" + match.fusion_rule,
    ]
    return PersonaRecord(
        student_id=persona.student_id,
        grade=persona.grade,
        academic_level=persona.academic_level,
        strong_subjects=persona.strong_subjects,
        weak_subjects=persona.weak_subjects,
        learning_profile_text="；".join(part for part in context_parts if part),
        math_anchor_profile=persona.math_anchor_profile,
        math_task_capability_anchor=persona.math_task_capability_anchor,
        raw_persona=persona.raw_persona,
    )


def _build_enhanced_persona(
    summary: HistorySummary,
    matched_persona: PersonaRecord,
    persona_source_mode: str,
) -> PersonaRecord:
    if persona_source_mode == "xes_history_only":
        strong_subjects: list[str] = []
        weak_subjects: list[str] = []
        if summary.history_accuracy >= 0.70:
            strong_subjects = ["数学"]
        elif summary.history_accuracy < 0.45:
            weak_subjects = ["数学"]

        learning_profile_parts = [
            f"真实 XES 历史数学表现：{summary.total_history_items}题，正确率{summary.history_accuracy:.3f}",
            f"同层位置：{summary.within_level_strength}",
        ]
        if summary.easy_accuracy is not None and summary.medium_accuracy is not None and summary.hard_accuracy is not None:
            learning_profile_parts.append(
                f"易中难正确率=({summary.easy_accuracy:.3f}, {summary.medium_accuracy:.3f}, {summary.hard_accuracy:.3f})"
            )
        learning_profile_parts.extend(summary.guessed_error_tendencies[:2])

        return PersonaRecord(
            student_id=summary.student_id,
            grade=matched_persona.grade,
            academic_level=summary.history_level,
            strong_subjects=strong_subjects or ["数学表现接近同层平均"],
            weak_subjects=weak_subjects or ["暂无明确薄弱学科"],
            learning_profile_text="；".join(learning_profile_parts),
            math_anchor_profile=_history_summary_to_math_anchor(summary),
            math_task_capability_anchor=_history_summary_to_capability_anchor(summary),
            raw_persona=matched_persona.raw_persona,
        )

    if persona_source_mode != "xes_history_plus_hachimi":
        raise ValueError(f"unknown persona_source_mode: {persona_source_mode}")

    strong_subjects = [subject for subject in matched_persona.strong_subjects if subject != "数学"]
    weak_subjects = [subject for subject in matched_persona.weak_subjects if subject != "数学"]
    if summary.history_accuracy >= 0.70:
        strong_subjects = ["数学"] + strong_subjects
    elif summary.history_accuracy < 0.45:
        weak_subjects = ["数学"] + weak_subjects
    learning_profile_text = matched_persona.learning_profile_text.strip()
    math_block_parts = [
        f"真实历史数学表现：{summary.total_history_items}题，正确率{summary.history_accuracy:.3f}",
        f"同层位置：{summary.within_level_strength}",
    ]
    if summary.easy_accuracy is not None and summary.medium_accuracy is not None and summary.hard_accuracy is not None:
        math_block_parts.append(
            f"易中难正确率=({summary.easy_accuracy:.3f}, {summary.medium_accuracy:.3f}, {summary.hard_accuracy:.3f})"
        )
    if summary.guessed_error_tendencies:
        math_block_parts.append("；".join(summary.guessed_error_tendencies[:2]))
    math_block = "；".join(math_block_parts)
    merged_learning_profile = learning_profile_text
    if merged_learning_profile:
        merged_learning_profile += "；"
    merged_learning_profile += math_block
    return PersonaRecord(
        student_id=summary.student_id,
        grade=matched_persona.grade,
        academic_level=summary.history_level,
        strong_subjects=strong_subjects,
        weak_subjects=weak_subjects,
        learning_profile_text=merged_learning_profile,
        math_anchor_profile=_history_summary_to_math_anchor(summary),
        math_task_capability_anchor=_history_summary_to_capability_anchor(summary),
        raw_persona=matched_persona.raw_persona,
    )


def _load_candidate_personas(settings: BenchmarkSettings) -> list[PersonaRecord]:
    raw_personas = load_personas(settings.persona_path, limit=None)
    if settings.strict_same_grade_persona:
        candidate_personas = [persona for persona in raw_personas if persona.grade == settings.target_grade]
    else:
        candidate_personas = raw_personas
    if not candidate_personas:
        raise ValueError("no candidate personas available for matching")
    return candidate_personas


def _build_history_only_benchmark_student(
    student_id: str,
    history: list[tuple[str, bool]],
    test: list[tuple[str, bool]],
    summary: HistorySummary,
    target_grade: str,
) -> BenchmarkStudent:
    observed_persona = PersonaRecord(
        student_id=summary.student_id,
        grade=target_grade,
        academic_level=summary.history_level,
        strong_subjects=[],
        weak_subjects=[],
        learning_profile_text="",
    )
    enhanced_persona = _build_enhanced_persona(
        summary=summary,
        matched_persona=observed_persona,
        persona_source_mode="xes_history_only",
    )
    return BenchmarkStudent(
        student_id=student_id,
        history=history,
        test=test,
        history_summary=summary,
        matched_persona_id="",
        matched_persona_score=0.0,
        enhanced_persona=enhanced_persona,
        persona_matcher_version="none_xes_history_only",
        candidate_persona_ids=[],
        persona_match_evidence=[],
        persona_conflict_evidence=[],
        persona_fusion_rule="No HACHIMI-1M prior; StudentModel is built only from generation-visible XES history.",
    )


def _attach_personas_to_rows(
    *,
    selected_rows: list[tuple[str, list[tuple[str, bool]], list[tuple[str, bool]]]],
    history_summaries: dict[str, HistorySummary],
    candidate_personas: list[PersonaRecord],
    persona_source_mode: str,
) -> list[BenchmarkStudent]:
    return attach_personas_to_rows_with_optional_llm(
        selected_rows=selected_rows,
        history_summaries=history_summaries,
        candidate_personas=candidate_personas,
        persona_source_mode=persona_source_mode,
        llm_client=None,
    )


def attach_personas_to_rows_with_optional_llm(
    *,
    selected_rows: list[tuple[str, list[tuple[str, bool]], list[tuple[str, bool]]]],
    history_summaries: dict[str, HistorySummary],
    candidate_personas: list[PersonaRecord],
    persona_source_mode: str,
    llm_client: OpenAICompatClient | None,
    target_grade: str = "",
) -> list[BenchmarkStudent]:
    benchmark_students: list[BenchmarkStudent] = []
    total_selected = len(selected_rows)
    for row_idx, (student_id, history, test) in enumerate(selected_rows, start=1):
        summary = history_summaries.get(student_id)
        if summary is None:
            continue
        if persona_source_mode == "xes_history_only":
            benchmark_students.append(
                _build_history_only_benchmark_student(
                    student_id=student_id,
                    history=history,
                    test=test,
                    summary=summary,
                    target_grade=target_grade,
                )
            )
            continue
        candidates = rank_persona_candidates(summary, candidate_personas, top_k=8)
        if llm_client is None:
            top_candidate = candidates[0]
            match = PersonaMatch(
                persona=top_candidate.persona,
                match_score=top_candidate.rank_score,
                matcher_version="deterministic_profile_ranker_v1",
                candidate_persona_ids=[top_candidate.persona.student_id],
                match_evidence=top_candidate.rank_evidence,
                conflict_evidence=top_candidate.rank_conflicts,
                fusion_rule=(
                    "Deterministic dry-run match only. Real XES HACHIMI matching must use "
                    "llm_profile_matcher_v1 after candidate ranking."
                ),
            )
        else:
            match = select_persona_match_with_llm(summary, candidates, llm_client)
        if (
            llm_client is not None
            and (row_idx == 1 or row_idx % 10 == 0 or row_idx == total_selected)
        ):
            print(
                f"[HACHIMI] completed={row_idx}/{total_selected}",
                flush=True,
            )
        enhanced_persona = _build_enhanced_persona(
            summary=summary,
            matched_persona=_augment_persona_with_match_context(match.persona, match),
            persona_source_mode=persona_source_mode,
        )
        benchmark_students.append(
            BenchmarkStudent(
                student_id=student_id,
                history=history,
                test=test,
                history_summary=summary,
                matched_persona_id=match.persona.student_id,
                matched_persona_score=match.match_score,
                enhanced_persona=enhanced_persona,
                persona_matcher_version=match.matcher_version,
                candidate_persona_ids=match.candidate_persona_ids,
                persona_match_evidence=match.match_evidence,
                persona_conflict_evidence=match.conflict_evidence,
                persona_fusion_rule=match.fusion_rule,
            )
        )
    return benchmark_students


def _summarize_benchmark_students(
    *,
    settings: BenchmarkSettings,
    benchmark_students: list[BenchmarkStudent],
    question_lookup: dict[str, QuestionRecord],
    history_size: int,
    test_size: int,
    extra_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    persona_match_counter = Counter(student.matched_persona_id for student in benchmark_students)
    math_tag_counter = Counter()
    math_tokens = {"数学", "鏁板"}
    for student in benchmark_students:
        math_in_strong = any(token in student.enhanced_persona.strong_subjects for token in math_tokens)
        math_in_weak = any(token in student.enhanced_persona.weak_subjects for token in math_tokens)
        if math_in_strong and math_in_weak:
            math_tag_counter["both"] += 1
        elif math_in_strong:
            math_tag_counter["strong"] += 1
        elif math_in_weak:
            math_tag_counter["weak"] += 1
        else:
            math_tag_counter["neutral"] += 1

    summary: dict[str, object] = {
        "n_benchmark_students": len(benchmark_students),
        "history_size": history_size,
        "test_size": test_size,
        "target_grade": settings.target_grade,
        "eligible_question_count": len(question_lookup),
        "persona_source_mode": settings.persona_source_mode,
        "matched_persona_unique_count": len(persona_match_counter),
        "matched_persona_top10": persona_match_counter.most_common(10),
        "math_subject_tag_counts": dict(math_tag_counter),
        "history_level_counts": dict(
            Counter(student.history_summary.history_level for student in benchmark_students)
        ),
    }
    if extra_summary:
        summary.update(extra_summary)
    return summary


def _build_fixed_common_test_benchmark_students(
    *,
    settings: BenchmarkSettings,
    eligible_question_ids: set[str],
    question_lookup: dict[str, QuestionRecord],
    student_rows: list[tuple[str, list[tuple[str, bool]]]],
    persona_match_llm_client: OpenAICompatClient | None = None,
) -> tuple[list[BenchmarkStudent], dict[str, QuestionRecord], dict[str, object]]:
    if settings.fixed_cohort_path is None:
        raise ValueError("fixed_cohort_path is required")
    fixed_config = _load_fixed_cohort_config(settings.fixed_cohort_path)
    history_size = int(fixed_config["history_size"])
    history_policy = str(fixed_config["history_policy"])
    test_question_ids = [str(question_id) for question_id in fixed_config["test_question_ids"]]
    test_question_set = set(test_question_ids)

    missing_from_eligible = sorted(test_question_set - eligible_question_ids, key=_question_sort_key)
    if missing_from_eligible:
        raise ValueError(f"fixed test questions are not eligible: {missing_from_eligible}")
    missing_from_metadata = sorted(test_question_set - set(question_lookup), key=_question_sort_key)
    if missing_from_metadata:
        raise ValueError(f"fixed test questions missing metadata: {missing_from_metadata}")

    students_by_level = fixed_config["students_by_level"]
    if not isinstance(students_by_level, dict):
        raise ValueError("normalized students_by_level must be dict")
    fixed_student_levels: dict[str, str] = {}
    selected_student_ids: list[str] = []
    for level in ("poor", "low", "medium", "high"):
        raw_students = students_by_level[level]
        if not isinstance(raw_students, list):
            raise ValueError(f"students_by_level.{level} must be list")
        for student_id in raw_students:
            student_text = str(student_id)
            fixed_student_levels[student_text] = level
            selected_student_ids.append(student_text)

    attempts_by_student = {student_id: attempts for student_id, attempts in student_rows}
    missing_students = sorted(set(selected_student_ids) - set(attempts_by_student), key=_question_sort_key)
    if missing_students:
        raise ValueError(f"fixed cohort students missing response rows: {missing_students}")

    selected_rows: list[tuple[str, list[tuple[str, bool]], list[tuple[str, bool]]]] = []
    for student_id in selected_student_ids:
        attempts = attempts_by_student[student_id]
        attempt_map = dict(attempts)
        missing_test = sorted(test_question_set - set(attempt_map), key=_question_sort_key)
        if missing_test:
            raise ValueError(f"student {student_id} is missing fixed test questions: {missing_test}")
        history = _select_fixed_history_attempts(
            attempts=attempts,
            test_question_ids=test_question_set,
            history_size=history_size,
            history_policy=history_policy,
        )
        test = [(question_id, bool(attempt_map[question_id])) for question_id in test_question_ids]
        selected_rows.append((student_id, history, test))

    history_summaries = _build_history_summaries(
        student_rows=[(student_id, history) for student_id, history, _ in selected_rows],
        question_lookup=question_lookup,
        history_size=history_size,
        response_csv_path=settings.response_csv_path,
        fixed_student_levels=fixed_student_levels,
    )
    benchmark_students = attach_personas_to_rows_with_optional_llm(
        selected_rows=selected_rows,
        history_summaries=history_summaries,
        candidate_personas=(
            [] if settings.persona_source_mode == "xes_history_only" else _load_candidate_personas(settings)
        ),
        persona_source_mode=settings.persona_source_mode,
        llm_client=(
            None if settings.persona_source_mode == "xes_history_only" else persona_match_llm_client
        ),
        target_grade=settings.target_grade,
    )
    if len(benchmark_students) != len(selected_student_ids):
        raise ValueError(
            "fixed benchmark student construction incomplete: "
            f"expected={len(selected_student_ids)}, got={len(benchmark_students)}"
        )

    common_question_lookup = {
        question_id: question_lookup[question_id]
        for question_id in sorted(test_question_set, key=_question_sort_key)
    }
    fixed_level_counts = Counter(fixed_student_levels[student_id] for student_id in selected_student_ids)
    summary = _summarize_benchmark_students(
        settings=settings,
        benchmark_students=benchmark_students,
        question_lookup=question_lookup,
        history_size=history_size,
        test_size=len(test_question_ids),
        extra_summary={
            "benchmark_design": "fixed_common_test",
            "fixed_cohort_path": str(settings.fixed_cohort_path),
            "history_policy": history_policy,
            "effective_history_size": history_size,
            "common_test_question_count": len(test_question_ids),
            "common_test_question_ids": test_question_ids,
            "fixed_students_by_level_counts": dict(fixed_level_counts),
            "history_question_overlap_with_test_count": 0,
        },
    )
    return benchmark_students, common_question_lookup, summary


def build_benchmark_students(
    settings: BenchmarkSettings,
    persona_match_llm_client: OpenAICompatClient | None = None,
) -> tuple[list[BenchmarkStudent], dict[str, QuestionRecord], dict[str, object]]:
    eligible_rows = _load_eligible_question_rows(settings.eligible_question_path)
    eligible_question_ids = {str(row["question_id"]) for row in eligible_rows}
    question_lookup = _build_question_lookup_with_metadata(
        question_path=settings.question_path,
        eligible_rows=eligible_rows,
    )
    student_rows = _iter_first_attempts_by_student(
        response_csv_path=settings.response_csv_path,
        allowed_question_ids=eligible_question_ids,
    )
    if settings.fixed_cohort_path:
        return _build_fixed_common_test_benchmark_students(
            settings=settings,
            eligible_question_ids=eligible_question_ids,
            question_lookup=question_lookup,
            student_rows=student_rows,
            persona_match_llm_client=persona_match_llm_client,
        )
    filtered_rows = [
        (student_id, attempts)
        for student_id, attempts in student_rows
        if len(attempts) >= settings.min_student_history + settings.min_student_test
    ]
    if len(filtered_rows) < settings.max_students:
        raise ValueError(
            f"not enough students for benchmark: required={settings.max_students}, available={len(filtered_rows)}"
        )

    history_summaries = _build_history_summaries(
        student_rows=filtered_rows,
        question_lookup=question_lookup,
        history_size=settings.history_size,
        response_csv_path=settings.response_csv_path,
    )
    candidate_personas = (
        [] if settings.persona_source_mode == "xes_history_only" else _load_candidate_personas(settings)
    )

    rng = random.Random(settings.sampling_seed)
    candidate_rows = list(filtered_rows)
    rng.shuffle(candidate_rows)
    chosen_rows = candidate_rows[: settings.max_students]

    benchmark_students: list[BenchmarkStudent] = []
    for student_id, attempts in chosen_rows:
        history = attempts[: settings.history_size]
        test = attempts[settings.history_size : settings.history_size + settings.test_size]
        if len(test) < settings.test_size:
            continue
        summary = history_summaries.get(student_id)
        if summary is None:
            continue
        if settings.persona_source_mode == "xes_history_only":
            benchmark_students.append(
                _build_history_only_benchmark_student(
                    student_id=student_id,
                    history=history,
                    test=test,
                    summary=summary,
                    target_grade=settings.target_grade,
                )
            )
            continue
        candidates = rank_persona_candidates(summary, candidate_personas, top_k=8)
        if persona_match_llm_client is None:
            top_candidate = candidates[0]
            match = PersonaMatch(
                persona=top_candidate.persona,
                match_score=top_candidate.rank_score,
                matcher_version="deterministic_profile_ranker_v1",
                candidate_persona_ids=[top_candidate.persona.student_id],
                match_evidence=top_candidate.rank_evidence,
                conflict_evidence=top_candidate.rank_conflicts,
                fusion_rule=(
                    "Deterministic dry-run match only. Real XES HACHIMI matching must use "
                    "llm_profile_matcher_v1 after candidate ranking."
                ),
            )
        else:
            match = select_persona_match_with_llm(summary, candidates, persona_match_llm_client)
        enhanced_persona = _build_enhanced_persona(
            summary=summary,
            matched_persona=_augment_persona_with_match_context(match.persona, match),
            persona_source_mode=settings.persona_source_mode,
        )
        benchmark_students.append(
            BenchmarkStudent(
                student_id=student_id,
                history=history,
                test=test,
                history_summary=summary,
                matched_persona_id=match.persona.student_id,
                matched_persona_score=match.match_score,
                enhanced_persona=enhanced_persona,
                persona_matcher_version=match.matcher_version,
                candidate_persona_ids=match.candidate_persona_ids,
                persona_match_evidence=match.match_evidence,
                persona_conflict_evidence=match.conflict_evidence,
                persona_fusion_rule=match.fusion_rule,
            )
        )

    if len(benchmark_students) != settings.max_students:
        raise ValueError(
            f"benchmark student construction incomplete: expected={settings.max_students}, got={len(benchmark_students)}"
        )

    persona_match_counter = Counter(student.matched_persona_id for student in benchmark_students)
    math_tag_counter = Counter()
    for student in benchmark_students:
        math_in_strong = "数学" in student.enhanced_persona.strong_subjects
        math_in_weak = "数学" in student.enhanced_persona.weak_subjects
        if math_in_strong and math_in_weak:
            math_tag_counter["both"] += 1
        elif math_in_strong:
            math_tag_counter["strong"] += 1
        elif math_in_weak:
            math_tag_counter["weak"] += 1
        else:
            math_tag_counter["neutral"] += 1

    summary = {
        "n_benchmark_students": len(benchmark_students),
        "history_size": settings.history_size,
        "test_size": settings.test_size,
        "target_grade": settings.target_grade,
        "eligible_question_count": len(question_lookup),
        "persona_source_mode": settings.persona_source_mode,
        "matched_persona_unique_count": len(persona_match_counter),
        "matched_persona_top10": persona_match_counter.most_common(10),
        "math_subject_tag_counts": dict(math_tag_counter),
        "history_level_counts": dict(
            Counter(student.history_summary.history_level for student in benchmark_students)
        ),
    }
    return benchmark_students, question_lookup, summary


def build_problem_profiles_for_questions(
    question_lookup: dict[str, QuestionRecord],
    llm_client: OpenAICompatClient,
) -> dict[str, ProblemRequirementProfile]:
    profiles: dict[str, ProblemRequirementProfile] = {}
    for question in question_lookup.values():
        profile = build_problem_requirement_profile(
            question_text=question.question_text,
            options=question.options,
            question_type=question.question_type,
            llm_client=llm_client,
            enable_difficulty_analysis=False,
            real_difficulty_band=None,
            difficulty_anchor_context=None,
        )
        profiles[question.question_id] = profile
    return profiles


def _internal_signals_to_payload(
    internal_signals: StudentInternalSignals | dict[str, str] | None,
) -> dict[str, str] | None:
    if internal_signals is None:
        return None
    if isinstance(internal_signals, StudentInternalSignals):
        return asdict(internal_signals)
    if isinstance(internal_signals, dict):
        payload = {str(key): str(value) for key, value in internal_signals.items()}
        if not payload:
            raise ValueError("internal_signals dict cannot be empty")
        return payload
    raise TypeError(f"unsupported internal_signals type: {type(internal_signals).__name__}")


def run_single_prediction(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals | dict[str, str] | None,
    question: QuestionRecord,
    problem_profile: ProblemRequirementProfile,
    llm_client: OpenAICompatClient,
    max_thinking_steps: int,
    ablation_mode: str = "full",
) -> dict[str, object]:
    if ablation_mode == "without_task_local_state":
        interaction_decision = build_default_interaction_decision_for_ablation()
        item_state = build_default_item_response_state_for_ablation()
        constraints = build_format_only_constraints(max_thinking_steps=max_thinking_steps)
    else:
        interaction_decision = build_student_item_interaction_decision(
            student_model=student_model,
            profile=problem_profile,
        )
        item_state = resolve_item_response_state(
            student_model=student_model,
            internal_signals=internal_signals,
            profile=problem_profile,
            question_text=question.question_text,
            llm_client=llm_client,
            use_difficulty_aware_prompt=False,
            interaction_decision=interaction_decision,
        )
        constraints = (
            build_format_only_constraints(max_thinking_steps=max_thinking_steps)
            if ablation_mode == "without_behavior_harness"
            else loosen_constraint_bundle(compile_constraints(item_state))
        )
    answer_output = generate_student_answer(
        student_model=student_model,
        internal_signals=internal_signals,
        problem_profile=problem_profile,
        item_state=item_state,
        constraints=constraints,
        interaction_decision=interaction_decision,
        question_id=question.question_id,
        question_text=question.question_text,
        options=question.options,
        response_persona="first",
        max_thinking_steps=max_thinking_steps,
        llm_client=llm_client,
        use_behavior_harness=ablation_mode != "without_behavior_harness",
    )
    return {
        "student_id": student_model.student_id,
        "question_id": question.question_id,
        "question_type": question.question_type,
        "predicted_answer": answer_output.predicted_answer,
        "student_response": answer_output.student_response,
        "gold_answers": question.answer,
        "has_options": bool(question.options),
        "student_model": asdict(student_model),
        "implementation_derived_signals": _internal_signals_to_payload(internal_signals),
        "problem_requirement_profile": asdict(problem_profile),
        "student_item_interaction_decision": (
            asdict(interaction_decision) if interaction_decision is not None else None
        ),
        "item_response_state": asdict(item_state) if item_state is not None else None,
        "constraint_bundle": asdict(constraints) if constraints is not None else None,
        "harness_version": "hachimi_no_difficulty_signal_loose_constraints",
        "method_variant": "state_step",
        "response_persona": "first",
        "difficulty_signal_enabled": False,
        "constraint_profile": "loose",
        "ablation_mode": ablation_mode,
        "behavior_harness_used_in_generation": ablation_mode != "without_behavior_harness",
        "thinking_trace": [asdict(step) for step in answer_output.thinking_trace],
        "thinking_steps_n": len(answer_output.thinking_trace),
    }


def _accuracy_metrics(y_true: list[int], y_pred: list[int]) -> dict[str, float | None]:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("accuracy metrics require aligned non-empty labels")
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)
    n = len(y_true)
    acc = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    tpr = tp / (tp + fn) if (tp + fn) > 0 else None
    tnr = tn / (tn + fp) if (tn + fp) > 0 else None
    balanced_acc = None
    if tpr is not None and tnr is not None:
        balanced_acc = (tpr + tnr) / 2
    mcc_den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn - fp * fn) / mcc_den) if mcc_den > 0 else None
    return {
        "accuracy": acc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "balanced_accuracy": balanced_acc,
        "mcc": mcc,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def _rmse(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or not xs:
        return None
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(xs, ys)) / len(xs))


def _top_bottom_overlap(
    real_map: dict[str, float],
    pred_map: dict[str, float],
    ratio: float,
) -> dict[str, object]:
    overlap_ids = sorted(set(real_map).intersection(pred_map))
    if not overlap_ids:
        return {"k": 0, "top_overlap": None, "bottom_overlap": None}
    k = max(1, int(len(overlap_ids) * ratio))
    real_top = {qid for qid, _ in sorted(real_map.items(), key=lambda item: item[1], reverse=True)[:k]}
    pred_top = {qid for qid, _ in sorted(pred_map.items(), key=lambda item: item[1], reverse=True)[:k]}
    real_bottom = {qid for qid, _ in sorted(real_map.items(), key=lambda item: item[1])[:k]}
    pred_bottom = {qid for qid, _ in sorted(pred_map.items(), key=lambda item: item[1])[:k]}
    return {
        "k": k,
        "top_overlap": len(real_top & pred_top) / k,
        "bottom_overlap": len(real_bottom & pred_bottom) / k,
    }


def _ks_statistic(xs: list[float], ys: list[float]) -> float | None:
    if not xs or not ys:
        return None
    xs_sorted = sorted(xs)
    ys_sorted = sorted(ys)
    grid = sorted(set(xs_sorted + ys_sorted))
    max_gap = 0.0
    for value in grid:
        fx = sum(1 for x in xs_sorted if x <= value) / len(xs_sorted)
        fy = sum(1 for y in ys_sorted if y <= value) / len(ys_sorted)
        max_gap = max(max_gap, abs(fx - fy))
    return max_gap


def _wasserstein_1d(xs: list[float], ys: list[float]) -> float | None:
    if not xs or not ys:
        return None
    xs_sorted = sorted(xs)
    ys_sorted = sorted(ys)
    n = min(len(xs_sorted), len(ys_sorted))
    if n == 0:
        return None
    if len(xs_sorted) != len(ys_sorted):
        def _sample_quantiles(values: list[float], n_q: int) -> list[float]:
            if n_q == 1:
                return [values[len(values) // 2]]
            out: list[float] = []
            for idx in range(n_q):
                pos = idx * (len(values) - 1) / (n_q - 1)
                low = int(math.floor(pos))
                high = int(math.ceil(pos))
                if low == high:
                    out.append(values[low])
                else:
                    frac = pos - low
                    out.append(values[low] * (1 - frac) + values[high] * frac)
            return out
        xs_sorted = _sample_quantiles(xs_sorted, n)
        ys_sorted = _sample_quantiles(ys_sorted, n)
    return sum(abs(x - y) for x, y in zip(xs_sorted, ys_sorted)) / n


def _build_rasch_input_from_records(
    records: list[dict[str, object]],
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    response_rows: list[dict[str, str]] = []
    student_ids = sorted({str(record["student_id"]) for record in records})
    question_ids = sorted({str(record["question_id"]) for record in records})
    for record in records:
        response_rows.append(
            {
                "student_id": str(record["student_id"]),
                "question_id": str(record["question_id"]),
                "is_correct": "1" if bool(record["is_correct"]) else "0",
            }
        )
    return response_rows, student_ids, question_ids


def _fit_rasch_from_binary_records(
    records: list[dict[str, object]],
) -> tuple[dict[str, float], dict[str, float], dict[str, object]]:
    response_rows, _, _ = _build_rasch_input_from_records(records)
    try:
        filtered = filter_extreme_scores(response_rows)
    except ValueError as exc:
        return {}, {}, {
            "n_students_estimation": 0,
            "n_items_estimation": 0,
            "n_responses_estimation": 0,
            "n_students_dropped_extreme": None,
            "n_items_dropped_extreme": None,
            "objective": None,
            "optimization_iterations": 0,
            "optimization_success": False,
            "fit_error": str(exc),
        }
    student_index = {student_id: idx for idx, student_id in enumerate(filtered.student_ids)}
    item_index = {question_id: idx for idx, question_id in enumerate(filtered.item_ids)}
    responses = [
        (
            student_index[row["student_id"]],
            item_index[row["question_id"]],
            int(row["is_correct"]),
        )
        for row in filtered.response_rows
    ]
    theta, b, objective, n_iter, success = fit_rasch_jml(
        responses=responses,
        n_students=len(filtered.student_ids),
        n_items=len(filtered.item_ids),
        max_iter=500,
    )
    theta_map = {student_id: float(theta[idx]) for student_id, idx in student_index.items()}
    b_map = {question_id: float(b[idx]) for question_id, idx in item_index.items()}
    summary = {
        "n_students_estimation": len(filtered.student_ids),
        "n_items_estimation": len(filtered.item_ids),
        "n_responses_estimation": len(filtered.response_rows),
        "n_students_dropped_extreme": len(filtered.dropped_students),
        "n_items_dropped_extreme": len(filtered.dropped_items),
        "objective": objective,
        "optimization_iterations": n_iter,
        "optimization_success": success,
    }
    return theta_map, b_map, summary


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _build_common_test_metrics(records: list[dict[str, object]]) -> dict[str, object]:
    if not records:
        raise ValueError("common test metrics require non-empty records")

    failed_records = [record for record in records if record.get("failure")]
    failure_by_level = {
        level: sum(1 for record in failed_records if str(record.get("history_level", "")) == level)
        for level in LEVEL_NAMES
    }
    by_student: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    by_item: dict[str, list[tuple[int, int]]] = defaultdict(list)
    by_level: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for record in records:
        student_id = str(record["student_id"])
        question_id = str(record["question_id"])
        level = str(record.get("history_level", ""))
        real = int(bool(record["real_is_correct"]))
        pred = int(bool(record["is_correct"]))
        by_student[student_id].append((real, pred, level))
        by_item[question_id].append((real, pred))
        by_level[level].append((real, pred, student_id))

    real_overall = sum(real for rows in by_item.values() for real, _ in rows) / len(records)
    pred_overall = sum(pred for rows in by_item.values() for _, pred in rows) / len(records)
    record_agreement = sum(
        int(real == pred)
        for rows in by_item.values()
        for real, pred in rows
    ) / len(records)

    real_item_acc = {
        question_id: sum(real for real, _ in rows) / len(rows)
        for question_id, rows in by_item.items()
    }
    pred_item_acc = {
        question_id: sum(pred for _, pred in rows) / len(rows)
        for question_id, rows in by_item.items()
    }
    item_ids = sorted(set(real_item_acc).intersection(pred_item_acc), key=_question_sort_key)
    item_real_values = [real_item_acc[question_id] for question_id in item_ids]
    item_pred_values = [pred_item_acc[question_id] for question_id in item_ids]

    real_student_acc = {
        student_id: sum(real for real, _, _ in rows) / len(rows)
        for student_id, rows in by_student.items()
    }
    pred_student_acc = {
        student_id: sum(pred for _, pred, _ in rows) / len(rows)
        for student_id, rows in by_student.items()
    }
    student_consistency = {
        student_id: sum(int(real == pred) for real, pred, _ in rows) / len(rows)
        for student_id, rows in by_student.items()
    }
    student_ids = sorted(set(real_student_acc).intersection(pred_student_acc), key=_question_sort_key)
    student_real_values = [real_student_acc[student_id] for student_id in student_ids]
    student_pred_values = [pred_student_acc[student_id] for student_id in student_ids]

    level_metrics: dict[str, dict[str, object]] = {}
    for level in LEVEL_NAMES:
        rows = by_level.get(level, [])
        if not rows:
            level_metrics[level] = {
                "n_students": 0,
                "n_records": 0,
                "real_accuracy": None,
                "predicted_accuracy": None,
                "accuracy_gap_abs": None,
                "consistency": None,
            }
            continue
        real_accuracy = sum(real for real, _, _ in rows) / len(rows)
        predicted_accuracy = sum(pred for _, pred, _ in rows) / len(rows)
        level_metrics[level] = {
            "n_students": len({student_id for _, _, student_id in rows}),
            "n_records": len(rows),
            "real_accuracy": real_accuracy,
            "predicted_accuracy": predicted_accuracy,
            "accuracy_gap_abs": abs(predicted_accuracy - real_accuracy),
            "consistency": sum(int(real == pred) for real, pred, _ in rows) / len(rows),
        }

    records_per_student = [len(rows) for rows in by_student.values()]
    records_per_item = [len(rows) for rows in by_item.values()]
    return {
        "n_students": len(by_student),
        "n_items": len(by_item),
        "n_records": len(records),
        "n_failed_records": len(failed_records),
        "failure_rate": len(failed_records) / len(records),
        "failure_by_level": failure_by_level,
        "records_per_student_min": min(records_per_student),
        "records_per_student_max": max(records_per_student),
        "records_per_item_min": min(records_per_item),
        "records_per_item_max": max(records_per_item),
        "is_complete_rectangle": (
            len(records) == len(by_student) * len(by_item)
            and len(set(records_per_student)) == 1
            and len(set(records_per_item)) == 1
        ),
        "overall_accuracy": pred_overall,
        "real_overall_accuracy": real_overall,
        "overall_accuracy_gap_abs": abs(pred_overall - real_overall),
        "record_agreement_accuracy": record_agreement,
        "consistency_mean": _mean(list(student_consistency.values())),
        "consistency_by_student": student_consistency,
        "item_accuracy_pearson": _pearson_corr(item_real_values, item_pred_values),
        "item_accuracy_spearman": _spearman_corr(item_real_values, item_pred_values),
        "item_accuracy_mae": _mean(
            [abs(real - pred) for real, pred in zip(item_real_values, item_pred_values)]
        ),
        "student_accuracy_pearson": _pearson_corr(student_real_values, student_pred_values),
        "student_accuracy_spearman": _spearman_corr(student_real_values, student_pred_values),
        "student_accuracy_mae": _mean(
            [abs(real - pred) for real, pred in zip(student_real_values, student_pred_values)]
        ),
        "student_accuracy_bias_mean": _mean(
            [pred - real for real, pred in zip(student_real_values, student_pred_values)]
        ),
        "per_level": level_metrics,
    }


def evaluate_benchmark_run(
    records: list[dict[str, object]],
    benchmark_students: list[BenchmarkStudent],
    question_lookup: dict[str, QuestionRecord],
) -> dict[str, object]:
    if not records:
        raise ValueError("cannot evaluate empty benchmark records")

    y_true = [int(record["real_is_correct"]) for record in records]
    y_pred = [int(bool(record["is_correct"])) for record in records]
    layer1 = _accuracy_metrics(y_true=y_true, y_pred=y_pred)

    real_item_counts = Counter()
    real_item_correct = Counter()
    pred_item_counts = Counter()
    pred_item_correct = Counter()
    real_student_total = Counter()
    real_student_correct = Counter()
    pred_student_total = Counter()
    pred_student_correct = Counter()
    level_records_real: dict[str, list[int]] = defaultdict(list)
    level_records_pred: dict[str, list[int]] = defaultdict(list)

    for record in records:
        question_id = str(record["question_id"])
        student_id = str(record["student_id"])
        real = int(record["real_is_correct"])
        pred = int(bool(record["is_correct"]))
        level = str(record["history_level"])

        real_item_counts[question_id] += 1
        real_item_correct[question_id] += real
        pred_item_counts[question_id] += 1
        pred_item_correct[question_id] += pred

        real_student_total[student_id] += 1
        real_student_correct[student_id] += real
        pred_student_total[student_id] += 1
        pred_student_correct[student_id] += pred

        level_records_real[level].append(real)
        level_records_pred[level].append(pred)

    real_item_acc = {
        question_id: real_item_correct[question_id] / real_item_counts[question_id]
        for question_id in real_item_counts
    }
    pred_item_acc = {
        question_id: pred_item_correct[question_id] / pred_item_counts[question_id]
        for question_id in pred_item_counts
    }
    overlap_qids = sorted(set(real_item_acc).intersection(pred_item_acc))
    real_values = [real_item_acc[qid] for qid in overlap_qids]
    pred_values = [pred_item_acc[qid] for qid in overlap_qids]
    layer2 = {
        "n_items": len(overlap_qids),
        "pearson": _pearson_corr(real_values, pred_values),
        "spearman": _spearman_corr(real_values, pred_values),
        "mae": (
            sum(abs(pred - real) for pred, real in zip(pred_values, real_values)) / len(overlap_qids)
            if overlap_qids
            else None
        ),
        "rmse": _rmse(pred_values, real_values),
        "top_bottom_overlap_10": _top_bottom_overlap(real_item_acc, pred_item_acc, 0.10),
        "top_bottom_overlap_20": _top_bottom_overlap(real_item_acc, pred_item_acc, 0.20),
        "predicted_item_accuracy_vs_full_rasch_b_pearson": _pearson_corr(
            [pred_item_acc[qid] for qid in overlap_qids if question_lookup.get(qid) and question_lookup[qid].paper_b_hat is not None],
            [float(question_lookup[qid].paper_b_hat) for qid in overlap_qids if question_lookup.get(qid) and question_lookup[qid].paper_b_hat is not None],
        ),
        "predicted_item_accuracy_vs_full_rasch_b_spearman": _spearman_corr(
            [pred_item_acc[qid] for qid in overlap_qids if question_lookup.get(qid) and question_lookup[qid].paper_b_hat is not None],
            [float(question_lookup[qid].paper_b_hat) for qid in overlap_qids if question_lookup.get(qid) and question_lookup[qid].paper_b_hat is not None],
        ),
    }

    rasch_real_records = [
        {"student_id": record["student_id"], "question_id": record["question_id"], "is_correct": bool(record["real_is_correct"])}
        for record in records
    ]
    rasch_pred_records = [
        {"student_id": record["student_id"], "question_id": record["question_id"], "is_correct": bool(record["is_correct"])}
        for record in records
    ]
    real_theta, real_b, real_rasch_summary = _fit_rasch_from_binary_records(rasch_real_records)
    pred_theta, pred_b, pred_rasch_summary = _fit_rasch_from_binary_records(rasch_pred_records)
    rasch_overlap_items = sorted(set(real_b).intersection(pred_b))
    rasch_overlap_students = sorted(set(real_theta).intersection(pred_theta))
    layer3 = {
        "rasch_item_n_overlap": len(rasch_overlap_items),
        "rasch_item_b_pearson": _pearson_corr(
            [real_b[qid] for qid in rasch_overlap_items],
            [pred_b[qid] for qid in rasch_overlap_items],
        ),
        "rasch_item_b_spearman": _spearman_corr(
            [real_b[qid] for qid in rasch_overlap_items],
            [pred_b[qid] for qid in rasch_overlap_items],
        ),
        "rasch_item_b_rmse": _rmse(
            [real_b[qid] for qid in rasch_overlap_items],
            [pred_b[qid] for qid in rasch_overlap_items],
        ),
        "rasch_student_n_overlap": len(rasch_overlap_students),
        "rasch_theta_pearson": _pearson_corr(
            [real_theta[sid] for sid in rasch_overlap_students],
            [pred_theta[sid] for sid in rasch_overlap_students],
        ),
        "rasch_theta_spearman": _spearman_corr(
            [real_theta[sid] for sid in rasch_overlap_students],
            [pred_theta[sid] for sid in rasch_overlap_students],
        ),
        "ability_group_monotonic_real": [
            (
                sum(level_records_real[level]) / len(level_records_real[level])
                if level_records_real[level]
                else None
            )
            for level in ("poor", "low", "medium", "high")
        ],
        "ability_group_monotonic_pred": [
            (
                sum(level_records_pred[level]) / len(level_records_pred[level])
                if level_records_pred[level]
                else None
            )
            for level in ("poor", "low", "medium", "high")
        ],
        "real_rasch_summary": real_rasch_summary,
        "pred_rasch_summary": pred_rasch_summary,
    }

    real_student_acc = {
        student_id: real_student_correct[student_id] / real_student_total[student_id]
        for student_id in real_student_total
    }
    pred_student_acc = {
        student_id: pred_student_correct[student_id] / pred_student_total[student_id]
        for student_id in pred_student_total
    }
    overlap_students = sorted(set(real_student_acc).intersection(pred_student_acc))
    layer4 = {
        "n_students": len(overlap_students),
        "student_accuracy_pearson": _pearson_corr(
            [real_student_acc[sid] for sid in overlap_students],
            [pred_student_acc[sid] for sid in overlap_students],
        ),
        "student_accuracy_spearman": _spearman_corr(
            [real_student_acc[sid] for sid in overlap_students],
            [pred_student_acc[sid] for sid in overlap_students],
        ),
        "student_accuracy_ks": _ks_statistic(
            [real_student_acc[sid] for sid in overlap_students],
            [pred_student_acc[sid] for sid in overlap_students],
        ),
        "student_accuracy_wasserstein": _wasserstein_1d(
            [real_student_acc[sid] for sid in overlap_students],
            [pred_student_acc[sid] for sid in overlap_students],
        ),
        "level_group_real_accuracy": {
            level: (
                sum(level_records_real[level]) / len(level_records_real[level])
                if level_records_real[level]
                else None
            )
            for level in LEVEL_NAMES
        },
        "level_group_pred_accuracy": {
            level: (
                sum(level_records_pred[level]) / len(level_records_pred[level])
                if level_records_pred[level]
                else None
            )
            for level in LEVEL_NAMES
        },
    }
    return {
        "layer1_individual_prediction": layer1,
        "layer2_item_difficulty_alignment": layer2,
        "layer3_psychometric_alignment": layer3,
        "layer4_student_difference_alignment": layer4,
        "common_test_metrics": _build_common_test_metrics(records),
    }
