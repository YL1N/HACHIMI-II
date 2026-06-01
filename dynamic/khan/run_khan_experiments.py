from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KHAN_ROOT = Path(__file__).resolve().parent
EEDI_ROOT = PROJECT_ROOT / "dynamic" / "eedi"
if str(EEDI_ROOT) not in sys.path:
    sys.path.insert(0, str(EEDI_ROOT))

from run_eedi_experiments import (  # noqa: E402
    _execute_turn_prediction_task,
    _execute_turn_prediction_task_until_success,
    _load_existing_failures,
    _load_existing_records,
    _persist_task_failure,
    _persist_task_result,
    _record_sort_key,
)
from src.data_loading import DialogueTurn, TurnPredictionTask  # noqa: E402
from src.evaluation_eedi import write_json, write_turn_level_outputs  # noqa: E402
from src.llm_client import LLMConfig  # noqa: E402


KHAN_NO_ANCHORED_QUESTION_TEXT = (
    "This Khan/CoMTA dialogue has no separate anchored question metadata. "
    "Infer the local mathematical task only from the visible dialogue history "
    "and the latest tutor turn."
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Khan/CoMTA turn-level student simulation with the EEDI dynamic core."
    )
    parser.add_argument(
        "--dataset_path",
        type=str,
        default=str(KHAN_ROOT / "CoMTA_dataset.json"),
    )
    parser.add_argument("--output_dir", type=str, default="")
    parser.add_argument("--max_dialogues", type=int, default=10)
    parser.add_argument("--max_tasks", type=int, default=0)
    parser.add_argument("--max_concurrency", type=int, default=1)
    parser.add_argument("--write_full_outputs_every_n", type=int, default=50)
    parser.add_argument("--llm_base_url", type=str, default="")
    parser.add_argument("--llm_model", type=str, default="")
    parser.add_argument("--llm_api_key", type=str, default="")
    parser.add_argument("--llm_timeout_s", type=float, default=120.0)
    parser.add_argument("--llm_temperature", type=float, default=0.2)
    parser.add_argument("--llm_max_tokens", type=int, default=1200)
    parser.add_argument(
        "--constraint_profile",
        type=str,
        default="default",
        choices=(
            "default",
            "loose",
            "no_specific_error_realization",
            "no_local_wrong_claim_anchor",
            "no_commitment_style",
            "no_style_constraints",
            "minimal_length_only",
        ),
    )
    parser.add_argument("--disable_llm_dynamic_violation_review", action="store_true")
    parser.add_argument("--disable_generation_retry", action="store_true")
    parser.add_argument(
        "--student_context_profile_mode",
        type=str,
        default="full",
        choices=("full", "behavioral_only"),
    )
    parser.add_argument(
        "--tutor_turn_profile_mode",
        type=str,
        default="full",
        choices=("full", "core"),
    )
    parser.add_argument(
        "--interaction_state_mode",
        type=str,
        default="full",
        choices=("full", "core"),
    )
    parser.add_argument(
        "--transition_prediction_mode",
        type=str,
        default="full",
        choices=("full", "core"),
    )
    parser.add_argument(
        "--error_blueprint_mode",
        type=str,
        default="full",
        choices=(
            "full",
            "structure_only",
            "structure_plus_wrong_claim_seed",
            "structure_plus_buggy_rule",
            "structure_no_mechanism",
        ),
    )
    parser.add_argument("--retry_until_success", action="store_true")
    parser.add_argument("--retry_sleep_s", type=float, default=0.5)
    parser.add_argument("--max_retry_attempts", type=int, default=0)
    parser.add_argument("--dry_run", action="store_true")
    return parser


def load_khan_turn_prediction_tasks(
    dataset_path: str | Path,
    max_dialogues: int | None = None,
) -> tuple[list[TurnPredictionTask], dict[tuple[str, int], str]]:
    path = Path(dataset_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Khan/CoMTA dataset must be a JSON list")
    selected = raw[:max_dialogues] if max_dialogues else raw
    tasks: list[TurnPredictionTask] = []
    ground_truth_by_key: dict[tuple[str, int], str] = {}
    for dialogue_index, dialogue in enumerate(selected):
        if not isinstance(dialogue, dict):
            raise ValueError(f"dialogue index={dialogue_index} is not an object")
        test_id = str(dialogue.get("test_id", dialogue_index)).strip()
        if not test_id:
            raise ValueError(f"dialogue index={dialogue_index} has empty test_id")
        dialogue_id = f"khan_{test_id}"
        math_level = str(dialogue.get("math_level", "") or "").strip()
        subjects = [(f"Khan math level: {math_level}", 0)] if math_level else []
        turns = _normalize_khan_turns(dialogue.get("data"), dialogue_index)
        for turn_index, turn in enumerate(turns):
            if turn.role != "student" or turn_index == 0:
                continue
            if turns[turn_index - 1].role != "tutor":
                continue
            tasks.append(
                TurnPredictionTask(
                    dialogue_id=dialogue_id,
                    question_id=test_id,
                    intervention_id="khan",
                    question_text=KHAN_NO_ANCHORED_QUESTION_TEXT,
                    subjects=list(subjects),
                    history=list(turns[:turn_index]),
                    target_turn_index=turn_index,
                )
            )
            ground_truth_by_key[(dialogue_id, turn_index)] = turn.content
    if not tasks:
        raise ValueError("no Khan turn-level student prediction tasks built")
    return tasks, ground_truth_by_key


def _normalize_khan_turns(raw_turns: object, dialogue_index: int) -> list[DialogueTurn]:
    if not isinstance(raw_turns, list):
        raise ValueError(f"dialogue index={dialogue_index} has no data list")
    normalized: list[DialogueTurn] = []
    for raw_turn in raw_turns:
        if not isinstance(raw_turn, dict):
            continue
        raw_role = str(raw_turn.get("role", "") or "").strip()
        role = {"assistant": "tutor", "user": "student"}.get(raw_role)
        content = " ".join(str(raw_turn.get("content", "") or "").split()).strip()
        if role is None or not content:
            continue
        if normalized and normalized[-1].role == role:
            previous = normalized[-1]
            normalized[-1] = DialogueTurn(
                role=role,
                content=f"{previous.content} {content}".strip(),
            )
        else:
            normalized.append(DialogueTurn(role=role, content=content))
    return normalized


def main() -> None:
    args = _build_parser().parse_args()
    _require_llm_args(args)
    max_concurrency = int(args.max_concurrency or 1)
    if max_concurrency < 1:
        raise ValueError("--max_concurrency must be >= 1")

    run_dir = (
        Path(args.output_dir)
        if args.output_dir
        else KHAN_ROOT / "outputs" / datetime.now().strftime("khan_eedi_core_run_%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    tasks, ground_truth_by_key = load_khan_turn_prediction_tasks(
        dataset_path=args.dataset_path,
        max_dialogues=args.max_dialogues,
    )
    if args.max_tasks > 0:
        tasks = tasks[: args.max_tasks]
    if args.dry_run:
        _write_run_metadata(run_dir, args, tasks, dry_run=True)
        print(f"[DryRun] tasks={len(tasks)} output_dir={run_dir}")
        return

    llm_config = LLMConfig(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        timeout_s=args.llm_timeout_s,
        temperature=args.llm_temperature,
        max_tokens=args.llm_max_tokens,
    )
    trace_path = run_dir / "stage_traces.jsonl"
    predictions_path = run_dir / "predictions.jsonl"
    failures_path = run_dir / "task_failures.jsonl"
    retry_events_path = run_dir / "task_retry_events.jsonl"
    output_lock = threading.Lock()
    records = _load_existing_records(predictions_path)
    failures = _load_existing_failures(failures_path)
    completed_keys = {
        (str(record["dialogue_id"]), int(record["turn_idx"])) for record in records
    }
    failed_keys = {
        (str(row["dialogue_id"]), int(row["turn_idx"])) for row in failures
    }
    task_order = {
        (task.dialogue_id, int(task.target_turn_index)): idx for idx, task in enumerate(tasks)
    }
    pending_tasks = [
        task
        for task in tasks
        if (task.dialogue_id, int(task.target_turn_index)) not in completed_keys
        and (task.dialogue_id, int(task.target_turn_index)) not in failed_keys
    ]
    _write_run_metadata(run_dir, args, tasks, dry_run=False)
    print(
        f"[Data] tasks={len(tasks)} completed={len(completed_keys)} "
        f"failed={len(failed_keys)} pending={len(pending_tasks)}"
    )
    completed_since_full_write = 0
    if max_concurrency == 1:
        for task in pending_tasks:
            completed_since_full_write = _run_and_persist_task(
                task=task,
                llm_config=llm_config,
                args=args,
                ground_truth_by_key=ground_truth_by_key,
                trace_path=trace_path,
                predictions_path=predictions_path,
                retry_events_path=retry_events_path,
                failures_path=failures_path,
                records=records,
                failures=failures,
                completed_keys=completed_keys,
                failed_keys=failed_keys,
                total_tasks=len(tasks),
                run_dir=run_dir,
                task_order=task_order,
                completed_since_full_write=completed_since_full_write,
                output_lock=output_lock,
            )
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max_concurrency, len(pending_tasks) or 1)
        ) as executor:
            future_map = {
                executor.submit(_execute_task_for_runner, task, llm_config, args, retry_events_path, output_lock): task
                for task in pending_tasks
            }
            for future in concurrent.futures.as_completed(future_map):
                task = future_map[future]
                try:
                    task_result = future.result()
                    task_result["record"]["gt_turn"] = ground_truth_by_key[task_result["task_key"]]
                except Exception as exc:
                    _persist_task_failure(task, exc, failures_path, failures, failed_keys)
                    continue
                completed_since_full_write = _persist_task_result(
                    task_result=task_result,
                    trace_path=trace_path,
                    predictions_path=predictions_path,
                    records=records,
                    completed_keys=completed_keys,
                    total_tasks=len(tasks),
                    run_dir=run_dir,
                    task_order=task_order,
                    write_full_outputs_every_n=int(args.write_full_outputs_every_n),
                    completed_since_full_write=completed_since_full_write,
                )
    if completed_since_full_write > 0 or not (run_dir / "turn_level_predictions.csv").exists():
        records.sort(key=lambda record: _record_sort_key(record, task_order))
        write_turn_level_outputs(run_dir, records)
    if failures:
        write_json(run_dir / "task_failures_summary.json", {"n_failed_tasks": len(failures)})
    print(f"[Done] output_dir={run_dir}")


def _execute_task_for_runner(
    task: TurnPredictionTask,
    llm_config: LLMConfig,
    args: argparse.Namespace,
    retry_events_path: Path,
    output_lock: threading.Lock,
) -> dict[str, object]:
    if args.retry_until_success:
        return _execute_turn_prediction_task_until_success(
            task=task,
            llm_config=llm_config,
            population_calibration_bank=[],
            population_calibration_top_k=0,
            constraint_profile=str(args.constraint_profile),
            disable_llm_dynamic_violation_review=bool(args.disable_llm_dynamic_violation_review),
            disable_generation_retry=bool(args.disable_generation_retry),
            student_context_profile_mode=str(args.student_context_profile_mode),
            tutor_turn_profile_mode=str(args.tutor_turn_profile_mode),
            interaction_state_mode=str(args.interaction_state_mode),
            transition_prediction_mode=str(args.transition_prediction_mode),
            error_blueprint_mode=str(args.error_blueprint_mode),
            retry_events_path=retry_events_path,
            retry_sleep_s=float(args.retry_sleep_s),
            max_retry_attempts=int(args.max_retry_attempts or 0),
            output_lock=output_lock,
        )
    return _execute_turn_prediction_task(
        task=task,
        llm_config=llm_config,
        population_calibration_bank=[],
        population_calibration_top_k=0,
        constraint_profile=str(args.constraint_profile),
        disable_llm_dynamic_violation_review=bool(args.disable_llm_dynamic_violation_review),
        disable_generation_retry=bool(args.disable_generation_retry),
        student_context_profile_mode=str(args.student_context_profile_mode),
        tutor_turn_profile_mode=str(args.tutor_turn_profile_mode),
        interaction_state_mode=str(args.interaction_state_mode),
        transition_prediction_mode=str(args.transition_prediction_mode),
        error_blueprint_mode=str(args.error_blueprint_mode),
    )


def _run_and_persist_task(
    task: TurnPredictionTask,
    llm_config: LLMConfig,
    args: argparse.Namespace,
    ground_truth_by_key: dict[tuple[str, int], str],
    trace_path: Path,
    predictions_path: Path,
    retry_events_path: Path,
    failures_path: Path,
    records: list[dict[str, object]],
    failures: list[dict[str, object]],
    completed_keys: set[tuple[str, int]],
    failed_keys: set[tuple[str, int]],
    total_tasks: int,
    run_dir: Path,
    task_order: dict[tuple[str, int], int],
    completed_since_full_write: int,
    output_lock: threading.Lock,
) -> int:
    try:
        task_result = _execute_task_for_runner(
            task=task,
            llm_config=llm_config,
            args=args,
            retry_events_path=retry_events_path,
            output_lock=output_lock,
        )
        task_result["record"]["gt_turn"] = ground_truth_by_key[task_result["task_key"]]
    except Exception as exc:
        _persist_task_failure(task, exc, failures_path, failures, failed_keys)
        return completed_since_full_write
    return _persist_task_result(
        task_result=task_result,
        trace_path=trace_path,
        predictions_path=predictions_path,
        records=records,
        completed_keys=completed_keys,
        total_tasks=total_tasks,
        run_dir=run_dir,
        task_order=task_order,
        write_full_outputs_every_n=int(args.write_full_outputs_every_n),
        completed_since_full_write=completed_since_full_write,
    )


def _write_run_metadata(
    run_dir: Path,
    args: argparse.Namespace,
    tasks: list[TurnPredictionTask],
    dry_run: bool,
) -> None:
    write_json(
        run_dir / "resolved_args.json",
        {
            "dataset_path": args.dataset_path,
            "max_dialogues": args.max_dialogues,
            "max_tasks": args.max_tasks,
            "n_selected_tasks": len(tasks),
            "max_concurrency": args.max_concurrency,
            "write_full_outputs_every_n": args.write_full_outputs_every_n,
            "llm_base_url": args.llm_base_url,
            "llm_model": args.llm_model,
            "llm_api_key": "***" if args.llm_api_key else "",
            "llm_timeout_s": args.llm_timeout_s,
            "llm_temperature": args.llm_temperature,
            "llm_max_tokens": args.llm_max_tokens,
            "constraint_profile": args.constraint_profile,
            "disable_llm_dynamic_violation_review": args.disable_llm_dynamic_violation_review,
            "disable_generation_retry": args.disable_generation_retry,
            "student_context_profile_mode": args.student_context_profile_mode,
            "tutor_turn_profile_mode": args.tutor_turn_profile_mode,
            "interaction_state_mode": args.interaction_state_mode,
            "transition_prediction_mode": args.transition_prediction_mode,
            "error_blueprint_mode": args.error_blueprint_mode,
            "retry_until_success": args.retry_until_success,
            "retry_sleep_s": args.retry_sleep_s,
            "max_retry_attempts": args.max_retry_attempts,
            "question_text_policy": KHAN_NO_ANCHORED_QUESTION_TEXT,
            "dry_run": dry_run,
        },
    )
    write_json(
        run_dir / "selected_tasks_preview.json",
        [
            {
                "dialogue_id": task.dialogue_id,
                "turn_idx": task.target_turn_index,
                "question_id": task.question_id,
                "intervention_id": task.intervention_id,
                "question_text": task.question_text,
                "subjects": list(task.subjects),
                "history": [asdict(turn) for turn in task.history],
            }
            for task in tasks[:10]
        ],
    )


def _require_llm_args(args: argparse.Namespace) -> None:
    if args.dry_run:
        return
    missing = [
        name
        for name in ("llm_base_url", "llm_model", "llm_api_key")
        if not str(getattr(args, name, "") or "").strip()
    ]
    if missing:
        raise ValueError(f"missing required LLM args: {', '.join('--' + item for item in missing)}")


if __name__ == "__main__":
    main()
