from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

XES_ROOT = Path(__file__).resolve().parents[0]
if str(XES_ROOT) not in sys.path:
    sys.path.insert(0, str(XES_ROOT))

from run_student_conditioned_benchmark import (  # type: ignore
    _problem_profile_from_dict,
    _read_json,
    _read_jsonl,
    _resolve_xes_path,
    _student_model_from_dict,
    _student_signals_from_dict,
)
from src.data_loading import load_questions
from src.generation import (
    TERMINAL_STEP_PROTOCOL_SUFFIX,
    ThinkingStep,
    _build_thinking_payload,
)
from src.prompts import get_answer_generator_prompt
from src.response_state import ConstraintBundle, ItemResponseState
from src.student_item_interaction import StudentItemInteractionDecision
from weak_model_harness.src.weak_actor import WEAK_ACTOR_ANSWER_PROMPT, WEAK_ACTOR_ANSWER_RETRY_PROMPT
from weak_model_harness.src.support_profile import task_support_profile_from_dict
from weak_model_harness.src.compile_cards import (
    compile_prompt_ladder,
    compile_response_protocol,
    compile_risk_card,
    compile_scaffold_budget,
    compile_student_state,
    compile_task_state,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export one XES harness case as JSON.")
    parser.add_argument("--run_dir", type=str, required=True)
    parser.add_argument("--student_id", type=str, required=True)
    parser.add_argument("--question_id", type=str, required=True)
    parser.add_argument("--output_path", type=str, required=True)
    parser.add_argument("--mode", choices=["auto", "strong", "weak"], default="auto")
    return parser


def _question_lookup_from_run_config(run_config: dict[str, object]) -> dict[str, object]:
    question_path = str(run_config["question_path"])
    questions = load_questions(question_path, skip_image_questions=True)
    return {question.question_id: question for question in questions}


def _load_single_record(records: list[dict[str, object]], student_id: str, question_id: str) -> dict[str, object]:
    matches = [
        record
        for record in records
        if str(record.get("student_id")) == student_id and str(record.get("question_id")) == question_id
    ]
    if not matches:
        raise ValueError(f"case record not found for student_id={student_id}, question_id={question_id}")
    if len(matches) > 1:
        raise ValueError(f"duplicate case records found for student_id={student_id}, question_id={question_id}")
    return matches[0]


def _reconstruct_thinking_io(
    *,
    record: dict[str, object],
    run_config: dict[str, object],
    question: object,
) -> dict[str, object]:
    student_model = _student_model_from_dict(record["student_model"])
    internal_signals = _student_signals_from_dict(record["implementation_derived_signals"])
    problem_profile = _problem_profile_from_dict(record["problem_requirement_profile"])
    interaction_decision = (
        StudentItemInteractionDecision(**record["student_item_interaction_decision"])
        if record.get("student_item_interaction_decision") is not None
        else None
    )
    item_state = ItemResponseState(**record["item_response_state"])
    constraints = ConstraintBundle(**record["constraint_bundle"])
    question_text = str(question.question_text)
    options = dict(question.options)
    thinking_trace = [ThinkingStep(**step) for step in record.get("thinking_trace", [])]
    effective_max_thinking_steps = min(int(run_config["max_thinking_steps"]), constraints.max_thinking_steps)

    step_records: list[dict[str, object]] = []
    previous_steps: list[ThinkingStep] = []
    for step_index in range(1, effective_max_thinking_steps + 1):
        remaining_step_budget = effective_max_thinking_steps - step_index + 1
        user_payload = _build_thinking_payload(
            student_model=student_model,
            internal_signals=internal_signals,
            problem_profile=problem_profile,
            item_state=item_state,
            constraints=constraints,
            interaction_decision=interaction_decision,
            question_id=str(record["question_id"]),
            question_text=question_text,
            options=options,
            thinking_trace=previous_steps,
            step_index=step_index,
            remaining_step_budget=remaining_step_budget,
        )
        system_prompt = get_answer_generator_prompt(str(run_config["response_persona"]))
        if remaining_step_budget == 1:
            system_prompt += TERMINAL_STEP_PROTOCOL_SUFFIX
        step_output = thinking_trace[step_index - 1] if step_index - 1 < len(thinking_trace) else None
        step_records.append(
            {
                "step_index": step_index,
                "remaining_step_budget": remaining_step_budget,
                "system_prompt": system_prompt,
                "user_payload": user_payload,
                "model_output": asdict(step_output) if step_output is not None else None,
            }
        )
        if step_output is not None:
            previous_steps.append(step_output)

    return {
        "student_model": record["student_model"],
        "implementation_derived_signals": record["implementation_derived_signals"],
        "problem_requirement_profile": record["problem_requirement_profile"],
        "student_item_interaction_decision": record.get("student_item_interaction_decision"),
        "item_response_state": record["item_response_state"],
        "constraint_bundle": record["constraint_bundle"],
        "question_text": question.question_text,
        "options": question.options,
        "run_config_response_persona": run_config["response_persona"],
        "run_config_max_thinking_steps": run_config["max_thinking_steps"],
        "steps": step_records,
        "final_model_output": {
            "predicted_answer": record.get("predicted_answer"),
            "student_response": record.get("student_response"),
            "thinking_steps_n": record.get("thinking_steps_n"),
        },
    }


def _reconstruct_weak_io(
    *,
    record: dict[str, object],
    question: object,
) -> dict[str, object]:
    student_state = compile_student_state(_student_model_from_dict(record["student_model"]))
    task_state = compile_task_state(
        str(record["question_id"]),
        str(record["question_type"]),
        _problem_profile_from_dict(record["problem_requirement_profile"]),
        task_support_profile_from_dict(record["task_support_profile"]),
    )
    scaffold_budget = compile_scaffold_budget(
        student_state,
        task_state,
        task_support_profile_from_dict(record["task_support_profile"]),
    )
    prompt_ladder = compile_prompt_ladder(
        task_state=task_state,
        scaffold_budget=scaffold_budget,
        task_support_profile=task_support_profile_from_dict(record["task_support_profile"]),
    )
    risk_card = compile_risk_card(
        student_state=student_state,
        task_state=task_state,
        task_support_profile=task_support_profile_from_dict(record["task_support_profile"]),
        scaffold_budget=scaffold_budget,
    )
    response_protocol = compile_response_protocol(
        task_state=task_state,
        scaffold_budget=scaffold_budget,
    )
    user_payload = {
        "student_state": asdict(student_state),
        "task_state": asdict(task_state),
        "scaffold_budget": asdict(scaffold_budget),
        "prompt_ladder": asdict(prompt_ladder),
        "risk_card": asdict(risk_card),
        "response_protocol": asdict(response_protocol),
        "question_text": question.question_text,
        "options": question.options,
    }
    return {
        "student_state": asdict(student_state),
        "task_state": asdict(task_state),
        "scaffold_budget": asdict(scaffold_budget),
        "prompt_ladder": asdict(prompt_ladder),
        "risk_card": asdict(risk_card),
        "response_protocol": asdict(response_protocol),
        "system_prompt_first": WEAK_ACTOR_ANSWER_PROMPT,
        "system_prompt_retry": WEAK_ACTOR_ANSWER_PROMPT + WEAK_ACTOR_ANSWER_RETRY_PROMPT,
        "user_payload": user_payload,
        "attempt_count": record.get("weak_actor_attempt_count"),
        "model_output": {
            "predicted_answer": record.get("predicted_answer"),
            "student_response": record.get("student_response"),
            "used_support_level": record.get("used_support_level"),
            "support_trace": record.get("support_trace"),
        },
        "question_text": question.question_text,
        "options": question.options,
    }


def main() -> None:
    args = _build_parser().parse_args()
    run_dir = Path(_resolve_xes_path(args.run_dir))
    output_path = Path(_resolve_xes_path(args.output_path))

    run_config_path = run_dir / "metrics.json"
    if not run_config_path.exists():
        raise FileNotFoundError(f"metrics.json not found in run_dir: {run_dir}")
    metrics = _read_json(run_config_path)
    if not isinstance(metrics, dict):
        raise ValueError("metrics.json must be a JSON object")
    run_config = metrics.get("run_config")
    if not isinstance(run_config, dict):
        raise ValueError("metrics.json missing run_config")

    question_lookup = _question_lookup_from_run_config(run_config)
    benchmark_students = {
        str(row["student_id"]): row
        for row in _read_jsonl(run_dir / "benchmark_students.jsonl")
    }
    records = _read_jsonl(run_dir / "predictions.jsonl")
    record = _load_single_record(records, args.student_id, args.question_id)
    benchmark_student = benchmark_students.get(args.student_id)
    if benchmark_student is None:
        raise ValueError(f"benchmark student not found: {args.student_id}")
    question = question_lookup.get(args.question_id)
    if question is None:
        raise ValueError(f"question not found in metadata: {args.question_id}")

    mode = args.mode
    if mode == "auto":
        mode = "weak" if "task_support_profile" in record else "strong"

    payload: dict[str, object] = {
        "run_dir": str(run_dir),
        "student_id": args.student_id,
        "question_id": args.question_id,
        "benchmark_student": benchmark_student,
        "prediction_record": record,
        "question_meta": {
            "question_id": question.question_id,
            "question_text": question.question_text,
            "question_type": question.question_type,
            "options": question.options,
            "answer": question.answer,
            "has_image_marker": question.has_image_marker,
            "difficulty_band": question.difficulty_band,
            "paper_module_name": question.paper_module_name,
            "paper_b_hat": question.paper_b_hat,
        },
    }
    if mode == "strong":
        payload["generation"] = _reconstruct_thinking_io(
            record=record,
            run_config=run_config,
            question=question,
        )
    else:
        payload["generation"] = _reconstruct_weak_io(
            record=record,
            question=question,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


if __name__ == "__main__":
    main()
