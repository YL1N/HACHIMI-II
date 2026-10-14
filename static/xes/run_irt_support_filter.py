from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.irt_support import IRTSupportSettings, build_irt_support_dataset
from src.runtime_paths import XES_OUTPUTS_DIR, XES_REPORTS_DIR, resolve_xes_path as resolve_xes_runtime_path


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filter XES questions for later IRT calibration support."
    )
    parser.add_argument(
        "--question_path",
        type=str,
        default="../XES3G5M/metadata/questions.json",
        help="Path to questions.json, relative to xes root by default.",
    )
    parser.add_argument(
        "--response_csv_path",
        type=str,
        default="../XES3G5M/question_level/train_valid_sequences_quelevel.csv",
        help="Path to train/valid response csv, relative to xes root by default.",
    )
    parser.add_argument("--min_item_response_count", type=int, default=500)
    parser.add_argument("--min_student_unique_items", type=int, default=50)
    parser.add_argument("--min_level_response_count", type=int, default=100)
    parser.add_argument("--max_level_share", type=float, default=0.45)
    parser.add_argument("--max_distribution_l1", type=float, default=0.25)
    parser.add_argument(
        "--include_image_questions",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--output_root",
        type=str,
        default=str(XES_OUTPUTS_DIR / "irt_support"),
        help="Output directory for diagnostics.",
    )
    return parser


def resolve_xes_path(raw_path: str) -> Path:
    return resolve_xes_runtime_path(raw_path)


def main() -> None:
    args = build_parser().parse_args()
    settings = IRTSupportSettings(
        min_item_response_count=args.min_item_response_count,
        min_student_unique_items=args.min_student_unique_items,
        min_level_response_count=args.min_level_response_count,
        max_level_share=args.max_level_share,
        max_distribution_l1=args.max_distribution_l1,
        include_image_questions=args.include_image_questions,
    )

    result = build_irt_support_dataset(
        question_path=resolve_xes_path(args.question_path),
        response_csv_path=resolve_xes_path(args.response_csv_path),
        settings=settings,
    )

    run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)

    write_json(run_dir / "summary.json", result.summary)
    write_json(run_dir / "eligible_questions.json", result.eligible_questions)
    write_json(
        run_dir / "item_diagnostics.json",
        [asdict(diagnostic) for diagnostic in result.item_diagnostics],
    )

    print(f"IRT support filter completed: {run_dir}")
    print(f"Eligible items: {result.summary['eligible_item_count']}")
    print(f"Candidate items: {result.summary['candidate_item_count']}")
    print(f"Students with ability level: {result.summary['students_with_ability_level']}")
    print(f"Failure reasons: {result.summary['failure_reason_counts']}")


if __name__ == "__main__":
    main()
