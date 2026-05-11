from __future__ import annotations

import argparse
import csv
import json
import os
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.data_loading import (
    apply_persona_variant,
    build_real_student_reference,
    compute_item_stats,
    filter_personas_by_grade,
    load_frozen_selected_questions,
    load_personas,
    load_questions,
    sample_personas,
    select_questions_with_stats,
)
from src.evaluation import (
    apply_official_correctness_labels,
    audit_question_answer_formats,
    compute_level_pattern_diagnostics,
    evaluate_against_real_students,
    evaluate_run,
    judge_prediction_correctness_with_llm,
)
from src.generation import (
    check_violation,
    generate_student_answer,
    generate_student_answer_direct,
    retry_with_tighter_constraints,
    should_retry_once,
)
from src.llm_client import LLMConfig, OpenAICompatClient
from src.problem_profile import build_problem_requirement_profile
from src.response_state import compile_constraints, resolve_item_response_state
from src.student_model import (
    ControlValueAnalysis,
    SRLAnalysis,
    SelfEfficacyAnalysis,
    StudentInternalSignals,
    StudentModel,
    build_student_model,
    map_student_model_to_internal_signals,
)


def _load_config_defaults(config_path: str) -> dict[str, object]:
    path = Path(config_path)
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal math student answering harness.")
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="Path to JSON config file. CLI args override config values.",
    )
    parser.add_argument(
        "--persona_path",
        type=str,
        default="merged_students_10k.jsonl",
        help="Path to the persona jsonl.",
    )
    parser.add_argument(
        "--question_path",
        type=str,
        default="XES3G5M/metadata/questions.json",
        help="Path to questions.json.",
    )
    parser.add_argument(
        "--response_csv_path",
        type=str,
        default="XES3G5M/question_level/test_quelevel.csv",
        help="Path to XES question-level response csv used for offline item stats.",
    )
    parser.add_argument("--max_personas", type=int, default=4, help="Number of personas to run.")
    parser.add_argument("--max_questions", type=int, default=8, help="Number of questions to run.")
    parser.add_argument(
        "--target_grade",
        type=str,
        default="\u4e09\u5e74\u7ea7",
        help="Only keep personas matching this grade (XES current set is grade 3).",
    )
    parser.add_argument(
        "--grade_match_mode",
        choices=["exact", "ordinal"],
        default="exact",
        help="Grade matching mode. Use exact for strict same-grade filtering.",
    )
    parser.add_argument(
        "--persona_sampling",
        choices=["head", "random", "stratified"],
        default="stratified",
        help="Persona sampling strategy after grade filtering.",
    )
    parser.add_argument(
        "--persona_variant",
        choices=["full_persona", "level_only", "math_salient", "shuffled_full"],
        default="full_persona",
        help="Persona information variant for controlled ablations.",
    )
    parser.add_argument(
        "--sampling_seed",
        type=int,
        default=42,
        help="Random seed for persona sampling (random/stratified).",
    )
    parser.add_argument(
        "--min_option_questions",
        type=int,
        default=1,
        help="Ensure at least this many selected questions have options.",
    )
    parser.add_argument(
        "--question_selection_mode",
        choices=["head", "representative", "difficulty_balanced"],
        default="representative",
        help="Question selection strategy from overlap set.",
    )
    parser.add_argument(
        "--question_selection_seed",
        type=int,
        default=42,
        help="Random seed used when question_selection_mode=representative.",
    )
    parser.add_argument(
        "--frozen_question_set_path",
        type=str,
        default="",
        help="Optional path to exported selected_questions.json used to freeze the benchmark set.",
    )
    parser.add_argument(
        "--hard_max_accuracy",
        type=float,
        default=0.5,
        help="For difficulty_balanced selection: hard items must have real accuracy < this value.",
    )
    parser.add_argument(
        "--medium_max_accuracy",
        type=float,
        default=0.75,
        help="For difficulty_balanced selection: medium items must have real accuracy <= this value.",
    )
    parser.add_argument(
        "--min_item_response_count",
        type=int,
        default=0,
        help="Only allow questions with at least this many real response events.",
    )
    parser.add_argument(
        "--max_rows_for_stats",
        type=int,
        default=None,
        help="Optional cap on response csv rows when computing item stats.",
    )
    parser.add_argument(
        "--include_image_questions",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include image-dependent questions (marker/asset/figure-reference). Default is skip.",
    )
    parser.add_argument(
        "--strict_stats",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail if response row has question/response length mismatch.",
    )
    parser.add_argument(
        "--real_level_assignment_scope",
        choices=["all_events", "selected_questions"],
        default="all_events",
        help="Scope for deriving real-student four-level bands from response logs.",
    )
    parser.add_argument(
        "--output_root",
        type=str,
        default="outputs",
        help="Root directory for run outputs.",
    )
    parser.add_argument(
        "--resume_run_dir",
        type=str,
        default="",
        help="Optional existing run directory to resume from.",
    )
    parser.add_argument(
        "--backend",
        choices=["llm"],
        default="llm",
        help="Inference backend.",
    )
    parser.add_argument("--llm_base_url", type=str, default="", help="OpenAI-compatible base URL.")
    parser.add_argument("--llm_model", type=str, default="", help="LLM model name.")
    parser.add_argument("--llm_api_key", type=str, default="", help="LLM API key.")
    parser.add_argument(
        "--llm_timeout_s",
        type=float,
        default=120.0,
        help="Per-request timeout for LLM calls.",
    )
    parser.add_argument(
        "--llm_temperature",
        type=float,
        default=0.2,
        help="Sampling temperature for LLM calls.",
    )
    parser.add_argument(
        "--llm_max_tokens",
        type=int,
        default=800,
        help="Max output tokens per LLM call.",
    )
    parser.add_argument(
        "--max_concurrency",
        type=int,
        default=8,
        help="Max concurrency for question-level generation.",
    )
    parser.add_argument(
        "--official_correctness_mode",
        choices=["rules_only", "rules_plus_llm_ambiguous_review"],
        default="rules_only",
        help=(
            "Official correctness labeling mode. "
            "Use rules_plus_llm_ambiguous_review only for structurally ambiguous evaluation cases."
        ),
    )
    parser.add_argument(
        "--enable_llm_correctness_judge",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Add an extra LLM-as-a-judge correctness label after final answer generation (diagnostic only).",
    )
    parser.add_argument(
        "--response_persona",
        choices=["first", "third"],
        default="first",
        help="Narrative perspective for student_response.",
    )
    parser.add_argument(
        "--method_variant",
        choices=["direct", "state_single", "state_step"],
        default="state_step",
        help="Method ablation variant for root-cause experiments.",
    )
    parser.add_argument(
        "--max_thinking_steps",
        type=int,
        default=12,
        help="Hard cap for step-by-step internal thinking loop. Exceeding the cap raises an error.",
    )
    return parser


def _parse_args() -> argparse.Namespace:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=str, default="")
    bootstrap_args, _ = bootstrap.parse_known_args()

    parser = _build_parser()
    config_defaults: dict[str, object] = {}
    config_path = bootstrap_args.config.strip()
    if not config_path:
        auto_config_path = Path("configs/run_local.json")
        if auto_config_path.exists():
            config_path = str(auto_config_path)
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


def _prepare_output_dir(output_root: str) -> Path:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    run_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = root / run_name
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _resolve_run_dir(output_root: str, resume_run_dir: str) -> tuple[Path, bool]:
    resume_path = resume_run_dir.strip()
    if not resume_path:
        return _prepare_output_dir(output_root), False

    run_dir = Path(resume_path)
    if not run_dir.exists():
        raise FileNotFoundError(f"resume run dir not found: {run_dir}")
    if not run_dir.is_dir():
        raise ValueError(f"resume run dir is not a directory: {run_dir}")
    return run_dir, True


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _append_jsonl_row(path: Path, row: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json in {path}: {exc}") from exc


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []

    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid jsonl in {path} at line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"jsonl row in {path} at line {line_no} must be object/dict, "
                    f"got {type(row).__name__}"
                )
            rows.append(row)
    return rows


def _require_llm_args(args: argparse.Namespace) -> None:
    missing: list[str] = []
    if not args.llm_base_url.strip():
        missing.append("--llm_base_url")
    if not args.llm_model.strip():
        missing.append("--llm_model")
    if not args.llm_api_key.strip():
        missing.append("--llm_api_key")
    if missing:
        raise ValueError(f"backend=llm requires args: {', '.join(missing)}")


def _args_for_logging(args: argparse.Namespace) -> dict[str, object]:
    payload = dict(vars(args))
    if payload.get("llm_api_key"):
        payload["llm_api_key"] = "***"
    return payload


def _resume_relevant_args(args: argparse.Namespace) -> dict[str, object]:
    payload = _args_for_logging(args)
    for key in ["config", "output_root", "resume_run_dir"]:
        payload.pop(key, None)
    return payload


def _write_or_validate_resolved_args(path: Path, args: argparse.Namespace, resume_mode: bool) -> None:
    payload = _args_for_logging(args)
    if not resume_mode:
        _write_json(path, payload)
        return
    if not path.exists():
        raise FileNotFoundError(f"resume requires existing resolved args file: {path}")
    existing = _load_json(path)
    if not isinstance(existing, dict):
        raise ValueError(f"resolved args file must be object/dict: {path}")
    existing_relevant = dict(existing)
    for key in ["config", "output_root", "resume_run_dir"]:
        existing_relevant.pop(key, None)
    current_relevant = _resume_relevant_args(args)
    if existing_relevant != current_relevant:
        raise ValueError(
            "resume args mismatch with existing run metadata: "
            f"path={path}"
        )


def _write_or_validate_json(
    path: Path,
    payload: object,
    label: str,
    resume_mode: bool,
) -> None:
    if not resume_mode:
        _write_json(path, payload)
        return
    if not path.exists():
        raise FileNotFoundError(f"resume requires existing {label}: {path}")
    existing = _load_json(path)
    if existing != payload:
        raise ValueError(f"resume mismatch for {label}: {path}")


def _require_dict(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be object/dict, got {type(payload).__name__}")
    return payload


def _require_text_field(payload: dict[str, object], field_name: str, label: str) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ValueError(f"{label} missing non-empty field: {field_name}")
    return value


def _require_string_list_field(
    payload: dict[str, object],
    field_name: str,
    label: str,
    allow_empty: bool = False,
) -> list[str]:
    raw_value = payload.get(field_name)
    if not isinstance(raw_value, list):
        raise ValueError(f"{label}.{field_name} must be list, got {type(raw_value).__name__}")
    values = [str(item).strip() for item in raw_value if str(item).strip()]
    if not values and not allow_empty:
        raise ValueError(f"{label}.{field_name} cannot be empty")
    return values


def _student_id_sort_key(student_id: object) -> tuple[int, int | str]:
    text = str(student_id).strip()
    try:
        return 0, int(text)
    except ValueError:
        return 1, text


def _task_key(student_id: object, question_id: object) -> tuple[str, str]:
    student_text = str(student_id).strip()
    question_text = str(question_id).strip()
    if not student_text or not question_text:
        raise ValueError(
            f"task key fields must be non-empty, got student_id={student_id!r}, "
            f"question_id={question_id!r}"
        )
    return student_text, question_text


def _sort_key(record: dict[str, object]) -> tuple[int, int]:
    student_text = str(record["student_id"])
    question_text = str(record["question_id"])
    try:
        student_id = int(student_text)
    except ValueError:
        student_id = 10**9
    try:
        question_id = int(question_text)
    except ValueError:
        question_id = 10**9
    return student_id, question_id


def _student_model_from_row(row: dict[str, object], label: str) -> StudentModel:
    self_efficacy_obj = _require_dict(
        row.get("self_efficacy_analysis"), f"{label}.self_efficacy_analysis"
    )
    srl_obj = _require_dict(row.get("srl_analysis"), f"{label}.srl_analysis")
    control_value_obj = _require_dict(
        row.get("control_value_analysis"), f"{label}.control_value_analysis"
    )
    return StudentModel(
        student_id=_require_text_field(row, "student_id", label),
        grade=_require_text_field(row, "grade", label),
        academic_level=_require_text_field(row, "academic_level", label),
        weak_subjects=_require_string_list_field(row, "weak_subjects", label),
        strong_subjects=_require_string_list_field(row, "strong_subjects", label),
        self_efficacy_analysis=SelfEfficacyAnalysis(
            efficacy_belief_description=_require_text_field(
                self_efficacy_obj,
                "efficacy_belief_description",
                f"{label}.self_efficacy_analysis",
            ),
            efficacy_belief_evidence=_require_string_list_field(
                self_efficacy_obj,
                "efficacy_belief_evidence",
                f"{label}.self_efficacy_analysis",
            ),
        ),
        srl_analysis=SRLAnalysis(
            primary_srl_vulnerability=_require_text_field(
                srl_obj,
                "primary_srl_vulnerability",
                f"{label}.srl_analysis",
            ),
            srl_process_evidence=_require_string_list_field(
                srl_obj,
                "srl_process_evidence",
                f"{label}.srl_analysis",
            ),
        ),
        control_value_analysis=ControlValueAnalysis(
            control_appraisal_description=_require_text_field(
                control_value_obj,
                "control_appraisal_description",
                f"{label}.control_value_analysis",
            ),
            value_appraisal_description=_require_text_field(
                control_value_obj,
                "value_appraisal_description",
                f"{label}.control_value_analysis",
            ),
            control_value_evidence=_require_string_list_field(
                control_value_obj,
                "control_value_evidence",
                f"{label}.control_value_analysis",
            ),
        ),
        engagement_level_tendency=_require_text_field(row, "engagement_level_tendency", label),
        engagement_evidence=_require_string_list_field(row, "engagement_evidence", label),
        response_directness_description=_require_text_field(
            row,
            "response_directness_description",
            label,
        ),
        response_directness_evidence=_require_string_list_field(
            row,
            "response_directness_evidence",
            label,
        ),
        raw_summary=_require_text_field(row, "raw_summary", label),
    )


def _student_signals_from_row(row: dict[str, object], label: str) -> StudentInternalSignals:
    return StudentInternalSignals(
        efficacy_signal=_require_text_field(row, "efficacy_signal", label),
        srl_fragility_signal=_require_text_field(row, "srl_fragility_signal", label),
        control_signal=_require_text_field(row, "control_signal", label),
        value_signal=_require_text_field(row, "value_signal", label),
        directness_signal=_require_text_field(row, "directness_signal", label),
    )


def _load_student_models_from_jsonl(path: Path) -> dict[str, StudentModel]:
    models: dict[str, StudentModel] = {}
    for row_index, row in enumerate(_load_jsonl(path), start=1):
        model = _student_model_from_row(row, label=f"{path.name}[{row_index}]")
        if model.student_id in models:
            raise ValueError(f"duplicate student_id in {path}: {model.student_id}")
        models[model.student_id] = model
    return models


def _load_student_signals_from_jsonl(path: Path) -> dict[str, StudentInternalSignals]:
    signals_by_id: dict[str, StudentInternalSignals] = {}
    for row_index, row in enumerate(_load_jsonl(path), start=1):
        student_id = _require_text_field(row, "student_id", f"{path.name}[{row_index}]")
        signal_payload = _require_dict(
            row.get("signals"), f"{path.name}[{row_index}].signals"
        )
        signals = _student_signals_from_row(
            signal_payload,
            label=f"{path.name}[{row_index}].signals",
        )
        if student_id in signals_by_id:
            raise ValueError(f"duplicate student_id in {path}: {student_id}")
        signals_by_id[student_id] = signals
    return signals_by_id


def _hydrate_student_artifacts_from_records(
    records: list[dict[str, object]],
    student_models_by_id: dict[str, StudentModel],
    student_signals_by_id: dict[str, StudentInternalSignals],
) -> None:
    for row_index, record in enumerate(records, start=1):
        record_label = f"predictions.jsonl[{row_index}]"
        student_id = _require_text_field(record, "student_id", record_label)

        student_model_payload = _require_dict(record.get("student_model"), f"{record_label}.student_model")
        hydrated_model = _student_model_from_row(
            student_model_payload,
            label=f"{record_label}.student_model",
        )
        if hydrated_model.student_id != student_id:
            raise ValueError(
                f"{record_label}.student_model.student_id mismatch: "
                f"{hydrated_model.student_id!r} vs record student_id={student_id!r}"
            )
        existing_model = student_models_by_id.get(student_id)
        if existing_model is None:
            student_models_by_id[student_id] = hydrated_model
        elif existing_model != hydrated_model:
            raise ValueError(f"inconsistent student_model cached for student_id={student_id}")

        signal_payload = _require_dict(
            record.get("implementation_derived_signals"),
            f"{record_label}.implementation_derived_signals",
        )
        hydrated_signals = _student_signals_from_row(
            signal_payload,
            label=f"{record_label}.implementation_derived_signals",
        )
        existing_signals = student_signals_by_id.get(student_id)
        if existing_signals is None:
            student_signals_by_id[student_id] = hydrated_signals
        elif existing_signals != hydrated_signals:
            raise ValueError(f"inconsistent implementation_derived_signals for student_id={student_id}")


def _load_task_rows_and_keys(
    path: Path,
    label: str,
) -> tuple[list[dict[str, object]], set[tuple[str, str]]]:
    rows = _load_jsonl(path)
    keys: set[tuple[str, str]] = set()
    for row_index, row in enumerate(rows, start=1):
        key = _task_key(
            row.get("student_id"),
            row.get("question_id"),
        )
        if key in keys:
            raise ValueError(f"duplicate task row in {label}: student_id={key[0]} question_id={key[1]}")
        keys.add(key)
    return rows, keys


def _build_selected_question_rows(
    questions,
    item_stats,
    selection_mode: str,
    hard_max_accuracy: float,
    medium_max_accuracy: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, question in enumerate(questions):
        difficulty_band: str | None = None
        if selection_mode == "difficulty_balanced":
            accuracy = item_stats[question.question_id].accuracy
            if accuracy < hard_max_accuracy:
                difficulty_band = "hard"
            elif accuracy <= medium_max_accuracy:
                difficulty_band = "medium"
            else:
                difficulty_band = "easy"
        rows.append(
            {
                "question_id": question.question_id,
                "question_type": question.question_type,
                "question_text": question.question_text,
                "options": question.options,
                "gold_answers": question.answer,
                "has_options": bool(question.options),
                "real_response_count": item_stats[question.question_id].total,
                "real_item_accuracy": item_stats[question.question_id].accuracy,
                "difficulty_band": difficulty_band,
            }
        )
    return rows


def _build_single_record(
    student_model,
    internal_signals,
    question,
    llm_client: OpenAICompatClient | None,
    persona_variant: str = "full_persona",
    method_variant: str = "state_step",
    enable_llm_correctness_judge: bool = False,
    response_persona: str = "first",
    max_thinking_steps: int = 12,
) -> dict[str, object]:
    if method_variant not in {"direct", "state_single", "state_step"}:
        raise ValueError(
            "method_variant must be one of direct/state_single/state_step, "
            f"got {method_variant!r}"
        )

    problem_profile = build_problem_requirement_profile(
        question_text=question.question_text,
        options=question.options,
        question_type=question.question_type,
        llm_client=llm_client,
    )
    item_state = None
    constraints = None
    violation = None
    retried = False

    if method_variant == "direct":
        answer_output = generate_student_answer_direct(
            student_model=student_model,
            internal_signals=internal_signals,
            problem_profile=problem_profile,
            question_id=question.question_id,
            question_text=question.question_text,
            options=question.options,
            response_persona=response_persona,
            llm_client=llm_client,
        )
    else:
        item_state = resolve_item_response_state(
            student_model=student_model,
            internal_signals=internal_signals,
            profile=problem_profile,
            question_text=question.question_text,
            llm_client=llm_client,
        )
        constraints = compile_constraints(item_state)
        generation_max_thinking_steps = 1 if method_variant == "state_single" else max_thinking_steps
        answer_output = generate_student_answer(
            student_model=student_model,
            internal_signals=internal_signals,
            problem_profile=problem_profile,
            item_state=item_state,
            constraints=constraints,
            question_id=question.question_id,
            question_text=question.question_text,
            options=question.options,
            response_persona=response_persona,
            max_thinking_steps=generation_max_thinking_steps,
            llm_client=llm_client,
        )
        violation = check_violation(
            answer_output=answer_output,
            item_state=item_state,
            constraints=constraints,
            llm_client=llm_client,
            enable_llm_boundary_review=True,
        )
        if should_retry_once(item_state=item_state, violation=violation):
            retried = True
            answer_output, constraints = retry_with_tighter_constraints(
                student_model=student_model,
                internal_signals=internal_signals,
                problem_profile=problem_profile,
                item_state=item_state,
                constraints=constraints,
                question_id=question.question_id,
                question_text=question.question_text,
                options=question.options,
                response_persona=response_persona,
                max_thinking_steps=generation_max_thinking_steps,
                llm_client=llm_client,
            )
            violation = check_violation(
                answer_output=answer_output,
                item_state=item_state,
                constraints=constraints,
                llm_client=llm_client,
                enable_llm_boundary_review=True,
            )

    llm_judge: dict[str, object] | None = None
    if enable_llm_correctness_judge:
        judge_output = judge_prediction_correctness_with_llm(
            question_text=question.question_text,
            options=question.options,
            predicted_answer=answer_output.predicted_answer,
            llm_client=llm_client,
        )
        llm_judge = {
            "is_correct": judge_output.is_correct,
            "confidence": judge_output.confidence,
        }

    return {
        "student_id": student_model.student_id,
        "question_id": question.question_id,
        "question_type": question.question_type,
        "persona_variant": persona_variant,
        "method_variant": method_variant,
        "response_persona": response_persona,
        "predicted_answer": answer_output.predicted_answer,
        "student_response": answer_output.student_response,
        "thinking_trace": [asdict(step) for step in answer_output.thinking_trace],
        "thinking_steps_n": len(answer_output.thinking_trace),
        "retried": retried,
        "final_violation": asdict(violation) if violation is not None else None,
        "student_model": asdict(student_model),
        "implementation_derived_signals": asdict(internal_signals),
        "problem_requirement_profile": asdict(problem_profile),
        "item_response_state": asdict(item_state) if item_state is not None else None,
        "constraint_bundle": asdict(constraints) if constraints is not None else None,
        # Gold answer is kept for offline evaluation only.
        "gold_answers": question.answer,
        "has_options": bool(question.options),
        "llm_judge": llm_judge,
    }


def main() -> None:
    args = _parse_args()
    run_dir, resume_mode = _resolve_run_dir(args.output_root, args.resume_run_dir)
    _require_llm_args(args)

    predictions_path = run_dir / "predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"
    metrics_path = run_dir / "metrics.json"
    resolved_args_path = run_dir / "resolved_args.json"
    real_reference_path = run_dir / "real_student_reference.json"
    selected_questions_path = run_dir / "selected_questions.json"
    answer_format_audit_path = run_dir / "selected_question_answer_format_audit.json"
    selected_personas_path = run_dir / "selected_personas.json"
    student_models_path = run_dir / "student_models.jsonl"
    student_signals_path = run_dir / "student_signals.jsonl"

    all_personas = load_personas(args.persona_path, limit=None)
    grade_filtered_personas = filter_personas_by_grade(
        all_personas, args.target_grade, match_mode=args.grade_match_mode
    )
    sampled_personas = sample_personas(
        grade_filtered_personas,
        max_personas=args.max_personas,
        sampling_mode=args.persona_sampling,
        seed=args.sampling_seed,
    )
    personas = apply_persona_variant(
        sampled_personas,
        persona_variant=args.persona_variant,
        seed=args.sampling_seed,
    )
    if len(sampled_personas) < args.max_personas:
        print(
            f"[Data] requested max_personas={args.max_personas} but only "
            f"{len(sampled_personas)} personas available after grade filter"
        )

    all_questions = load_questions(
        args.question_path,
        skip_image_questions=not args.include_image_questions,
    )
    item_stats, parse_report = compute_item_stats(
        args.response_csv_path,
        max_rows=args.max_rows_for_stats,
        strict=args.strict_stats,
    )
    frozen_question_set_path = args.frozen_question_set_path.strip()
    if frozen_question_set_path:
        questions = load_frozen_selected_questions(
            frozen_selection_path=frozen_question_set_path,
            questions=all_questions,
            item_stats=item_stats,
        )
    else:
        questions = select_questions_with_stats(
            questions=all_questions,
            item_stats=item_stats,
            max_questions=args.max_questions,
            min_option_questions=args.min_option_questions,
            selection_mode=args.question_selection_mode,
            selection_seed=args.question_selection_seed,
            min_item_response_count=args.min_item_response_count,
            hard_max_accuracy=args.hard_max_accuracy,
            medium_max_accuracy=args.medium_max_accuracy,
        )
    real_reference = build_real_student_reference(
        response_csv_path=args.response_csv_path,
        selected_question_ids=[question.question_id for question in questions],
        level_assignment_scope=args.real_level_assignment_scope,
        max_rows=args.max_rows_for_stats,
        strict=args.strict_stats,
    )
    question_lookup = {question.question_id: question for question in questions}
    selected_question_answer_format_audit = audit_question_answer_formats(questions)
    selected_question_rows = _build_selected_question_rows(
        questions=questions,
        item_stats=item_stats,
        selection_mode=args.question_selection_mode,
        hard_max_accuracy=args.hard_max_accuracy,
        medium_max_accuracy=args.medium_max_accuracy,
    )
    selected_persona_rows = [asdict(persona) for persona in personas]

    _write_or_validate_resolved_args(
        resolved_args_path,
        args=args,
        resume_mode=resume_mode,
    )
    _write_or_validate_json(
        selected_questions_path,
        payload=selected_question_rows,
        label="selected_questions.json",
        resume_mode=resume_mode,
    )
    _write_or_validate_json(
        real_reference_path,
        payload=asdict(real_reference),
        label="real_student_reference.json",
        resume_mode=resume_mode,
    )
    _write_or_validate_json(
        answer_format_audit_path,
        payload=selected_question_answer_format_audit,
        label="selected_question_answer_format_audit.json",
        resume_mode=resume_mode,
    )
    _write_or_validate_json(
        selected_personas_path,
        payload=selected_persona_rows,
        label="selected_personas.json",
        resume_mode=resume_mode,
    )

    selected_level_dist = Counter(persona.academic_level for persona in personas)
    print(
        f"[Data] personas={len(personas)} questions={len(questions)} "
        f"item_stats={len(item_stats)}"
    )
    print(
        f"[Data] target_grade={args.target_grade} "
        f"grade_match_mode={args.grade_match_mode} "
        f"grade_filtered_pool={len(grade_filtered_personas)} "
        f"persona_sampling={args.persona_sampling} "
        f"persona_variant={args.persona_variant} "
        f"sampling_seed={args.sampling_seed}"
    )
    print(f"[Data] selected_persona_level_dist={dict(selected_level_dist)}")
    print(
        "[Data] response_parse_report="
        f"(rows_read={parse_report.rows_read}, "
        f"rows_skipped_length_mismatch={parse_report.rows_skipped_length_mismatch}, "
        f"events_skipped_invalid={parse_report.events_skipped_invalid})"
    )
    print(
        "[Data] question_selection="
        f"mode={'frozen_file' if frozen_question_set_path else args.question_selection_mode} "
        f"seed={args.question_selection_seed} "
        f"min_item_response_count={args.min_item_response_count} "
        f"hard_max_accuracy={args.hard_max_accuracy} "
        f"medium_max_accuracy={args.medium_max_accuracy}"
    )
    if frozen_question_set_path:
        print(f"[Data] frozen_question_set_path={frozen_question_set_path}")
    print(
        "[Data] real_level_assignment="
        f"scope={real_reference.level_assignment_scope} "
        f"thresholds={real_reference.level_thresholds} "
        f"level_counts={real_reference.student_level_counts}"
    )
    print(f"[Run] backend={args.backend} max_concurrency={args.max_concurrency}")
    print(f"[Run] config={args.config or '(none)'}")
    print(f"[Run] resume_mode={resume_mode}")
    if resume_mode:
        print(f"[Run] resume_run_dir={run_dir}")
    print(f"[Run] response_persona={args.response_persona}")
    print(f"[Run] method_variant={args.method_variant}")
    print(f"[Run] max_thinking_steps={args.max_thinking_steps}")
    print(f"[Run] official_correctness_mode={args.official_correctness_mode}")
    print(f"[Run] enable_llm_correctness_judge={args.enable_llm_correctness_judge}")

    llm_client = OpenAICompatClient(
        LLMConfig(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            timeout_s=args.llm_timeout_s,
            temperature=args.llm_temperature,
            max_tokens=args.llm_max_tokens,
        )
    )

    records, completed_prediction_keys = _load_task_rows_and_keys(
        predictions_path,
        label=str(predictions_path),
    )
    failures, failed_task_keys = _load_task_rows_and_keys(
        failures_path,
        label=str(failures_path),
    )
    duplicated_completed_keys = completed_prediction_keys.intersection(failed_task_keys)
    if duplicated_completed_keys:
        sample_key = sorted(duplicated_completed_keys)[0]
        raise ValueError(
            "same task exists in both predictions and failures: "
            f"student_id={sample_key[0]} question_id={sample_key[1]}"
        )
    completed_task_keys = set(completed_prediction_keys).union(failed_task_keys)

    student_models_by_id = _load_student_models_from_jsonl(student_models_path)
    student_signals_by_id = _load_student_signals_from_jsonl(student_signals_path)
    _hydrate_student_artifacts_from_records(
        records=records,
        student_models_by_id=student_models_by_id,
        student_signals_by_id=student_signals_by_id,
    )

    expected_student_ids = {persona.student_id for persona in personas}
    extra_model_ids = sorted(set(student_models_by_id) - expected_student_ids, key=_student_id_sort_key)
    if extra_model_ids:
        raise ValueError(f"unexpected cached student models in run dir: {extra_model_ids}")
    extra_signal_ids = sorted(set(student_signals_by_id) - expected_student_ids, key=_student_id_sort_key)
    if extra_signal_ids:
        raise ValueError(f"unexpected cached student signals in run dir: {extra_signal_ids}")
    if not set(student_signals_by_id).issubset(set(student_models_by_id)):
        raise ValueError("cached student signals contain student_id with no matching cached student model")

    student_models: list[StudentModel] = []
    for persona in personas:
        student_model = student_models_by_id.get(persona.student_id)
        if student_model is None:
            student_model = build_student_model(persona, llm_client=llm_client)
            student_models_by_id[student_model.student_id] = student_model
            _append_jsonl_row(student_models_path, asdict(student_model))
        student_models.append(student_model)

    student_signals: dict[str, StudentInternalSignals] = {}
    for student_model in student_models:
        signals = student_signals_by_id.get(student_model.student_id)
        if signals is None:
            signals = map_student_model_to_internal_signals(
                student_model,
                llm_client=llm_client,
            )
            student_signals_by_id[student_model.student_id] = signals
            _append_jsonl_row(
                student_signals_path,
                {
                    "student_id": student_model.student_id,
                    "signals": asdict(signals),
                },
            )
        student_signals[student_model.student_id] = signals

    student_model_rows = [
        asdict(student_models_by_id[student_id])
        for student_id in sorted(student_models_by_id, key=_student_id_sort_key)
    ]
    _write_jsonl(student_models_path, student_model_rows)
    student_signal_rows = [
        {
            "student_id": student_id,
            "signals": asdict(student_signals_by_id[student_id]),
        }
        for student_id in sorted(student_signals_by_id, key=_student_id_sort_key)
    ]
    _write_jsonl(student_signals_path, student_signal_rows)

    all_tasks = [
        (student_model, student_signals[student_model.student_id], question)
        for student_model in student_models
        for question in questions
    ]
    all_task_keys = {
        _task_key(student_model.student_id, question.question_id)
        for student_model, _, question in all_tasks
    }
    if not completed_task_keys.issubset(all_task_keys):
        unexpected_completed = sorted(completed_task_keys - all_task_keys)[0]
        raise ValueError(
            "cached completed task not found in current run definition: "
            f"student_id={unexpected_completed[0]} question_id={unexpected_completed[1]}"
        )
    tasks = [
        (student_model, internal_signals, question)
        for student_model, internal_signals, question in all_tasks
        if _task_key(student_model.student_id, question.question_id) not in completed_task_keys
    ]
    total_tasks = len(all_tasks)
    cached_predictions_at_start = len(records)
    cached_failures_at_start = len(failures)
    pending_tasks_at_start = len(tasks)
    print(
        f"[Run] total_tasks={total_tasks} pending_tasks={pending_tasks_at_start} "
        f"cached_predictions={cached_predictions_at_start} cached_failures={cached_failures_at_start}"
    )

    if tasks:
        max_workers = max(1, min(args.max_concurrency, len(tasks)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _build_single_record,
                    student_model,
                    internal_signals,
                    question,
                    llm_client,
                    args.persona_variant,
                    args.method_variant,
                    args.enable_llm_correctness_judge,
                    args.response_persona,
                    args.max_thinking_steps,
                ): (
                    student_model.student_id,
                    question.question_id,
                )
                for student_model, internal_signals, question in tasks
            }
            for future in as_completed(futures):
                student_id, question_id = futures[future]
                task_key = _task_key(student_id, question_id)
                try:
                    record = future.result()
                except Exception as exc:
                    failure_row = {
                        "student_id": str(student_id),
                        "question_id": str(question_id),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": "".join(
                            traceback.format_exception(type(exc), exc, exc.__traceback__)
                        ),
                    }
                    failures.append(failure_row)
                    completed_task_keys.add(task_key)
                    _append_jsonl_row(failures_path, failure_row)
                    continue
                records.append(record)
                completed_task_keys.add(task_key)
                _append_jsonl_row(predictions_path, record)

    if not records:
        raise RuntimeError(
            f"all predictions failed; see {failures_path} for explicit failure details"
        )

    records.sort(key=_sort_key)
    failures.sort(key=_sort_key)
    official_correctness_summary = apply_official_correctness_labels(
        records=records,
        question_lookup=question_lookup,
        llm_client=llm_client,
        official_correctness_mode=args.official_correctness_mode,
    )
    metrics = evaluate_run(records=records, item_stats=item_stats)
    metrics.update(evaluate_against_real_students(records=records, real_reference=real_reference))
    metrics.update(compute_level_pattern_diagnostics(records=records))
    metrics["backend"] = args.backend
    metrics["max_concurrency"] = args.max_concurrency
    metrics["target_grade"] = args.target_grade
    metrics["grade_match_mode"] = args.grade_match_mode
    metrics["persona_sampling"] = args.persona_sampling
    metrics["persona_variant"] = args.persona_variant
    metrics["sampling_seed"] = args.sampling_seed
    metrics["question_selection_mode"] = args.question_selection_mode
    metrics["question_selection_seed"] = args.question_selection_seed
    metrics["frozen_question_set_path"] = frozen_question_set_path
    metrics["question_selection_source"] = (
        "frozen_file" if frozen_question_set_path else "selection_mode"
    )
    metrics["min_item_response_count"] = args.min_item_response_count
    metrics["hard_max_accuracy"] = args.hard_max_accuracy
    metrics["medium_max_accuracy"] = args.medium_max_accuracy
    metrics["real_level_assignment_scope"] = args.real_level_assignment_scope
    metrics["selected_persona_level_dist"] = dict(selected_level_dist)
    metrics["llm_model"] = args.llm_model
    metrics["llm_base_url"] = args.llm_base_url
    metrics["config_path"] = args.config
    metrics["response_persona"] = args.response_persona
    metrics["method_variant"] = args.method_variant
    metrics["max_thinking_steps"] = args.max_thinking_steps
    metrics["official_correctness_mode"] = args.official_correctness_mode
    metrics["enable_llm_correctness_judge"] = args.enable_llm_correctness_judge
    metrics["resume_mode"] = resume_mode
    metrics["cached_predictions_at_start"] = cached_predictions_at_start
    metrics["cached_failures_at_start"] = cached_failures_at_start
    metrics["pending_tasks_at_start"] = pending_tasks_at_start
    metrics["n_attempted_tasks"] = total_tasks
    metrics["n_successful_predictions"] = len(records)
    metrics["n_failures"] = len(failures)
    metrics["failure_rate"] = len(failures) / total_tasks if total_tasks else 0.0
    metrics.update(official_correctness_summary)

    if args.enable_llm_correctness_judge:
        judged_records = [record for record in records if isinstance(record.get("llm_judge"), dict)]
        if judged_records:
            judge_match = sum(
                int(bool(record["llm_judge"]["is_correct"]) == bool(record["is_correct"]))
                for record in judged_records
            )
            judge_positive = sum(int(bool(record["llm_judge"]["is_correct"])) for record in judged_records)
            metrics["llm_judge_n"] = len(judged_records)
            metrics["llm_judge_agreement_with_gold"] = judge_match / len(judged_records)
            metrics["llm_judge_positive_rate"] = judge_positive / len(judged_records)

    _write_jsonl(predictions_path, records)
    _write_jsonl(failures_path, failures)
    _write_json(metrics_path, metrics)

    # Parse-friendly outputs for downstream analysis.
    compact_jsonl_path = run_dir / "predictions_compact.jsonl"
    compact_rows: list[dict[str, object]] = []
    for record in records:
        student_model = record["student_model"]
        state = record.get("item_response_state")
        if not isinstance(state, dict):
            state = {}
        violation = record.get("final_violation")
        if not isinstance(violation, dict):
            violation = {}
        correctness_label = record.get("correctness_label", {})
        compact_rows.append(
            {
                "student_id": record["student_id"],
                "student_grade": student_model["grade"],
                "student_academic_level": student_model["academic_level"],
                "question_id": record["question_id"],
                "question_type": record["question_type"],
                "persona_variant": record["persona_variant"],
                "method_variant": record.get("method_variant"),
                "response_persona": record["response_persona"],
                "predicted_answer": record["predicted_answer"],
                "gold_answers": "|".join(record["gold_answers"]),
                "is_correct": record["is_correct"],
                "thinking_steps_n": record["thinking_steps_n"],
                "response_state": state.get("response_state"),
                "prerequisite_familiarity": state.get("prerequisite_familiarity"),
                "commitment_tendency": state.get("commitment_tendency"),
                "explanation_depth_cap": state.get("explanation_depth_cap"),
                "retried": record["retried"],
                "correctness_source": correctness_label.get("source"),
                "answer_format_category": correctness_label.get("answer_format_category"),
                "official_llm_review_used": correctness_label.get("llm_review_used"),
                "official_llm_review_reason": correctness_label.get("llm_review_reason"),
                "official_llm_review_confidence": correctness_label.get("llm_review_confidence"),
                "has_violation": violation.get("has_violation"),
                "violation_reasons": (
                    "|".join(violation["reasons"]) if isinstance(violation.get("reasons"), list) else ""
                ),
                "llm_judge_is_correct": (
                    record["llm_judge"]["is_correct"] if isinstance(record.get("llm_judge"), dict) else None
                ),
                "llm_judge_confidence": (
                    record["llm_judge"]["confidence"] if isinstance(record.get("llm_judge"), dict) else None
                ),
            }
        )
    _write_jsonl(compact_jsonl_path, compact_rows)

    compact_csv_path = run_dir / "predictions_compact.csv"
    fieldnames = list(compact_rows[0].keys()) if compact_rows else []
    with compact_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(compact_rows)

    retries = sum(int(record["retried"]) for record in records)
    remaining_violations = sum(
        int(
            isinstance(record.get("final_violation"), dict)
            and bool(record["final_violation"].get("has_violation", False))
        )
        for record in records
    )
    print(f"[Run] outputs={run_dir}")
    print(
        f"[Run] predictions={len(records)} failures={len(failures)} "
        f"retries={retries} remaining_violations={remaining_violations}"
    )
    print(
        "[Run] official_correctness="
        f"mode={metrics['official_correctness_mode']} "
        f"rule_n={metrics['official_correctness_rule_n']} "
        f"llm_review_n={metrics['official_correctness_llm_review_n']}"
    )
    print(f"[Run] overall_accuracy={metrics['overall_accuracy']:.4f}")
    print(
        "[Run] item_level="
        f"n_overlap={metrics['n_questions_overlap_with_xes_stats']} "
        f"mae={metrics['item_accuracy_mae_vs_xes']} "
        f"pearson={metrics['item_accuracy_pearson_vs_xes']}"
    )
    print(
        "[Run] real_alignment="
        f"overall_gap={metrics['overall_accuracy_gap_vs_real_students']:.4f} "
        f"item_n_overlap={metrics['item_n_overlap_vs_real_students']} "
        f"item_mae={metrics['item_accuracy_mae_vs_real_students']} "
        f"item_pearson={metrics['item_accuracy_pearson_vs_real_students']}"
    )


if __name__ == "__main__":
    main()
