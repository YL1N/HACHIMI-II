from __future__ import annotations

import csv
import json
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

# Unicode escapes keep key handling stable even when terminal codepages differ.
K_ID = "id"
K_GRADE = "\u5e74\u7ea7"
K_ACADEMIC_LEVEL = "\u5b66\u672f\u6c34\u5e73"
K_STRONG_SUBJECTS = "\u64c5\u957f\u79d1\u76ee"
K_WEAK_SUBJECTS = "\u8584\u5f31\u79d1\u76ee"
K_PERSONALITY = "\u4eba\u683c"
K_MENTAL_HEALTH = "\u5fc3\u7406\u5065\u5eb7"

QUESTION_IMAGE_MARKER_RE = re.compile(r"question_\d+-image_\d+", re.IGNORECASE)
QUESTION_IMAGE_FILE_RE = re.compile(r"question_(\d+)-image_\d+\.(png|jpg|jpeg|webp)$", re.IGNORECASE)
FIGURE_REFERENCE_RE = re.compile(
    r"(?:\u5982\u4e0b\u56fe|\u4e0b\u56fe|\u5982\u56fe|\u56fe\u4e2d|\u56fe\u793a|\u89c1\u56fe|\u53f3\u56fe|\u5de6\u56fe)"
)
SPLIT_SUBJECTS_RE = re.compile(r"[,\uff0c\u3001/;|\s]+")
LEARNING_CLAUSE_SPLIT_RE = re.compile(r"[,\uff0c\u3001;\uff1b\u3002\uff01\uff1f!?]+")
LEVEL_NAMES = ("high", "medium", "low", "poor")
STUDENT_ID_FIELDS = ("uid", "student_id", "user_id", "id")
MATH_SALIENT_KEYWORDS = (
    "\u6570\u5b66",
    "\u5b66\u4e60",
    "\u5b66\u4e1a",
    "\u6210\u7ee9",
    "\u8003\u8bd5",
    "\u505a\u9898",
    "\u9898",
    "\u6311\u6218",
    "\u56f0\u96be",
    "\u5931\u8d25",
    "\u9000\u7f29",
    "\u81ea\u4fe1",
    "\u81ea\u5f8b",
    "\u575a\u6301",
    "\u4e3b\u52a8",
    "\u8868\u8fbe",
    "\u6ce8\u610f",
    "\u4e13\u6ce8",
    "\u5206\u5fc3",
    "\u7126\u8651",
    "\u7d27\u5f20",
    "\u538b\u529b",
    "\u8c03\u8282",
    "\u4efb\u52a1",
    "\u5c1d\u8bd5",
    "\u53cd\u9988",
    "\u72ec\u7acb",
)


@dataclass(frozen=True)
class MathAnchorProfile:
    anchor_student_id: str
    support_item_count: int
    support_accuracy: float
    support_accuracy_percentile_within_level: float
    support_level: str
    within_level_strength: str
    easy_accuracy: float | None
    medium_accuracy: float | None
    hard_accuracy: float | None
    summary: str
    evidence: list[str]
    excluded_question_count: int


@dataclass(frozen=True)
class MathTaskCapabilityAnchor:
    arithmetic_fluency: str
    word_problem_transfer: str
    multi_step_stability: str
    geometry_intuition: str
    pattern_rule_detection: str
    option_elimination: str
    fill_blank_precision: str
    hard_item_persistence: str
    guessing_tendency: str
    capability_evidence: list[str]
    support_anchor_ids: list[str]
    support_level: str
    support_aggregation_size: int


@dataclass(frozen=True)
class PersonaRecord:
    student_id: str
    grade: str
    academic_level: str
    strong_subjects: list[str]
    weak_subjects: list[str]
    learning_profile_text: str
    math_anchor_profile: MathAnchorProfile | None = None
    math_task_capability_anchor: MathTaskCapabilityAnchor | None = None
    raw_persona: dict[str, object] | None = None


@dataclass(frozen=True)
class QuestionRecord:
    question_id: str
    question_text: str
    question_type: str
    options: dict[str, str]
    answer: list[str]
    has_image_marker: bool
    difficulty_band: str | None = None
    paper_slot_id: int | None = None
    paper_module_name: str | None = None
    paper_b_hat: float | None = None


@dataclass(frozen=True)
class ItemStats:
    total: int
    correct: int
    accuracy: float


@dataclass(frozen=True)
class ResponseParseReport:
    rows_read: int
    rows_skipped_length_mismatch: int
    events_skipped_invalid: int


@dataclass(frozen=True)
class RealStudentReference:
    question_ids: list[str]
    level_assignment_scope: str
    overall_accuracy: float
    item_accuracy: dict[str, float]
    level_thresholds: dict[str, float]
    student_level_counts: dict[str, int]
    level_overall_accuracy: dict[str, float | None]
    level_item_accuracy: dict[str, dict[str, float]]
    level_n_events: dict[str, int]
    level_n_students_with_selected_events: dict[str, int]
    pass1_parse_report: ResponseParseReport
    pass2_parse_report: ResponseParseReport


def _validate_frozen_selected_row(
    row: object,
    row_index: int,
) -> dict[str, object]:
    if not isinstance(row, dict):
        raise ValueError(
            f"frozen selected question row {row_index} must be object/dict, got {type(row).__name__}"
        )
    return row


def _to_subject_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        return [part for part in SPLIT_SUBJECTS_RE.split(raw) if part]
    return []


def _to_optional_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            f"math_anchor_profile.evidence must be list when present, got {type(value).__name__}"
        )
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_academic_level(raw_level: str) -> str:
    raw_text = (raw_level or "").strip()
    if not raw_text:
        raise ValueError("academic level is empty")
    text = raw_text.lower()

    # Chinese variants from persona source.
    if text.startswith("\u5dee") or "\u540e50%" in text:
        return "poor"
    if text.startswith("\u4f4e") or "\u524d30%\u81f350%" in text:
        return "low"
    # Must be checked before the "top 10%" bucket to avoid medium->high misclassification.
    if text.startswith("\u4e2d") or "\u524d10%\u81f330%" in text:
        return "medium"
    if text.startswith("\u9ad8") or "\u524d10%" in text:
        return "high"

    # English fallback for portability.
    if text.startswith("poor"):
        return "poor"
    if text.startswith("low"):
        return "low"
    if text.startswith("medium"):
        return "medium"
    if text.startswith("high"):
        return "high"

    raise ValueError(f"unrecognized academic level: {raw_level!r}")


def _parse_optional_math_anchor_profile(value: object) -> MathAnchorProfile | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(
            f"math_anchor_profile must be object/dict when present, got {type(value).__name__}"
        )
    anchor_student_id = str(value.get("anchor_student_id", "")).strip()
    if not anchor_student_id:
        raise ValueError("math_anchor_profile.anchor_student_id cannot be empty")
    support_level = _normalize_academic_level(str(value.get("support_level", "")))
    within_level_strength = str(value.get("within_level_strength", "")).strip()
    if within_level_strength not in {
        "above_level_average",
        "near_level_average",
        "below_level_average",
    }:
        raise ValueError(
            "math_anchor_profile.within_level_strength must be one of "
            "above_level_average/near_level_average/below_level_average"
        )
    summary = str(value.get("summary", "")).strip()
    if not summary:
        raise ValueError("math_anchor_profile.summary cannot be empty")
    support_item_count = int(value.get("support_item_count", 0))
    if support_item_count <= 0:
        raise ValueError("math_anchor_profile.support_item_count must be positive")
    support_accuracy = float(value.get("support_accuracy"))
    support_percentile = float(value.get("support_accuracy_percentile_within_level"))
    excluded_question_count = int(value.get("excluded_question_count", 0))

    def _optional_float(field_name: str) -> float | None:
        raw = value.get(field_name)
        if raw is None:
            return None
        return float(raw)

    return MathAnchorProfile(
        anchor_student_id=anchor_student_id,
        support_item_count=support_item_count,
        support_accuracy=support_accuracy,
        support_accuracy_percentile_within_level=support_percentile,
        support_level=support_level,
        within_level_strength=within_level_strength,
        easy_accuracy=_optional_float("easy_accuracy"),
        medium_accuracy=_optional_float("medium_accuracy"),
        hard_accuracy=_optional_float("hard_accuracy"),
        summary=summary,
        evidence=_to_optional_string_list(value.get("evidence")),
        excluded_question_count=excluded_question_count,
    )


def _validate_capability_level(value: object, field_name: str) -> str:
    text = str(value).strip().lower()
    if text not in {"low", "medium", "high"}:
        raise ValueError(f"{field_name} must be one of low/medium/high, got {value!r}")
    return text


def _parse_optional_math_task_capability_anchor(
    value: object,
) -> MathTaskCapabilityAnchor | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(
            "math_task_capability_anchor must be object/dict when present, "
            f"got {type(value).__name__}"
        )

    support_anchor_ids = _to_subject_list(value.get("support_anchor_ids"))
    if not support_anchor_ids:
        raise ValueError("math_task_capability_anchor.support_anchor_ids cannot be empty")

    support_level = _normalize_academic_level(str(value.get("support_level", "")))
    try:
        support_aggregation_size = int(value.get("support_aggregation_size", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "math_task_capability_anchor.support_aggregation_size must be positive int"
        ) from exc
    if support_aggregation_size <= 0:
        raise ValueError("math_task_capability_anchor.support_aggregation_size must be positive")

    capability_evidence = _to_subject_list(value.get("capability_evidence"))
    if not capability_evidence:
        raise ValueError("math_task_capability_anchor.capability_evidence cannot be empty")

    return MathTaskCapabilityAnchor(
        arithmetic_fluency=_validate_capability_level(
            value.get("arithmetic_fluency"),
            "math_task_capability_anchor.arithmetic_fluency",
        ),
        word_problem_transfer=_validate_capability_level(
            value.get("word_problem_transfer"),
            "math_task_capability_anchor.word_problem_transfer",
        ),
        multi_step_stability=_validate_capability_level(
            value.get("multi_step_stability"),
            "math_task_capability_anchor.multi_step_stability",
        ),
        geometry_intuition=_validate_capability_level(
            value.get("geometry_intuition"),
            "math_task_capability_anchor.geometry_intuition",
        ),
        pattern_rule_detection=_validate_capability_level(
            value.get("pattern_rule_detection"),
            "math_task_capability_anchor.pattern_rule_detection",
        ),
        option_elimination=_validate_capability_level(
            value.get("option_elimination"),
            "math_task_capability_anchor.option_elimination",
        ),
        fill_blank_precision=_validate_capability_level(
            value.get("fill_blank_precision"),
            "math_task_capability_anchor.fill_blank_precision",
        ),
        hard_item_persistence=_validate_capability_level(
            value.get("hard_item_persistence"),
            "math_task_capability_anchor.hard_item_persistence",
        ),
        guessing_tendency=_validate_capability_level(
            value.get("guessing_tendency"),
            "math_task_capability_anchor.guessing_tendency",
        ),
        capability_evidence=capability_evidence,
        support_anchor_ids=support_anchor_ids,
        support_level=support_level,
        support_aggregation_size=support_aggregation_size,
    )


def _build_learning_profile_text(persona: dict[str, object], max_chars: int = 360) -> str:
    personality = str(persona.get(K_PERSONALITY, "") or "").strip()
    mental_health = str(persona.get(K_MENTAL_HEALTH, "") or "").strip()
    merged = " ".join(part for part in [personality, mental_health] if part).strip()
    return merged[:max_chars]


def _build_math_salient_learning_profile_text(
    learning_profile_text: str,
    max_chars: int = 240,
) -> str:
    text = str(learning_profile_text or "").strip()
    if not text:
        return ""
    clauses = [
        clause.strip()
        for clause in LEARNING_CLAUSE_SPLIT_RE.split(text)
        if clause.strip()
    ]
    selected: list[str] = []
    for clause in clauses:
        if any(keyword in clause for keyword in MATH_SALIENT_KEYWORDS):
            if clause not in selected:
                selected.append(clause)
    return "；".join(selected)[:max_chars]


def load_personas(path: str | Path, limit: int | None = None) -> list[PersonaRecord]:
    personas: list[PersonaRecord] = []
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"persona file not found: {source}")

    with source.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if limit is not None and len(personas) >= limit:
                break
            if not line.strip():
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid persona json at line {line_no}: {exc}") from exc

            missing_keys = [key for key in [K_ID, K_GRADE, K_ACADEMIC_LEVEL] if key not in row]
            if missing_keys:
                raise ValueError(
                    f"persona line {line_no} missing required keys: {missing_keys}"
                )

            student_id = str(row[K_ID]).strip()
            grade = str(row[K_GRADE]).strip()
            if not student_id or not grade:
                raise ValueError(f"persona line {line_no} has empty id/grade")

            academic_level = _normalize_academic_level(str(row[K_ACADEMIC_LEVEL]))
            strong_subjects = _to_subject_list(row.get(K_STRONG_SUBJECTS))
            weak_subjects = _to_subject_list(row.get(K_WEAK_SUBJECTS))
            learning_profile_text = _build_learning_profile_text(row)
            math_anchor_profile = _parse_optional_math_anchor_profile(
                row.get("math_anchor_profile")
            )
            math_task_capability_anchor = _parse_optional_math_task_capability_anchor(
                row.get("math_task_capability_anchor")
            )

            personas.append(
                PersonaRecord(
                    student_id=student_id,
                    grade=grade,
                    academic_level=academic_level,
                    strong_subjects=strong_subjects,
                    weak_subjects=weak_subjects,
                    learning_profile_text=learning_profile_text,
                    math_anchor_profile=math_anchor_profile,
                    math_task_capability_anchor=math_task_capability_anchor,
                    raw_persona=dict(row),
                )
            )

    if not personas:
        raise ValueError(f"no valid personas loaded from {source}")
    return personas


def _contains_chinese_numeral(text: str, digit_char: str) -> bool:
    return digit_char in text


def _grade_to_ordinal(grade_text: str) -> int | None:
    text = (grade_text or "").strip()
    if not text:
        return None
    # Extract the Arabic-numeral grade level from the grade label.
    match = re.search(r"(\d+)", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None

    # Chinese numerals commonly seen in this dataset.
    mapping = {
        1: ["\u4e00"],
        2: ["\u4e8c", "\u4e24"],
        3: ["\u4e09"],
        4: ["\u56db"],
        5: ["\u4e94"],
        6: ["\u516d"],
        7: ["\u4e03"],
        8: ["\u516b"],
        9: ["\u4e5d"],
    }
    for ordinal, chars in mapping.items():
        if any(_contains_chinese_numeral(text, ch) for ch in chars):
            return ordinal
    return None


def filter_personas_by_grade(
    personas: list[PersonaRecord],
    target_grade: str,
    match_mode: str = "exact",
) -> list[PersonaRecord]:
    target = target_grade.strip()
    if not target:
        raise ValueError("target_grade cannot be empty")

    if match_mode not in {"exact", "ordinal"}:
        raise ValueError(f"match_mode must be 'exact' or 'ordinal', got {match_mode!r}")

    if match_mode == "exact":
        filtered = [persona for persona in personas if persona.grade.strip() == target]
    else:
        target_ord = _grade_to_ordinal(target)
        if target_ord is None:
            raise ValueError(f"unable to parse target_grade ordinal from: {target!r}")
        filtered = []
        for persona in personas:
            ord_value = _grade_to_ordinal(persona.grade)
            if ord_value is None:
                continue
            if ord_value == target_ord:
                filtered.append(persona)

    if not filtered:
        raise ValueError(
            f"no personas matched target_grade={target!r} with match_mode={match_mode!r}"
        )
    return filtered


def sample_personas(
    personas: list[PersonaRecord],
    max_personas: int,
    sampling_mode: str = "stratified",
    seed: int = 42,
) -> list[PersonaRecord]:
    if max_personas <= 0:
        raise ValueError(f"max_personas must be positive, got {max_personas}")
    if sampling_mode not in {"head", "random", "stratified"}:
        raise ValueError(
            f"sampling_mode must be one of head/random/stratified, got {sampling_mode!r}"
        )
    if len(personas) <= max_personas:
        return list(personas)
    if sampling_mode == "head":
        return list(personas[:max_personas])

    rng = random.Random(seed)
    if sampling_mode == "random":
        return rng.sample(personas, max_personas)

    # Stratified round-robin over academic levels to reduce sampling bias.
    level_order = ["high", "medium", "low", "poor", "unknown"]
    buckets: dict[str, list[PersonaRecord]] = defaultdict(list)
    for persona in personas:
        buckets[persona.academic_level].append(persona)
    ordered_levels = [level for level in level_order if buckets.get(level)]
    if not ordered_levels:
        return rng.sample(personas, max_personas)
    for level in ordered_levels:
        rng.shuffle(buckets[level])

    selected: list[PersonaRecord] = []
    while len(selected) < max_personas:
        progressed = False
        for level in ordered_levels:
            if not buckets[level]:
                continue
            selected.append(buckets[level].pop())
            progressed = True
            if len(selected) >= max_personas:
                break
        if not progressed:
            break
    if len(selected) < max_personas:
        selected_set = {p.student_id for p in selected}
        remaining = [persona for persona in personas if persona.student_id not in selected_set]
        selected.extend(rng.sample(remaining, max_personas - len(selected)))
    return selected


def _build_shuffled_full_personas(
    personas: list[PersonaRecord],
    seed: int = 42,
) -> list[PersonaRecord]:
    if not personas:
        return []

    by_level: dict[str, list[tuple[int, PersonaRecord]]] = defaultdict(list)
    for idx, persona in enumerate(personas):
        by_level[persona.academic_level].append((idx, persona))

    shuffled = list(personas)
    for level, indexed_personas in by_level.items():
        if len(indexed_personas) <= 1:
            continue

        level_seed = seed + sum(ord(ch) for ch in level)
        offset = 1 + (level_seed % (len(indexed_personas) - 1))
        donors = [persona for _, persona in indexed_personas]
        rotated_donors = donors[offset:] + donors[:offset]

        for (target_idx, target_persona), donor_persona in zip(indexed_personas, rotated_donors):
            shuffled[target_idx] = replace(
                target_persona,
                strong_subjects=list(donor_persona.strong_subjects),
                weak_subjects=list(donor_persona.weak_subjects),
                learning_profile_text=donor_persona.learning_profile_text,
            )
    return shuffled


def apply_persona_variant(
    personas: list[PersonaRecord],
    persona_variant: str = "full_persona",
    seed: int = 42,
) -> list[PersonaRecord]:
    if persona_variant not in {"full_persona", "level_only", "math_salient", "shuffled_full"}:
        raise ValueError(
            "persona_variant must be one of full_persona/level_only/math_salient/shuffled_full, "
            f"got {persona_variant!r}"
        )
    if persona_variant == "full_persona":
        return list(personas)
    if persona_variant == "math_salient":
        return [
            replace(
                persona,
                learning_profile_text=_build_math_salient_learning_profile_text(
                    persona.learning_profile_text
                ),
            )
            for persona in personas
        ]
    if persona_variant == "shuffled_full":
        return _build_shuffled_full_personas(personas=personas, seed=seed)
    return [
        replace(
            persona,
            strong_subjects=[],
            weak_subjects=[],
            learning_profile_text="",
        )
        for persona in personas
    ]


def _normalize_options(raw_options: object) -> dict[str, str]:
    if raw_options is None:
        return {}
    if not isinstance(raw_options, dict):
        raise ValueError(f"question options must be a dict, got: {type(raw_options).__name__}")
    return {
        str(key).strip(): str(value).strip()
        for key, value in raw_options.items()
        if str(key).strip()
    }


def _normalize_answers(raw_answer: object) -> list[str]:
    if raw_answer is None:
        return []
    if isinstance(raw_answer, list):
        return [str(item).strip() for item in raw_answer if str(item).strip()]
    if isinstance(raw_answer, str):
        text = raw_answer.strip()
        return [text] if text else []
    raise ValueError(f"question answer must be list/str, got: {type(raw_answer).__name__}")


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute percentile on empty values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = max(0.0, min(1.0, p)) * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    ratio = pos - lo
    return sorted_values[lo] * (1 - ratio) + sorted_values[hi] * ratio


def _compute_quartile_thresholds(values: list[float]) -> tuple[float, float, float]:
    if not values:
        raise ValueError("cannot compute quartile thresholds from empty values")
    ordered = sorted(values)
    q25 = _percentile(ordered, 0.25)
    q50 = _percentile(ordered, 0.50)
    q75 = _percentile(ordered, 0.75)
    return q25, q50, q75


def _assign_level_by_quartile(
    accuracy: float,
    q25: float,
    q50: float,
    q75: float,
) -> str:
    if accuracy >= q75:
        return "high"
    if accuracy >= q50:
        return "medium"
    if accuracy >= q25:
        return "low"
    return "poor"


def _resolve_student_id(row: dict[str, str], row_index: int) -> str:
    for key in STUDENT_ID_FIELDS:
        value = str(row.get(key, "") or "").strip()
        if value:
            return value
    return f"row_{row_index}"


def _assign_accuracy_bin(
    accuracy: float,
    q25: float,
    q50: float,
    q75: float,
) -> int:
    if accuracy < q25:
        return 0
    if accuracy < q50:
        return 1
    if accuracy < q75:
        return 2
    return 3


def _sample_representative_questions(
    candidates: list[QuestionRecord],
    item_stats: dict[str, ItemStats],
    target_count: int,
    rng: random.Random,
) -> list[QuestionRecord]:
    if target_count <= 0 or not candidates:
        return []
    if target_count >= len(candidates):
        return list(candidates)

    accuracies = [item_stats[question.question_id].accuracy for question in candidates]
    q25, q50, q75 = _compute_quartile_thresholds(accuracies)
    buckets: dict[int, list[QuestionRecord]] = {0: [], 1: [], 2: [], 3: []}
    for question in candidates:
        accuracy = item_stats[question.question_id].accuracy
        bucket = _assign_accuracy_bin(accuracy, q25, q50, q75)
        buckets[bucket].append(question)
    for bucket_questions in buckets.values():
        rng.shuffle(bucket_questions)

    selected: list[QuestionRecord] = []
    while len(selected) < target_count:
        progressed = False
        for bucket in [0, 1, 2, 3]:
            if not buckets[bucket]:
                continue
            selected.append(buckets[bucket].pop())
            progressed = True
            if len(selected) >= target_count:
                break
        if not progressed:
            break
    return selected[:target_count]


def _sample_evenly_spaced_questions(
    candidates: list[QuestionRecord],
    target_count: int,
) -> list[QuestionRecord]:
    if target_count <= 0 or not candidates:
        return []
    if target_count >= len(candidates):
        return list(candidates)

    selected: list[QuestionRecord] = []
    total = len(candidates)
    for idx in range(target_count):
        pos = int((idx + 0.5) * total / target_count)
        pos = min(total - 1, max(0, pos))
        selected.append(candidates[pos])
    return selected


def _resolve_difficulty_band(
    accuracy: float,
    hard_max_accuracy: float,
    medium_max_accuracy: float,
) -> str:
    if accuracy < hard_max_accuracy:
        return "hard"
    if accuracy <= medium_max_accuracy:
        return "medium"
    return "easy"


def _split_questions_into_difficulty_bands(
    candidates: list[QuestionRecord],
    item_stats: dict[str, ItemStats],
    hard_max_accuracy: float,
    medium_max_accuracy: float,
) -> dict[str, list[QuestionRecord]]:
    if not (0.0 <= hard_max_accuracy <= medium_max_accuracy <= 1.0):
        raise ValueError(
            "difficulty accuracy thresholds must satisfy "
            f"0 <= hard_max_accuracy <= medium_max_accuracy <= 1, got "
            f"{hard_max_accuracy}, {medium_max_accuracy}"
        )

    bands: dict[str, list[QuestionRecord]] = {"hard": [], "medium": [], "easy": []}
    for question in candidates:
        accuracy = item_stats[question.question_id].accuracy
        band = _resolve_difficulty_band(
            accuracy=accuracy,
            hard_max_accuracy=hard_max_accuracy,
            medium_max_accuracy=medium_max_accuracy,
        )
        bands[band].append(question)

    for band_name, band_questions in bands.items():
        bands[band_name] = sorted(
            band_questions,
            key=lambda question: (
                item_stats[question.question_id].accuracy,
                item_stats[question.question_id].total,
                int(question.question_id),
            ),
        )
    return bands


def _collect_question_ids_with_image_assets(questions_path: Path) -> set[str]:
    images_dir = questions_path.parent / "images"
    if not images_dir.exists() or not images_dir.is_dir():
        return set()

    question_ids: set[str] = set()
    for image_path in images_dir.iterdir():
        if not image_path.is_file():
            continue
        match = QUESTION_IMAGE_FILE_RE.fullmatch(image_path.name)
        if not match:
            continue
        question_ids.add(match.group(1))
    return question_ids


def load_questions(
    path: str | Path,
    limit: int | None = None,
    skip_image_questions: bool = True,
) -> list[QuestionRecord]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"question file not found: {source}")
    question_ids_with_image_assets = _collect_question_ids_with_image_assets(source)

    with source.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid question json: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"questions json must be dict, got: {type(data).__name__}")

    records: list[QuestionRecord] = []
    ordered_items = sorted(data.items(), key=lambda kv: int(kv[0]))
    for qid, payload in ordered_items:
        if limit is not None and len(records) >= limit:
            break
        if not isinstance(payload, dict):
            raise ValueError(f"question {qid} payload must be dict")

        question_text = str(payload.get("content", "") or "").strip()
        if not question_text:
            continue

        options = _normalize_options(payload.get("options", {}))
        answers = _normalize_answers(payload.get("answer"))
        question_type = str(payload.get("type", "") or "").strip()
        has_question_image_marker = bool(QUESTION_IMAGE_MARKER_RE.search(question_text))
        has_image_asset = str(qid) in question_ids_with_image_assets
        mentions_figure_reference = bool(FIGURE_REFERENCE_RE.search(question_text))
        has_image_dependency = (
            has_question_image_marker or has_image_asset or mentions_figure_reference
        )
        if skip_image_questions and has_image_dependency:
            continue

        records.append(
            QuestionRecord(
                question_id=str(qid),
                question_text=question_text,
                question_type=question_type,
                options=options,
                answer=answers,
                has_image_marker=has_image_dependency,
            )
        )

    if not records:
        raise ValueError(f"no usable questions loaded from {source}")
    return records


def compute_item_stats(
    response_csv_path: str | Path,
    max_rows: int | None = None,
    strict: bool = False,
) -> tuple[dict[str, ItemStats], ResponseParseReport]:
    source = Path(response_csv_path)
    if not source.exists():
        raise FileNotFoundError(f"response csv not found: {source}")

    totals: defaultdict[str, int] = defaultdict(int)
    corrects: defaultdict[str, int] = defaultdict(int)
    rows_read = 0
    rows_skipped_length_mismatch = 0
    events_skipped_invalid = 0

    with source.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"questions", "responses"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError(
                f"response csv missing required columns: expected {required}, got {reader.fieldnames}"
            )

        for row in reader:
            rows_read += 1
            if max_rows is not None and rows_read > max_rows:
                break

            question_ids = (row.get("questions") or "").split(",")
            responses = (row.get("responses") or "").split(",")
            if len(question_ids) != len(responses):
                rows_skipped_length_mismatch += 1
                if strict:
                    raise ValueError(
                        f"row {rows_read} has mismatched lengths: "
                        f"questions={len(question_ids)} responses={len(responses)}"
                    )
                continue

            for qid_raw, response_raw in zip(question_ids, responses):
                qid = qid_raw.strip()
                resp_text = response_raw.strip()
                if not qid or not resp_text:
                    events_skipped_invalid += 1
                    continue
                if resp_text not in {"0", "1"}:
                    events_skipped_invalid += 1
                    continue

                totals[qid] += 1
                if resp_text == "1":
                    corrects[qid] += 1

    stats = {
        qid: ItemStats(total=totals[qid], correct=corrects[qid], accuracy=corrects[qid] / totals[qid])
        for qid in totals
        if totals[qid] > 0
    }
    report = ResponseParseReport(
        rows_read=rows_read,
        rows_skipped_length_mismatch=rows_skipped_length_mismatch,
        events_skipped_invalid=events_skipped_invalid,
    )
    if not stats:
        raise ValueError("no item stats were computed from response csv")
    return stats, report


def select_questions_with_stats(
    questions: Iterable[QuestionRecord],
    item_stats: dict[str, ItemStats],
    max_questions: int,
    min_option_questions: int = 1,
    selection_mode: str = "representative",
    selection_seed: int = 42,
    min_item_response_count: int = 0,
    hard_max_accuracy: float = 0.5,
    medium_max_accuracy: float = 0.75,
) -> list[QuestionRecord]:
    if selection_mode not in {"head", "representative", "difficulty_balanced"}:
        raise ValueError(
            "selection_mode must be one of head/representative/difficulty_balanced, "
            f"got {selection_mode!r}"
        )
    if min_item_response_count < 0:
        raise ValueError(
            f"min_item_response_count must be non-negative, got {min_item_response_count}"
        )

    matched = [question for question in questions if question.question_id in item_stats]
    if not matched:
        raise ValueError("no overlap between loaded questions and response item stats")
    eligible = [
        question
        for question in matched
        if item_stats[question.question_id].total >= min_item_response_count
    ]
    if not eligible:
        raise ValueError(
            "no questions remain after applying item response count filter: "
            f"min_item_response_count={min_item_response_count}"
        )

    if selection_mode == "head":
        option_questions = [question for question in eligible if question.options]
        selected: list[QuestionRecord] = []
        selected_ids: set[str] = set()

        option_target = max(0, min(min_option_questions, max_questions))
        for question in option_questions:
            if len(selected) >= option_target:
                break
            selected.append(question)
            selected_ids.add(question.question_id)

        for question in eligible:
            if len(selected) >= max_questions:
                break
            if question.question_id in selected_ids:
                continue
            selected.append(question)
            selected_ids.add(question.question_id)

        if not selected:
            raise ValueError("no overlap between loaded questions and response item stats")
        return selected

    if selection_mode == "difficulty_balanced":
        if max_questions <= 0 or max_questions % 3 != 0:
            raise ValueError(
                "difficulty_balanced requires max_questions to be a positive multiple of 3, "
                f"got {max_questions}"
            )
        per_band = max_questions // 3
        bands = _split_questions_into_difficulty_bands(
            eligible,
            item_stats=item_stats,
            hard_max_accuracy=hard_max_accuracy,
            medium_max_accuracy=medium_max_accuracy,
        )
        for band_name, band_questions in bands.items():
            if len(band_questions) < per_band:
                raise ValueError(
                    f"not enough {band_name} questions after filtering: "
                    f"required={per_band}, available={len(band_questions)}"
                )
        selected: list[QuestionRecord] = []
        for band_name in ["hard", "medium", "easy"]:
            selected.extend(
                _sample_evenly_spaced_questions(
                    candidates=bands[band_name],
                    target_count=per_band,
                )
            )
        return selected

    rng = random.Random(selection_seed)
    option_questions = [question for question in eligible if question.options]
    selected: list[QuestionRecord] = []
    selected_ids: set[str] = set()

    option_target = max(0, min(min_option_questions, max_questions))
    option_selected = _sample_representative_questions(
        candidates=option_questions,
        item_stats=item_stats,
        target_count=min(option_target, len(option_questions)),
        rng=rng,
    )
    for question in option_selected:
        selected.append(question)
        selected_ids.add(question.question_id)

    remaining_slots = max_questions - len(selected)
    remaining_questions = [
        question for question in eligible if question.question_id not in selected_ids
    ]
    sampled_remaining = _sample_representative_questions(
        candidates=remaining_questions,
        item_stats=item_stats,
        target_count=min(remaining_slots, len(remaining_questions)),
        rng=rng,
    )
    for question in sampled_remaining:
        selected.append(question)
        selected_ids.add(question.question_id)

    if not selected:
        raise ValueError("no overlap between loaded questions and response item stats")
    return selected


def load_frozen_selected_questions(
    frozen_selection_path: str | Path,
    questions: Iterable[QuestionRecord],
    item_stats: dict[str, ItemStats],
) -> list[QuestionRecord]:
    source = Path(frozen_selection_path)
    if not source.exists():
        raise FileNotFoundError(f"frozen selected question file not found: {source}")

    with source.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid frozen selected question json: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(
            "frozen selected question file must be a JSON list, "
            f"got {type(data).__name__}"
        )

    question_lookup = {question.question_id: question for question in questions}
    selected: list[QuestionRecord] = []
    seen_qids: set[str] = set()
    for row_index, raw_row in enumerate(data, start=1):
        row = _validate_frozen_selected_row(raw_row, row_index=row_index)
        qid = str(row.get("question_id", "")).strip()
        if not qid:
            raise ValueError(f"frozen selected question row {row_index} missing question_id")
        if qid in seen_qids:
            raise ValueError(f"duplicate question_id in frozen selected question file: {qid}")
        seen_qids.add(qid)

        question = question_lookup.get(qid)
        if question is None:
            raise KeyError(f"question_id={qid!r} from frozen file missing in loaded questions")
        if qid not in item_stats:
            raise KeyError(f"question_id={qid!r} from frozen file missing in item_stats")

        frozen_question_type = str(row.get("question_type", "")).strip()
        if frozen_question_type and frozen_question_type != question.question_type:
            raise ValueError(
                f"frozen question_type mismatch for question_id={qid}: "
                f"frozen={frozen_question_type!r}, loaded={question.question_type!r}"
            )

        frozen_question_text = str(row.get("question_text", "")).strip()
        if frozen_question_text and frozen_question_text != question.question_text:
            raise ValueError(
                f"frozen question_text mismatch for question_id={qid}"
            )

        if "options" in row:
            frozen_options = _normalize_options(row.get("options"))
            if frozen_options != question.options:
                raise ValueError(f"frozen options mismatch for question_id={qid}")

        if "gold_answers" in row:
            frozen_answers = _normalize_answers(row.get("gold_answers"))
            if frozen_answers != question.answer:
                raise ValueError(f"frozen gold_answers mismatch for question_id={qid}")

        difficulty_band_raw = str(row.get("difficulty_band", "") or "").strip()
        difficulty_band = difficulty_band_raw if difficulty_band_raw else None

        paper_module_name_raw = str(row.get("paper_module_name", "") or "").strip()
        paper_module_name = paper_module_name_raw if paper_module_name_raw else None

        paper_slot_id_raw = row.get("paper_slot_id")
        if paper_slot_id_raw is None or str(paper_slot_id_raw).strip() == "":
            paper_slot_id = None
        else:
            try:
                paper_slot_id = int(paper_slot_id_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid paper_slot_id for frozen question_id={qid}: {paper_slot_id_raw!r}"
                ) from exc

        paper_b_hat_raw = row.get("paper_b_hat")
        if paper_b_hat_raw is None or str(paper_b_hat_raw).strip() == "":
            paper_b_hat = None
        else:
            try:
                paper_b_hat = float(paper_b_hat_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid paper_b_hat for frozen question_id={qid}: {paper_b_hat_raw!r}"
                ) from exc

        selected.append(
            replace(
                question,
                difficulty_band=difficulty_band,
                paper_slot_id=paper_slot_id,
                paper_module_name=paper_module_name,
                paper_b_hat=paper_b_hat,
            )
        )

    if not selected:
        raise ValueError("frozen selected question file is empty")
    return selected


def build_real_student_reference(
    response_csv_path: str | Path,
    selected_question_ids: Iterable[str],
    level_assignment_scope: str = "all_events",
    max_rows: int | None = None,
    strict: bool = False,
) -> RealStudentReference:
    if level_assignment_scope not in {"all_events", "selected_questions"}:
        raise ValueError(
            "level_assignment_scope must be one of all_events/selected_questions, "
            f"got {level_assignment_scope!r}"
        )

    selected_qids = [str(qid).strip() for qid in selected_question_ids if str(qid).strip()]
    if not selected_qids:
        raise ValueError("selected_question_ids cannot be empty")
    selected_set = set(selected_qids)

    source = Path(response_csv_path)
    if not source.exists():
        raise FileNotFoundError(f"response csv not found: {source}")

    global_totals: defaultdict[str, int] = defaultdict(int)
    global_corrects: defaultdict[str, int] = defaultdict(int)
    rows_read_1 = 0
    rows_skipped_length_mismatch_1 = 0
    events_skipped_invalid_1 = 0

    with source.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"questions", "responses"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError(
                f"response csv missing required columns: expected {required}, got {reader.fieldnames}"
            )
        for row in reader:
            rows_read_1 += 1
            if max_rows is not None and rows_read_1 > max_rows:
                break

            student_id = _resolve_student_id(row, rows_read_1)
            question_ids = (row.get("questions") or "").split(",")
            responses = (row.get("responses") or "").split(",")
            if len(question_ids) != len(responses):
                rows_skipped_length_mismatch_1 += 1
                if strict:
                    raise ValueError(
                        f"row {rows_read_1} has mismatched lengths: "
                        f"questions={len(question_ids)} responses={len(responses)}"
                    )
                continue

            for qid_raw, response_raw in zip(question_ids, responses):
                qid = qid_raw.strip()
                resp_text = response_raw.strip()
                if not qid or not resp_text:
                    events_skipped_invalid_1 += 1
                    continue
                if resp_text not in {"0", "1"}:
                    events_skipped_invalid_1 += 1
                    continue
                if level_assignment_scope == "selected_questions" and qid not in selected_set:
                    continue

                global_totals[student_id] += 1
                if resp_text == "1":
                    global_corrects[student_id] += 1

    student_accuracies: dict[str, float] = {}
    for student_id, total in global_totals.items():
        if total <= 0:
            continue
        student_accuracies[student_id] = global_corrects[student_id] / total
    if not student_accuracies:
        raise ValueError("no student accuracies available for level assignment")

    q25, q50, q75 = _compute_quartile_thresholds(list(student_accuracies.values()))
    student_levels: dict[str, str] = {
        student_id: _assign_level_by_quartile(acc, q25, q50, q75)
        for student_id, acc in student_accuracies.items()
    }

    student_level_counts: defaultdict[str, int] = defaultdict(int)
    for level in student_levels.values():
        student_level_counts[level] += 1

    total_selected = 0
    correct_selected = 0
    selected_item_totals: defaultdict[str, int] = defaultdict(int)
    selected_item_corrects: defaultdict[str, int] = defaultdict(int)
    level_totals: defaultdict[str, int] = defaultdict(int)
    level_corrects: defaultdict[str, int] = defaultdict(int)
    level_item_totals: dict[str, defaultdict[str, int]] = {
        level: defaultdict(int) for level in LEVEL_NAMES
    }
    level_item_corrects: dict[str, defaultdict[str, int]] = {
        level: defaultdict(int) for level in LEVEL_NAMES
    }
    level_students_with_selected_events: dict[str, set[str]] = {level: set() for level in LEVEL_NAMES}
    rows_read_2 = 0
    rows_skipped_length_mismatch_2 = 0
    events_skipped_invalid_2 = 0

    with source.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"questions", "responses"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError(
                f"response csv missing required columns: expected {required}, got {reader.fieldnames}"
            )
        for row in reader:
            rows_read_2 += 1
            if max_rows is not None and rows_read_2 > max_rows:
                break

            student_id = _resolve_student_id(row, rows_read_2)
            student_level = student_levels.get(student_id)
            if student_level is None:
                continue

            question_ids = (row.get("questions") or "").split(",")
            responses = (row.get("responses") or "").split(",")
            if len(question_ids) != len(responses):
                rows_skipped_length_mismatch_2 += 1
                if strict:
                    raise ValueError(
                        f"row {rows_read_2} has mismatched lengths: "
                        f"questions={len(question_ids)} responses={len(responses)}"
                    )
                continue

            for qid_raw, response_raw in zip(question_ids, responses):
                qid = qid_raw.strip()
                resp_text = response_raw.strip()
                if not qid or not resp_text:
                    events_skipped_invalid_2 += 1
                    continue
                if resp_text not in {"0", "1"}:
                    events_skipped_invalid_2 += 1
                    continue
                if qid not in selected_set:
                    continue

                total_selected += 1
                selected_item_totals[qid] += 1
                level_totals[student_level] += 1
                level_item_totals[student_level][qid] += 1
                level_students_with_selected_events[student_level].add(student_id)

                if resp_text == "1":
                    correct_selected += 1
                    selected_item_corrects[qid] += 1
                    level_corrects[student_level] += 1
                    level_item_corrects[student_level][qid] += 1

    if total_selected <= 0:
        raise ValueError("no selected-question events found in response csv")

    item_accuracy = {
        qid: selected_item_corrects[qid] / selected_item_totals[qid]
        for qid in selected_item_totals
        if selected_item_totals[qid] > 0
    }
    level_overall_accuracy: dict[str, float | None] = {}
    level_item_accuracy: dict[str, dict[str, float]] = {}
    level_n_events: dict[str, int] = {}
    level_n_students_with_selected: dict[str, int] = {}
    for level in LEVEL_NAMES:
        total = level_totals[level]
        level_n_events[level] = total
        level_n_students_with_selected[level] = len(level_students_with_selected_events[level])
        level_overall_accuracy[level] = (level_corrects[level] / total) if total > 0 else None
        level_item_accuracy[level] = {
            qid: level_item_corrects[level][qid] / level_item_totals[level][qid]
            for qid in level_item_totals[level]
            if level_item_totals[level][qid] > 0
        }

    pass1_report = ResponseParseReport(
        rows_read=rows_read_1,
        rows_skipped_length_mismatch=rows_skipped_length_mismatch_1,
        events_skipped_invalid=events_skipped_invalid_1,
    )
    pass2_report = ResponseParseReport(
        rows_read=rows_read_2,
        rows_skipped_length_mismatch=rows_skipped_length_mismatch_2,
        events_skipped_invalid=events_skipped_invalid_2,
    )
    return RealStudentReference(
        question_ids=selected_qids,
        level_assignment_scope=level_assignment_scope,
        overall_accuracy=correct_selected / total_selected,
        item_accuracy=item_accuracy,
        level_thresholds={"q25": q25, "q50": q50, "q75": q75},
        student_level_counts={level: student_level_counts[level] for level in LEVEL_NAMES},
        level_overall_accuracy=level_overall_accuracy,
        level_item_accuracy=level_item_accuracy,
        level_n_events=level_n_events,
        level_n_students_with_selected_events=level_n_students_with_selected,
        pass1_parse_report=pass1_report,
        pass2_parse_report=pass2_report,
    )
