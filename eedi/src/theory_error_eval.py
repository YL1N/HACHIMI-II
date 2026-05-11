from __future__ import annotations

import csv
import json
from ast import literal_eval
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evaluation_eedi import write_json, write_jsonl
from .llm_client import LLMConfig, OpenAICompatClient

KNOWLEDGE_TYPES = (
    "factual",
    "conceptual",
    "procedural",
    "metacognitive",
)
ERROR_LOCI = (
    "reading",
    "comprehension",
    "transformation",
    "process_skills",
    "encoding",
)
ERROR_MECHANISMS = (
    "language_difficulty",
    "spatial_information_difficulty",
    "deficient_prerequisites",
    "incorrect_associations",
    "irrelevant_rules",
)

THEORY_SOURCE_NOTES = {
    "knowledge_type": (
        "Anderson & Krathwohl (2001) knowledge dimension, used for mathematics "
        "error analysis by Benecke & Kaiser (2023)."
    ),
    "error_locus": (
        "Newman Error Analysis, summarized by White (2010): reading, "
        "comprehension, transformation, process skills, encoding."
    ),
    "error_mechanism": (
        "Radatz (1979) error causes: language difficulties, spatial information "
        "difficulties, deficient prerequisites, incorrect associations, "
        "application of irrelevant rules."
    ),
}

THEORY_ERROR_OUTPUT_SCHEMA = """Required output JSON schema:
{
  "has_codable_math_error": boolean,
  "knowledge_type": "factual" | "conceptual" | "procedural" | "metacognitive" | null,
  "error_locus": "reading" | "comprehension" | "transformation" | "process_skills" | "encoding" | null,
  "error_mechanism": "language_difficulty" | "spatial_information_difficulty" | "deficient_prerequisites" | "incorrect_associations" | "irrelevant_rules" | null,
  "evidence": ["non-empty string", "non-empty string"]
}

Hard output rules:
- Return exactly these five top-level keys and no others.
- evidence must always be a JSON array of 1 to 3 non-empty strings.
- If has_codable_math_error is false, set all three labels to null, but still provide 1 to 3 evidence strings explaining why the turn is not a codable mathematical error.
- Do not return markdown fences.
- Do not return prose before or after the JSON object."""

CODER_SYSTEM_PROMPT = """You are a mathematics-education error-analysis judge.

Your job is to code ONE student turn using three theory-grounded dimensions only.
Do not invent task-specific categories.
Do not use surface answer matching as your coding rule.
Code only what is evidenced by the current student turn, the local dialogue context, and the question/solution context provided.

Framework 1: Knowledge Type
Source:
- Anderson & Krathwohl (2001), knowledge dimension.
- Used for mathematics error analysis by Benecke & Kaiser (2023).

Allowed labels:
- factual
- conceptual
- procedural
- metacognitive

Use them as follows:
- factual:
  Use this when the error mainly reflects missing or incorrect terminology, symbols, specific details/elements, basic number facts, or formulas.
  This follows factual knowledge: terminology and specific details/elements.
- conceptual:
  Use this when the error mainly reflects misunderstanding of concepts, principles, classifications, or relationships among mathematical ideas.
  This follows conceptual knowledge: classifications, categories, principles, generalizations, theories, models, and structures.
- procedural:
  Use this when the error mainly reflects not knowing how to carry out a method, algorithm, or procedure, or not knowing which procedure/criterion should be used.
  This follows procedural knowledge: subject-specific skills and algorithms, techniques and methods, and criteria for determining when to use appropriate procedures.
- metacognitive:
  Use this when the error is best explained by a failure of strategy awareness, monitoring, or self-knowledge about cognition rather than primarily factual, conceptual, or procedural deficiency.
  This follows metacognitive knowledge: strategic knowledge, knowledge about cognitive tasks, and self-knowledge.

Framework 2: Error Locus
Source:
- Newman Error Analysis, summarized by White (2010).

Allowed labels:
- reading
- comprehension
- transformation
- process_skills
- encoding

Use them as follows:
- reading:
  The student cannot correctly read or identify the relevant word, number, or mathematical symbol needed to start solving.
- comprehension:
  The student can read the problem text/symbols but does not understand what the question is asking, what is known, what is unknown, or what condition matters.
- transformation:
  The student understands the problem situation but cannot translate it into the correct mathematical representation, operation, or method.
- process_skills:
  The student has selected a basically relevant representation or method, but carries out the procedure or calculation incorrectly.
- encoding:
  The student has essentially completed the mathematical work but expresses the final answer in an unacceptable or incorrect written/stated form.

Important Newman rule:
- Treat the framework as hierarchical.
- Choose the earliest stage at which the breakdown is evidenced.

Framework 3: Error Mechanism
Source:
- Radatz (1979).

Allowed labels:
- language_difficulty
- spatial_information_difficulty
- deficient_prerequisites
- incorrect_associations
- irrelevant_rules

Use them as follows:
- language_difficulty:
  The error is mainly due to semantic misunderstanding or difficulty translating between natural language and mathematical language.
- spatial_information_difficulty:
  The error is mainly due to difficulty obtaining or using spatial/visual information, diagrams, layouts, positions, or spatial relations.
- deficient_prerequisites:
  The error is mainly due to deficient mastery of prerequisite skills, facts, or concepts needed for this task.
- incorrect_associations:
  The error is mainly due to an incorrect association, misleading linkage, or rigidity of thinking.
- irrelevant_rules:
  The error is mainly due to applying an irrelevant rule, strategy, or procedure from another kind of problem.

General coding rules:
1. Code only what is evidenced by:
   - the current student turn,
   - the immediately relevant dialogue context,
   - the question and official solution context.
2. If the student turn does not contain a substantive mathematical error that can be coded using these frameworks, return:
   has_codable_math_error = false
   and set all three labels to null.
3. If uncertainty language is present but the student still expresses a mathematical error, code the mathematical error.
4. Do not create any new labels.
5. If more than one label seems plausible:
   - for Newman, choose the earliest evidenced breakdown;
   - for the other two frameworks, choose the single label most directly supported by the evidence.
6. If the evidence is insufficient to choose labels reliably, return has_codable_math_error = false.
7. Return JSON only.

""" + THEORY_ERROR_OUTPUT_SCHEMA


@dataclass(frozen=True)
class TheoryErrorCode:
    has_codable_math_error: bool
    knowledge_type: str | None
    error_locus: str | None
    error_mechanism: str | None
    evidence: list[str]


def load_theory_error_rows(input_file: Path, truncate: int = 0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with input_file.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            row = dict(raw_row)
            row["turn_idx"] = int(str(row["turn_idx"]))
            for key in ("subjects", "turns", "question_annotation", "correctness", "acts", "eedi_kcs", "ocean_persona"):
                row[key] = _parse_optional_literal(row.get(key, ""))
            rows.append(row)
            if truncate > 0 and len(rows) >= truncate:
                break
    return rows


def build_theory_error_user_prompt(
    row: dict[str, Any],
    student_turn_text: str,
    turn_label: str,
) -> str:
    question_block = str(row.get("question", "") or "").strip()
    prompt_stub = str(row.get("prompt", "") or "").strip()
    question_annotation = row.get("question_annotation")
    official_solution_lines: list[str] = []
    if isinstance(question_annotation, dict):
        correct_option = question_annotation.get("correct_option")
        solution = str(question_annotation.get("solution", "") or "").strip()
        if correct_option:
            official_solution_lines.append(f"Correct option: {correct_option}")
        if solution:
            official_solution_lines.append(f"Official solution:\n{solution}")
    official_solution_block = "\n\n".join(official_solution_lines).strip()

    blocks = [
        f"Turn being coded: {turn_label}",
        "Question Context:",
        question_block,
        "Dialogue Context Up To This Turn:",
        prompt_stub,
    ]
    if official_solution_block:
        blocks.extend(
            [
                "Official Solution Context:",
                official_solution_block,
            ]
        )
    blocks.extend(
        [
            "Current Student Turn:",
            str(student_turn_text or "").strip(),
            (
                "Task: Decide whether this student turn contains a substantive "
                "codable mathematical error. If yes, code it using the three "
                "theory-grounded frameworks exactly as instructed in the system prompt."
            ),
        ]
    )
    return "\n\n".join(blocks).strip()


def evaluate_theory_error_rows(
    rows: list[dict[str, Any]],
    llm_config: LLMConfig,
    max_concurrency: int,
) -> list[dict[str, Any]]:
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be > 0")
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_map = {
            executor.submit(_evaluate_single_row, row, llm_config): row
            for row in rows
        }
        for future in as_completed(future_map):
            records.append(future.result())
    records.sort(
        key=lambda row: (
            _safe_int(row["dialogue_idx"]),
            _safe_int(row["turn_idx"]),
            str(row["key"]),
        )
    )
    return records


def build_theory_error_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful_records = [row for row in records if not bool(row.get("judge_failed"))]
    failed_records = [row for row in records if bool(row.get("judge_failed"))]
    gold_official_incorrect = [row for row in records if bool(row["gold_officially_incorrect"])]
    gold_codable = [
        row for row in successful_records if bool(row["gold_has_codable_math_error"])
    ]
    denominator = len(gold_codable)
    knowledge_matches = sum(1 for row in gold_codable if bool(row["same_knowledge_type"]))
    locus_matches = sum(1 for row in gold_codable if bool(row["same_error_locus"]))
    mechanism_matches = sum(1 for row in gold_codable if bool(row["same_error_mechanism"]))
    pred_codable_given_gold_codable = sum(
        1 for row in gold_codable if bool(row["pred_has_codable_math_error"])
    )

    gold_knowledge_counter = Counter(
        str(row["gold_code"]["knowledge_type"]) for row in gold_codable
    )
    gold_locus_counter = Counter(
        str(row["gold_code"]["error_locus"]) for row in gold_codable
    )
    gold_mechanism_counter = Counter(
        str(row["gold_code"]["error_mechanism"]) for row in gold_codable
    )

    return {
        "theory_sources": THEORY_SOURCE_NOTES,
        "n_evaluated_rows": len(records),
        "n_successful_rows": len(successful_records),
        "n_failed_rows": len(failed_records),
        "row_success_rate": _ratio(len(successful_records), len(records)),
        "n_gold_officially_incorrect_rows": len(gold_official_incorrect),
        "n_gold_codable_math_error_rows": denominator,
        "n_pred_codable_given_gold_codable": pred_codable_given_gold_codable,
        "pred_codable_given_gold_codable_rate": _ratio(
            pred_codable_given_gold_codable,
            denominator,
        ),
        "n_gold_code_failures": sum(
            1 for row in records if str(row.get("gold_judge_error", "")).strip()
        ),
        "n_pred_code_failures": sum(
            1 for row in records if str(row.get("pred_judge_error", "")).strip()
        ),
        "knowledge_type_match_rate": {
            "count": knowledge_matches,
            "denominator": denominator,
            "rate": _ratio(knowledge_matches, denominator),
        },
        "error_locus_match_rate": {
            "count": locus_matches,
            "denominator": denominator,
            "rate": _ratio(locus_matches, denominator),
        },
        "error_mechanism_match_rate": {
            "count": mechanism_matches,
            "denominator": denominator,
            "rate": _ratio(mechanism_matches, denominator),
        },
        "gold_label_distributions": {
            "knowledge_type": dict(gold_knowledge_counter),
            "error_locus": dict(gold_locus_counter),
            "error_mechanism": dict(gold_mechanism_counter),
        },
    }


def write_theory_error_outputs(
    output_dir: Path,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "theory_error_judgments.jsonl", records)
    write_json(output_dir / "theory_error_summary.json", summary)
    _write_results_csv(output_dir / "theory_error_results.csv", records)
    (output_dir / "theory_error_summary.md").write_text(
        _render_summary_markdown(summary),
        encoding="utf-8",
    )


def _evaluate_single_row(
    row: dict[str, Any],
    llm_config: LLMConfig,
) -> dict[str, Any]:
    client = OpenAICompatClient(llm_config)
    gold_officially_incorrect = _gold_turn_is_officially_incorrect(row)
    gold_code, gold_judge_error = _code_turn_or_error(
        client=client,
        row=row,
        student_turn_text=str(row.get("gt_turn", "") or ""),
        turn_label="ground_truth_student_turn",
    )
    pred_code, pred_judge_error = _code_turn_or_error(
        client=client,
        row=row,
        student_turn_text=str(row.get("pred_turn", "") or ""),
        turn_label="candidate_student_turn",
    )
    judge_failed = gold_code is None or pred_code is None
    same_knowledge_type: bool | None = False
    same_error_locus: bool | None = False
    same_error_mechanism: bool | None = False
    if judge_failed:
        same_knowledge_type = None
        same_error_locus = None
        same_error_mechanism = None
    elif gold_code.has_codable_math_error:
        same_knowledge_type = (
            pred_code.has_codable_math_error
            and gold_code.knowledge_type == pred_code.knowledge_type
        )
        same_error_locus = (
            pred_code.has_codable_math_error
            and gold_code.error_locus == pred_code.error_locus
        )
        same_error_mechanism = (
            pred_code.has_codable_math_error
            and gold_code.error_mechanism == pred_code.error_mechanism
        )
    return {
        "key": str(row.get("key", "") or ""),
        "dialogue_idx": int(row["dialogue_idx"]),
        "turn_idx": int(row["turn_idx"]),
        "gold_officially_incorrect": gold_officially_incorrect,
        "judge_failed": judge_failed,
        "gold_judge_error": gold_judge_error,
        "pred_judge_error": pred_judge_error,
        "gt_turn": str(row.get("gt_turn", "") or ""),
        "pred_turn": str(row.get("pred_turn", "") or ""),
        "gold_has_codable_math_error": (
            None if gold_code is None else gold_code.has_codable_math_error
        ),
        "pred_has_codable_math_error": (
            None if pred_code is None else pred_code.has_codable_math_error
        ),
        "same_knowledge_type": same_knowledge_type,
        "same_error_locus": same_error_locus,
        "same_error_mechanism": same_error_mechanism,
        "gold_code": None if gold_code is None else _code_to_dict(gold_code),
        "pred_code": None if pred_code is None else _code_to_dict(pred_code),
    }


def _code_turn(
    client: OpenAICompatClient,
    row: dict[str, Any],
    student_turn_text: str,
    turn_label: str,
) -> TheoryErrorCode:
    user_prompt = build_theory_error_user_prompt(
        row=row,
        student_turn_text=student_turn_text,
        turn_label=turn_label,
    )
    raw = client.chat_json(
        system_prompt=CODER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    try:
        return _validate_theory_error_code(raw)
    except ValueError as exc:
        repaired = client.retry_schema_json(
            system_prompt=CODER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            previous_reply=raw,
            validation_error=(
                f"{exc}\n\n{THEORY_ERROR_OUTPUT_SCHEMA}"
            ),
        )
        try:
            return _validate_theory_error_code(repaired)
        except ValueError as second_exc:
            final_raw = client.chat_json(
                system_prompt=CODER_SYSTEM_PROMPT,
                user_prompt=(
                    user_prompt
                    + "\n\nReturn JSON using this exact schema:\n"
                    + THEORY_ERROR_OUTPUT_SCHEMA
                ),
            )
            try:
                return _validate_theory_error_code(final_raw)
            except ValueError as third_exc:
                raise ValueError(
                    "theory error judge schema validation failed after explicit retries: "
                    f"first={exc}; second={second_exc}; third={third_exc}"
                ) from third_exc


def _code_turn_or_error(
    client: OpenAICompatClient,
    row: dict[str, Any],
    student_turn_text: str,
    turn_label: str,
) -> tuple[TheoryErrorCode | None, str]:
    try:
        return (
            _code_turn(
                client=client,
                row=row,
                student_turn_text=student_turn_text,
                turn_label=turn_label,
            ),
            "",
        )
    except Exception as exc:
        return None, _truncate_error_message(str(exc))


def _validate_theory_error_code(raw: object) -> TheoryErrorCode:
    obj = _require_dict(raw, "theory error code")
    required_keys = {
        "has_codable_math_error",
        "knowledge_type",
        "error_locus",
        "error_mechanism",
        "evidence",
    }
    got_keys = set(obj)
    if got_keys != required_keys:
        missing = sorted(required_keys - got_keys)
        extra = sorted(got_keys - required_keys)
        raise ValueError(
            f"theory error code keys mismatch: missing={missing}, extra={extra}"
        )
    has_codable = _coerce_bool(obj["has_codable_math_error"], "has_codable_math_error")
    evidence = _coerce_string_list(obj["evidence"], "evidence")
    if not evidence:
        raise ValueError("evidence must contain at least one item")
    if not has_codable:
        if obj["knowledge_type"] is not None:
            raise ValueError("knowledge_type must be null when has_codable_math_error=false")
        if obj["error_locus"] is not None:
            raise ValueError("error_locus must be null when has_codable_math_error=false")
        if obj["error_mechanism"] is not None:
            raise ValueError("error_mechanism must be null when has_codable_math_error=false")
        return TheoryErrorCode(
            has_codable_math_error=False,
            knowledge_type=None,
            error_locus=None,
            error_mechanism=None,
            evidence=evidence,
        )
    knowledge_type = _coerce_enum(
        obj["knowledge_type"],
        KNOWLEDGE_TYPES,
        "knowledge_type",
    )
    error_locus = _coerce_enum(
        obj["error_locus"],
        ERROR_LOCI,
        "error_locus",
    )
    error_mechanism = _coerce_enum(
        obj["error_mechanism"],
        ERROR_MECHANISMS,
        "error_mechanism",
    )
    return TheoryErrorCode(
        has_codable_math_error=True,
        knowledge_type=knowledge_type,
        error_locus=error_locus,
        error_mechanism=error_mechanism,
        evidence=evidence,
    )


def _code_to_dict(code: TheoryErrorCode) -> dict[str, Any]:
    return {
        "has_codable_math_error": code.has_codable_math_error,
        "knowledge_type": code.knowledge_type,
        "error_locus": code.error_locus,
        "error_mechanism": code.error_mechanism,
        "evidence": list(code.evidence),
    }


def _gold_turn_is_officially_incorrect(row: dict[str, Any]) -> bool:
    correctness = row.get("correctness")
    if not isinstance(correctness, dict):
        return False
    turn_key = f"turn {int(row['turn_idx']) + 1}"
    turn_entry = correctness.get(turn_key)
    if not isinstance(turn_entry, dict):
        return False
    return turn_entry.get("correct") is False


__all__ = [
    "build_theory_error_summary",
    "evaluate_theory_error_rows",
    "load_theory_error_rows",
    "write_theory_error_outputs",
    "_gold_turn_is_officially_incorrect",
]


def _parse_optional_literal(raw: object) -> object:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return literal_eval(text)
    except (SyntaxError, ValueError):
        return raw


def _require_dict(raw: object, context_name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{context_name} must be a JSON object")
    return raw


def _coerce_bool(raw: object, field_name: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"{field_name} must be boolean, got {raw!r}")
    return raw


def _coerce_enum(raw: object, allowed: tuple[str, ...], field_name: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{field_name} must be a string enum, got {raw!r}")
    value = raw.strip()
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )
    return value


def _coerce_string_list(raw: object, field_name: str) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list of strings")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must contain only strings, got {item!r}")
        text = item.strip()
        if not text:
            raise ValueError(f"{field_name} cannot contain empty strings")
        values.append(text)
    return values


def _ratio(count: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return count / denominator


def _safe_int(raw: object) -> int:
    try:
        return int(raw)
    except Exception:
        return 0


def _write_results_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "key",
        "dialogue_idx",
        "turn_idx",
        "gold_officially_incorrect",
        "judge_failed",
        "gold_judge_error",
        "pred_judge_error",
        "gold_has_codable_math_error",
        "pred_has_codable_math_error",
        "same_knowledge_type",
        "same_error_locus",
        "same_error_mechanism",
        "gold_knowledge_type",
        "pred_knowledge_type",
        "gold_error_locus",
        "pred_error_locus",
        "gold_error_mechanism",
        "pred_error_mechanism",
        "gt_turn",
        "pred_turn",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(
                {
                    "key": row["key"],
                    "dialogue_idx": row["dialogue_idx"],
                    "turn_idx": row["turn_idx"],
                    "gold_officially_incorrect": row["gold_officially_incorrect"],
                    "judge_failed": row["judge_failed"],
                    "gold_judge_error": row["gold_judge_error"],
                    "pred_judge_error": row["pred_judge_error"],
                    "gold_has_codable_math_error": row["gold_has_codable_math_error"],
                    "pred_has_codable_math_error": row["pred_has_codable_math_error"],
                    "same_knowledge_type": row["same_knowledge_type"],
                    "same_error_locus": row["same_error_locus"],
                    "same_error_mechanism": row["same_error_mechanism"],
                    "gold_knowledge_type": _get_code_field(row["gold_code"], "knowledge_type"),
                    "pred_knowledge_type": _get_code_field(row["pred_code"], "knowledge_type"),
                    "gold_error_locus": _get_code_field(row["gold_code"], "error_locus"),
                    "pred_error_locus": _get_code_field(row["pred_code"], "error_locus"),
                    "gold_error_mechanism": _get_code_field(row["gold_code"], "error_mechanism"),
                    "pred_error_mechanism": _get_code_field(row["pred_code"], "error_mechanism"),
                    "gt_turn": row["gt_turn"],
                    "pred_turn": row["pred_turn"],
                }
            )


def _render_summary_markdown(summary: dict[str, Any]) -> str:
    def _fmt_rate(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:.4f}"

    lines = [
        "# Theory Error Eval Summary",
        "",
        "## Theory Sources",
        "",
        f"- Knowledge Type: {summary['theory_sources']['knowledge_type']}",
        f"- Error Locus: {summary['theory_sources']['error_locus']}",
        f"- Error Mechanism: {summary['theory_sources']['error_mechanism']}",
        "",
        "## Coverage",
        "",
        f"- Evaluated rows: {summary['n_evaluated_rows']}",
        f"- Successful judge rows: {summary['n_successful_rows']} ({_fmt_rate(summary['row_success_rate'])})",
        f"- Failed judge rows: {summary['n_failed_rows']}",
        f"- Gold-side judge failures: {summary['n_gold_code_failures']}",
        f"- Pred-side judge failures: {summary['n_pred_code_failures']}",
        (
            "- Gold officially incorrect rows included in evaluation: "
            f"{summary['n_gold_officially_incorrect_rows']}"
        ),
        f"- Gold codable math-error rows: {summary['n_gold_codable_math_error_rows']}",
        (
            "- Pred codable given gold codable: "
            f"{summary['n_pred_codable_given_gold_codable']} "
            f"({_fmt_rate(summary['pred_codable_given_gold_codable_rate'])})"
        ),
        "",
        "## Match Rates",
        "",
        "| Metric | Count | Denominator | Rate |",
        "| --- | ---: | ---: | ---: |",
        (
            f"| Knowledge Type | {summary['knowledge_type_match_rate']['count']} | "
            f"{summary['knowledge_type_match_rate']['denominator']} | "
            f"{_fmt_rate(summary['knowledge_type_match_rate']['rate'])} |"
        ),
        (
            f"| Error Locus | {summary['error_locus_match_rate']['count']} | "
            f"{summary['error_locus_match_rate']['denominator']} | "
            f"{_fmt_rate(summary['error_locus_match_rate']['rate'])} |"
        ),
        (
            f"| Error Mechanism | {summary['error_mechanism_match_rate']['count']} | "
            f"{summary['error_mechanism_match_rate']['denominator']} | "
            f"{_fmt_rate(summary['error_mechanism_match_rate']['rate'])} |"
        ),
        "",
        "## Gold Label Distributions",
        "",
        f"- Knowledge Type: {json.dumps(summary['gold_label_distributions']['knowledge_type'], ensure_ascii=False)}",
        f"- Error Locus: {json.dumps(summary['gold_label_distributions']['error_locus'], ensure_ascii=False)}",
        f"- Error Mechanism: {json.dumps(summary['gold_label_distributions']['error_mechanism'], ensure_ascii=False)}",
        "",
    ]
    return "\n".join(lines)


def _get_code_field(code: dict[str, Any] | None, field_name: str) -> object:
    if not isinstance(code, dict):
        return None
    return code.get(field_name)


def _truncate_error_message(message: str, limit: int = 800) -> str:
    text = str(message or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"
