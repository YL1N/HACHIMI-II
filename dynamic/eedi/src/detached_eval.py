from __future__ import annotations

import csv
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from rouge_score import rouge_scorer

from .evaluation_eedi import write_json, write_jsonl
from .llm_client import LLMConfig
from .theory_error_eval import (
    _evaluate_single_row as _evaluate_single_theory_row,
    _gold_turn_is_officially_incorrect,
    evaluate_theory_error_rows,
    load_theory_error_rows,
)

LETTERS = ["A", "B", "C", "D"]

OFFICIAL_CORRECTNESS_SYSTEM_PROMPT = """You are a math education expert. You will observe a tutoring dialogue where a student is attempting to solve a math problem. You will see two versions of the next student turn: a ground-truth turn and a candidate turn. Your job is to evaluate the correctness and errors of the candidate turn.
- The correctness of the ground-truth turn is given. You must evaluate the correctness of the candidate turn.
- Correctness can be "correct", "incorrect", or "na". It is "correct" if the student correctly responds to the previous tutor turn. It is "incorrect" if the student incorrectly responds to the previous tutor turn, or indicates they do not know the answer. It is "na" in all other cases, such as when the tutor does not ask a question or only asks a conversational question, or if the student response is purely conversational. A turn is conversational when it does not address a mathematical task posed by the tutor.
- If both the ground-truth AND candidate turns are "incorrect", evaluate if they have the same error. They have the same error if the two turns are mathematically EQUIVALENT. If they are mathematically inequivalent, they do NOT have the same error.

After reasoning, please return the correctness of the **candidate** turn as "correct", "incorrect", or "na". If both the ground-truth and candidate turns are incorrect, add "same error" or "different error" to your response (ex: "incorrect, same error"). Do not include any other text in your response."""


class OpenAICompatTextClient:
    def __init__(self, config: LLMConfig):
        self._cfg = config
        self._chat_url = config.base_url.rstrip("/") + "/chat/completions"

    # Retry transient connection/endpoint failures (e.g. WinError 10054 reset,
    # timeouts, 5xx) instead of crashing the whole eval. Content errors are NOT
    # retried (handled below). Mirrors the retry loop in RemoteEmbeddingClient.
    _CHAT_MAX_RETRIES = 8
    _CHAT_RETRY_SLEEP_S = 3.0
    _TRANSIENT_MARKERS = (
        "url error",
        "10054",
        "10053",
        "timed out",
        "timeout",
        "connection",
        "reset",
        "remote end closed",
        "temporarily unavailable",
        "bad gateway",
        "502",
        "503",
        "504",
        "520",
        "521",
        "522",
        "523",
        "524",
        "gateway time-out",
        "error code: 5",
        "max retries",
    )

    def chat_text(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._cfg.model,
            "temperature": self._cfg.temperature,
            "max_tokens": self._cfg.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        attempt = 0
        while True:
            attempt += 1
            try:
                body = _post_json(
                    url=self._chat_url,
                    api_key=self._cfg.api_key,
                    payload=payload,
                    timeout_s=self._cfg.timeout_s,
                )
                break
            except Exception as exc:  # noqa: BLE001 - retry only transient
                msg = str(exc).lower()
                transient = any(m in msg for m in self._TRANSIENT_MARKERS)
                if not transient or attempt > self._CHAT_MAX_RETRIES:
                    raise
                time.sleep(self._CHAT_RETRY_SLEEP_S)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"malformed chat completion response: {body}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"empty content from model response: {body}")
        return content.strip()


class RemoteEmbeddingClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_s: float,
    ):
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._timeout_s = timeout_s

    def embed_texts(
        self,
        texts: list[str],
        model: str,
        batch_size: int,
        max_retries: int,
        retry_sleep_s: float,
    ) -> np.ndarray:
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            attempt = 0
            while True:
                attempt += 1
                try:
                    body = _post_json(
                        url=self._url,
                        api_key=self._api_key,
                        payload={"model": model, "input": batch},
                        timeout_s=self._timeout_s,
                    )
                    break
                except Exception:
                    if attempt > max_retries:
                        raise
                    if retry_sleep_s > 0:
                        time.sleep(retry_sleep_s)
            try:
                data = body["data"]
            except KeyError as exc:
                raise ValueError(f"malformed embedding response: {body}") from exc
            if not isinstance(data, list):
                raise ValueError(f"embedding response data must be list: {body}")
            ordered = sorted(data, key=lambda item: int(item["index"]))
            all_vectors.extend([item["embedding"] for item in ordered])
        return np.asarray(all_vectors, dtype=np.float32)


def run_detached_eval(
    input_file: Path,
    output_dir: Path,
    llm_config: LLMConfig,
    embedding_base_url: str,
    embedding_model: str,
    embedding_api_key: str,
    embedding_batch_size: int,
    embedding_timeout_s: float,
    embedding_max_retries: int,
    embedding_retry_sleep_s: float,
    max_concurrency: int,
    truncate: int = 0,
) -> dict[str, Any]:
    rows = load_theory_error_rows(input_file=input_file, truncate=truncate)
    if not rows:
        raise ValueError("no rows loaded from input_file")

    should_compute_text_similarity = bool(
        str(embedding_base_url or "").strip()
        and str(embedding_model or "").strip()
        and str(embedding_api_key or "").strip()
    )

    if should_compute_text_similarity:
        return _run_detached_eval_batch_with_embeddings(
            rows=rows,
            output_dir=output_dir,
            llm_config=llm_config,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            embedding_api_key=embedding_api_key,
            embedding_batch_size=embedding_batch_size,
            embedding_timeout_s=embedding_timeout_s,
            embedding_max_retries=embedding_max_retries,
            embedding_retry_sleep_s=embedding_retry_sleep_s,
            max_concurrency=max_concurrency,
        )

    combined_records = run_detached_eval_streaming(
        rows=rows,
        output_dir=output_dir,
        llm_config=llm_config,
        max_concurrency=max_concurrency,
    )
    summary = build_detached_eval_summary(combined_records)
    write_detached_eval_outputs(
        output_dir=output_dir,
        records=combined_records,
        summary=summary,
    )
    _write_detached_eval_progress(
        progress_path=output_dir / "detached_eval_progress.json",
        expected_rows=len(rows),
        completed_rows=len(combined_records),
        pending_rows=len(rows) - len(combined_records),
        status="completed",
    )
    return summary


def _run_detached_eval_batch_with_embeddings(
    rows: list[dict[str, Any]],
    output_dir: Path,
    llm_config: LLMConfig,
    embedding_base_url: str,
    embedding_model: str,
    embedding_api_key: str,
    embedding_batch_size: int,
    embedding_timeout_s: float,
    embedding_max_retries: int,
    embedding_retry_sleep_s: float,
    max_concurrency: int,
) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        text_future = executor.submit(
            compute_text_similarity,
            rows=rows,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            embedding_api_key=embedding_api_key,
            embedding_batch_size=embedding_batch_size,
            embedding_timeout_s=embedding_timeout_s,
            embedding_max_retries=embedding_max_retries,
            embedding_retry_sleep_s=embedding_retry_sleep_s,
        )
        correctness_future = executor.submit(
            evaluate_official_correctness,
            rows=rows,
            llm_config=llm_config,
            max_concurrency=max_concurrency,
        )
        text_scores = text_future.result()
        correctness_records = correctness_future.result()
    theory_rows = [row for row in rows if _gold_turn_is_officially_incorrect(row)]
    theory_records = evaluate_theory_error_rows(
        rows=theory_rows,
        llm_config=llm_config,
        max_concurrency=max_concurrency,
    )

    combined_records = build_detached_eval_records(
        rows=rows,
        text_scores=text_scores,
        correctness_records=correctness_records,
        theory_records=theory_records,
    )
    summary = build_detached_eval_summary(combined_records)
    write_detached_eval_outputs(
        output_dir=output_dir,
        records=combined_records,
        summary=summary,
    )
    return summary


def run_detached_eval_streaming(
    rows: list[dict[str, Any]],
    output_dir: Path,
    llm_config: LLMConfig,
    max_concurrency: int,
) -> list[dict[str, Any]]:
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be > 0")
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "detached_eval_results.jsonl"
    progress_path = output_dir / "detached_eval_progress.json"
    existing_records = _load_existing_detached_records(results_path)
    completed_uids = {str(row["uid"]) for row in existing_records}
    pending_rows = [row for row in rows if _row_uid(row) not in completed_uids]
    _write_detached_eval_progress(
        progress_path=progress_path,
        expected_rows=len(rows),
        completed_rows=len(existing_records),
        pending_rows=len(pending_rows),
        status="running",
    )
    if pending_rows:
        client = OpenAICompatTextClient(llm_config)
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            future_map = {
                executor.submit(_evaluate_single_streaming_row, client, row, llm_config): row
                for row in pending_rows
            }
            completed_since_start = 0
            for future in as_completed(future_map):
                record = future.result()
                _append_jsonl(results_path, record)
                existing_records.append(record)
                completed_since_start += 1
                _write_detached_eval_progress(
                    progress_path=progress_path,
                    expected_rows=len(rows),
                    completed_rows=len(existing_records),
                    pending_rows=len(rows) - len(existing_records),
                    status="running",
                )
                if completed_since_start % 100 == 0:
                    print(
                        json.dumps(
                            {
                                "event": "detached_eval_progress",
                                "completed_rows": len(existing_records),
                                "expected_rows": len(rows),
                                "pending_rows": len(rows) - len(existing_records),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
    existing_records.sort(key=lambda row: (row["dialogue_idx"], row["turn_idx"], row["uid"]))
    _write_detached_eval_progress(
        progress_path=progress_path,
        expected_rows=len(rows),
        completed_rows=len(existing_records),
        pending_rows=len(rows) - len(existing_records),
        status="finalizing",
    )
    return existing_records


def _evaluate_single_streaming_row(
    client: OpenAICompatTextClient,
    row: dict[str, Any],
    llm_config: LLMConfig,
) -> dict[str, Any]:
    uid = _row_uid(row)
    gt_label = _get_gt_correctness_label(row)
    text_scores = _compute_single_text_similarity(row)
    correctness = None
    if gt_label != "na":
        correctness = _evaluate_single_correctness_row(client, row)
    theory = None
    if _gold_turn_is_officially_incorrect(row):
        theory = _evaluate_single_theory_row(row, llm_config)
    return _build_single_detached_eval_record(
        row=row,
        uid=uid,
        text_scores=text_scores,
        correctness=correctness,
        theory=theory,
    )


def _compute_single_text_similarity(row: dict[str, Any]) -> dict[str, float | None]:
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)
    score = scorer.score(
        target=str(row.get("gt_turn", "") or ""),
        prediction=str(row.get("pred_turn", "") or ""),
    )["rougeL"].fmeasure
    return {
        "rougeL": float(score),
        "cosine_similarity": None,
    }


def build_empty_text_similarity(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, float | None]]:
    return {
        _row_uid(row): {
            "rougeL": None,
            "cosine_similarity": None,
        }
        for row in rows
    }


def compute_text_similarity(
    rows: list[dict[str, Any]],
    embedding_base_url: str,
    embedding_model: str,
    embedding_api_key: str,
    embedding_batch_size: int,
    embedding_timeout_s: float,
    embedding_max_retries: int,
    embedding_retry_sleep_s: float,
) -> dict[str, dict[str, float]]:
    gt_turns = [str(row.get("gt_turn", "") or "") for row in rows]
    pred_turns = [str(row.get("pred_turn", "") or "") for row in rows]
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)
    rouge_scores = [
        scorer.score(target=gt_turn, prediction=pred_turn)["rougeL"].fmeasure
        for gt_turn, pred_turn in zip(gt_turns, pred_turns)
    ]

    if not embedding_base_url.strip():
        raise ValueError("embedding_base_url is required for detached text similarity")
    client = RemoteEmbeddingClient(
        base_url=embedding_base_url,
        api_key=embedding_api_key or "EMPTY",
        timeout_s=embedding_timeout_s,
    )
    gt_embeddings = client.embed_texts(
        texts=gt_turns,
        model=embedding_model,
        batch_size=embedding_batch_size,
        max_retries=embedding_max_retries,
        retry_sleep_s=embedding_retry_sleep_s,
    )
    pred_embeddings = client.embed_texts(
        texts=pred_turns,
        model=embedding_model,
        batch_size=embedding_batch_size,
        max_retries=embedding_max_retries,
        retry_sleep_s=embedding_retry_sleep_s,
    )
    cos_scores = np.einsum("ij,ij->i", gt_embeddings, pred_embeddings).tolist()

    result: dict[str, dict[str, float]] = {}
    for row, rouge_score_value, cos_score_value in zip(rows, rouge_scores, cos_scores):
        result[_row_uid(row)] = {
            "rougeL": float(rouge_score_value),
            "cosine_similarity": float(cos_score_value),
        }
    return result


def evaluate_official_correctness(
    rows: list[dict[str, Any]],
    llm_config: LLMConfig,
    max_concurrency: int,
) -> dict[str, dict[str, Any]]:
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be > 0")
    client = OpenAICompatTextClient(llm_config)
    eligible_rows = [row for row in rows if _get_gt_correctness_label(row) != "na"]
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_map = {
            executor.submit(_evaluate_single_correctness_row, client, row): row
            for row in eligible_rows
        }
        for future in as_completed(future_map):
            record = future.result()
            results[str(record["uid"])] = record
    return results


def build_detached_eval_records(
    rows: list[dict[str, Any]],
    text_scores: dict[str, dict[str, float]],
    correctness_records: dict[str, dict[str, Any]],
    theory_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    theory_map = {_row_uid(row): row for row in theory_records}
    combined: list[dict[str, Any]] = []
    for row in rows:
        uid = _row_uid(row)
        correctness = correctness_records.get(uid)
        theory = theory_map.get(uid)
        gt_label = _get_gt_correctness_label(row)
        pred_label = (
            None
            if correctness is None
            else correctness.get("pred_correctness_label")
        )
        same_error_all3 = None
        if theory is not None and not bool(theory.get("judge_failed")):
            if (
                theory.get("gold_has_codable_math_error") is True
                and theory.get("pred_has_codable_math_error") is True
            ):
                same_error_all3 = bool(
                    theory.get("same_knowledge_type")
                    and theory.get("same_error_locus")
                    and theory.get("same_error_mechanism")
                )
            else:
                same_error_all3 = False
        combined.append(
            {
                "uid": uid,
                "key": str(row.get("key", "") or ""),
                "dialogue_idx": int(row["dialogue_idx"]),
                "turn_idx": int(row["turn_idx"]),
                "gt_turn": str(row.get("gt_turn", "") or ""),
                "pred_turn": str(row.get("pred_turn", "") or ""),
                "rougeL": text_scores[uid]["rougeL"],
                "cosine_similarity": text_scores[uid]["cosine_similarity"],
                "official_gt_correctness_label": gt_label,
                "official_pred_correctness_label": pred_label,
                "official_correctness_match": (
                    None if correctness is None else correctness.get("correctness_match")
                ),
                "official_correctness_judge_raw": (
                    "" if correctness is None else correctness.get("judge_raw", "")
                ),
                "gold_has_codable_math_error": (
                    None if theory is None else theory.get("gold_has_codable_math_error")
                ),
                "pred_has_codable_math_error": (
                    None if theory is None else theory.get("pred_has_codable_math_error")
                ),
                "same_knowledge_type": (
                    None if theory is None else theory.get("same_knowledge_type")
                ),
                "same_error_locus": (
                    None if theory is None else theory.get("same_error_locus")
                ),
                "same_error_mechanism": (
                    None if theory is None else theory.get("same_error_mechanism")
                ),
                "same_error_all3": same_error_all3,
                "judge_failed": None if theory is None else theory.get("judge_failed"),
                "gold_judge_error": "" if theory is None else theory.get("gold_judge_error", ""),
                "pred_judge_error": "" if theory is None else theory.get("pred_judge_error", ""),
                "gold_code": None if theory is None else theory.get("gold_code"),
                "pred_code": None if theory is None else theory.get("pred_code"),
            }
        )
    combined.sort(key=lambda row: (row["dialogue_idx"], row["turn_idx"], row["uid"]))
    return combined


def _build_single_detached_eval_record(
    row: dict[str, Any],
    uid: str,
    text_scores: dict[str, float | None],
    correctness: dict[str, Any] | None,
    theory: dict[str, Any] | None,
) -> dict[str, Any]:
    gt_label = _get_gt_correctness_label(row)
    pred_label = (
        None
        if correctness is None
        else correctness.get("pred_correctness_label")
    )
    same_error_all3 = None
    if theory is not None and not bool(theory.get("judge_failed")):
        if (
            theory.get("gold_has_codable_math_error") is True
            and theory.get("pred_has_codable_math_error") is True
        ):
            same_error_all3 = bool(
                theory.get("same_knowledge_type")
                and theory.get("same_error_locus")
                and theory.get("same_error_mechanism")
            )
        else:
            same_error_all3 = False
    return {
        "uid": uid,
        "key": str(row.get("key", "") or ""),
        "dialogue_idx": int(row["dialogue_idx"]),
        "turn_idx": int(row["turn_idx"]),
        "gt_turn": str(row.get("gt_turn", "") or ""),
        "pred_turn": str(row.get("pred_turn", "") or ""),
        "rougeL": text_scores["rougeL"],
        "cosine_similarity": text_scores["cosine_similarity"],
        "official_gt_correctness_label": gt_label,
        "official_pred_correctness_label": pred_label,
        "official_correctness_match": (
            None if correctness is None else correctness.get("correctness_match")
        ),
        "official_correctness_judge_raw": (
            "" if correctness is None else correctness.get("judge_raw", "")
        ),
        "gold_has_codable_math_error": (
            None if theory is None else theory.get("gold_has_codable_math_error")
        ),
        "pred_has_codable_math_error": (
            None if theory is None else theory.get("pred_has_codable_math_error")
        ),
        "same_knowledge_type": (
            None if theory is None else theory.get("same_knowledge_type")
        ),
        "same_error_locus": (
            None if theory is None else theory.get("same_error_locus")
        ),
        "same_error_mechanism": (
            None if theory is None else theory.get("same_error_mechanism")
        ),
        "same_error_all3": same_error_all3,
        "judge_failed": None if theory is None else theory.get("judge_failed"),
        "gold_judge_error": "" if theory is None else theory.get("gold_judge_error", ""),
        "pred_judge_error": "" if theory is None else theory.get("pred_judge_error", ""),
        "gold_code": None if theory is None else theory.get("gold_code"),
        "pred_code": None if theory is None else theory.get("pred_code"),
    }


def _load_existing_detached_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"record must be object at {path}:{line_number}")
            uid = str(record.get("uid", "") or "")
            if not uid:
                raise ValueError(f"record missing uid at {path}:{line_number}")
            if uid in seen_uids:
                raise ValueError(f"duplicate uid in existing detached eval output: {uid}")
            seen_uids.add(uid)
            records.append(record)
    return records


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def _write_detached_eval_progress(
    progress_path: Path,
    expected_rows: int,
    completed_rows: int,
    pending_rows: int,
    status: str,
) -> None:
    write_json(
        progress_path,
        {
            "status": status,
            "expected_rows": expected_rows,
            "completed_rows": completed_rows,
            "pending_rows": pending_rows,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def build_detached_eval_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    rouge_values = [
        float(row["rougeL"])
        for row in records
        if row.get("rougeL") is not None
    ]
    cos_values = [
        float(row["cosine_similarity"])
        for row in records
        if row.get("cosine_similarity") is not None
    ]

    correctness_rows = [
        row for row in records if row["official_correctness_match"] is not None
    ]
    correctness_matches = sum(
        1 for row in correctness_rows if bool(row["official_correctness_match"])
    )
    correctness_parse_failures = sum(
        1
        for row in correctness_rows
        if row["official_pred_correctness_label"] not in {"correct", "incorrect", "na"}
    )
    gt_correctness_counter = Counter(
        str(row["official_gt_correctness_label"]) for row in correctness_rows
    )
    pred_correctness_counter = Counter(
        str(row["official_pred_correctness_label"]) for row in correctness_rows
    )

    theory_rows = [row for row in records if row["judge_failed"] is not None]
    successful_theory_rows = [row for row in theory_rows if row["judge_failed"] is False]
    failed_theory_rows = [row for row in theory_rows if row["judge_failed"] is True]
    gold_official_incorrect_rows = [
        row for row in theory_rows if row["official_gt_correctness_label"] == "incorrect"
    ]
    pred_official_incorrect_rows = [
        row for row in theory_rows if row["official_pred_correctness_label"] == "incorrect"
    ]
    both_official_incorrect_rows = [
        row
        for row in theory_rows
        if row["official_gt_correctness_label"] == "incorrect"
        and row["official_pred_correctness_label"] == "incorrect"
    ]
    gold_codable_rows = [
        row for row in successful_theory_rows if row["gold_has_codable_math_error"] is True
    ]
    pred_codable_rows = [
        row for row in successful_theory_rows if row["pred_has_codable_math_error"] is True
    ]
    both_codable_rows = [
        row
        for row in successful_theory_rows
        if row["gold_has_codable_math_error"] is True
        and row["pred_has_codable_math_error"] is True
    ]
    same_knowledge_count = sum(1 for row in both_codable_rows if bool(row["same_knowledge_type"]))
    same_locus_count = sum(1 for row in both_codable_rows if bool(row["same_error_locus"]))
    same_mechanism_count = sum(
        1 for row in both_codable_rows if bool(row["same_error_mechanism"])
    )
    same_all3_count = sum(1 for row in both_codable_rows if bool(row["same_error_all3"]))

    return {
        "n_rows": len(records),
        "text_similarity": {
            "cosine_similarity_mean": _mean(cos_values),
            "semantic_similarity_metric": "rougeL",
            "semantic_similarity_mean": _mean(rouge_values),
            "rougeL_mean": _mean(rouge_values),
        },
        "correctness": {
            "n_eligible_rows": len(correctness_rows),
            "match_count": correctness_matches,
            "match_rate": _ratio(correctness_matches, len(correctness_rows)),
            "parse_failure_count": correctness_parse_failures,
            "gold_distribution": dict(gt_correctness_counter),
            "pred_distribution": dict(pred_correctness_counter),
        },
        "same_error": {
            "n_theory_rows": len(theory_rows),
            "n_successful_theory_rows": len(successful_theory_rows),
            "n_failed_theory_rows": len(failed_theory_rows),
            "n_gold_officially_incorrect_rows": len(gold_official_incorrect_rows),
            "n_pred_officially_incorrect_rows": len(pred_official_incorrect_rows),
            "n_both_officially_incorrect_rows": len(both_official_incorrect_rows),
            "n_gold_codable_math_error_rows": len(gold_codable_rows),
            "n_pred_codable_math_error_rows": len(pred_codable_rows),
            "n_both_codable_math_error_rows": len(both_codable_rows),
            "error_realization_rate": _ratio(len(both_codable_rows), len(gold_codable_rows)),
            "same_error_rate": _ratio(same_all3_count, len(both_codable_rows)),
            "same_knowledge_type_rate": _ratio(same_knowledge_count, len(both_codable_rows)),
            "same_error_locus_rate": _ratio(same_locus_count, len(both_codable_rows)),
            "same_error_mechanism_rate": _ratio(
                same_mechanism_count,
                len(both_codable_rows),
            ),
            "same_error_all3_count": same_all3_count,
            "gold_label_distributions": {
                "knowledge_type": dict(
                    Counter(
                        str(row["gold_code"]["knowledge_type"])
                        for row in gold_codable_rows
                        if isinstance(row["gold_code"], dict)
                    )
                ),
                "error_locus": dict(
                    Counter(
                        str(row["gold_code"]["error_locus"])
                        for row in gold_codable_rows
                        if isinstance(row["gold_code"], dict)
                    )
                ),
                "error_mechanism": dict(
                    Counter(
                        str(row["gold_code"]["error_mechanism"])
                        for row in gold_codable_rows
                        if isinstance(row["gold_code"], dict)
                    )
                ),
            },
        },
    }


def write_detached_eval_outputs(
    output_dir: Path,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "detached_eval_results.jsonl", records)
    write_json(output_dir / "detached_eval_summary.json", summary)
    _write_detached_eval_csv(output_dir / "detached_eval_results.csv", records)
    (output_dir / "detached_eval_summary.md").write_text(
        _render_detached_eval_summary_markdown(summary),
        encoding="utf-8",
    )


def _evaluate_single_correctness_row(
    client: OpenAICompatTextClient,
    row: dict[str, Any],
) -> dict[str, Any]:
    gt_label = _get_gt_correctness_label(row)
    if gt_label == "na":
        raise ValueError("gt correctness is na and should not be judged")
    prompt = _build_official_correctness_user_prompt(row, gt_label)
    result_text = client.chat_text(
        system_prompt=OFFICIAL_CORRECTNESS_SYSTEM_PROMPT,
        user_prompt=prompt,
    )
    pred_label = _parse_official_pred_correctness_label(result_text)
    if gt_label == "correct":
        match = pred_label == "correct"
    elif gt_label == "incorrect":
        match = pred_label == "incorrect"
    else:
        match = None
    return {
        "uid": _row_uid(row),
        "gt_correctness_label": gt_label,
        "pred_correctness_label": pred_label,
        "correctness_match": match,
        "judge_raw": result_text,
    }


def _build_official_correctness_user_prompt(
    row: dict[str, Any],
    gt_correctness_label: str,
) -> str:
    prompt = _build_official_llm_prompt(row)
    prompt += (
        f"\n\nGround-truth next student turn:\n{str(row.get('gt_turn', '') or '')}"
        f"\nCorrectness: {gt_correctness_label}\n\nCandidate next student turn:\n"
        f"{str(row.get('pred_turn', '') or '')}"
    )
    return prompt


def _build_official_llm_prompt(row: dict[str, Any]) -> str:
    question = _format_official_question(row)
    prompt = f"Question:\n{question}\n\nConversation History:"
    turns = row.get("turns")
    if not isinstance(turns, list):
        turns = []
    ending_turn = int(row["turn_idx"])
    for idx, turn in enumerate(turns[:ending_turn]):
        if not isinstance(turn, dict):
            continue
        role_title = "Student" if str(turn.get("role", "")) == "student" else "Tutor"
        prompt += f"\nTurn {idx + 1} ({role_title}): {str(turn.get('content', '') or '')}"
    return prompt


def _format_official_question(row: dict[str, Any]) -> str:
    question = str(row.get("question", "") or "")
    annotation = row.get("question_annotation")
    if not isinstance(annotation, dict) or not bool(annotation.get("solvable")):
        return question
    correct_option = annotation.get("correct_option")
    try:
        correct_option_int = int(correct_option)
    except Exception:
        correct_option_int = 0
    if 1 <= correct_option_int <= len(LETTERS):
        question += f"\nCorrect Answer: {LETTERS[correct_option_int - 1]}"
    question += f"\nSolution: {str(annotation.get('solution', '') or '')}\n"
    for idx in range(1, 5):
        explanation = str(annotation.get(f"option_{idx}_explanation", "") or "")
        question += f"Answer {LETTERS[idx - 1]} Explanation: {explanation}"
        if idx < 4:
            question += "\n"
    return question


def _get_gt_correctness_label(row: dict[str, Any]) -> str:
    correctness = row.get("correctness")
    if not isinstance(correctness, dict):
        return "na"
    turn_key = f"turn {int(row['turn_idx']) + 1}"
    turn_entry = correctness.get(turn_key)
    if not isinstance(turn_entry, dict):
        return "na"
    value = turn_entry.get("correct")
    if value is True:
        return "correct"
    if value is False:
        return "incorrect"
    return "na"


def _parse_official_pred_correctness_label(raw_text: str) -> str | None:
    text = str(raw_text or "").strip().lower()
    if text == "correct":
        return "correct"
    if "incorrect" in text:
        return "incorrect"
    if text == "na":
        return "na"
    return None


def _row_uid(row: dict[str, Any]) -> str:
    return f"{int(row['dialogue_idx'])}:{int(row['turn_idx'])}:{str(row.get('key', '') or '')}"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _ratio(count: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return count / denominator


def _write_detached_eval_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "uid",
        "key",
        "dialogue_idx",
        "turn_idx",
        "rougeL",
        "cosine_similarity",
        "official_gt_correctness_label",
        "official_pred_correctness_label",
        "official_correctness_match",
        "gold_has_codable_math_error",
        "pred_has_codable_math_error",
        "same_knowledge_type",
        "same_error_locus",
        "same_error_mechanism",
        "same_error_all3",
        "judge_failed",
        "gold_judge_error",
        "pred_judge_error",
        "gt_turn",
        "pred_turn",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow({field: row.get(field) for field in fieldnames})


def _render_detached_eval_summary_markdown(summary: dict[str, Any]) -> str:
    def _fmt(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:.4f}"

    lines = [
        "# Detached Eval Summary",
        "",
        "## Core Metrics",
        "",
        f"- Correctness match rate: {_fmt(summary['correctness']['match_rate'])}",
        f"- Same-error rate: {_fmt(summary['same_error']['same_error_rate'])}",
        f"- Cosine similarity mean: {_fmt(summary['text_similarity']['cosine_similarity_mean'])}",
        f"- Semantic similarity mean (ROUGE-L): {_fmt(summary['text_similarity']['semantic_similarity_mean'])}",
        "",
        "## Correctness",
        "",
        f"- Eligible rows: {summary['correctness']['n_eligible_rows']}",
        f"- Match count: {summary['correctness']['match_count']}",
        f"- Parse failures: {summary['correctness']['parse_failure_count']}",
        f"- Gold distribution: {json.dumps(summary['correctness']['gold_distribution'], ensure_ascii=False)}",
        f"- Pred distribution: {json.dumps(summary['correctness']['pred_distribution'], ensure_ascii=False)}",
        "",
        "## Same Error",
        "",
        f"- Gold officially incorrect rows: {summary['same_error']['n_gold_officially_incorrect_rows']}",
        f"- Pred officially incorrect rows: {summary['same_error']['n_pred_officially_incorrect_rows']}",
        f"- Both officially incorrect rows: {summary['same_error']['n_both_officially_incorrect_rows']}",
        f"- Gold codable math-error rows: {summary['same_error']['n_gold_codable_math_error_rows']}",
        f"- Pred codable math-error rows: {summary['same_error']['n_pred_codable_math_error_rows']}",
        f"- Both codable math-error rows: {summary['same_error']['n_both_codable_math_error_rows']}",
        f"- Error realization rate: {_fmt(summary['same_error']['error_realization_rate'])}",
        f"- Same knowledge type rate: {_fmt(summary['same_error']['same_knowledge_type_rate'])}",
        f"- Same error locus rate: {_fmt(summary['same_error']['same_error_locus_rate'])}",
        f"- Same error mechanism rate: {_fmt(summary['same_error']['same_error_mechanism_rate'])}",
        "",
    ]
    return "\n".join(lines)


def _post_json(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_s: float,
) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_s) as resp:
            resp_bytes = resp.read()
    except HTTPError as exc:
        err_payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP error status={exc.code}, body={err_payload[:800]}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"URL error: {exc}") from exc

    try:
        parsed = json.loads(resp_bytes.decode("utf-8"))
    except Exception as exc:
        snippet = resp_bytes[:500].decode("utf-8", errors="replace")
        raise ValueError(f"invalid JSON response: {snippet!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"unexpected response shape: {type(parsed).__name__}")
    return parsed
