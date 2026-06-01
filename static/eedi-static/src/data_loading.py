from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LEVEL_NAMES = ("poor", "low", "medium", "high")


@dataclass(frozen=True)
class EediStaticQuestion:
    question_id: str
    question_text: str
    image_path: str
    ocr_answer: str
    subject_names: list[str]
    subject_top: str
    subject_leaf: str
    empirical_accuracy: float
    all_train_response_count: int


@dataclass(frozen=True)
class EediStaticAttempt:
    question_id: str
    answer_id: str
    answer_value: str
    correct_answer: str
    is_correct: bool
    subject_leaf: str
    date_answered: str


@dataclass(frozen=True)
class EediStaticStudent:
    student_id: str
    ability_level: str
    ability_score_proxy: float
    history: list[EediStaticAttempt]
    test: list[EediStaticAttempt]
    age_floor: int | None = None
    age_group: str | None = None


@dataclass(frozen=True)
class EediStaticDataset:
    config: dict[str, Any]
    dataset_root: Path
    questions: dict[str, EediStaticQuestion]
    students: list[EediStaticStudent]


def load_json(path: str | Path) -> Any:
    source = Path(path)
    with source.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_dataset_root(config_path: str | Path, config: dict[str, Any]) -> Path:
    raw_root = str(config.get("source_dataset_root") or "").strip()
    if raw_root:
        root = Path(raw_root)
    else:
        root = Path(config_path).resolve().parents[1]
    if not root.exists():
        raise FileNotFoundError(f"EEDI-static dataset root not found: {root}")
    return root


def _selected_student_ids(config: dict[str, Any], max_students: int | None = None) -> list[str]:
    students_by_level = config.get("students_by_level")
    if not isinstance(students_by_level, dict):
        raise ValueError("config requires students_by_level object")
    normalized_by_level: dict[str, list[str]] = {}
    seen: set[str] = set()
    for level in LEVEL_NAMES:
        raw_ids = students_by_level.get(level)
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValueError(f"students_by_level.{level} must be a non-empty list")
        level_ids: list[str] = []
        for raw_id in raw_ids:
            student_id = str(raw_id).strip()
            if not student_id:
                raise ValueError(f"empty student id in level={level}")
            if student_id in seen:
                raise ValueError(f"duplicate selected student id: {student_id}")
            seen.add(student_id)
            level_ids.append(student_id)
        normalized_by_level[level] = level_ids

    if max_students is None:
        return [
            student_id
            for level in LEVEL_NAMES
            for student_id in normalized_by_level[level]
        ]
    if max_students <= 0:
        raise ValueError("max_students must be positive when provided")

    selected: list[str] = []
    cursor = 0
    while len(selected) < max_students:
        level = LEVEL_NAMES[cursor % len(LEVEL_NAMES)]
        level_idx = cursor // len(LEVEL_NAMES)
        if level_idx < len(normalized_by_level[level]):
            selected.append(normalized_by_level[level][level_idx])
        cursor += 1
        if cursor > max_students + sum(len(ids) for ids in normalized_by_level.values()):
            raise ValueError("could not select requested max_students from fixed cohort")
    return selected


def load_questions_from_config(config: dict[str, Any]) -> dict[str, EediStaticQuestion]:
    raw_questions = config.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("config requires non-empty questions list")
    test_question_ids = {str(question_id) for question_id in config.get("test_question_ids", [])}
    if not test_question_ids:
        raise ValueError("config requires non-empty test_question_ids")
    raw_dataset_root = str(config.get("source_dataset_root") or "").strip()
    if not raw_dataset_root:
        raise ValueError("config requires source_dataset_root to resolve question images")
    dataset_root = Path(raw_dataset_root)

    questions: dict[str, EediStaticQuestion] = {}
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise ValueError("question row must be an object")
        question_id = str(raw["QuestionId"])
        if question_id not in test_question_ids:
            continue
        subject_names = [str(value) for value in raw.get("subject_names", [])]
        question_text = str(raw.get("question_text", "")).strip()
        if not question_text:
            raise ValueError(f"empty question_text for QuestionId={question_id}")
        image_path = str(raw.get("image_path") or "").strip()
        if not image_path:
            raise ValueError(f"empty image_path for QuestionId={question_id}")
        resolved_image_path = Path(image_path)
        if not resolved_image_path.is_absolute():
            resolved_image_path = dataset_root / resolved_image_path
        questions[question_id] = EediStaticQuestion(
            question_id=question_id,
            question_text=question_text,
            image_path=str(resolved_image_path),
            ocr_answer=str(raw.get("ocr_answer", "")).strip(),
            subject_names=subject_names,
            subject_top=str(raw.get("subject_top") or "unknown"),
            subject_leaf=str(raw.get("subject_leaf") or "unknown"),
            empirical_accuracy=float(raw.get("empirical_accuracy_all_train", 0.0)),
            all_train_response_count=int(raw.get("all_train_response_count", 0)),
        )
    missing = sorted(test_question_ids - set(questions), key=lambda value: int(value))
    if missing:
        raise ValueError(f"test questions missing from config questions list: {missing[:20]}")
    return questions


def _load_selected_train_attempts(
    train_path: Path,
    selected_student_ids: set[str],
) -> dict[str, list[dict[str, str]]]:
    if not train_path.exists():
        raise FileNotFoundError(f"train data not found: {train_path}")
    attempts_by_student: dict[str, list[dict[str, str]]] = defaultdict(list)
    with train_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"QuestionId", "UserId", "AnswerId", "IsCorrect", "CorrectAnswer", "AnswerValue"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"train data missing columns: expected={sorted(required)}, got={reader.fieldnames}")
        for row in reader:
            student_id = str(row["UserId"])
            if student_id not in selected_student_ids:
                continue
            question_id = str(row["QuestionId"])
            attempts_by_student[student_id].append(
                {
                    "QuestionId": question_id,
                    "AnswerId": str(row["AnswerId"]),
                    "IsCorrect": str(row["IsCorrect"]),
                    "CorrectAnswer": str(row["CorrectAnswer"]),
                    "AnswerValue": str(row["AnswerValue"]),
                }
            )
    missing_students = sorted(selected_student_ids - set(attempts_by_student), key=int)
    if missing_students:
        raise ValueError(f"selected students missing train attempts: {missing_students[:20]}")
    return attempts_by_student


def _load_answer_dates(answer_metadata_path: Path, needed_answer_ids: set[str]) -> dict[str, str]:
    if not answer_metadata_path.exists():
        raise FileNotFoundError(f"answer metadata not found: {answer_metadata_path}")
    dates: dict[str, str] = {}
    with answer_metadata_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"AnswerId", "DateAnswered"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"answer metadata missing columns: expected={sorted(required)}, got={reader.fieldnames}"
            )
        for row in reader:
            answer_id = str(int(float(row["AnswerId"]))) if row.get("AnswerId") else ""
            if answer_id not in needed_answer_ids:
                continue
            date_answered = str(row.get("DateAnswered") or "").strip()
            if not date_answered:
                raise ValueError(f"empty DateAnswered for AnswerId={answer_id}")
            dates[answer_id] = date_answered
            if len(dates) == len(needed_answer_ids):
                break
    missing = sorted(needed_answer_ids - set(dates), key=int)
    if missing:
        raise ValueError(f"missing DateAnswered for selected AnswerIds: {missing[:20]}")
    return dates


def _load_subject_leaf_map(dataset_root: Path) -> dict[str, str]:
    data_root = dataset_root / "raw_data" / "data"
    subject_path = data_root / "metadata" / "subject_metadata.csv"
    question_path = data_root / "metadata" / "question_metadata_task_3_4.csv"
    if not subject_path.exists():
        raise FileNotFoundError(f"subject metadata not found: {subject_path}")
    if not question_path.exists():
        raise FileNotFoundError(f"question metadata not found: {question_path}")

    subjects: dict[str, str] = {}
    with subject_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            subjects[str(row["SubjectId"])] = str(row["Name"])

    subject_leaf_by_question: dict[str, str] = {}
    with question_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            raw_path = json.loads(row["SubjectId"])
            subject_ids = [str(value) for value in raw_path]
            subject_leaf_by_question[str(row["QuestionId"])] = subjects.get(subject_ids[-1], "unknown")
    return subject_leaf_by_question


def _pick_even_history(
    candidates: list[EediStaticAttempt],
    history_size: int,
) -> list[EediStaticAttempt]:
    if history_size <= 0:
        raise ValueError("history_size must be positive")
    if len(candidates) < history_size:
        raise ValueError(f"not enough non-test history: required={history_size}, available={len(candidates)}")
    segment_count = 3
    base_take = history_size // segment_count
    remainder = history_size % segment_count
    selected: list[tuple[int, EediStaticAttempt]] = []
    for segment_idx in range(segment_count):
        start = segment_idx * len(candidates) // segment_count
        end = (segment_idx + 1) * len(candidates) // segment_count
        segment = candidates[start:end]
        take_n = base_take + (1 if segment_idx < remainder else 0)
        if len(segment) < take_n:
            raise ValueError(f"history segment too small: segment={segment_idx}, required={take_n}")
        selected.extend((start + idx, attempt) for idx, attempt in enumerate(segment[:take_n]))
    selected.sort(key=lambda item: item[0])
    return [attempt for _, attempt in selected]


def build_dataset(
    config_path: str | Path,
    history_size: int = 30,
    max_students: int | None = None,
    max_questions: int | None = None,
) -> EediStaticDataset:
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("benchmark config must be a JSON object")
    dataset_root = resolve_dataset_root(config_path, config)
    questions = load_questions_from_config(config)

    selected_student_ids = _selected_student_ids(config, max_students=max_students)
    selected_student_set = set(selected_student_ids)

    test_question_ids = [str(question_id) for question_id in config["test_question_ids"]]
    if max_questions is not None:
        test_question_ids = test_question_ids[:max_questions]
    test_question_set = set(test_question_ids)
    questions = {question_id: questions[question_id] for question_id in test_question_ids}

    train_path = dataset_root / "raw_data" / "data" / "train_data" / "train_task_3_4.csv"
    answer_metadata_path = dataset_root / "raw_data" / "data" / "metadata" / "answer_metadata_task_3_4.csv"
    allowed_question_ids = set(config["test_question_ids"])
    for question in config.get("questions", []):
        if isinstance(question, dict) and "QuestionId" in question:
            allowed_question_ids.add(str(question["QuestionId"]))

    raw_attempts = _load_selected_train_attempts(
        train_path=train_path,
        selected_student_ids=selected_student_set,
    )
    needed_answer_ids = {
        str(row["AnswerId"])
        for attempts in raw_attempts.values()
        for row in attempts
    }
    answer_dates = _load_answer_dates(answer_metadata_path, needed_answer_ids)

    question_subject_leaf = _load_subject_leaf_map(dataset_root)
    question_subject_leaf.update({
        str(row["QuestionId"]): str(row.get("subject_leaf") or "unknown")
        for row in config.get("questions", [])
        if isinstance(row, dict) and "QuestionId" in row
    })
    level_by_student: dict[str, str] = {}
    for level, ids in config["students_by_level"].items():
        for student_id in ids:
            level_by_student[str(student_id)] = str(level)
    score_by_student = {
        str(row["UserId"]): float(row["ability_score_proxy"])
        for row in config.get("students", [])
        if isinstance(row, dict) and "UserId" in row
    }
    age_floor_by_student = {
        str(row["UserId"]): int(row["age_floor"])
        for row in config.get("students", [])
        if isinstance(row, dict) and "UserId" in row and row.get("age_floor") is not None
    }
    age_group_by_student = {
        str(row["UserId"]): str(row["age_group"])
        for row in config.get("students", [])
        if isinstance(row, dict) and "UserId" in row and row.get("age_group") is not None
    }

    students: list[EediStaticStudent] = []
    for student_id in selected_student_ids:
        attempts: list[EediStaticAttempt] = []
        for row in raw_attempts[student_id]:
            answer_id = str(row["AnswerId"])
            question_id = str(row["QuestionId"])
            attempts.append(
                EediStaticAttempt(
                    question_id=question_id,
                    answer_id=answer_id,
                    answer_value=str(row["AnswerValue"]),
                    correct_answer=str(row["CorrectAnswer"]),
                    is_correct=str(row["IsCorrect"]) == "1",
                    subject_leaf=question_subject_leaf.get(question_id, "unknown"),
                    date_answered=answer_dates[answer_id],
                )
            )
        attempts.sort(key=lambda attempt: (attempt.date_answered, int(attempt.answer_id)))
        test_by_question = {attempt.question_id: attempt for attempt in attempts if attempt.question_id in test_question_set}
        missing_test = sorted(test_question_set - set(test_by_question), key=int)
        if missing_test:
            raise ValueError(f"student {student_id} missing test questions: {missing_test[:20]}")
        history_candidates = [attempt for attempt in attempts if attempt.question_id not in test_question_set]
        history = _pick_even_history(history_candidates, history_size)
        test = [test_by_question[question_id] for question_id in test_question_ids]
        students.append(
            EediStaticStudent(
                student_id=student_id,
                ability_level=level_by_student[student_id],
                ability_score_proxy=score_by_student[student_id],
                history=history,
                test=test,
                age_floor=age_floor_by_student.get(student_id),
                age_group=age_group_by_student.get(student_id),
            )
        )

    _validate_dataset(students, questions, history_size, test_question_ids)
    return EediStaticDataset(
        config=config,
        dataset_root=dataset_root,
        questions=questions,
        students=students,
    )


def _validate_dataset(
    students: list[EediStaticStudent],
    questions: dict[str, EediStaticQuestion],
    history_size: int,
    test_question_ids: list[str],
) -> None:
    if not students:
        raise ValueError("no benchmark students built")
    if len(set(test_question_ids)) != len(test_question_ids):
        raise ValueError("duplicate test question ids")
    test_set = set(test_question_ids)
    missing_questions = sorted(test_set - set(questions), key=int)
    if missing_questions:
        raise ValueError(f"test questions missing question records: {missing_questions[:20]}")
    level_counts = Counter(student.ability_level for student in students)
    unknown_levels = sorted(set(level_counts) - set(LEVEL_NAMES))
    if unknown_levels:
        raise ValueError(f"unknown ability levels: {unknown_levels}")
    for student in students:
        if len(student.history) != history_size:
            raise ValueError(f"student {student.student_id} history size mismatch")
        if [attempt.question_id for attempt in student.test] != test_question_ids:
            raise ValueError(f"student {student.student_id} test question order mismatch")
        history_overlap = {attempt.question_id for attempt in student.history}.intersection(test_set)
        if history_overlap:
            raise ValueError(f"student {student.student_id} history overlaps test: {sorted(history_overlap, key=int)}")


def summarize_history(student: EediStaticStudent) -> dict[str, Any]:
    total = len(student.history)
    correct = sum(1 for attempt in student.history if attempt.is_correct)
    subject_total = Counter(attempt.subject_leaf for attempt in student.history)
    subject_correct = Counter(attempt.subject_leaf for attempt in student.history if attempt.is_correct)
    subject_accuracy = {
        subject: subject_correct[subject] / count
        for subject, count in subject_total.items()
    }
    weakest_subjects = [
        subject
        for subject, _ in sorted(subject_accuracy.items(), key=lambda item: (item[1], subject_total[item[0]], item[0]))[:5]
    ]
    strongest_subjects = [
        subject
        for subject, _ in sorted(subject_accuracy.items(), key=lambda item: (-item[1], -subject_total[item[0]], item[0]))[:5]
    ]
    return {
        "student_id": student.student_id,
        "ability_level": student.ability_level,
        "ability_score_proxy": student.ability_score_proxy,
        "age_floor": student.age_floor,
        "age_group": student.age_group,
        "history_size": total,
        "history_accuracy": correct / total if total else 0.0,
        "subject_accuracy": subject_accuracy,
        "weakest_subjects": weakest_subjects,
        "strongest_subjects": strongest_subjects,
    }
