from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.runtime_paths import XES_OUTPUTS_DIR, XES_ROOT


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def resolve_xes_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (XES_ROOT / path).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a difficulty-agnostic base item pool from an eligible XES question set."
    )
    parser.add_argument(
        "--eligible_question_path",
        type=str,
        required=True,
        help="Path to eligible_questions.json from the support filter run.",
    )
    parser.add_argument(
        "--support_summary_path",
        type=str,
        default="",
        help="Optional path to summary.json from the same support filter run.",
    )
    parser.add_argument(
        "--output_root",
        type=str,
        default=str(XES_OUTPUTS_DIR / "base_item_pool"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    eligible_question_path = resolve_xes_path(args.eligible_question_path)
    support_summary_path = resolve_xes_path(args.support_summary_path) if args.support_summary_path else None

    eligible_questions = json.loads(eligible_question_path.read_text(encoding="utf-8"))
    if not isinstance(eligible_questions, list):
        raise ValueError("eligible question file must be a JSON list")
    if not eligible_questions:
        raise ValueError("eligible question file is empty")

    support_summary = None
    if support_summary_path is not None:
        support_summary = json.loads(support_summary_path.read_text(encoding="utf-8"))
        if not isinstance(support_summary, dict):
            raise ValueError("support summary file must be a JSON dict")

    item_rows: list[dict[str, object]] = []
    module_counter = Counter()
    route_top_counter = Counter()
    question_type_counter = Counter()
    for row in eligible_questions:
        primary_route_top = row.get("primary_route_top")
        primary_route_module = row.get("primary_route_module")
        module_name = (
            f"{primary_route_top} / {primary_route_module}"
            if primary_route_top and primary_route_module
            else "unknown / unknown"
        )
        module_counter[module_name] += 1
        route_top_counter[str(primary_route_top)] += 1
        question_type_counter[str(row.get("question_type"))] += 1
        level_counts = row.get("irt_support_level_counts") or {}
        item_rows.append(
            {
                "question_id": str(row["question_id"]),
                "question_type": row["question_type"],
                "question_text": row["question_text"],
                "options": row["options"],
                "gold_answers": row["gold_answers"],
                "has_options": bool(row["has_options"]),
                "irt_support_total": int(row["irt_support_total"]),
                "irt_support_accuracy": float(row["irt_support_accuracy"]),
                "irt_support_high_count": int(level_counts.get("high", 0)),
                "irt_support_medium_count": int(level_counts.get("medium", 0)),
                "irt_support_low_count": int(level_counts.get("low", 0)),
                "irt_support_poor_count": int(level_counts.get("poor", 0)),
                "irt_support_max_level_share": float(row["irt_support_max_level_share"]),
                "irt_support_distribution_l1": float(row["irt_support_distribution_l1"]),
                "primary_route_top": primary_route_top,
                "primary_route_module": primary_route_module,
                "module_name": module_name,
            }
        )

    item_rows.sort(key=lambda row: row["question_id"])
    module_rows = [
        {"module_name": module_name, "n_items": count}
        for module_name, count in module_counter.most_common()
    ]

    summary = {
        "source_eligible_question_path": str(eligible_question_path),
        "source_support_summary_path": str(support_summary_path) if support_summary_path is not None else "",
        "base_item_count": len(item_rows),
        "module_count": len(module_rows),
        "route_top_counts": dict(route_top_counter),
        "question_type_counts": dict(question_type_counter),
        "support_settings": support_summary.get("settings", {}) if support_summary is not None else {},
        "students_with_ability_level": support_summary.get("students_with_ability_level") if support_summary else None,
    }

    run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "summary.json", summary)
    write_json(run_dir / "base_item_pool.json", item_rows)
    write_csv(run_dir / "base_item_pool.csv", item_rows)
    write_csv(run_dir / "module_summary.csv", module_rows)

    print(f"Base item pool exported: {run_dir}")
    print(f"Items: {summary['base_item_count']}")
    print(f"Modules: {summary['module_count']}")


if __name__ == "__main__":
    main()
