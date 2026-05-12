from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import time
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.data_loading import build_turn_prediction_tasks, load_eedi_dialogues
from src.dialogue_context import build_dialogue_context_state
from src.error_blueprint import build_error_blueprint
from src.evaluation_eedi import append_jsonl, export_official_eval_csv, write_json
from src.llm_client import LLMConfig, OpenAICompatClient
from src.population_calibration import (
    build_population_calibration_summary,
    load_population_calibration_bank,
    population_calibration_summary_to_dict,
)
from src.runtime_paths import EEDI_OUTPUTS_DIR, PROJECT_ROOT
from src.student_model import build_student_context_profile
from src.tutor_turn_profile import build_tutor_turn_profile
from src.weak_generation import generate_weak_student_turn
from src.weak_generation_v4 import generate_weak_student_turn_v4
from src.weak_generation_v5 import generate_weak_student_turn_v5
from src.weak_generation_v51 import generate_weak_student_turn_v51
from src.weak_generation_v52 import generate_weak_student_turn_v52
from src.weak_harness import (
    ABLATION_MODES,
    build_student_prior,
    build_tutor_move,
    build_visible_context,
    compile_teaching_support_packet,
    error_blueprint_to_local_error_state,
    predict_support_uptake,
    resolve_local_claim_seed,
    resolve_local_error_realization,
    resolve_math_claim_affordance,
    resolve_mediated_target_availability,
    resolve_learning_access_state,
    resolve_turn_response_constraint,
    update_learning_state,
)
from src.weak_harness_v4 import (
    compile_teaching_support_packet_v4,
    resolve_mediated_turn_plan,
)
from src.weak_harness_v5 import (
    compile_opportunity_constraint_bundle,
    resolve_learning_opportunity_state,
)
from src.weak_harness_v51 import (
    compile_opportunity_constraint_bundle_v51,
    resolve_local_belief_state,
    resolve_student_response_policy,
    resolve_support_transformation_state,
)
from src.weak_harness_v52 import (
    compile_opportunity_constraint_bundle_v52,
    resolve_claim_realization_frame,
    resolve_local_belief_state_v52,
    resolve_student_response_policy_v52,
    resolve_support_transformation_state_v52,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the EEDI weak-model tutoring harness."
    )
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
    parser.add_argument("--max_concurrency", type=int, default=1)
    parser.add_argument("--output_dir", type=str, default="")
    parser.add_argument(
        "--resume_existing",
        action="store_true",
        help=(
            "Continue an existing output_dir by loading prior predictions and "
            "rerunning unfinished tasks until they succeed."
        ),
    )
    parser.add_argument(
        "--ablation_mode",
        type=str,
        choices=list(ABLATION_MODES),
        default="commitment_first",
    )
    parser.add_argument(
        "--architecture_version",
        type=str,
        choices=["v31", "v3", "v4", "v5", "v5_1", "v5_2"],
        default="v31",
    )
    parser.add_argument("--compiler_llm_base_url", type=str, default="")
    parser.add_argument("--compiler_llm_model", type=str, default="")
    parser.add_argument("--compiler_llm_api_key", type=str, default="")
    parser.add_argument("--compiler_llm_api_key_env", type=str, default="")
    parser.add_argument("--compiler_llm_timeout_s", type=float, default=120.0)
    parser.add_argument("--compiler_llm_temperature", type=float, default=0.2)
    parser.add_argument("--compiler_llm_max_tokens", type=int, default=1200)
    parser.add_argument("--actor_llm_base_url", type=str, default="")
    parser.add_argument("--actor_llm_model", type=str, default="")
    parser.add_argument("--actor_llm_api_key", type=str, default="")
    parser.add_argument("--actor_llm_api_key_env", type=str, default="")
    parser.add_argument("--actor_llm_timeout_s", type=float, default=120.0)
    parser.add_argument("--actor_llm_temperature", type=float, default=0.2)
    parser.add_argument("--actor_llm_max_tokens", type=int, default=512)
    parser.add_argument("--population_calibration_bank_path", type=str, default="")
    parser.add_argument("--population_calibration_top_k", type=int, default=0)
    return parser


def _load_config_defaults(config_path: str) -> dict[str, object]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("config must be a JSON object")
    return raw


def _parse_args() -> argparse.Namespace:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=str, default="")
    bootstrap_args, _ = bootstrap.parse_known_args()

    parser = _build_parser()
    config_path = str(bootstrap_args.config or "").strip()
    if config_path:
        defaults = _load_config_defaults(config_path)
        valid_keys = {action.dest for action in parser._actions if action.dest != "help"}
        unknown_keys = sorted(set(defaults) - valid_keys)
        if unknown_keys:
            raise ValueError(f"unknown config keys: {unknown_keys}")
        parser.set_defaults(**defaults)
    args = parser.parse_args()
    if config_path and not args.config:
        args.config = config_path
    return args


def _resolve_api_key(args: argparse.Namespace, field_name: str, env_field_name: str) -> None:
    env_name = str(getattr(args, env_field_name) or "").strip()
    if not env_name:
        return
    env_value = os.environ.get(env_name, "").strip()
    if not env_value:
        raise ValueError(f"missing required environment variable for {field_name}: {env_name}")
    setattr(args, field_name, env_value)


def _require_llm_args(args: argparse.Namespace) -> None:
    missing: list[str] = []
    for prefix in ("compiler", "actor"):
        if not str(getattr(args, f"{prefix}_llm_base_url")).strip():
            missing.append(f"--{prefix}_llm_base_url")
        if not str(getattr(args, f"{prefix}_llm_model")).strip():
            missing.append(f"--{prefix}_llm_model")
        if not str(getattr(args, f"{prefix}_llm_api_key")).strip():
            missing.append(f"--{prefix}_llm_api_key")
    if missing:
        raise ValueError(f"LLM config missing required args: {', '.join(missing)}")


def _build_llm_config(args: argparse.Namespace, prefix: str) -> LLMConfig:
    return LLMConfig(
        base_url=getattr(args, f"{prefix}_llm_base_url"),
        model=getattr(args, f"{prefix}_llm_model"),
        api_key=getattr(args, f"{prefix}_llm_api_key"),
        timeout_s=float(getattr(args, f"{prefix}_llm_timeout_s")),
        temperature=float(getattr(args, f"{prefix}_llm_temperature")),
        max_tokens=int(getattr(args, f"{prefix}_llm_max_tokens")),
    )


def _task_key(task) -> tuple[str, int]:
    return (str(task.dialogue_id), int(task.target_turn_index))


def _row_key(row: dict[str, object], path: Path, line_no: int) -> tuple[str, int]:
    dialogue_id = row.get("dialogue_id")
    turn_idx = row.get("turn_idx")
    if dialogue_id is None or turn_idx is None:
        raise ValueError(f"{path} line {line_no} missing dialogue_id or turn_idx")
    return (str(dialogue_id), int(turn_idx))


def _load_jsonl_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{path} line {line_no} is not a JSON object")
            rows.append(payload)
    return rows


def _load_existing_prediction_records(path: Path) -> list[dict[str, object]]:
    rows = _load_jsonl_rows(path)
    seen: set[tuple[str, int]] = set()
    for line_no, row in enumerate(rows, start=1):
        key = _row_key(row, path, line_no)
        if key in seen:
            raise ValueError(f"{path} contains duplicate prediction key {key}")
        seen.add(key)
    return rows


def _load_existing_failure_records(path: Path) -> list[dict[str, object]]:
    rows = _load_jsonl_rows(path)
    seen: set[tuple[str, int]] = set()
    for line_no, row in enumerate(rows, start=1):
        key = _row_key(row, path, line_no)
        if key in seen:
            raise ValueError(f"{path} contains duplicate failure key {key}")
        seen.add(key)
    return rows


def _completed_task_keys(
    records: list[dict[str, object]],
) -> set[tuple[str, int]]:
    prediction_keys = {
        _row_key(row, Path("existing predictions"), line_no)
        for line_no, row in enumerate(records, start=1)
    }
    return prediction_keys


def main() -> None:
    args = _parse_args()
    _resolve_api_key(args, "compiler_llm_api_key", "compiler_llm_api_key_env")
    _resolve_api_key(args, "actor_llm_api_key", "actor_llm_api_key_env")
    _require_llm_args(args)

    if args.output_dir:
        run_dir = Path(args.output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = EEDI_OUTPUTS_DIR / datetime.now().strftime("weak_harness_%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=False)

    compiler_llm_client = OpenAICompatClient(_build_llm_config(args, "compiler"))
    actor_llm_client = OpenAICompatClient(_build_llm_config(args, "actor"))

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
    if not tasks:
        raise ValueError("no EEDI tasks selected for weak harness execution")
    population_calibration_bank = (
        load_population_calibration_bank(args.population_calibration_bank_path)
        if str(args.population_calibration_bank_path or "").strip()
        and int(args.population_calibration_top_k or 0) > 0
        else []
    )

    write_json(
        run_dir / "resolved_args.json",
        {
            "config": args.config,
            "anchored_dialogues_path": args.anchored_dialogues_path,
            "question_metadata_path": args.question_metadata_path,
            "dialogue_subjects_path": args.dialogue_subjects_path,
            "max_dialogues": args.max_dialogues,
            "max_tasks": args.max_tasks,
            "max_concurrency": args.max_concurrency,
            "resume_existing": args.resume_existing,
            "ablation_mode": args.ablation_mode,
            "architecture_version": args.architecture_version,
            "compiler_llm_base_url": args.compiler_llm_base_url,
            "compiler_llm_model": args.compiler_llm_model,
            "compiler_llm_api_key": "***",
            "compiler_llm_api_key_env": args.compiler_llm_api_key_env,
            "compiler_llm_timeout_s": args.compiler_llm_timeout_s,
            "compiler_llm_temperature": args.compiler_llm_temperature,
            "compiler_llm_max_tokens": args.compiler_llm_max_tokens,
            "actor_llm_base_url": args.actor_llm_base_url,
            "actor_llm_model": args.actor_llm_model,
            "actor_llm_api_key": "***",
            "actor_llm_api_key_env": args.actor_llm_api_key_env,
            "actor_llm_timeout_s": args.actor_llm_timeout_s,
            "actor_llm_temperature": args.actor_llm_temperature,
            "actor_llm_max_tokens": args.actor_llm_max_tokens,
            "population_calibration_bank_path": args.population_calibration_bank_path,
            "population_calibration_top_k": args.population_calibration_top_k,
        },
    )
    _write_progress(
        run_dir=run_dir,
        total_tasks=len(tasks),
        completed_tasks=0,
        pending_tasks=len(tasks),
        records_count=0,
        failures_count=0,
        current_task=None,
    )

    predictions_path = run_dir / "predictions.jsonl"
    traces_path = run_dir / "stage_traces.jsonl"
    retry_events_path = run_dir / "task_retry_events.jsonl"
    output_lock = threading.Lock()
    records: list[dict[str, object]] = []
    if args.resume_existing:
        records = _load_existing_prediction_records(predictions_path)
    completed_task_keys = _completed_task_keys(records)
    tasks_to_run = [
        task for task in tasks if _task_key(task) not in completed_task_keys
    ]
    compiler_llm_config = _build_llm_config(args, "compiler")
    actor_llm_config = _build_llm_config(args, "actor")

    if int(args.max_concurrency) <= 1:
        for task in tasks_to_run:
            _write_progress(
                run_dir=run_dir,
                total_tasks=len(tasks),
                completed_tasks=len(records),
                pending_tasks=max(0, len(tasks) - len(records)),
                records_count=len(records),
                failures_count=0,
                current_task=_task_key(task),
            )
            task_result = _execute_turn_prediction_task_until_success(
                task=task,
                compiler_llm_config=compiler_llm_config,
                actor_llm_config=actor_llm_config,
                ablation_mode=args.ablation_mode,
                architecture_version=args.architecture_version,
                population_calibration_bank=population_calibration_bank,
                population_calibration_top_k=int(args.population_calibration_top_k or 0),
                retry_events_path=retry_events_path,
                output_lock=output_lock,
            )
            _persist_task_result(
                task=task,
                task_result=task_result,
                ground_truth_by_key=ground_truth_by_key,
                traces_path=traces_path,
                predictions_path=predictions_path,
                records=records,
                output_lock=output_lock,
            )
            _write_progress(
                run_dir=run_dir,
                total_tasks=len(tasks),
                completed_tasks=len(records),
                pending_tasks=max(0, len(tasks) - len(records)),
                records_count=len(records),
                failures_count=0,
                current_task=_task_key(task),
            )
    else:
        if tasks_to_run:
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=min(int(args.max_concurrency), len(tasks_to_run))
            )
            futures: dict[concurrent.futures.Future[dict[str, object]], object] = {}
            try:
                for task in tasks_to_run:
                    with output_lock:
                        _write_progress(
                            run_dir=run_dir,
                            total_tasks=len(tasks),
                            completed_tasks=len(records),
                            pending_tasks=max(0, len(tasks) - len(records)),
                            records_count=len(records),
                            failures_count=0,
                            current_task=_task_key(task),
                        )
                    futures[
                        executor.submit(
                            _execute_turn_prediction_task_until_success,
                            task,
                            compiler_llm_config,
                            actor_llm_config,
                            args.ablation_mode,
                            args.architecture_version,
                            population_calibration_bank,
                            int(args.population_calibration_top_k or 0),
                            retry_events_path,
                            output_lock,
                        )
                    ] = task
                for future in concurrent.futures.as_completed(futures):
                    task = futures[future]
                    task_result = future.result()
                    _persist_task_result(
                        task=task,
                        task_result=task_result,
                        ground_truth_by_key=ground_truth_by_key,
                        traces_path=traces_path,
                        predictions_path=predictions_path,
                        records=records,
                        output_lock=output_lock,
                    )
                    _write_progress(
                        run_dir=run_dir,
                        total_tasks=len(tasks),
                        completed_tasks=len(records),
                        pending_tasks=max(0, len(tasks) - len(records)),
                        records_count=len(records),
                        failures_count=0,
                        current_task=_task_key(task),
                    )
            except Exception:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            executor.shutdown(wait=True)

    records.sort(key=lambda row: (str(row["dialogue_id"]), int(row["turn_idx"])))
    official_eval_input = export_official_eval_csv(
        output_dir=run_dir,
        records=records,
        annotated_eedi_dir=PROJECT_ROOT / "external/sim-student-eval/data/annotated/eedi",
    )
    _write_outputs(
        run_dir=run_dir,
        records=records,
        failures=[],
        official_eval_input=official_eval_input,
    )
    print(run_dir)


def _execute_turn_prediction_task_until_success(
    task,
    compiler_llm_config: LLMConfig,
    actor_llm_config: LLMConfig,
    ablation_mode: str,
    architecture_version: str,
    population_calibration_bank,
    population_calibration_top_k: int,
    retry_events_path: Path,
    output_lock: threading.Lock,
) -> dict[str, object]:
    attempt = 0
    last_error: Exception | None = None
    while True:
        attempt += 1
        try:
            task_result = _execute_turn_prediction_task(
                task=task,
                compiler_llm_config=compiler_llm_config,
                actor_llm_config=actor_llm_config,
                ablation_mode=ablation_mode,
                architecture_version=architecture_version,
                population_calibration_bank=population_calibration_bank,
                population_calibration_top_k=population_calibration_top_k,
            )
            task_result["record"]["task_retry_attempts"] = attempt
            return task_result
        except Exception as exc:
            last_error = exc
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
            time.sleep(0.5)
            continue


def _execute_turn_prediction_task(
    task,
    compiler_llm_config: LLMConfig,
    actor_llm_config: LLMConfig,
    ablation_mode: str,
    architecture_version: str,
    population_calibration_bank,
    population_calibration_top_k: int,
) -> dict[str, object]:
    compiler_llm_client = OpenAICompatClient(compiler_llm_config)
    actor_llm_client = OpenAICompatClient(actor_llm_config)
    context = build_dialogue_context_state(task)
    tutor_turn_profile = build_tutor_turn_profile(
        context=context,
        llm_client=compiler_llm_client,
    )
    population_calibration_summary = build_population_calibration_summary(
        context=context,
        tutor_profile=tutor_turn_profile,
        exemplar_bank=population_calibration_bank,
        top_k=population_calibration_top_k,
    )
    student_context_profile = build_student_context_profile(
        context=context,
        llm_client=compiler_llm_client,
        population_calibration_summary=population_calibration_summary,
    )
    visible_context = build_visible_context(context)
    student_prior = build_student_prior(
        student_context_profile,
        population_calibration_summary=population_calibration_summary,
    )
    tutor_move = build_tutor_move(tutor_turn_profile)
    learning_access_state = resolve_learning_access_state(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        llm_client=compiler_llm_client,
    )
    support_uptake = predict_support_uptake(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        llm_client=compiler_llm_client,
    )
    math_claim_affordance = resolve_math_claim_affordance(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        llm_client=compiler_llm_client,
    )
    mediated_target_availability = resolve_mediated_target_availability(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        llm_client=compiler_llm_client,
    )
    turn_response_constraint = resolve_turn_response_constraint(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        math_claim_affordance=math_claim_affordance,
        mediated_target_availability=mediated_target_availability,
    )
    local_error_state = None
    local_claim_seed = None
    mediated_turn_plan = None
    learning_opportunity_state = None
    student_response_policy = None
    local_belief_state = None
    support_transformation_state = None
    claim_realization_frame = None
    if architecture_version == "v4":
        local_error_state = resolve_local_error_realization(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            turn_response_constraint=turn_response_constraint,
            llm_client=compiler_llm_client,
        )
        mediated_turn_plan = resolve_mediated_turn_plan(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            local_error_state=local_error_state,
            llm_client=compiler_llm_client,
        )
        teaching_support_packet = compile_teaching_support_packet_v4(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            local_error_state=local_error_state,
            mediated_turn_plan=mediated_turn_plan,
            ablation_mode=ablation_mode,
        )
        generated_turn = generate_weak_student_turn_v4(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            mediated_turn_plan=mediated_turn_plan,
            teaching_support_packet=teaching_support_packet,
            llm_client=actor_llm_client,
        )
    elif architecture_version == "v5":
        learning_opportunity_state = resolve_learning_opportunity_state(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            llm_client=compiler_llm_client,
        )
        teaching_support_packet = compile_opportunity_constraint_bundle(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            learning_opportunity_state=learning_opportunity_state,
            ablation_mode=ablation_mode,
        )
        generated_turn = generate_weak_student_turn_v5(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            learning_opportunity_state=learning_opportunity_state,
            opportunity_constraint_bundle=teaching_support_packet,
            llm_client=actor_llm_client,
        )
    elif architecture_version == "v5_1":
        learning_opportunity_state = resolve_learning_opportunity_state(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            llm_client=compiler_llm_client,
        )
        student_response_policy = resolve_student_response_policy(
            visible_context=visible_context,
            student_prior=student_prior,
            llm_client=compiler_llm_client,
        )
        local_belief_state = resolve_local_belief_state(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            llm_client=compiler_llm_client,
        )
        support_transformation_state = resolve_support_transformation_state(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            student_response_policy=student_response_policy,
            local_belief_state=local_belief_state,
            llm_client=compiler_llm_client,
        )
        teaching_support_packet = compile_opportunity_constraint_bundle_v51(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            learning_opportunity_state=learning_opportunity_state,
            student_response_policy=student_response_policy,
            local_belief_state=local_belief_state,
            support_transformation_state=support_transformation_state,
            ablation_mode=ablation_mode,
        )
        generated_turn = generate_weak_student_turn_v51(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            learning_opportunity_state=learning_opportunity_state,
            student_response_policy=student_response_policy,
            local_belief_state=local_belief_state,
            support_transformation_state=support_transformation_state,
            opportunity_constraint_bundle_v51=teaching_support_packet,
            llm_client=actor_llm_client,
        )
    elif architecture_version == "v5_2":
        learning_opportunity_state = resolve_learning_opportunity_state(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            llm_client=compiler_llm_client,
        )
        student_response_policy = resolve_student_response_policy_v52(
            visible_context=visible_context,
            student_prior=student_prior,
            llm_client=compiler_llm_client,
        )
        local_belief_state = resolve_local_belief_state_v52(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            llm_client=compiler_llm_client,
        )
        support_transformation_state = resolve_support_transformation_state_v52(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            student_response_policy=student_response_policy,
            local_belief_state=local_belief_state,
            llm_client=compiler_llm_client,
        )
        claim_realization_frame = resolve_claim_realization_frame(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            learning_opportunity_state=learning_opportunity_state,
            student_response_policy=student_response_policy,
            local_belief_state=local_belief_state,
            support_transformation_state=support_transformation_state,
            llm_client=compiler_llm_client,
        )
        teaching_support_packet = compile_opportunity_constraint_bundle_v52(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            learning_opportunity_state=learning_opportunity_state,
            student_response_policy=student_response_policy,
            local_belief_state=local_belief_state,
            support_transformation_state=support_transformation_state,
            claim_realization_frame=claim_realization_frame,
            ablation_mode=ablation_mode,
        )
        generated_turn = generate_weak_student_turn_v52(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            learning_opportunity_state=learning_opportunity_state,
            student_response_policy=student_response_policy,
            local_belief_state=local_belief_state,
            support_transformation_state=support_transformation_state,
            claim_realization_frame=claim_realization_frame,
            opportunity_constraint_bundle_v52=teaching_support_packet,
            llm_client=actor_llm_client,
        )
    else:
        local_error_state = resolve_local_error_realization(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            turn_response_constraint=turn_response_constraint,
            llm_client=compiler_llm_client,
        )
        local_claim_seed = resolve_local_claim_seed(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            local_error_state=local_error_state,
            llm_client=compiler_llm_client,
        )
        teaching_support_packet = compile_teaching_support_packet(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            mediated_target_availability=mediated_target_availability,
            turn_response_constraint=turn_response_constraint,
            local_error_state=local_error_state,
            local_claim_seed=local_claim_seed,
            ablation_mode=ablation_mode,
        )
        generated_turn = generate_weak_student_turn(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            local_error_state=local_error_state,
            teaching_support_packet=teaching_support_packet,
            llm_client=actor_llm_client,
        )
    if not generated_turn.validation.is_valid:
        raise ValueError(
            "generated weak student turn failed validation after retry: "
            f"{generated_turn.validation.issues}"
        )
    if local_error_state is None:
        local_error_state = resolve_local_error_realization(
            visible_context=visible_context,
            student_prior=student_prior,
            tutor_move=tutor_move,
            learning_access_state=learning_access_state,
            support_uptake=support_uptake,
            math_claim_affordance=math_claim_affordance,
            turn_response_constraint=turn_response_constraint,
            llm_client=compiler_llm_client,
        )
    strong_error_blueprint = build_error_blueprint(
        student_context_profile=student_context_profile,
        context=context,
        tutor_profile=tutor_turn_profile,
        interaction_state=_weak_state_to_interaction_state(
            learning_access_state,
            support_uptake,
        ),
        transition_prediction=_weak_state_to_transition_prediction(
            learning_access_state,
            support_uptake,
        ),
        llm_client=compiler_llm_client,
        population_calibration_summary=population_calibration_summary,
    )
    strong_error_state = error_blueprint_to_local_error_state(strong_error_blueprint)
    learning_state_update = update_learning_state(
        visible_context=visible_context,
        student_prior=student_prior,
        tutor_move=tutor_move,
        learning_access_state=learning_access_state,
        support_uptake=support_uptake,
        teaching_support_packet=teaching_support_packet,
        generated_turn=generated_turn.pred_turn,
        llm_client=compiler_llm_client,
    )
    record = {
        "dialogue_id": task.dialogue_id,
        "question_id": task.question_id,
        "intervention_id": task.intervention_id,
        "turn_idx": task.target_turn_index,
        "question_text": task.question_text,
        "subjects": list(task.subjects),
        "history": [asdict(turn) for turn in task.history],
        "pred_turn": generated_turn.pred_turn,
        "stop_dialogue": generated_turn.stop_dialogue,
        "retried": generated_turn.retried,
        "validation": asdict(generated_turn.validation),
        "student_context_profile": asdict(student_context_profile),
        "tutor_turn_profile": asdict(tutor_turn_profile),
        "population_calibration_summary": population_calibration_summary_to_dict(
            population_calibration_summary
        ),
        "visible_context": asdict(visible_context),
        "student_prior": asdict(student_prior),
        "tutor_move": asdict(tutor_move),
        "learning_access_state": asdict(learning_access_state),
        "support_uptake": asdict(support_uptake),
        "math_claim_affordance": asdict(math_claim_affordance),
        "mediated_target_availability": asdict(mediated_target_availability),
        "turn_response_constraint": asdict(turn_response_constraint),
        "local_error_state": asdict(local_error_state),
        "local_claim_seed": (
            None if local_claim_seed is None else asdict(local_claim_seed)
        ),
        "mediated_turn_plan": (
            None if mediated_turn_plan is None else asdict(mediated_turn_plan)
        ),
        "learning_opportunity_state": (
            None
            if learning_opportunity_state is None
            else asdict(learning_opportunity_state)
        ),
        "student_response_policy": (
            None
            if student_response_policy is None
            else asdict(student_response_policy)
        ),
        "local_belief_state": (
            None if local_belief_state is None else asdict(local_belief_state)
        ),
        "support_transformation_state": (
            None
            if support_transformation_state is None
            else asdict(support_transformation_state)
        ),
        "claim_realization_frame": (
            None if claim_realization_frame is None else asdict(claim_realization_frame)
        ),
        "local_error_state_used_in_generation": architecture_version not in {"v5", "v5_1", "v5_2"},
        "strong_error_state_for_analysis": asdict(strong_error_state),
        "strong_error_blueprint": asdict(strong_error_blueprint),
        "teaching_support_packet": asdict(teaching_support_packet),
        "learning_state_update": asdict(learning_state_update),
        "turn_rationale": list(generated_turn.turn_rationale),
        "turn_plan": (
            asdict(generated_turn.turn_plan)
            if hasattr(generated_turn, "turn_plan")
            else None
        ),
        "ablation_mode": ablation_mode,
        "architecture_version": architecture_version,
    }
    trace_rows = [
        _build_trace_row(
            task,
            "population_calibration_summary",
            population_calibration_summary_to_dict(population_calibration_summary),
        ),
        _build_trace_row(task, "student_context_profile", asdict(student_context_profile)),
        _build_trace_row(task, "tutor_turn_profile", asdict(tutor_turn_profile)),
        _build_trace_row(task, "visible_context", asdict(visible_context)),
        _build_trace_row(task, "student_prior", asdict(student_prior)),
        _build_trace_row(task, "tutor_move", asdict(tutor_move)),
        _build_trace_row(task, "learning_access_state", asdict(learning_access_state)),
        _build_trace_row(task, "support_uptake", asdict(support_uptake)),
        _build_trace_row(task, "math_claim_affordance", asdict(math_claim_affordance)),
        _build_trace_row(
            task,
            "mediated_target_availability",
            asdict(mediated_target_availability),
        ),
        _build_trace_row(
            task,
            "turn_response_constraint",
            asdict(turn_response_constraint),
        ),
        _build_trace_row(task, "local_error_state", asdict(local_error_state)),
    ]
    if local_claim_seed is not None:
        trace_rows.append(
            _build_trace_row(task, "local_claim_seed", asdict(local_claim_seed))
        )
    if mediated_turn_plan is not None:
        trace_rows.append(
            _build_trace_row(task, "mediated_turn_plan", asdict(mediated_turn_plan))
        )
    if learning_opportunity_state is not None:
        trace_rows.append(
            _build_trace_row(
                task,
                "learning_opportunity_state",
                asdict(learning_opportunity_state),
            )
        )
    if student_response_policy is not None:
        trace_rows.append(
            _build_trace_row(
                task,
                "student_response_policy",
                asdict(student_response_policy),
            )
        )
    if local_belief_state is not None:
        trace_rows.append(
            _build_trace_row(
                task,
                "local_belief_state",
                asdict(local_belief_state),
            )
        )
    if support_transformation_state is not None:
        trace_rows.append(
            _build_trace_row(
                task,
                "support_transformation_state",
                asdict(support_transformation_state),
            )
        )
    if claim_realization_frame is not None:
        trace_rows.append(
            _build_trace_row(
                task,
                "claim_realization_frame",
                asdict(claim_realization_frame),
            )
        )
    trace_rows.extend(
        [
        _build_trace_row(
            task,
            "strong_error_state_for_analysis",
            asdict(strong_error_state),
        ),
        _build_trace_row(task, "strong_error_blueprint", asdict(strong_error_blueprint)),
        _build_trace_row(task, "teaching_support_packet", asdict(teaching_support_packet)),
        _build_trace_row(
            task,
            "generated_weak_student_turn",
            {
                "pred_turn": generated_turn.pred_turn,
                "stop_dialogue": generated_turn.stop_dialogue,
                "turn_rationale": list(generated_turn.turn_rationale),
                "turn_plan": (
                    asdict(generated_turn.turn_plan)
                    if hasattr(generated_turn, "turn_plan")
                    else None
                ),
                "validation": asdict(generated_turn.validation),
                "retried": generated_turn.retried,
            },
        ),
        _build_trace_row(task, "learning_state_update", asdict(learning_state_update)),
        ]
    )
    return {
        "record": record,
        "trace_rows": trace_rows,
    }


def _build_trace_row(task, stage: str, payload: object) -> dict[str, object]:
    return {
        "dialogue_id": task.dialogue_id,
        "turn_idx": task.target_turn_index,
        "stage": stage,
        "payload": payload,
    }


def _write_outputs(
    run_dir: Path,
    records: list[dict[str, object]],
    failures: list[dict[str, object]],
    official_eval_input: Path | None,
) -> None:
    csv_path = run_dir / "turn_level_predictions.csv"
    metrics_path = run_dir / "metrics.json"
    fieldnames = [
        "dialogue_id",
        "question_id",
        "intervention_id",
        "turn_idx",
        "gt_turn",
        "pred_turn",
        "response_space",
        "access_zone",
        "target_engagement_mode",
        "target_availability",
        "success_affordance",
        "error_continuity_risk",
        "claim_requirement",
        "error_pressure",
        "local_error_presence",
        "claim_seed_mode",
        "local_newman_locus",
        "local_error_mechanism",
        "ablation_mode",
        "architecture_version",
        "sentence_count",
        "retried",
        "question_text",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "dialogue_id": record["dialogue_id"],
                    "question_id": record["question_id"],
                    "intervention_id": record["intervention_id"],
                    "turn_idx": record["turn_idx"],
                    "gt_turn": record.get("gt_turn", ""),
                    "pred_turn": record["pred_turn"],
                    "response_space": record["teaching_support_packet"]["response_space"],
                    "access_zone": record["learning_access_state"]["access_zone"],
                    "target_engagement_mode": record["teaching_support_packet"][
                        "target_engagement_mode"
                    ],
                    "target_availability": record["teaching_support_packet"][
                        "target_availability"
                    ],
                    "success_affordance": record["teaching_support_packet"][
                        "success_affordance"
                    ],
                    "error_continuity_risk": record["teaching_support_packet"][
                        "error_continuity_risk"
                    ],
                    "claim_requirement": record["teaching_support_packet"][
                        "claim_requirement"
                    ],
                    "error_pressure": record["teaching_support_packet"][
                        "error_pressure"
                    ],
                    "local_error_presence": record["teaching_support_packet"][
                        "local_error_presence"
                    ],
                    "claim_seed_mode": record["teaching_support_packet"][
                        "claim_seed_mode"
                    ],
                    "local_newman_locus": record["teaching_support_packet"][
                        "local_newman_locus"
                    ],
                    "local_error_mechanism": record["teaching_support_packet"][
                        "local_error_mechanism"
                    ],
                    "ablation_mode": record["ablation_mode"],
                    "architecture_version": record.get("architecture_version", "v3"),
                    "sentence_count": record["validation"]["sentence_count"],
                    "retried": record["retried"],
                    "question_text": record["question_text"],
                }
            )
    response_space_distribution: dict[str, int] = {}
    engagement_distribution: dict[str, int] = {}
    error_presence_distribution: dict[str, int] = {}
    claim_seed_mode_distribution: dict[str, int] = {}
    target_availability_distribution: dict[str, int] = {}
    success_affordance_distribution: dict[str, int] = {}
    error_pressure_distribution: dict[str, int] = {}
    for record in records:
        response_space = str(record["teaching_support_packet"]["response_space"])
        engagement_mode = str(record["teaching_support_packet"]["target_engagement_mode"])
        error_presence = str(record["teaching_support_packet"]["local_error_presence"])
        target_availability = str(record["teaching_support_packet"]["target_availability"])
        success_affordance = str(record["teaching_support_packet"]["success_affordance"])
        error_pressure = str(record["teaching_support_packet"]["error_pressure"])
        claim_seed_mode = str(record["teaching_support_packet"]["claim_seed_mode"])
        response_space_distribution[response_space] = (
            response_space_distribution.get(response_space, 0) + 1
        )
        engagement_distribution[engagement_mode] = (
            engagement_distribution.get(engagement_mode, 0) + 1
        )
        error_presence_distribution[error_presence] = (
            error_presence_distribution.get(error_presence, 0) + 1
        )
        claim_seed_mode_distribution[claim_seed_mode] = (
            claim_seed_mode_distribution.get(claim_seed_mode, 0) + 1
        )
        target_availability_distribution[target_availability] = (
            target_availability_distribution.get(target_availability, 0) + 1
        )
        success_affordance_distribution[success_affordance] = (
            success_affordance_distribution.get(success_affordance, 0) + 1
        )
        error_pressure_distribution[error_pressure] = (
            error_pressure_distribution.get(error_pressure, 0) + 1
        )
    write_json(
        metrics_path,
        {
            "n_records": len(records),
            "n_failures": len(failures),
            "ablation_mode": records[0]["ablation_mode"] if records else None,
            "architecture_version": (
                records[0].get("architecture_version") if records else None
            ),
            "response_space_distribution": response_space_distribution,
            "target_engagement_distribution": engagement_distribution,
            "local_error_presence_distribution": error_presence_distribution,
            "claim_seed_mode_distribution": claim_seed_mode_distribution,
            "target_availability_distribution": target_availability_distribution,
            "success_affordance_distribution": success_affordance_distribution,
            "error_pressure_distribution": error_pressure_distribution,
            "official_eval_input": str(official_eval_input) if official_eval_input else None,
        },
    )


def _write_progress(
    run_dir: Path,
    total_tasks: int,
    completed_tasks: int,
    pending_tasks: int,
    records_count: int,
    failures_count: int,
    current_task: tuple[str, int] | None,
) -> None:
    write_json(
        run_dir / "progress.json",
        {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "records_count": records_count,
            "failures_count": failures_count,
            "current_task": None if current_task is None else list(current_task),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def _weak_state_to_interaction_state(learning_access_state, support_uptake):
    from src.student_turn_state import InteractionState

    competence_position = {
        "already_can_do": "within_current_competence",
        "reachable_with_current_support": "within_zpd",
        "not_reachable_this_turn": "beyond_zpd",
    }[learning_access_state.access_zone]
    misconception_status = (
        "active_misconception"
        if learning_access_state.persistent_obstacle in {"misconception", "missing_relation"}
        else "not_salient"
    )
    metacog_state = {
        "tutor_regulated": "unmonitored",
        "shared_regulation": "weak_monitoring",
        "self_regulation": "active_monitoring",
    }[learning_access_state.regulation_state]
    help_internalization = {
        "no_uptake": "no_uptake",
        "noticing_only": "surface_uptake",
        "partial_use": "partial_internalization",
        "substantive_use": "integrated_internalization",
    }[support_uptake.uptake_depth]
    attempt_readiness = {
        "acknowledge_or_brief_react": "not_ready",
        "ask_for_clarification": "not_ready",
        "attempt_local_step": "ready_for_local_attempt",
        "revise_prior_idea": "ready_to_revise",
        "explain_current_judgment": "ready_for_local_attempt",
    }[learning_access_state.turn_readiness]
    commitment = (
        "committed"
        if support_uptake.uptake_depth in {"partial_use", "substantive_use"}
        and learning_access_state.turn_readiness
        in {"attempt_local_step", "revise_prior_idea", "explain_current_judgment"}
        else "tentative"
    )
    return InteractionState(
        competence_position=competence_position,
        misconception_status=misconception_status,
        metacognitive_regulation_state=metacog_state,
        help_internalization_state=help_internalization,
        help_seeking_state="adaptive_help_seeking",
        attempt_readiness=attempt_readiness,
        engagement_form=support_uptake.likely_next_engagement_mode,
        response_commitment_state=commitment,
        response_maturity_cap="brief_local_explanation",
        state_evidence=list(learning_access_state.state_evidence),
    )


def _weak_state_to_transition_prediction(learning_access_state, support_uptake):
    from src.transition import StateTransitionPrediction

    attempt_readiness = {
        "acknowledge_or_brief_react": "not_ready",
        "ask_for_clarification": "not_ready",
        "attempt_local_step": "ready_for_local_attempt",
        "revise_prior_idea": "ready_to_revise",
        "explain_current_judgment": "ready_for_local_attempt",
    }[learning_access_state.turn_readiness]
    misconception = (
        "active_misconception"
        if learning_access_state.persistent_obstacle in {"misconception", "missing_relation"}
        else "not_salient"
    )
    commitment = (
        "committed"
        if support_uptake.uptake_depth in {"partial_use", "substantive_use"}
        else "tentative"
    )
    return StateTransitionPrediction(
        predicted_next_competence_position=(
            "within_current_competence"
            if learning_access_state.access_zone == "already_can_do"
            else "within_zpd"
            if learning_access_state.access_zone == "reachable_with_current_support"
            else "beyond_zpd"
        ),
        predicted_next_misconception_status=misconception,
        predicted_next_metacognitive_regulation_state=(
            "weak_monitoring"
            if learning_access_state.regulation_state != "self_regulation"
            else "active_monitoring"
        ),
        predicted_next_help_internalization_state=(
            "surface_uptake"
            if support_uptake.uptake_depth == "noticing_only"
            else "partial_internalization"
            if support_uptake.uptake_depth == "partial_use"
            else "integrated_internalization"
            if support_uptake.uptake_depth == "substantive_use"
            else "no_uptake"
        ),
        predicted_next_help_seeking_state="adaptive_help_seeking",
        predicted_next_attempt_readiness=attempt_readiness,
        predicted_next_engagement_form=support_uptake.likely_next_engagement_mode,
        predicted_next_response_commitment_state=commitment,
        predicted_next_response_maturity_cap="brief_local_explanation",
        predicted_misconception_trajectory_shift=(
            "hold_trajectory"
            if misconception == "active_misconception"
            else "stabilize_resolution"
        ),
        transition_rationale=list(learning_access_state.state_evidence),
    )


def _persist_task_result(
    task,
    task_result: dict[str, object],
    ground_truth_by_key: dict[tuple[str, int], str],
    traces_path: Path,
    predictions_path: Path,
    records: list[dict[str, object]],
    output_lock: threading.Lock,
) -> None:
    task_result["record"]["gt_turn"] = ground_truth_by_key[
        (task.dialogue_id, int(task.target_turn_index))
    ]
    with output_lock:
        for row in task_result["trace_rows"]:
            append_jsonl(traces_path, row)
        append_jsonl(predictions_path, task_result["record"])
        records.append(task_result["record"])


def _persist_task_failure(
    task,
    exc: Exception,
    failures_path: Path,
    failures: list[dict[str, object]],
) -> None:
    failure = {
        "dialogue_id": task.dialogue_id,
        "turn_idx": task.target_turn_index,
        "question_id": task.question_id,
        "intervention_id": task.intervention_id,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
    append_jsonl(failures_path, failure)
    failures.append(failure)


if __name__ == "__main__":
    main()
