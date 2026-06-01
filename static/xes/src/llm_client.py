from __future__ import annotations

import json
import re
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JSON_REPAIR_RETRY_PROMPT = (
    "Your previous reply was not valid JSON or was truncated. "
    "Regenerate the answer from scratch. Return exactly one complete JSON object "
    "and nothing else. Ensure all braces and quotes are closed."
)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_s: float = 120.0
    temperature: float = 0.2
    max_tokens: int = 800
    response_format_json: bool = False


def _extract_first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, end = decoder.raw_decode(text[idx:])
        except JSONDecodeError:
            continue
        if isinstance(obj, dict):
            _ = end
            return obj
    raise ValueError(f"no JSON object found in model output: {text[:300]!r}")


def _extract_partial_string_fields(text: str, required_keys: list[str]) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    for key in required_keys:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*"', text)
        if match is None:
            raise ValueError(f"missing key in partial JSON salvage: {key}")
        cursor = match.end()
        chars: list[str] = []
        escaped = False
        while cursor < len(text):
            ch = text[cursor]
            cursor += 1
            if escaped:
                chars.append(ch)
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                chars.append(ch)
                continue
            if ch == '"':
                break
            chars.append(ch)
        raw_value = "".join(chars).strip()
        if not raw_value:
            raise ValueError(f"empty value in partial JSON salvage: {key}")
        extracted[key] = (
            raw_value.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        )
    return extracted


class OpenAICompatClient:
    def __init__(self, config: LLMConfig):
        self._cfg = config
        self._chat_url = config.base_url.rstrip("/") + "/chat/completions"

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload = {
            "model": self._cfg.model,
            "temperature": self._cfg.temperature,
            "max_tokens": self._cfg.max_tokens,
            "messages": base_messages,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self._cfg.response_format_json:
            payload["response_format"] = {"type": "json_object"}
        body = self._post_json(payload)
        content = self._extract_content(body)
        try:
            return _extract_first_json_object(content)
        except ValueError as first_exc:
            repair_payload = {
                "model": self._cfg.model,
                "temperature": self._cfg.temperature,
                "max_tokens": self._cfg.max_tokens,
                "messages": base_messages
                + [{"role": "user", "content": JSON_REPAIR_RETRY_PROMPT}],
                "chat_template_kwargs": {"enable_thinking": False},
            }
            if self._cfg.response_format_json:
                repair_payload["response_format"] = {"type": "json_object"}
            repair_body = self._post_json(repair_payload)
            repair_content = self._extract_content(repair_body)
            try:
                return _extract_first_json_object(repair_content)
            except ValueError as second_exc:
                if partial_string_keys:
                    for candidate in [repair_content, content]:
                        try:
                            return _extract_partial_string_fields(
                                candidate,
                                partial_string_keys,
                            )
                        except ValueError:
                            continue
                raise ValueError(
                    "no JSON object found after one explicit JSON repair retry. "
                    f"first_content={content[:300]!r} "
                    f"repair_content={repair_content[:300]!r}"
                ) from second_exc

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

        try:
            parsed = json.loads(resp_bytes.decode("utf-8"))
        except Exception as exc:
            snippet = resp_bytes[:500].decode("utf-8", errors="replace")
            raise ValueError(f"invalid JSON response from LLM endpoint: {snippet!r}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"unexpected response shape from LLM endpoint: {type(parsed).__name__}")
        return parsed
