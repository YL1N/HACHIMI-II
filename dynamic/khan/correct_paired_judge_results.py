from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any


CORRECT_VALUE_PATTERNS = (
    "answer is correct in value",
    "answer is correct",
    "which is correct",
    "is mathematically correct",
    "mathematically correct",
    "correctly computes",
    "correctly computed",
    "correctly converts",
    "correctly converted",
    "correctly identifies",
    "correctly identified",
    "correctly states",
    "correctly stated",
)

PROTOCOL_MISMATCH_NOT_CODABLE_PATTERNS = (
    "gave final answer instead of",
    "gives final answer instead of",
    "gave the final answer instead of",
    "gives the final answer instead of",
    "final solution instead of",
    "final answer without",
    "without showing",
    "instead of the requested",
    "did not compute the actual",
    "does not compute the actual",
    "did not provide",
    "does not provide",
    "does not state",
    "did not state",
    "asks for clarification",
    "asks for help",
    "asks for a problem",
    "says 'yes'",
    "said 'yes'",
    "responds 'yes'",
    "only affirms",
    "asks a question instead of",
    "asks for confirmation instead of",
)

CONTRADICTION_GUARDS = (
    "incorrectly",
    "not correctly",
    "not correct",
    "which is incorrect",
    "is incorrect",
    "wrong",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def correct_row(
    row: dict[str, Any],
    manual_audit_by_sample_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    corrected = copy.deepcopy(row)
    reasons: list[str] = []

    manual_audit = None
    if manual_audit_by_sample_id:
        sample_id = str(corrected.get("sample_id") or "")
        manual_audit = manual_audit_by_sample_id.get(sample_id)

    for side in ("real", "candidate"):
        reasons.extend(_apply_side_text_rules(corrected, side))

    if manual_audit is not None:
        reasons.extend(_apply_manual_audit(corrected, manual_audit))

    _enforce_consistency(corrected)
    corrected["correction_reasons"] = sorted(set(reasons))
    corrected["judge_corrected"] = bool(reasons)
    return corrected


def _apply_side_text_rules(row: dict[str, Any], side: str) -> list[str]:
    reasons: list[str] = []
    evidence = str(row.get(f"{side}_evidence") or "")
    evidence_lower = evidence.lower()

    if _has_correct_value_signal(evidence_lower):
        if row.get(f"{side}_function") == "incorrect":
            row[f"{side}_function"] = "correct"
            row[f"{side}_satisfies_criterion"] = True
            reasons.append(f"{side}:equivalent_or_correct_value")
        if row.get(f"{side}_has_codable_error") is True:
            _clear_error_code(row, side)
            reasons.append(f"{side}:equivalent_or_correct_value")
        return reasons

    if any(pattern in evidence_lower for pattern in PROTOCOL_MISMATCH_NOT_CODABLE_PATTERNS):
        if row.get(f"{side}_has_codable_error") is True:
            _clear_error_code(row, side)
            reasons.append(f"{side}:local_protocol_mismatch_not_codable_math_error")

    return reasons


def _has_correct_value_signal(evidence_lower: str) -> bool:
    if not any(pattern in evidence_lower for pattern in CORRECT_VALUE_PATTERNS):
        return False
    if any(pattern in evidence_lower for pattern in CONTRADICTION_GUARDS):
        return False
    return True


def _apply_manual_audit(row: dict[str, Any], manual_audit: dict[str, Any]) -> list[str]:
    category = str(manual_audit.get("category") or "")
    note = str(manual_audit.get("note") or "").lower()
    reasons: list[str] = []

    if category == "judge_noise_denominator":
        if row.get("real_has_codable_error") is True:
            _clear_error_code(row, "real")
            reasons.append("manual:real_denominator_not_codable")
        if any(
            phrase in note
            for phrase in (
                "correct",
                "equivalent",
                "mathematically valid",
                "real is correct",
            )
        ):
            row["real_function"] = "correct"
            row["real_satisfies_criterion"] = True
            reasons.append("manual:real_function_correct")
    elif category == "judge_noise_candidate":
        if row.get("candidate_has_codable_error") is True:
            _clear_error_code(row, "candidate")
            reasons.append("manual:candidate_not_codable")
        if "candidate answer" in note and "correct" in note:
            row["candidate_function"] = "correct"
            row["candidate_satisfies_criterion"] = True
            reasons.append("manual:candidate_function_correct")
    elif category == "ambiguous":
        row["manual_audit_ambiguous"] = True
        reasons.append("manual:ambiguous_no_field_change")

    return reasons


def _clear_error_code(row: dict[str, Any], side: str) -> None:
    row[f"{side}_has_codable_error"] = False
    row[f"{side}_knowledge_type"] = None
    row[f"{side}_error_locus"] = None
    row[f"{side}_error_mechanism"] = None


def _enforce_consistency(row: dict[str, Any]) -> None:
    for side in ("real", "candidate"):
        if row.get(f"{side}_function") != "incorrect":
            _clear_error_code(row, side)
        if row.get(f"{side}_has_codable_error") is not True:
            _clear_error_code(row, side)

    both_error = bool(row.get("real_has_codable_error")) and bool(row.get("candidate_has_codable_error"))
    row["both_have_codable_error"] = both_error
    row["same_function"] = row.get("real_function") == row.get("candidate_function")

    if both_error:
        row["same_knowledge"] = (
            row.get("real_knowledge_type") == row.get("candidate_knowledge_type")
            and row.get("real_knowledge_type") is not None
        )
        row["same_locus"] = (
            row.get("real_error_locus") == row.get("candidate_error_locus")
            and row.get("real_error_locus") is not None
        )
        row["same_mechanism"] = (
            row.get("real_error_mechanism") == row.get("candidate_error_mechanism")
            and row.get("real_error_mechanism") is not None
        )
    else:
        row["same_knowledge"] = None
        row["same_locus"] = None
        row["same_mechanism"] = None


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "n_rows": len(rows),
        "by_mode": {},
    }
    for mode in sorted({str(row.get("mode") or "simulation") for row in rows}):
        mode_rows = [row for row in rows if str(row.get("mode") or "simulation") == mode]
        same_count = sum(1 for row in mode_rows if bool(row.get("same_function")))
        real_error_rows = [row for row in mode_rows if bool(row.get("real_has_codable_error"))]
        candidate_error_rows = [row for row in mode_rows if bool(row.get("candidate_has_codable_error"))]
        both_error_rows = [row for row in mode_rows if bool(row.get("both_have_codable_error"))]
        summary["by_mode"][mode] = {
            "n": len(mode_rows),
            "same_function_count": same_count,
            "same_function_rate": _ratio(same_count, len(mode_rows)),
            "real_function_counts": _counts(row.get("real_function") for row in mode_rows),
            "candidate_function_counts": _counts(row.get("candidate_function") for row in mode_rows),
            "real_codable_error_n": len(real_error_rows),
            "candidate_codable_error_n": len(candidate_error_rows),
            "both_codable_error_n": len(both_error_rows),
            "error_realization_rate": _ratio(len(both_error_rows), len(real_error_rows)),
            "same_knowledge_rate": _nullable_bool_rate(row.get("same_knowledge") for row in both_error_rows),
            "same_locus_rate": _nullable_bool_rate(row.get("same_locus") for row in both_error_rows),
            "same_mechanism_rate": _nullable_bool_rate(row.get("same_mechanism") for row in both_error_rows),
        }
    return summary


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _counts(values: Any) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for value in values:
        counter[str(value)] += 1
    return dict(counter)


def _nullable_bool_rate(values: Any) -> float | None:
    kept = [value for value in values if value is not None]
    if not kept:
        return None
    return sum(1 for value in kept if bool(value)) / len(kept)


def load_manual_audit(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("manual audit file must contain a JSON list")
    result: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("manual audit item must be a JSON object")
        sample_id = str(item.get("sample_id") or "")
        manual_audit = item.get("manual_audit")
        if sample_id and isinstance(manual_audit, dict):
            result[sample_id] = manual_audit
    return result


def build_correction_summary(original_rows: list[dict[str, Any]], corrected_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(original_rows) != len(corrected_rows):
        raise ValueError("original and corrected row counts differ")

    changed_rows = [
        (original, corrected)
        for original, corrected in zip(original_rows, corrected_rows)
        if bool(corrected.get("judge_corrected"))
    ]
    reason_counter: Counter[str] = Counter()
    field_counter: Counter[str] = Counter()
    for original, corrected in changed_rows:
        reason_counter.update(corrected.get("correction_reasons") or [])
        for field in (
            "real_function",
            "candidate_function",
            "real_has_codable_error",
            "candidate_has_codable_error",
            "both_have_codable_error",
            "same_function",
        ):
            if original.get(field) != corrected.get(field):
                field_counter[field] += 1

    return {
        "n_rows": len(original_rows),
        "n_corrected_rows": len(changed_rows),
        "correction_reasons": dict(reason_counter),
        "changed_fields": dict(field_counter),
        "original_summary": summarize_rows(original_rows),
        "corrected_summary": summarize_rows(corrected_rows),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    original = summary["original_summary"]["by_mode"]["simulation"]
    corrected = summary["corrected_summary"]["by_mode"]["simulation"]

    def fmt(value: Any) -> str:
        if value is None:
            return "NA"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    rows = [
        ("same_function_rate", original["same_function_rate"], corrected["same_function_rate"]),
        ("error_realization_rate", original["error_realization_rate"], corrected["error_realization_rate"]),
        ("same_knowledge_rate", original["same_knowledge_rate"], corrected["same_knowledge_rate"]),
        ("same_locus_rate", original["same_locus_rate"], corrected["same_locus_rate"]),
        ("same_mechanism_rate", original["same_mechanism_rate"], corrected["same_mechanism_rate"]),
        ("real_codable_error_n", original["real_codable_error_n"], corrected["real_codable_error_n"]),
        ("candidate_codable_error_n", original["candidate_codable_error_n"], corrected["candidate_codable_error_n"]),
        ("both_codable_error_n", original["both_codable_error_n"], corrected["both_codable_error_n"]),
    ]
    lines = [
        "# Corrected Khan Paired Judge Summary",
        "",
        f"- Rows: `{summary['n_rows']}`",
        f"- Corrected rows: `{summary['n_corrected_rows']}`",
        "",
        "| metric | original | corrected |",
        "|---|---:|---:|",
    ]
    for name, before, after in rows:
        lines.append(f"| `{name}` | `{fmt(before)}` | `{fmt(after)}` |")
    lines.extend(
        [
            "",
            "## Correction Reasons",
            "",
            "| reason | count |",
            "|---|---:|",
        ]
    )
    for reason, count in sorted(summary["correction_reasons"].items()):
        lines.append(f"| `{reason}` | `{count}` |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply deterministic manual-audit corrections to Khan paired judge rows.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output_dir", type=Path, required=True)
    parser.add_argument("--manual_audit", type=Path, default=None)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    manual = load_manual_audit(args.manual_audit)
    corrected = [correct_row(row, manual) for row in rows]
    summary = build_correction_summary(rows, corrected)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "corrected_paired_judge_rows.jsonl", corrected)
    write_jsonl(
        args.output_dir / "correction_log.jsonl",
        [row for row in corrected if bool(row.get("judge_corrected"))],
    )
    (args.output_dir / "corrected_summary.json").write_text(
        json.dumps(summary["corrected_summary"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "correction_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "corrected_vs_original.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
