from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from .data_loading import EnemStaticQuestion, EnemStaticStudent
from .science_chain import Prediction


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(indexed):
        end = idx + 1
        while end < len(indexed) and indexed[end][1] == indexed[idx][1]:
            end += 1
        avg_rank = (idx + 1 + end) / 2
        for original_idx, _ in indexed[idx:end]:
            ranks[original_idx] = avg_rank
        idx = end
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return _pearson(_rank(xs), _rank(ys))


def evaluate_predictions(
    predictions: list[Prediction],
    students: list[EnemStaticStudent],
    questions: dict[str, EnemStaticQuestion],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempt_lookup = {
        (student.student_id, attempt.question_id): attempt
        for student in students
        for attempt in student.test
    }
    level_by_student = {student.student_id: student.ability_level for student in students}
    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        key = (prediction.student_id, prediction.question_id)
        attempt = attempt_lookup.get(key)
        if attempt is None:
            raise ValueError(f"prediction has no matching test attempt: {key}")
        simulated_is_correct = prediction.predicted_answer == attempt.correct_answer
        rows.append(
            {
                "student_id": prediction.student_id,
                "ability_level": level_by_student[prediction.student_id],
                "question_id": prediction.question_id,
                "skill_code": questions[prediction.question_id].skill_code,
                "competency_short_name": questions[prediction.question_id].competency_short_name,
                "predicted_answer": prediction.predicted_answer,
                "real_answer_value": attempt.answer_value,
                "correct_answer": attempt.correct_answer,
                "real_is_correct": attempt.is_correct,
                "simulated_is_correct": simulated_is_correct,
                "consistency": simulated_is_correct == attempt.is_correct,
                "answer_match": prediction.predicted_answer == attempt.answer_value,
                "student_response": prediction.student_response,
            }
        )

    pred_acc = _mean([1.0 if row["simulated_is_correct"] else 0.0 for row in rows])
    real_acc = _mean([1.0 if row["real_is_correct"] else 0.0 for row in rows])
    consistency = _mean([1.0 if row["consistency"] else 0.0 for row in rows])
    answer_match = _mean([1.0 if row["answer_match"] else 0.0 for row in rows])

    by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_level: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_competency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_student[row["student_id"]].append(row)
        by_question[row["question_id"]].append(row)
        by_level[row["ability_level"]].append(row)
        by_competency[row["competency_short_name"]].append(row)

    student_real: list[float] = []
    student_pred: list[float] = []
    for student_id in sorted(by_student, key=lambda value: int(value)):
        group = by_student[student_id]
        student_real.append(_mean([1.0 if row["real_is_correct"] else 0.0 for row in group]) or 0.0)
        student_pred.append(_mean([1.0 if row["simulated_is_correct"] else 0.0 for row in group]) or 0.0)

    question_real: list[float] = []
    question_pred: list[float] = []
    for question_id in sorted(by_question, key=lambda value: int(value)):
        group = by_question[question_id]
        question_real.append(_mean([1.0 if row["real_is_correct"] else 0.0 for row in group]) or 0.0)
        question_pred.append(_mean([1.0 if row["simulated_is_correct"] else 0.0 for row in group]) or 0.0)

    def group_metrics(group: list[dict[str, Any]]) -> dict[str, float | None | int]:
        return {
            "n": len(group),
            "real_accuracy": _mean([1.0 if row["real_is_correct"] else 0.0 for row in group]),
            "pred_accuracy": _mean([1.0 if row["simulated_is_correct"] else 0.0 for row in group]),
            "consistency": _mean([1.0 if row["consistency"] else 0.0 for row in group]),
            "answer_match": _mean([1.0 if row["answer_match"] else 0.0 for row in group]),
        }

    metrics = {
        "n_predictions": len(rows),
        "n_students": len(by_student),
        "n_questions": len(by_question),
        "real_accuracy": real_acc,
        "pred_accuracy": pred_acc,
        "consistency": consistency,
        "answer_match": answer_match,
        "student_accuracy_pearson": _pearson(student_real, student_pred),
        "student_accuracy_spearman": _spearman(student_real, student_pred),
        "item_accuracy_pearson": _pearson(question_real, question_pred),
        "item_accuracy_spearman": _spearman(question_real, question_pred),
        "per_level": {level: group_metrics(group) for level, group in sorted(by_level.items())},
        "per_competency": {name: group_metrics(group) for name, group in sorted(by_competency.items())},
        "predicted_answer_counts": dict(Counter(row["predicted_answer"] for row in rows)),
        "real_answer_counts": dict(Counter(row["real_answer_value"] for row in rows)),
    }
    return metrics, rows
