from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from src.data_loading import build_turn_prediction_tasks, load_eedi_dialogues
from src.dialogue_context import build_dialogue_context_state, format_history_text
from src.llm_client import LLMConfig, OpenAICompatClient
from src.population_calibration import (
    PopulationCalibrationExemplar,
    write_population_calibration_bank,
)
from src.runtime_paths import PROJECT_ROOT, resolve_eedi_path
from src.theory_error_eval import code_single_student_turn
from src.tutor_turn_profile import build_tutor_turn_profile


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a population calibration exemplar bank for EEDI."
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
    parser.add_argument("--max_dialogues", type=int, default=0)
    parser.add_argument("--max_tasks", type=int, default=100)
    parser.add_argument(
        "--sampling_mode",
        type=str,
        choices=["head", "uniform"],
        default="uniform",
    )
    parser.add_argument("--output_path", type=str, default="")
    parser.add_argument("--llm_base_url", type=str, default="")
    parser.add_argument("--llm_model", type=str, default="")
    parser.add_argument("--llm_api_key", type=str, default="")
    parser.add_argument("--llm_api_key_env", type=str, default="")
    parser.add_argument("--llm_timeout_s", type=float, default=120.0)
    parser.add_argument("--llm_temperature", type=float, default=0.2)
    parser.add_argument("--llm_max_tokens", type=int, default=1200)
    return parser


def _load_config_defaults(config_path: str) -> dict[str, object]:
    path = resolve_eedi_path(config_path)
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


def _resolve_api_key(args: argparse.Namespace) -> None:
    env_name = str(args.llm_api_key_env or "").strip()
    if not env_name:
        return
    env_value = os.environ.get(env_name, "").strip()
    if not env_value:
        raise ValueError(f"missing required environment variable for llm_api_key: {env_name}")
    args.llm_api_key = env_value


def _require_llm_args(args: argparse.Namespace) -> None:
    missing: list[str] = []
    if not str(args.llm_base_url).strip():
        missing.append("--llm_base_url")
    if not str(args.llm_model).strip():
        missing.append("--llm_model")
    if not str(args.llm_api_key).strip():
        missing.append("--llm_api_key")
    if missing:
        raise ValueError(f"LLM config missing required args: {', '.join(missing)}")


def main() -> None:
    args = _parse_args()
    _resolve_api_key(args)
    _require_llm_args(args)
    if not str(args.output_path or "").strip():
        raise ValueError("--output_path is required")

    llm_config = LLMConfig(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        timeout_s=float(args.llm_timeout_s),
        temperature=float(args.llm_temperature),
        max_tokens=int(args.llm_max_tokens),
    )
    llm_client = OpenAICompatClient(llm_config)

    dialogues = load_eedi_dialogues(
        anchored_dialogues_path=args.anchored_dialogues_path,
        question_metadata_path=args.question_metadata_path,
        dialogue_subjects_path=args.dialogue_subjects_path,
    )
    tasks, ground_truth_by_key = build_turn_prediction_tasks(
        dialogues,
        max_dialogues=(None if int(args.max_dialogues or 0) <= 0 else int(args.max_dialogues)),
    )
    if int(args.max_tasks or 0) > 0:
        tasks = _select_tasks(
            tasks=tasks,
            max_tasks=int(args.max_tasks),
            sampling_mode=str(args.sampling_mode),
        )
    if not tasks:
        raise ValueError("no calibration tasks selected")

    exemplars: list[PopulationCalibrationExemplar] = []
    for task in tasks:
        key = (task.dialogue_id, int(task.target_turn_index))
        gold_turn = ground_truth_by_key.get(key, "").strip()
        if not gold_turn:
            raise ValueError(f"missing gold turn for calibration task {key}")
        context = build_dialogue_context_state(task)
        tutor_profile = build_tutor_turn_profile(context=context, llm_client=llm_client)
        theory_row = {
            "key": task.dialogue_id,
            "dialogue_idx": len(exemplars),
            "turn_idx": int(task.target_turn_index),
            "question": task.question_text,
            "prompt": format_history_text(task.history),
            "question_annotation": None,
            "correctness": None,
        }
        theory_code = code_single_student_turn(
            row=theory_row,
            student_turn_text=gold_turn,
            llm_client=llm_client,
            turn_label="ground_truth_student_turn",
        )
        exemplars.append(
            PopulationCalibrationExemplar(
                dialogue_id=task.dialogue_id,
                question_id=task.question_id,
                intervention_id=task.intervention_id,
                turn_idx=int(task.target_turn_index),
                subjects=list(task.subjects),
                history_turn_count=len(task.history),
                latest_tutor_turn=context.latest_tutor_turn,
                last_student_turn=context.last_student_turn,
                tutor_profile=asdict(tutor_profile),
                has_codable_math_error=theory_code.has_codable_math_error,
                knowledge_type=theory_code.knowledge_type,
                error_locus=theory_code.error_locus,
                error_mechanism=theory_code.error_mechanism,
                error_evidence=list(theory_code.evidence),
            )
        )

    output_path = resolve_eedi_path(args.output_path)
    write_population_calibration_bank(output_path, exemplars)
    print(output_path)


def _select_tasks(
    tasks: list,
    max_tasks: int,
    sampling_mode: str,
) -> list:
    if max_tasks <= 0 or len(tasks) <= max_tasks:
        return list(tasks)
    if sampling_mode == "head":
        return list(tasks[:max_tasks])
    if sampling_mode != "uniform":
        raise ValueError(f"unsupported sampling_mode: {sampling_mode}")
    if max_tasks == 1:
        return [tasks[0]]
    last_index = len(tasks) - 1
    selected_indices: list[int] = []
    seen: set[int] = set()
    for sample_idx in range(max_tasks):
        raw_index = round(sample_idx * last_index / (max_tasks - 1))
        if raw_index in seen:
            continue
        selected_indices.append(raw_index)
        seen.add(raw_index)
    next_index = 0
    while len(selected_indices) < max_tasks:
        if next_index not in seen:
            selected_indices.append(next_index)
            seen.add(next_index)
        next_index += 1
    selected_indices.sort()
    return [tasks[index] for index in selected_indices]


if __name__ == "__main__":
    main()
