from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_s: float = 120.0
    temperature: float = 0.2
    max_tokens: int = 1600
    response_format_json: bool = False


def extract_first_json_object(text: str) -> dict[str, Any]:
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


class OpenAICompatClient:
    def __init__(self, config: LLMConfig):
        self._cfg = config
        self._chat_url = config.base_url.rstrip("/") + "/chat/completions"

    def build_chat_payload(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "temperature": self._cfg.temperature,
            "max_tokens": self._cfg.max_tokens,
            "messages": messages,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self._cfg.response_format_json:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload = self.build_chat_payload(messages)
        content = self._extract_content(self._post_json(payload))
        try:
            return extract_first_json_object(content)
        except ValueError:
            repair_payload = dict(payload)
            repair_payload["messages"] = messages + [
                {
                    "role": "user",
                    "content": "Your previous reply was not valid JSON. Return exactly one JSON object.",
                }
            ]
            return extract_first_json_object(self._extract_content(self._post_json(repair_payload)))

    def chat_json_with_image(self, system_prompt: str, user_prompt: str, image_path: str | Path) -> dict[str, Any]:
        image_url = self._image_to_data_url(Path(image_path))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ]
        payload = self.build_chat_payload(messages)
        content = self._extract_content(self._post_json(payload))
        try:
            return extract_first_json_object(content)
        except ValueError:
            repair_payload = dict(payload)
            repair_payload["messages"] = messages + [
                {
                    "role": "user",
                    "content": "Your previous reply was not valid JSON. Return exactly one JSON object.",
                }
            ]
            return extract_first_json_object(self._extract_content(self._post_json(repair_payload)))

    def _image_to_data_url(self, image_path: Path) -> str:
        if not image_path.exists():
            raise FileNotFoundError(f"image not found: {image_path}")
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _extract_content(self, body: dict[str, Any]) -> str:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"malformed chat completion response: {body}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"empty content from model response: {body}")
        return content

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._cfg.api_key:
            headers["Authorization"] = f"Bearer {self._cfg.api_key}"
        request = Request(self._chat_url, data=raw, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self._cfg.timeout_s) as response:
                raw_body = response.read()
        except HTTPError as exc:
            err_payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP error status={exc.code}, body={err_payload[:800]}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM URL error: {exc}") from exc
        parsed = json.loads(raw_body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"unexpected LLM response type: {type(parsed).__name__}")
        return parsed
