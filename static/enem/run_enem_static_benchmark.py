from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Any

from src.data_loading import (
    AreaItemBank,
    EnemStaticQuestion,
    EnemStaticStudent,
    build_dataset,
    load_area_item_bank,
    load_json,
    summarize_history,
)
from src.evaluation import evaluate_predictions
from src.hachimi import (
    HachimiMatch,
    build_enem_observed_profile,
    deterministic_hachimi_match,
    load_hachimi_matches,
    load_hachimi_personas,
    rank_hachimi_candidates,
    select_hachimi_match_with_llm,
)
from src.llm_client import LLMConfig, OpenAICompatClient
from src.question_images import build_question_page_manifest
from src.science_chain import (
    ConstraintBundle,
    ControlValueAnalysis,
    ItemResponseState,
    Prediction,
    ProblemRequirementProfile,
    SRLAnalysis,
    ScienceTaskCapabilityProfile,
    SelfEfficacyAnalysis,
    StudentInternalSignals,
    StudentItemInteractionDecision,
    StudentModel,
    build_problem_profile,
    build_student_item_interaction_decision,
    build_student_model,
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
    parser = argparse.ArgumentParser(description="Run ENEM static natural-science student simulation benchmark.")
    parser.add_argument("--config_path", default=str(ROOT / "configs" / "enem_cn_static_smoke_20260528.json"))
    parser.add_argument("--output_root", default=str(ROOT / "outputs" / "enem_cn_static_benchmark"))
    parser.add_argument("--run_dir", default=None)
    parser.add_argument("--history_size", type=int, default=None)
    parser.add_argument("--max_students", type=int, default=None)
    parser.add_argument("--max_questions", type=int, default=None)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--build_page_images", action="store_true")
    parser.add_argument("--page_image_dpi", type=int, default=150)
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
    parser.add_argument("--failure_rerun_rounds", type=int, default=2)
    parser.add_argument("--hachimi_persona_paths", nargs="*", default=[])
    return parser


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
            timeout_s=args.timeout_s,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            response_format_json=args.response_format_json,
        )
    )


def create_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def maybe_build_effective_config(config_path: Path, run_dir: Path, args: argparse.Namespace) -> Path:
    if not args.build_page_images:
        return config_path
    config = load_json(config_path)
    dataset_root = Path(str(config["source_dataset_root"]))
    area = str(config.get("target_area") or "CN")
    item_bank = load_area_item_bank(
        dataset_root=dataset_root,
        area=area,
        regular_codes=[str(code) for code in config.get("regular_codes", [])] or None,
        base_booklet_code=str(config["base_booklet_code"]) if config.get("base_booklet_code") else None,
    )
    cache_dir = (
        ROOT
        / "cache"
        / "question_images"
        / f"{area.upper()}_{item_bank.base_booklet_code}_dpi{args.page_image_dpi}_bbox_column_crop_v1"
    )
    manifest_path = cache_dir / "question_image_manifest.jsonl"
    build_question_page_manifest(
        dataset_root=dataset_root,
        item_bank=item_bank,
        output_path=manifest_path,
        page_image_dir=cache_dir / "pages",
        dpi=args.page_image_dpi,
    )
    config["question_image_manifest_path"] = str(manifest_path.resolve())
    config["question_image_cache_dir"] = str(cache_dir.resolve())
    effective_config_path = run_dir / "effective_config.json"
    write_json(effective_config_path, config)
    return effective_config_path


def load_student_model(row: dict[str, Any]) -> StudentModel:
    return StudentModel(
        student_id=str(row["student_id"]),
        grade=str(row["grade"]),
        academic_level=str(row["academic_level"]),
        weak_skill_areas=[str(item) for item in row["weak_skill_areas"]],
        strong_skill_areas=[str(item) for item in row["strong_skill_areas"]],
        self_efficacy_analysis=SelfEfficacyAnalysis(**row["self_efficacy_analysis"]),
        srl_analysis=SRLAnalysis(**row["srl_analysis"]),
        control_value_analysis=ControlValueAnalysis(**row["control_value_analysis"]),
        engagement_level_tendency=str(row["engagement_level_tendency"]),
        engagement_evidence=[str(item) for item in row["engagement_evidence"]],
        response_directness_description=str(row["response_directness_description"]),
        response_directness_evidence=[str(item) for item in row["response_directness_evidence"]],
        raw_summary=str(row["raw_summary"]),
        domain_anchor_profile_summary=str(row["domain_anchor_profile_summary"]),
        domain_anchor_profile_evidence=[str(item) for item in row["domain_anchor_profile_evidence"]],
        science_task_capability_profile=ScienceTaskCapabilityProfile(**row["science_task_capability_profile"]),
        matched_hachimi_id=row.get("matched_hachimi_id"),
        hachimi_profile_card=row.get("hachimi_profile_card"),
        hachimi_match_evidence=row.get("hachimi_match_evidence"),
        hachimi_conflict_evidence=row.get("hachimi_conflict_evidence"),
        fusion_rule=row.get("fusion_rule"),
    )


def load_student_models(path: Path) -> dict[str, StudentModel]:
    return {model.student_id: model for model in [load_student_model(row) for row in read_jsonl(path)]}


def load_internal_signals(path: Path, student_ids: list[str]) -> dict[str, StudentInternalSignals]:
    rows = read_jsonl(path)
    if len(rows) > len(student_ids):
        raise ValueError(f"too many internal signal rows: rows={len(rows)} students={len(student_ids)}")
    return {
        student_id: StudentInternalSignals(**row)
        for student_id, row in zip(student_ids, rows)
    }


def load_problem_profiles(path: Path) -> dict[str, ProblemRequirementProfile]:
    profiles = [ProblemRequirementProfile(**row) for row in read_jsonl(path)]
    return {profile.question_id: profile for profile in profiles}


def build_or_load_hachimi_matches(
    path: Path,
    students: list[EnemStaticStudent],
    hachimi_persona_paths: list[str],
    llm: OpenAICompatClient | None,
) -> dict[str, HachimiMatch]:
    if not hachimi_persona_paths:
        return {}
    matches = load_hachimi_matches(path)
    if matches:
        print(f"[Cache] loaded hachimi_matches={len(matches)}", flush=True)
    personas = load_hachimi_personas([Path(raw_path) for raw_path in hachimi_persona_paths])
    for idx, student in enumerate(students, start=1):
        if student.student_id in matches:
            continue
        if llm is None:
            match = deterministic_hachimi_match(student, personas)
        else:
            observed = build_enem_observed_profile(student)
            candidates = rank_hachimi_candidates(observed, personas, top_k=8)
            match = select_hachimi_match_with_llm(observed, candidates, llm)
        matches[student.student_id] = match
        append_jsonl_row(path, match.to_row())
        if len(matches) == 1 or len(matches) % 25 == 0 or idx == len(students):
            print(f"[HACHIMI] completed={len(matches)}/{len(students)}", flush=True)
    return matches


def build_or_load_student_models(
    path: Path,
    students: list[EnemStaticStudent],
    llm: OpenAICompatClient | None,
    hachimi_matches: dict[str, HachimiMatch],
) -> dict[str, StudentModel]:
    models = load_student_models(path) if path.exists() else {}
    if models:
        print(f"[Cache] loaded student_models={len(models)}", flush=True)
    for idx, student in enumerate(students, start=1):
        if student.student_id in models:
            continue
        model = build_student_model(student, llm, hachimi_matches.get(student.student_id))
        models[student.student_id] = model
        append_jsonl_row(path, asdict(model))
        if len(models) == 1 or len(models) % 25 == 0 or idx == len(students):
            print(f"[StudentModel] completed={len(models)}/{len(students)}", flush=True)
    return models


def build_or_load_internal_signals(
    path: Path,
    student_ids: list[str],
    student_models: dict[str, StudentModel],
    llm: OpenAICompatClient | None,
) -> dict[str, StudentInternalSignals]:
    signals = load_internal_signals(path, student_ids) if path.exists() else {}
    if signals:
        print(f"[Cache] loaded internal_signals={len(signals)}", flush=True)
    for idx, student_id in enumerate(student_ids, start=1):
        if student_id in signals:
            continue
        item = map_student_model_to_internal_signals(student_models[student_id], llm)
        signals[student_id] = item
        append_jsonl_row(path, asdict(item))
        if len(signals) == 1 or len(signals) % 25 == 0 or idx == len(student_ids):
            print(f"[InternalSignals] completed={len(signals)}/{len(student_ids)}", flush=True)
    return signals


def build_or_load_problem_profiles(
    path: Path,
    questions: list[EnemStaticQuestion],
    llm: OpenAICompatClient | None,
) -> dict[str, ProblemRequirementProfile]:
    profiles = load_problem_profiles(path) if path.exists() else {}
    if profiles:
        print(f"[Cache] loaded problem_profiles={len(profiles)}", flush=True)
    for idx, question in enumerate(questions, start=1):
        if question.question_id in profiles:
            continue
        profile = build_problem_profile(question, llm)
        profiles[question.question_id] = profile
        append_jsonl_row(path, asdict(profile))
        if len(profiles) == 1 or len(profiles) % 10 == 0 or idx == len(questions):
            print(f"[ProblemProfile] completed={len(profiles)}/{len(questions)}", flush=True)
    return profiles


def run_single_prediction(
    student: EnemStaticStudent,
    question: EnemStaticQuestion,
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
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
    student: EnemStaticStudent,
    question: EnemStaticQuestion,
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    problem_profile: ProblemRequirementProfile,
    llm: OpenAICompatClient | None,
    max_generation_attempts: int,
    task_retry_attempts: int,
) -> Prediction:
    last_error: Exception | None = None
    for _ in range(max(1, task_retry_attempts)):
        try:
            return run_single_prediction(
                student,
                question,
                student_model,
                internal_signals,
                problem_profile,
                llm,
                max_generation_attempts,
            )
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"prediction failed after {task_retry_attempts} attempt(s): "
        f"student_id={student.student_id}, question_id={question.question_id}, error={last_error!r}"
    )


def prediction_to_row(prediction: Prediction) -> dict[str, Any]:
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


def prediction_row_to_eval_object(row: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        student_id=str(row["student_id"]),
        question_id=str(row["question_id"]),
        predicted_answer=str(row["predicted_answer"]),
        student_response=str(row["student_response"]),
    )


def prediction_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["student_id"]), str(row["question_id"])


def main() -> None:
    args = build_parser().parse_args()
    run_dir = create_run_dir(args)
    config_path = maybe_build_effective_config(Path(args.config_path), run_dir, args)
    dataset = build_dataset(
        config_path=config_path,
        history_size=args.history_size,
        max_students=args.max_students,
        max_questions=args.max_questions,
    )
    llm = make_llm(args)
    write_json(
        run_dir / "run_config.json",
        {
            "config_path": str(config_path),
            "history_size": args.history_size,
            "max_students": args.max_students,
            "max_questions": args.max_questions,
            "dry_run": args.dry_run,
            "build_page_images": args.build_page_images,
            "llm_base_url": args.llm_base_url,
            "llm_model": args.llm_model,
            "max_concurrency": args.max_concurrency,
            "generation_attempts": args.generation_attempts,
            "task_retry_attempts": args.task_retry_attempts,
            "failure_rerun_rounds": args.failure_rerun_rounds,
            "hachimi_persona_paths": args.hachimi_persona_paths,
        },
    )

    students = dataset.students
    questions = [dataset.questions[question_id] for question_id in dataset.test_item_ids]
    print(f"[Data] area={dataset.target_area} students={len(students)} questions={len(questions)} tasks={len(students) * len(questions)}")
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
        hachimi_matches,
    )
    internal_signals = build_or_load_internal_signals(
        run_dir / "student_internal_signals.jsonl",
        student_ids,
        student_models,
        llm,
    )
    problem_profiles = build_or_load_problem_profiles(run_dir / "problem_profiles.jsonl", questions, llm)

    prediction_path = run_dir / "predictions.jsonl"
    failure_path = run_dir / "failures.jsonl"
    failure_attempts_path = run_dir / "failure_attempts.jsonl"
    existing_rows = read_jsonl(prediction_path)
    completed_keys = {prediction_key(row) for row in existing_rows}
    total_tasks = len(students) * len(questions)
    pending_pairs = [
        (student, question)
        for student in students
        for question in questions
        if (student.student_id, question.question_id) not in completed_keys
    ]
    max_rounds = 1 + max(0, args.failure_rerun_rounds)
    progress_path = run_dir / "progress.json"
    for round_idx in range(max_rounds):
        if not pending_pairs:
            break
        round_failures: list[dict[str, Any]] = []
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
                tasks[future] = {"student_id": student.student_id, "question_id": question.question_id}
            print(
                f"[Predict] round={round_idx + 1}/{max_rounds} submitted={len(tasks)} skipped={len(completed_keys)} total={total_tasks}",
                flush=True,
            )
            for future in as_completed(tasks):
                meta = tasks[future]
                try:
                    prediction = future.result()
                    append_jsonl_row(prediction_path, prediction_to_row(prediction))
                    completed_keys.add((prediction.student_id, prediction.question_id))
                    if len(completed_keys) == 1 or len(completed_keys) % 100 == 0:
                        write_json(
                            progress_path,
                            {
                                "total_tasks": total_tasks,
                                "completed_total": len(completed_keys),
                                "failures_in_round": len(round_failures),
                                "round": round_idx + 1,
                                "updated_at": datetime.now().isoformat(timespec="seconds"),
                            },
                        )
                        print(f"[Progress] completed_total={len(completed_keys)}/{total_tasks}", flush=True)
                except Exception as exc:
                    failure = {
                        "student_id": meta["student_id"],
                        "question_id": meta["question_id"],
                        "round": round_idx + 1,
                        "error": repr(exc),
                    }
                    round_failures.append(failure)
                    append_jsonl_row(failure_attempts_path, failure)
        pending_key_set = {(str(row["student_id"]), str(row["question_id"])) for row in round_failures}
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
        write_jsonl(
            failure_path,
            [{"student_id": student.student_id, "question_id": question.question_id} for student, question in pending_pairs],
        )
        raise RuntimeError(f"{len(pending_pairs)} prediction tasks still failed; see {failure_path}")

    all_rows = read_jsonl(prediction_path)
    unique_count = len({prediction_key(row) for row in all_rows})
    if unique_count != total_tasks:
        raise RuntimeError(f"prediction count mismatch: unique={unique_count}, expected={total_tasks}")
    all_rows.sort(key=lambda row: (int(str(row["student_id"])), int(str(row["question_id"]))))
    write_jsonl(prediction_path, all_rows)
    metrics, eval_rows = evaluate_predictions(
        [prediction_row_to_eval_object(row) for row in all_rows],  # type: ignore[arg-type]
        students,
        dataset.questions,
    )
    write_jsonl(run_dir / "eval_rows.jsonl", eval_rows)
    write_json(run_dir / "metrics.json", metrics)
    write_json(
        progress_path,
        {
            "total_tasks": total_tasks,
            "completed_total": total_tasks,
            "failures": 0,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    print(f"[Done] run_dir={run_dir}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
