from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from baseline_specs import BASELINE_SPECS, EVALUATION_ONLY_FIELDS, FORBIDDEN_FIELDS, get_baseline_spec
from dataset_adapters import (
    DEFAULT_EEDI_ANCHORED_DIALOGUES_PATH,
    DEFAULT_EEDI_DIALOGUE_SUBJECTS_PATH,
    DEFAULT_EEDI_QUESTION_METADATA_PATH,
    DEFAULT_KHAN_DATASET_PATH,
    BaselineExample,
    load_examples,
)
from llm_io import LLMConfig, OpenAICompatClient, parse_student_reply_json
from prompt_builders import build_prompt_payload, check_basic_violations, render_prompt


DRY_RUN_STUDENT_REPLY = "I'm not sure yet."


def main() -> None:
    args = _build_parser().parse_args()
    if not str(args.llm_api_key or "").strip():
        args.llm_api_key = os.environ.get("INF_API_KEY", "")
    _validate_args(args)

    spec = get_baseline_spec(args.baseline)
    run_dir = _create_run_dir(args.output_root, args.dataset, args.baseline, args.run_dir, bool(args.resume))
    failures_path = run_dir / "failure_cases.jsonl"
    predictions_path = run_dir / "predictions.jsonl"
    eval_rows_path = run_dir / "eval_rows.jsonl"
    progress_path = run_dir / "progress.json"
    if not args.resume:
        for path in (failures_path, predictions_path, eval_rows_path):
            path.write_text("", encoding="utf-8")
    else:
        for path in (failures_path, predictions_path, eval_rows_path):
            if not path.exists():
                path.write_text("", encoding="utf-8")
    _write_prompt_templates(run_dir)
    _write_json(run_dir / "run_config.json", _run_config(args, run_dir))

    examples = load_examples(
        dataset_name=args.dataset,
        max_dialogues=_positive_or_none(args.max_dialogues),
        eedi_anchored_dialogues_path=args.eedi_anchored_dialogues_path,
        eedi_question_metadata_path=args.eedi_question_metadata_path,
        eedi_dialogue_subjects_path=args.eedi_dialogue_subjects_path,
        khan_dataset_path=args.khan_dataset_path,
    )
    if args.max_tasks > 0:
        examples = examples[: args.max_tasks]
    if not examples:
        raise ValueError("no tasks selected")
    existing_records = _read_jsonl(predictions_path) if args.resume else []
    existing_failures = _read_jsonl(failures_path) if args.resume else []
    completed_keys = {_record_key(record) for record in existing_records}
    failed_keys = {_record_key(record) for record in existing_failures}
    pending_examples = [
        example
        for example in examples
        if _example_key(example) not in completed_keys and _example_key(example) not in failed_keys
    ]
    _write_progress(
        progress_path,
        total=len(examples),
        completed=len(existing_records),
        failed=len(existing_failures),
        pending=len(pending_examples),
    )

    client = None if args.dry_run else OpenAICompatClient(_llm_config(args))
    new_records = _run_examples(
        examples=pending_examples,
        spec_name=args.baseline,
        client=client,
        dry_run=bool(args.dry_run),
        failures_path=failures_path,
        predictions_path=predictions_path,
        eval_rows_path=eval_rows_path,
        progress_path=progress_path,
        initial_completed=len(existing_records),
        initial_failed=len(existing_failures),
        total=len(examples),
        max_concurrency=int(args.max_concurrency),
        max_retries=int(args.max_retries),
        progress_every=int(args.progress_every),
    )
    records = existing_records + new_records
    _write_turn_level_csv(run_dir / "turn_level_predictions.csv", records)
    _write_json(run_dir / "metrics.json", _build_metrics(records, len(_read_jsonl(failures_path)), len(examples)))
    _write_progress(
        progress_path,
        total=len(examples),
        completed=len(records),
        failed=len(_read_jsonl(failures_path)),
        pending=max(0, len(examples) - len(records) - len(_read_jsonl(failures_path))),
    )
    print(f"[dynamic-baselines] output_dir={run_dir} records={len(records)}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run dynamic tutoring-dialogue baselines.")
    parser.add_argument("--dataset", choices=("eedi_qatd2k", "khan_comta"), required=True)
    parser.add_argument("--baseline", choices=tuple(sorted(BASELINE_SPECS)), required=True)
    parser.add_argument("--output_root", type=str, default=str(Path(__file__).resolve().parent / "outputs"))
    parser.add_argument("--llm_base_url", type=str, default="")
    parser.add_argument("--llm_model", type=str, default="")
    parser.add_argument("--llm_api_key", type=str, default="")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max_tokens", type=int, default=1200)
    parser.add_argument("--timeout_s", type=float, default=120.0)
    parser.add_argument("--max_dialogues", type=int, default=10)
    parser.add_argument("--max_tasks", type=int, default=0)
    parser.add_argument("--max_concurrency", type=int, default=1)
    parser.add_argument("--max_retries", type=int, default=2)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--run_dir", type=str, default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--progress_every", type=int, default=100)
    parser.add_argument("--eedi_anchored_dialogues_path", type=str, default=str(DEFAULT_EEDI_ANCHORED_DIALOGUES_PATH))
    parser.add_argument("--eedi_question_metadata_path", type=str, default=str(DEFAULT_EEDI_QUESTION_METADATA_PATH))
    parser.add_argument("--eedi_dialogue_subjects_path", type=str, default=str(DEFAULT_EEDI_DIALOGUE_SUBJECTS_PATH))
    parser.add_argument("--khan_dataset_path", type=str, default=str(DEFAULT_KHAN_DATASET_PATH))
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if int(args.max_concurrency) < 1:
        raise ValueError("--max_concurrency must be >= 1")
    if int(args.max_dialogues) < 0:
        raise ValueError("--max_dialogues must be >= 0")
    if int(args.max_tasks) < 0:
        raise ValueError("--max_tasks must be >= 0")
    if int(args.progress_every) < 0:
        raise ValueError("--progress_every must be >= 0")
    if int(args.max_retries) < 0:
        raise ValueError("--max_retries must be >= 0")
    if float(args.timeout_s) <= 0:
        raise ValueError("--timeout_s must be > 0")
    if int(args.max_tokens) <= 0:
        raise ValueError("--max_tokens must be > 0")
    if args.dry_run:
        return
    missing = [
        option
        for option, value in (
            ("--llm_base_url", args.llm_base_url),
            ("--llm_model", args.llm_model),
            ("--llm_api_key", args.llm_api_key),
        )
        if not str(value or "").strip()
    ]
    if missing:
        raise ValueError(f"missing required LLM args without --dry_run: {', '.join(missing)}")


def _run_examples(
    examples: list[BaselineExample],
    spec_name: str,
    client: OpenAICompatClient | None,
    dry_run: bool,
    failures_path: Path,
    predictions_path: Path,
    eval_rows_path: Path,
    progress_path: Path,
    initial_completed: int,
    initial_failed: int,
    total: int,
    max_concurrency: int,
    max_retries: int,
    progress_every: int,
) -> list[dict[str, Any]]:
    if not examples:
        return []
    completed = initial_completed
    failed = initial_failed
    if max_concurrency == 1:
        records: list[dict[str, Any]] = []
        for order, example in enumerate(examples):
            record = _run_one_example(
                order=order,
                example=example,
                spec_name=spec_name,
                client=client,
                dry_run=dry_run,
                failures_path=failures_path,
                max_retries=max_retries,
            )
            if record is not None:
                records.append(record)
                _append_jsonl(predictions_path, record)
                _append_jsonl(eval_rows_path, _build_eval_row(record))
                completed += 1
            else:
                failed += 1
            if progress_every > 0 and (completed + failed) % progress_every == 0:
                _write_progress(
                    progress_path,
                    total=total,
                    completed=completed,
                    failed=failed,
                    pending=max(0, total - completed - failed),
                )
        return records

    records_by_order: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(max_concurrency, len(examples))) as executor:
        futures = {
            executor.submit(
                _run_one_example,
                order,
                example,
                spec_name,
                client,
                dry_run,
                failures_path,
                max_retries,
            ): order
            for order, example in enumerate(examples)
        }
        for future in as_completed(futures):
            record = future.result()
            if record is not None:
                records_by_order[int(record["metadata"]["task_order"])] = record
                _append_jsonl(predictions_path, record)
                _append_jsonl(eval_rows_path, _build_eval_row(record))
                completed += 1
            else:
                failed += 1
            if progress_every > 0 and (completed + failed) % progress_every == 0:
                _write_progress(
                    progress_path,
                    total=total,
                    completed=completed,
                    failed=failed,
                    pending=max(0, total - completed - failed),
                )
    return [records_by_order[index] for index in sorted(records_by_order)]


def _run_one_example(
    order: int,
    example: BaselineExample,
    spec_name: str,
    client: OpenAICompatClient | None,
    dry_run: bool,
    failures_path: Path,
    max_retries: int,
) -> dict[str, Any] | None:
    spec = get_baseline_spec(spec_name)
    prompt = render_prompt(example, spec)
    payload = build_prompt_payload(example, spec)
    retry_count = 0
    raw_response = ""
    last_traceback = ""
    for attempt in range(max_retries + 1):
        retry_count = attempt
        try:
            if dry_run:
                pred_turn = DRY_RUN_STUDENT_REPLY
                raw_response = json.dumps({"student_reply": pred_turn}, ensure_ascii=False)
            else:
                if client is None:
                    raise ValueError("client is required unless dry_run is enabled")
                raw_response = client.complete_json(spec.system_message, prompt)
                pred_turn = parse_student_reply_json(raw_response)
            break
        except Exception as exc:
            last_traceback = traceback.format_exc()
            if attempt < max_retries:
                time.sleep(min(2.0, 0.2 * (attempt + 1)))
                continue
            _append_jsonl(
                failures_path,
                {
                    "dataset_name": example.dataset_name,
                    "baseline_name": spec.name,
                    "dialogue_id": example.dialogue_id,
                    "question_id": example.question_id,
                    "intervention_id": example.intervention_id,
                    "turn_idx": example.turn_idx,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": last_traceback,
                    "raw_response": raw_response,
                    "prompt_sha256": _sha256(prompt),
                    "retry_count": retry_count,
                },
            )
            return None

    violation_report = check_basic_violations(pred_turn)
    return {
        "baseline_name": spec.name,
        "baseline_family": spec.family,
        "source_reference": spec.source_reference,
        "dataset_name": example.dataset_name,
        "dialogue_id": example.dialogue_id,
        "question_id": example.question_id,
        "intervention_id": example.intervention_id,
        "turn_idx": example.turn_idx,
        "history": [asdict(turn) for turn in example.history_before_target],
        "pred_turn": pred_turn,
        "prompt_type": spec.prompt_type,
        "input_fields": sorted(payload.keys()),
        "forbidden_fields": list(FORBIDDEN_FIELDS),
        "retry_count": retry_count,
        "violation_report": violation_report,
        "gt_turn": example.gt_turn,
        "evaluation_fields": {
            "gt_turn": example.gt_turn,
            "evaluation_only_fields": list(EVALUATION_ONLY_FIELDS),
        },
        "metadata": {
            "task_order": order,
            "dry_run": dry_run,
            "prompt_sha256": _sha256(prompt),
            "raw_response_sha256": _sha256(raw_response),
            "subjects": payload["subjects"],
            "question_text_chars": len(example.question_text),
            "history_turn_count": len(example.history_before_target),
        },
    }


def _build_metrics(records: list[dict[str, Any]], n_failures: int = 0, n_total: int | None = None) -> dict[str, Any]:
    n_records = len(records)
    n_empty_outputs = sum(1 for record in records if not str(record["pred_turn"]).strip())
    n_violations = sum(
        1
        for record in records
        if bool(record.get("violation_report", {}).get("has_violation"))
    )
    n_retried = sum(1 for record in records if int(record.get("retry_count", 0)) > 0)
    return {
        "n_records": n_records,
        "n_dialogues": len({str(record["dialogue_id"]) for record in records}),
        "n_empty_outputs": n_empty_outputs,
        "violation_rate": n_violations / n_records if n_records else 0.0,
        "retry_rate": n_retried / n_records if n_records else 0.0,
        "n_failures": n_failures,
        "failure_rate": n_failures / n_total if n_total else 0.0,
    }


def _write_turn_level_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "baseline_name",
        "baseline_family",
        "dataset_name",
        "dialogue_id",
        "question_id",
        "intervention_id",
        "turn_idx",
        "pred_turn",
        "gt_turn",
        "violation_report",
        "history",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "baseline_name": record["baseline_name"],
                    "baseline_family": record["baseline_family"],
                    "dataset_name": record["dataset_name"],
                    "dialogue_id": record["dialogue_id"],
                    "question_id": record["question_id"],
                    "intervention_id": record["intervention_id"],
                    "turn_idx": record["turn_idx"],
                    "pred_turn": record["pred_turn"],
                    "gt_turn": record["gt_turn"],
                    "violation_report": json.dumps(record["violation_report"], ensure_ascii=False),
                    "history": json.dumps(record["history"], ensure_ascii=False),
                }
            )


def _write_prompt_templates(run_dir: Path) -> None:
    template_dir = run_dir / "prompt_templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    for spec in BASELINE_SPECS.values():
        text = (
            f"# {spec.name}\n\n"
            f"- family: {spec.family}\n"
            f"- prompt_type: {spec.prompt_type}\n"
            f"- source_reference: {spec.source_reference}\n"
            f"- uses_profile: {spec.uses_profile}\n"
            f"- uses_memory: {spec.uses_memory}\n\n"
            "## System\n\n"
            f"{spec.system_message}\n\n"
            "## Instruction\n\n"
            f"{spec.instruction}\n\n"
            "## Required Output\n\n"
            '{"student_reply": "<one short next student utterance>"}\n'
        )
        (template_dir / f"{spec.name}.md").write_text(text, encoding="utf-8")


def _create_run_dir(output_root: str, dataset: str, baseline: str, run_dir_arg: str, resume: bool) -> Path:
    if run_dir_arg:
        run_dir = Path(run_dir_arg)
        if run_dir.exists() and not resume:
            raise FileExistsError(f"run_dir already exists; use --resume to continue: {run_dir}")
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(output_root) / dataset / baseline / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _run_config(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    return {
        "dataset": args.dataset,
        "baseline": args.baseline,
        "output_root": args.output_root,
        "run_dir": str(run_dir),
        "llm_base_url": args.llm_base_url,
        "llm_model": args.llm_model,
        "llm_api_key": "***" if args.llm_api_key else "",
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "timeout_s": args.timeout_s,
        "max_dialogues": args.max_dialogues,
        "max_tasks": args.max_tasks,
        "max_concurrency": args.max_concurrency,
        "max_retries": args.max_retries,
        "dry_run": args.dry_run,
        "resume": args.resume,
        "progress_every": args.progress_every,
        "eedi_anchored_dialogues_path": args.eedi_anchored_dialogues_path,
        "eedi_question_metadata_path": args.eedi_question_metadata_path,
        "eedi_dialogue_subjects_path": args.eedi_dialogue_subjects_path,
        "khan_dataset_path": args.khan_dataset_path,
        "forbidden_fields": list(FORBIDDEN_FIELDS),
    }


def _llm_config(args: argparse.Namespace) -> LLMConfig:
    return LLMConfig(
        base_url=str(args.llm_base_url),
        model=str(args.llm_model),
        api_key=str(args.llm_api_key),
        temperature=float(args.temperature),
        max_tokens=int(args.max_tokens),
        timeout_s=float(args.timeout_s),
    )


def _positive_or_none(value: int) -> int | None:
    parsed = int(value)
    return parsed if parsed > 0 else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        f.flush()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
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


def _example_key(example: BaselineExample) -> tuple[str, str, str, str]:
    return (
        str(example.dialogue_id),
        str(example.question_id),
        str(example.intervention_id),
        str(example.turn_idx),
    )


def _record_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record["dialogue_id"]),
        str(record["question_id"]),
        str(record["intervention_id"]),
        str(record["turn_idx"]),
    )


def _build_eval_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_name": record["dataset_name"],
        "baseline_name": record["baseline_name"],
        "baseline_family": record["baseline_family"],
        "dialogue_id": record["dialogue_id"],
        "question_id": record["question_id"],
        "intervention_id": record["intervention_id"],
        "turn_idx": record["turn_idx"],
        "pred_turn": record["pred_turn"],
        "gt_turn": record["gt_turn"],
        "violation_report": record["violation_report"],
        "retry_count": record["retry_count"],
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
