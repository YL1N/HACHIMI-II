from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path
from ast import literal_eval


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def write_turn_level_outputs(
    output_dir: Path,
    records: list[dict[str, object]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "predictions.jsonl"
    csv_path = output_dir / "turn_level_predictions.csv"
    metrics_path = output_dir / "metrics.json"

    write_jsonl(jsonl_path, records)

    fieldnames = [
        "dialogue_id",
        "question_id",
        "intervention_id",
        "turn_idx",
        "gt_turn",
        "pred_turn",
        "retried",
        "has_violation",
        "violation_types",
        "question_text",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            final_violation = record["violation_check"]
            writer.writerow(
                {
                    "dialogue_id": record["dialogue_id"],
                    "question_id": record["question_id"],
                    "intervention_id": record["intervention_id"],
                    "turn_idx": record["turn_idx"],
                    "gt_turn": record["gt_turn"],
                    "pred_turn": record["pred_turn"],
                    "retried": record["retried"],
                    "has_violation": final_violation["has_violation"],
                    "violation_types": "|".join(final_violation["violation_types"]),
                    "question_text": record["question_text"],
                }
            )

    interaction_counter = Counter(
        str(record["interaction_state"]["response_commitment_state"]) for record in records
    )
    maturity_counter = Counter(
        str(record["interaction_state"]["response_maturity_cap"]) for record in records
    )
    violation_counter = Counter()
    retries = 0
    remaining_violations = 0
    for record in records:
        if bool(record["retried"]):
            retries += 1
        final_violation = record["violation_check"]
        if bool(final_violation["has_violation"]):
            remaining_violations += 1
        for name in final_violation["violation_types"]:
            violation_counter[str(name)] += 1
    metrics = {
        "n_records": len(records),
        "retries": retries,
        "remaining_violations": remaining_violations,
        "response_commitment_distribution": dict(interaction_counter),
        "response_maturity_distribution": dict(maturity_counter),
        "violation_distribution": dict(violation_counter),
    }
    write_json(metrics_path, metrics)


def export_official_eval_csv(
    output_dir: Path,
    records: list[dict[str, object]],
    annotated_eedi_dir: Path,
) -> Path | None:
    matched_rows: list[dict[str, object]] = []
    keys_needed = {
        (str(record["dialogue_id"]), int(record["turn_idx"])): record for record in records
    }
    if not keys_needed:
        return None

    dialogue_idx_map: dict[str, int] = {}
    next_dialogue_idx = 0
    for split_name in ("train_gpt-4.1.csv", "val_gpt-4.1.csv", "test_gpt-4.1.csv"):
        path = annotated_eedi_dir / split_name
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for source_dialogue_idx, row in enumerate(reader):
                key_text = str(row.get("key", "")).strip()
                if not key_text:
                    continue
                try:
                    key_tuple = literal_eval(key_text)
                except (SyntaxError, ValueError):
                    continue
                if not isinstance(key_tuple, tuple) or len(key_tuple) != 2:
                    continue
                dialogue_id = f"{key_tuple[0]}_{key_tuple[1]}"
                try:
                    turns = literal_eval(str(row.get("turns", "") or ""))
                except (SyntaxError, ValueError):
                    continue
                if not isinstance(turns, list):
                    continue
                if dialogue_id not in dialogue_idx_map:
                    dialogue_idx_map[dialogue_id] = next_dialogue_idx
                    next_dialogue_idx += 1
                dialogue_idx = dialogue_idx_map[dialogue_id]
                for turn_idx, turn in enumerate(turns):
                    if not isinstance(turn, dict) or str(turn.get("role", "")).strip() != "student":
                        continue
                    match_key = (dialogue_id, turn_idx)
                    record = keys_needed.get(match_key)
                    if record is None:
                        continue
                    matched_rows.append(
                        {
                            "key": key_text,
                            "dialogue_idx": dialogue_idx,
                            "turn_idx": turn_idx,
                            "prompt": _build_official_prompt_stub(row, turn_idx),
                            "gt_turn": str(turn.get("content", "") or ""),
                            "pred_turn": record["pred_turn"],
                            "question": row.get("question"),
                            "subjects": row.get("subjects"),
                            "turns": row.get("turns"),
                            "question_annotation": row.get("question_annotation"),
                            "acts": row.get("acts"),
                            "correctness": row.get("correctness"),
                            "eedi_kcs": row.get("eedi_kcs"),
                            "ocean_persona": row.get("ocean_persona"),
                            "freeform_persona": row.get("freeform_persona"),
                        }
                    )

    if not matched_rows:
        return None

    out_path = output_dir / "official_eval_input.csv"
    fieldnames = list(matched_rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matched_rows)
    return out_path


def _build_official_prompt_stub(row: dict[str, str], turn_idx: int) -> str:
    question = str(row.get("question", "") or "")
    turns_raw = str(row.get("turns", "") or "")
    try:
        turns = literal_eval(turns_raw)
    except (SyntaxError, ValueError):
        return f"Question:\n{question}\n\nConversation History:\n{turns_raw}"
    if not isinstance(turns, list):
        return f"Question:\n{question}\n\nConversation History:\n{turns_raw}"
    history_lines: list[str] = []
    for idx, turn in enumerate(turns[:turn_idx]):
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "") or "").strip().title()
        content = str(turn.get("content", "") or "").strip()
        history_lines.append(f"Turn {idx + 1} ({role}): {content}")
    return f"Question:\n{question}\n\nConversation History:\n" + "\n".join(history_lines)
