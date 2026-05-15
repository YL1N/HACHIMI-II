from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_metrics(summary: dict[str, object]) -> dict[str, object]:
    correctness = summary.get("correctness", {})
    same_error = summary.get("same_error", {})
    return {
        "consistency": correctness.get("match_rate"),
        "same_knowledge": same_error.get("same_knowledge_type_rate"),
        "same_locus": same_error.get("same_error_locus_rate"),
        "same_mechanism": same_error.get("same_error_mechanism_rate"),
        "error_realization": same_error.get("error_realization_rate"),
        "n_rows": summary.get("n_rows"),
        "n_correctness_rows": correctness.get("n_eligible_rows"),
        "n_theory_rows": same_error.get("n_theory_rows"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_root", type=str, required=True)
    args = parser.parse_args()

    root = Path(args.input_root)
    if not root.exists():
        raise FileNotFoundError(root)

    rows: list[dict[str, object]] = []
    for variant_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        summary_path = variant_dir / "detached_eval_5metrics" / "detached_eval_summary.json"
        metrics_path = variant_dir / "metrics.json"
        resolved_args_path = variant_dir / "resolved_args.json"
        if not summary_path.exists():
            continue
        summary = _load_json(summary_path)
        metrics = _load_json(metrics_path) if metrics_path.exists() else {}
        resolved_args = _load_json(resolved_args_path) if resolved_args_path.exists() else {}
        row = {
            "variant": variant_dir.name,
            **_extract_metrics(summary),
            "n_generation_records": metrics.get("n_records"),
            "retries": metrics.get("retries"),
            "remaining_violations": metrics.get("remaining_violations"),
            "constraint_profile": resolved_args.get("constraint_profile"),
            "population_calibration_top_k": resolved_args.get("population_calibration_top_k"),
            "student_context_profile_mode": resolved_args.get("student_context_profile_mode"),
            "tutor_turn_profile_mode": resolved_args.get("tutor_turn_profile_mode"),
            "interaction_state_mode": resolved_args.get("interaction_state_mode"),
            "transition_prediction_mode": resolved_args.get("transition_prediction_mode"),
            "error_blueprint_mode": resolved_args.get("error_blueprint_mode"),
            "disable_llm_dynamic_violation_review": resolved_args.get(
                "disable_llm_dynamic_violation_review"
            ),
            "disable_generation_retry": resolved_args.get("disable_generation_retry"),
        }
        rows.append(row)

    output_json = root / "summary.json"
    output_md = root / "summary.md"
    output_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    headers = [
        "variant",
        "consistency",
        "same_knowledge",
        "same_locus",
        "same_mechanism",
        "error_realization",
        "retries",
        "remaining_violations",
    ]
    md_lines = ["# EEDI strong revisit 1000 汇总", "", "| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        md_lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("variant", "")),
                    _fmt(row.get("consistency")),
                    _fmt(row.get("same_knowledge")),
                    _fmt(row.get("same_locus")),
                    _fmt(row.get("same_mechanism")),
                    _fmt(row.get("error_realization")),
                    str(row.get("retries", "")),
                    str(row.get("remaining_violations", "")),
                ]
            )
            + " |"
        )
    output_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(output_json)
    print(output_md)


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    main()
