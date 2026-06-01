from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass(frozen=True)
class ExtremeFilterResult:
    response_rows: list[dict[str, str]]
    student_ids: list[str]
    item_ids: list[str]
    dropped_students: dict[str, dict[str, object]]
    dropped_items: dict[str, dict[str, object]]
    rounds: list[dict[str, int]]


def compute_raw_score_counters(
    response_rows: list[dict[str, str]],
) -> tuple[Counter, Counter, Counter, Counter]:
    student_raw_score = Counter()
    student_n = Counter()
    item_raw_score = Counter()
    item_n = Counter()
    for row in response_rows:
        student_id = row["student_id"]
        question_id = row["question_id"]
        score = int(row["is_correct"])
        student_raw_score[student_id] += score
        student_n[student_id] += 1
        item_raw_score[question_id] += score
        item_n[question_id] += 1
    return student_raw_score, student_n, item_raw_score, item_n


def filter_extreme_scores(response_rows: list[dict[str, str]]) -> ExtremeFilterResult:
    active_rows = response_rows
    dropped_students: dict[str, dict[str, object]] = {}
    dropped_items: dict[str, dict[str, object]] = {}
    rounds: list[dict[str, int]] = []
    round_index = 0

    while True:
        round_index += 1
        student_raw_score, student_n, item_raw_score, item_n = compute_raw_score_counters(active_rows)

        all_wrong_students = {student_id for student_id in student_n if student_raw_score[student_id] == 0}
        all_right_students = {
            student_id for student_id in student_n if student_raw_score[student_id] == student_n[student_id]
        }
        all_wrong_items = {question_id for question_id in item_n if item_raw_score[question_id] == 0}
        all_right_items = {question_id for question_id in item_n if item_raw_score[question_id] == item_n[question_id]}

        rounds.append(
            {
                "round": round_index,
                "n_students": len(student_n),
                "n_items": len(item_n),
                "n_responses": len(active_rows),
                "dropped_all_wrong_students": len(all_wrong_students),
                "dropped_all_right_students": len(all_right_students),
                "dropped_all_wrong_items": len(all_wrong_items),
                "dropped_all_right_items": len(all_right_items),
            }
        )

        if not all_wrong_students and not all_right_students and not all_wrong_items and not all_right_items:
            break

        for student_id in sorted(all_wrong_students):
            dropped_students.setdefault(student_id, {"reason": "all_wrong", "round": round_index})
        for student_id in sorted(all_right_students):
            dropped_students.setdefault(student_id, {"reason": "all_right", "round": round_index})
        for question_id in sorted(all_wrong_items):
            dropped_items.setdefault(question_id, {"reason": "all_wrong", "round": round_index})
        for question_id in sorted(all_right_items):
            dropped_items.setdefault(question_id, {"reason": "all_right", "round": round_index})

        active_rows = [
            row
            for row in active_rows
            if row["student_id"] not in dropped_students and row["question_id"] not in dropped_items
        ]
        if not active_rows:
            raise ValueError("Extreme-score filtering removed all responses; this module cannot support Rasch estimation.")

    student_ids = sorted({row["student_id"] for row in active_rows})
    item_ids = sorted({row["question_id"] for row in active_rows})
    if len(item_ids) < 2:
        raise ValueError("Rasch fitting requires at least two non-extreme items after filtering.")
    if not student_ids:
        raise ValueError("No non-extreme students remain after filtering.")

    return ExtremeFilterResult(
        response_rows=active_rows,
        student_ids=student_ids,
        item_ids=item_ids,
        dropped_students=dropped_students,
        dropped_items=dropped_items,
        rounds=rounds,
    )


def fit_rasch_jml(
    responses: list[tuple[int, int, int]],
    n_students: int,
    n_items: int,
    max_iter: int = 1000,
) -> tuple[np.ndarray, np.ndarray, float, int, bool]:
    if n_items < 2:
        raise ValueError("Rasch fitting requires at least two items")

    student_idx = np.asarray([row[0] for row in responses], dtype=np.int32)
    item_idx = np.asarray([row[1] for row in responses], dtype=np.int32)
    score = np.asarray([row[2] for row in responses], dtype=np.float64)

    x0 = np.zeros(n_students + n_items - 1, dtype=np.float64)
    tol = 1e-6
    armijo = 1e-4
    min_step = 1e-8

    def unpack(params: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        theta = params[:n_students]
        b = np.zeros(n_items, dtype=np.float64)
        b[:-1] = params[n_students:]
        return theta, b

    def objective_and_grad(params: np.ndarray) -> tuple[float, np.ndarray]:
        theta, b = unpack(params)
        logits = theta[student_idx] - b[item_idx]
        objective = float(np.sum(np.logaddexp(0.0, logits) - score * logits))
        prob = sigmoid(logits)
        residual = prob - score
        grad_theta = np.bincount(student_idx, weights=residual, minlength=n_students)
        grad_b_full = np.bincount(item_idx, weights=-residual, minlength=n_items)
        grad = np.concatenate([grad_theta, grad_b_full[:-1]])
        return objective, grad

    params = x0.copy()
    objective, grad = objective_and_grad(params)
    success = False
    n_iter = 0

    for n_iter in range(1, max_iter + 1):
        grad_norm = float(np.max(np.abs(grad))) if grad.size else 0.0
        if grad_norm <= tol:
            success = True
            break

        step = 1.0
        grad_sq = float(np.dot(grad, grad))
        if grad_sq == 0.0:
            success = True
            break

        while step >= min_step:
            candidate = params - step * grad
            candidate_objective, candidate_grad = objective_and_grad(candidate)
            if candidate_objective <= objective - armijo * step * grad_sq:
                params = candidate
                objective = candidate_objective
                grad = candidate_grad
                break
            step *= 0.5
        else:
            break

    theta, b = unpack(params)
    shift = float(theta.mean()) if theta.size else 0.0
    theta = theta - shift
    b = b - shift
    return theta, b, objective, n_iter, success
