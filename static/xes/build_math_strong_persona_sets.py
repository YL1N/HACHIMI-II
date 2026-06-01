from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

XES_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = XES_ROOT.parent.parent
if str(XES_ROOT) not in sys.path:
    sys.path.insert(0, str(XES_ROOT))

from src.data_loading import filter_personas_by_grade, load_personas, sample_personas


GRADE_LABELS = {
    3: "三年级",
    4: "四年级",
    5: "五年级",
    6: "六年级",
}
LEVELS = ("high", "medium", "low", "poor")
MATH = "数学"


def _load_raw_rows_by_id(path: Path) -> dict[str, dict[str, object]]:
    rows_by_id: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            student_id = str(row.get("id", "")).strip()
            if not student_id:
                raise ValueError(f"source row {line_no} missing id")
            if student_id in rows_by_id:
                raise ValueError(f"duplicate student id in source file: {student_id}")
            rows_by_id[student_id] = row
    if not rows_by_id:
        raise ValueError(f"no persona rows loaded from {path}")
    return rows_by_id


def _select_grade_math_strong_rows(
    *,
    personas_path: Path,
    grade_label: str,
    per_level: int,
    seed: int,
) -> tuple[list[dict[str, object]], dict[str, int], int]:
    all_personas = load_personas(personas_path, limit=None)
    raw_rows_by_id = _load_raw_rows_by_id(personas_path)

    grade_personas = filter_personas_by_grade(
        all_personas,
        target_grade=grade_label,
        match_mode="exact",
    )
    math_strong_personas = [
        persona
        for persona in grade_personas
        if MATH in persona.strong_subjects
    ]
    available_counts = Counter(persona.academic_level for persona in math_strong_personas)

    required_total = per_level * len(LEVELS)
    for level in LEVELS:
        available = available_counts.get(level, 0)
        if available < per_level:
            raise ValueError(
                f"{grade_label} 数学强项画像不足: level={level}, required={per_level}, available={available}"
            )

    sampled = sample_personas(
        math_strong_personas,
        max_personas=required_total,
        sampling_mode="stratified",
        seed=seed,
    )
    sampled_counts = Counter(persona.academic_level for persona in sampled)
    for level in LEVELS:
        if sampled_counts.get(level, 0) != per_level:
            raise ValueError(
                f"{grade_label} 抽样后层级数量不对: level={level}, expected={per_level}, actual={sampled_counts.get(level, 0)}"
            )

    selected_rows = [raw_rows_by_id[persona.student_id] for persona in sampled]
    return selected_rows, dict(sampled_counts), len(math_strong_personas)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build grade-specific math-strong 20x4 persona sets for XES experiments."
    )
    parser.add_argument(
        "--source",
        type=str,
        default=str(PROJECT_ROOT / "merged_students_10k.jsonl"),
        help="Source persona pool jsonl.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(PROJECT_ROOT / "data"),
        help="Directory to write persona jsonl files.",
    )
    parser.add_argument(
        "--grades",
        type=int,
        nargs="+",
        default=[3, 4, 5, 6],
        help="Grades to export. Supported: 3 4 5 6.",
    )
    parser.add_argument(
        "--per_level",
        type=int,
        default=20,
        help="How many personas to keep for each academic level.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Sampling seed.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    source_path = Path(args.source).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    for grade in args.grades:
        if grade not in GRADE_LABELS:
            raise ValueError(f"unsupported grade: {grade}")
        grade_label = GRADE_LABELS[grade]
        selected_rows, sampled_counts, eligible_total = _select_grade_math_strong_rows(
            personas_path=source_path,
            grade_label=grade_label,
            per_level=args.per_level,
            seed=args.seed,
        )
        output_path = output_dir / f"personas_math_strong_grade{grade}_exact_{args.per_level}x4_seed{args.seed}.jsonl"
        _write_jsonl(output_path, selected_rows)
        manifest_row = {
            "grade": grade_label,
            "output_path": str(output_path),
            "eligible_math_strong_total": eligible_total,
            "sampled_counts": sampled_counts,
            "n_selected": len(selected_rows),
        }
        manifest.append(manifest_row)
        print(json.dumps(manifest_row, ensure_ascii=False))

    manifest_path = output_dir / f"personas_math_strong_manifest_{args.per_level}x4_seed{args.seed}.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(json.dumps({"manifest_path": str(manifest_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
