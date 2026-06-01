from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from src.data_loading import load_json
from src.image_direct_solve import compute_direct_metrics, load_direct_questions
from src.llm_client import LLMConfig, OpenAICompatClient
from src.question_text_experiment import (
    load_question_text_manifest,
    solve_translated_question_directly,
    solve_translated_question_with_image_directly,
)


ROOT = Path(__file__).resolve().parent
JSONL_LOCK = Lock()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_LOCK:
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
    parser = argparse.ArgumentParser(description="Directly solve English-translated ENEM question text.")
    parser.add_argument("--config_path", required=True)
    parser.add_argument("--question_text_manifest_path", required=True)
    parser.add_argument("--include_image", action="store_true")
    parser.add_argument("--output_root", default=str(ROOT / "outputs" / "enem_cn_text_direct_solve"))
    parser.add_argument("--run_dir", default=None)
    parser.add_argument("--llm_base_url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--llm_model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--llm_api_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max_tokens", type=int, default=1200)
    parser.add_argument("--timeout_s", type=float, default=180.0)
    parser.add_argument("--max_concurrency", type=int, default=8)
    parser.add_argument("--task_retry_attempts", type=int, default=3)
    return parser


def create_run_dir(args: argparse.Namespace) -> Path:
    run_dir = Path(args.run_dir) if args.run_dir else Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    if not args.llm_base_url or not args.llm_model:
        raise ValueError("--llm_base_url and --llm_model are required")
    config = load_json(args.config_path)
    if not config.get("question_image_manifest_path"):
        raise ValueError("config_path must point to an effective config with question_image_manifest_path")
    run_dir = create_run_dir(args)
    questions = load_direct_questions(args.config_path)
    text_by_id = load_question_text_manifest(args.question_text_manifest_path)
    missing = [question.question_id for question in questions if question.question_id not in text_by_id]
    if missing:
        raise ValueError(f"missing translated question text for question_ids={missing[:10]}")

    predictions_path = run_dir / "text_direct_predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"
    existing = read_jsonl(predictions_path)
    completed_ids = {str(row["question_id"]) for row in existing}
    pending = [question for question in questions if question.question_id not in completed_ids]
    llm = OpenAICompatClient(
        LLMConfig(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            timeout_s=args.timeout_s,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            response_format_json=True,
        )
    )
    write_json(
        run_dir / "run_config.json",
        {
            "task": "enem_english_text_direct_solve_no_student_simulation",
            "config_path": str(Path(args.config_path).resolve()),
            "question_text_manifest_path": str(Path(args.question_text_manifest_path).resolve()),
            "include_image": args.include_image,
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
    print(f"run_dir={run_dir}", flush=True)
    print(f"questions={len(questions)} completed={len(completed_ids)} pending={len(pending)}", flush=True)

    failures: list[dict[str, Any]] = []
    if pending:
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            tasks = {
                executor.submit(
                    run_one,
                    question,
                    text_by_id[question.question_id]["question_text"],
                    llm,
                    args.task_retry_attempts,
                    args.include_image,
                ): question
                for question in pending
            }
            for idx, future in enumerate(as_completed(tasks), start=1):
                question = tasks[future]
                try:
                    append_jsonl(predictions_path, future.result())
                    if idx % 5 == 0 or idx == len(pending):
                        print(f"completed_pending={idx}/{len(pending)}", flush=True)
                except Exception as exc:
                    failure = {"question_id": question.question_id, "item_position": question.item_position, "error": repr(exc)}
                    failures.append(failure)
                    append_jsonl(failures_path, failure)
    if failures:
        raise RuntimeError(f"{len(failures)} direct text solves failed; see {failures_path}")
    rows = read_jsonl(predictions_path)
    rows.sort(key=lambda row: int(row["item_position"]))
    with predictions_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    metrics = compute_direct_metrics(rows, n_questions=len(questions), n_failures=0)
    write_json(run_dir / "metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)


def run_one(
    question,
    question_text: str,
    llm: OpenAICompatClient,
    task_retry_attempts: int,
    include_image: bool,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt_idx in range(1, task_retry_attempts + 1):
        try:
            parsed = (
                solve_translated_question_with_image_directly(question, question_text, llm)
                if include_image
                else solve_translated_question_directly(question, question_text, llm)
            )
            return {
                "question_id": question.question_id,
                "item_position": question.item_position,
                "gold_answer": question.gold_answer,
                "selected_answer": parsed["selected_answer"],
                "is_correct": parsed["selected_answer"] == question.gold_answer,
                "confidence": parsed["confidence"],
                "reason": parsed["reason"],
                "split": question.split,
                "skill_code": question.skill_code,
                "skill_summary": question.skill_summary,
                "competency_short_name": question.competency_short_name,
                "attempt_idx": attempt_idx,
                "input_mode": "english_text_plus_original_image" if include_image else "english_text_only",
            }
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"ENEM text direct solve failed after {task_retry_attempts} attempt(s): "
        f"question_id={question.question_id}, error={last_error!r}"
    )


if __name__ == "__main__":
    main()
