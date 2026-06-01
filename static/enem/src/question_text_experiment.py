from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_loading import ANSWER_SPACE, load_json
from .image_direct_solve import EnemImageDirectQuestion, normalize_answer
from .llm_client import OpenAICompatClient


def parse_translation_payload(payload: dict[str, Any]) -> dict[str, str]:
    question_text = str(payload.get("question_text") or "").strip()
    notes = str(payload.get("translation_notes") or "").strip()
    if len(question_text) < 80:
        raise ValueError("question_text is too short")
    return {
        "question_text": question_text,
        "translation_notes": notes,
    }


def translate_question_image(question: EnemImageDirectQuestion, llm: OpenAICompatClient) -> dict[str, str]:
    system_prompt = (
        "You translate exam items for a controlled research experiment. "
        "Return exactly one JSON object. Do not solve the question."
    )
    user_prompt = (
        "Translate the attached Portuguese ENEM natural-science multiple-choice question into English. "
        "Preserve all answer labels A, B, C, D, E; preserve numbers, units, equations, symbols, tables, graph labels, and named entities. "
        "If a figure, table, or diagram is needed, describe all visible information in English without adding new facts. "
        "Do not reveal or infer the correct answer. "
        "Return JSON with keys: question_text, translation_notes. "
        "question_text must contain the full translated stem and all options."
    )
    return parse_translation_payload(llm.chat_json_with_image(system_prompt, user_prompt, question.image_path))


def load_question_text_manifest(path: str | Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = load_json_line(line)
            rows[str(row["question_id"])] = {
                "question_text": str(row["question_text"]),
                "question_text_language": str(row.get("question_text_language") or "en"),
            }
    return rows


def load_json_line(line: str) -> dict[str, Any]:
    import json

    parsed = json.loads(line)
    if not isinstance(parsed, dict):
        raise ValueError("jsonl row must be an object")
    return parsed


def solve_translated_question_directly(
    question: EnemImageDirectQuestion,
    question_text: str,
    llm: OpenAICompatClient,
) -> dict[str, str]:
    system_prompt = (
        "You are solving an ENEM natural-science multiple-choice question from an English translation. "
        "Use only the translated question text. Do not simulate a student. Return exactly one JSON object."
    )
    user_prompt = f"""
Question text:
{question_text}

Choose the best answer among A, B, C, D, E.
Return JSON with keys: selected_answer, confidence, reason.
selected_answer must be one of A, B, C, D, E.
confidence must be high, medium, or low.
reason must be one short sentence.
"""
    payload = llm.chat_json(system_prompt, user_prompt)
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


def solve_translated_question_with_image_directly(
    question: EnemImageDirectQuestion,
    question_text: str,
    llm: OpenAICompatClient,
) -> dict[str, str]:
    system_prompt = (
        "You are solving an ENEM natural-science multiple-choice question. "
        "Use the English translation as the main text and use the attached original image only for visual information, "
        "such as figures, graphs, tables, formulas, spatial layout, and any details missing from the translation. "
        "Do not simulate a student. Return exactly one JSON object."
    )
    user_prompt = f"""
English translation of the question:
{question_text}

The attached image is the original Portuguese question crop. Use it to inspect diagrams, graphs, formulas, tables, units, and visual context.
Choose the best answer among A, B, C, D, E.
Return JSON with keys: selected_answer, confidence, reason.
selected_answer must be one of A, B, C, D, E.
confidence must be high, medium, or low.
reason must be one short sentence.
"""
    payload = llm.chat_json_with_image(system_prompt, user_prompt, question.image_path)
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


def compute_text_direct_metrics(rows: list[dict[str, Any]], n_questions: int, n_failures: int) -> dict[str, Any]:
    from .image_direct_solve import compute_direct_metrics

    return compute_direct_metrics(rows, n_questions=n_questions, n_failures=n_failures)
