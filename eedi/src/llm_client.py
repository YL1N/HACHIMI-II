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
SCHEMA_REPAIR_RETRY_PROMPT = (
    "Your previous reply violated the required JSON schema or field typing rules. "
    "Schema problem: {validation_error}\n"
    "Regenerate the full JSON object from scratch.\n"
    "Hard rules:\n"
    "- Top-level keys must match required_schema exactly.\n"
    "- Do not omit required fields.\n"
    "- Do not wrap scalar enum fields in lists.\n"
    "- Return exactly one JSON object and nothing else."
)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout_s: float = 120.0
    temperature: float = 0.2
    max_tokens: int = 800


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
        return self._chat_json_from_messages(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            partial_string_keys=partial_string_keys,
        )

    def retry_schema_json(
        self,
        system_prompt: str,
        user_prompt: str,
        previous_reply: object,
        validation_error: str,
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        if isinstance(previous_reply, str):
            assistant_content = previous_reply
        else:
            assistant_content = json.dumps(previous_reply, ensure_ascii=False)
        return self._chat_json_from_messages(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_content},
                {
                    "role": "user",
                    "content": SCHEMA_REPAIR_RETRY_PROMPT.format(
                        validation_error=validation_error
                    ),
                },
            ],
            partial_string_keys=partial_string_keys,
        )

    def _chat_json_from_messages(
        self,
        messages: list[dict[str, str]],
        partial_string_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self._cfg.model,
            "temperature": self._cfg.temperature,
            "max_tokens": self._cfg.max_tokens,
            "messages": messages,
        }
        if "dashscope.aliyuncs.com" in self._cfg.base_url:
            payload["enable_thinking"] = False
        body = self._post_json(payload)
        content = self._extract_content(body)
        try:
            return _extract_first_json_object(content)
        except ValueError as first_exc:
            repair_payload = {
                "model": self._cfg.model,
                "temperature": self._cfg.temperature,
                "max_tokens": self._cfg.max_tokens,
                "messages": messages
                + [{"role": "user", "content": JSON_REPAIR_RETRY_PROMPT}],
            }
            if "dashscope.aliyuncs.com" in self._cfg.base_url:
                repair_payload["enable_thinking"] = False
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
        request = Request(
            self._chat_url,
            data=raw,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._cfg.api_key}",
            },
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


def require_object(value: object, context_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            f"{context_name} must be a JSON object, got {type(value).__name__}: {value!r}"
        )
    return value


def require_keys(
    value: object,
    required_keys: tuple[str, ...],
    context_name: str,
) -> dict[str, Any]:
    obj = require_object(value, context_name)
    missing = [key for key in required_keys if key not in obj]
    if missing:
        got_keys = sorted(str(key) for key in obj.keys())
        raise ValueError(
            f"{context_name} missing required keys: {missing}; got_keys={got_keys}"
        )
    return obj
