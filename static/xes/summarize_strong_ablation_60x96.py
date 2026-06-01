from __future__ import annotations

import argparse
import json
from pathlib import Path


VARIANT_ORDER = [
    "baseline_hachimi_state_step",
    "history_only_state_step",
    "hachimi_direct",
    "hachimi_state_single",
    "hachimi_no_difficulty_anchor",
    "hachimi_third_person_response",
    "history_only_direct",
    "history_only_state_single",
    "history_only_no_difficulty_anchor",
    "hachimi_direct_no_difficulty_anchor",
    "hachimi_state_single_no_difficulty_anchor",
    "history_only_direct_no_difficulty_anchor",
    "hachimi_no_real_difficulty_band",
    "hachimi_no_difficulty_signal",
    "hachimi_no_difficulty_signal_no_internal_signals",
    "hachimi_no_difficulty_signal_minimal_signals",
    "hachimi_no_difficulty_signal_student_capability_only",
    "hachimi_no_difficulty_signal_student_no_psych_fields",
    "hachimi_no_difficulty_signal_student_no_style_fields",
    "hachimi_no_difficulty_signal_problem_core_only",
    "hachimi_no_difficulty_signal_no_problem_justifications",
    "hachimi_no_difficulty_signal_no_problem_notes",
    "hachimi_no_difficulty_signal_no_interaction_decision",
    "hachimi_no_difficulty_signal_item_state_label_only",
    "hachimi_no_difficulty_signal_loose_constraints",
]


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _latest_run_dir(variant_dir: Path) -> Path:
    candidates = sorted(
        [path for path in variant_dir.iterdir() if path.is_dir() and path.name.startswith("run_")],
        key=lambda path: path.name,
    )
    if not candidates:
        raise FileNotFoundError(f"no run_* dir found under {variant_dir}")
    return candidates[-1]


def _metric(payload: dict[str, object], path: list[str]) -> object:
    value: object = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _fmt(value: object) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _row_for_variant(output_root: Path, variant: str) -> dict[str, object]:
    run_dir = _latest_run_dir(output_root / variant)
    metrics = _load_json(run_dir / "metrics.json")
    common = metrics.get("common_test_metrics", {})
    if not isinstance(common, dict):
        common = {}
    layer2 = metrics.get("layer2_item_difficulty_alignment", {})
    if not isinstance(layer2, dict):
        layer2 = {}
    layer4 = metrics.get("layer4_student_difference_alignment", {})
    if not isinstance(layer4, dict):
        layer4 = {}
    return {
        "variant": variant,
        "run_dir": str(run_dir),
        "acc": common.get("overall_accuracy"),
        "real_acc": common.get("real_overall_accuracy"),
        "consistency": common.get("consistency_mean"),
        "item_P": layer2.get("pearson"),
        "item_S": layer2.get("spearman"),
        "student_P": layer4.get("student_accuracy_pearson"),
        "student_S": layer4.get("student_accuracy_spearman"),
        "failure_rate": common.get("failure_rate"),
    }


def _markdown_table(rows: list[dict[str, object]]) -> str:
    headers = [
        "variant",
        "acc",
        "consistency",
        "item_P",
        "item_S",
        "student_P",
        "student_S",
        "failure_rate",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(header)) for header in headers) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize XES strong harness ablation runs.")
    parser.add_argument(
        "--output_root",
        default="static/xes/outputs/xes_strong_ablation_60x96_20260512",
    )
    parser.add_argument(
        "--output_report",
        default="static/xes/reports/xes_strong_ablation_results_20260512.md",
    )
    args = parser.parse_args()

    output_root = Path(args.output_root)
    rows = [
        _row_for_variant(output_root, variant)
        for variant in VARIANT_ORDER
        if (output_root / variant).exists()
    ]
    if not rows:
        raise ValueError(f"no ablation variant outputs found under {output_root}")

    baseline = next((row for row in rows if row["variant"] == "baseline_hachimi_state_step"), None)
    lines = [
        "# XES strong harness ablation results",
        "",
        "## Core metrics",
        "",
        _markdown_table(rows),
        "",
    ]
    if baseline is not None:
        base_consistency = baseline.get("consistency")
        lines.extend(["## Delta vs baseline", ""])
        lines.append("| variant | delta_consistency | delta_item_P | delta_student_P |")
        lines.append("|---|---|---|---|")
        for row in rows:
            def delta(key: str) -> object:
                current = row.get(key)
                base = baseline.get(key)
                if isinstance(current, (int, float)) and isinstance(base, (int, float)):
                    return float(current) - float(base)
                return None
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row["variant"]),
                        _fmt(delta("consistency")),
                        _fmt(delta("item_P")),
                        _fmt(delta("student_P")),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(["## Run dirs", ""])
    for row in rows:
        lines.append(f"- `{row['variant']}`: `{row['run_dir']}`")
    lines.append("")

    report_path = Path(args.output_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
