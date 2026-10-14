from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from .data_loading import LEVEL_NAMES, ItemStats, QuestionRecord, RealStudentReference
from .llm_client import OpenAICompatClient
from .prompts import ANSWER_CORRECTNESS_JUDGE_PROMPT

OPTION_LETTER_RE = re.compile(r"[A-D]", re.IGNORECASE)
OPTION_TOKEN_RE = re.compile(r"^[A-D]$", re.IGNORECASE)
LATEX_MARKER_RE = re.compile(r"\$+")
LATEX_TEXT_WRAPPER_RE = re.compile(r"\\(?:text|mathrm|operatorname)\s*\{([^{}]*)\}")
LATEX_FRAC_RE = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
WHITESPACE_RE = re.compile(r"\s+")
MULTI_PART_SPLIT_RE = re.compile(r"[;,\uFF0C\uFF1B\u3001]+")
PART_INDEX_PREFIX_RE = re.compile(r"^(?:\(?\d+\)?[.)\u3001:]|[\u2460-\u2469])")
TRAILING_PUNCTUATION_RE = re.compile(r"[\u3002\uFF0E.]+$")
SIMPLE_NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?$")
RATIO_RE = re.compile(r"^-?\d+(?:\.\d+)?:-?\d+(?:\.\d+)?$")
COMPARATOR_RE = re.compile(r"^(?:<|>|=|<=|>=|\u2260)$")
ASCII_ALPHA_RE = re.compile(r"[a-z]", re.IGNORECASE)
STRUCTURAL_OPERATOR_RE = re.compile(r"[=+\-*/^]")
LEVEL_ORDER = ("high", "medium", "low", "poor")


@dataclass(frozen=True)
class JudgeCorrectnessResult:
    is_correct: bool
    confidence: str


@dataclass(frozen=True)
class AnswerFormatAssessment:
    category: str
    rule_confident: bool
    llm_review_reason: str | None


@dataclass(frozen=True)
class CorrectnessLabelResult:
    is_correct: bool
    source: str
    rule_result: bool
    answer_format_category: str
    llm_review_reason: str | None
    llm_review_used: bool
    llm_review_confidence: str | None


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


def _validate_enum(value: Any, allowed: set[str], field_name: str) -> str:
    text = str(value).strip().lower()
    if text in allowed:
        return text
    raise ValueError(f"invalid {field_name}: {value!r}, allowed={sorted(allowed)}")


def judge_prediction_correctness_with_llm(
    question_text: str,
    options: dict[str, str],
    predicted_answer: str,
    llm_client: OpenAICompatClient | None = None,
) -> JudgeCorrectnessResult:
    if llm_client is None:
        raise ValueError("judge_prediction_correctness_with_llm requires llm_client")

    user_payload = {
        "question_text": question_text,
        "options": options,
        "predicted_answer": predicted_answer,
        "required_output_schema": {
            "is_correct": "true|false",
            "confidence": "low|medium|high",
        },
    }
    parsed = llm_client.chat_json(
        system_prompt=ANSWER_CORRECTNESS_JUDGE_PROMPT,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
    )
    return JudgeCorrectnessResult(
        is_correct=_validate_bool(parsed.get("is_correct"), "is_correct"),
        confidence=_validate_enum(
            parsed.get("confidence"),
            {"low", "medium", "high"},
            "confidence",
        ),
    )


def _extract_option_letter(text: str) -> str:
    match = OPTION_LETTER_RE.search(text or "")
    return match.group(0).upper() if match else ""


def _unwrap_latex_text_wrappers(text: str) -> str:
    previous = None
    current = text
    while current != previous:
        previous = current
        current = LATEX_TEXT_WRAPPER_RE.sub(r"\1", current)
    return current


def _normalize_frac_commands(text: str) -> str:
    previous = None
    current = text
    while current != previous:
        previous = current
        current = LATEX_FRAC_RE.sub(r"\1/\2", current)
    return current


def _is_entirely_wrapped(text: str, open_char: str, close_char: str) -> bool:
    if len(text) < 2 or not text.startswith(open_char) or not text.endswith(close_char):
        return False
    balance = 0
    for idx, char in enumerate(text):
        if char == open_char:
            balance += 1
        elif char == close_char:
            balance -= 1
        if balance == 0 and idx < len(text) - 1:
            return False
        if balance < 0:
            return False
    return balance == 0


def _strip_outer_wrappers(text: str) -> str:
    current = text.strip()
    wrapper_pairs = [
        ("(", ")"),
        ("[", "]"),
        ("{", "}"),
        ("\uFF08", "\uFF09"),
    ]
    changed = True
    while changed and current:
        changed = False
        for open_char, close_char in wrapper_pairs:
            if _is_entirely_wrapped(current, open_char, close_char):
                current = current[1:-1].strip()
                changed = True
    return current


def _strip_trailing_punctuation(text: str) -> str:
    current = text
    while current and unicodedata.category(current[-1]).startswith("P"):
        current = current[:-1]
    return current


def _normalize_common_answer_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", str(text or ""))
    cleaned = LATEX_MARKER_RE.sub("", cleaned)
    cleaned = _unwrap_latex_text_wrappers(cleaned)
    cleaned = _normalize_frac_commands(cleaned)

    replacements = {
        "\\left": "",
        "\\right": "",
        "\\times": "*",
        "\u00D7": "*",
        "\\cdot": "*",
        "\\div": "/",
        "\u00F7": "/",
        "\uFF0C": ",",
        "\uFF1B": ";",
    }
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)

    cleaned = cleaned.replace("{", "").replace("}", "").replace("\\", "")
    cleaned = WHITESPACE_RE.sub("", cleaned)
    cleaned = cleaned.strip().strip("\"'\u201C\u201D\u2018\u2019")
    cleaned = TRAILING_PUNCTUATION_RE.sub("", cleaned)
    cleaned = _strip_trailing_punctuation(cleaned)
    cleaned = _strip_outer_wrappers(cleaned)
    return cleaned.strip().lower()


def _normalize_fill_answer(text: str) -> str:
    return _normalize_common_answer_text(text)


def _extract_option_token(text: str) -> str:
    normalized = _normalize_common_answer_text(text)
    if OPTION_TOKEN_RE.fullmatch(normalized):
        return normalized.upper()
    return ""


def _expand_single_answer_variants(text: str) -> list[str]:
    base = _normalize_common_answer_text(text)
    if not base:
        return []
    variants = [base]
    if "=" in base:
        tail = _strip_outer_wrappers(base.rsplit("=", 1)[-1])
        tail = _strip_trailing_punctuation(tail)
        if tail and tail not in variants:
            variants.append(tail)
    return variants


def _classify_normalized_atom(text: str) -> str:
    if not text:
        return "empty"
    if OPTION_TOKEN_RE.fullmatch(text):
        return "option_token"
    if SIMPLE_NUMERIC_RE.fullmatch(text):
        return "numeric_token"
    if RATIO_RE.fullmatch(text):
        return "ratio_token"
    if COMPARATOR_RE.fullmatch(text):
        return "comparator_token"

    has_separator = "," in text or ";" in text
    if has_separator:
        parts = [part for part in re.split(r"[;,]+", text) if part]
        if parts and all(SIMPLE_NUMERIC_RE.fullmatch(part) for part in parts):
            return "tuple_numeric_token"
        if parts and all(
            _classify_normalized_atom(part) in {"simple_text_token", "comparator_token"}
            for part in parts
        ):
            return "tuple_text_token"

    has_alpha = bool(ASCII_ALPHA_RE.search(text))
    has_structural_operator = bool(STRUCTURAL_OPERATOR_RE.search(text))
    if has_alpha and has_structural_operator:
        return "symbolic_equation_token"
    if has_alpha:
        return "symbolic_expression_token"
    if has_structural_operator:
        return "equation_like_token"
    return "simple_text_token"


def assess_answer_format(gold_answers: list[str], has_options: bool) -> AnswerFormatAssessment:
    if has_options:
        return AnswerFormatAssessment(
            category="option_explicit",
            rule_confident=True,
            llm_review_reason=None,
        )

    normalized_answers = [
        _normalize_common_answer_text(answer)
        for answer in gold_answers
        if _normalize_common_answer_text(answer)
    ]
    if not normalized_answers:
        return AnswerFormatAssessment(
            category="empty_gold",
            rule_confident=False,
            llm_review_reason="empty_gold_answer",
        )

    atom_types = [_classify_normalized_atom(answer) for answer in normalized_answers]
    if all(atom_type == "option_token" for atom_type in atom_types):
        return AnswerFormatAssessment(
            category="option_implicit",
            rule_confident=True,
            llm_review_reason=None,
        )

    simple_exact_types = {
        "numeric_token",
        "ratio_token",
        "comparator_token",
        "simple_text_token",
        "tuple_numeric_token",
        "tuple_text_token",
    }
    if len(atom_types) == 1 and atom_types[0] in simple_exact_types:
        return AnswerFormatAssessment(
            category=f"single_{atom_types[0]}",
            rule_confident=True,
            llm_review_reason=None,
        )
    if len(atom_types) > 1 and all(atom_type in simple_exact_types for atom_type in atom_types):
        return AnswerFormatAssessment(
            category="multi_simple_exact",
            rule_confident=True,
            llm_review_reason=None,
        )

    if any(atom_type == "symbolic_equation_token" for atom_type in atom_types):
        return AnswerFormatAssessment(
            category="symbolic_equation",
            rule_confident=False,
            llm_review_reason="symbolic_equation_gold",
        )
    if any(atom_type == "symbolic_expression_token" for atom_type in atom_types):
        return AnswerFormatAssessment(
            category="symbolic_expression",
            rule_confident=False,
            llm_review_reason="symbolic_expression_gold",
        )
    if any(atom_type == "equation_like_token" for atom_type in atom_types):
        return AnswerFormatAssessment(
            category="equation_like",
            rule_confident=False,
            llm_review_reason="equation_like_gold",
        )
    return AnswerFormatAssessment(
        category="complex_other",
        rule_confident=False,
        llm_review_reason="complex_gold_format",
    )


def _normalize_answer_part(text: str) -> str:
    part = _normalize_common_answer_text(text)
    part = PART_INDEX_PREFIX_RE.sub("", part)
    part = _strip_outer_wrappers(part)
    part = part.strip("()[]{}\uFF08\uFF09")
    return part.strip().lower()


def _split_predicted_parts(text: str) -> list[str]:
    raw_parts = MULTI_PART_SPLIT_RE.split(_normalize_common_answer_text(text))
    parts = [_normalize_answer_part(part) for part in raw_parts]
    return [part for part in parts if part]


def _normalize_predicted_answer_for_pattern(
    predicted_answer: str,
    has_options: bool,
) -> str:
    if has_options:
        return _extract_option_token(predicted_answer) or _extract_option_letter(predicted_answer)
    return _normalize_fill_answer(predicted_answer)


def compute_level_pattern_diagnostics(records: list[dict[str, object]]) -> dict[str, object]:
    if not records:
        raise ValueError("cannot compute level pattern diagnostics on empty records")

    by_level_question_counts: dict[str, defaultdict[str, int]] = {
        level: defaultdict(int) for level in LEVEL_ORDER
    }
    by_level_question_correct: dict[str, defaultdict[str, int]] = {
        level: defaultdict(int) for level in LEVEL_ORDER
    }
    by_level_question_answers: dict[str, defaultdict[str, Counter[str]]] = {
        level: defaultdict(Counter) for level in LEVEL_ORDER
    }
    covered_questions: set[str] = set()

    for record in records:
        student_model = record.get("student_model", {})
        if not isinstance(student_model, dict):
            continue
        level = str(student_model.get("academic_level", "")).strip().lower()
        if level not in LEVEL_ORDER:
            continue

        qid = str(record.get("question_id", "")).strip()
        if not qid:
            continue
        covered_questions.add(qid)

        by_level_question_counts[level][qid] += 1
        by_level_question_correct[level][qid] += int(bool(record.get("is_correct", False)))

        normalized_answer = _normalize_predicted_answer_for_pattern(
            predicted_answer=str(record.get("predicted_answer", "")),
            has_options=bool(record.get("has_options", False)),
        )
        if normalized_answer:
            by_level_question_answers[level][qid][normalized_answer] += 1

    strict_monotonic_qids: list[str] = []
    same_dominant_answer_qids: list[str] = []
    same_dominant_answer_details: list[dict[str, object]] = []
    per_question_level_accuracy: dict[str, dict[str, float]] = {}

    def _question_sort_key(value: str) -> tuple[int, int | str]:
        return (0, int(value)) if value.isdigit() else (1, value)

    for qid in sorted(covered_questions, key=_question_sort_key):
        if any(by_level_question_counts[level].get(qid, 0) == 0 for level in LEVEL_ORDER):
            continue

        level_accuracy = {
            level: (
                by_level_question_correct[level][qid] / by_level_question_counts[level][qid]
            )
            for level in LEVEL_ORDER
        }
        per_question_level_accuracy[qid] = level_accuracy
        if (
            level_accuracy["high"] > level_accuracy["medium"]
            > level_accuracy["low"]
            > level_accuracy["poor"]
        ):
            strict_monotonic_qids.append(qid)

        dominant_answers: list[str] = []
        unique_modes = True
        for level in LEVEL_ORDER:
            answer_counter = by_level_question_answers[level].get(qid, Counter())
            if not answer_counter:
                unique_modes = False
                break
            top_count = max(answer_counter.values())
            top_answers = sorted(
                answer for answer, count in answer_counter.items() if count == top_count
            )
            if len(top_answers) != 1:
                unique_modes = False
                break
            dominant_answers.append(top_answers[0])

        if unique_modes and len(set(dominant_answers)) == 1:
            same_dominant_answer_qids.append(qid)
            same_dominant_answer_details.append(
                {
                    "question_id": qid,
                    "dominant_answer": dominant_answers[0],
                    "level_accuracy": level_accuracy,
                }
            )

    questions_with_complete_coverage_n = len(per_question_level_accuracy)
    return {
        "questions_with_complete_four_level_coverage_n": questions_with_complete_coverage_n,
        "strict_monotonic_item_count": len(strict_monotonic_qids),
        "strict_monotonic_item_fraction": (
            len(strict_monotonic_qids) / questions_with_complete_coverage_n
            if questions_with_complete_coverage_n
            else None
        ),
        "strict_monotonic_item_examples": strict_monotonic_qids[:20],
        "same_dominant_answer_all_levels_count": len(same_dominant_answer_qids),
        "same_dominant_answer_all_levels_fraction": (
            len(same_dominant_answer_qids) / questions_with_complete_coverage_n
            if questions_with_complete_coverage_n
            else None
        ),
        "same_dominant_answer_all_levels_examples": same_dominant_answer_details[:20],
    }


def _is_ordered_subsequence_match(predicted: str, gold_parts: list[str]) -> bool:
    cursor = 0
    for gold in gold_parts:
        idx = predicted.find(gold, cursor)
        if idx < 0:
            return False
        cursor = idx + len(gold)
    return True


def is_prediction_correct(
    predicted_answer: str,
    gold_answers: list[str],
    has_options: bool,
) -> bool:
    if not gold_answers:
        return False

    if has_options:
        pred_letter = _extract_option_token(predicted_answer) or _extract_option_letter(
            predicted_answer
        )
        gold_letters = {
            token
            for ans in gold_answers
            for token in [_extract_option_token(ans) or _extract_option_letter(ans)]
            if token
        }
        return bool(pred_letter) and pred_letter in gold_letters

    pred_letter = _extract_option_token(predicted_answer)
    gold_letter_tokens = [_extract_option_token(ans) for ans in gold_answers]
    if pred_letter and gold_letter_tokens and all(token for token in gold_letter_tokens):
        return pred_letter in set(gold_letter_tokens)

    pred_norm = _normalize_fill_answer(predicted_answer)
    gold_norm_list = []
    for ans in gold_answers:
        variants = _expand_single_answer_variants(ans)
        if variants:
            gold_norm_list.append(variants[-1])
    gold_norm_list = [ans for ans in gold_norm_list if ans]
    if not pred_norm or not gold_norm_list:
        return False

    if len(gold_norm_list) == 1:
        gold_variants = _expand_single_answer_variants(gold_answers[0])
        if pred_norm in gold_variants:
            return True

        pred_parts = _split_predicted_parts(predicted_answer)
        for gold_variant in gold_variants:
            gold_parts = _split_predicted_parts(gold_variant)
            if len(pred_parts) > 1 and pred_parts == gold_parts:
                return True
        return False

    pred_parts = _split_predicted_parts(predicted_answer)
    if len(pred_parts) == len(gold_norm_list):
        if all(pred_parts[i] == gold_norm_list[i] for i in range(len(gold_norm_list))):
            return True

    return _is_ordered_subsequence_match(pred_norm, gold_norm_list)


def label_prediction_correctness(
    predicted_answer: str,
    gold_answers: list[str],
    has_options: bool,
    question_text: str,
    options: dict[str, str],
    llm_client: OpenAICompatClient | None = None,
    official_correctness_mode: str = "rules_only",
) -> CorrectnessLabelResult:
    if official_correctness_mode not in {"rules_only", "rules_plus_llm_ambiguous_review"}:
        raise ValueError(
            "official_correctness_mode must be 'rules_only' or "
            f"'rules_plus_llm_ambiguous_review', got {official_correctness_mode!r}"
        )

    assessment = assess_answer_format(gold_answers=gold_answers, has_options=has_options)
    rule_result = is_prediction_correct(
        predicted_answer=predicted_answer,
        gold_answers=gold_answers,
        has_options=has_options,
    )
    if rule_result:
        return CorrectnessLabelResult(
            is_correct=True,
            source="rule",
            rule_result=True,
            answer_format_category=assessment.category,
            llm_review_reason=None,
            llm_review_used=False,
            llm_review_confidence=None,
        )

    if official_correctness_mode == "rules_only":
        return CorrectnessLabelResult(
            is_correct=False,
            source="rule",
            rule_result=False,
            answer_format_category=assessment.category,
            llm_review_reason=None,
            llm_review_used=False,
            llm_review_confidence=None,
        )

    if not assessment.llm_review_reason:
        return CorrectnessLabelResult(
            is_correct=False,
            source="rule",
            rule_result=False,
            answer_format_category=assessment.category,
            llm_review_reason=None,
            llm_review_used=False,
            llm_review_confidence=None,
        )
    if llm_client is None:
        raise ValueError(
            "rules_plus_llm_ambiguous_review requires llm_client for ambiguous evaluation cases"
        )

    judge_output = judge_prediction_correctness_with_llm(
        question_text=question_text,
        options=options,
        predicted_answer=predicted_answer,
        llm_client=llm_client,
    )
    return CorrectnessLabelResult(
        is_correct=judge_output.is_correct,
        source="llm_ambiguous_review",
        rule_result=False,
        answer_format_category=assessment.category,
        llm_review_reason=assessment.llm_review_reason,
        llm_review_used=True,
        llm_review_confidence=judge_output.confidence,
    )


def apply_official_correctness_labels(
    records: list[dict[str, object]],
    question_lookup: dict[str, QuestionRecord],
    llm_client: OpenAICompatClient | None = None,
    official_correctness_mode: str = "rules_only",
) -> dict[str, object]:
    summary = {
        "official_correctness_mode": official_correctness_mode,
        "official_correctness_rule_n": 0,
        "official_correctness_llm_review_n": 0,
        "official_correctness_llm_review_positive_n": 0,
        "official_correctness_category_counts": {},
        "official_correctness_llm_review_reason_counts": {},
    }
    category_counts: defaultdict[str, int] = defaultdict(int)
    reason_counts: defaultdict[str, int] = defaultdict(int)

    for record in records:
        qid = str(record["question_id"])
        question = question_lookup.get(qid)
        if question is None:
            raise KeyError(f"question_id={qid!r} missing from question_lookup during evaluation")

        result = label_prediction_correctness(
            predicted_answer=str(record["predicted_answer"]),
            gold_answers=[str(x) for x in record.get("gold_answers", [])],
            has_options=bool(record.get("has_options", False)),
            question_text=question.question_text,
            options=question.options,
            llm_client=llm_client,
            official_correctness_mode=official_correctness_mode,
        )
        record["is_correct"] = result.is_correct
        record["correctness_label"] = {
            "source": result.source,
            "rule_result": result.rule_result,
            "answer_format_category": result.answer_format_category,
            "llm_review_reason": result.llm_review_reason,
            "llm_review_used": result.llm_review_used,
            "llm_review_confidence": result.llm_review_confidence,
        }

        category_counts[result.answer_format_category] += 1
        if result.llm_review_used:
            summary["official_correctness_llm_review_n"] += 1
            summary["official_correctness_llm_review_positive_n"] += int(result.is_correct)
            if result.llm_review_reason:
                reason_counts[result.llm_review_reason] += 1
        else:
            summary["official_correctness_rule_n"] += 1

    summary["official_correctness_category_counts"] = dict(sorted(category_counts.items()))
    summary["official_correctness_llm_review_reason_counts"] = dict(sorted(reason_counts.items()))
    return summary


def audit_question_answer_formats(questions: list[QuestionRecord]) -> dict[str, object]:
    category_counts: defaultdict[str, int] = defaultdict(int)
    ambiguous_examples: list[dict[str, object]] = []
    for question in questions:
        assessment = assess_answer_format(
            gold_answers=question.answer,
            has_options=bool(question.options),
        )
        category_counts[assessment.category] += 1
        if not assessment.rule_confident and len(ambiguous_examples) < 50:
            ambiguous_examples.append(
                {
                    "question_id": question.question_id,
                    "question_type": question.question_type,
                    "category": assessment.category,
                    "llm_review_reason": assessment.llm_review_reason,
                    "gold_answers": question.answer,
                }
            )
    return {
        "n_questions": len(questions),
        "category_counts": dict(sorted(category_counts.items())),
        "ambiguous_examples": ambiguous_examples,
    }


def _pearson_corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    den = den_x * den_y
    if den == 0:
        return None
    return num / den


def _rankdata(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(indexed):
        end = idx + 1
        while end < len(indexed) and indexed[end][1] == indexed[idx][1]:
            end += 1
        avg_rank = (idx + 1 + end) / 2.0
        for pos in range(idx, end):
            ranks[indexed[pos][0]] = avg_rank
        idx = end
    return ranks


def _spearman_corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return _pearson_corr(_rankdata(xs), _rankdata(ys))


def evaluate_run(
    records: list[dict[str, object]],
    item_stats: dict[str, ItemStats],
    question_lookup: dict[str, QuestionRecord] | None = None,
) -> dict[str, object]:
    if not records:
        raise ValueError("cannot evaluate empty records")

    total = 0
    total_correct = 0
    by_question_counts: defaultdict[str, int] = defaultdict(int)
    by_question_correct: defaultdict[str, int] = defaultdict(int)

    for record in records:
        qid = str(record["question_id"])
        if "correctness_label" in record and "is_correct" in record:
            correct = bool(record["is_correct"])
        else:
            predicted_answer = str(record["predicted_answer"])
            gold_answers = [str(x) for x in record.get("gold_answers", [])]
            has_options = bool(record.get("has_options", False))
            correct = is_prediction_correct(
                predicted_answer=predicted_answer,
                gold_answers=gold_answers,
                has_options=has_options,
            )
            record["is_correct"] = correct

        total += 1
        total_correct += int(correct)
        by_question_counts[qid] += 1
        by_question_correct[qid] += int(correct)

    predicted_item_acc = {
        qid: by_question_correct[qid] / by_question_counts[qid] for qid in by_question_counts
    }

    overlap_qids = sorted(set(predicted_item_acc).intersection(item_stats))
    pred_values = [predicted_item_acc[qid] for qid in overlap_qids]
    real_values = [item_stats[qid].accuracy for qid in overlap_qids]
    mae = (
        sum(abs(pred - real) for pred, real in zip(pred_values, real_values)) / len(overlap_qids)
        if overlap_qids
        else None
    )
    pearson = _pearson_corr(pred_values, real_values) if overlap_qids else None
    spearman = _spearman_corr(pred_values, real_values) if overlap_qids else None

    rasch_overlap_qids: list[str] = []
    rasch_pred_values: list[float] = []
    rasch_b_values: list[float] = []
    if question_lookup is not None:
        for qid in sorted(predicted_item_acc):
            question = question_lookup.get(qid)
            if question is None or question.paper_b_hat is None:
                continue
            rasch_overlap_qids.append(qid)
            rasch_pred_values.append(predicted_item_acc[qid])
            rasch_b_values.append(float(question.paper_b_hat))

    rasch_pearson = (
        _pearson_corr(rasch_pred_values, rasch_b_values) if rasch_overlap_qids else None
    )
    rasch_spearman = (
        _spearman_corr(rasch_pred_values, rasch_b_values) if rasch_overlap_qids else None
    )

    return {
        "n_predictions": total,
        "overall_accuracy": total_correct / total if total else 0.0,
        "n_questions_predicted": len(by_question_counts),
        "n_questions_overlap_with_xes_stats": len(overlap_qids),
        "item_accuracy_mae_vs_xes": mae,
        "item_accuracy_pearson_vs_xes": pearson,
        "item_accuracy_spearman_vs_xes": spearman,
        "item_n_overlap_with_rasch_b_hat": len(rasch_overlap_qids),
        "item_accuracy_pearson_vs_rasch_b_hat": rasch_pearson,
        "item_accuracy_spearman_vs_rasch_b_hat": rasch_spearman,
    }


def evaluate_against_real_students(
    records: list[dict[str, object]],
    real_reference: RealStudentReference,
) -> dict[str, object]:
    if not records:
        raise ValueError("cannot compare empty records with real students")

    total = 0
    total_correct = 0
    by_question_counts: defaultdict[str, int] = defaultdict(int)
    by_question_correct: defaultdict[str, int] = defaultdict(int)
    by_level_counts: defaultdict[str, int] = defaultdict(int)
    by_level_correct: defaultdict[str, int] = defaultdict(int)
    by_level_question_counts: dict[str, defaultdict[str, int]] = {
        level: defaultdict(int) for level in LEVEL_NAMES
    }
    by_level_question_correct: dict[str, defaultdict[str, int]] = {
        level: defaultdict(int) for level in LEVEL_NAMES
    }
    by_level_student_ids: dict[str, set[str]] = {level: set() for level in LEVEL_NAMES}

    for record in records:
        qid = str(record["question_id"])
        is_correct = bool(record.get("is_correct", False))
        student_model = record.get("student_model", {})
        level_raw = ""
        if isinstance(student_model, dict):
            level_raw = str(student_model.get("academic_level", "")).strip().lower()
        level = level_raw if level_raw in LEVEL_NAMES else ""

        total += 1
        total_correct += int(is_correct)
        by_question_counts[qid] += 1
        by_question_correct[qid] += int(is_correct)

        if level:
            by_level_counts[level] += 1
            by_level_correct[level] += int(is_correct)
            by_level_question_counts[level][qid] += 1
            by_level_question_correct[level][qid] += int(is_correct)
            by_level_student_ids[level].add(str(record.get("student_id", "")))

    predicted_item_accuracy = {
        qid: by_question_correct[qid] / by_question_counts[qid] for qid in by_question_counts
    }
    real_item_accuracy = real_reference.item_accuracy
    overlap_qids = sorted(set(predicted_item_accuracy).intersection(real_item_accuracy))
    pred_values = [predicted_item_accuracy[qid] for qid in overlap_qids]
    real_values = [real_item_accuracy[qid] for qid in overlap_qids]
    item_mae = (
        sum(abs(pred - real) for pred, real in zip(pred_values, real_values)) / len(overlap_qids)
        if overlap_qids
        else None
    )
    item_pearson = _pearson_corr(pred_values, real_values) if overlap_qids else None
    item_spearman = _spearman_corr(pred_values, real_values) if overlap_qids else None

    level_alignment: dict[str, dict[str, object]] = {}
    for level in LEVEL_NAMES:
        pred_level_total = by_level_counts[level]
        pred_level_overall = (
            by_level_correct[level] / pred_level_total if pred_level_total > 0 else None
        )
        real_level_overall = real_reference.level_overall_accuracy.get(level)
        level_gap = (
            abs(pred_level_overall - real_level_overall)
            if pred_level_overall is not None and real_level_overall is not None
            else None
        )

        pred_level_item_accuracy = {
            qid: by_level_question_correct[level][qid] / by_level_question_counts[level][qid]
            for qid in by_level_question_counts[level]
            if by_level_question_counts[level][qid] > 0
        }
        real_level_item_accuracy = real_reference.level_item_accuracy.get(level, {})
        level_overlap_qids = sorted(set(pred_level_item_accuracy).intersection(real_level_item_accuracy))
        level_pred_values = [pred_level_item_accuracy[qid] for qid in level_overlap_qids]
        level_real_values = [real_level_item_accuracy[qid] for qid in level_overlap_qids]
        level_item_mae = (
            sum(abs(pred - real) for pred, real in zip(level_pred_values, level_real_values))
            / len(level_overlap_qids)
            if level_overlap_qids
            else None
        )
        level_item_pearson = (
            _pearson_corr(level_pred_values, level_real_values) if level_overlap_qids else None
        )
        level_item_spearman = (
            _spearman_corr(level_pred_values, level_real_values) if level_overlap_qids else None
        )
        level_alignment[level] = {
            "predicted_overall_accuracy": pred_level_overall,
            "real_overall_accuracy": real_level_overall,
            "overall_accuracy_gap": level_gap,
            "predicted_n_records": pred_level_total,
            "predicted_n_students": len(by_level_student_ids[level]),
            "real_n_students_with_level": real_reference.student_level_counts.get(level, 0),
            "real_n_students_with_selected_events": real_reference.level_n_students_with_selected_events.get(
                level, 0
            ),
            "real_n_events_on_selected_questions": real_reference.level_n_events.get(level, 0),
            "item_n_overlap": len(level_overlap_qids),
            "item_mae": level_item_mae,
            "item_pearson": level_item_pearson,
            "item_spearman": level_item_spearman,
        }

    predicted_overall = total_correct / total if total else 0.0
    overall_gap = abs(predicted_overall - real_reference.overall_accuracy)
    level_gap_values = [
        level_alignment[level]["overall_accuracy_gap"]
        for level in LEVEL_NAMES
        if level_alignment[level]["overall_accuracy_gap"] is not None
    ]
    return {
        "real_overall_accuracy": real_reference.overall_accuracy,
        "overall_accuracy_gap_vs_real_students": overall_gap,
        "mean_level_overall_accuracy_gap": (
            sum(level_gap_values) / len(level_gap_values) if level_gap_values else None
        ),
        "item_n_overlap_vs_real_students": len(overlap_qids),
        "item_accuracy_mae_vs_real_students": item_mae,
        "item_accuracy_pearson_vs_real_students": item_pearson,
        "item_accuracy_spearman_vs_real_students": item_spearman,
        "real_level_assignment_scope": real_reference.level_assignment_scope,
        "real_level_thresholds": real_reference.level_thresholds,
        "real_student_level_counts": real_reference.student_level_counts,
        "level_alignment_vs_real_students": level_alignment,
    }
