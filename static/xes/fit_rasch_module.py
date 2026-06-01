from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.rasch_fit import compute_raw_score_counters, filter_extreme_scores, fit_rasch_jml


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass(frozen=True)
class RaschFitResult:
    summary: dict[str, object]
    item_rows: list[dict[str, object]]
    student_rows: list[dict[str, object]]


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def build_rasch_module_fit(module_dir: Path, max_iter: int = 1000) -> RaschFitResult:
    response_rows = load_csv_rows(module_dir / "responses_long.csv")
    student_rows = load_csv_rows(module_dir / "student_ability.csv")
    item_rows = json.loads((module_dir / "item_pool.json").read_text(encoding="utf-8"))

    full_student_ids = sorted({row["student_id"] for row in response_rows})
    full_item_ids = sorted({row["question_id"] for row in response_rows})
    filtered = filter_extreme_scores(response_rows)
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
        max_iter=max_iter,
    )

    student_raw_score, student_n, item_raw_score, item_n = compute_raw_score_counters(response_rows)
    est_student_raw_score, est_student_n, est_item_raw_score, est_item_n = compute_raw_score_counters(filtered.response_rows)

    student_ability_lookup = {row["student_id"]: row for row in student_rows}
    item_pool_lookup = {str(row["question_id"]): row for row in item_rows}

    fitted_student_rows = []
    for student_id in full_student_ids:
        source = student_ability_lookup[student_id]
        drop_meta = filtered.dropped_students.get(student_id)
        idx = student_index.get(student_id)
        fitted_student_rows.append(
            {
                "student_id": student_id,
                "rasch_status": "estimated" if idx is not None else "dropped_extreme",
                "theta_hat": float(theta[idx]) if idx is not None else None,
                "ability_level": source["ability_level"],
                "ability_score_proxy": float(source["ability_score_proxy"]),
                "eligible_item_response_count": int(source["eligible_item_response_count"]),
                "raw_score_full": int(student_raw_score[student_id]),
                "raw_accuracy_full": student_raw_score[student_id] / student_n[student_id],
                "raw_score_estimation": int(est_student_raw_score.get(student_id, 0)),
                "raw_accuracy_estimation": (
                    est_student_raw_score[student_id] / est_student_n[student_id] if student_id in est_student_n else None
                ),
                "response_count_full": int(student_n[student_id]),
                "response_count_estimation": int(est_student_n.get(student_id, 0)),
                "excluded_reason": drop_meta["reason"] if drop_meta else "",
                "excluded_round": int(drop_meta["round"]) if drop_meta else None,
            }
        )

    fitted_item_rows = []
    for question_id in full_item_ids:
        source = item_pool_lookup[question_id]
        drop_meta = filtered.dropped_items.get(question_id)
        idx = item_index.get(question_id)
        fitted_item_rows.append(
            {
                "question_id": question_id,
                "rasch_status": "estimated" if idx is not None else "dropped_extreme",
                "b_hat": float(b[idx]) if idx is not None else None,
                "question_type": source["question_type"],
                "primary_route_top": source["primary_route_top"],
                "primary_route_module": source["primary_route_module"],
                "irt_support_total": int(source["irt_support_total"]),
                "irt_support_accuracy": float(source["irt_support_accuracy"]),
                "raw_score_full": int(item_raw_score[question_id]),
                "raw_accuracy_full": item_raw_score[question_id] / item_n[question_id],
                "raw_score_estimation": int(est_item_raw_score.get(question_id, 0)),
                "raw_accuracy_estimation": (
                    est_item_raw_score[question_id] / est_item_n[question_id] if question_id in est_item_n else None
                ),
                "response_count_full": int(item_n[question_id]),
                "response_count_estimation": int(est_item_n.get(question_id, 0)),
                "excluded_reason": drop_meta["reason"] if drop_meta else "",
                "excluded_round": int(drop_meta["round"]) if drop_meta else None,
            }
        )
    fitted_item_rows.sort(
        key=lambda row: (
            row["b_hat"] is None,
            float(row["b_hat"]) if row["b_hat"] is not None else 0.0,
        )
    )

    summary = {
        "module_dir": str(module_dir),
        "module_name": response_rows[0]["primary_route_name"] if response_rows else "",
        "n_students_total": len(full_student_ids),
        "n_items_total": len(full_item_ids),
        "n_responses_total": len(response_rows),
        "n_students_estimation": len(filtered.student_ids),
        "n_items_estimation": len(filtered.item_ids),
        "n_responses_estimation": len(filtered.response_rows),
        "n_students_dropped_extreme": len(filtered.dropped_students),
        "n_items_dropped_extreme": len(filtered.dropped_items),
        "n_students_dropped_all_wrong": sum(
            1 for meta in filtered.dropped_students.values() if meta["reason"] == "all_wrong"
        ),
        "n_students_dropped_all_right": sum(
            1 for meta in filtered.dropped_students.values() if meta["reason"] == "all_right"
        ),
        "n_items_dropped_all_wrong": sum(1 for meta in filtered.dropped_items.values() if meta["reason"] == "all_wrong"),
        "n_items_dropped_all_right": sum(1 for meta in filtered.dropped_items.values() if meta["reason"] == "all_right"),
        "extreme_filter_rounds": filtered.rounds,
        "objective": objective,
        "optimization_iterations": n_iter,
        "optimization_success": success,
        "theta_mean": float(np.mean(theta)),
        "theta_std": float(np.std(theta)),
        "b_mean": float(np.mean(b)),
        "b_std": float(np.std(b)),
    }
    return RaschFitResult(
        summary=summary,
        item_rows=fitted_item_rows,
        student_rows=fitted_student_rows,
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit a first-pass Rasch model for one exported module.")
    parser.add_argument("--module_dir", type=str, required=True)
    parser.add_argument(
        "--output_root",
        type=str,
        default="static/xes/outputs/rasch_module_fits",
    )
    parser.add_argument("--max_iter", type=int, default=1000)
    args = parser.parse_args()

    module_dir = Path(args.module_dir)
    fit = build_rasch_module_fit(module_dir, max_iter=args.max_iter)
    run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "summary.json", fit.summary)
    write_csv(run_dir / "item_parameters.csv", fit.item_rows)
    write_csv(run_dir / "student_parameters.csv", fit.student_rows)

    print(f"Rasch fit completed: {run_dir}")
    print(f"Module: {fit.summary['module_name']}")
    print(f"Students (estimation / total): {fit.summary['n_students_estimation']} / {fit.summary['n_students_total']}")
    print(f"Items (estimation / total): {fit.summary['n_items_estimation']} / {fit.summary['n_items_total']}")
    print(f"Responses (estimation / total): {fit.summary['n_responses_estimation']} / {fit.summary['n_responses_total']}")
    print(f"Dropped extreme students: {fit.summary['n_students_dropped_extreme']}")
    print(f"Dropped extreme items: {fit.summary['n_items_dropped_extreme']}")
    print(f"Optimization success: {fit.summary['optimization_success']}")


if __name__ == "__main__":
    main()
