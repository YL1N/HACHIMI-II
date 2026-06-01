from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .runtime_paths import XES_OUTPUTS_DIR, resolve_xes_path


@dataclass(frozen=True)
class DifficultyAnchorCase:
    question_id: str
    question_type: str
    module_name: str
    difficulty_band: str
    paper_b_hat: float
    question_text: str
    short_structural_reason: str


@dataclass(frozen=True)
class DifficultyAnchorContext:
    target_question_local_difficulty_hypothesis: str
    easy_anchor: DifficultyAnchorCase
    medium_anchor: DifficultyAnchorCase
    hard_anchor: DifficultyAnchorCase
    difficulty_anchor_rationale: list[str]


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_xes_path(raw_path: str | Path) -> Path:
    return resolve_xes_path(raw_path)


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


def _difficulty_band_reason(band: str, item: dict[str, object]) -> str:
    parts: list[str] = []
    if item.get("question_type"):
        parts.append(f"question_type={item['question_type']}")
    if item.get("module_name"):
        parts.append(f"module={item['module_name']}")
    if item.get("b_hat") is not None:
        parts.append(f"b_hat={float(item['b_hat']):.3f}")
    if item.get("irt_support_accuracy") is not None:
        parts.append(f"support_accuracy={float(item['irt_support_accuracy']):.3f}")
    return f"{band}_anchor: " + ", ".join(parts)


def _build_anchor_case(item: dict[str, object]) -> DifficultyAnchorCase:
    question_text = str(item.get("question_text", "")).strip()
    if not question_text:
        raise ValueError(f"anchor item missing question_text: question_id={item.get('question_id')}")
    return DifficultyAnchorCase(
        question_id=str(item["question_id"]),
        question_type=str(item["question_type"]),
        module_name=str(item["module_name"]),
        difficulty_band=str(item["difficulty_band"]),
        paper_b_hat=float(item["b_hat"]),
        question_text=question_text,
        short_structural_reason=_difficulty_band_reason(str(item["difficulty_band"]), item),
    )


class DifficultyAnchorBank:
    def __init__(
        self,
        base_item_pool_path: str | Path = XES_OUTPUTS_DIR / "base_item_pool/run_20260427_192805/base_item_pool.json",
        rasch_root: str | Path = XES_OUTPUTS_DIR / "rasch_module_fits",
        min_item_response_count: int = 100,
        max_level_share: float = 0.35,
    ) -> None:
        self.base_item_pool_path = _resolve_xes_path(base_item_pool_path)
        self.rasch_root = _resolve_xes_path(rasch_root)
        self.min_item_response_count = min_item_response_count
        self.max_level_share = max_level_share
        self._by_module_type_band = self._build_index()

    def _build_index(self) -> dict[tuple[str, str, str], list[dict[str, object]]]:
        raw_rows = _load_json(self.base_item_pool_path)
        if not isinstance(raw_rows, list):
            raise ValueError("base_item_pool.json must be a JSON list")
        rasch_map = _latest_rasch_item_map(self.rasch_root)

        merged_rows: list[dict[str, object]] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                raise ValueError("base item pool contains non-dict row")
            qid = str(row.get("question_id", "")).strip()
            if not qid:
                continue
            rasch_meta = rasch_map.get(qid)
            if rasch_meta is None:
                continue
            if int(row.get("irt_support_total", 0)) < self.min_item_response_count:
                continue
            if float(row.get("irt_support_max_level_share", 1.0)) > self.max_level_share:
                continue
            merged = dict(row)
            merged["module_name"] = str(rasch_meta["module_name"])
            merged["b_hat"] = float(rasch_meta["b_hat"])
            merged_rows.append(merged)

        by_module: dict[str, list[dict[str, object]]] = {}
        for row in merged_rows:
            by_module.setdefault(str(row["module_name"]), []).append(row)

        index: dict[tuple[str, str, str], list[dict[str, object]]] = {}
        for module_name, rows in by_module.items():
            rows.sort(
                key=lambda row: (
                    float(row["b_hat"]),
                    -int(row.get("irt_support_total", 0)),
                    str(row["question_id"]),
                )
            )
            n_rows = len(rows)
            if n_rows < 3:
                continue
            easy_cut = n_rows / 3
            medium_cut = 2 * n_rows / 3
            for idx, row in enumerate(rows):
                if idx < easy_cut:
                    band = "easy"
                elif idx < medium_cut:
                    band = "medium"
                else:
                    band = "hard"
                key = (module_name, str(row["question_type"]), band)
                index.setdefault(key, []).append({**row, "difficulty_band": band})
        return index

    def _pick_anchor(
        self,
        module_name: str,
        question_type: str,
        band: str,
        exclude_question_id: str,
    ) -> DifficultyAnchorCase:
        primary_key = (module_name, question_type, band)
        candidates = [
            row for row in self._by_module_type_band.get(primary_key, [])
            if str(row["question_id"]) != exclude_question_id
        ]
        if not candidates:
            fallback_module_candidates: list[dict[str, object]] = []
            for (candidate_module, candidate_type, candidate_band), rows in self._by_module_type_band.items():
                if candidate_type == question_type and candidate_band == band:
                    for row in rows:
                        if str(row["question_id"]) != exclude_question_id:
                            fallback_module_candidates.append(row)
            if not fallback_module_candidates:
                raise ValueError(
                    "no difficulty anchor candidate found for "
                    f"module={module_name!r}, question_type={question_type!r}, band={band!r}"
                )
            candidates = sorted(
                fallback_module_candidates,
                key=lambda row: (
                    0 if str(row["module_name"]) == module_name else 1,
                    abs(float(row["b_hat"])),
                    -int(row.get("irt_support_total", 0)),
                    str(row["question_id"]),
                ),
            )
        return _build_anchor_case(candidates[0])

    def build_context_for_question(
        self,
        question_id: str,
        question_type: str,
        module_name: str | None,
        paper_b_hat: float | None,
        real_difficulty_band: str | None,
    ) -> DifficultyAnchorContext | None:
        if module_name is None:
            return None

        if real_difficulty_band is not None:
            local_hypothesis = str(real_difficulty_band)
        elif paper_b_hat is None:
            local_hypothesis = "unknown"
        else:
            local_hypothesis = "medium"
            if paper_b_hat <= -0.5:
                local_hypothesis = "easy"
            elif paper_b_hat >= 0.5:
                local_hypothesis = "hard"

        easy_anchor = self._pick_anchor(module_name, question_type, "easy", question_id)
        medium_anchor = self._pick_anchor(module_name, question_type, "medium", question_id)
        hard_anchor = self._pick_anchor(module_name, question_type, "hard", question_id)

        rationale = [
            f"target_module={module_name}",
            f"target_question_type={question_type}",
            f"local_difficulty_hypothesis={local_hypothesis}",
            "anchors are same-type support items used only for relative difficulty interpretation",
        ]
        if paper_b_hat is not None:
            rationale.insert(2, f"target_b_hat={paper_b_hat:.3f}")
        return DifficultyAnchorContext(
            target_question_local_difficulty_hypothesis=local_hypothesis,
            easy_anchor=easy_anchor,
            medium_anchor=medium_anchor,
            hard_anchor=hard_anchor,
            difficulty_anchor_rationale=rationale,
        )
