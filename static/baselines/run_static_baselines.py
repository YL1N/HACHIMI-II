from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from static.baselines.baseline_specs import BASELINE_NAMES, DATASET_NAMES, get_baseline_spec
    from static.baselines.dataset_adapters import Example, build_prompt_payload, load_examples
    from static.baselines.llm_io import LLMConfig, LLMJSONError, call_openai_compatible_json
    from static.baselines.prompt_builders import build_prompt_messages, write_prompt_templates
    from static.xes.src.evaluation import is_prediction_correct
else:
    from .baseline_specs import BASELINE_NAMES, DATASET_NAMES, get_baseline_spec
    from .dataset_adapters import Example, build_prompt_payload, load_examples
    from .llm_io import LLMConfig, LLMJSONError, call_openai_compatible_json
    from .prompt_builders import build_prompt_messages, write_prompt_templates
    from ..xes.src.evaluation import is_prediction_correct


def run_baseline(
    dataset: str,
    baseline: str,
    output_root: Path,
    llm_base_url: str,
    llm_model: str,
    llm_api_key: str,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    max_students: int | None,
    max_items: int | None,
    max_concurrency: int,
    dry_run: bool,
    max_retries: int = 2,
    run_dir: Path | None = None,
    resume: bool = False,
    progress_every: int = 100,
) -> Path:
    if dataset not in DATASET_NAMES:
        raise ValueError(f"unknown dataset: {dataset}")
    spec = get_baseline_spec(baseline)
    examples = load_examples(dataset, max_students=max_students, max_items=max_items)
    run_dir = run_dir or output_root / dataset / baseline / time.strftime("run_%Y%m%d_%H%M%S")
    if run_dir.exists() and not resume:
        raise FileExistsError(f"run_dir already exists; use --resume to continue: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    write_prompt_templates(run_dir / "prompt_templates")
    config = {
        "dataset": dataset,
        "baseline": baseline,
        "baseline_family": spec.family,
        "output_root": str(output_root),
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "llm_api_key": "***" if llm_api_key else "",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout_s": timeout_s,
        "max_students": max_students,
        "max_items": max_items,
        "max_concurrency": max_concurrency,
        "max_retries": max_retries,
        "dry_run": dry_run,
        "resume": resume,
        "n_examples": len(examples),
        "generation_visible_fields": list(spec.generation_visible_fields),
        "generation_forbidden_fields": list(spec.generation_forbidden_fields),
    }
    _write_json(run_dir / "run_config.json", config)
    llm_config = LLMConfig(
        base_url=llm_base_url,
        model=llm_model,
        api_key=llm_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )
    predictions_path = run_dir / "predictions.jsonl"
    eval_rows_path = run_dir / "eval_rows.jsonl"
    failures_path = run_dir / "failure_cases.jsonl"
    progress_path = run_dir / "progress.json"
    predictions: list[dict[str, Any]] = _read_jsonl(predictions_path) if resume else []
    eval_rows: list[dict[str, Any]] = _read_jsonl(eval_rows_path) if resume else []
    failures: list[dict[str, Any]] = _read_jsonl(failures_path) if resume else []
    if not resume:
        for path in (predictions_path, eval_rows_path, failures_path):
            path.write_text("", encoding="utf-8")
    else:
        for path in (predictions_path, eval_rows_path, failures_path):
            if not path.exists():
                path.write_text("", encoding="utf-8")
    completed_keys = {
        (str(row["student_id"]), str(row["question_id"])) for row in predictions
    }
    failed_keys = {
        (str(row["student_id"]), str(row["question_id"])) for row in failures
    }
    pending_examples = [
        example
        for example in examples
        if (example.student_id, example.question_id) not in completed_keys
        and (example.student_id, example.question_id) not in failed_keys
    ]
    _write_progress(
        progress_path,
        total=len(examples),
        completed=len(predictions),
        failed=len(failures),
        pending=len(pending_examples),
    )
    worker_count = max(1, max_concurrency)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_example = {
            executor.submit(_run_one_with_retries, example, baseline, spec.family, llm_config, dry_run, max_retries): example
            for example in pending_examples
        }
        for future in as_completed(future_to_example):
            example = future_to_example[future]
            try:
                prediction, eval_row = future.result()
            except (LLMJSONError, RuntimeError, OSError, KeyError, ValueError) as error:
                failures.append(
                    {
                        "dataset_name": example.dataset_name,
                        "baseline_name": baseline,
                        "student_id": example.student_id,
                        "question_id": example.question_id,
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                        "retry_count": max_retries,
                    }
                )
                _append_jsonl(failures_path, failures[-1])
                continue
            predictions.append(prediction)
            eval_rows.append(eval_row)
            _append_jsonl(predictions_path, prediction)
            _append_jsonl(eval_rows_path, eval_row)
            completed_total = len(predictions) + len(failures)
            if progress_every > 0 and completed_total % progress_every == 0:
                _write_progress(
                    progress_path,
                    total=len(examples),
                    completed=len(predictions),
                    failed=len(failures),
                    pending=max(0, len(examples) - completed_total),
                )
    metrics = compute_metrics(eval_rows)
    metrics["n_failures"] = len(failures)
    metrics["failure_rate"] = len(failures) / len(examples) if examples else None
    _write_json(run_dir / "metrics.json", metrics)
    _write_progress(
        progress_path,
        total=len(examples),
        completed=len(predictions),
        failed=len(failures),
        pending=max(0, len(examples) - len(predictions) - len(failures)),
    )
    return run_dir


def _run_one_with_retries(
    example: Example,
    baseline: str,
    baseline_family: str,
    llm_config: LLMConfig,
    dry_run: bool,
    max_retries: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            prediction, eval_row = _run_one(example, baseline, baseline_family, llm_config, dry_run)
            prediction["retry_count"] = attempt
            eval_row["retry_count"] = attempt
            return prediction, eval_row
        except (LLMJSONError, RuntimeError, OSError, KeyError, ValueError) as error:
            last_error = error
            if attempt < max_retries:
                time.sleep(min(2.0, 0.2 * (attempt + 1)))
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry loop exited unexpectedly")


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n_predictions = len(rows)
    students = {str(row["student_id"]) for row in rows}
    questions = {str(row["question_id"]) for row in rows}
    real_correct = [_as_bool(row["real_is_correct"]) for row in rows]
    pred_correct = [_as_bool(row["pred_is_correct"]) for row in rows]
    consistent = [real == pred for real, pred in zip(real_correct, pred_correct)]
    answer_match = [_as_bool(row["matches_real_answer"]) for row in rows]
    violations = [_as_bool(row["violation"]) for row in rows]
    retries = [int(row.get("retry_count", 0)) for row in rows]
    return {
        "n_predictions": n_predictions,
        "n_students": len(students),
        "n_questions": len(questions),
        "real_accuracy": _rate(real_correct),
        "pred_accuracy": _rate(pred_correct),
        "consistency": _rate(consistent),
        "answer_match": _rate(answer_match),
        "student_accuracy_pearson": _accuracy_corr(rows, group_key="student_id", method="pearson"),
        "student_accuracy_spearman": _accuracy_corr(rows, group_key="student_id", method="spearman"),
        "item_accuracy_pearson": _accuracy_corr(rows, group_key="question_id", method="pearson"),
        "item_accuracy_spearman": _accuracy_corr(rows, group_key="question_id", method="spearman"),
        "violation_rate": _rate(violations),
        "retry_rate": mean(retries) if retries else 0.0,
    }


def _run_one(
    example: Example,
    baseline: str,
    baseline_family: str,
    llm_config: LLMConfig,
    dry_run: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = get_baseline_spec(baseline)
    messages = build_prompt_messages(baseline, example)
    prompt_payload = build_prompt_payload(example)
    if dry_run:
        parsed = _dry_run_prediction(example)
    else:
        parsed = call_openai_compatible_json(messages, example.image_path, llm_config)
    predicted_answer = str(parsed["predicted_answer"]).strip()
    student_response = str(parsed["student_response"]).strip()
    violation = _has_format_violation(predicted_answer, example.answer_space)
    violation_report = _violation_report(predicted_answer, example.answer_space)
    has_options = bool(example.answer_space and example.answer_space != ["free_text"])
    pred_is_correct = is_prediction_correct(
        predicted_answer=predicted_answer,
        gold_answers=[example.correct_answer],
        has_options=has_options,
    )
    matches_real_answer = is_prediction_correct(
        predicted_answer=predicted_answer,
        gold_answers=[example.real_answer],
        has_options=has_options,
    )
    prediction = {
        "baseline_name": baseline,
        "baseline_family": baseline_family,
        "source_reference": spec.source_reference,
        "dataset_name": example.dataset_name,
        "student_id": example.student_id,
        "question_id": example.question_id,
        "question_type": _question_type(example.answer_space),
        "predicted_answer": predicted_answer,
        "student_response": student_response,
        "prompt_type": baseline,
        "input_fields": sorted(prompt_payload.keys()),
        "forbidden_fields": list(spec.generation_forbidden_fields),
        "has_image": bool(example.image_path),
        "violation": violation,
        "violation_report": violation_report,
        "retry_count": 0,
        "gold_answers": [example.correct_answer],
        "evaluation_fields": {
            "real_answer": example.real_answer,
            "correct_answer": example.correct_answer,
            "real_is_correct": example.real_is_correct,
        },
        "metadata": {
            "method_status": spec.method_status,
            "prompt_sha256": _sha256(json.dumps(messages, ensure_ascii=False)),
            "prompt_payload": prompt_payload,
        },
    }
    eval_row = {
        "dataset_name": example.dataset_name,
        "baseline_name": baseline,
        "baseline_family": baseline_family,
        "student_id": example.student_id,
        "question_id": example.question_id,
        "predicted_answer": predicted_answer,
        "real_answer": example.real_answer,
        "correct_answer": example.correct_answer,
        "real_is_correct": example.real_is_correct,
        "pred_is_correct": pred_is_correct,
        "matches_real_answer": matches_real_answer,
        "violation": violation,
        "violation_report": violation_report,
        "retry_count": 0,
    }
    return prediction, eval_row


def _dry_run_prediction(example: Example) -> dict[str, str]:
    answer = _first_legal_answer(example.answer_space)
    return {"predicted_answer": answer, "student_response": answer}


def _first_legal_answer(answer_space: list[str]) -> str:
    if not answer_space:
        raise ValueError("answer_space cannot be empty")
    if answer_space == ["free_text"]:
        return "1"
    return str(answer_space[0])


def _has_format_violation(predicted_answer: str, answer_space: list[str]) -> bool:
    return bool(_violation_report(predicted_answer, answer_space)["has_violation"])


def _violation_report(predicted_answer: str, answer_space: list[str]) -> dict[str, Any]:
    violations: list[str] = []
    if not predicted_answer.strip():
        violations.append("empty_predicted_answer")
    if answer_space and answer_space != ["free_text"]:
        in_space = any(
            is_prediction_correct(
                predicted_answer=predicted_answer,
                gold_answers=[opt],
                has_options=True,
            )
            for opt in answer_space
        )
        if not in_space:
            violations.append("predicted_answer_outside_answer_space")
    return {"has_violation": bool(violations), "violation_types": violations}


def _question_type(answer_space: list[str]) -> str:
    if answer_space == ["free_text"]:
        return "free_text"
    return f"{len(answer_space)}-choice"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _answer_equal(left: str, right: str) -> bool:
    return is_prediction_correct(
        predicted_answer=left,
        gold_answers=[right],
        has_options=False,
    )


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _as_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"expected bool, got {type(value).__name__}")
    return value


def _accuracy_corr(rows: list[dict[str, Any]], group_key: str, method: str) -> float | None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row[group_key]), []).append(row)
    real_values: list[float] = []
    pred_values: list[float] = []
    for group_rows in grouped.values():
        real_values.append(sum(1 for row in group_rows if row["real_is_correct"]) / len(group_rows))
        pred_values.append(sum(1 for row in group_rows if row["pred_is_correct"]) / len(group_rows))
    if len(real_values) < 2:
        return None
    if method == "pearson":
        return _pearson(real_values, pred_values)
    if method == "spearman":
        return _pearson(_ranks(real_values), _ranks(pred_values))
    raise ValueError(f"unknown correlation method: {method}")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = mean(xs)
    mean_y = mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    denominator = denom_x * denom_y
    if denominator == 0:
        return None
    return numerator / denominator


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for original_index, _ in indexed[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
        file.flush()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be object: {path}:{line_no}")
            rows.append(row)
    return rows


def _write_progress(path: Path, total: int, completed: int, failed: int, pending: int) -> None:
    _write_json(
        path,
        {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "updated_at_epoch_s": time.time(),
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run static item-response baselines.")
    parser.add_argument("--dataset", choices=DATASET_NAMES, required=True)
    parser.add_argument("--baseline", choices=BASELINE_NAMES, required=True)
    parser.add_argument("--output_root", type=Path, required=True)
    parser.add_argument("--llm_base_url", required=True)
    parser.add_argument("--llm_model", required=True)
    parser.add_argument("--llm_api_key", default="")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max_tokens", type=int, default=800)
    parser.add_argument("--timeout_s", type=float, default=180.0)
    parser.add_argument("--max_students", type=int, default=None)
    parser.add_argument("--max_items", type=int, default=None)
    parser.add_argument("--max_concurrency", type=int, default=1)
    parser.add_argument("--max_retries", type=int, default=2)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--run_dir", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--progress_every", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    llm_api_key = args.llm_api_key or os.environ.get("INF_API_KEY", "")
    run_dir = run_baseline(
        dataset=args.dataset,
        baseline=args.baseline,
        output_root=args.output_root,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        llm_api_key=llm_api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout_s,
        max_students=args.max_students,
        max_items=args.max_items,
        max_concurrency=args.max_concurrency,
        max_retries=args.max_retries,
        dry_run=args.dry_run,
        run_dir=args.run_dir,
        resume=args.resume,
        progress_every=args.progress_every,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
