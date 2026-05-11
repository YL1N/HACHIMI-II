from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unknown"


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


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split exported IRT calibration inputs into per-module subdirectories."
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        help="Directory containing summary.json, item_pool.json, responses_long.csv, student_ability.csv, module_summary.csv",
    )
    parser.add_argument(
        "--min_items",
        type=int,
        default=20,
        help="Only export modules with at least this many items.",
    )
    parser.add_argument(
        "--min_students",
        type=int,
        default=3000,
        help="Only export modules with at least this many students.",
    )
    parser.add_argument(
        "--min_responses",
        type=int,
        default=20000,
        help="Only export modules with at least this many responses.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    module_rows = load_csv_rows(input_dir / "module_summary.csv")
    response_rows = load_csv_rows(input_dir / "responses_long.csv")
    student_rows = load_csv_rows(input_dir / "student_ability.csv")
    item_rows = json.loads((input_dir / "item_pool.json").read_text(encoding="utf-8"))

    eligible_modules = []
    for row in module_rows:
        n_items = int(row["n_items"])
        n_students = int(row["n_students"])
        n_responses = int(row["n_responses"])
        if n_items < args.min_items:
            continue
        if n_students < args.min_students:
            continue
        if n_responses < args.min_responses:
            continue
        eligible_modules.append(row["module_name"])

    item_by_module: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in item_rows:
        module_name = f"{row['primary_route_top']} / {row['primary_route_module']}"
        item_by_module[module_name].append(row)

    response_by_module: dict[str, list[dict[str, str]]] = defaultdict(list)
    student_ids_by_module: dict[str, set[str]] = defaultdict(set)
    for row in response_rows:
        module_name = row["primary_route_name"]
        response_by_module[module_name].append(row)
        student_ids_by_module[module_name].add(row["student_id"])

    student_lookup = {row["student_id"]: row for row in student_rows}
    output_root = input_dir / "modules"
    output_root.mkdir(parents=True, exist_ok=True)

    exported_summary = []
    for module_name in eligible_modules:
        module_slug = slugify(module_name)
        module_dir = output_root / module_slug
        module_dir.mkdir(parents=True, exist_ok=True)

        module_item_rows = sorted(item_by_module[module_name], key=lambda row: str(row["question_id"]))
        module_response_rows = response_by_module[module_name]
        module_student_rows = [
            student_lookup[student_id]
            for student_id in sorted(student_ids_by_module[module_name])
            if student_id in student_lookup
        ]
        write_json(module_dir / "item_pool.json", module_item_rows)
        write_csv(module_dir / "responses_long.csv", module_response_rows)
        write_csv(module_dir / "student_ability.csv", module_student_rows)

        exported_summary.append(
            {
                "module_name": module_name,
                "module_slug": module_slug,
                "n_items": len(module_item_rows),
                "n_students": len(module_student_rows),
                "n_responses": len(module_response_rows),
            }
        )

    write_json(output_root / "exported_modules_summary.json", exported_summary)
    print(f"Module split completed: {output_root}")
    print(f"Exported modules: {len(exported_summary)}")


if __name__ == "__main__":
    main()
