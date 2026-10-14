from __future__ import annotations

import csv
import json
from pathlib import Path


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _latest_rasch_item_map(rasch_root: Path) -> dict[str, dict[str, object]]:
    latest_run_by_module: dict[str, Path] = {}
    for run_dir in sorted(rasch_root.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = _load_json(summary_path)
        if not isinstance(summary, dict) or "module_name" not in summary:
            continue
        if "n_students_estimation" not in summary:
            continue
        latest_run_by_module[str(summary["module_name"])] = run_dir

    item_map: dict[str, dict[str, object]] = {}
    for module_name, run_dir in latest_run_by_module.items():
        item_path = run_dir / "item_parameters.csv"
        if not item_path.exists():
            continue
        with item_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not isinstance(row, dict):
                    raise ValueError(f"invalid rasch item row in {item_path}")
                if str(row.get("rasch_status", "")).strip() != "estimated":
                    continue
                qid = str(row.get("question_id", "")).strip()
                b_hat_text = str(row.get("b_hat", "")).strip()
                if not qid or not b_hat_text:
                    continue
                item_map[qid] = {
                    "module_name": module_name,
                    "b_hat": float(b_hat_text),
                }
    return item_map
