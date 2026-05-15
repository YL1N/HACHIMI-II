from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

XES_ROOT = Path(__file__).resolve().parents[1]
if str(XES_ROOT) not in sys.path:
    sys.path.insert(0, str(XES_ROOT))

from run_student_conditioned_benchmark import (  # type: ignore
    _append_jsonl,
    _problem_profile_from_dict,
    _read_json,
    _read_jsonl,
    _resolve_xes_path,
    _student_model_from_dict,
    _write_json,
    _write_jsonl,
)
from src.evaluation import apply_official_correctness_labels
from src.llm_client import LLMConfig, OpenAICompatClient
from src.student_conditioned_benchmark import (
    BenchmarkSettings,
    build_benchmark_students,
    build_problem_profiles_for_questions,
    evaluate_benchmark_run,
)
from src.student_model import build_student_model

from weak_model_harness.src.compile_cards import (
    compile_prompt_ladder,
    compile_response_protocol,
    compile_risk_card,
    compile_scaffold_budget,
    compile_student_state,
    compile_task_state,
)
from weak_model_harness.src.support_profile import (
    build_task_support_profile,
    task_support_profile_from_dict,
)
from weak_model_harness.src.validate import validate_answer_output
from weak_model_harness.src.weak_actor import generate_answer_with_weak_model
from weak_model_harness.src.weak_llm_client import WeakLLMConfig, WeakOpenAICompatClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run XES weak-model student simulation benchmark."
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
    parser.add_argument("--persona_path", type=str, default="../merged_students_10k.jsonl")
    parser.add_argument("--question_path", type=str, default="../XES3G5M/metadata/questions.json")
    parser.add_argument("--target_grade", type=str, default="三年级")
    parser.add_argument("--max_students", type=int, default=100)
    parser.add_argument("--history_size", type=int, default=20)
    parser.add_argument("--test_size", type=int, default=10)
    parser.add_argument("--sampling_seed", type=int, default=42)
    parser.add_argument("--fixed_cohort_path", type=str, default=None)
    parser.add_argument(
        "--persona_source_mode",
        choices=["xes_history_plus_hachimi", "xes_history_only"],
        default="xes_history_plus_hachimi",
    )
    parser.add_argument("--official_correctness_mode", choices=["rules_only"], default="rules_only")
    parser.add_argument("--max_concurrency", type=int, default=4)
    parser.add_argument("--strong_llm_base_url", type=str, required=True)
    parser.add_argument("--strong_llm_model", type=str, required=True)
    parser.add_argument("--strong_llm_api_key", type=str, default="")
    parser.add_argument("--strong_llm_no_auth", action="store_true")
    parser.add_argument("--weak_llm_base_url", type=str, required=True)
    parser.add_argument("--weak_llm_model", type=str, required=True)
    parser.add_argument("--weak_llm_api_key", type=str, default="")
    parser.add_argument("--weak_llm_api_key_env", type=str, default="BAILIAN_API_KEY")
    parser.add_argument("--weak_enable_thinking", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--output_root", type=str, default="outputs/weak_model_benchmark")
    parser.add_argument("--resume_run_dir", type=str, default=None)
    parser.add_argument("--bootstrap_from_run_dir", type=str, default=None)
    return parser


def _run_single_weak_prediction(
    *,
    student_model: object,
    question: object,
    problem_profile: object,
    task_support_profile: object,
    weak_client: WeakOpenAICompatClient,
) -> dict[str, object]:
    student_state = compile_student_state(student_model)
    task_state = compile_task_state(
        str(question.question_id),
        str(question.question_type),
        problem_profile,
        task_support_profile,
    )
    scaffold_budget = compile_scaffold_budget(
        student_state,
        task_state,
        task_support_profile,
    )
    prompt_ladder = compile_prompt_ladder(
        task_state=task_state,
        scaffold_budget=scaffold_budget,
        task_support_profile=task_support_profile,
    )
    risk_card = compile_risk_card(
        student_state=student_state,
        task_state=task_state,
        task_support_profile=task_support_profile,
        scaffold_budget=scaffold_budget,
    )
    response_protocol = compile_response_protocol(
        task_state=task_state,
        scaffold_budget=scaffold_budget,
    )
    answer_output = generate_answer_with_weak_model(
        student_state=student_state,
        task_state=task_state,
        scaffold_budget=scaffold_budget,
        prompt_ladder=prompt_ladder,
        risk_card=risk_card,
        response_protocol=response_protocol,
        question_text=question.question_text,
        options=question.options,
        llm_client=weak_client,
    )
    answer_validation = validate_answer_output(
        task_state=task_state,
        response_protocol=response_protocol,
        predicted_answer=str(answer_output["predicted_answer"]),
        student_response=str(answer_output["student_response"]),
        used_support_level=str(answer_output["used_support_level"]),
    )
    if not answer_validation.is_valid:
        raise ValueError(f"invalid weak answer output: {answer_validation.issues}")
    return {
        "student_id": student_model.student_id,
        "question_id": question.question_id,
        "question_type": question.question_type,
        "predicted_answer": answer_output["predicted_answer"],
        "student_response": answer_output["student_response"],
        "gold_answers": question.answer,
        "has_options": bool(question.options),
        "student_model": asdict(student_model),
        "problem_requirement_profile": asdict(problem_profile),
        "task_support_profile": asdict(task_support_profile),
        "student_state": asdict(student_state),
        "task_state": asdict(task_state),
        "scaffold_budget": asdict(scaffold_budget),
        "prompt_ladder": asdict(prompt_ladder),
        "risk_card": asdict(risk_card),
        "response_protocol": asdict(response_protocol),
        "used_support_level": answer_output["used_support_level"],
        "support_trace": answer_output["support_trace"],
        "weak_actor_attempt_count": answer_output.get("attempt_count"),
        "prediction_failed": False,
    }


def _print_progress(tag: str, current: int, total: int, *, question_id: str | None = None) -> None:
    message = f"{tag}: {current}/{total}"
    if question_id is not None:
        message += f" question_id={question_id}"
    print(message, flush=True)


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
    if args.bootstrap_from_run_dir:
        args.bootstrap_from_run_dir = _resolve_xes_path(args.bootstrap_from_run_dir)

    if args.strong_llm_no_auth:
        args.strong_llm_api_key = ""
    weak_api_key = args.weak_llm_api_key.strip() or os.environ.get(args.weak_llm_api_key_env, "").strip()
    if not weak_api_key:
        raise ValueError(f"missing weak llm api key via --weak_llm_api_key or env {args.weak_llm_api_key_env}")

    output_root = Path(args.output_root)
    if args.resume_run_dir:
        run_dir = Path(args.resume_run_dir)
        if not run_dir.exists():
            raise FileNotFoundError(f"resume_run_dir not found: {run_dir}")
    else:
        run_dir = output_root / datetime.now().strftime("run_%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=False)

    if args.bootstrap_from_run_dir:
        bootstrap_dir = Path(args.bootstrap_from_run_dir)
        if not bootstrap_dir.exists():
            raise FileNotFoundError(f"bootstrap_from_run_dir not found: {bootstrap_dir}")
        for filename in [
            "benchmark_summary.json",
            "benchmark_students.jsonl",
            "problem_profiles.json",
            "task_support_profiles.json",
            "student_models.jsonl",
        ]:
            source = bootstrap_dir / filename
            target = run_dir / filename
            if source.exists() and not target.exists():
                shutil.copy2(source, target)

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
        max_thinking_steps=1,
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
                    "history_summary": student.history_summary.__dict__,
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

    tasks: list[tuple[str, str, bool, str]] = []
    for student in benchmark_students:
        for question_id, real_is_correct in student.test:
            tasks.append((student.student_id, question_id, real_is_correct, student.history_summary.history_level))
    task_question_lookup = {
        question_id: question_lookup[question_id]
        for question_id in sorted({question_id for _, question_id, _, _ in tasks})
    }

    strong_client = OpenAICompatClient(
        LLMConfig(
            base_url=args.strong_llm_base_url,
            model=args.strong_llm_model,
            api_key=args.strong_llm_api_key,
            timeout_s=120.0,
            temperature=0.2,
            max_tokens=1200,
            response_format_json=True,
        )
    )
    weak_client = WeakOpenAICompatClient(
        WeakLLMConfig(
            base_url=args.weak_llm_base_url,
            model=args.weak_llm_model,
            api_key=weak_api_key,
            timeout_s=120.0,
            temperature=0.0,
            max_tokens=256,
            response_format_json=True,
            enable_thinking=bool(args.weak_enable_thinking),
        )
    )

    problem_profiles_path = run_dir / "problem_profiles.json"
    if problem_profiles_path.exists():
        problem_profiles = {
            str(question_id): _problem_profile_from_dict(profile)
            for question_id, profile in _read_json(problem_profiles_path).items()
        }
    else:
        problem_profiles = build_problem_profiles_for_questions(
            question_lookup=task_question_lookup,
            llm_client=strong_client,
        )
        _write_json(
            problem_profiles_path,
            {question_id: asdict(profile) for question_id, profile in problem_profiles.items()},
        )

    task_support_profiles_path = run_dir / "task_support_profiles.json"
    task_support_profiles_partial_path = run_dir / "task_support_profiles.partial.json"
    if task_support_profiles_path.exists():
        task_support_profiles = {
            str(question_id): task_support_profile_from_dict(profile)
            for question_id, profile in _read_json(task_support_profiles_path).items()
        }
    else:
        task_support_profiles = {}
        if task_support_profiles_partial_path.exists():
            task_support_profiles = {
                str(question_id): task_support_profile_from_dict(profile)
                for question_id, profile in _read_json(task_support_profiles_partial_path).items()
            }
        total_task_support = len(task_question_lookup)
        _print_progress(
            "task_support_profile resume",
            len(task_support_profiles),
            total_task_support,
        )
        for built_count, (question_id, question) in enumerate(task_question_lookup.items(), start=1):
            if question_id in task_support_profiles:
                continue
            task_support_profiles[question_id] = build_task_support_profile(
                question_text=question.question_text,
                options=question.options,
                question_type=question.question_type,
                problem_requirement_profile=problem_profiles[question_id],
                llm_client=strong_client,
            )
            _write_json(
                task_support_profiles_partial_path,
                {
                    stored_question_id: asdict(profile)
                    for stored_question_id, profile in task_support_profiles.items()
                },
            )
            _print_progress(
                "task_support_profile built",
                len(task_support_profiles),
                total_task_support,
                question_id=question_id,
            )
        _write_json(
            task_support_profiles_path,
            {
                question_id: asdict(profile)
                for question_id, profile in task_support_profiles.items()
            },
        )
        if task_support_profiles_partial_path.exists():
            task_support_profiles_partial_path.unlink()

    student_models_path = run_dir / "student_models.jsonl"
    student_models = {
        str(row["student_id"]): _student_model_from_dict(row)
        for row in _read_jsonl(student_models_path)
    }
    pending_students = [student for student in benchmark_students if student.student_id not in student_models]
    if pending_students:
        for student in pending_students:
            student_model = build_student_model(student.enhanced_persona, llm_client=strong_client)
            student_models[student.student_id] = student_model
            _append_jsonl(student_models_path, asdict(student_model))

    predictions_path = run_dir / "predictions.jsonl"
    records = _read_jsonl(predictions_path)
    completed_task_keys = {
        (str(record["student_id"]), str(record["question_id"]))
        for record in records
    }
    pending_tasks = [task for task in tasks if (str(task[0]), str(task[1])) not in completed_task_keys]
    if pending_tasks:
        total_pending_tasks = len(pending_tasks)
        with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
            future_map = {}
            for student_id, question_id, real_is_correct, history_level in pending_tasks:
                future = executor.submit(
                    _run_single_weak_prediction,
                    student_model=student_models[student_id],
                    question=question_lookup[question_id],
                    problem_profile=problem_profiles[question_id],
                    task_support_profile=task_support_profiles[question_id],
                    weak_client=weak_client,
                )
                future_map[future] = (student_id, question_id, real_is_correct, history_level)
            completed_now = 0
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
                        "prediction_failed": True,
                        "failure_stage": "weak_prediction",
                        "failure_type": type(exc).__name__,
                        "failure": str(exc),
                    }
                record["real_is_correct"] = bool(real_is_correct)
                record["history_level"] = history_level
                records.append(record)
                _append_jsonl(predictions_path, record)
                completed_now += 1
                if (
                    completed_now == 1
                    or completed_now == total_pending_tasks
                    or completed_now % 50 == 0
                ):
                    _print_progress(
                        "prediction progress",
                        completed_now,
                        total_pending_tasks,
                        question_id=question_id,
                    )

    records.sort(key=lambda row: (str(row["student_id"]), str(row["question_id"])))
    correctness_summary = apply_official_correctness_labels(
        records=records,
        question_lookup=question_lookup,
        llm_client=None,
        official_correctness_mode=args.official_correctness_mode,
    )
    metrics = evaluate_benchmark_run(
        records=records,
        benchmark_students=benchmark_students,
        question_lookup=question_lookup,
    )
    metrics["correctness_summary"] = correctness_summary
    run_config = dict(vars(args))
    run_config["strong_llm_api_key"] = "***REDACTED***"
    run_config["weak_llm_api_key"] = "***REDACTED***"
    metrics["run_config"] = run_config

    _write_jsonl(run_dir / "predictions.jsonl", records)
    _write_json(run_dir / "metrics.json", metrics)
    print(f"weak-model benchmark completed: {run_dir}", flush=True)
    print(f"n_students={len(benchmark_students)}", flush=True)
    print(f"n_predictions={len(records)}", flush=True)


if __name__ == "__main__":
    main()
