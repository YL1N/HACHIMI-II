from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class WeakLLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout_s: float = 120.0
    temperature: float = 0.0
    max_tokens: int = 256
    response_format_json: bool = False
    enable_thinking: bool | None = None


def _extract_first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
        except JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"no JSON object found in model output: {text[:300]!r}")


class WeakOpenAICompatClient:
    def __init__(self, config: WeakLLMConfig):
        self._cfg = config
        self._chat_url = config.base_url.rstrip("/") + "/chat/completions"

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "temperature": self._cfg.temperature,
            "max_tokens": self._cfg.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self._cfg.response_format_json:
            payload["response_format"] = {"type": "json_object"}
        if self._cfg.enable_thinking is not None:
            payload["enable_thinking"] = self._cfg.enable_thinking
        body = self._post_json(payload)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"malformed chat completion response: {body}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"empty content from model response: {body}")
        return _extract_first_json_object(content)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._cfg.api_key}",
        }
        request = Request(
            self._chat_url,
            data=raw,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._cfg.timeout_s) as resp:
                resp_bytes = resp.read()
        except HTTPError as exc:
            err_payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LLM HTTP error status={exc.code}, body={err_payload[:800]}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"LLM URL error: {exc}") from exc
        parsed = json.loads(resp_bytes.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"unexpected response shape from LLM endpoint: {type(parsed).__name__}")
        return parsed
