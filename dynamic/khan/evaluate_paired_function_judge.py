from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from label_khan_correctness import (
    LLMConfig,
    OpenAICompatClient,
    KhanTurnSample,
    append_jsonl,
    build_turn_samples,
    read_jsonl,
    write_json,
    write_jsonl,
)


ROOT = Path(__file__).resolve().parent

FUNCTION_LABELS = {"correct", "incorrect", "na"}
TUTOR_REQUEST_LABELS = {
    "math_final_answer",
    "math_intermediate_step",
    "math_explanation",
    "math_judgment",
    "non_math",
}
RESPONSE_TYPE_LABELS = {
    "answers_request",
    "asks_clarification",
    "says_dont_know",
    "social_or_preference",
    "unrelated",
}
KNOWLEDGE_LABELS = {"factual", "conceptual", "procedural", "metacognitive"}
LOCUS_LABELS = {"reading", "comprehension", "transformation", "process_skills", "encoding"}
MECHANISM_LABELS = {
    "language_difficulty",
    "spatial_information_difficulty",
    "deficient_prerequisites",
    "incorrect_associations",
    "irrelevant_rules",
}


PAIR_JUDGE_SYSTEM_PROMPT = """You compare two student turns in the same math tutoring context.
Return exactly one compact JSON object and no markdown.

You will receive:
- visible dialogue history before the target student turn,
- the real student turn,
- a candidate student turn.

Your job:
1. Label what the real student turn is doing: correct, incorrect, or na.
2. Label what the candidate student turn is doing: correct, incorrect, or na.
3. If either turn contains a substantive codable math error, code the error using the listed theory labels.

Function labels:
- correct: the turn correctly satisfies the immediately preceding tutor's local math request.
- incorrect: the tutor requested a math answer/step/judgment, but the turn is wrong, missing, confused, asks for explanation instead of answering, or gives an invalid method.
- na: the preceding tutor turn did not request a math answer/step/judgment, or the turn is only social, preference, planning, affect, or non-math.

Important EEDI-style rules:
- Judge only relative to the immediately preceding tutor turn and visible history.
- tutor_request_type is determined by the immediately preceding tutor turn, not by whether the student mentions math.
- If the preceding tutor asks what to practice next, whether to continue, or another preference/planning question, use non_math.
- Use the full history to resolve references like "that problem", "again", "this", or "the same question".
- If the tutor asks an intermediate step, judge that exact intermediate step, not the final answer to the whole problem.
- If the tutor asks a final answer, judge the final answer.
- Decide the local criterion once, before judging either student turn.
- Judge the real student turn independently; the candidate turn must not make the real turn look better or worse.
- Mathematically equivalent answers count as correct unless the tutor explicitly asks for a specific form.
- If the tutor asks for a value, simplified integers, decimals, or equivalent fractions are acceptable when mathematically equal.
- If the tutor asks what an expression "equals", judge the mathematical value; do not require an unsimplified fraction, intermediate form, or shown work unless explicitly requested.
- If the tutor requests a math answer/step/judgment and the student asks "what do you mean?", "can you explain?", "I don't know", or similar, label incorrect.
- If the student gives a wrong attempt and then explicitly self-corrects in the same turn, judge the final self-corrected answer.
- If the student gives both a wrong answer and a correct answer without clear self-correction, label incorrect.
- If the student gives an answer and then adds a social/unrelated sentence, judge the answer part first.
- If the tutor only states an answer/explanation and the student merely says "yes", "ok", "yeah", or similar acknowledgement, label na unless the tutor explicitly asks for a math judgment.
- Direction words, signs, units, and options matter.
- Spelling and casual wording do not matter if the math meaning is clear.

Codable math error:
- Only an incorrect math response can have a codable math error.
- If a turn is correct or na, has_codable_error must be false and all error labels null.
- If the turn is incorrect only because it is social, unrelated, or says "I don't know", has_codable_error should usually be false.

Knowledge labels: factual, conceptual, procedural, metacognitive.
Error locus labels: reading, comprehension, transformation, process_skills, encoding.
Error mechanism labels: language_difficulty, spatial_information_difficulty, deficient_prerequisites, incorrect_associations, irrelevant_rules.

Return exactly these keys:
- tutor_request_type
- requested_local_criterion
- real_response_type
- candidate_response_type
- real_satisfies_criterion
- candidate_satisfies_criterion
- real_function
- candidate_function
- real_has_codable_error
- candidate_has_codable_error
- real_knowledge_type
- candidate_knowledge_type
- real_error_locus
- candidate_error_locus
- real_error_mechanism
- candidate_error_mechanism
- real_evidence
- candidate_evidence

Allowed tutor_request_type values:
- math_final_answer
- math_intermediate_step
- math_explanation
- math_judgment
- non_math

Allowed response_type values:
- answers_request
- asks_clarification
- says_dont_know
- social_or_preference
- unrelated

Consistency constraints:
- If tutor_request_type is non_math, both function labels must be na and both satisfies fields must be null.
- For non_math, requested_local_criterion must be "none".
- If tutor_request_type is not non_math and a response_type is asks_clarification or says_dont_know, that side's function must be incorrect.
- If a response_type is social_or_preference or unrelated, that side's function should be na unless it contains a substantive math answer.
- If a response_type is answers_request, that side's satisfies field must be true or false.
- If a side's satisfies field is true, that side's function must be correct.
- If a side's satisfies field is false, that side's function must be incorrect.
- If a side's function is correct or na, that side cannot have a codable error.
- real_evidence must support only the real side's label.
- candidate_evidence must support only the candidate side's label.
- Keep each evidence field short, ideally one sentence under 25 words.
"""


def build_pair_prompt(sample: KhanTurnSample, candidate_turn: str) -> str:
    history_lines: list[str] = []
    for idx, turn in enumerate(sample.history):
        role = "Tutor" if turn["role"] in {"assistant", "tutor"} else "Student"
        history_lines.append(f"Turn {idx + 1} ({role}): {turn['content']}")
    return (
        f"Math level: {sample.math_level}\n\n"
        "Visible dialogue history before the target student turn:\n"
        + "\n".join(history_lines)
        + "\n\nReal student turn:\n"
        + sample.gt_student_turn
        + "\n\nCandidate student turn:\n"
        + candidate_turn
        + "\n\nReturn JSON only."
    )


def _nullable_label(value: object, allowed: set[str], field_name: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"", "null", "none", "na", "n/a"}:
        return None
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)} or null; got {value!r}")
    return text


def _bool_value(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"{field_name} must be boolean; got {value!r}")


def _nullable_bool_value(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"null", "none", "na", "n/a", ""}:
            return None
        if text in {"true", "false"}:
            return text == "true"
    raise ValueError(f"{field_name} must be true, false, or null; got {value!r}")


def _required_label(parsed: dict[str, Any], field_name: str, allowed: set[str]) -> str:
    value = str(parsed.get(field_name, "") or "").strip().lower()
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}; got {value!r}")
    return value


def _derive_function(
    tutor_request_type: str,
    response_type: str,
    satisfies_criterion: bool | None,
    side_name: str,
) -> str | None:
    if tutor_request_type == "non_math":
        return None
    if response_type in {"social_or_preference", "unrelated"}:
        return None
    if response_type != "answers_request":
        return "incorrect"
    if satisfies_criterion is True:
        return "correct"
    if satisfies_criterion is False:
        return "incorrect"
    raise ValueError(f"{side_name}_satisfies_criterion must be true or false for answer-like math responses")


def _form_is_explicitly_required(requested_local_criterion: str) -> bool:
    text = requested_local_criterion.lower()
    return any(
        phrase in text
        for phrase in [
            "as a fraction",
            "fraction form",
            "as a decimal",
            "decimal form",
            "mixed number",
            "unsimplified",
            "specific form",
        ]
    )


def _check_side_evidence_consistency(
    function_label: str,
    evidence: str,
    requested_local_criterion: str,
    side_name: str,
) -> None:
    evidence_text = evidence.lower()
    if function_label == "incorrect" and not _form_is_explicitly_required(requested_local_criterion):
        contradiction_phrases = [
            "correct value",
            "mathematically correct",
            "equivalent answer",
            "equivalent value",
            "which is correct",
        ]
        if any(phrase in evidence_text for phrase in contradiction_phrases):
            raise ValueError(f"{side_name}_evidence contradicts function=incorrect")


def parse_pair_judgment(parsed: dict[str, Any]) -> dict[str, Any]:
    tutor_request_type = _required_label(parsed, "tutor_request_type", TUTOR_REQUEST_LABELS)
    requested_local_criterion = str(parsed.get("requested_local_criterion", "") or "").strip()
    if not requested_local_criterion and tutor_request_type == "non_math":
        requested_local_criterion = "none"
    elif not requested_local_criterion:
        raise ValueError("requested_local_criterion cannot be empty")
    real_response_type = _required_label(parsed, "real_response_type", RESPONSE_TYPE_LABELS)
    candidate_response_type = _required_label(parsed, "candidate_response_type", RESPONSE_TYPE_LABELS)
    real_satisfies = _nullable_bool_value(parsed.get("real_satisfies_criterion"), "real_satisfies_criterion")
    candidate_satisfies = _nullable_bool_value(
        parsed.get("candidate_satisfies_criterion"),
        "candidate_satisfies_criterion",
    )
    real_function = _required_label(parsed, "real_function", FUNCTION_LABELS)
    candidate_function = _required_label(parsed, "candidate_function", FUNCTION_LABELS)
    derived_real_function = _derive_function(
        tutor_request_type,
        real_response_type,
        real_satisfies,
        "real",
    )
    derived_candidate_function = _derive_function(
        tutor_request_type,
        candidate_response_type,
        candidate_satisfies,
        "candidate",
    )
    if derived_real_function is not None and real_function != derived_real_function:
        raise ValueError(
            f"real_function={real_function!r} conflicts with structured decision {derived_real_function!r}"
        )
    if derived_candidate_function is not None and candidate_function != derived_candidate_function:
        raise ValueError(
            f"candidate_function={candidate_function!r} conflicts with structured decision {derived_candidate_function!r}"
        )
    if tutor_request_type == "non_math" or real_response_type in {"social_or_preference", "unrelated"}:
        real_satisfies = None
    if tutor_request_type == "non_math" or candidate_response_type in {"social_or_preference", "unrelated"}:
        candidate_satisfies = None

    real_has_error = _bool_value(parsed.get("real_has_codable_error"), "real_has_codable_error")
    candidate_has_error = _bool_value(
        parsed.get("candidate_has_codable_error"),
        "candidate_has_codable_error",
    )
    if real_function != "incorrect":
        real_has_error = False
    if candidate_function != "incorrect":
        candidate_has_error = False

    real_knowledge = _nullable_label(parsed.get("real_knowledge_type"), KNOWLEDGE_LABELS, "real_knowledge_type")
    candidate_knowledge = _nullable_label(
        parsed.get("candidate_knowledge_type"),
        KNOWLEDGE_LABELS,
        "candidate_knowledge_type",
    )
    real_locus = _nullable_label(parsed.get("real_error_locus"), LOCUS_LABELS, "real_error_locus")
    candidate_locus = _nullable_label(parsed.get("candidate_error_locus"), LOCUS_LABELS, "candidate_error_locus")
    real_mechanism = _nullable_label(parsed.get("real_error_mechanism"), MECHANISM_LABELS, "real_error_mechanism")
    candidate_mechanism = _nullable_label(
        parsed.get("candidate_error_mechanism"),
        MECHANISM_LABELS,
        "candidate_error_mechanism",
    )
    if not real_has_error:
        real_knowledge = None
        real_locus = None
        real_mechanism = None
    elif real_knowledge is None or real_locus is None or real_mechanism is None:
        raise ValueError("real codable error requires all real error labels")
    if not candidate_has_error:
        candidate_knowledge = None
        candidate_locus = None
        candidate_mechanism = None
    elif candidate_knowledge is None or candidate_locus is None or candidate_mechanism is None:
        raise ValueError("candidate codable error requires all candidate error labels")

    real_evidence = str(parsed.get("real_evidence", "") or "").strip()
    candidate_evidence = str(parsed.get("candidate_evidence", "") or "").strip()
    if not real_evidence:
        raise ValueError("real_evidence cannot be empty")
    if not candidate_evidence:
        raise ValueError("candidate_evidence cannot be empty")

    both_error = real_has_error and candidate_has_error
    return {
        "tutor_request_type": tutor_request_type,
        "requested_local_criterion": requested_local_criterion,
        "real_response_type": real_response_type,
        "candidate_response_type": candidate_response_type,
        "real_satisfies_criterion": real_satisfies,
        "candidate_satisfies_criterion": candidate_satisfies,
        "real_function": real_function,
        "candidate_function": candidate_function,
        "same_function": real_function == candidate_function,
        "real_has_codable_error": real_has_error,
        "candidate_has_codable_error": candidate_has_error,
        "both_have_codable_error": both_error,
        "real_knowledge_type": real_knowledge,
        "candidate_knowledge_type": candidate_knowledge,
        "real_error_locus": real_locus,
        "candidate_error_locus": candidate_locus,
        "real_error_mechanism": real_mechanism,
        "candidate_error_mechanism": candidate_mechanism,
        "same_knowledge": None if not both_error else real_knowledge == candidate_knowledge and real_knowledge is not None,
        "same_locus": None if not both_error else real_locus == candidate_locus and real_locus is not None,
        "same_mechanism": None if not both_error else real_mechanism == candidate_mechanism and real_mechanism is not None,
        "real_evidence": real_evidence,
        "candidate_evidence": candidate_evidence,
        "evidence": f"Real: {real_evidence} Candidate: {candidate_evidence}",
    }


def build_pairs(samples: list[KhanTurnSample], modes: list[str], seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    shuffled_turns = [sample.gt_student_turn for sample in samples]
    rng.shuffle(shuffled_turns)
    if len(shuffled_turns) > 1:
        shuffled_turns = shuffled_turns[1:] + shuffled_turns[:1]
    pairs: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples):
        candidates = {
            "real_real": sample.gt_student_turn,
            "shuffled_real": shuffled_turns[idx],
            "trivial_dont_know": "I don't know.",
        }
        for mode in modes:
            if mode not in candidates:
                raise ValueError(f"unknown mode={mode!r}")
            pairs.append(
                {
                    "pair_id": f"{mode}::{sample.sample_id}",
                    "mode": mode,
                    "sample": sample,
                    "candidate_turn": candidates[mode],
                }
            )
    return pairs


def build_simulation_pairs_from_prediction_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        dialogue_id = str(row.get("dialogue_id", "") or "").strip()
        turn_idx = int(row.get("turn_idx"))
        gt_turn = str(row.get("gt_turn", "") or "").strip()
        pred_turn = str(row.get("pred_turn", "") or "").strip()
        if not dialogue_id:
            raise ValueError(f"prediction row index={row_index} has empty dialogue_id")
        if not gt_turn:
            raise ValueError(f"prediction row index={row_index} has empty gt_turn")
        if not pred_turn:
            raise ValueError(f"prediction row index={row_index} has empty pred_turn")
        history = _normalize_prediction_history(row.get("history"), row_index)
        latest_tutor_turn = ""
        for turn in reversed(history):
            if turn["role"] == "assistant":
                latest_tutor_turn = turn["content"]
                break
        if not latest_tutor_turn:
            raise ValueError(f"prediction row index={row_index} has no visible tutor turn")
        math_level = _prediction_math_level(row)
        sample = KhanTurnSample(
            sample_id=f"{dialogue_id}_turn_{turn_idx}",
            test_id=str(row.get("question_id", dialogue_id) or dialogue_id),
            math_level=math_level,
            dialogue_turn_count=len(history) + 1,
            target_turn_idx=turn_idx,
            history=history,
            tutor_turn=latest_tutor_turn,
            gt_student_turn=gt_turn,
        )
        pairs.append(
            {
                "pair_id": f"simulation::{sample.sample_id}",
                "mode": "simulation",
                "sample": sample,
                "candidate_turn": pred_turn,
            }
        )
    return pairs


def _normalize_prediction_history(raw_history: object, row_index: int) -> list[dict[str, str]]:
    if not isinstance(raw_history, list) or not raw_history:
        raise ValueError(f"prediction row index={row_index} has empty history")
    history: list[dict[str, str]] = []
    for turn in raw_history:
        if not isinstance(turn, dict):
            continue
        raw_role = str(turn.get("role", "") or "").strip()
        role = {
            "tutor": "assistant",
            "assistant": "assistant",
            "student": "user",
            "user": "user",
        }.get(raw_role)
        content = " ".join(str(turn.get("content", "") or "").split()).strip()
        if role is None or not content:
            continue
        history.append({"role": role, "content": content})
    if not history:
        raise ValueError(f"prediction row index={row_index} has no usable history")
    return history


def _prediction_math_level(row: dict[str, Any]) -> str:
    subjects = row.get("subjects")
    if isinstance(subjects, list):
        for subject in subjects:
            if isinstance(subject, (list, tuple)) and subject:
                text = str(subject[0]).strip()
                prefix = "Khan math level: "
                if text.startswith(prefix):
                    return text[len(prefix) :].strip()
                if text:
                    return text
    return ""


def judge_one(
    pair: dict[str, Any],
    client: OpenAICompatClient,
    max_attempts: int,
) -> dict[str, Any]:
    sample: KhanTurnSample = pair["sample"]
    candidate_turn = str(pair["candidate_turn"])
    prompt = build_pair_prompt(sample, candidate_turn)
    last_error = ""
    for attempt_idx in range(max_attempts):
        try:
            parsed = client.chat_json(PAIR_JUDGE_SYSTEM_PROMPT, prompt)
            judgment = parse_pair_judgment(parsed)
            return {
                "pair_id": pair["pair_id"],
                "mode": pair["mode"],
                "sample_id": sample.sample_id,
                "test_id": sample.test_id,
                "math_level": sample.math_level,
                "target_turn_idx": sample.target_turn_idx,
                "history": sample.history,
                "tutor_turn": sample.tutor_turn,
                "real_student_turn": sample.gt_student_turn,
                "candidate_student_turn": candidate_turn,
                **judgment,
                "judge_attempt": attempt_idx + 1,
            }
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(1 + attempt_idx)
    raise RuntimeError(f"paired judgment failed after {max_attempts} attempts: {last_error}")


def summarize(rows: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "n_rows": len(rows),
        "n_failures": len(failures),
        "by_mode": {},
    }
    for mode in sorted({str(row["mode"]) for row in rows}):
        mode_rows = [row for row in rows if str(row["mode"]) == mode]
        same_count = sum(1 for row in mode_rows if bool(row["same_function"]))
        real_error_rows = [row for row in mode_rows if bool(row["real_has_codable_error"])]
        candidate_error_rows = [row for row in mode_rows if bool(row["candidate_has_codable_error"])]
        both_error_rows = [row for row in mode_rows if bool(row["both_have_codable_error"])]
        summary["by_mode"][mode] = {
            "n": len(mode_rows),
            "same_function_count": same_count,
            "same_function_rate": same_count / len(mode_rows) if mode_rows else None,
            "real_function_counts": _counts(row["real_function"] for row in mode_rows),
            "candidate_function_counts": _counts(row["candidate_function"] for row in mode_rows),
            "real_codable_error_n": len(real_error_rows),
            "candidate_codable_error_n": len(candidate_error_rows),
            "both_codable_error_n": len(both_error_rows),
            "error_realization_rate": (
                len(both_error_rows) / len(real_error_rows) if real_error_rows else None
            ),
            "same_knowledge_rate": _nullable_bool_rate(row.get("same_knowledge") for row in both_error_rows),
            "same_locus_rate": _nullable_bool_rate(row.get("same_locus") for row in both_error_rows),
            "same_mechanism_rate": _nullable_bool_rate(row.get("same_mechanism") for row in both_error_rows),
        }
    return summary


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = str(value)
        counts[text] = counts.get(text, 0) + 1
    return counts


def _nullable_bool_rate(values: Any) -> float | None:
    values_list = [value for value in values if value is not None]
    if not values_list:
        return None
    return sum(1 for value in values_list if bool(value)) / len(values_list)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Khan paired function judge sanity checks.")
    parser.add_argument("--dataset_path", default=str(ROOT / "CoMTA_dataset.json"))
    parser.add_argument(
        "--predictions_path",
        default="",
        help="When set, evaluate real student turns against pred_turn from this simulation predictions.jsonl.",
    )
    parser.add_argument("--output_dir", default=str(ROOT / "outputs" / "paired_function_judge_sanity_20260522"))
    parser.add_argument("--modes", default="real_real,shuffled_real,trivial_dont_know")
    parser.add_argument("--max_samples", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--llm_base_url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--llm_model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--llm_api_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--timeout_s", type=float, default=120.0)
    parser.add_argument("--max_tokens", type=int, default=1200)
    parser.add_argument("--max_concurrency", type=int, default=8)
    parser.add_argument("--max_attempts", type=int, default=4)
    parser.add_argument("--dry_run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    if str(args.predictions_path or "").strip():
        prediction_rows = read_jsonl(Path(args.predictions_path))
        if args.max_samples is not None:
            prediction_rows = prediction_rows[: args.max_samples]
        pairs = build_simulation_pairs_from_prediction_rows(prediction_rows)
        modes = ["simulation"]
        samples = [pair["sample"] for pair in pairs]
    else:
        samples = build_turn_samples(Path(args.dataset_path))
        if args.max_samples is not None:
            samples = samples[: args.max_samples]
        modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
        pairs = build_pairs(samples, modes, args.seed)
    write_jsonl(
        output_dir / "pair_inputs.jsonl",
        [
            {
                "pair_id": pair["pair_id"],
                "mode": pair["mode"],
                "sample_id": pair["sample"].sample_id,
                "test_id": pair["sample"].test_id,
                "target_turn_idx": pair["sample"].target_turn_idx,
                "tutor_turn": pair["sample"].tutor_turn,
                "real_student_turn": pair["sample"].gt_student_turn,
                "candidate_student_turn": pair["candidate_turn"],
            }
            for pair in pairs
        ],
    )
    write_json(
        output_dir / "run_config.json",
        {
            "dataset_path": args.dataset_path,
            "predictions_path": args.predictions_path,
            "n_samples": len(samples),
            "n_pairs": len(pairs),
            "modes": modes,
            "seed": args.seed,
            "dry_run": args.dry_run,
        },
    )
    if args.dry_run:
        print(f"[DryRun] samples={len(samples)} pairs={len(pairs)} output_dir={output_dir}")
        return
    if not args.llm_base_url or not args.llm_model:
        raise ValueError("--llm_base_url and --llm_model are required unless --dry_run is set")

    rows_path = output_dir / "paired_judge_rows.jsonl"
    failures_path = output_dir / "failures.jsonl"
    completed = {str(row["pair_id"]) for row in read_jsonl(rows_path)}
    remaining = [pair for pair in pairs if str(pair["pair_id"]) not in completed]
    if failures_path.exists() and remaining:
        failures_path.unlink()

    client = OpenAICompatClient(
        LLMConfig(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            timeout_s=args.timeout_s,
            max_tokens=args.max_tokens,
        )
    )
    print(f"[Data] pairs={len(pairs)} completed={len(completed)} remaining={len(remaining)}")
    with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
        future_map = {
            executor.submit(judge_one, pair, client, args.max_attempts): pair
            for pair in remaining
        }
        done = 0
        for future in as_completed(future_map):
            pair = future_map[future]
            try:
                append_jsonl(rows_path, future.result())
            except Exception as exc:
                sample: KhanTurnSample = pair["sample"]
                append_jsonl(
                    failures_path,
                    {
                        "pair_id": pair["pair_id"],
                        "mode": pair["mode"],
                        "sample_id": sample.sample_id,
                        "error": repr(exc),
                    },
                )
            done += 1
            if done % 20 == 0 or done == len(remaining):
                print(f"[Progress] judged_this_run={done}/{len(remaining)}")

    rows = read_jsonl(rows_path)
    failures = read_jsonl(failures_path)
    summary = summarize(rows, failures)
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[Done] output_dir={output_dir}")


if __name__ == "__main__":
    main()
