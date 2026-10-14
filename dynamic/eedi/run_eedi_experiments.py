from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.constraint_bundle import compile_behavior_harness
from src.constraint_bundle import BehaviorHarness
from src.data_loading import build_turn_prediction_tasks, load_eedi_dialogues
from src.dialogue_context import build_dialogue_context_state
from src.error_blueprint import build_error_blueprint
from src.error_blueprint import ErrorBlueprint
from src.evaluation_eedi import (
    append_jsonl,
    export_official_eval_csv,
    write_json,
    write_turn_level_outputs,
)
from src.generation import generate_student_turn
from src.llm_client import LLMConfig, OpenAICompatClient
from src.persona_prior import (
    build_persona_prior_summary,
    load_persona_bank,
    persona_prior_summary_to_dict,
)
from src.revisit_controls import (
    apply_error_blueprint_revisit,
    apply_interaction_state_revisit,
    apply_student_context_profile_revisit,
    apply_transition_prediction_revisit,
    apply_tutor_turn_profile_revisit,
)
from src.runtime_paths import (
    EEDI_OUTPUTS_DIR,
    PROJECT_ROOT,
    resolve_eedi_path,
)
from src.student_model import build_student_context_profile
from src.student_turn_state import infer_task_local_state
from src.student_turn_state import TaskLocalLearnerState
from src.transition import predict_state_transition
from src.transition import StateTransitionPrediction
from src.tutor_turn_profile import build_tutor_turn_profile


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run EEDI turn-level student simulation.")
    parser.add_argument("--config", type=str, default="")
    parser.add_argument(
        "--anchored_dialogues_path",
        type=str,
        default=str(
            PROJECT_ROOT
            / "EEDI_data/dynamic/Question-Anchored-Tutoring-Dialogues-2k/anchored-dialogues/train.csv"
        ),
    )
    parser.add_argument(
        "--question_metadata_path",
        type=str,
        default=str(
            PROJECT_ROOT
            / "EEDI_data/dynamic/Question-Anchored-Tutoring-Dialogues-2k/dq-question-metadata.csv"
        ),
    )
    parser.add_argument(
        "--dialogue_subjects_path",
        type=str,
        default=str(
            PROJECT_ROOT
            / "EEDI_data/dynamic/Question-Anchored-Tutoring-Dialogues-2k/dialogue-subjects.csv"
        ),
    )
    parser.add_argument("--max_dialogues", type=int, default=10)
    parser.add_argument("--max_tasks", type=int, default=0)
    parser.add_argument(
        "--task_index_start",
        type=int,
        default=0,
        help="Inclusive zero-based task index after dialogue expansion and max_tasks slicing.",
    )
    parser.add_argument(
        "--task_index_end",
        type=int,
        default=0,
        help="Exclusive zero-based task index after dialogue expansion and max_tasks slicing. 0 means no upper bound.",
    )
    parser.add_argument(
        "--llm_total_concurrency_budget",
        type=int,
        default=0,
        help=(
            "Total concurrency budget for the shared OpenAI-compatible endpoint. "
            "Generation and judge run sequentially, so this is the per-stage cap."
        ),
    )
    parser.add_argument("--max_concurrency", type=int, default=0)
    parser.add_argument("--write_full_outputs_every_n", type=int, default=100)
    parser.add_argument("--llm_judge_batch_size", type=int, default=0)
    parser.add_argument("--output_dir", type=str, default="")
    parser.add_argument("--llm_base_url", type=str, default="")
    parser.add_argument("--llm_model", type=str, default="")
    parser.add_argument("--llm_api_key", type=str, default="")
    parser.add_argument("--llm_api_key_env", type=str, default="")
    parser.add_argument("--llm_timeout_s", type=float, default=120.0)
    parser.add_argument("--llm_temperature", type=float, default=0.2)
    parser.add_argument("--llm_max_tokens", type=int, default=1200)
    parser.add_argument("--embedding_api_base_url", type=str, default="")
    parser.add_argument(
        "--embedding_model",
        type=str,
        default="Qwen/Qwen3-Embedding-8B",
    )
    parser.add_argument("--embedding_api_key", type=str, default="")
    parser.add_argument("--embedding_batch_size", type=int, default=16)
    parser.add_argument("--embedding_timeout_s", type=float, default=60.0)
    parser.add_argument("--embedding_max_retries", type=int, default=3)
    parser.add_argument("--embedding_retry_sleep_s", type=float, default=2.0)
    parser.add_argument(
        "--official_evaluations",
        type=str,
        default="sim-corr-errs",
        help=(
            "Comma-separated official eval names to run after generation. "
            "Default is the theory-focused subset: sim-corr-errs."
        ),
    )
    parser.add_argument(
        "--skip_official_eval",
        action="store_true",
        help="Skip automatic official evaluation after generation.",
    )
    parser.add_argument("--persona_bank_path", type=str, default="")
    parser.add_argument("--persona_matching_top_k", type=int, default=0)
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
    parser.add_argument(
        "--disable_llm_dynamic_violation_review",
        action="store_true",
    )
    parser.add_argument(
        "--disable_generation_retry",
        action="store_true",
    )
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
    parser.add_argument(
        "--ablation_mode",
        type=str,
        default="full",
        choices=(
            "full",
            "without_hachimi_prior",
            "without_task_local_state",
            "without_behavior_harness",
        ),
    )
    parser.add_argument(
        "--retry_until_success",
        action="store_true",
        help="Retry failed generation tasks until they succeed.",
    )
    parser.add_argument(
        "--retry_sleep_s",
        type=float,
        default=0.5,
        help="Sleep interval between task retry attempts when retry_until_success is enabled.",
    )
    parser.add_argument(
        "--max_retry_attempts",
        type=int,
        default=0,
        help="Maximum retry attempts per task when retry_until_success is enabled. 0 means no limit.",
    )
    return parser


def _load_config_defaults(config_path: str) -> dict[str, object]:
    path = resolve_eedi_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid config json: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("config must be a JSON object")
    return raw


def _parse_args() -> argparse.Namespace:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=str, default="")
    bootstrap_args, _ = bootstrap.parse_known_args()

    parser = _build_parser()
    config_defaults: dict[str, object] = {}
    config_path = bootstrap_args.config.strip()
    if not config_path:
        for candidate in (
            PROJECT_ROOT / "dynamic/eedi/configs/run_local.json",
            PROJECT_ROOT / "configs/run_local.json",
        ):
            if candidate.exists():
                config_path = str(candidate)
                break
    if config_path:
        config_defaults = _load_config_defaults(config_path)
        valid_keys = {action.dest for action in parser._actions if action.dest != "help"}
        unknown_keys = sorted(set(config_defaults) - valid_keys)
        if unknown_keys:
            raise ValueError(f"unknown config keys: {unknown_keys}")
        parser.set_defaults(**config_defaults)

    args = parser.parse_args()
    if config_path and not args.config:
        args.config = config_path
    return args


def _require_llm_args(args: argparse.Namespace) -> None:
    missing: list[str] = []
    if not args.llm_base_url.strip():
        missing.append("--llm_base_url")
    if not args.llm_model.strip():
        missing.append("--llm_model")
    if not args.llm_api_key.strip():
        missing.append("--llm_api_key")
    if missing:
        raise ValueError(f"LLM config missing required args: {', '.join(missing)}")


def _resolve_llm_api_key(args: argparse.Namespace) -> None:
    env_name = str(args.llm_api_key_env or "").strip()
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if not env_value:
            raise ValueError(f"missing required environment variable for llm_api_key: {env_name}")
        args.llm_api_key = env_value


def _resolve_llm_concurrency_args(args: argparse.Namespace) -> None:
    requested_total_budget = int(args.llm_total_concurrency_budget or 0)
    generation_override = int(args.max_concurrency or 0)
    judge_override = int(args.llm_judge_batch_size or 0)
    if requested_total_budget < 0:
        raise ValueError("--llm_total_concurrency_budget must be >= 0")
    if generation_override < 0:
        raise ValueError("--max_concurrency must be >= 0")
    if judge_override < 0:
        raise ValueError("--llm_judge_batch_size must be >= 0")

    legacy_candidates = [
        value for value in (generation_override, judge_override) if value > 0
    ]
    effective_total_budget = (
        requested_total_budget if requested_total_budget > 0 else max(legacy_candidates, default=1)
    )
    if generation_override > effective_total_budget:
        raise ValueError(
            "--max_concurrency cannot exceed --llm_total_concurrency_budget"
        )
    if judge_override > effective_total_budget:
        raise ValueError(
            "--llm_judge_batch_size cannot exceed --llm_total_concurrency_budget"
        )

    args.llm_total_concurrency_budget = effective_total_budget
    args.effective_generation_concurrency = (
        generation_override if generation_override > 0 else effective_total_budget
    )
    args.effective_llm_judge_batch_size = (
        judge_override if judge_override > 0 else effective_total_budget
    )


def main() -> None:
    args = _parse_args()
    _resolve_llm_api_key(args)
    _require_llm_args(args)
    _resolve_llm_concurrency_args(args)
    if not args.skip_official_eval:
        _preflight_official_eval_requirements(
            evaluations=args.official_evaluations,
            embedding_api_base_url=args.embedding_api_base_url,
            embedding_model=args.embedding_model,
            embedding_api_key=args.embedding_api_key,
            embedding_batch_size=args.embedding_batch_size,
            embedding_timeout_s=args.embedding_timeout_s,
            embedding_max_retries=args.embedding_max_retries,
            embedding_retry_sleep_s=args.embedding_retry_sleep_s,
    )
    if args.output_dir:
        run_dir = resolve_eedi_path(args.output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = EEDI_OUTPUTS_DIR / datetime.now().strftime("run_%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=False)

    llm_config = LLMConfig(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        timeout_s=args.llm_timeout_s,
        temperature=args.llm_temperature,
        max_tokens=args.llm_max_tokens,
    )
    llm_client = OpenAICompatClient(llm_config)

    dialogues = load_eedi_dialogues(
        anchored_dialogues_path=args.anchored_dialogues_path,
        question_metadata_path=args.question_metadata_path,
        dialogue_subjects_path=args.dialogue_subjects_path,
    )
    tasks, ground_truth_by_key = build_turn_prediction_tasks(
        dialogues,
        max_dialogues=args.max_dialogues,
    )
    if args.max_tasks > 0:
        tasks = tasks[: args.max_tasks]
    if args.task_index_start < 0:
        raise ValueError("--task_index_start must be >= 0")
    if args.task_index_end < 0:
        raise ValueError("--task_index_end must be >= 0")
    if args.task_index_end and args.task_index_end < args.task_index_start:
        raise ValueError("--task_index_end must be >= --task_index_start")
    if args.task_index_start or args.task_index_end:
        end = args.task_index_end if args.task_index_end else len(tasks)
        tasks = tasks[args.task_index_start : end]
    if not tasks:
        raise ValueError("no EEDI tasks selected for execution")
    persona_bank = (
        load_persona_bank(str(resolve_eedi_path(args.persona_bank_path)))
        if str(args.persona_bank_path or "").strip()
        and int(args.persona_matching_top_k or 0) > 0
        else []
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
    if completed_keys:
        print(f"Resuming run_dir={run_dir} with {len(completed_keys)} completed task(s).")
    if failed_keys:
        print(f"Found {len(failed_keys)} previously failed task(s); they will be skipped.")

    write_json(
        run_dir / "resolved_args.json",
        {
            "anchored_dialogues_path": args.anchored_dialogues_path,
            "question_metadata_path": args.question_metadata_path,
            "dialogue_subjects_path": args.dialogue_subjects_path,
            "max_dialogues": args.max_dialogues,
            "max_tasks": args.max_tasks,
            "task_index_start": args.task_index_start,
            "task_index_end": args.task_index_end,
            "llm_total_concurrency_budget": args.llm_total_concurrency_budget,
            "max_concurrency_override": args.max_concurrency or None,
            "effective_generation_concurrency": args.effective_generation_concurrency,
            "write_full_outputs_every_n": args.write_full_outputs_every_n,
            "llm_judge_batch_size_override": args.llm_judge_batch_size or None,
            "effective_llm_judge_batch_size": args.effective_llm_judge_batch_size,
            "config": args.config,
            "llm_base_url": args.llm_base_url,
            "llm_model": args.llm_model,
            "llm_api_key": "***",
            "llm_api_key_env": args.llm_api_key_env,
            "llm_timeout_s": args.llm_timeout_s,
            "llm_temperature": args.llm_temperature,
            "llm_max_tokens": args.llm_max_tokens,
            "embedding_api_base_url": args.embedding_api_base_url,
            "embedding_model": args.embedding_model,
            "embedding_api_key": "***" if args.embedding_api_key else "",
            "embedding_batch_size": args.embedding_batch_size,
            "embedding_timeout_s": args.embedding_timeout_s,
            "embedding_max_retries": args.embedding_max_retries,
            "embedding_retry_sleep_s": args.embedding_retry_sleep_s,
            "official_evaluations": args.official_evaluations,
            "official_eval_input": None,
            "persona_bank_path": args.persona_bank_path,
            "persona_matching_top_k": args.persona_matching_top_k,
            "constraint_profile": args.constraint_profile,
            "disable_llm_dynamic_violation_review": args.disable_llm_dynamic_violation_review,
            "disable_generation_retry": args.disable_generation_retry,
            "student_context_profile_mode": args.student_context_profile_mode,
            "tutor_turn_profile_mode": args.tutor_turn_profile_mode,
            "interaction_state_mode": args.interaction_state_mode,
            "transition_prediction_mode": args.transition_prediction_mode,
            "error_blueprint_mode": args.error_blueprint_mode,
            "ablation_mode": args.ablation_mode,
            "retry_until_success": args.retry_until_success,
            "retry_sleep_s": args.retry_sleep_s,
            "max_retry_attempts": args.max_retry_attempts,
        },
    )

    task_order = {
        (task.dialogue_id, int(task.target_turn_index)): idx for idx, task in enumerate(tasks)
    }
    records.sort(key=lambda record: _record_sort_key(record, task_order))
    pending_tasks = [
        task
        for task in tasks
        if (task.dialogue_id, int(task.target_turn_index)) not in completed_keys
        and (task.dialogue_id, int(task.target_turn_index)) not in failed_keys
    ]
    if pending_tasks:
        print(
            f"Running {len(pending_tasks)} pending task(s) "
            f"with generation_concurrency={args.effective_generation_concurrency} "
            f"(total budget={args.llm_total_concurrency_budget})"
        )
    completed_since_full_write = 0
    if pending_tasks:
        if args.effective_generation_concurrency <= 1:
            for task in pending_tasks:
                try:
                    if args.retry_until_success:
                        task_result = _execute_turn_prediction_task_until_success(
                            task=task,
                            llm_config=llm_config,
                            persona_bank=persona_bank,
                            persona_matching_top_k=int(args.persona_matching_top_k or 0),
                            constraint_profile=str(args.constraint_profile),
                            disable_llm_dynamic_violation_review=bool(
                                args.disable_llm_dynamic_violation_review
                            ),
                            disable_generation_retry=bool(args.disable_generation_retry),
                            student_context_profile_mode=str(args.student_context_profile_mode),
                            tutor_turn_profile_mode=str(args.tutor_turn_profile_mode),
                            interaction_state_mode=str(args.interaction_state_mode),
                            transition_prediction_mode=str(args.transition_prediction_mode),
                            error_blueprint_mode=str(args.error_blueprint_mode),
                            ablation_mode=str(args.ablation_mode),
                            retry_events_path=retry_events_path,
                            retry_sleep_s=float(args.retry_sleep_s),
                            max_retry_attempts=int(args.max_retry_attempts or 0),
                            output_lock=output_lock,
                        )
                    else:
                        task_result = _execute_turn_prediction_task(
                            task,
                            llm_config,
                            persona_bank,
                            int(args.persona_matching_top_k or 0),
                            str(args.constraint_profile),
                            bool(args.disable_llm_dynamic_violation_review),
                            bool(args.disable_generation_retry),
                            str(args.student_context_profile_mode),
                            str(args.tutor_turn_profile_mode),
                            str(args.interaction_state_mode),
                            str(args.transition_prediction_mode),
                            str(args.error_blueprint_mode),
                            str(args.ablation_mode),
                        )
                    task_result["record"]["gt_turn"] = ground_truth_by_key[task_result["task_key"]]
                except Exception as exc:
                    _persist_task_failure(
                        task=task,
                        exc=exc,
                        failures_path=failures_path,
                        failures=failures,
                        failed_keys=failed_keys,
                    )
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
                    write_full_outputs_every_n=args.write_full_outputs_every_n,
                    completed_since_full_write=completed_since_full_write,
                )
        else:
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=min(args.effective_generation_concurrency, len(pending_tasks))
            )
            futures: dict[concurrent.futures.Future[dict[str, object]], object] = {}
            try:
                for task in pending_tasks:
                    if args.retry_until_success:
                        future = executor.submit(
                            _execute_turn_prediction_task_until_success,
                            task,
                            llm_config,
                            persona_bank,
                            int(args.persona_matching_top_k or 0),
                            str(args.constraint_profile),
                            bool(args.disable_llm_dynamic_violation_review),
                            bool(args.disable_generation_retry),
                            str(args.student_context_profile_mode),
                            str(args.tutor_turn_profile_mode),
                            str(args.interaction_state_mode),
                            str(args.transition_prediction_mode),
                            str(args.error_blueprint_mode),
                            str(args.ablation_mode),
                            retry_events_path,
                            float(args.retry_sleep_s),
                            int(args.max_retry_attempts or 0),
                            output_lock,
                        )
                    else:
                        future = executor.submit(
                            _execute_turn_prediction_task,
                            task,
                            llm_config,
                            persona_bank,
                            int(args.persona_matching_top_k or 0),
                            str(args.constraint_profile),
                            bool(args.disable_llm_dynamic_violation_review),
                            bool(args.disable_generation_retry),
                            str(args.student_context_profile_mode),
                            str(args.tutor_turn_profile_mode),
                            str(args.interaction_state_mode),
                            str(args.transition_prediction_mode),
                            str(args.error_blueprint_mode),
                            str(args.ablation_mode),
                        )
                    futures[future] = task
                for future in concurrent.futures.as_completed(futures):
                    task = futures[future]
                    try:
                        task_result = future.result()
                        task_result["record"]["gt_turn"] = ground_truth_by_key[
                            task_result["task_key"]
                        ]
                    except Exception as exc:
                        _persist_task_failure(
                            task=task,
                            exc=exc,
                            failures_path=failures_path,
                            failures=failures,
                            failed_keys=failed_keys,
                        )
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
                        write_full_outputs_every_n=args.write_full_outputs_every_n,
                        completed_since_full_write=completed_since_full_write,
                    )
            except Exception:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            executor.shutdown(wait=True)
    if completed_since_full_write > 0 or not (run_dir / "turn_level_predictions.csv").exists():
        records.sort(key=lambda record: _record_sort_key(record, task_order))
        write_turn_level_outputs(run_dir, records)
    if failures:
        write_json(
            run_dir / "task_failures_summary.json",
            {
                "n_failed_tasks": len(failures),
            },
        )

    official_eval_input = export_official_eval_csv(
        output_dir=run_dir,
        records=records,
        annotated_eedi_dir=PROJECT_ROOT / "external/sim-student-eval/data/annotated/eedi",
    )
    write_json(
        run_dir / "resolved_args.json",
        {
            "anchored_dialogues_path": args.anchored_dialogues_path,
            "question_metadata_path": args.question_metadata_path,
            "dialogue_subjects_path": args.dialogue_subjects_path,
            "max_dialogues": args.max_dialogues,
            "max_tasks": args.max_tasks,
            "llm_total_concurrency_budget": args.llm_total_concurrency_budget,
            "max_concurrency_override": args.max_concurrency or None,
            "effective_generation_concurrency": args.effective_generation_concurrency,
            "write_full_outputs_every_n": args.write_full_outputs_every_n,
            "llm_judge_batch_size_override": args.llm_judge_batch_size or None,
            "effective_llm_judge_batch_size": args.effective_llm_judge_batch_size,
            "config": args.config,
            "llm_base_url": args.llm_base_url,
            "llm_model": args.llm_model,
            "llm_api_key": "***",
            "llm_api_key_env": args.llm_api_key_env,
            "llm_timeout_s": args.llm_timeout_s,
            "llm_temperature": args.llm_temperature,
            "llm_max_tokens": args.llm_max_tokens,
            "embedding_api_base_url": args.embedding_api_base_url,
            "embedding_model": args.embedding_model,
            "embedding_api_key": "***" if args.embedding_api_key else "",
            "embedding_batch_size": args.embedding_batch_size,
            "embedding_timeout_s": args.embedding_timeout_s,
            "embedding_max_retries": args.embedding_max_retries,
            "embedding_retry_sleep_s": args.embedding_retry_sleep_s,
            "official_evaluations": args.official_evaluations,
            "official_eval_input": str(official_eval_input) if official_eval_input else None,
            "skip_official_eval": args.skip_official_eval,
            "persona_bank_path": args.persona_bank_path,
            "persona_matching_top_k": args.persona_matching_top_k,
            "constraint_profile": args.constraint_profile,
            "disable_llm_dynamic_violation_review": args.disable_llm_dynamic_violation_review,
            "disable_generation_retry": args.disable_generation_retry,
            "student_context_profile_mode": args.student_context_profile_mode,
            "tutor_turn_profile_mode": args.tutor_turn_profile_mode,
            "interaction_state_mode": args.interaction_state_mode,
            "transition_prediction_mode": args.transition_prediction_mode,
            "error_blueprint_mode": args.error_blueprint_mode,
            "ablation_mode": args.ablation_mode,
            "retry_until_success": args.retry_until_success,
            "retry_sleep_s": args.retry_sleep_s,
            "max_retry_attempts": args.max_retry_attempts,
        },
    )
    if official_eval_input and not args.skip_official_eval:
        _run_official_eval(
            run_dir=run_dir,
            official_eval_input=official_eval_input,
            evaluations=args.official_evaluations,
            embedding_api_base_url=args.embedding_api_base_url,
            embedding_model=args.embedding_model,
            embedding_api_key=args.embedding_api_key,
            embedding_batch_size=args.embedding_batch_size,
            embedding_timeout_s=args.embedding_timeout_s,
            embedding_max_retries=args.embedding_max_retries,
            embedding_retry_sleep_s=args.embedding_retry_sleep_s,
            llm_judge_batch_size=args.effective_llm_judge_batch_size,
        )
    print(run_dir)


def _execute_turn_prediction_task(
    task,
    llm_config: LLMConfig,
    persona_bank,
    persona_matching_top_k: int,
    constraint_profile: str,
    disable_llm_dynamic_violation_review: bool,
    disable_generation_retry: bool,
    student_context_profile_mode: str,
    tutor_turn_profile_mode: str,
    interaction_state_mode: str,
    transition_prediction_mode: str,
    error_blueprint_mode: str,
    ablation_mode: str = "full",
) -> dict[str, object]:
    llm_client = OpenAICompatClient(llm_config)
    context = build_dialogue_context_state(task)
    tutor_profile = build_tutor_turn_profile(context=context, llm_client=llm_client)
    tutor_profile = apply_tutor_turn_profile_revisit(
        tutor_profile,
        tutor_turn_profile_mode,
    )
    persona_prior_summary = build_persona_prior_summary(
        context=context,
        tutor_profile=tutor_profile,
        persona_bank=[] if ablation_mode == "without_hachimi_prior" else persona_bank,
        top_k=0 if ablation_mode == "without_hachimi_prior" else persona_matching_top_k,
        llm_client=llm_client if ablation_mode != "without_hachimi_prior" else None,
        exclude_dialogue_id=task.dialogue_id,
    )
    student_context_profile = build_student_context_profile(
        context=context,
        llm_client=llm_client,
        persona_prior_summary=persona_prior_summary,
    )
    student_context_profile = apply_student_context_profile_revisit(
        student_context_profile,
        student_context_profile_mode,
    )
    if ablation_mode == "without_task_local_state":
        interaction_state = _default_interaction_state_for_ablation()
        transition_prediction = _default_transition_prediction_for_ablation()
        error_blueprint = _default_error_blueprint_for_ablation()
        constraint_bundle = _format_only_dynamic_constraints_for_ablation()
    else:
        interaction_state = infer_task_local_state(
            student_context_profile=student_context_profile,
            context=context,
            tutor_profile=tutor_profile,
            llm_client=llm_client,
            persona_prior_summary=persona_prior_summary,
        )
        interaction_state = apply_interaction_state_revisit(
            interaction_state,
            interaction_state_mode,
        )
        transition_prediction = predict_state_transition(
            student_context_profile=student_context_profile,
            context=context,
            tutor_profile=tutor_profile,
            interaction_state=interaction_state,
            llm_client=llm_client,
            persona_prior_summary=persona_prior_summary,
        )
        transition_prediction = apply_transition_prediction_revisit(
            transition_prediction,
            transition_prediction_mode,
        )
        error_blueprint = build_error_blueprint(
            student_context_profile=student_context_profile,
            context=context,
            tutor_profile=tutor_profile,
            interaction_state=interaction_state,
            transition_prediction=transition_prediction,
            llm_client=llm_client,
            persona_prior_summary=persona_prior_summary,
        )
        error_blueprint = apply_error_blueprint_revisit(
            error_blueprint,
            error_blueprint_mode,
        )
        constraint_bundle = (
            _format_only_dynamic_constraints_for_ablation()
            if ablation_mode == "without_behavior_harness"
            else compile_behavior_harness(
                prediction=transition_prediction,
                error_blueprint=error_blueprint,
                constraint_profile=constraint_profile,
            )
        )
    generated_turn = generate_student_turn(
        student_context_profile=student_context_profile,
        context=context,
        tutor_profile=tutor_profile,
        interaction_state=interaction_state,
        transition_prediction=transition_prediction,
        error_blueprint=error_blueprint,
        constraint_bundle=constraint_bundle,
        llm_client=llm_client,
        use_llm_dynamic_violation_review=not disable_llm_dynamic_violation_review,
        use_generation_retry=not disable_generation_retry,
        use_behavior_harness=ablation_mode != "without_behavior_harness",
    )
    trace_rows = [
        _build_trace_row(
            task=task,
            stage="persona_prior_summary",
            payload=persona_prior_summary_to_dict(persona_prior_summary),
        ),
        _build_trace_row(
            task=task,
            stage="student_context_profile",
            payload=asdict(student_context_profile),
        ),
        _build_trace_row(
            task=task,
            stage="tutor_turn_profile",
            payload=asdict(tutor_profile),
        ),
        _build_trace_row(
            task=task,
            stage="interaction_state",
            payload=asdict(interaction_state),
        ),
        _build_trace_row(
            task=task,
            stage="state_transition_prediction",
            payload=asdict(transition_prediction),
        ),
        _build_trace_row(
            task=task,
            stage="error_blueprint",
            payload=asdict(error_blueprint),
        ),
        _build_trace_row(
            task=task,
            stage="constraint_bundle",
            payload=asdict(constraint_bundle),
        ),
        _build_trace_row(
            task=task,
            stage="generated_student_turn",
            payload={
                "pred_turn": generated_turn.pred_turn,
                "draft_turn": generated_turn.draft_turn,
                "stop_dialogue": generated_turn.stop_dialogue,
                "step_traces": [asdict(step) for step in generated_turn.step_traces],
                "violation_check": asdict(generated_turn.violation_check),
                "retried": generated_turn.retried,
                "semantic_preservation": (
                    asdict(generated_turn.semantic_preservation)
                    if generated_turn.semantic_preservation
                    else None
                ),
                "surface_realization": (
                    asdict(generated_turn.surface_realization)
                    if generated_turn.surface_realization
                    else None
                ),
            },
        ),
    ]
    record = {
        "dialogue_id": task.dialogue_id,
        "question_id": task.question_id,
        "intervention_id": task.intervention_id,
        "turn_idx": task.target_turn_index,
        "question_text": task.question_text,
        "subjects": list(task.subjects),
        "history": [asdict(turn) for turn in task.history],
        "pred_turn": generated_turn.pred_turn,
        "draft_turn": generated_turn.draft_turn,
        "stop_dialogue": generated_turn.stop_dialogue,
        "retried": generated_turn.retried,
        "student_context_profile": asdict(student_context_profile),
        "dialogue_context": asdict(context),
        "tutor_turn_profile": asdict(tutor_profile),
        "persona_prior_summary": persona_prior_summary_to_dict(
            persona_prior_summary
        ),
        "interaction_state": asdict(interaction_state),
        "state_transition_prediction": asdict(transition_prediction),
        "error_blueprint": asdict(error_blueprint),
        "constraint_bundle": asdict(constraint_bundle),
        "revisit_flags": {
            "constraint_profile": constraint_profile,
            "disable_llm_dynamic_violation_review": disable_llm_dynamic_violation_review,
            "disable_generation_retry": disable_generation_retry,
            "student_context_profile_mode": student_context_profile_mode,
            "tutor_turn_profile_mode": tutor_turn_profile_mode,
            "interaction_state_mode": interaction_state_mode,
            "transition_prediction_mode": transition_prediction_mode,
            "error_blueprint_mode": error_blueprint_mode,
            "ablation_mode": ablation_mode,
            "dynamic_hachimi_prior_status": (
                "hachimi_1m_persona_prior_disabled"
                if ablation_mode == "without_hachimi_prior"
                else "hachimi_1m_persona_prior_enabled"
            ),
            "behavior_harness_used_in_generation": ablation_mode != "without_behavior_harness",
        },
        "step_traces": [asdict(step) for step in generated_turn.step_traces],
        "violation_check": asdict(generated_turn.violation_check),
        "semantic_preservation": (
            asdict(generated_turn.semantic_preservation)
            if generated_turn.semantic_preservation
            else None
        ),
        "surface_realization": (
            asdict(generated_turn.surface_realization)
            if generated_turn.surface_realization
            else None
        ),
    }
    return {
        "task_key": (task.dialogue_id, int(task.target_turn_index)),
        "trace_rows": trace_rows,
        "record": record,
    }


def _default_interaction_state_for_ablation() -> TaskLocalLearnerState:
    return TaskLocalLearnerState(
        competence_position="within_zpd",
        misconception_status="not_salient",
        metacognitive_regulation_state="weak_monitoring",
        help_internalization_state="surface_uptake",
        help_seeking_state="help_ambivalent",
        attempt_readiness="ready_for_local_attempt",
        engagement_form="Active",
        response_commitment_state="tentative",
        response_maturity_cap="brief_local_explanation",
        state_evidence=[
            "ablation=without_task_local_state",
            "neutral dynamic default; no task-local learner state inferred",
        ],
    )


def _default_transition_prediction_for_ablation() -> StateTransitionPrediction:
    return StateTransitionPrediction(
        predicted_next_competence_position="within_zpd",
        predicted_next_misconception_status="not_salient",
        predicted_next_metacognitive_regulation_state="weak_monitoring",
        predicted_next_help_internalization_state="surface_uptake",
        predicted_next_help_seeking_state="help_ambivalent",
        predicted_next_attempt_readiness="ready_for_local_attempt",
        predicted_next_engagement_form="Active",
        predicted_next_response_commitment_state="tentative",
        predicted_next_response_maturity_cap="brief_local_explanation",
        predicted_misconception_trajectory_shift="hold_trajectory",
        transition_rationale=[
            "ablation=without_task_local_state",
            "neutral dynamic default; no state transition inferred from current tutor turn",
        ],
    )


def _default_error_blueprint_for_ablation() -> ErrorBlueprint:
    return ErrorBlueprint(
        error_presence="no_specific_error",
        newman_error_locus=None,
        radatz_error_mechanism=None,
        buggy_rule=None,
        wrong_claim_seed=None,
        blueprint_evidence=[
            "ablation=without_task_local_state",
            "neutral dynamic default; no local error blueprint inferred",
        ],
    )


def _format_only_dynamic_constraints_for_ablation() -> BehaviorHarness:
    return BehaviorHarness(
        max_sentences=4,
        max_step_budget=2,
        allow_direct_answer=True,
        allow_full_reasoning=True,
        allow_help_seeking_language=True,
        must_preserve_local_confusion=False,
        must_preserve_misconception_continuity=False,
        expected_error_presence="no_specific_error",
        expected_newman_error_locus=None,
        expected_radatz_error_mechanism=None,
        buggy_rule=None,
        wrong_claim_seed=None,
        must_realize_specific_error=False,
        must_anchor_to_local_wrong_claim=False,
        required_commitment_style="any",
        forbidden_patterns=[],
        style_constraints=[],
    )


def _execute_turn_prediction_task_until_success(
    task,
    llm_config: LLMConfig,
    persona_bank,
    persona_matching_top_k: int,
    constraint_profile: str,
    disable_llm_dynamic_violation_review: bool,
    disable_generation_retry: bool,
    student_context_profile_mode: str,
    tutor_turn_profile_mode: str,
    interaction_state_mode: str,
    transition_prediction_mode: str,
    error_blueprint_mode: str,
    ablation_mode: str,
    retry_events_path: Path,
    retry_sleep_s: float,
    max_retry_attempts: int,
    output_lock: threading.Lock,
) -> dict[str, object]:
    attempt = 0
    while True:
        attempt += 1
        try:
            task_result = _execute_turn_prediction_task(
                task=task,
                llm_config=llm_config,
                persona_bank=persona_bank,
                persona_matching_top_k=persona_matching_top_k,
                constraint_profile=constraint_profile,
                disable_llm_dynamic_violation_review=disable_llm_dynamic_violation_review,
                disable_generation_retry=disable_generation_retry,
                student_context_profile_mode=student_context_profile_mode,
                tutor_turn_profile_mode=tutor_turn_profile_mode,
                interaction_state_mode=interaction_state_mode,
                transition_prediction_mode=transition_prediction_mode,
                error_blueprint_mode=error_blueprint_mode,
                ablation_mode=ablation_mode,
            )
            task_result["record"]["task_retry_attempts"] = attempt
            return task_result
        except Exception as exc:
            with output_lock:
                append_jsonl(
                    retry_events_path,
                    {
                        "dialogue_id": task.dialogue_id,
                        "turn_idx": task.target_turn_index,
                        "question_id": task.question_id,
                        "intervention_id": task.intervention_id,
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
            if max_retry_attempts > 0 and attempt >= max_retry_attempts:
                raise RuntimeError(
                    f"task exceeded max_retry_attempts={max_retry_attempts} after "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            if retry_sleep_s > 0:
                time.sleep(retry_sleep_s)


def _build_trace_row(task, stage: str, payload: object) -> dict[str, object]:
    return {
        "dialogue_id": task.dialogue_id,
        "turn_idx": task.target_turn_index,
        "stage": stage,
        "payload": payload,
    }


def _record_sort_key(
    record: dict[str, object],
    task_order: dict[tuple[str, int], int],
) -> tuple[int, str, int]:
    key = (str(record["dialogue_id"]), int(record["turn_idx"]))
    return (
        int(task_order.get(key, 10**9)),
        str(record["dialogue_id"]),
        int(record["turn_idx"]),
    )


def _persist_task_result(
    task_result: dict[str, object],
    trace_path: Path,
    predictions_path: Path,
    records: list[dict[str, object]],
    completed_keys: set[tuple[str, int]],
    total_tasks: int,
    run_dir: Path,
    task_order: dict[tuple[str, int], int],
    write_full_outputs_every_n: int,
    completed_since_full_write: int,
) -> int:
    task_key = task_result["task_key"]
    if task_key in completed_keys:
        raise ValueError(f"duplicate completed task key encountered: {task_key}")
    trace_rows = task_result["trace_rows"]
    if not isinstance(trace_rows, list):
        raise ValueError("trace_rows must be a list")
    for row in trace_rows:
        append_jsonl(trace_path, row)
    record = task_result["record"]
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")
    append_jsonl(predictions_path, record)
    records.append(record)
    records.sort(key=lambda item: _record_sort_key(item, task_order))
    completed_keys.add(task_key)
    completed_since_full_write += 1
    print(
        f"Completed {len(records)}/{total_tasks} tasks: "
        f"{record['dialogue_id']} turn_idx={record['turn_idx']}"
    )
    if (
        write_full_outputs_every_n > 0
        and completed_since_full_write >= write_full_outputs_every_n
    ):
        write_turn_level_outputs(run_dir, records)
        completed_since_full_write = 0
    return completed_since_full_write


def _persist_task_failure(
    task,
    exc: Exception,
    failures_path: Path,
    failures: list[dict[str, object]],
    failed_keys: set[tuple[str, int]],
) -> None:
    task_key = (str(task.dialogue_id), int(task.target_turn_index))
    if task_key in failed_keys:
        return
    failure = {
        "dialogue_id": task.dialogue_id,
        "question_id": task.question_id,
        "intervention_id": task.intervention_id,
        "turn_idx": task.target_turn_index,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }
    append_jsonl(failures_path, failure)
    failures.append(failure)
    failed_keys.add(task_key)
    print(
        f"Failed task {task.dialogue_id} turn_idx={task.target_turn_index}: "
        f"{type(exc).__name__}: {exc}"
    )


def _load_existing_records(predictions_path: Path) -> list[dict[str, object]]:
    if not predictions_path.exists():
        return []
    records: list[dict[str, object]] = []
    with predictions_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid jsonl in existing predictions file at line {line_no}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"existing predictions line {line_no} must be object, got {type(row).__name__}"
                )
            records.append(row)
    return records


def _load_existing_failures(failures_path: Path) -> list[dict[str, object]]:
    if not failures_path.exists():
        return []
    failures: list[dict[str, object]] = []
    with failures_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid jsonl in existing failures file at line {line_no}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"existing failure line {line_no} must be object, got {type(row).__name__}"
                )
            failures.append(row)
    return failures


def _run_official_eval(
    run_dir: Path,
    official_eval_input: Path,
    evaluations: str,
    embedding_api_base_url: str = "",
    embedding_model: str = "",
    embedding_api_key: str = "",
    embedding_batch_size: int = 16,
    embedding_timeout_s: float = 60.0,
    embedding_max_retries: int = 3,
    embedding_retry_sleep_s: float = 2.0,
    llm_judge_batch_size: int = 100,
) -> None:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "dynamic/eedi/run_official_eval.py"),
        "--input_file",
        str(official_eval_input),
        "--evaluations",
        evaluations,
        "--no-llm_judge_batch_api",
        "--llm_judge_batch_size",
        str(llm_judge_batch_size),
    ]
    if embedding_api_base_url.strip():
        cmd.extend(["--embedding_api_base_url", embedding_api_base_url.strip()])
    if embedding_model.strip():
        cmd.extend(["--embedding_model", embedding_model.strip()])
    if embedding_api_key.strip():
        cmd.extend(["--embedding_api_key", embedding_api_key.strip()])
    if embedding_batch_size > 0:
        cmd.extend(["--embedding_batch_size", str(embedding_batch_size)])
    if embedding_timeout_s > 0:
        cmd.extend(["--embedding_timeout_s", str(embedding_timeout_s)])
    if embedding_max_retries >= 0:
        cmd.extend(["--embedding_max_retries", str(embedding_max_retries)])
    if embedding_retry_sleep_s >= 0:
        cmd.extend(["--embedding_retry_sleep_s", str(embedding_retry_sleep_s)])
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        write_json(
            run_dir / "official_eval_status.json",
            {
                "status": "failed",
                "command": cmd,
                "returncode": exc.returncode,
            },
        )
        raise
    write_json(
        run_dir / "official_eval_status.json",
        {
            "status": "completed",
            "command": cmd,
        },
    )


def _preflight_official_eval_requirements(
    evaluations: str,
    embedding_api_base_url: str = "",
    embedding_model: str = "",
    embedding_api_key: str = "",
    embedding_batch_size: int = 16,
    embedding_timeout_s: float = 60.0,
    embedding_max_retries: int = 3,
    embedding_retry_sleep_s: float = 2.0,
) -> None:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "dynamic/eedi/run_official_eval.py"),
        "--evaluations",
        evaluations,
        "--preflight_only",
    ]
    if embedding_api_base_url.strip():
        cmd.extend(["--embedding_api_base_url", embedding_api_base_url.strip()])
    if embedding_model.strip():
        cmd.extend(["--embedding_model", embedding_model.strip()])
    if embedding_api_key.strip():
        cmd.extend(["--embedding_api_key", embedding_api_key.strip()])
    if embedding_batch_size > 0:
        cmd.extend(["--embedding_batch_size", str(embedding_batch_size)])
    if embedding_timeout_s > 0:
        cmd.extend(["--embedding_timeout_s", str(embedding_timeout_s)])
    if embedding_max_retries >= 0:
        cmd.extend(["--embedding_max_retries", str(embedding_max_retries)])
    if embedding_retry_sleep_s >= 0:
        cmd.extend(["--embedding_retry_sleep_s", str(embedding_retry_sleep_s)])
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


if __name__ == "__main__":
    main()
