from __future__ import annotations

import base64
import json
import mimetypes
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .llm_client import extract_first_json_object


ANSWER_VALUES = ("1", "2", "3", "4")
LETTER_TO_VALUE = {"A": "1", "B": "2", "C": "3", "D": "4"}


@dataclass(frozen=True)
class ImageDirectQuestion:
    question_id: str
    image_path: Path
    gold_answer: str
    empirical_accuracy: float
    subject_names: list[str]
    subject_top: str
    subject_leaf: str


@dataclass(frozen=True)
class VisionLLMConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_s: float = 180.0
    temperature: float = 0.0
    max_tokens: int = 1024


def normalize_answer_value(value: object) -> str:
    answer = str(value).strip().upper()
    if answer in LETTER_TO_VALUE:
        return LETTER_TO_VALUE[answer]
    if answer in ANSWER_VALUES:
        return answer
    raise ValueError(f"selected_answer must be one of 1/2/3/4 or A/B/C/D, got={value!r}")


def extract_prediction_payload(raw_text: str) -> dict[str, Any]:
    payload = extract_first_json_object(raw_text)
    selected_answer = normalize_answer_value(payload.get("selected_answer"))
    confidence = str(payload.get("confidence") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if not confidence:
        raise ValueError(f"empty confidence in model output: {raw_text[:300]!r}")
    if not reason:
        raise ValueError(f"empty reason in model output: {raw_text[:300]!r}")
    return {
        "selected_answer": selected_answer,
        "confidence": confidence,
        "reason": reason,
    }


def load_questions(config_path: Path, max_questions: int | None = None) -> list[ImageDirectQuestion]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    dataset_root = Path(str(config["source_dataset_root"]))
    raw_questions = config.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("config requires non-empty questions list")

    questions: list[ImageDirectQuestion] = []
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise ValueError("question row must be an object")
        correct_answers = raw.get("train_correct_answers")
        if not isinstance(correct_answers, list) or len(correct_answers) != 1:
            raise ValueError(f"question requires exactly one gold answer: {raw.get('QuestionId')}")
        image_rel = str(raw.get("image_path") or "").strip()
        if not image_rel:
            raise ValueError(f"question missing image_path: {raw.get('QuestionId')}")
        image_path = dataset_root / image_rel
        if not image_path.exists():
            raise FileNotFoundError(f"question image not found: {image_path}")
        questions.append(
            ImageDirectQuestion(
                question_id=str(raw["QuestionId"]),
                image_path=image_path,
                gold_answer=normalize_answer_value(correct_answers[0]),
                empirical_accuracy=float(raw.get("empirical_accuracy_all_train", 0.0)),
                subject_names=[str(value) for value in raw.get("subject_names", [])],
                subject_top=str(raw.get("subject_top") or "unknown"),
                subject_leaf=str(raw.get("subject_leaf") or "unknown"),
            )
        )
        if max_questions is not None and len(questions) >= max_questions:
            break
    return questions


def image_to_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_prompt() -> str:
    return (
        "Solve the math multiple-choice question shown in the image. "
        "The answer options are labeled A, B, C, D. Map A to \"1\", B to \"2\", C to \"3\", and D to \"4\". "
        "Use only the image. Return exactly one JSON object with keys: "
        "selected_answer, confidence, reason. selected_answer must be \"1\", \"2\", \"3\", or \"4\". "
        "confidence must be high, medium, or low. reason must be one short sentence under 20 words."
    )


def call_vision_llm(question: ImageDirectQuestion, config: VisionLLMConfig) -> str:
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_prompt()},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(question.image_path)}},
                ],
            }
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = Request(config.base_url.rstrip("/") + "/chat/completions", data=raw, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=config.timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP error status={exc.code}, body={error_body[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"LLM URL error: {exc}") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"malformed chat completion response: {body}") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"empty content from model response: {body}")
    return content


def compute_metrics(rows: list[dict[str, Any]], n_questions: int, n_failures: int) -> dict[str, Any]:
    correct = sum(1 for row in rows if row["selected_answer"] == row["gold_answer"])
    return {
        "n_questions": n_questions,
        "n_predictions": len(rows),
        "n_failures": n_failures,
        "accuracy": correct / len(rows) if rows else None,
        "correct": correct,
        "selected_answer_counts": dict(Counter(str(row["selected_answer"]) for row in rows)),
        "gold_answer_counts": dict(Counter(str(row["gold_answer"]) for row in rows)),
    }


def count_unresolved_failure_ids(
    prediction_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
) -> set[str]:
    predicted_ids = {str(row["question_id"]) for row in prediction_rows}
    failed_ids = {str(row["question_id"]) for row in failure_rows}
    return failed_ids - predicted_ids
