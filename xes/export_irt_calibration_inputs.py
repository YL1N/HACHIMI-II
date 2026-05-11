from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from src.irt_support import export_irt_calibration_dataset
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
        for row in rows:
            writer.writerow(row)


def resolve_xes_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (XES_ROOT / path).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export cleaned IRT calibration inputs from a filtered XES item pool."
    )
    parser.add_argument(
        "--question_path",
        type=str,
        default="../XES3G5M/metadata/questions.json",
    )
    parser.add_argument(
        "--response_csv_path",
        type=str,
        default="../XES3G5M/question_level/train_valid_sequences_quelevel.csv",
    )
    parser.add_argument(
        "--eligible_question_path",
        type=str,
        required=True,
        help="Path to eligible_questions.json from the support filter run.",
    )
    parser.add_argument("--min_student_unique_items", type=int, default=50)
    parser.add_argument(
        "--include_image_questions",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--output_root",
        type=str,
        default=str(XES_OUTPUTS_DIR / "irt_calibration_inputs"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    export = export_irt_calibration_dataset(
        question_path=resolve_xes_path(args.question_path),
        response_csv_path=resolve_xes_path(args.response_csv_path),
        eligible_question_path=resolve_xes_path(args.eligible_question_path),
        min_student_unique_items=args.min_student_unique_items,
        include_image_questions=args.include_image_questions,
    )

    run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)

    write_json(run_dir / "summary.json", export.summary)
    write_csv(run_dir / "student_ability.csv", export.student_ability_rows)
    write_json(run_dir / "item_pool.json", export.item_pool_rows)
    write_csv(run_dir / "responses_long.csv", export.response_rows)
    write_csv(run_dir / "module_summary.csv", export.module_summary_rows)

    print(f"IRT calibration inputs exported: {run_dir}")
    print(f"Students: {export.summary['n_students_in_export']}")
    print(f"Items: {export.summary['n_items_in_export']}")
    print(f"Responses: {export.summary['n_responses_in_export']}")
    print(f"Modules: {export.summary['n_modules_in_export']}")


if __name__ == "__main__":
    main()
