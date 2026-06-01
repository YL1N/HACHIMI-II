from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data_loading import (
    ANSWER_SPACE,
    EnemItem,
    load_area_item_bank,
    load_json,
    split_history_test_items,
)
from .llm_client import OpenAICompatClient


@dataclass(frozen=True)
class EnemImageDirectQuestion:
    question_id: str
    item_position: int
    image_path: Path
    gold_answer: str
    skill_code: str
    skill_summary: str
    competency_short_name: str
    split: str


def normalize_answer(value: object) -> str:
    answer = str(value or "").strip().upper()
    if answer not in ANSWER_SPACE:
        raise ValueError(f"selected_answer must be one of A/B/C/D/E, got={value!r}")
    return answer


def parse_direct_solve_payload(payload: dict[str, Any]) -> dict[str, str]:
    selected_answer = normalize_answer(payload.get("selected_answer"))
    confidence = str(payload.get("confidence") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip()
    if confidence not in {"high", "medium", "low"}:
        raise ValueError(f"confidence must be high/medium/low, got={confidence!r}")
    if not reason:
        raise ValueError("reason must be non-empty")
    return {
        "selected_answer": selected_answer,
        "confidence": confidence,
        "reason": reason,
    }


def load_direct_questions(
    config_path: str | Path,
    max_questions: int | None = None,
) -> list[EnemImageDirectQuestion]:
    path = Path(config_path)
    config = load_json(path)
    dataset_root = Path(str(config["source_dataset_root"]))
    manifest_path = Path(str(config.get("question_image_manifest_path") or ""))
    if not manifest_path.is_absolute():
        manifest_path = path.resolve().parent / manifest_path
    if not manifest_path.exists():
        raise FileNotFoundError(f"question image manifest not found: {manifest_path}")

    image_manifest: dict[str, str] = {}
    with manifest_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = load_json_line(line)
            image_manifest[str(row["question_id"])] = str(row["image_path"])

    item_bank = load_area_item_bank(
        dataset_root=dataset_root,
        area=str(config.get("target_area") or "CN"),
        regular_codes=[str(code) for code in config.get("regular_codes", [])] or None,
        base_booklet_code=str(config["base_booklet_code"]) if config.get("base_booklet_code") else None,
        image_manifest=image_manifest,
    )
    history_ids, test_ids = split_history_test_items(
        list(item_bank.common_items.values()),
        int(config.get("history_size") or 20),
        seed=int(config.get("sampling_seed") or 42),
    )
    split_by_id = {question_id: "history" for question_id in history_ids}
    split_by_id.update({question_id: "test" for question_id in test_ids})

    questions: list[EnemImageDirectQuestion] = []
    for item in sorted(item_bank.common_items.values(), key=lambda row: row.item_position):
        questions.append(_question_from_item(item, split_by_id[str(item.question_id)]))
        if max_questions is not None and len(questions) >= max_questions:
            break
    return questions


def load_json_line(line: str) -> dict[str, Any]:
    import json

    parsed = json.loads(line)
    if not isinstance(parsed, dict):
        raise ValueError("jsonl row must be an object")
    return parsed


def _question_from_item(item: EnemItem, split: str) -> EnemImageDirectQuestion:
    if not item.image_path:
        raise ValueError(f"item missing image_path: question_id={item.question_id}")
    image_path = Path(item.image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"question image not found: {image_path}")
    return EnemImageDirectQuestion(
        question_id=str(item.question_id),
        item_position=item.item_position,
        image_path=image_path,
        gold_answer=normalize_answer(item.correct_answer),
        skill_code=item.skill_code,
        skill_summary=item.skill_summary,
        competency_short_name=item.competency_short_name,
        split=split,
    )


def solve_question_directly(
    question: EnemImageDirectQuestion,
    llm: OpenAICompatClient,
) -> dict[str, str]:
    system_prompt = (
        "You are solving an ENEM natural-science multiple-choice question. "
        "Use only the image. Do not simulate a student. Return exactly one JSON object."
    )
    user_prompt = (
        "The image contains one Portuguese ENEM Ciências da Natureza question. "
        "Choose the best answer among A, B, C, D, E. "
        "Return JSON with keys: selected_answer, confidence, reason. "
        "selected_answer must be one of A, B, C, D, E. "
        "confidence must be high, medium, or low. "
        "reason must be one short sentence."
    )
    payload = llm.chat_json_with_image(system_prompt, user_prompt, question.image_path)
    return parse_direct_solve_payload(payload)


def compute_direct_metrics(rows: list[dict[str, Any]], n_questions: int, n_failures: int) -> dict[str, Any]:
    correct = sum(1 for row in rows if row["selected_answer"] == row["gold_answer"])
    metrics: dict[str, Any] = {
        "n_questions": n_questions,
        "n_predictions": len(rows),
        "n_failures": n_failures,
        "accuracy": correct / len(rows) if rows else None,
        "correct": correct,
        "selected_answer_counts": dict(Counter(str(row["selected_answer"]) for row in rows)),
        "gold_answer_counts": dict(Counter(str(row["gold_answer"]) for row in rows)),
    }
    by_split: dict[str, Any] = {}
    for split in sorted({str(row["split"]) for row in rows}):
        split_rows = [row for row in rows if str(row["split"]) == split]
        split_correct = sum(1 for row in split_rows if row["selected_answer"] == row["gold_answer"])
        by_split[split] = {
            "n_predictions": len(split_rows),
            "correct": split_correct,
            "accuracy": split_correct / len(split_rows) if split_rows else None,
        }
    metrics["by_split"] = by_split
    return metrics


def count_unresolved_failure_ids(
    prediction_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
) -> set[str]:
    predicted_ids = {str(row["question_id"]) for row in prediction_rows}
    failed_ids = {str(row["question_id"]) for row in failure_rows}
    return failed_ids - predicted_ids
