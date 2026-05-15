from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.evaluation import apply_official_correctness_labels
from src.llm_client import LLMConfig, OpenAICompatClient
from src.problem_profile import ProblemRequirementProfile
from src.runtime_paths import XES_ROOT
from src.student_conditioned_benchmark import (
    BenchmarkSettings,
    ablate_student_model_fields,
    build_benchmark_students,
    build_problem_profiles_for_questions,
    evaluate_benchmark_run,
    run_single_prediction,
)
from src.student_model import (
    ControlValueAnalysis,
    MathTaskCapabilityProfile,
    SRLAnalysis,
    SelfEfficacyAnalysis,
    StudentInternalSignals,
    StudentModel,
    build_student_model,
    map_student_model_to_internal_signals,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"jsonl row must be object: {path}")
                rows.append(row)
    return rows


def _resolve_xes_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate)
    return str((XES_ROOT / candidate).resolve())


def _build_single_problem_profile(
    args: tuple[str, object, OpenAICompatClient, bool, bool, str],
) -> tuple[str, object]:
    (
        question_id,
        question,
        llm_client,
        enable_difficulty_anchor_context,
        enable_real_difficulty_band,
        problem_profile_fields_mode,
    ) = args
    profile = build_problem_profiles_for_questions(
        question_lookup={question_id: question},
        llm_client=llm_client,
        enable_difficulty_anchor_context=enable_difficulty_anchor_context,
        enable_real_difficulty_band=enable_real_difficulty_band,
        problem_profile_fields_mode=problem_profile_fields_mode,
    )[question_id]
    return question_id, profile


def _filter_internal_signals(
    internal_signals: StudentInternalSignals,
    mode: str,
) -> StudentInternalSignals | dict[str, str] | None:
    if mode == "full":
        return internal_signals
    if mode == "none":
        return None
    if mode == "minimal":
        return {
            "srl_fragility_signal": internal_signals.srl_fragility_signal,
            "directness_signal": internal_signals.directness_signal,
        }
    raise ValueError(f"unknown internal_signals_mode: {mode}")


def _internal_signals_to_payload(
    internal_signals: StudentInternalSignals | dict[str, str] | None,
) -> dict[str, str] | None:
    if internal_signals is None:
        return None
    if isinstance(internal_signals, StudentInternalSignals):
        return asdict(internal_signals)
    if isinstance(internal_signals, dict):
        return {str(key): str(value) for key, value in internal_signals.items()}
    raise TypeError(f"unsupported internal_signals type: {type(internal_signals).__name__}")


def _build_single_student_stack(
    args: tuple[object, OpenAICompatClient, str, str],
) -> tuple[str, object, object]:
    student, llm_client, internal_signals_mode, student_model_fields_mode = args
    student_model = build_student_model(student.enhanced_persona, llm_client=llm_client)
    student_model = ablate_student_model_fields(
        student_model,
        student_model_fields_mode,
    )
    if internal_signals_mode == "none":
        internal_signals = None
    else:
        full_internal_signals = map_student_model_to_internal_signals(
            student_model,
            llm_client=llm_client,
        )
        internal_signals = _filter_internal_signals(
            full_internal_signals,
            internal_signals_mode,
        )
    return student.student_id, student_model, internal_signals


def _problem_profile_from_dict(row: dict[str, object]) -> ProblemRequirementProfile:
    return ProblemRequirementProfile(**row)


def _student_model_from_dict(row: dict[str, object]) -> StudentModel:
    capability = row.get("math_task_capability_profile")
    return StudentModel(
        student_id=str(row["student_id"]),
        grade=str(row["grade"]),
        academic_level=str(row["academic_level"]),
        weak_subjects=list(row["weak_subjects"]),
        strong_subjects=list(row["strong_subjects"]),
        self_efficacy_analysis=SelfEfficacyAnalysis(**row["self_efficacy_analysis"]),
        srl_analysis=SRLAnalysis(**row["srl_analysis"]),
        control_value_analysis=ControlValueAnalysis(**row["control_value_analysis"]),
        engagement_level_tendency=str(row["engagement_level_tendency"]),
        engagement_evidence=list(row["engagement_evidence"]),
        response_directness_description=str(row["response_directness_description"]),
        response_directness_evidence=list(row["response_directness_evidence"]),
        raw_summary=str(row["raw_summary"]),
        math_anchor_profile_summary=str(row.get("math_anchor_profile_summary", "")),
        math_anchor_profile_evidence=list(row.get("math_anchor_profile_evidence", [])),
        math_task_capability_profile=(
            MathTaskCapabilityProfile(**capability)
            if isinstance(capability, dict)
            else None
        ),
    )


def _student_signals_from_dict(row: object) -> StudentInternalSignals | dict[str, str] | None:
    if row is None:
        return None
    if not isinstance(row, dict):
        raise ValueError(f"student signals row must be object or null, got {type(row).__name__}")
    full_keys = {
        "efficacy_signal",
        "srl_fragility_signal",
        "control_signal",
        "value_signal",
        "directness_signal",
    }
    if set(row) == full_keys:
        return StudentInternalSignals(**row)
    return {str(key): str(value) for key, value in row.items()}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run XES student-conditioned benchmark with enhanced personas."
    )
    parser.add_argument(
        "--eligible_question_path",
        type=str,
        default="outputs/irt_support/run_20260427_183859/eligible_questions.json",
    )
    parser.add_argument(
        "--response_csv_path",
        type=str,
        default="../XES3G5M/question_level/train_valid_sequences_quelevel.csv",
    )
    parser.add_argument(
        "--persona_path",
        type=str,
        default="../merged_students_10k.jsonl",
    )
    parser.add_argument(
        "--question_path",
        type=str,
        default="../XES3G5M/metadata/questions.json",
    )
    parser.add_argument("--target_grade", type=str, default="三年级")
    parser.add_argument("--max_students", type=int, default=1000)
    parser.add_argument("--history_size", type=int, default=20)
    parser.add_argument("--test_size", type=int, default=10)
    parser.add_argument("--sampling_seed", type=int, default=42)
    parser.add_argument("--fixed_cohort_path", type=str, default=None)
    parser.add_argument(
        "--persona_source_mode",
        choices=["xes_history_plus_hachimi", "xes_history_only"],
        default="xes_history_plus_hachimi",
    )
    parser.add_argument("--prepare_only", action="store_true")
    parser.add_argument("--official_correctness_mode", choices=["rules_only", "rules_plus_llm_ambiguous_review"], default="rules_only")
    parser.add_argument("--method_variant", choices=["direct", "state_single", "state_step"], default="state_step")
    parser.add_argument("--response_persona", choices=["first", "third"], default="first")
    parser.add_argument("--max_thinking_steps", type=int, default=12)
    parser.add_argument(
        "--internal_signals_mode",
        choices=["full", "none", "minimal"],
        default="full",
    )
    parser.add_argument(
        "--student_model_fields_mode",
        choices=["full", "capability_only", "no_psych_fields", "no_style_fields"],
        default="full",
    )
    parser.add_argument(
        "--problem_profile_fields_mode",
        choices=["full", "problem_core_only", "no_problem_justifications", "no_problem_notes"],
        default="full",
    )
    parser.add_argument(
        "--interaction_decision_mode",
        choices=["full", "none"],
        default="full",
    )
    parser.add_argument(
        "--item_state_fields_mode",
        choices=["full", "state_label_only"],
        default="full",
    )
    parser.add_argument(
        "--constraint_mode",
        choices=["full", "loose"],
        default="full",
    )
    parser.add_argument(
        "--violation_retry_mode",
        choices=["off", "on"],
        default="off",
    )
    parser.add_argument(
        "--enable_difficulty_anchor_context",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--enable_real_difficulty_band",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--max_concurrency", type=int, default=8)
    parser.add_argument("--llm_base_url", type=str, default=None)
    parser.add_argument("--llm_model", type=str, default=None)
    parser.add_argument("--llm_api_key", type=str, default=None)
    parser.add_argument("--llm_api_key_env", type=str, default=None)
    parser.add_argument("--llm_no_auth", action="store_true")
    parser.add_argument("--llm_timeout_s", type=float, default=120.0)
    parser.add_argument("--llm_temperature", type=float, default=0.2)
    parser.add_argument("--llm_max_tokens", type=int, default=2000)
    parser.add_argument("--llm_response_format_json", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output_root", type=str, default="outputs/student_conditioned_benchmark")
    parser.add_argument("--resume_run_dir", type=str, default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    args.eligible_question_path = _resolve_xes_path(args.eligible_question_path)
    args.response_csv_path = _resolve_xes_path(args.response_csv_path)
    args.persona_path = _resolve_xes_path(args.persona_path)
    args.question_path = _resolve_xes_path(args.question_path)
    args.output_root = _resolve_xes_path(args.output_root)
    if args.fixed_cohort_path:
        args.fixed_cohort_path = _resolve_xes_path(args.fixed_cohort_path)
    if args.resume_run_dir:
        args.resume_run_dir = _resolve_xes_path(args.resume_run_dir)

    if not args.prepare_only:
        if args.llm_api_key_env and not args.llm_api_key:
            args.llm_api_key = os.environ.get(args.llm_api_key_env, "").strip()
        if args.llm_no_auth:
            args.llm_api_key = ""
        missing_llm_args = [
            name
            for name in ("llm_base_url", "llm_model", "llm_api_key")
            if not getattr(args, name) and not (name == "llm_api_key" and args.llm_no_auth)
        ]
        if missing_llm_args:
            raise ValueError(f"missing required LLM args when prepare_only is false: {missing_llm_args}")

    output_root = Path(args.output_root)
    if args.resume_run_dir:
        run_dir = Path(args.resume_run_dir)
        if not run_dir.exists():
            raise FileNotFoundError(f"resume_run_dir not found: {run_dir}")
    else:
        run_dir = output_root / datetime.now().strftime("run_%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=False)

    settings = BenchmarkSettings(
        eligible_question_path=args.eligible_question_path,
        response_csv_path=args.response_csv_path,
        persona_path=args.persona_path,
        question_path=args.question_path,
        target_grade=args.target_grade,
        max_students=args.max_students,
        history_size=args.history_size,
        test_size=args.test_size,
        official_correctness_mode=args.official_correctness_mode,
        method_variant=args.method_variant,
        response_persona=args.response_persona,
        max_thinking_steps=args.max_thinking_steps,
        enable_difficulty_anchor_context=args.enable_difficulty_anchor_context,
        enable_real_difficulty_band=args.enable_real_difficulty_band,
        internal_signals_mode=args.internal_signals_mode,
        student_model_fields_mode=args.student_model_fields_mode,
        problem_profile_fields_mode=args.problem_profile_fields_mode,
        interaction_decision_mode=args.interaction_decision_mode,
        item_state_fields_mode=args.item_state_fields_mode,
        constraint_mode=args.constraint_mode,
        violation_retry_mode=args.violation_retry_mode,
        sampling_seed=args.sampling_seed,
        persona_source_mode=args.persona_source_mode,
        fixed_cohort_path=args.fixed_cohort_path,
    )

    benchmark_students, question_lookup, benchmark_summary = build_benchmark_students(settings)
    if not (run_dir / "benchmark_summary.json").exists():
        _write_json(run_dir / "benchmark_summary.json", benchmark_summary)
    if not (run_dir / "benchmark_students.jsonl").exists():
        _write_jsonl(
            run_dir / "benchmark_students.jsonl",
            [
                {
                    "student_id": student.student_id,
                    "history": student.history,
                    "test": student.test,
                    "history_summary": {
                        **student.history_summary.__dict__,
                    },
                    "matched_persona_id": student.matched_persona_id,
                    "matched_persona_score": student.matched_persona_score,
                    "enhanced_persona": {
                        "student_id": student.enhanced_persona.student_id,
                        "grade": student.enhanced_persona.grade,
                        "academic_level": student.enhanced_persona.academic_level,
                        "strong_subjects": student.enhanced_persona.strong_subjects,
                        "weak_subjects": student.enhanced_persona.weak_subjects,
                        "learning_profile_text": student.enhanced_persona.learning_profile_text,
                        "math_anchor_profile": student.enhanced_persona.math_anchor_profile.__dict__ if student.enhanced_persona.math_anchor_profile else None,
                        "math_task_capability_anchor": student.enhanced_persona.math_task_capability_anchor.__dict__ if student.enhanced_persona.math_task_capability_anchor else None,
                    },
                }
                for student in benchmark_students
            ],
        )

    if args.prepare_only:
        print(f"student-conditioned benchmark prepared: {run_dir}", flush=True)
        print(f"n_students={len(benchmark_students)}", flush=True)
        return

    tasks: list[tuple[str, str, bool, str]] = []
    for student in benchmark_students:
        for question_id, real_is_correct in student.test:
            tasks.append(
                (
                    student.student_id,
                    question_id,
                    real_is_correct,
                    student.history_summary.history_level,
                )
            )
    task_question_lookup = {
        question_id: question_lookup[question_id]
        for question_id in sorted({question_id for _, question_id, _, _ in tasks})
    }
    print(f"prepared benchmark students: {len(benchmark_students)}", flush=True)
    print(f"prediction tasks: {len(tasks)}", flush=True)
    print(f"unique test questions: {len(task_question_lookup)}", flush=True)

    llm_client = OpenAICompatClient(
        LLMConfig(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            timeout_s=args.llm_timeout_s,
            temperature=args.llm_temperature,
            max_tokens=args.llm_max_tokens,
            response_format_json=bool(args.llm_response_format_json),
        )
    )

    problem_profiles_path = run_dir / "problem_profiles.json"
    if problem_profiles_path.exists():
        problem_profiles = {
            str(question_id): _problem_profile_from_dict(profile)
            for question_id, profile in _read_json(problem_profiles_path).items()
        }
    else:
        problem_profiles = {}
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            future_map = {
                executor.submit(
                    _build_single_problem_profile,
                    (
                        question_id,
                        question,
                        llm_client,
                        args.enable_difficulty_anchor_context,
                        args.enable_real_difficulty_band,
                        args.problem_profile_fields_mode,
                    ),
                ): question_id
                for question_id, question in task_question_lookup.items()
            }
            for future in as_completed(future_map):
                question_id, profile = future.result()
                problem_profiles[question_id] = profile
        _write_json(
            problem_profiles_path,
            {question_id: profile.__dict__ for question_id, profile in problem_profiles.items()},
        )
    print(f"problem profiles built: {len(problem_profiles)}", flush=True)

    student_models_path = run_dir / "student_models.jsonl"
    student_signals_path = run_dir / "student_signals.jsonl"
    student_models = {
        str(row["student_id"]): _student_model_from_dict(row)
        for row in _read_jsonl(student_models_path)
    }
    student_signals = {
        str(row["student_id"]): _student_signals_from_dict(row["signals"])
        for row in _read_jsonl(student_signals_path)
    }
    pending_students = [
        student
        for student in benchmark_students
        if student.student_id not in student_models or student.student_id not in student_signals
    ]
    if pending_students:
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            future_map = {
                executor.submit(
                    _build_single_student_stack,
                    (
                        student,
                        llm_client,
                        args.internal_signals_mode,
                        args.student_model_fields_mode,
                    ),
                ): student.student_id
                for student in pending_students
            }
            for future in as_completed(future_map):
                student_id, student_model, internal_signals = future.result()
                student_models[student_id] = student_model
                student_signals[student_id] = internal_signals
                _append_jsonl(student_models_path, asdict(student_model))
                _append_jsonl(
                    student_signals_path,
                    {
                        "student_id": student_id,
                        "signals": _internal_signals_to_payload(internal_signals),
                    },
                )
    print(f"student stacks built: {len(student_models)}", flush=True)

    predictions_path = run_dir / "predictions.jsonl"
    records = _read_jsonl(predictions_path)
    completed_task_keys = {
        (str(record["student_id"]), str(record["question_id"]))
        for record in records
    }
    pending_tasks = [
        task
        for task in tasks
        if (str(task[0]), str(task[1])) not in completed_task_keys
    ]
    if pending_tasks:
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            future_map = {}
            for student_id, question_id, real_is_correct, history_level in pending_tasks:
                future = executor.submit(
                    run_single_prediction,
                    student_models[student_id],
                    student_signals[student_id],
                    question_lookup[question_id],
                    problem_profiles[question_id],
                    llm_client,
                    args.method_variant,
                    args.response_persona,
                    args.max_thinking_steps,
                    args.interaction_decision_mode,
                    args.item_state_fields_mode,
                    args.constraint_mode,
                    args.violation_retry_mode,
                )
                future_map[future] = (student_id, question_id, real_is_correct, history_level)

            for future in as_completed(future_map):
                student_id, question_id, real_is_correct, history_level = future_map[future]
                try:
                    record = future.result()
                except Exception as exc:
                    record = {
                        "student_id": student_id,
                        "question_id": question_id,
                        "question_type": question_lookup[question_id].question_type,
                        "predicted_answer": "",
                        "student_response": "",
                        "gold_answers": question_lookup[question_id].answer,
                        "has_options": bool(question_lookup[question_id].options),
                        "student_model": asdict(student_models[student_id]),
                        "implementation_derived_signals": _internal_signals_to_payload(
                            student_signals[student_id]
                        ),
                        "problem_requirement_profile": asdict(problem_profiles[question_id]),
                        "student_item_interaction_decision": None,
                        "interaction_decision_mode": args.interaction_decision_mode,
                        "item_response_state": None,
                        "item_state_fields_mode": args.item_state_fields_mode,
                        "constraint_bundle": None,
                        "constraint_mode": args.constraint_mode,
                        "thinking_trace": [],
                        "thinking_steps_n": 0,
                        "violation_retry_mode": args.violation_retry_mode,
                        "initial_output_before_violation_retry": None,
                        "initial_constraint_bundle_before_violation_retry": None,
                        "violation_report_before_retry": None,
                        "retried_after_violation": False,
                        "prediction_failed": True,
                        "failure_stage": "run_single_prediction",
                        "failure_type": type(exc).__name__,
                        "failure": str(exc),
                    }
                if "prediction_failed" not in record:
                    record["prediction_failed"] = False
                record["real_is_correct"] = bool(real_is_correct)
                record["history_level"] = history_level
                records.append(record)
                _append_jsonl(predictions_path, record)
    print(f"predictions collected: {len(records)}", flush=True)

    records.sort(key=lambda row: (str(row["student_id"]), str(row["question_id"])))
    correctness_summary = apply_official_correctness_labels(
        records=records,
        question_lookup=question_lookup,
        llm_client=llm_client,
        official_correctness_mode=args.official_correctness_mode,
    )
    metrics = evaluate_benchmark_run(
        records=records,
        benchmark_students=benchmark_students,
        question_lookup=question_lookup,
    )
    metrics["correctness_summary"] = correctness_summary
    run_config = dict(vars(args))
    run_config["llm_api_key"] = "***REDACTED***"
    metrics["run_config"] = run_config

    _write_jsonl(run_dir / "predictions.jsonl", records)
    _write_json(run_dir / "metrics.json", metrics)

    print(f"student-conditioned benchmark completed: {run_dir}", flush=True)
    print(f"n_students={len(benchmark_students)}", flush=True)
    print(f"n_predictions={len(records)}", flush=True)


if __name__ == "__main__":
    main()
