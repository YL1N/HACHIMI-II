from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from src.image_direct_solve import (
    VisionLLMConfig,
    call_vision_llm,
    compute_metrics,
    count_unresolved_failure_ids,
    extract_prediction_payload,
    load_questions,
)


ROOT = Path(__file__).resolve().parent


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
        file.flush()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Directly solve EEDI-static question images with a vision LLM.")
    parser.add_argument(
        "--config_path",
        default=str(ROOT / "configs" / "eedi_static_common_test_676x265_text_only_clean_20260520.json"),
    )
    parser.add_argument("--output_root", default=str(ROOT / "outputs" / "eedi_static_image_direct_solve"))
    parser.add_argument("--run_dir", default=None)
    parser.add_argument("--max_questions", type=int, default=None)
    parser.add_argument("--llm_base_url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--llm_model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--llm_api_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max_tokens", type=int, default=1024)
    parser.add_argument("--timeout_s", type=float, default=180.0)
    parser.add_argument("--max_concurrency", type=int, default=8)
    parser.add_argument("--task_retry_attempts", type=int, default=3)
    return parser


def run_one(question, llm_config: VisionLLMConfig, task_retry_attempts: int) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt_idx in range(1, task_retry_attempts + 1):
        try:
            raw_text = call_vision_llm(question, llm_config)
            parsed = extract_prediction_payload(raw_text)
            return {
                "question_id": question.question_id,
                "image_path": str(question.image_path),
                "gold_answer": question.gold_answer,
                "selected_answer": parsed["selected_answer"],
                "is_correct": parsed["selected_answer"] == question.gold_answer,
                "confidence": parsed["confidence"],
                "reason": parsed["reason"],
                "raw_model_output": raw_text,
                "attempt_idx": attempt_idx,
                "empirical_accuracy": question.empirical_accuracy,
                "subject_names": question.subject_names,
                "subject_top": question.subject_top,
                "subject_leaf": question.subject_leaf,
            }
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"image direct solve failed after {task_retry_attempts} attempt(s): "
        f"question_id={question.question_id}, error={last_error!r}"
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    if not args.llm_base_url or not args.llm_model:
        raise ValueError("--llm_base_url and --llm_model are required")
    if args.max_concurrency <= 0:
        raise ValueError("--max_concurrency must be positive")
    if args.task_retry_attempts <= 0:
        raise ValueError("--task_retry_attempts must be positive")

    config_path = Path(args.config_path)
    questions = load_questions(config_path, max_questions=args.max_questions)
    run_dir = Path(args.run_dir) if args.run_dir else Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    predictions_path = run_dir / "image_direct_predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"

    existing = read_jsonl(predictions_path)
    completed_ids = {str(row["question_id"]) for row in existing}
    pending = [question for question in questions if question.question_id not in completed_ids]

    llm_config = VisionLLMConfig(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout_s,
    )
    write_json(
        run_dir / "run_config.json",
        {
            "task": "direct_solve_original_question_images_no_student_simulation",
            "config_path": str(config_path.resolve()),
            "n_questions": len(questions),
            "pending_at_start": len(pending),
            "llm_base_url": args.llm_base_url,
            "llm_model": args.llm_model,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "max_concurrency": args.max_concurrency,
            "task_retry_attempts": args.task_retry_attempts,
            "started_or_resumed_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    write_jsonl_path = run_dir / "questions.jsonl"
    if not write_jsonl_path.exists():
        for question in questions:
            append_jsonl(
                write_jsonl_path,
                {
                    "question_id": question.question_id,
                    "image_path": str(question.image_path),
                    "gold_answer": question.gold_answer,
                    "empirical_accuracy": question.empirical_accuracy,
                    "subject_names": question.subject_names,
                },
            )

    print(f"run_dir={run_dir}")
    print(f"questions={len(questions)} completed={len(completed_ids)} pending={len(pending)}")
    failures: list[dict[str, Any]] = []
    if pending:
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            future_to_question = {
                executor.submit(run_one, question, llm_config, args.task_retry_attempts): question
                for question in pending
            }
            for idx, future in enumerate(as_completed(future_to_question), start=1):
                question = future_to_question[future]
                try:
                    row = future.result()
                    append_jsonl(predictions_path, row)
                    if idx % 10 == 0 or idx == len(pending):
                        print(f"completed_pending={idx}/{len(pending)}")
                except Exception as exc:
                    failure = {
                        "question_id": question.question_id,
                        "image_path": str(question.image_path),
                        "error": repr(exc),
                    }
                    failures.append(failure)
                    append_jsonl(failures_path, failure)
                    print(f"failure question_id={question.question_id}: {exc!r}")

    prediction_rows = read_jsonl(predictions_path)
    failure_rows = read_jsonl(failures_path)
    unresolved_failure_ids = count_unresolved_failure_ids(prediction_rows, failure_rows)
    metrics = compute_metrics(prediction_rows, n_questions=len(questions), n_failures=len(unresolved_failure_ids))
    metrics["unresolved_failure_ids"] = sorted(unresolved_failure_ids, key=int)
    write_json(run_dir / "metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
