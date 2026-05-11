from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.runtime_paths import XES_OUTPUTS_DIR, XES_ROOT


@dataclass(frozen=True)
class CandidateItem:
    question_id: str
    question_type: str
    question_text: str
    options: dict[str, str]
    gold_answers: list[str]
    has_options: bool
    irt_support_total: int
    irt_support_accuracy: float
    irt_support_high_count: int
    irt_support_medium_count: int
    irt_support_low_count: int
    irt_support_poor_count: int
    irt_support_max_level_share: float
    irt_support_distribution_l1: float
    module_name: str
    b_hat: float
    difficulty_band: str
    band_center: float


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


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def load_latest_rasch_item_map(rasch_root: Path) -> dict[str, dict[str, object]]:
    latest_run_by_module: dict[str, Path] = {}
    for run_dir in sorted(rasch_root.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = load_json(summary_path)
        if not isinstance(summary, dict):
            raise ValueError(f"summary.json must be dict: {summary_path}")
        if "n_students_estimation" not in summary:
            continue
        module_name = str(summary["module_name"])
        latest_run_by_module[module_name] = run_dir

    item_map: dict[str, dict[str, object]] = {}
    for module_name, run_dir in latest_run_by_module.items():
        for row in load_csv_rows(run_dir / "item_parameters.csv"):
            if row.get("rasch_status") != "estimated":
                continue
            b_hat = row.get("b_hat")
            if not b_hat:
                continue
            question_id = str(row["question_id"])
            item_map[question_id] = {
                "module_name": module_name,
                "b_hat": float(b_hat),
                "rasch_run_dir": str(run_dir),
            }
    return item_map


def build_candidate_pool(
    base_item_pool_path: Path,
    blueprint: dict[str, object],
    rasch_root: Path,
) -> tuple[list[CandidateItem], dict[str, object]]:
    raw_rows = load_json(base_item_pool_path)
    if not isinstance(raw_rows, list):
        raise ValueError("base_item_pool.json must be a JSON list")
    rasch_map = load_latest_rasch_item_map(rasch_root)

    requirements = blueprint.get("candidate_pool_requirements", {})
    if not isinstance(requirements, dict):
        raise ValueError("candidate_pool_requirements must be dict")
    min_item_response_count = int(requirements.get("min_item_response_count", 0))
    max_level_share = float(requirements.get("max_level_share", 1.0))

    allowed_modules = {
        str(slot["module_name"])
        for slot in blueprint.get("slots", [])
        if isinstance(slot, dict) and "module_name" in slot
    }
    if not allowed_modules:
        raise ValueError("blueprint slots are empty")

    merged_rows: list[dict[str, object]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ValueError("base item pool contains non-dict row")
        question_id = str(row["question_id"])
        rasch_meta = rasch_map.get(question_id)
        if rasch_meta is None:
            continue
        if str(rasch_meta["module_name"]) not in allowed_modules:
            continue
        if int(row["irt_support_total"]) < min_item_response_count:
            continue
        if float(row["irt_support_max_level_share"]) > max_level_share:
            continue
        merged = dict(row)
        merged["module_name"] = str(rasch_meta["module_name"])
        merged["b_hat"] = float(rasch_meta["b_hat"])
        merged_rows.append(merged)

    by_module: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in merged_rows:
        by_module[str(row["module_name"])].append(row)

    candidate_items: list[CandidateItem] = []
    band_summary: dict[str, dict[str, int]] = {}
    for module_name, rows in by_module.items():
        rows.sort(
            key=lambda row: (
                float(row["b_hat"]),
                -int(row["irt_support_total"]),
                float(row["irt_support_distribution_l1"]),
                str(row["question_id"]),
            )
        )
        n_rows = len(rows)
        if n_rows < 3:
            raise ValueError(f"module candidate count too small for banding: {module_name} -> {n_rows}")

        easy_cut = n_rows / 3
        medium_cut = 2 * n_rows / 3
        band_values: dict[str, list[float]] = {"easy": [], "medium": [], "hard": []}
        for idx, row in enumerate(rows):
            if idx < easy_cut:
                band = "easy"
            elif idx < medium_cut:
                band = "medium"
            else:
                band = "hard"
            band_values[band].append(float(row["b_hat"]))
            row["difficulty_band"] = band

        band_center = {
            band: sorted(values)[len(values) // 2]
            for band, values in band_values.items()
            if values
        }
        band_summary[module_name] = {
            band: len(band_values[band]) for band in ("easy", "medium", "hard")
        }

        for row in rows:
            difficulty_band = str(row["difficulty_band"])
            candidate_items.append(
                CandidateItem(
                    question_id=str(row["question_id"]),
                    question_type=str(row["question_type"]),
                    question_text=str(row["question_text"]),
                    options=dict(row.get("options") or {}),
                    gold_answers=[str(answer) for answer in row.get("gold_answers", [])],
                    has_options=bool(row["has_options"]),
                    irt_support_total=int(row["irt_support_total"]),
                    irt_support_accuracy=float(row["irt_support_accuracy"]),
                    irt_support_high_count=int(row["irt_support_high_count"]),
                    irt_support_medium_count=int(row["irt_support_medium_count"]),
                    irt_support_low_count=int(row["irt_support_low_count"]),
                    irt_support_poor_count=int(row["irt_support_poor_count"]),
                    irt_support_max_level_share=float(row["irt_support_max_level_share"]),
                    irt_support_distribution_l1=float(row["irt_support_distribution_l1"]),
                    module_name=module_name,
                    b_hat=float(row["b_hat"]),
                    difficulty_band=difficulty_band,
                    band_center=float(band_center[difficulty_band]),
                )
            )

    pool_summary = {
        "candidate_item_count": len(candidate_items),
        "candidate_module_count": len(by_module),
        "candidate_type_counts": dict(Counter(item.question_type for item in candidate_items)),
        "candidate_module_counts": {
            module_name: len(rows) for module_name, rows in sorted(by_module.items(), key=lambda item: len(item[1]), reverse=True)
        },
        "candidate_band_counts": band_summary,
    }
    return candidate_items, pool_summary


def candidate_to_output_row(slot: dict[str, object], item: CandidateItem) -> dict[str, object]:
    return {
        "slot_id": int(slot["slot_id"]),
        "module_name": item.module_name,
        "difficulty_band": item.difficulty_band,
        "question_type": item.question_type,
        "question_id": item.question_id,
        "b_hat": item.b_hat,
        "irt_support_total": item.irt_support_total,
        "irt_support_accuracy": item.irt_support_accuracy,
        "irt_support_max_level_share": item.irt_support_max_level_share,
        "irt_support_distribution_l1": item.irt_support_distribution_l1,
        "question_text": item.question_text,
        "options_json": json.dumps(item.options, ensure_ascii=False),
        "gold_answers_json": json.dumps(item.gold_answers, ensure_ascii=False),
    }


def build_readable_markdown(form_name: str, rows: list[dict[str, object]]) -> str:
    lines = [f"# {form_name}", ""]
    for row in rows:
        lines.append(
            f"## 第{row['slot_id']}题｜{row['module_name']}｜{row['difficulty_band']}｜{row['question_type']}"
        )
        lines.append(str(row["question_text"]))
        options = json.loads(str(row["options_json"]))
        if options:
            for key, value in options.items():
                lines.append(f"- {key}. {value}")
        lines.append("")
    lines.append("# 答案")
    lines.append("")
    for row in rows:
        lines.append(f"- 第{row['slot_id']}题：{row['gold_answers_json']}")
    lines.append("")
    return "\n".join(lines)


def assemble_forms(
    candidate_items: list[CandidateItem],
    blueprint: dict[str, object],
    form_names: list[str],
) -> tuple[dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    slots = blueprint.get("slots", [])
    if not isinstance(slots, list) or not slots:
        raise ValueError("blueprint slots must be non-empty list")

    by_constraint: dict[tuple[str, str, str], list[CandidateItem]] = defaultdict(list)
    for item in candidate_items:
        key = (item.module_name, item.difficulty_band, item.question_type)
        by_constraint[key].append(item)

    for key, items in by_constraint.items():
        items.sort(
            key=lambda item: (
                abs(item.b_hat - item.band_center),
                item.irt_support_distribution_l1,
                -item.irt_support_total,
                item.question_id,
            )
        )

    forms: dict[str, list[dict[str, object]]] = {form_name: [] for form_name in form_names}
    used_question_ids: set[str] = set()
    form_b_sum = {form_name: 0.0 for form_name in form_names}

    slot_diagnostics: list[dict[str, object]] = []
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("slot must be dict")
        key = (
            str(slot["module_name"]),
            str(slot["difficulty_band"]),
            str(slot["question_type"]),
        )
        pool = [item for item in by_constraint[key] if item.question_id not in used_question_ids]
        if len(pool) < len(form_names):
            raise ValueError(
                f"slot {slot['slot_id']} lacks candidates for {key}: need {len(form_names)}, got {len(pool)}"
            )

        chosen = pool[: len(form_names)]
        remaining_forms = sorted(form_names, key=lambda form_name: (form_b_sum[form_name], form_name))
        chosen_sorted = sorted(chosen, key=lambda item: item.b_hat, reverse=True)
        for item, form_name in zip(chosen_sorted, remaining_forms):
            forms[form_name].append(candidate_to_output_row(slot, item))
            used_question_ids.add(item.question_id)
            form_b_sum[form_name] += item.b_hat

        slot_diagnostics.append(
            {
                "slot_id": int(slot["slot_id"]),
                "module_name": key[0],
                "difficulty_band": key[1],
                "question_type": key[2],
                "candidate_count_before_take": len(pool),
                "assigned_question_ids": [item.question_id for item in chosen],
            }
        )

    for form_name in form_names:
        forms[form_name].sort(key=lambda row: int(row["slot_id"]))
    return forms, slot_diagnostics


def summarize_form(form_name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "form_name": form_name,
        "n_items": len(rows),
        "type_counts": dict(Counter(str(row["question_type"]) for row in rows)),
        "difficulty_counts": dict(Counter(str(row["difficulty_band"]) for row in rows)),
        "module_counts": dict(Counter(str(row["module_name"]) for row in rows)),
        "mean_b_hat": sum(float(row["b_hat"]) for row in rows) / len(rows),
        "mean_support_total": sum(int(row["irt_support_total"]) for row in rows) / len(rows),
        "mean_distribution_l1": sum(float(row["irt_support_distribution_l1"]) for row in rows) / len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble several XES papers from a theory-guided blueprint.")
    parser.add_argument(
        "--blueprint_path",
        type=str,
        default="configs/assembly_blueprint_v1_balanced_20.json",
    )
    parser.add_argument(
        "--base_item_pool_path",
        type=str,
        default="outputs/base_item_pool/run_20260427_192805/base_item_pool.json",
    )
    parser.add_argument(
        "--rasch_root",
        type=str,
        default="outputs/rasch_module_fits",
    )
    parser.add_argument(
        "--form_names",
        type=str,
        default="Form_A,Form_B,Form_C",
        help="Comma-separated output form names.",
    )
    parser.add_argument(
        "--output_root",
        type=str,
        default=str(XES_OUTPUTS_DIR / "principled_papers"),
    )
    args = parser.parse_args()

    blueprint_path = resolve_xes_path(args.blueprint_path)
    base_item_pool_path = resolve_xes_path(args.base_item_pool_path)
    rasch_root = resolve_xes_path(args.rasch_root)
    blueprint = load_json(blueprint_path)
    if not isinstance(blueprint, dict):
        raise ValueError("blueprint file must be dict")

    candidate_items, pool_summary = build_candidate_pool(
        base_item_pool_path=base_item_pool_path,
        blueprint=blueprint,
        rasch_root=rasch_root,
    )
    form_names = [name.strip() for name in args.form_names.split(",") if name.strip()]
    if not form_names:
        raise ValueError("form_names is empty")
    forms, slot_diagnostics = assemble_forms(
        candidate_items=candidate_items,
        blueprint=blueprint,
        form_names=form_names,
    )

    run_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)

    write_json(run_dir / "blueprint_used.json", blueprint)
    write_json(run_dir / "candidate_pool_summary.json", pool_summary)
    write_json(run_dir / "slot_diagnostics.json", slot_diagnostics)

    form_summaries = []
    answer_key_rows = []
    for form_name, rows in forms.items():
        summary = summarize_form(form_name, rows)
        form_summaries.append(summary)
        write_json(run_dir / f"{form_name}.json", rows)
        write_csv(run_dir / f"{form_name}.csv", rows)
        (run_dir / f"{form_name}.md").write_text(
            build_readable_markdown(form_name, rows),
            encoding="utf-8",
        )
        for row in rows:
            answer_key_rows.append(
                {
                    "form_name": form_name,
                    "slot_id": row["slot_id"],
                    "question_id": row["question_id"],
                    "gold_answers_json": row["gold_answers_json"],
                }
            )

    write_json(run_dir / "form_summaries.json", form_summaries)
    write_csv(run_dir / "form_summaries.csv", form_summaries)
    write_csv(run_dir / "answer_key.csv", answer_key_rows)

    print(f"Principled papers assembled: {run_dir}")
    for summary in form_summaries:
        print(
            f"{summary['form_name']}: items={summary['n_items']}, "
            f"mean_b={summary['mean_b_hat']:.4f}, "
            f"mean_support={summary['mean_support_total']:.1f}"
        )


if __name__ == "__main__":
    main()
