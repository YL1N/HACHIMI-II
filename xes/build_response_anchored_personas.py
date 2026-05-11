from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.persona_anchoring import (
    AnchorBuildSettings,
    build_response_anchored_persona_rows,
    load_excluded_question_ids,
)
from src.runtime_paths import XES_OUTPUTS_DIR, XES_ROOT


DEFAULT_FROZEN_PATHS = [
    "outputs/principled_papers_frozen_questions/run_20260427_195718/Form_A_selected_questions.json",
    "outputs/principled_papers_frozen_questions/run_20260427_195718/Form_B_selected_questions.json",
    "outputs/principled_papers_frozen_questions/run_20260427_195718/Form_C_selected_questions.json",
]


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (XES_ROOT / path).resolve()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build response-anchored Hachimi personas for the XES grade-3 task."
    )
    parser.add_argument(
        "--persona_path",
        type=str,
        default="../data/personas_grade3_exact_20x4_seed42.jsonl",
        help="Source Hachimi persona jsonl, relative to xes root by default.",
    )
    parser.add_argument(
        "--response_csv_path",
        type=str,
        default="../XES3G5M/question_level/train_valid_sequences_quelevel.csv",
        help="Support response csv used for behavior anchoring.",
    )
    parser.add_argument(
        "--exclude_question_set_paths",
        type=str,
        nargs="*",
        default=DEFAULT_FROZEN_PATHS,
        help="Frozen evaluation question files to exclude from support anchoring.",
    )
    parser.add_argument("--min_student_unique_items", type=int, default=50)
    parser.add_argument("--hard_max_accuracy", type=float, default=0.50)
    parser.add_argument("--medium_max_accuracy", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--capability_neighbor_count",
        type=int,
        default=5,
        help="How many matched support students to aggregate when building structured math capability anchors.",
    )
    parser.add_argument(
        "--min_capability_item_count",
        type=int,
        default=5,
        help="Minimum aggregated item count required before trusting a metric-specific capability estimate.",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="../data/personas_grade3_exact_20x4_seed42_response_anchored_formABC.jsonl",
        help="Output anchored persona jsonl.",
    )
    parser.add_argument(
        "--output_root",
        type=str,
        default=str(XES_OUTPUTS_DIR / "response_anchored_personas"),
        help="Directory for manifest / diagnostics.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    persona_path = _resolve_path(args.persona_path)
    response_csv_path = _resolve_path(args.response_csv_path)
    exclude_paths = [_resolve_path(raw_path) for raw_path in args.exclude_question_set_paths]
    output_path = _resolve_path(args.output_path)

    excluded_question_ids = load_excluded_question_ids(exclude_paths)
    settings = AnchorBuildSettings(
        min_student_unique_items=args.min_student_unique_items,
        hard_max_accuracy=args.hard_max_accuracy,
        medium_max_accuracy=args.medium_max_accuracy,
        seed=args.seed,
        capability_neighbor_count=args.capability_neighbor_count,
        min_capability_item_count=args.min_capability_item_count,
    )
    output_rows, summary = build_response_anchored_persona_rows(
        persona_path=persona_path,
        response_csv_path=response_csv_path,
        excluded_question_ids=excluded_question_ids,
        settings=settings,
    )

    _write_jsonl(output_path, output_rows)

    run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        **summary,
        "persona_path": str(persona_path),
        "response_csv_path": str(response_csv_path),
        "exclude_question_set_paths": [str(path) for path in exclude_paths],
        "output_path": str(output_path),
    }
    _write_json(run_dir / "summary.json", manifest)
    _write_json(run_dir / "sample_anchor_profile.json", output_rows[0].get("math_anchor_profile"))
    _write_json(
        run_dir / "sample_capability_anchor.json",
        output_rows[0].get("math_task_capability_anchor"),
    )

    print(f"response-anchored personas written to: {output_path}")
    print(f"diagnostics directory: {run_dir}")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
