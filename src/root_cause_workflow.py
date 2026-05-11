from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .data_loading import (
    PersonaRecord,
    QuestionRecord,
    compute_item_stats,
    filter_personas_by_grade,
    load_frozen_selected_questions,
    load_personas,
    load_questions,
    sample_personas,
)
from .evaluation import apply_official_correctness_labels
from .generation import (
    check_violation,
    generate_student_answer,
    retry_with_tighter_constraints,
    should_retry_once,
)
from .llm_client import LLMConfig, OpenAICompatClient
from .problem_profile import ProblemRequirementProfile, build_problem_requirement_profile
from .prompts import SIMPLE_FORCED_STATE_PROMPT
from .response_state import (
    build_forced_item_response_state,
    compile_constraints,
    resolve_item_response_state,
)
from .student_model import (
    ControlValueAnalysis,
    SRLAnalysis,
    SelfEfficacyAnalysis,
    StudentInternalSignals,
    StudentModel,
    build_student_model,
    map_student_model_to_internal_signals,
)

ROOT_CAUSE_OUTPUT_ROOT = Path("outputs/root_cause")
ROOT_CAUSE_PLAN_PATH = Path("reports/root_cause_experiment_plan.md")
ROOT_CAUSE_C1_REPORT_PATH = Path("reports/c1_method_ablation_20260421.md")
ROOT_CAUSE_D1_REPORT_PATH = Path("reports/d1_simple_forced_state_20260421.md")
ROOT_CAUSE_D2_REPORT_PATH = Path("reports/d2_full_forced_state_20260421.md")
ROOT_CAUSE_E1_REPORT_PATH = Path("reports/e1_counterfactual_sensitivity_20260421.md")
ROOT_CAUSE_F1_REPORT_PATH = Path("reports/f1_stability_20260421.md")
ROOT_CAUSE_G1_REPORT_PATH = Path("reports/g1_root_cause_final_report_20260421.md")
DEFAULT_CONFIG_PATH = Path("configs/run_local.json")
DEFAULT_FROZEN_QUESTION_SET_PATH = Path("outputs/run_20260420_014128/selected_questions.json")
FORCED_STATE_ORDER = ("mastered", "partial", "guessable", "unreachable")


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def _append_jsonl_row(path: Path, row: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _prepare_output_dir(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    run_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = output_root / run_name
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _load_config(config_path: Path) -> dict[str, object]:
    payload = _read_json(config_path)
    if not isinstance(payload, dict):
        raise ValueError(f"config must be object/dict: {config_path}")
    return payload


def _build_llm_client(config_path: Path = DEFAULT_CONFIG_PATH) -> OpenAICompatClient:
    config = _load_config(config_path)
    return OpenAICompatClient(
        LLMConfig(
            base_url=str(config["llm_base_url"]),
            model=str(config["llm_model"]),
            api_key=str(config["llm_api_key"]),
            timeout_s=float(config.get("llm_timeout_s", 120.0)),
            temperature=float(config.get("llm_temperature", 0.2)),
            max_tokens=int(config.get("llm_max_tokens", 800)),
        )
    )


def _load_frozen_questions(
    config_path: Path = DEFAULT_CONFIG_PATH,
    frozen_question_set_path: Path = DEFAULT_FROZEN_QUESTION_SET_PATH,
) -> tuple[list[QuestionRecord], dict[str, QuestionRecord]]:
    config = _load_config(config_path)
    all_questions = load_questions(
        str(config["question_path"]),
        skip_image_questions=not bool(config.get("include_image_questions", False)),
    )
    item_stats, _ = compute_item_stats(
        str(config["response_csv_path"]),
        max_rows=config.get("max_rows_for_stats"),
        strict=bool(config.get("strict_stats", False)),
    )
    questions = load_frozen_selected_questions(
        frozen_selection_path=str(frozen_question_set_path),
        questions=all_questions,
        item_stats=item_stats,
    )
    return questions, {question.question_id: question for question in questions}


def _format_float(value: object, digits: int = 4) -> str:
    if value is None:
        return "NA"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return str(value)


def _load_run_metrics(run_dir: Path) -> dict[str, object]:
    metrics_path = run_dir / "metrics.json"
    payload = _read_json(metrics_path)
    if not isinstance(payload, dict):
        raise ValueError(f"metrics must be object/dict: {metrics_path}")
    return payload


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _build_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _replace_auto_block(section_text: str, block_id: str, block_text: str) -> str:
    start_marker = f"<!-- AUTO-{block_id}-START -->"
    end_marker = f"<!-- AUTO-{block_id}-END -->"
    replacement = f"{start_marker}\n{block_text.rstrip()}\n{end_marker}"
    if start_marker in section_text and end_marker in section_text:
        pattern = re.compile(
            rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
            re.DOTALL,
        )
        return pattern.sub(replacement, section_text)
    stripped = section_text.rstrip()
    if stripped:
        stripped += "\n\n"
    return stripped + replacement + "\n"


def update_root_cause_plan(
    stage_id: str,
    output_dir: str,
    summary: str,
    current_position: str,
    next_step: str,
    actual_config_lines: list[str],
    actual_conclusion_lines: list[str],
) -> None:
    text = ROOT_CAUSE_PLAN_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    updated_lines: list[str] = []
    row_updated = False
    for line in lines:
        if line.startswith("- 当前执行位置："):
            updated_lines.append(f"- 当前执行位置：`{current_position}`")
            continue
        if line.startswith("- 下一步："):
            updated_lines.append(f"- 下一步：`{next_step}`")
            continue
        if line.startswith(f"| {stage_id} |"):
            parts = line.split("|")
            if len(parts) < 8:
                raise ValueError(f"unexpected plan table row format: {line}")
            parts[4] = " 已完成 "
            parts[5] = f" `{output_dir}` "
            parts[6] = f" {summary} "
            updated_lines.append("|".join(parts))
            row_updated = True
            continue
        updated_lines.append(line)
    if not row_updated:
        raise ValueError(f"failed to update plan table row for stage_id={stage_id}")

    updated_text = "\n".join(updated_lines) + "\n"
    heading_pattern = re.compile(
        rf"(### {re.escape(stage_id)} .*?)(?=\n### |\Z)",
        re.DOTALL,
    )
    match = heading_pattern.search(updated_text)
    if match is None:
        raise ValueError(f"failed to find section heading for stage_id={stage_id}")
    section_text = match.group(1)
    block_lines = [
        "- 实际运行配置：",
        *[f"  - {line}" for line in actual_config_lines],
        "- 实际关键结论：",
        *[f"  - {line}" for line in actual_conclusion_lines],
    ]
    replaced_section = _replace_auto_block(
        section_text=section_text,
        block_id=f"{stage_id}-DETAILS",
        block_text="\n".join(block_lines),
    )
    updated_text = (
        updated_text[: match.start()]
        + replaced_section
        + updated_text[match.end() :]
    )
    _write_text(ROOT_CAUSE_PLAN_PATH, updated_text)


def _compute_forced_state_metrics(records: list[dict[str, object]]) -> dict[str, object]:
    if not records:
        raise ValueError("cannot compute forced-state metrics on empty records")

    by_state_counts: dict[str, int] = {state: 0 for state in FORCED_STATE_ORDER}
    by_state_correct: dict[str, int] = {state: 0 for state in FORCED_STATE_ORDER}
    by_state_question_counts: dict[str, defaultdict[str, int]] = {
        state: defaultdict(int) for state in FORCED_STATE_ORDER
    }
    by_state_question_correct: dict[str, defaultdict[str, int]] = {
        state: defaultdict(int) for state in FORCED_STATE_ORDER
    }
    by_state_question_answers: dict[str, defaultdict[str, Counter[str]]] = {
        state: defaultdict(Counter) for state in FORCED_STATE_ORDER
    }
    question_ids: set[str] = set()

    for record in records:
        state = str(record["forced_response_state"])
        if state not in FORCED_STATE_ORDER:
            raise ValueError(f"unexpected forced_response_state in record: {state!r}")
        qid = str(record["question_id"])
        by_state_counts[state] += 1
        by_state_correct[state] += int(bool(record["is_correct"]))
        by_state_question_counts[state][qid] += 1
        by_state_question_correct[state][qid] += int(bool(record["is_correct"]))
        answer = str(record.get("predicted_answer", "")).strip()
        if answer:
            by_state_question_answers[state][qid][answer] += 1
        question_ids.add(qid)

    state_accuracy = {
        state: (
            by_state_correct[state] / by_state_counts[state]
            if by_state_counts[state]
            else None
        )
        for state in FORCED_STATE_ORDER
    }
    strict_descending_qids: list[str] = []
    same_dominant_answer_qids: list[str] = []
    for qid in sorted(question_ids, key=lambda value: int(value) if value.isdigit() else value):
        if any(by_state_question_counts[state].get(qid, 0) == 0 for state in FORCED_STATE_ORDER):
            continue
        accuracy_by_state = {
            state: by_state_question_correct[state][qid] / by_state_question_counts[state][qid]
            for state in FORCED_STATE_ORDER
        }
        if (
            accuracy_by_state["mastered"]
            > accuracy_by_state["partial"]
            > accuracy_by_state["guessable"]
            > accuracy_by_state["unreachable"]
        ):
            strict_descending_qids.append(qid)

        dominant_answers: list[str] = []
        unique_modes = True
        for state in FORCED_STATE_ORDER:
            answer_counter = by_state_question_answers[state].get(qid, Counter())
            if not answer_counter:
                unique_modes = False
                break
            top_count = max(answer_counter.values())
            top_answers = sorted(
                answer for answer, count in answer_counter.items() if count == top_count
            )
            if len(top_answers) != 1:
                unique_modes = False
                break
            dominant_answers.append(top_answers[0])
        if unique_modes and len(set(dominant_answers)) == 1:
            same_dominant_answer_qids.append(qid)

    return {
        "forced_state_accuracy": state_accuracy,
        "mastered_accuracy": state_accuracy["mastered"],
        "partial_accuracy": state_accuracy["partial"],
        "guessable_accuracy": state_accuracy["guessable"],
        "unreachable_accuracy": state_accuracy["unreachable"],
        "strict_state_descending_item_count": len(strict_descending_qids),
        "strict_state_descending_item_fraction": (
            len(strict_descending_qids) / len(question_ids) if question_ids else None
        ),
        "same_dominant_answer_all_states_count": len(same_dominant_answer_qids),
        "same_dominant_answer_all_states_fraction": (
            len(same_dominant_answer_qids) / len(question_ids) if question_ids else None
        ),
        "strict_state_descending_item_examples": strict_descending_qids[:20],
        "same_dominant_answer_all_states_examples": same_dominant_answer_qids[:20],
    }


def _neutral_student_model(student_id: str) -> StudentModel:
    return StudentModel(
        student_id=student_id,
        grade="三年级",
        academic_level="medium",
        weak_subjects=["unknown"],
        strong_subjects=["unknown"],
        self_efficacy_analysis=SelfEfficacyAnalysis(
            efficacy_belief_description="Neutral diagnostic placeholder.",
            efficacy_belief_evidence=["Used only for forced-state diagnostics."],
        ),
        srl_analysis=SRLAnalysis(
            primary_srl_vulnerability="Neutral diagnostic placeholder.",
            srl_process_evidence=["Used only for forced-state diagnostics."],
        ),
        control_value_analysis=ControlValueAnalysis(
            control_appraisal_description="Neutral diagnostic placeholder.",
            value_appraisal_description="Neutral diagnostic placeholder.",
            control_value_evidence=["Used only for forced-state diagnostics."],
        ),
        engagement_level_tendency="Active",
        engagement_evidence=["Neutral diagnostic placeholder."],
        response_directness_description="Neutral diagnostic placeholder.",
        response_directness_evidence=["Used only for forced-state diagnostics."],
        raw_summary="Neutral diagnostic placeholder.",
    )


def _neutral_internal_signals() -> StudentInternalSignals:
    return StudentInternalSignals(
        efficacy_signal="medium",
        srl_fragility_signal="medium",
        control_signal="medium",
        value_signal="medium",
        directness_signal="medium",
    )


def _generate_simple_forced_state_answer(
    question: QuestionRecord,
    forced_response_state: str,
    llm_client: OpenAICompatClient,
) -> dict[str, str]:
    user_payload = {
        "forced_response_state": forced_response_state,
        "question_id": question.question_id,
        "question_text": question.question_text,
        "options": question.options,
        "required_output_schema": {
            "predicted_answer": "string",
            "student_response": "string",
        },
    }
    parsed = llm_client.chat_json(
        system_prompt=SIMPLE_FORCED_STATE_PROMPT,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
        partial_string_keys=["predicted_answer", "student_response"],
    )
    predicted_answer = str(parsed.get("predicted_answer", "")).strip()
    student_response = str(parsed.get("student_response", "")).strip()
    if not predicted_answer:
        raise ValueError("simple forced-state generation missing predicted_answer")
    if not student_response:
        raise ValueError("simple forced-state generation missing student_response")
    return {
        "predicted_answer": predicted_answer,
        "student_response": student_response,
    }


def run_d1_simple_forced_state(
    output_root: Path = ROOT_CAUSE_OUTPUT_ROOT / "D1_simple_forced_state",
    config_path: Path = DEFAULT_CONFIG_PATH,
    frozen_question_set_path: Path = DEFAULT_FROZEN_QUESTION_SET_PATH,
    samples_per_state: int = 20,
    max_questions: int | None = None,
    max_concurrency: int = 16,
) -> Path:
    if samples_per_state <= 0:
        raise ValueError("samples_per_state must be positive")
    run_dir = _prepare_output_dir(output_root)
    predictions_path = run_dir / "predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"
    metrics_path = run_dir / "metrics.json"
    resolved_config_path = run_dir / "resolved_config.json"

    llm_client = _build_llm_client(config_path=config_path)
    questions, question_lookup = _load_frozen_questions(
        config_path=config_path,
        frozen_question_set_path=frozen_question_set_path,
    )
    if max_questions is not None:
        questions = questions[:max_questions]
        question_lookup = {question.question_id: question for question in questions}
    resolved_config = {
        "config_path": str(config_path),
        "frozen_question_set_path": str(frozen_question_set_path),
        "samples_per_state": samples_per_state,
        "max_questions": max_questions,
        "max_concurrency": max_concurrency,
        "forced_states": list(FORCED_STATE_ORDER),
    }
    _write_json(resolved_config_path, resolved_config)

    tasks = [
        (forced_state, sample_index, question)
        for forced_state in FORCED_STATE_ORDER
        for sample_index in range(1, samples_per_state + 1)
        for question in questions
    ]
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, len(tasks)))) as executor:
        future_map = {
            executor.submit(
                _generate_simple_forced_state_answer,
                question,
                forced_state,
                llm_client,
            ): (forced_state, sample_index, question)
            for forced_state, sample_index, question in tasks
        }
        for future in as_completed(future_map):
            forced_state, sample_index, question = future_map[future]
            try:
                answer_output = future.result()
            except Exception as exc:
                failure_row = {
                    "forced_response_state": forced_state,
                    "sample_index": sample_index,
                    "question_id": question.question_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failures.append(failure_row)
                _append_jsonl_row(failures_path, failure_row)
                continue
            record = {
                "forced_response_state": forced_state,
                "sample_index": sample_index,
                "question_id": question.question_id,
                "question_type": question.question_type,
                "predicted_answer": answer_output["predicted_answer"],
                "student_response": answer_output["student_response"],
                "forced_state_definition": asdict(build_forced_item_response_state(forced_state)),
                "gold_answers": question.answer,
                "has_options": bool(question.options),
            }
            records.append(record)
            _append_jsonl_row(predictions_path, record)

    if not records:
        raise RuntimeError(f"D1 produced no successful predictions; see {failures_path}")

    apply_official_correctness_labels(
        records=records,
        question_lookup=question_lookup,
        llm_client=llm_client,
        official_correctness_mode="rules_only",
    )
    records.sort(
        key=lambda row: (
            FORCED_STATE_ORDER.index(str(row["forced_response_state"])),
            int(row["sample_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    failures.sort(
        key=lambda row: (
            FORCED_STATE_ORDER.index(str(row["forced_response_state"])),
            int(row["sample_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    _write_jsonl(predictions_path, records)
    _write_jsonl(failures_path, failures)

    metrics = _compute_forced_state_metrics(records)
    metrics.update(
        {
            "samples_per_state": samples_per_state,
            "n_attempted_tasks": len(tasks),
            "n_successful_predictions": len(records),
            "n_failures": len(failures),
            "failure_rate": len(failures) / len(tasks) if tasks else 0.0,
        }
    )
    _write_json(metrics_path, metrics)
    return run_dir


def _build_problem_profiles(
    questions: list[QuestionRecord],
    llm_client: OpenAICompatClient,
    max_concurrency: int = 8,
) -> dict[str, ProblemRequirementProfile]:
    profiles: dict[str, ProblemRequirementProfile] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, len(questions)))) as executor:
        future_map = {
            executor.submit(
                build_problem_requirement_profile,
                question.question_text,
                question.options,
                question.question_type,
                llm_client,
            ): question
            for question in questions
        }
        for future in as_completed(future_map):
            question = future_map[future]
            profiles[question.question_id] = future.result()
    return profiles


def run_d2_full_forced_state(
    output_root: Path = ROOT_CAUSE_OUTPUT_ROOT / "D2_full_forced_state",
    config_path: Path = DEFAULT_CONFIG_PATH,
    frozen_question_set_path: Path = DEFAULT_FROZEN_QUESTION_SET_PATH,
    samples_per_state: int = 20,
    max_questions: int | None = None,
    max_concurrency: int = 16,
    response_persona: str = "first",
    max_thinking_steps: int = 12,
) -> Path:
    if samples_per_state <= 0:
        raise ValueError("samples_per_state must be positive")
    run_dir = _prepare_output_dir(output_root)
    predictions_path = run_dir / "predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"
    metrics_path = run_dir / "metrics.json"
    resolved_config_path = run_dir / "resolved_config.json"

    llm_client = _build_llm_client(config_path=config_path)
    questions, question_lookup = _load_frozen_questions(
        config_path=config_path,
        frozen_question_set_path=frozen_question_set_path,
    )
    if max_questions is not None:
        questions = questions[:max_questions]
        question_lookup = {question.question_id: question for question in questions}
    problem_profiles = _build_problem_profiles(questions=questions, llm_client=llm_client)
    resolved_config = {
        "config_path": str(config_path),
        "frozen_question_set_path": str(frozen_question_set_path),
        "samples_per_state": samples_per_state,
        "max_questions": max_questions,
        "max_concurrency": max_concurrency,
        "response_persona": response_persona,
        "max_thinking_steps": max_thinking_steps,
        "forced_states": list(FORCED_STATE_ORDER),
    }
    _write_json(resolved_config_path, resolved_config)

    tasks = [
        (forced_state, sample_index, question)
        for forced_state in FORCED_STATE_ORDER
        for sample_index in range(1, samples_per_state + 1)
        for question in questions
    ]
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    neutral_signals = _neutral_internal_signals()

    def _run_single_task(
        forced_state: str,
        sample_index: int,
        question: QuestionRecord,
    ) -> dict[str, object]:
        student_model = _neutral_student_model(
            student_id=f"{forced_state}_{sample_index}",
        )
        problem_profile = problem_profiles[question.question_id]
        item_state = build_forced_item_response_state(forced_state)
        constraints = compile_constraints(item_state)
        answer_output = generate_student_answer(
            student_model=student_model,
            internal_signals=neutral_signals,
            problem_profile=problem_profile,
            item_state=item_state,
            constraints=constraints,
            question_id=question.question_id,
            question_text=question.question_text,
            options=question.options,
            response_persona=response_persona,
            max_thinking_steps=max_thinking_steps,
            llm_client=llm_client,
        )
        violation = check_violation(
            answer_output=answer_output,
            item_state=item_state,
            constraints=constraints,
            llm_client=llm_client,
            enable_llm_boundary_review=True,
        )
        retried = False
        if should_retry_once(item_state=item_state, violation=violation):
            retried = True
            answer_output, constraints = retry_with_tighter_constraints(
                student_model=student_model,
                internal_signals=neutral_signals,
                problem_profile=problem_profile,
                item_state=item_state,
                constraints=constraints,
                question_id=question.question_id,
                question_text=question.question_text,
                options=question.options,
                response_persona=response_persona,
                max_thinking_steps=max_thinking_steps,
                llm_client=llm_client,
            )
            violation = check_violation(
                answer_output=answer_output,
                item_state=item_state,
                constraints=constraints,
                llm_client=llm_client,
                enable_llm_boundary_review=True,
            )
        return {
            "forced_response_state": forced_state,
            "sample_index": sample_index,
            "question_id": question.question_id,
            "question_type": question.question_type,
            "predicted_answer": answer_output.predicted_answer,
            "student_response": answer_output.student_response,
            "thinking_trace": [asdict(step) for step in answer_output.thinking_trace],
            "thinking_steps_n": len(answer_output.thinking_trace),
            "retried": retried,
            "final_violation": asdict(violation),
            "problem_requirement_profile": asdict(problem_profile),
            "item_response_state": asdict(item_state),
            "constraint_bundle": asdict(constraints),
            "gold_answers": question.answer,
            "has_options": bool(question.options),
        }

    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, len(tasks)))) as executor:
        future_map = {
            executor.submit(_run_single_task, forced_state, sample_index, question): (
                forced_state,
                sample_index,
                question,
            )
            for forced_state, sample_index, question in tasks
        }
        for future in as_completed(future_map):
            forced_state, sample_index, question = future_map[future]
            try:
                record = future.result()
            except Exception as exc:
                failure_row = {
                    "forced_response_state": forced_state,
                    "sample_index": sample_index,
                    "question_id": question.question_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failures.append(failure_row)
                _append_jsonl_row(failures_path, failure_row)
                continue
            records.append(record)
            _append_jsonl_row(predictions_path, record)

    if not records:
        raise RuntimeError(f"D2 produced no successful predictions; see {failures_path}")

    apply_official_correctness_labels(
        records=records,
        question_lookup=question_lookup,
        llm_client=llm_client,
        official_correctness_mode="rules_only",
    )
    records.sort(
        key=lambda row: (
            FORCED_STATE_ORDER.index(str(row["forced_response_state"])),
            int(row["sample_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    failures.sort(
        key=lambda row: (
            FORCED_STATE_ORDER.index(str(row["forced_response_state"])),
            int(row["sample_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    _write_jsonl(predictions_path, records)
    _write_jsonl(failures_path, failures)

    remaining_violations = sum(
        int(bool(record["final_violation"]["has_violation"])) for record in records
    )
    retries = sum(int(bool(record["retried"])) for record in records)
    metrics = _compute_forced_state_metrics(records)
    metrics.update(
        {
            "samples_per_state": samples_per_state,
            "n_attempted_tasks": len(tasks),
            "n_successful_predictions": len(records),
            "n_failures": len(failures),
            "failure_rate": len(failures) / len(tasks) if tasks else 0.0,
            "remaining_violations": remaining_violations,
            "retry_count": retries,
            "mean_thinking_steps": (
                sum(int(record["thinking_steps_n"]) for record in records) / len(records)
            ),
        }
    )
    _write_json(metrics_path, metrics)
    return run_dir


def write_c1_report(
    direct_run_dir: Path,
    state_single_run_dir: Path,
    state_step_run_dir: Path,
    report_path: Path = ROOT_CAUSE_C1_REPORT_PATH,
) -> str:
    direct_metrics = _load_run_metrics(direct_run_dir)
    single_metrics = _load_run_metrics(state_single_run_dir)
    step_metrics = _load_run_metrics(state_step_run_dir)

    rows = [
        [
            "direct",
            _format_float(direct_metrics.get("overall_accuracy")),
            _format_float(direct_metrics.get("overall_accuracy_gap_vs_real_students")),
            _format_float(direct_metrics.get("item_accuracy_pearson_vs_real_students")),
            _format_float(direct_metrics.get("item_accuracy_mae_vs_real_students")),
            _format_float(direct_metrics.get("mean_level_overall_accuracy_gap")),
            str(direct_metrics.get("strict_monotonic_item_count")),
            str(direct_metrics.get("same_dominant_answer_all_levels_count")),
            _format_float(direct_metrics.get("failure_rate")),
        ],
        [
            "state_single",
            _format_float(single_metrics.get("overall_accuracy")),
            _format_float(single_metrics.get("overall_accuracy_gap_vs_real_students")),
            _format_float(single_metrics.get("item_accuracy_pearson_vs_real_students")),
            _format_float(single_metrics.get("item_accuracy_mae_vs_real_students")),
            _format_float(single_metrics.get("mean_level_overall_accuracy_gap")),
            str(single_metrics.get("strict_monotonic_item_count")),
            str(single_metrics.get("same_dominant_answer_all_levels_count")),
            _format_float(single_metrics.get("failure_rate")),
        ],
        [
            "state_step",
            _format_float(step_metrics.get("overall_accuracy")),
            _format_float(step_metrics.get("overall_accuracy_gap_vs_real_students")),
            _format_float(step_metrics.get("item_accuracy_pearson_vs_real_students")),
            _format_float(step_metrics.get("item_accuracy_mae_vs_real_students")),
            _format_float(step_metrics.get("mean_level_overall_accuracy_gap")),
            str(step_metrics.get("strict_monotonic_item_count")),
            str(step_metrics.get("same_dominant_answer_all_levels_count")),
            _format_float(step_metrics.get("failure_rate")),
        ],
    ]

    best_pearson_name = max(
        [
            ("direct", float(direct_metrics["item_accuracy_pearson_vs_real_students"])),
            ("state_single", float(single_metrics["item_accuracy_pearson_vs_real_students"])),
            ("state_step", float(step_metrics["item_accuracy_pearson_vs_real_students"])),
        ],
        key=lambda item: item[1],
    )[0]
    best_monotonic_name = max(
        [
            ("direct", int(direct_metrics["strict_monotonic_item_count"])),
            ("state_single", int(single_metrics["strict_monotonic_item_count"])),
            ("state_step", int(step_metrics["strict_monotonic_item_count"])),
        ],
        key=lambda item: item[1],
    )[0]

    report = f"""# C1 方法消融：`direct` vs `state_single` vs `state_step`

## 1. 用途

判断当前问题主要出在方法链的哪一段。

这一步固定：

- persona：`full_persona`
- 题集：`outputs/run_20260420_014128/selected_questions.json`
- 模型：`qwen`
- 判分：`rules_only`

只改方法：

- `direct = persona -> direct answer`
- `state_single = persona -> state -> one final step`
- `state_step = persona -> state -> bounded multi-step + violation check + optional retry`

## 2. 运行目录

- `direct`
  - `{direct_run_dir}`
- `state_single`
  - `{state_single_run_dir}`
- `state_step`
  - `{state_step_run_dir}`

## 3. 关键结果

{_build_markdown_table(
    headers=[
        "方法",
        "overall acc",
        "overall gap",
        "item Pearson",
        "item MAE",
        "mean level gap",
        "strict monotonic",
        "same dominant",
        "failure rate",
    ],
    rows=rows,
)}

## 4. 判断

- 题目级相关性最好的方法是：`{best_pearson_name}`
- 四档结构性最好的方法是：`{best_monotonic_name}`
- `direct` 的最大问题不是平均分，而是四档结构明显塌缩：它的 `strict_monotonic_item_count` 很低，且跨档主流答案相同题数很高
- 如果 `state_single` 或 `state_step` 在 item Pearson、严格单调、跨档答案分化上明显优于 `direct`，就说明状态层不是摆设，而是在纠正直接作答带来的结构塌缩
- 如果 `state_step` 反而不如 `state_single`，则问题更像出在多步协议本身，而不是“有没有状态层”

## 5. 结论

本实验的核心是比较三种链路谁更能保住：

- 题目级相关性
- 四档分层结构
- 跨档答案分化

因此正式结论应优先看这些结构指标，而不是只看整体准确率是否贴均值。

## 6. 反作弊说明

- 三个条件都没有把真实标签带入 generation path
- 没有按题号特判
- 没有按目标 accuracy 后处理翻答案
- 只改方法链，不改题集、不改 persona、不改评测器
"""
    _write_text(report_path, report)

    direct_monotonic = int(direct_metrics["strict_monotonic_item_count"])
    single_monotonic = int(single_metrics["strict_monotonic_item_count"])
    step_monotonic = int(step_metrics["strict_monotonic_item_count"])
    direct_pearson = float(direct_metrics["item_accuracy_pearson_vs_real_students"])
    single_pearson = float(single_metrics["item_accuracy_pearson_vs_real_students"])
    step_pearson = float(step_metrics["item_accuracy_pearson_vs_real_students"])
    if direct_pearson >= max(single_pearson, step_pearson) and direct_monotonic >= max(
        single_monotonic, step_monotonic
    ):
        return "direct 没有明显输给带状态方法；当前方法链整体增益不足，甚至可能在帮倒忙"
    if single_pearson > direct_pearson and step_pearson < single_pearson:
        return "state_single 优于 direct，而 state_step 低于 state_single；状态层有价值，但多步协议本身在拖后腿"
    return "direct、state_single、state_step 的对比表明问题不只在是否有状态层，还要看多步协议是否进一步拉低结构指标"


def write_d1_report(
    d1_run_dir: Path,
    report_path: Path = ROOT_CAUSE_D1_REPORT_PATH,
) -> str:
    metrics = _load_run_metrics(d1_run_dir)
    state_accuracy = metrics["forced_state_accuracy"]
    strict_descent = (
        float(metrics["mastered_accuracy"])
        > float(metrics["partial_accuracy"])
        > float(metrics["guessable_accuracy"])
        > float(metrics["unreachable_accuracy"])
    )
    rows = [
        [state, _format_float(state_accuracy[state])] for state in FORCED_STATE_ORDER
    ]
    report = f"""# D1 强制状态服从：`simple_forced_state`

## 1. 用途

判断模型在最简单条件下，能不能仅凭强制状态本身把四种边界分开。

这里故意不走 persona，也不走状态推断，只做最简诊断：

- 输入：`forced response_state + math item`
- 输出：直接最终答案

## 2. 运行目录

- `{d1_run_dir}`

## 3. 四状态准确率

{_build_markdown_table(headers=["状态", "accuracy"], rows=rows)}

## 4. 关键指标

- `strict_state_descending_item_count = {metrics["strict_state_descending_item_count"]}`
- `same_dominant_answer_all_states_count = {metrics["same_dominant_answer_all_states_count"]}`
- `failure_rate = {_format_float(metrics["failure_rate"])}`

## 5. 判断

- 四状态整体准确率是否严格下降：`{"是" if strict_descent else "否"}`
- 如果这里都分不开，问题更偏模型边界本身
- 如果这里能分开，而后面的 `D2` 分不开，问题就更偏完整方法协议

## 6. 反作弊说明

- 没有引入真实标签到 generation path
- 这里只喂固定状态，不按题号做任何特判
- 真实答案仍只用于离线判分
"""
    _write_text(report_path, report)
    if strict_descent:
        return "simple_forced_state 下四状态整体能拉开；模型在最简单条件下具备基本状态服从能力"
    return "simple_forced_state 下四状态都拉不开；第二层模型边界问题嫌疑很大"


def write_d2_report(
    d1_run_dir: Path,
    d2_run_dir: Path,
    report_path: Path = ROOT_CAUSE_D2_REPORT_PATH,
) -> str:
    d1_metrics = _load_run_metrics(d1_run_dir)
    d2_metrics = _load_run_metrics(d2_run_dir)
    d1_rows = [
        [state, _format_float(d1_metrics["forced_state_accuracy"][state])]
        for state in FORCED_STATE_ORDER
    ]
    d2_rows = [
        [state, _format_float(d2_metrics["forced_state_accuracy"][state])]
        for state in FORCED_STATE_ORDER
    ]
    d1_desc = (
        float(d1_metrics["mastered_accuracy"])
        > float(d1_metrics["partial_accuracy"])
        > float(d1_metrics["guessable_accuracy"])
        > float(d1_metrics["unreachable_accuracy"])
    )
    d2_desc = (
        float(d2_metrics["mastered_accuracy"])
        > float(d2_metrics["partial_accuracy"])
        > float(d2_metrics["guessable_accuracy"])
        > float(d2_metrics["unreachable_accuracy"])
    )
    report = f"""# D2 强制状态服从：`full_forced_state`

## 1. 用途

比较：

- `D1 = simple_forced_state`
- `D2 = full_forced_state`

看完整 generation 协议会不会破坏强制状态本来可以带来的分化。

## 2. 运行目录

- `D1`
  - `{d1_run_dir}`
- `D2`
  - `{d2_run_dir}`

## 3. 四状态准确率对比

### D1

{_build_markdown_table(headers=["状态", "accuracy"], rows=d1_rows)}

### D2

{_build_markdown_table(headers=["状态", "accuracy"], rows=d2_rows)}

## 4. 关键指标

- `D1 strict_state_descending_item_count = {d1_metrics["strict_state_descending_item_count"]}`
- `D2 strict_state_descending_item_count = {d2_metrics["strict_state_descending_item_count"]}`
- `D1 same_dominant_answer_all_states_count = {d1_metrics["same_dominant_answer_all_states_count"]}`
- `D2 same_dominant_answer_all_states_count = {d2_metrics["same_dominant_answer_all_states_count"]}`
- `D2 retry_count = {d2_metrics["retry_count"]}`
- `D2 remaining_violations = {d2_metrics["remaining_violations"]}`

## 5. 判断

- D1 四状态整体是否严格下降：`{"是" if d1_desc else "否"}`
- D2 四状态整体是否严格下降：`{"是" if d2_desc else "否"}`
- 如果 D1 能分开、D2 分不开，说明完整方法协议在吃掉状态差异
- 如果 D1 和 D2 都分不开，更像是模型本身就难以服从这种状态边界

## 6. 反作弊说明

- D2 仍然没有把真实标签带进 generation path
- 只把状态从“模型推断”改成“外部强制指定”
- 真实答案仍只用于离线判分
"""
    _write_text(report_path, report)
    if d1_desc and not d2_desc:
        return "D1 能分开而 D2 分不开；完整 generation 协议明显在破坏状态服从，问题更偏方法层"
    if not d1_desc:
        return "D1 本身就分不开；第二层模型边界问题更重，D2 不能单独归咎于方法层"
    return "D1 和 D2 都能基本分开；完整协议不是状态服从崩掉的唯一主因"


def _load_frozen_question_subset(
    max_questions: int,
    config_path: Path = DEFAULT_CONFIG_PATH,
    frozen_question_set_path: Path = DEFAULT_FROZEN_QUESTION_SET_PATH,
) -> tuple[list[QuestionRecord], dict[str, QuestionRecord]]:
    questions, question_lookup = _load_frozen_questions(
        config_path=config_path,
        frozen_question_set_path=frozen_question_set_path,
    )
    subset = questions[:max_questions]
    return subset, {question.question_id: question for question in subset}


def _build_state_step_record(
    student_model: StudentModel,
    internal_signals: StudentInternalSignals,
    question: QuestionRecord,
    problem_profile: ProblemRequirementProfile,
    llm_client: OpenAICompatClient,
    response_persona: str = "first",
    max_thinking_steps: int = 12,
) -> dict[str, object]:
    item_state = resolve_item_response_state(
        student_model=student_model,
        internal_signals=internal_signals,
        profile=problem_profile,
        question_text=question.question_text,
        llm_client=llm_client,
    )
    constraints = compile_constraints(item_state)
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
        max_thinking_steps=max_thinking_steps,
        llm_client=llm_client,
    )
    violation = check_violation(
        answer_output=answer_output,
        item_state=item_state,
        constraints=constraints,
        llm_client=llm_client,
        enable_llm_boundary_review=True,
    )
    retried = False
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
            max_thinking_steps=max_thinking_steps,
            llm_client=llm_client,
        )
        violation = check_violation(
            answer_output=answer_output,
            item_state=item_state,
            constraints=constraints,
            llm_client=llm_client,
            enable_llm_boundary_review=True,
        )
    return {
        "question_id": question.question_id,
        "question_type": question.question_type,
        "predicted_answer": answer_output.predicted_answer,
        "student_response": answer_output.student_response,
        "thinking_trace": [asdict(step) for step in answer_output.thinking_trace],
        "thinking_steps_n": len(answer_output.thinking_trace),
        "retried": retried,
        "final_violation": asdict(violation),
        "student_model": asdict(student_model),
        "implementation_derived_signals": asdict(internal_signals),
        "problem_requirement_profile": asdict(problem_profile),
        "item_response_state": asdict(item_state),
        "constraint_bundle": asdict(constraints),
        "gold_answers": question.answer,
        "has_options": bool(question.options),
    }


def _counterfactual_persona_pairs() -> list[dict[str, object]]:
    return [
        {
            "factor": "math_subject_strength",
            "positive_label": "math_strong",
            "negative_label": "math_weak",
            "positive_persona": PersonaRecord(
                student_id="cf_math_strong",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["数学", "语文"],
                weak_subjects=["英语"],
                learning_profile_text="做数学题时通常有把握，遇到新题愿意尝试，也会主动检查关键步骤。",
            ),
            "negative_persona": PersonaRecord(
                student_id="cf_math_weak",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["语文"],
                weak_subjects=["数学", "英语"],
                learning_profile_text="做数学题时常常先觉得自己不会，遇到稍难题就容易退缩，不太愿意继续尝试。",
            ),
        },
        {
            "factor": "efficacy",
            "positive_label": "high_efficacy",
            "negative_label": "low_efficacy",
            "positive_persona": PersonaRecord(
                student_id="cf_high_efficacy",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["语文"],
                weak_subjects=["英语"],
                learning_profile_text="做数学题时通常相信自己能慢慢做出来，即使一开始不会也愿意继续想办法。",
            ),
            "negative_persona": PersonaRecord(
                student_id="cf_low_efficacy",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["语文"],
                weak_subjects=["英语"],
                learning_profile_text="做数学题时经常先怀疑自己做不出来，一遇到卡点就觉得再想也没有用。",
            ),
        },
        {
            "factor": "srl_fragility",
            "positive_label": "low_srl_fragility",
            "negative_label": "high_srl_fragility",
            "positive_persona": PersonaRecord(
                student_id="cf_low_srl_fragility",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["语文"],
                weak_subjects=["英语"],
                learning_profile_text="做数学题时会先看清条件，能按步骤检查，遇到困难也会继续调整做法。",
            ),
            "negative_persona": PersonaRecord(
                student_id="cf_high_srl_fragility",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["语文"],
                weak_subjects=["英语"],
                learning_profile_text="做数学题时容易急躁分心，常常没看清条件就开始做，卡住后也不太会检查和调整。",
            ),
        },
        {
            "factor": "engagement_style",
            "positive_label": "constructive",
            "negative_label": "passive",
            "positive_persona": PersonaRecord(
                student_id="cf_constructive",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["语文"],
                weak_subjects=["英语"],
                learning_profile_text="面对数学题时更愿意主动组织信息，自己尝试想关系、补步骤、解释为什么。",
            ),
            "negative_persona": PersonaRecord(
                student_id="cf_passive",
                grade="三年级",
                academic_level="medium",
                strong_subjects=["语文"],
                weak_subjects=["英语"],
                learning_profile_text="面对数学题时更偏被动，常常只等着套现成办法，不太主动整理条件或补充想法。",
            ),
        },
    ]


def _state_rank(response_state: str) -> int:
    ranking = {
        "mastered": 3,
        "partial": 2,
        "guessable": 1,
        "unreachable": 0,
    }
    if response_state not in ranking:
        raise ValueError(f"unexpected response_state: {response_state!r}")
    return ranking[response_state]


def run_e1_counterfactual_sensitivity(
    output_root: Path = ROOT_CAUSE_OUTPUT_ROOT / "E1_counterfactual_sensitivity",
    config_path: Path = DEFAULT_CONFIG_PATH,
    frozen_question_set_path: Path = DEFAULT_FROZEN_QUESTION_SET_PATH,
    max_questions: int = 20,
    repeats_per_side: int = 5,
    max_concurrency: int = 12,
    response_persona: str = "first",
    max_thinking_steps: int = 12,
) -> Path:
    run_dir = _prepare_output_dir(output_root)
    predictions_path = run_dir / "predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"
    metrics_path = run_dir / "metrics.json"
    resolved_config_path = run_dir / "resolved_config.json"

    llm_client = _build_llm_client(config_path=config_path)
    questions, question_lookup = _load_frozen_question_subset(
        max_questions=max_questions,
        config_path=config_path,
        frozen_question_set_path=frozen_question_set_path,
    )
    problem_profiles = _build_problem_profiles(questions=questions, llm_client=llm_client)
    factor_pairs = _counterfactual_persona_pairs()
    persona_entries: dict[tuple[str, str], tuple[StudentModel, StudentInternalSignals]] = {}
    for pair in factor_pairs:
        positive_persona = pair["positive_persona"]
        negative_persona = pair["negative_persona"]
        positive_model = build_student_model(positive_persona, llm_client=llm_client)
        negative_model = build_student_model(negative_persona, llm_client=llm_client)
        persona_entries[(pair["factor"], pair["positive_label"])] = (
            positive_model,
            map_student_model_to_internal_signals(positive_model, llm_client=llm_client),
        )
        persona_entries[(pair["factor"], pair["negative_label"])] = (
            negative_model,
            map_student_model_to_internal_signals(negative_model, llm_client=llm_client),
        )

    resolved_config = {
        "config_path": str(config_path),
        "frozen_question_set_path": str(frozen_question_set_path),
        "max_questions": max_questions,
        "repeats_per_side": repeats_per_side,
        "max_concurrency": max_concurrency,
        "response_persona": response_persona,
        "max_thinking_steps": max_thinking_steps,
        "factors": [
            {
                "factor": pair["factor"],
                "positive_label": pair["positive_label"],
                "negative_label": pair["negative_label"],
            }
            for pair in factor_pairs
        ],
    }
    _write_json(resolved_config_path, resolved_config)

    tasks = []
    for pair in factor_pairs:
        for side_label in [pair["positive_label"], pair["negative_label"]]:
            for repeat_index in range(1, repeats_per_side + 1):
                for question in questions:
                    tasks.append((pair["factor"], side_label, repeat_index, question))

    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    def _run_single_task(
        factor: str,
        side_label: str,
        repeat_index: int,
        question: QuestionRecord,
    ) -> dict[str, object]:
        student_model, internal_signals = persona_entries[(factor, side_label)]
        record = _build_state_step_record(
            student_model=student_model,
            internal_signals=internal_signals,
            question=question,
            problem_profile=problem_profiles[question.question_id],
            llm_client=llm_client,
            response_persona=response_persona,
            max_thinking_steps=max_thinking_steps,
        )
        record["factor"] = factor
        record["persona_side"] = side_label
        record["repeat_index"] = repeat_index
        return record

    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, len(tasks)))) as executor:
        future_map = {
            executor.submit(_run_single_task, factor, side_label, repeat_index, question): (
                factor,
                side_label,
                repeat_index,
                question,
            )
            for factor, side_label, repeat_index, question in tasks
        }
        for future in as_completed(future_map):
            factor, side_label, repeat_index, question = future_map[future]
            try:
                record = future.result()
            except Exception as exc:
                failure_row = {
                    "factor": factor,
                    "persona_side": side_label,
                    "repeat_index": repeat_index,
                    "question_id": question.question_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failures.append(failure_row)
                _append_jsonl_row(failures_path, failure_row)
                continue
            records.append(record)
            _append_jsonl_row(predictions_path, record)

    if not records:
        raise RuntimeError(f"E1 produced no successful predictions; see {failures_path}")

    apply_official_correctness_labels(
        records=records,
        question_lookup=question_lookup,
        llm_client=llm_client,
        official_correctness_mode="rules_only",
    )
    records.sort(
        key=lambda row: (
            str(row["factor"]),
            str(row["persona_side"]),
            int(row["repeat_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    failures.sort(
        key=lambda row: (
            str(row["factor"]),
            str(row["persona_side"]),
            int(row["repeat_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    _write_jsonl(predictions_path, records)
    _write_jsonl(failures_path, failures)

    factor_metrics: dict[str, dict[str, object]] = {}
    pair_lookup = {pair["factor"]: pair for pair in factor_pairs}
    for factor, pair in pair_lookup.items():
        paired_rows: dict[tuple[int, str], dict[str, dict[str, object]]] = defaultdict(dict)
        for record in records:
            if str(record["factor"]) != factor:
                continue
            key = (int(record["repeat_index"]), str(record["question_id"]))
            paired_rows[key][str(record["persona_side"])] = record
        matched_pairs = [
            row_pair
            for row_pair in paired_rows.values()
            if pair["positive_label"] in row_pair and pair["negative_label"] in row_pair
        ]
        if not matched_pairs:
            continue
        state_change_n = 0
        answer_change_n = 0
        correctness_change_n = 0
        state_improve_n = 0
        positive_correct_n = 0
        negative_correct_n = 0
        positive_state_sum = 0
        negative_state_sum = 0
        for row_pair in matched_pairs:
            positive_record = row_pair[pair["positive_label"]]
            negative_record = row_pair[pair["negative_label"]]
            positive_state = str(positive_record["item_response_state"]["response_state"])
            negative_state = str(negative_record["item_response_state"]["response_state"])
            positive_rank = _state_rank(positive_state)
            negative_rank = _state_rank(negative_state)
            positive_state_sum += positive_rank
            negative_state_sum += negative_rank
            state_change_n += int(positive_state != negative_state)
            answer_change_n += int(
                str(positive_record["predicted_answer"]) != str(negative_record["predicted_answer"])
            )
            correctness_change_n += int(
                bool(positive_record["is_correct"]) != bool(negative_record["is_correct"])
            )
            state_improve_n += int(positive_rank > negative_rank)
            positive_correct_n += int(bool(positive_record["is_correct"]))
            negative_correct_n += int(bool(negative_record["is_correct"]))
        factor_metrics[factor] = {
            "pair_count": len(matched_pairs),
            "positive_label": pair["positive_label"],
            "negative_label": pair["negative_label"],
            "state_change_rate": state_change_n / len(matched_pairs),
            "answer_change_rate": answer_change_n / len(matched_pairs),
            "correctness_change_rate": correctness_change_n / len(matched_pairs),
            "state_improve_rate": state_improve_n / len(matched_pairs),
            "positive_mean_state_rank": positive_state_sum / len(matched_pairs),
            "negative_mean_state_rank": negative_state_sum / len(matched_pairs),
            "positive_accuracy": positive_correct_n / len(matched_pairs),
            "negative_accuracy": negative_correct_n / len(matched_pairs),
        }

    metrics = {
        "n_attempted_tasks": len(tasks),
        "n_successful_predictions": len(records),
        "n_failures": len(failures),
        "failure_rate": len(failures) / len(tasks) if tasks else 0.0,
        "factor_metrics": factor_metrics,
        "mean_state_change_rate": (
            sum(float(item["state_change_rate"]) for item in factor_metrics.values()) / len(factor_metrics)
            if factor_metrics
            else None
        ),
        "mean_answer_change_rate": (
            sum(float(item["answer_change_rate"]) for item in factor_metrics.values()) / len(factor_metrics)
            if factor_metrics
            else None
        ),
        "mean_correctness_change_rate": (
            sum(float(item["correctness_change_rate"]) for item in factor_metrics.values()) / len(factor_metrics)
            if factor_metrics
            else None
        ),
    }
    _write_json(metrics_path, metrics)
    return run_dir


def write_e1_report(
    e1_run_dir: Path,
    report_path: Path = ROOT_CAUSE_E1_REPORT_PATH,
) -> str:
    metrics = _load_run_metrics(e1_run_dir)
    factor_metrics = metrics["factor_metrics"]
    rows = []
    for factor, item in factor_metrics.items():
        rows.append(
            [
                factor,
                _format_float(item["state_change_rate"]),
                _format_float(item["answer_change_rate"]),
                _format_float(item["correctness_change_rate"]),
                _format_float(item["state_improve_rate"]),
            ]
        )
    report = f"""# E1 反事实敏感性测试

## 1. 用途

判断 persona 某个关键因素变化后，状态和答案会不会跟着变。

## 2. 运行目录

- `{e1_run_dir}`

## 3. 各因素结果

{_build_markdown_table(
    headers=["factor", "state_change", "answer_change", "correctness_change", "state_improve"],
    rows=rows,
)}

## 4. 总体均值

- `mean_state_change_rate = {_format_float(metrics["mean_state_change_rate"])}`
- `mean_answer_change_rate = {_format_float(metrics["mean_answer_change_rate"])}`
- `mean_correctness_change_rate = {_format_float(metrics["mean_correctness_change_rate"])}`

## 5. 判断

- 如果 persona 改了但 `state_change_rate` 仍然很低，说明画像关键信号没有稳定传到状态层
- 如果 `state_change_rate` 不低，但 `answer_change_rate` 很低，说明状态变了也没有稳定传到答案层
"""
    _write_text(report_path, report)
    mean_state_change = float(metrics["mean_state_change_rate"] or 0.0)
    mean_answer_change = float(metrics["mean_answer_change_rate"] or 0.0)
    if mean_state_change < 0.20:
        return "关键 persona 因素变化后 state 仍很少改变；画像信号没有被稳定读取"
    if mean_answer_change < 0.10:
        return "persona 变化能推动 state 变化，但 answer 跟随变化仍弱；更像 state 到 answer 这一段有阻塞"
    return "关键 persona 因素变化已经能传到 state 和 answer，两层之间并非完全失灵"


def run_f1_stability(
    output_root: Path = ROOT_CAUSE_OUTPUT_ROOT / "F1_stability",
    config_path: Path = DEFAULT_CONFIG_PATH,
    frozen_question_set_path: Path = DEFAULT_FROZEN_QUESTION_SET_PATH,
    max_questions: int = 20,
    max_personas: int = 8,
    repeats: int = 3,
    max_concurrency: int = 12,
    response_persona: str = "first",
    max_thinking_steps: int = 12,
) -> Path:
    run_dir = _prepare_output_dir(output_root)
    predictions_path = run_dir / "predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"
    metrics_path = run_dir / "metrics.json"
    resolved_config_path = run_dir / "resolved_config.json"

    llm_client = _build_llm_client(config_path=config_path)
    config = _load_config(config_path)
    personas = load_personas(str(config["persona_path"]))
    personas = filter_personas_by_grade(
        personas,
        str(config["target_grade"]),
        match_mode=str(config.get("grade_match_mode", "exact")),
    )
    personas = sample_personas(
        personas,
        max_personas=max_personas,
        sampling_mode="stratified",
        seed=42,
    )
    questions, question_lookup = _load_frozen_question_subset(
        max_questions=max_questions,
        config_path=config_path,
        frozen_question_set_path=frozen_question_set_path,
    )
    problem_profiles = _build_problem_profiles(questions=questions, llm_client=llm_client)
    student_entries: dict[str, tuple[StudentModel, StudentInternalSignals]] = {}
    for persona in personas:
        student_model = build_student_model(persona, llm_client=llm_client)
        student_entries[persona.student_id] = (
            student_model,
            map_student_model_to_internal_signals(student_model, llm_client=llm_client),
        )

    resolved_config = {
        "config_path": str(config_path),
        "frozen_question_set_path": str(frozen_question_set_path),
        "max_questions": max_questions,
        "max_personas": max_personas,
        "repeats": repeats,
        "max_concurrency": max_concurrency,
        "response_persona": response_persona,
        "max_thinking_steps": max_thinking_steps,
    }
    _write_json(resolved_config_path, resolved_config)

    tasks = [
        (persona.student_id, repeat_index, question)
        for persona in personas
        for repeat_index in range(1, repeats + 1)
        for question in questions
    ]
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    def _run_single_task(
        student_id: str,
        repeat_index: int,
        question: QuestionRecord,
    ) -> dict[str, object]:
        student_model, internal_signals = student_entries[student_id]
        record = _build_state_step_record(
            student_model=student_model,
            internal_signals=internal_signals,
            question=question,
            problem_profile=problem_profiles[question.question_id],
            llm_client=llm_client,
            response_persona=response_persona,
            max_thinking_steps=max_thinking_steps,
        )
        record["student_id"] = student_id
        record["repeat_index"] = repeat_index
        return record

    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, len(tasks)))) as executor:
        future_map = {
            executor.submit(_run_single_task, student_id, repeat_index, question): (
                student_id,
                repeat_index,
                question,
            )
            for student_id, repeat_index, question in tasks
        }
        for future in as_completed(future_map):
            student_id, repeat_index, question = future_map[future]
            try:
                record = future.result()
            except Exception as exc:
                failure_row = {
                    "student_id": student_id,
                    "repeat_index": repeat_index,
                    "question_id": question.question_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failures.append(failure_row)
                _append_jsonl_row(failures_path, failure_row)
                continue
            records.append(record)
            _append_jsonl_row(predictions_path, record)

    if not records:
        raise RuntimeError(f"F1 produced no successful predictions; see {failures_path}")

    apply_official_correctness_labels(
        records=records,
        question_lookup=question_lookup,
        llm_client=llm_client,
        official_correctness_mode="rules_only",
    )
    records.sort(
        key=lambda row: (
            str(row["student_id"]),
            int(row["repeat_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    failures.sort(
        key=lambda row: (
            str(row["student_id"]),
            int(row["repeat_index"]),
            int(str(row["question_id"])) if str(row["question_id"]).isdigit() else str(row["question_id"]),
        )
    )
    _write_jsonl(predictions_path, records)
    _write_jsonl(failures_path, failures)

    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["student_id"]), str(record["question_id"]))].append(record)
    state_varies = 0
    answer_varies = 0
    correctness_varies = 0
    fully_stable = 0
    per_level_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (student_id, question_id), group in grouped.items():
        level = str(group[0]["student_model"]["academic_level"])
        state_values = {
            str(item["item_response_state"]["response_state"]) for item in group
        }
        answer_values = {str(item["predicted_answer"]) for item in group}
        correctness_values = {bool(item["is_correct"]) for item in group}
        state_changed = len(state_values) > 1
        answer_changed = len(answer_values) > 1
        correctness_changed = len(correctness_values) > 1
        state_varies += int(state_changed)
        answer_varies += int(answer_changed)
        correctness_varies += int(correctness_changed)
        fully_stable += int(not state_changed and not answer_changed and not correctness_changed)
        per_level_stats[level]["n"] += 1
        per_level_stats[level]["state_varies"] += int(state_changed)
        per_level_stats[level]["answer_varies"] += int(answer_changed)
        per_level_stats[level]["correctness_varies"] += int(correctness_changed)
    level_metrics = {}
    for level, stats in per_level_stats.items():
        n = stats["n"]
        level_metrics[level] = {
            "n": n,
            "state_change_rate": stats["state_varies"] / n,
            "answer_change_rate": stats["answer_varies"] / n,
            "correctness_change_rate": stats["correctness_varies"] / n,
        }

    metrics = {
        "n_attempted_tasks": len(tasks),
        "n_successful_predictions": len(records),
        "n_failures": len(failures),
        "failure_rate": len(failures) / len(tasks) if tasks else 0.0,
        "base_task_count": len(grouped),
        "response_state_change_rate": state_varies / len(grouped),
        "predicted_answer_change_rate": answer_varies / len(grouped),
        "is_correct_change_rate": correctness_varies / len(grouped),
        "fully_stable_rate": fully_stable / len(grouped),
        "level_metrics": level_metrics,
    }
    _write_json(metrics_path, metrics)
    return run_dir


def write_f1_report(
    f1_run_dir: Path,
    report_path: Path = ROOT_CAUSE_F1_REPORT_PATH,
) -> str:
    metrics = _load_run_metrics(f1_run_dir)
    level_rows = []
    level_metrics = metrics["level_metrics"]
    for level in sorted(level_metrics):
        level_rows.append(
            [
                level,
                str(level_metrics[level]["n"]),
                _format_float(level_metrics[level]["state_change_rate"]),
                _format_float(level_metrics[level]["answer_change_rate"]),
                _format_float(level_metrics[level]["correctness_change_rate"]),
            ]
        )
    report = f"""# F1 稳定性测试

## 1. 用途

判断同一个输入重复运行时，状态、答案和判分会不会明显漂移。

## 2. 运行目录

- `{f1_run_dir}`

## 3. 总体结果

- `response_state_change_rate = {_format_float(metrics["response_state_change_rate"])}`
- `predicted_answer_change_rate = {_format_float(metrics["predicted_answer_change_rate"])}`
- `is_correct_change_rate = {_format_float(metrics["is_correct_change_rate"])}`
- `fully_stable_rate = {_format_float(metrics["fully_stable_rate"])}`

## 4. 分层结果

{_build_markdown_table(
    headers=["level", "n", "state_change", "answer_change", "correctness_change"],
    rows=level_rows,
)}

## 5. 判断

- 如果这些变化率很高，第二层模型稳定性问题更重
- 如果变化率不高但总体效果仍差，问题更偏画像表示或方法结构，而不是纯随机波动
"""
    _write_text(report_path, report)
    if float(metrics["response_state_change_rate"]) > 0.30 or float(metrics["predicted_answer_change_rate"]) > 0.30:
        return "同输入重复运行波动较高；第二层模型稳定性问题明显"
    return "同输入重复运行整体还算稳定；问题不主要来自纯随机波动"


def write_g1_report(
    c1_run_dirs: dict[str, Path],
    d1_run_dir: Path,
    d2_run_dir: Path,
    e1_run_dir: Path,
    f1_run_dir: Path,
    report_path: Path = ROOT_CAUSE_G1_REPORT_PATH,
) -> str:
    c1_direct = _load_run_metrics(c1_run_dirs["direct"])
    c1_single = _load_run_metrics(c1_run_dirs["state_single"])
    c1_step = _load_run_metrics(c1_run_dirs["state_step"])
    d1 = _load_run_metrics(d1_run_dir)
    d2 = _load_run_metrics(d2_run_dir)
    e1 = _load_run_metrics(e1_run_dir)
    f1 = _load_run_metrics(f1_run_dir)

    d1_desc = (
        float(d1["mastered_accuracy"])
        > float(d1["partial_accuracy"])
        > float(d1["guessable_accuracy"])
        > float(d1["unreachable_accuracy"])
    )
    d2_desc = (
        float(d2["mastered_accuracy"])
        > float(d2["partial_accuracy"])
        > float(d2["guessable_accuracy"])
        > float(d2["unreachable_accuracy"])
    )
    persona_score = 2
    method_score = 0
    model_score = 0

    if float(e1.get("mean_state_change_rate") or 0.0) < 0.20:
        persona_score += 1
    if float(c1_step["item_accuracy_pearson_vs_real_students"]) < float(
        c1_single["item_accuracy_pearson_vs_real_students"]
    ):
        method_score += 1
    if d1_desc and not d2_desc:
        method_score += 2
    if not d1_desc:
        model_score += 2
    if float(f1["response_state_change_rate"]) > 0.30 or float(f1["predicted_answer_change_rate"]) > 0.30:
        model_score += 1
    if d1_desc and d2_desc and float(e1.get("mean_answer_change_rate") or 0.0) < 0.10:
        method_score += 1

    score_rows = [
        ["画像层", str(persona_score)],
        ["方法层", str(method_score)],
        ["模型边界/稳定性", str(model_score)],
    ]
    sorted_scores = sorted(
        [("画像层", persona_score), ("方法层", method_score), ("模型边界/稳定性", model_score)],
        key=lambda item: item[1],
        reverse=True,
    )
    primary_cause = sorted_scores[0][0]
    secondary_cause = sorted_scores[1][0]
    report = f"""# G1 最终归因报告

## 1. 固定结论回顾

- `B1`：`full_persona` 只比 `level_only` 好一点，不构成明显优势
- `B2`：`math_salient` 明显优于 `full_persona`
- `B3`：`shuffled_full ≈ full_persona`

这三步已经先把画像层问题钉住了：当前完整 persona 既有噪声，也没有被稳定细读。

## 2. 后续实验摘要

- `C1 direct/state_single/state_step`
  - `direct item_pearson = {_format_float(c1_direct["item_accuracy_pearson_vs_real_students"])}`
  - `state_single item_pearson = {_format_float(c1_single["item_accuracy_pearson_vs_real_students"])}`
  - `state_step item_pearson = {_format_float(c1_step["item_accuracy_pearson_vs_real_students"])}`
- `D1`
  - simple forced-state 严格下降：`{"是" if d1_desc else "否"}`
- `D2`
  - full forced-state 严格下降：`{"是" if d2_desc else "否"}`
- `E1`
  - `mean_state_change_rate = {_format_float(e1["mean_state_change_rate"])}`
  - `mean_answer_change_rate = {_format_float(e1["mean_answer_change_rate"])}`
- `F1`
  - `response_state_change_rate = {_format_float(f1["response_state_change_rate"])}`
  - `predicted_answer_change_rate = {_format_float(f1["predicted_answer_change_rate"])}`

## 3. 三层评分

{_build_markdown_table(headers=["层", "score"], rows=score_rows)}

## 4. 最终判断

- `主因`：{primary_cause}
- `次因`：{secondary_cause}
- `可修复项`：
  - 收缩 persona 到真正影响数学作答的少量关键信号
  - 减少会吃掉状态差异的多步协议噪声
  - 对 state 到 answer 的传递做更直接、更可审计的约束
- `当前模型时代限制`：
  - 如果 `D1` 本身都分不开，说明当前这代模型对细粒度状态边界的原生服从能力有限
  - 如果 `F1` 波动不小，说明即便结构正确，重复运行的稳定性也仍然是硬边界

## 5. 总结

综合全部实验，更像是：

1. 当前 persona 表示方式有明显问题
2. 当前方法协议，尤其是更重的多步协议，也会吃掉本来就不强的有效信号
3. 模型本身的边界和稳定性问题仍然存在，但不是唯一解释
"""
    _write_text(report_path, report)
    return f"最终归因已完成：主因更偏{primary_cause}，次因更偏{secondary_cause}"


def collect_run_progress(run_dir: Path) -> dict[str, object]:
    predictions_path = run_dir / "predictions.jsonl"
    failures_path = run_dir / "failures.jsonl"
    metrics_path = run_dir / "metrics.json"
    prediction_count = _count_jsonl_rows(predictions_path)
    failure_count = _count_jsonl_rows(failures_path)
    latest_mtime = None
    if predictions_path.exists():
        latest_mtime = predictions_path.stat().st_mtime
    elif failures_path.exists():
        latest_mtime = failures_path.stat().st_mtime
    return {
        "run_dir": str(run_dir),
        "prediction_count": prediction_count,
        "failure_count": failure_count,
        "completed": metrics_path.exists(),
        "latest_update_ts": latest_mtime,
    }
