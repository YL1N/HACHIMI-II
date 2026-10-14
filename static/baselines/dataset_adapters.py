from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]

XES_COHORT = (
    REPO_ROOT
    / "static"
    / "xes"
    / "outputs"
    / "xes_strong_ablation_60x96"
    / "hachimi_ii"
    / "run"
)
EEDI_STATIC_COHORT = (
    REPO_ROOT
    / "static"
    / "eedi-static"
    / "outputs"
    / "eedi_static_image_student_sim_480x107"
    / "run_20260526_025006"
)
ENEM_CN_COHORT = (
    REPO_ROOT
    / "static"
    / "enem"
    / "outputs"
    / "enem_cn_static_benchmark"
    / "qwen35_en_text_plus_image_7200x24_20260530"
)
XES_QUESTIONS_PATH = REPO_ROOT / "XES3G5M" / "metadata" / "questions.json"


@dataclass(frozen=True)
class Example:
    dataset_name: str
    student_id: str
    question_id: str
    history_summary: str
    profile_text: str
    question_text: str
    image_path: str | None
    answer_space: list[str]
    real_answer: str
    correct_answer: str
    real_is_correct: bool


def build_prompt_payload(example: Example) -> dict[str, Any]:
    return {
        "dataset_name": example.dataset_name,
        "student_id": example.student_id,
        "question_id": example.question_id,
        "history_summary": example.history_summary,
        "profile_text": example.profile_text,
        "question_text": example.question_text,
        "image_path": example.image_path,
        "answer_space": example.answer_space,
    }


def load_examples(dataset_name: str, max_students: int | None, max_items: int | None) -> list[Example]:
    if dataset_name == "xes":
        return load_xes_examples(max_students=max_students, max_items=max_items)
    if dataset_name == "eedi_static":
        return load_eedi_static_examples(max_students=max_students, max_items=max_items)
    if dataset_name == "enem_cn":
        return load_enem_cn_examples(max_students=max_students, max_items=max_items)
    raise ValueError(f"unknown dataset: {dataset_name}")


def load_xes_examples(max_students: int | None, max_items: int | None) -> list[Example]:
    required = [XES_COHORT / "benchmark_students.jsonl", XES_QUESTIONS_PATH]
    _require_files(required)
    question_lookup = _load_xes_questions(XES_QUESTIONS_PATH)
    rows = _read_jsonl(XES_COHORT / "benchmark_students.jsonl")
    examples: list[Example] = []
    for student in _limit(rows, max_students):
        student_id = _required_str(student, "student_id")
        history_summary = _summarize_xes_history(student)
        profile_text = _xes_profile_text(student)
        for pair in _limit(_required_list(student, "test"), max_items):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"XES test item must be [question_id, correctness]: student_id={student_id}")
            question_id = str(pair[0])
            real_is_correct = _required_bool_value(pair[1], f"student_id={student_id} question_id={question_id}")
            question = question_lookup.get(question_id)
            if question is None:
                raise KeyError(f"XES question missing metadata: question_id={question_id}")
            correct_answer = _join_answers(_required_list(question, "answer"))
            real_answer = correct_answer if real_is_correct else "__incorrect_or_unobserved_answer__"
            examples.append(
                Example(
                    dataset_name="xes",
                    student_id=student_id,
                    question_id=question_id,
                    history_summary=history_summary,
                    profile_text=profile_text,
                    question_text=_format_question_text(question),
                    image_path=None,
                    answer_space=_answer_space_from_xes_question(question),
                    real_answer=real_answer,
                    correct_answer=correct_answer,
                    real_is_correct=real_is_correct,
                )
            )
    if not examples:
        raise ValueError("no XES examples loaded")
    return examples


def load_eedi_static_examples(max_students: int | None, max_items: int | None) -> list[Example]:
    required = [
        EEDI_STATIC_COHORT / "benchmark_students.jsonl",
        EEDI_STATIC_COHORT / "questions.jsonl",
        EEDI_STATIC_COHORT / "student_models.jsonl",
    ]
    _require_files(required)
    question_lookup = _read_jsonl_lookup(EEDI_STATIC_COHORT / "questions.jsonl", "question_id")
    model_lookup = _read_jsonl_lookup(EEDI_STATIC_COHORT / "student_models.jsonl", "student_id")
    rows = _read_jsonl(EEDI_STATIC_COHORT / "benchmark_students.jsonl")
    examples: list[Example] = []
    for student in _limit(rows, max_students):
        student_id = _required_str(student, "student_id")
        profile_text = _profile_text_from_model(model_lookup.get(student_id), student)
        history_summary = _summarize_eedi_history(student)
        for item in _limit(_required_list(student, "test"), max_items):
            if not isinstance(item, dict):
                raise ValueError(f"Eedi-static test item must be object: student_id={student_id}")
            question_id = _required_str(item, "question_id")
            question = question_lookup.get(question_id)
            if question is None:
                raise KeyError(f"Eedi-static question missing metadata: question_id={question_id}")
            examples.append(
                Example(
                    dataset_name="eedi_static",
                    student_id=student_id,
                    question_id=question_id,
                    history_summary=history_summary,
                    profile_text=profile_text,
                    question_text=_question_text_with_subjects(question),
                    image_path=_optional_existing_image(question.get("image_path")),
                    answer_space=_required_str_list(question, "answer_space", default=["1", "2", "3", "4"]),
                    real_answer=_required_str(item, "answer_value"),
                    correct_answer=_required_str(item, "correct_answer"),
                    real_is_correct=_required_bool(item, "is_correct"),
                )
            )
    if not examples:
        raise ValueError("no Eedi-static examples loaded")
    return examples


def load_enem_cn_examples(max_students: int | None, max_items: int | None) -> list[Example]:
    required = [
        ENEM_CN_COHORT / "benchmark_students.jsonl",
        ENEM_CN_COHORT / "questions.jsonl",
        ENEM_CN_COHORT / "student_models.jsonl",
    ]
    _require_files(required)
    question_lookup = _read_jsonl_lookup(ENEM_CN_COHORT / "questions.jsonl", "question_id")
    model_lookup = _read_jsonl_lookup(ENEM_CN_COHORT / "student_models.jsonl", "student_id")
    rows = _read_jsonl(ENEM_CN_COHORT / "benchmark_students.jsonl")
    examples: list[Example] = []
    for student in _limit(rows, max_students):
        student_id = _required_str(student, "student_id")
        profile_text = _profile_text_from_model(model_lookup.get(student_id), student)
        history_summary = _summarize_enem_history(student)
        for item in _limit(_required_list(student, "test"), max_items):
            if not isinstance(item, dict):
                raise ValueError(f"ENEM test item must be object: student_id={student_id}")
            question_id = _required_str(item, "question_id")
            question = question_lookup.get(question_id)
            if question is None:
                raise KeyError(f"ENEM question missing metadata: question_id={question_id}")
            examples.append(
                Example(
                    dataset_name="enem_cn",
                    student_id=student_id,
                    question_id=question_id,
                    history_summary=history_summary,
                    profile_text=profile_text,
                    question_text=_question_text_with_subjects(question),
                    image_path=_optional_existing_image(question.get("image_path")),
                    answer_space=_required_str_list(question, "answer_space"),
                    real_answer=_required_str(item, "answer_value"),
                    correct_answer=_required_str(item, "correct_answer"),
                    real_is_correct=_required_bool(item, "is_correct"),
                )
            )
    if not examples:
        raise ValueError("no ENEM examples loaded")
    return examples


def _require_files(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(str(path))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be object: {path}:{line_no}")
            rows.append(row)
    if not rows:
        raise ValueError(f"empty JSONL file: {path}")
    return rows


def _read_jsonl_lookup(path: Path, key: str) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        row_key = _required_str(row, key)
        lookup[row_key] = row
    return lookup


def _load_xes_questions(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"XES questions must be dict: {path}")
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _limit(rows: list[Any], max_n: int | None) -> list[Any]:
    if max_n is None:
        return rows
    if max_n < 0:
        raise ValueError("max limit must be non-negative")
    return rows[:max_n]


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        raise KeyError(key)
    text = str(value).strip()
    if not text:
        raise ValueError(f"missing non-empty string field: {key}")
    return text


def _required_bool(row: dict[str, Any], key: str) -> bool:
    if key not in row:
        raise KeyError(key)
    return _required_bool_value(row[key], key)


def _required_bool_value(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"expected bool for {label}")
    return value


def _required_list(row: dict[str, Any], key: str) -> list[Any]:
    value = row.get(key)
    if not isinstance(value, list):
        raise ValueError(f"missing list field: {key}")
    return value


def _required_str_list(row: dict[str, Any], key: str, default: list[str] | None = None) -> list[str]:
    value = row.get(key, default)
    if not isinstance(value, list) or not value:
        raise ValueError(f"missing non-empty list field: {key}")
    return [str(item) for item in value]


def _join_answers(values: list[Any]) -> str:
    if not values:
        raise ValueError("answer list cannot be empty")
    return ";".join(_strip_math_marks(str(value)) for value in values)


def _strip_math_marks(text: str) -> str:
    return text.replace("$$", "").strip()


def _format_question_text(question: dict[str, Any]) -> str:
    text = _required_str(question, "content")
    options = question.get("options") or {}
    if isinstance(options, dict) and options:
        option_lines = [f"{key}. {value}" for key, value in sorted(options.items())]
        return text + "\nOptions:\n" + "\n".join(option_lines)
    return text


def _answer_space_from_xes_question(question: dict[str, Any]) -> list[str]:
    options = question.get("options") or {}
    if isinstance(options, dict) and options:
        return [str(key) for key in sorted(options)]
    return ["free_text"]


def _summarize_xes_history(student: dict[str, Any]) -> str:
    summary = student.get("history_summary")
    if isinstance(summary, dict):
        return _safe_json_summary(
            {
                "total_history_items": summary.get("total_history_items"),
                "history_accuracy": summary.get("history_accuracy"),
                "history_level": summary.get("history_level"),
                "module_accuracy": summary.get("module_accuracy"),
                "type_accuracy": summary.get("type_accuracy"),
                "guessed_error_tendencies": summary.get("guessed_error_tendencies"),
            }
        )
    history = _required_list(student, "history")
    correct = sum(1 for pair in history if isinstance(pair, list) and len(pair) == 2 and pair[1] is True)
    return f"history_items={len(history)}; history_accuracy={correct / len(history):.3f}"


def _xes_profile_text(student: dict[str, Any]) -> str:
    persona = student.get("enhanced_persona")
    if isinstance(persona, dict):
        return _profile_text_from_model(persona, student)
    return _summarize_xes_history(student)


def _summarize_eedi_history(student: dict[str, Any]) -> str:
    return _summarize_object_history(student, "EEDI history anchor")


def _summarize_enem_history(student: dict[str, Any]) -> str:
    return _summarize_object_history(student, "ENEM calibration history")


def _summarize_object_history(student: dict[str, Any], label: str) -> str:
    history = _required_list(student, "history")
    accuracy = student.get("history_accuracy")
    if accuracy is None:
        correct = sum(1 for row in history if isinstance(row, dict) and row.get("is_correct") is True)
        accuracy = correct / len(history) if history else 0.0
    topics: dict[str, int] = {}
    for row in history:
        if isinstance(row, dict):
            topic = str(row.get("subject_leaf") or row.get("competency_short_name") or row.get("skill_code") or "unknown")
            topics[topic] = topics.get(topic, 0) + 1
    top_topics = sorted(topics.items(), key=lambda item: (-item[1], item[0]))[:8]
    return _safe_json_summary({"label": label, "history_count": len(history), "history_accuracy": accuracy, "top_history_topics": top_topics})


def _profile_text_from_model(model: dict[str, Any] | None, fallback: dict[str, Any]) -> str:
    source = model if isinstance(model, dict) else fallback
    visible = {
        "grade": source.get("grade"),
        "academic_level": source.get("academic_level") or source.get("ability_level"),
        "weak_subjects": source.get("weak_subjects") or source.get("weak_skill_areas"),
        "strong_subjects": source.get("strong_subjects") or source.get("strong_skill_areas"),
        "raw_summary": source.get("raw_summary"),
        "anchor_summary": source.get("math_anchor_profile_summary") or source.get("domain_anchor_profile_summary"),
        "self_efficacy": _nested_text(source.get("self_efficacy_analysis")),
        "srl": _nested_text(source.get("srl_analysis")),
        "control_value": _nested_text(source.get("control_value_analysis")),
        "response_directness": source.get("response_directness_description"),
        "capability_profile": source.get("math_task_capability_profile") or source.get("science_task_capability_profile"),
    }
    return _safe_json_summary(visible)


def _nested_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: item for key, item in value.items() if isinstance(item, (str, int, float, bool, list))}
    return value


def _question_text_with_subjects(question: dict[str, Any]) -> str:
    parts = [_required_str(question, "question_text")]
    subject_bits = [
        question.get("subject_top"),
        question.get("subject_leaf"),
        question.get("skill_code"),
        question.get("skill_summary"),
        question.get("competency_short_name"),
        question.get("competency_focus"),
    ]
    visible_subjects = [str(bit) for bit in subject_bits if bit]
    if visible_subjects:
        parts.append("Visible topic metadata: " + " | ".join(visible_subjects))
    return "\n\n".join(parts)


def _optional_existing_image(value: Any) -> str | None:
    if value is None:
        return None
    path = Path(str(value))
    if not path.exists():
        raise FileNotFoundError(str(path))
    return str(path)


def _safe_json_summary(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _remove_forbidden_words(encoded)


def _remove_forbidden_words(text: str) -> str:
    forbidden_patterns = [
        r'"correct_answer"\s*:\s*"[^"]*",?\s*',
        r'"answer_value"\s*:\s*"[^"]*",?\s*',
        r'"is_correct"\s*:\s*(true|false),?\s*',
        r"'correct_answer'\s*:\s*'[^']*',?\s*",
        r"'answer_value'\s*:\s*'[^']*',?\s*",
        r"'is_correct'\s*:\s*(True|False),?\s*",
        r'"test_count"\s*:\s*\d+,?\s*',
        r"'test_count'\s*:\s*\d+,?\s*",
    ]
    cleaned = text
    for pattern in forbidden_patterns:
        cleaned = re.sub(pattern, "", cleaned)
    return cleaned
