from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import sys

ENEM_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ENEM_ROOT))

from run_enem_static_benchmark import prediction_key, prediction_row_to_eval_object, write_json, write_jsonl  # noqa: E402
from src.data_loading import build_dataset  # noqa: E402
from src.evaluation import evaluate_predictions  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_no}") from exc
    return rows


def apply_student_shard(students: list[Any], shard_index: int, shard_count: int) -> list[Any]:
    return [student for index, student in enumerate(students) if index % shard_count == shard_index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_path", required=True)
    parser.add_argument("--max_students", type=int, required=True)
    parser.add_argument("--shard_count", type=int, required=True)
    parser.add_argument("--shard_root", required=True)
    parser.add_argument("--merged_run_dir", required=True)
    args = parser.parse_args()

    dataset = build_dataset(config_path=args.config_path, max_students=args.max_students)
    questions = {question_id: dataset.questions[question_id] for question_id in dataset.test_item_ids}
    all_prediction_rows: list[dict[str, Any]] = []
    all_students: list[Any] = []
    shard_manifests: list[dict[str, Any]] = []

    for shard_index in range(args.shard_count):
        shard_dir = Path(args.shard_root) / f"shard_{shard_index:02d}_of_{args.shard_count:02d}"
        prediction_path = shard_dir / "predictions.jsonl"
        metrics_path = shard_dir / "metrics.json"
        if not metrics_path.exists():
            raise FileNotFoundError(f"missing shard metrics: {metrics_path}")
        if not prediction_path.exists():
            raise FileNotFoundError(f"missing shard predictions: {prediction_path}")
        shard_students = apply_student_shard(dataset.students, shard_index, args.shard_count)
        rows = read_jsonl(prediction_path)
        expected = len(shard_students) * len(dataset.test_item_ids)
        unique = len({prediction_key(row) for row in rows})
        if unique != expected:
            raise RuntimeError(
                f"shard prediction count mismatch shard={shard_index}: unique={unique}, expected={expected}"
            )
        all_prediction_rows.extend(rows)
        all_students.extend(shard_students)
        shard_manifests.append(
            {
                "shard_index": shard_index,
                "run_dir": str(shard_dir),
                "n_students": len(shard_students),
                "n_predictions": unique,
            }
        )

    expected_total = len(dataset.students) * len(dataset.test_item_ids)
    all_prediction_rows.sort(key=lambda row: (int(str(row["student_id"])), int(str(row["question_id"]))))
    unique_total = len({prediction_key(row) for row in all_prediction_rows})
    if unique_total != expected_total:
        raise RuntimeError(f"merged prediction count mismatch: unique={unique_total}, expected={expected_total}")
    all_students.sort(key=lambda student: int(str(student.student_id)))
    metrics, eval_rows = evaluate_predictions(
        [prediction_row_to_eval_object(row) for row in all_prediction_rows],
        all_students,
        questions,
    )

    merged_run_dir = Path(args.merged_run_dir)
    merged_run_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(merged_run_dir / "predictions.jsonl", all_prediction_rows)
    write_jsonl(merged_run_dir / "eval_rows.jsonl", eval_rows)
    write_json(merged_run_dir / "metrics.json", metrics)
    write_json(
        merged_run_dir / "shard_manifest.json",
        {
            "config_path": args.config_path,
            "max_students": args.max_students,
            "shard_count": args.shard_count,
            "shards": shard_manifests,
        },
    )
    print(json.dumps({"merged_run_dir": str(merged_run_dir), **metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
