from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from label_khan_correctness import (  # noqa: E402
    LLMConfig,
    OpenAICompatClient,
    SYSTEM_PROMPT,
    KhanTurnSample,
    _looks_like_direct_math_answer,
    append_jsonl,
    build_label_prompt,
    parse_label,
    read_jsonl,
    write_json,
    write_jsonl,
)


@dataclass(frozen=True)
class EediCalibrationSample:
    sample: KhanTurnSample
    gold_label: str
    gold_summary: str


def normalize_text(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def official_label(correctness: dict[str, Any], turn_idx: int) -> tuple[str, str]:
    entry = correctness.get(f"turn {turn_idx + 1}")
    if not isinstance(entry, dict):
        return "na", ""
    summary = str(entry.get("summary", "") or "")
    value = entry.get("correct")
    if value is True:
        return "correct", summary
    if value is False:
        return "incorrect", summary
    return "na", summary


def load_eedi_calibration_samples(
    annotated_csv_path: Path,
    max_per_label: int,
    seed: int,
) -> list[EediCalibrationSample]:
    rows = list(csv.DictReader(annotated_csv_path.open("r", encoding="utf-8", newline="")))
    by_label: dict[str, list[EediCalibrationSample]] = {"correct": [], "incorrect": [], "na": []}
    for row_idx, row in enumerate(rows):
        try:
            turns = ast.literal_eval(str(row.get("turns", "") or ""))
            correctness = ast.literal_eval(str(row.get("correctness", "") or ""))
        except Exception:
            continue
        if not isinstance(turns, list) or not isinstance(correctness, dict):
            continue
        normalized_turns: list[dict[str, str]] = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role_raw = str(turn.get("role", "") or "").strip()
            if role_raw == "tutor":
                role = "assistant"
            elif role_raw == "student":
                role = "user"
            else:
                continue
            content = normalize_text(turn.get("content", ""))
            if content:
                normalized_turns.append({"role": role, "content": content})
        for turn_idx, turn in enumerate(normalized_turns):
            if turn["role"] != "user" or turn_idx == 0:
                continue
            previous = normalized_turns[turn_idx - 1]
            if previous["role"] != "assistant":
                continue
            gold_label, gold_summary = official_label(correctness, turn_idx)
            sample = KhanTurnSample(
                sample_id=f"eedi_row_{row_idx}_turn_{turn_idx}",
                test_id=str(row.get("key", row_idx)),
                math_level=f"EEDI\nProblem context: {normalize_text(row.get('question', ''))}",
                dialogue_turn_count=len(normalized_turns),
                target_turn_idx=turn_idx,
                history=normalized_turns[:turn_idx],
                tutor_turn=previous["content"],
                gt_student_turn=turn["content"],
            )
            by_label[gold_label].append(
                EediCalibrationSample(
                    sample=sample,
                    gold_label=gold_label,
                    gold_summary=gold_summary,
                )
            )
    rng = random.Random(seed)
    selected: list[EediCalibrationSample] = []
    for label, samples in by_label.items():
        rng.shuffle(samples)
        selected.extend(samples[:max_per_label])
    rng.shuffle(selected)
    if not selected:
        raise ValueError("no EEDI calibration samples selected")
    return selected


def label_one(
    calibration_sample: EediCalibrationSample,
    client: OpenAICompatClient,
    max_attempts: int,
) -> dict[str, Any]:
    sample = calibration_sample.sample
    prompt = build_label_prompt(sample)
    last_error = ""
    for attempt_idx in range(max_attempts):
        try:
            parsed = client.chat_json(SYSTEM_PROMPT, prompt)
            pred_label, confidence, rationale, decision = parse_label(parsed)
            if (
                decision["tutor_request_type"] != "non_math"
                and decision["student_response_type"] != "answers_request"
                and _looks_like_direct_math_answer(sample.gt_student_turn)
            ):
                raise ValueError(
                    "direct math-looking response to math request must use student_response_type=answers_request"
                )
            return {
                "sample_id": sample.sample_id,
                "test_id": sample.test_id,
                "target_turn_idx": sample.target_turn_idx,
                "history": sample.history,
                "tutor_turn": sample.tutor_turn,
                "gt_student_turn": sample.gt_student_turn,
                "gold_label": calibration_sample.gold_label,
                "gold_summary": calibration_sample.gold_summary,
                **decision,
                "pred_label": pred_label,
                "label_confidence": confidence,
                "label_rationale": rationale,
                "label_attempt": attempt_idx + 1,
                "is_match": pred_label == calibration_sample.gold_label,
            }
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(1 + attempt_idx)
    raise RuntimeError(f"calibration labeling failed after {max_attempts} attempts: {last_error}")


def summarize(rows: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    labels = ["correct", "incorrect", "na"]
    confusion = {gold: {pred: 0 for pred in labels} for gold in labels}
    for row in rows:
        confusion[str(row["gold_label"])][str(row["pred_label"])] += 1
    match_count = sum(1 for row in rows if bool(row["is_match"]))
    return {
        "n_labeled": len(rows),
        "n_failures": len(failures),
        "match_count": match_count,
        "match_rate": match_count / len(rows) if rows else None,
        "gold_counts": dict(Counter(str(row["gold_label"]) for row in rows)),
        "pred_counts": dict(Counter(str(row["pred_label"]) for row in rows)),
        "confusion": confusion,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calibrate Khan correctness judge against official EEDI labels.")
    parser.add_argument(
        "--annotated_csv_path",
        default=str(
            PROJECT_ROOT
            / "external"
            / "sim-student-eval"
            / "data"
            / "annotated"
            / "eedi"
            / "test_gpt-4.1.csv"
        ),
    )
    parser.add_argument("--output_dir", default=str(ROOT / "outputs" / "eedi_correctness_judge_calibration_20260522"))
    parser.add_argument("--max_per_label", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--llm_base_url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--llm_model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--llm_api_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--timeout_s", type=float, default=120.0)
    parser.add_argument("--max_tokens", type=int, default=500)
    parser.add_argument("--max_concurrency", type=int, default=8)
    parser.add_argument("--max_attempts", type=int, default=5)
    parser.add_argument("--dry_run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    samples = load_eedi_calibration_samples(
        annotated_csv_path=Path(args.annotated_csv_path),
        max_per_label=args.max_per_label,
        seed=args.seed,
    )
    write_jsonl(
        output_dir / "calibration_samples.jsonl",
        [
            {
                **sample.sample.__dict__,
                "gold_label": sample.gold_label,
                "gold_summary": sample.gold_summary,
            }
            for sample in samples
        ],
    )
    write_json(
        output_dir / "run_config.json",
        {
            "annotated_csv_path": args.annotated_csv_path,
            "max_per_label": args.max_per_label,
            "seed": args.seed,
            "n_samples": len(samples),
            "dry_run": args.dry_run,
        },
    )
    if args.dry_run:
        print(f"[DryRun] samples={len(samples)} output_dir={output_dir}")
        return
    if not args.llm_base_url or not args.llm_model:
        raise ValueError("--llm_base_url and --llm_model are required unless --dry_run is set")

    rows_path = output_dir / "calibration_predictions.jsonl"
    failures_path = output_dir / "failures.jsonl"
    completed = {str(row["sample_id"]) for row in read_jsonl(rows_path)}
    remaining = [sample for sample in samples if sample.sample.sample_id not in completed]
    if failures_path.exists() and remaining:
        failures_path.unlink()
    client = OpenAICompatClient(
        LLMConfig(
            base_url=args.llm_base_url,
            model=args.llm_model,
            api_key=args.llm_api_key,
            timeout_s=args.timeout_s,
            max_tokens=args.max_tokens,
        )
    )
    print(f"[Data] samples={len(samples)} completed={len(completed)} remaining={len(remaining)}")
    with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
        future_map = {
            executor.submit(label_one, sample, client, args.max_attempts): sample
            for sample in remaining
        }
        done = 0
        for future in as_completed(future_map):
            sample = future_map[future]
            try:
                append_jsonl(rows_path, future.result())
            except Exception as exc:
                append_jsonl(
                    failures_path,
                    {
                        "sample_id": sample.sample.sample_id,
                        "gold_label": sample.gold_label,
                        "error": repr(exc),
                    },
                )
            done += 1
            if done % 20 == 0 or done == len(remaining):
                print(f"[Progress] completed_this_run={done}/{len(remaining)}")

    rows = read_jsonl(rows_path)
    failures = read_jsonl(failures_path)
    summary = summarize(rows, failures)
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[Done] output_dir={output_dir}")


if __name__ == "__main__":
    main()
