from __future__ import annotations

import argparse
import json
import os
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from src.data_loading import EediStaticQuestion, EediStaticStudent, build_dataset, summarize_history
from src.evaluation import evaluate_predictions
from src.hachimi import (
    HachimiMatch,
    build_eedi_observed_profile,
    load_hachimi_matches,
    load_hachimi_personas,
    rank_hachimi_candidates,
    select_hachimi_match_with_llm,
)
from src.llm_client import LLMConfig, OpenAICompatClient
from src.static_chain import (
    ControlValueAnalysis,
    MathTaskCapabilityProfile,
    Prediction,
    ProblemRequirementProfile,
    SRLAnalysis,
    SelfEfficacyAnalysis,
    StudentInternalSignals,
    StudentModel,
    build_problem_profile,
    build_student_model,
    build_student_item_interaction_decision,
    compile_constraints,
    generate_prediction,
    map_student_model_to_internal_signals,
    resolve_item_response_state,
)


ROOT = Path(__file__).resolve().parent
JSONL_APPEND_LOCK = Lock()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl_row(path: Path, row: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_APPEND_LOCK:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run independent EEDI-static student simulation benchmark.")
    parser.add_argument(
        "--config_path",
        default=str(ROOT / "configs" / "eedi_static_common_test_676x265_text_only_clean_20260520.json"),
    )
    parser.add_argument("--output_root", default=str(ROOT / "outputs" / "eedi_static_benchmark"))
    parser.add_argument("--run_dir", default=None, help="Existing or new run directory. Existing cached objects are reused.")
    parser.add_argument("--history_size", type=int, default=30)
    parser.add_argument("--max_students", type=int, default=None)
    parser.add_argument("--max_questions", type=int, default=None)
    parser.add_argument("--dry_run", action="store_true", help="Use deterministic local heuristics instead of LLM calls.")
    parser.add_argument("--llm_base_url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--llm_model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--llm_api_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max_tokens", type=int, default=1800)
    parser.add_argument("--timeout_s", type=float, default=120.0)
    parser.add_argument("--response_format_json", action="store_true")
    parser.add_argument("--max_concurrency", type=int, default=4)
    parser.add_argument("--generation_attempts", type=int, default=4)
    parser.add_argument("--task_retry_attempts", type=int, default=2)
    parser.add_argument("--failure_rerun_rounds", type=int, default=3)
    parser.add_argument(
        "--hachimi_persona_paths",
        nargs="*",
        default=[],
        help="Optional HACHIMI persona jsonl paths. When set, each EEDI student gets an auditable HACHIMI match.",
    )
    return parser


def load_student_model(row: dict[str, object]) -> StudentModel:
    return StudentModel(
        student_id=str(row["student_id"]),
        grade=str(row["grade"]),
        academic_level=str(row["academic_level"]),
        weak_subjects=list(row["weak_subjects"]),  # type: ignore[arg-type]
        strong_subjects=list(row["strong_subjects"]),  # type: ignore[arg-type]
        self_efficacy_analysis=SelfEfficacyAnalysis(**row["self_efficacy_analysis"]),  # type: ignore[arg-type]
        srl_analysis=SRLAnalysis(**row["srl_analysis"]),  # type: ignore[arg-type]
        control_value_analysis=ControlValueAnalysis(**row["control_value_analysis"]),  # type: ignore[arg-type]
        engagement_level_tendency=str(row["engagement_level_tendency"]),
        engagement_evidence=list(row["engagement_evidence"]),  # type: ignore[arg-type]
        response_directness_description=str(row["response_directness_description"]),
        response_directness_evidence=list(row["response_directness_evidence"]),  # type: ignore[arg-type]
        raw_summary=str(row["raw_summary"]),
        math_anchor_profile_summary=str(row["math_anchor_profile_summary"]),
        math_anchor_profile_evidence=list(row["math_anchor_profile_evidence"]),  # type: ignore[arg-type]
        math_task_capability_profile=MathTaskCapabilityProfile(**row["math_task_capability_profile"]),  # type: ignore[arg-type]
        matched_hachimi_id=str(row["matched_hachimi_id"]) if row.get("matched_hachimi_id") is not None else None,
        hachimi_profile_card=dict(row["hachimi_profile_card"]) if row.get("hachimi_profile_card") is not None else None,
        hachimi_match_evidence=(
            [str(item) for item in row["hachimi_match_evidence"]]
            if row.get("hachimi_match_evidence") is not None
            else None
        ),
        hachimi_conflict_evidence=(
            [str(item) for item in row["hachimi_conflict_evidence"]]
            if row.get("hachimi_conflict_evidence") is not None
            else None
        ),
        fusion_rule=str(row["fusion_rule"]) if row.get("fusion_rule") is not None else None,
    )


def load_student_models(path: Path) -> dict[str, StudentModel]:
    models = [load_student_model(row) for row in read_jsonl(path)]
    return {model.student_id: model for model in models}


def load_internal_signals(path: Path, student_ids: list[str]) -> dict[str, StudentInternalSignals]:
    rows = read_jsonl(path)
    if len(rows) != len(student_ids):
        raise ValueError(f"cannot map internal signals: rows={len(rows)} students={len(student_ids)}")
    return {
        student_id: StudentInternalSignals(**row)  # type: ignore[arg-type]
        for student_id, row in zip(student_ids, rows)
    }


def load_problem_profiles(path: Path) -> dict[str, ProblemRequirementProfile]:
    profiles = [ProblemRequirementProfile(**row) for row in read_jsonl(path)]  # type: ignore[arg-type]
    return {profile.question_id: profile for profile in profiles}


def build_or_load_student_models(
    path: Path,
    students: list[EediStaticStudent],
    llm: OpenAICompatClient | None,
    hachimi_matches: dict[str, HachimiMatch] | None = None,
) -> dict[str, StudentModel]:
    student_models = load_student_models(path) if path.exists() else {}
    if student_models:
        print(f"[Cache] loaded student_models={len(student_models)}", flush=True)
    if hachimi_matches:
        stale = [
            student_id
            for student_id, model in student_models.items()
            if student_id in hachimi_matches and model.matched_hachimi_id is None
        ]
        if stale:
            raise ValueError(
                "existing student_models cache was built without HACHIMI; "
                f"use a fresh run_dir or delete student_models.jsonl. stale_count={len(stale)}"
            )
    for idx, student in enumerate(students, start=1):
        if student.student_id in student_models:
            continue
        model = build_student_model(
            student,
            llm,
            hachimi_match=hachimi_matches.get(student.student_id) if hachimi_matches else None,
        )
        student_models[student.student_id] = model
        append_jsonl_row(path, asdict(model))
        if len(student_models) == 1 or len(student_models) % 25 == 0 or idx == len(students):
            print(f"[StudentModel] completed={len(student_models)}/{len(students)}", flush=True)
    return student_models


def build_or_load_hachimi_matches(
    path: Path,
    students: list[EediStaticStudent],
    hachimi_persona_paths: list[str],
    llm: OpenAICompatClient | None,
) -> dict[str, HachimiMatch]:
    if not hachimi_persona_paths:
        return {}
    if llm is None:
        raise ValueError("--hachimi_persona_paths requires an LLM because final HACHIMI matching is model-based")
    matches = load_hachimi_matches(path)
    if matches:
        print(f"[Cache] loaded hachimi_matches={len(matches)}", flush=True)
    stale_matches = [
        student.student_id
        for student in students
        if student.student_id in matches
        and (
            matches[student.student_id].matcher_version != "llm_profile_matcher_v1"
            or not matches[student.student_id].candidate_hachimi_ids
        )
    ]
    if stale_matches:
        raise ValueError(
            "existing hachimi_matches cache was not built by llm_profile_matcher_v1; "
            f"use a fresh run_dir or delete hachimi_matches.jsonl. stale_count={len(stale_matches)}"
        )
    personas = load_hachimi_personas([Path(raw_path) for raw_path in hachimi_persona_paths])
    for idx, student in enumerate(students, start=1):
        if student.student_id in matches:
            continue
        observed_profile = build_eedi_observed_profile(student, age=student.age_floor)
        candidates = rank_hachimi_candidates(observed_profile, personas, top_k=8)
        match = select_hachimi_match_with_llm(observed_profile, candidates, llm)
        matches[student.student_id] = match
        append_jsonl_row(path, match.to_row())
        if len(matches) == 1 or len(matches) % 25 == 0 or idx == len(students):
            print(f"[HACHIMI] completed={len(matches)}/{len(students)}", flush=True)
    return matches


def build_or_load_internal_signals(
    path: Path,
    student_ids: list[str],
    student_models: dict[str, StudentModel],
    llm: OpenAICompatClient | None,
) -> dict[str, StudentInternalSignals]:
    rows = read_jsonl(path)
    internal_signals: dict[str, StudentInternalSignals] = {}
    if rows:
        if len(rows) > len(student_ids):
            raise ValueError(f"too many internal signal rows: rows={len(rows)} students={len(student_ids)}")
        internal_signals = {
            student_id: StudentInternalSignals(**row)  # type: ignore[arg-type]
            for student_id, row in zip(student_ids, rows)
        }
        print(f"[Cache] loaded internal_signals={len(internal_signals)}", flush=True)
    for idx, student_id in enumerate(student_ids, start=1):
        if student_id in internal_signals:
            continue
        signals = map_student_model_to_internal_signals(student_models[student_id], llm)
        internal_signals[student_id] = signals
        append_jsonl_row(path, asdict(signals))
        if len(internal_signals) == 1 or len(internal_signals) % 25 == 0 or idx == len(student_ids):
            print(f"[InternalSignals] completed={len(internal_signals)}/{len(student_ids)}", flush=True)
    return internal_signals


def build_or_load_problem_profiles(
    path: Path,
    questions: list[EediStaticQuestion],
    llm: OpenAICompatClient | None,
) -> dict[str, ProblemRequirementProfile]:
    problem_profiles = load_problem_profiles(path) if path.exists() else {}
    if problem_profiles:
        print(f"[Cache] loaded problem_profiles={len(problem_profiles)}", flush=True)
    for idx, question in enumerate(questions, start=1):
        if question.question_id in problem_profiles:
            continue
        profile = build_problem_profile(question, llm)
        problem_profiles[question.question_id] = profile
        append_jsonl_row(path, asdict(profile))
        if len(problem_profiles) == 1 or len(problem_profiles) % 10 == 0 or idx == len(questions):
            print(f"[ProblemProfile] completed={len(problem_profiles)}/{len(questions)}", flush=True)
    return problem_profiles


def make_llm(args: argparse.Namespace) -> OpenAICompatClient | None:
    if args.dry_run:
        return None
    if not args.llm_base_url or not args.llm_model:
        raise ValueError("--llm_base_url and --llm_model are required unless --dry_run is set")
    return OpenAICompatClient(
        LLMConfig(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout_s,
            response_format_json=args.response_format_json,
        )
    )


def run_single_prediction(
    student: EediStaticStudent,
    question: EediStaticQuestion,
    student_model,
    internal_signals,
    problem_profile,
    llm: OpenAICompatClient | None,
    max_generation_attempts: int,
) -> Prediction:
    interaction = build_student_item_interaction_decision(
        student_model=student_model,
        internal_signals=internal_signals,
        profile=problem_profile,
        question=question,
        llm=llm,
    )
    response_state = resolve_item_response_state(
        student_model=student_model,
        internal_signals=internal_signals,
        profile=problem_profile,
        interaction_decision=interaction,
        llm=llm,
    )
    constraints = compile_constraints(response_state)
    return generate_prediction(
        student=student,
        question=question,
        student_model=student_model,
        internal_signals=internal_signals,
        problem_profile=problem_profile,
        interaction_decision=interaction,
        item_state=response_state,
        constraints=constraints,
        llm=llm,
        max_generation_attempts=max_generation_attempts,
    )


def run_prediction_task_with_retries(
    student: EediStaticStudent,
    question: EediStaticQuestion,
    student_model,
    internal_signals,
    problem_profile,
    llm: OpenAICompatClient | None,
    max_generation_attempts: int,
    task_retry_attempts: int,
) -> Prediction:
    if task_retry_attempts < 1:
        raise ValueError("task_retry_attempts must be >= 1")
    last_error: Exception | None = None
    for _attempt_idx in range(task_retry_attempts):
        try:
            return run_single_prediction(
                student=student,
                question=question,
                student_model=student_model,
                internal_signals=internal_signals,
                problem_profile=problem_profile,
                llm=llm,
                max_generation_attempts=max_generation_attempts,
            )
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"prediction failed after {task_retry_attempts} task attempt(s): "
        f"student_id={student.student_id}, question_id={question.question_id}, error={last_error!r}"
    )


def prediction_to_row(prediction: Prediction) -> dict[str, object]:
    return {
        "student_id": prediction.student_id,
        "question_id": prediction.question_id,
        "predicted_answer": prediction.predicted_answer,
        "student_response": prediction.student_response,
        "student_model": asdict(prediction.student_model),
        "internal_signals": asdict(prediction.internal_signals),
        "problem_profile": asdict(prediction.problem_profile),
        "interaction_decision": asdict(prediction.interaction_decision),
        "response_state": asdict(prediction.response_state),
        "constraint_bundle": asdict(prediction.constraint_bundle),
        "violation_report": asdict(prediction.violation_report),
        "retry_count": prediction.retry_count,
    }


def prediction_row_to_eval_object(row: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        student_id=str(row["student_id"]),
        question_id=str(row["question_id"]),
        predicted_answer=str(row["predicted_answer"]),
        student_response=str(row["student_response"]),
    )


def prediction_key(row: dict[str, object]) -> tuple[str, str]:
    return str(row["student_id"]), str(row["question_id"])


def main() -> None:
    args = build_parser().parse_args()
    config_path = Path(args.config_path)
    dataset = build_dataset(
        config_path=config_path,
        history_size=args.history_size,
        max_students=args.max_students,
        max_questions=args.max_questions,
    )
    llm = make_llm(args)

    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=False)
    if not (run_dir / "run_config.json").exists():
        write_json(
            run_dir / "run_config.json",
            {
                "config_path": str(config_path),
                "history_size": args.history_size,
                "max_students": args.max_students,
                "max_questions": args.max_questions,
                "dry_run": args.dry_run,
                "llm_base_url": args.llm_base_url,
                "llm_model": args.llm_model,
            "max_concurrency": args.max_concurrency,
            "generation_attempts": args.generation_attempts,
            "task_retry_attempts": args.task_retry_attempts,
            "failure_rerun_rounds": args.failure_rerun_rounds,
            "hachimi_persona_paths": args.hachimi_persona_paths,
        },
    )

    question_ids = list(dataset.questions)
    questions = [dataset.questions[question_id] for question_id in question_ids]
    students = dataset.students

    print(f"[Data] students={len(students)} questions={len(questions)} tasks={len(students) * len(questions)}")
    if not (run_dir / "benchmark_students.jsonl").exists():
        write_jsonl(run_dir / "benchmark_students.jsonl", [asdict(student) for student in students])
    if not (run_dir / "questions.jsonl").exists():
        write_jsonl(run_dir / "questions.jsonl", [asdict(question) for question in questions])
    if not (run_dir / "history_summaries.jsonl").exists():
        write_jsonl(run_dir / "history_summaries.jsonl", [summarize_history(student) for student in students])

    student_ids = [student.student_id for student in students]
    hachimi_matches = build_or_load_hachimi_matches(
        run_dir / "hachimi_matches.jsonl",
        students,
        args.hachimi_persona_paths,
        llm,
    )
    student_models = build_or_load_student_models(
        run_dir / "student_models.jsonl",
        students,
        llm,
        hachimi_matches=hachimi_matches,
    )
    internal_signals = build_or_load_internal_signals(
        run_dir / "student_internal_signals.jsonl",
        student_ids,
        student_models,
        llm,
    )
    problem_profiles = build_or_load_problem_profiles(run_dir / "problem_profiles.jsonl", questions, llm)

    predictions: list[Prediction] = []
    prediction_path = run_dir / "predictions.jsonl"
    failure_path = run_dir / "failures.jsonl"
    failure_attempts_path = run_dir / "failure_attempts.jsonl"
    existing_prediction_rows = read_jsonl(prediction_path)
    completed_keys = {prediction_key(row) for row in existing_prediction_rows}
    total_tasks = len(students) * len(questions)
    progress_path = run_dir / "progress.json"
    if completed_keys:
        print(f"[Resume] completed_predictions={len(completed_keys)}", flush=True)
    if failure_path.exists() and len(completed_keys) < total_tasks:
        archived_failure_path = run_dir / f"failures_previous_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        failure_path.rename(archived_failure_path)
        print(f"[Resume] archived previous failures to {archived_failure_path}", flush=True)

    pending_pairs = [
        (student, question)
        for student in students
        for question in questions
        if (student.student_id, question.question_id) not in completed_keys
    ]
    completed_this_run = 0
    total_failures_this_run = 0
    max_rounds = 1 + max(0, args.failure_rerun_rounds)
    for round_idx in range(max_rounds):
        if not pending_pairs:
            break
        round_failures: list[dict[str, object]] = []
        tasks = {}
        with ThreadPoolExecutor(max_workers=max(1, args.max_concurrency)) as executor:
            for student, question in pending_pairs:
                future = executor.submit(
                    run_prediction_task_with_retries,
                    student,
                    question,
                    student_models[student.student_id],
                    internal_signals[student.student_id],
                    problem_profiles[question.question_id],
                    llm,
                    args.generation_attempts,
                    args.task_retry_attempts,
                )
                tasks[future] = {
                    "student_id": student.student_id,
                    "question_id": question.question_id,
                }
            print(
                f"[Predict] round={round_idx + 1}/{max_rounds} submitted={len(tasks)} "
                f"skipped={len(completed_keys)} total={total_tasks}",
                flush=True,
            )
            for future in as_completed(tasks):
                task_meta = tasks[future]
                try:
                    prediction = future.result()
                    predictions.append(prediction)
                    append_jsonl_row(prediction_path, prediction_to_row(prediction))
                    completed_keys.add((prediction.student_id, prediction.question_id))
                    completed_this_run += 1
                    completed_total = len(completed_keys)
                    if completed_this_run == 1 or completed_this_run % 100 == 0:
                        write_json(
                            progress_path,
                            {
                                "total_tasks": total_tasks,
                                "completed_existing": len(existing_prediction_rows),
                                "completed_this_run": completed_this_run,
                                "completed_total": completed_total,
                                "failures": total_failures_this_run + len(round_failures),
                                "remaining_submitted": len(tasks) - completed_this_run - len(round_failures),
                                "failure_rerun_round": round_idx,
                                "updated_at": datetime.now().isoformat(timespec="seconds"),
                            },
                        )
                        print(
                            f"[Progress] completed_total={completed_total}/{total_tasks} "
                            f"failures={total_failures_this_run + len(round_failures)}",
                            flush=True,
                        )
                except Exception as exc:
                    failure = {
                        "student_id": task_meta["student_id"],
                        "question_id": task_meta["question_id"],
                        "round": round_idx + 1,
                        "error": repr(exc),
                    }
                    round_failures.append(failure)
                    append_jsonl_row(failure_attempts_path, failure)
        total_failures_this_run += len(round_failures)
        pending_key_set = {
            (str(failure["student_id"]), str(failure["question_id"]))
            for failure in round_failures
        }
        pending_pairs = [
            (student, question)
            for student in students
            for question in questions
            if (student.student_id, question.question_id) in pending_key_set
            and (student.student_id, question.question_id) not in completed_keys
        ]
        if pending_pairs:
            print(f"[Retry] round={round_idx + 1} remaining_failures={len(pending_pairs)}", flush=True)

    if pending_pairs:
        final_failures = [
            {"student_id": student.student_id, "question_id": question.question_id}
            for student, question in pending_pairs
        ]
        write_jsonl(failure_path, final_failures)
        raise RuntimeError(
            f"{len(final_failures)} prediction tasks still failed after {max_rounds} round(s); "
            f"{len(predictions)} succeeded and were appended to {prediction_path}; "
            f"see {failure_path}"
        )

    all_prediction_rows = read_jsonl(prediction_path)
    if len({prediction_key(row) for row in all_prediction_rows}) != total_tasks:
        raise RuntimeError(
            f"prediction count mismatch: unique={len({prediction_key(row) for row in all_prediction_rows})}, "
            f"expected={total_tasks}"
        )
    write_json(
        progress_path,
        {
            "total_tasks": total_tasks,
            "completed_existing": len(completed_keys),
            "completed_this_run": len(predictions),
            "completed_total": total_tasks,
            "failures": 0,
            "remaining_submitted": 0,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    all_prediction_rows.sort(key=lambda row: (int(str(row["student_id"])), int(str(row["question_id"]))))
    write_jsonl(prediction_path, all_prediction_rows)
    metrics, eval_rows = evaluate_predictions(
        [prediction_row_to_eval_object(row) for row in all_prediction_rows],  # type: ignore[arg-type]
        students,
        dataset.questions,
    )
    write_jsonl(run_dir / "eval_rows.jsonl", eval_rows)
    write_json(run_dir / "metrics.json", metrics)

    print(f"[Done] run_dir={run_dir}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
