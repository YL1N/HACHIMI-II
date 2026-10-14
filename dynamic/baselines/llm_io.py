from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout_s: float


class OpenAICompatClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._endpoint = self._build_endpoint(config.base_url)

    def complete_json(self, system_message: str, user_prompt: str) -> str:
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
        payload = json.loads(raw)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"unexpected LLM response shape: {payload}") from exc
        if not isinstance(content, str):
            raise ValueError("LLM response content is not a string")
        return content

    @staticmethod
    def _build_endpoint(base_url: str) -> str:
        cleaned = base_url.strip().rstrip("/")
        if not cleaned:
            raise ValueError("llm_base_url is required")
        if cleaned.endswith("/chat/completions"):
            return cleaned
        return f"{cleaned}/chat/completions"


def parse_student_reply_json(raw_content: str) -> str:
    try:
        payload: Any = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON output must be an object")
    extra_keys = sorted(set(payload) - {"student_reply"})
    missing_keys = sorted({"student_reply"} - set(payload))
    if missing_keys or extra_keys:
        raise ValueError(
            f"LLM JSON keys mismatch; missing={missing_keys} extra={extra_keys}"
        )
    reply = payload["student_reply"]
    if not isinstance(reply, str):
        raise ValueError("student_reply must be a string")
    return reply.strip()
