from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.runtime_paths import XES_OUTPUTS_DIR, resolve_xes_path as resolve_xes_runtime_path


def resolve_xes_path(raw_path: str) -> Path:
    return resolve_xes_runtime_path(raw_path)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_form_rows(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError(f"paper form must be a JSON list: {path}")
    rows: list[dict[str, object]] = []
    for row_index, row in enumerate(payload, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"paper form row {row_index} must be object/dict")
        rows.append(row)
    if not rows:
        raise ValueError(f"paper form is empty: {path}")
    return rows


def parse_json_field(row: dict[str, object], key: str) -> object:
    raw_value = row.get(key)
    if not isinstance(raw_value, str):
        raise ValueError(f"{key} must be JSON string in paper row question_id={row.get('question_id')}")
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {key} for question_id={row.get('question_id')}: {exc}") from exc


def convert_form(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen_question_ids: set[str] = set()
    for row in load_form_rows(path):
        question_id = str(row.get("question_id", "")).strip()
        if not question_id:
            raise ValueError(f"missing question_id in {path}")
        if question_id in seen_question_ids:
            raise ValueError(f"duplicate question_id in {path}: {question_id}")
        seen_question_ids.add(question_id)

        options = parse_json_field(row, "options_json")
        gold_answers = parse_json_field(row, "gold_answers_json")
        if not isinstance(options, dict):
            raise ValueError(f"options_json must decode to dict for question_id={question_id}")
        if not isinstance(gold_answers, list):
            raise ValueError(f"gold_answers_json must decode to list for question_id={question_id}")

        out.append(
            {
                "question_id": question_id,
                "question_type": str(row["question_type"]),
                "question_text": str(row["question_text"]),
                "options": {str(key): str(value) for key, value in options.items()},
                "gold_answers": [str(answer) for answer in gold_answers],
                "has_options": bool(options),
                "real_response_count": int(row["irt_support_total"]),
                "real_item_accuracy": float(row["irt_support_accuracy"]),
                "difficulty_band": str(row["difficulty_band"]),
                "paper_slot_id": int(row["slot_id"]),
                "paper_module_name": str(row["module_name"]),
                "paper_b_hat": float(row["b_hat"]),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert assembled paper forms to H1/H2 frozen question JSON files.")
    parser.add_argument("--paper_dir", type=str, required=True)
    parser.add_argument("--form_names", type=str, default="Form_A,Form_B,Form_C")
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(XES_OUTPUTS_DIR / "principled_papers_frozen_questions"),
    )
    args = parser.parse_args()

    paper_dir = resolve_xes_path(args.paper_dir)
    form_names = [name.strip() for name in args.form_names.split(",") if name.strip()]
    if not form_names:
        raise ValueError("form_names is empty")

    output_dir = Path(args.output_dir) / paper_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for form_name in form_names:
        source_path = paper_dir / f"{form_name}.json"
        frozen_rows = convert_form(source_path)
        output_path = output_dir / f"{form_name}_selected_questions.json"
        write_json(output_path, frozen_rows)
        manifest.append(
            {
                "form_name": form_name,
                "source_path": str(source_path),
                "output_path": str(output_path),
                "n_questions": len(frozen_rows),
            }
        )

    write_json(output_dir / "manifest.json", manifest)
    print(f"Frozen question files exported: {output_dir}")
    for row in manifest:
        print(f"{row['form_name']}: {row['n_questions']} -> {row['output_path']}")


if __name__ == "__main__":
    main()
