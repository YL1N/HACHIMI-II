from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout_s: float


class LLMJSONError(ValueError):
    pass


def call_openai_compatible_json(
    messages: list[dict[str, Any]],
    image_path: str | None,
    config: LLMConfig,
) -> dict[str, Any]:
    payload_messages = _with_vision_payload(messages, image_path)
    body = {
        "model": config.model,
        "messages": payload_messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    url = config.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = urllib.request.Request(
        url=url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_s) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {error.code}: {detail}") from error
    parsed_response = json.loads(response_body)
    try:
        content = parsed_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise LLMJSONError("LLM response missing choices[0].message.content") from error
    return parse_llm_json(content)


def parse_llm_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = _strip_code_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMJSONError(f"LLM content is not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise LLMJSONError("LLM JSON must be an object")
    predicted_answer = parsed.get("predicted_answer")
    student_response = parsed.get("student_response")
    if not isinstance(predicted_answer, str) or not predicted_answer.strip():
        raise LLMJSONError("LLM JSON missing non-empty predicted_answer")
    if not isinstance(student_response, str) or not student_response.strip():
        raise LLMJSONError("LLM JSON missing non-empty student_response")
    return {
        "predicted_answer": predicted_answer.strip(),
        "student_response": student_response.strip(),
    }


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if not lines or not lines[0].startswith("```"):
        return text
    if lines[-1].strip() == "```":
        lines = lines[1:-1]
    else:
        lines = lines[1:]
    return "\n".join(lines).strip()


def _with_vision_payload(messages: list[dict[str, Any]], image_path: str | None) -> list[dict[str, Any]]:
    if not image_path:
        return messages
    image_url = _image_data_url(Path(image_path))
    converted = [dict(message) for message in messages]
    user_index = len(converted) - 1
    original_text = str(converted[user_index].get("content", ""))
    converted[user_index]["content"] = [
        {"type": "text", "text": original_text},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
    return converted


def _image_data_url(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(str(path))
    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
