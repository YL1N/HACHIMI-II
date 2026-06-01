from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_s: float = 120.0
    temperature: float = 0.0
    max_tokens: int = 600


class OpenAICompatClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._chat_url = config.base_url.rstrip("/") + "/chat/completions"

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        content = self._extract_content(self._post_json(payload))
        try:
            return _extract_json_object(content)
        except ValueError:
            repair_payload = dict(payload)
            repair_payload["messages"] = payload["messages"] + [
                {
                    "role": "user",
                    "content": "Your previous reply was not valid JSON. Return exactly one JSON object.",
                }
            ]
            repair_content = self._extract_content(self._post_json(repair_payload))
            return _extract_json_object(repair_content)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        request = Request(self._chat_url, data=raw, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self._config.timeout_s) as response:
                body = response.read()
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP error status={exc.code}, body={message[:800]}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM URL error: {exc}") from exc
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"unexpected LLM response type: {type(parsed).__name__}")
        return parsed

    @staticmethod
    def _extract_content(body: dict[str, Any]) -> str:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"malformed LLM response: {body}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"empty LLM content: {body}")
        return content


@dataclass(frozen=True)
class KhanTurnSample:
    sample_id: str
    test_id: str
    math_level: str
    dialogue_turn_count: int
    target_turn_idx: int
    history: list[dict[str, str]]
    tutor_turn: str
    gt_student_turn: str


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"no JSON object found in model output: {text[:300]!r}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")
        file.flush()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_turn_samples(dataset_path: Path) -> list[KhanTurnSample]:
    dialogues = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(dialogues, list):
        raise ValueError("CoMTA dataset must be a JSON list")
    samples: list[KhanTurnSample] = []
    for dialogue_index, dialogue in enumerate(dialogues):
        if not isinstance(dialogue, dict):
            raise ValueError(f"dialogue index={dialogue_index} is not an object")
        turns = dialogue.get("data")
        if not isinstance(turns, list):
            raise ValueError(f"dialogue index={dialogue_index} has no data list")
        test_id = str(dialogue.get("test_id", dialogue_index)).strip()
        math_level = str(dialogue.get("math_level", "") or "").strip()
        normalized_turns: list[dict[str, str]] = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role", "") or "").strip()
            content = " ".join(str(turn.get("content", "") or "").split()).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized_turns.append({"role": role, "content": content})
        for turn_idx, turn in enumerate(normalized_turns):
            if turn["role"] != "user" or turn_idx == 0:
                continue
            previous_turn = normalized_turns[turn_idx - 1]
            if previous_turn["role"] != "assistant":
                continue
            samples.append(
                KhanTurnSample(
                    sample_id=f"{test_id}_turn_{turn_idx}",
                    test_id=test_id,
                    math_level=math_level,
                    dialogue_turn_count=len(normalized_turns),
                    target_turn_idx=turn_idx,
                    history=normalized_turns[:turn_idx],
                    tutor_turn=previous_turn["content"],
                    gt_student_turn=turn["content"],
                )
            )
    if not samples:
        raise ValueError("no assistant->user turn-level samples built")
    return samples


SYSTEM_PROMPT = """You label one real student turn in a math tutoring dialogue.
Return exactly one compact JSON object and no markdown.

Allowed final labels:
- correct
- incorrect
- na

Use EEDI-style turn-level correctness:
- correct: the target student turn correctly satisfies the immediately preceding tutor's local math request.
- incorrect: the tutor requested a math answer/step/judgment, but the student response is wrong, missing, confused, asks for explanation instead of answering, or gives an invalid method.
- na: the preceding tutor turn did not request a math answer/step/judgment, or the target student turn is only social/preference/planning/affect.

Important rules:
- Judge only the target student turn relative to the immediately preceding tutor turn and visible history.
- Do not use future turns.
- If the tutor asks an intermediate step, judge that exact intermediate step, not the final answer to the whole problem.
- If the tutor asks a final answer, judge the final answer.
- If the tutor requests a math answer/step/judgment and the student asks "what do you mean?", "can you explain?", "I don't know", or similar, label incorrect.
- Direction words matter: if the expected local answer is "left" and the student says "right", label incorrect.
- If the student gives a wrong attempt and then explicitly self-corrects in the same turn, judge the final self-corrected answer.
- If the student gives both a wrong answer and a correct answer without clear self-correction, label incorrect.
- If the student gives an answer and then adds a social/unrelated sentence, judge the answer part first.
- If the tutor only states the answer/explanation and the student merely says "yes", "ok", "yeah", or similar acknowledgement, label na unless the tutor explicitly asks for a math judgment.
- If a visible problem context exists and the tutor asks "How can I help?" or "Do you have an idea how to start?", a student saying they do not know how to start is incorrect.

Return exactly these keys:
- tutor_request_type: one of math_final_answer, math_intermediate_step, math_explanation, math_judgment, non_math
- requested_local_criterion: a short phrase describing the expected local answer/criterion, or "none" for non_math
- student_response_type: one of answers_request, asks_clarification, says_dont_know, social_or_preference, unrelated
- student_satisfies_criterion: true, false, or null
- label: correct, incorrect, or na
- confidence: low, medium, or high
- evidence: one short sentence, at most 20 words

Consistency constraints:
- If tutor_request_type is non_math, label must be na.
- If tutor_request_type is not non_math and student_response_type is asks_clarification or says_dont_know, label must be incorrect.
- If the student gives a number, expression, operation, method, or direct answer candidate to a math request, student_response_type must be answers_request.
- If student_satisfies_criterion is true, label must be correct.
- If student_satisfies_criterion is false and tutor_request_type is not non_math, label must be incorrect.
- evidence must directly support label and must not say the opposite label.
"""


def build_label_prompt(sample: KhanTurnSample) -> str:
    history_lines = []
    for idx, turn in enumerate(sample.history):
        role = "Tutor" if turn["role"] == "assistant" else "Student"
        history_lines.append(f"Turn {idx + 1} ({role}): {turn['content']}")
    return (
        f"Math level: {sample.math_level}\n\n"
        "Visible dialogue history before the target student turn:\n"
        + "\n".join(history_lines)
        + "\n\nTarget student turn to label:\n"
        + sample.gt_student_turn
        + "\n\nReturn JSON only."
    )


def parse_label(parsed: dict[str, Any]) -> tuple[str, str, list[str], dict[str, object]]:
    request_type = str(parsed.get("tutor_request_type", "") or "").strip().lower()
    if request_type not in {
        "math_final_answer",
        "math_intermediate_step",
        "math_explanation",
        "math_judgment",
        "non_math",
    }:
        raise ValueError(f"invalid tutor_request_type={request_type!r}")
    criterion = str(parsed.get("requested_local_criterion", "") or "").strip()
    if not criterion:
        raise ValueError("requested_local_criterion cannot be empty")
    response_type = str(parsed.get("student_response_type", "") or "").strip().lower()
    if response_type not in {
        "answers_request",
        "asks_clarification",
        "says_dont_know",
        "social_or_preference",
        "unrelated",
    }:
        raise ValueError(f"invalid student_response_type={response_type!r}")
    raw_label = str(parsed.get("label", "") or "").strip().lower()
    if raw_label not in {"correct", "incorrect", "na"}:
        raise ValueError(f"label must be correct, incorrect, or na; got {raw_label!r}")
    satisfies_raw = parsed.get("student_satisfies_criterion")
    if satisfies_raw is None:
        satisfies: bool | None = None
    elif isinstance(satisfies_raw, bool):
        satisfies = satisfies_raw
    elif isinstance(satisfies_raw, str) and satisfies_raw.strip().lower() in {"true", "false", "null", "none"}:
        value = satisfies_raw.strip().lower()
        satisfies = True if value == "true" else False if value == "false" else None
    else:
        raise ValueError(f"student_satisfies_criterion must be true, false, or null; got {satisfies_raw!r}")
    confidence = str(parsed.get("confidence", "") or "").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        raise ValueError(f"confidence must be low, medium, or high; got {confidence!r}")
    evidence_raw = parsed.get("evidence")
    if isinstance(evidence_raw, str):
        rationale = [evidence_raw.strip()]
    elif isinstance(evidence_raw, list):
        rationale = [str(item).strip() for item in evidence_raw if str(item).strip()]
    else:
        rationale = []
    if not rationale:
        raise ValueError("evidence must be a non-empty string")
    evidence_text = " ".join(rationale).lower()
    if request_type == "non_math":
        label = "na"
    elif response_type in {"asks_clarification", "says_dont_know"}:
        label = "incorrect"
    elif satisfies is True:
        label = "correct"
    elif satisfies is False:
        label = "incorrect"
    else:
        raise ValueError("math request with answer-like response requires student_satisfies_criterion true or false")
    if label == "correct" and any(
        token in evidence_text
        for token in ["incorrect", "wrong", "not correct", "does not", "fails", "failed"]
    ):
        raise ValueError("evidence contradicts label=correct")
    if label == "incorrect" and any(
        token in evidence_text
        for token in ["is correct", "correctly answers", "mathematically correct", "accurate"]
    ):
        raise ValueError("evidence contradicts label=incorrect")
    return label, confidence, rationale[:1], {
        "tutor_request_type": request_type,
        "requested_local_criterion": criterion,
        "student_response_type": response_type,
        "student_satisfies_criterion": satisfies,
        "raw_model_label": raw_label,
    }


def _looks_like_direct_math_answer(text: str) -> bool:
    stripped = text.strip().lower()
    if re.fullmatch(r"[-+]?\d+(\.\d+)?(%|°)?", stripped):
        return True
    if re.search(r"\d+\s*/\s*\d+|[a-z]\s*=|[+\-*/=<>]|\\frac|\\div|\\times", stripped):
        return True
    math_words = {
        "add",
        "subtract",
        "multiply",
        "divide",
        "left",
        "right",
        "remainder",
        "factor",
        "multiple",
        "slope",
        "derivative",
        "integral",
    }
    return any(word in stripped.split() for word in math_words)


def label_one(sample: KhanTurnSample, client: OpenAICompatClient, max_attempts: int) -> dict[str, Any]:
    last_error = ""
    prompt = build_label_prompt(sample)
    for attempt_idx in range(max_attempts):
        try:
            parsed = client.chat_json(SYSTEM_PROMPT, prompt)
            label, confidence, rationale, decision = parse_label(parsed)
            if (
                decision["tutor_request_type"] != "non_math"
                and decision["student_response_type"] != "answers_request"
                and _looks_like_direct_math_answer(sample.gt_student_turn)
            ):
                raise ValueError("direct math-looking response to math request must use student_response_type=answers_request")
            return {
                **asdict(sample),
                **decision,
                "pseudo_correctness": label,
                "label_confidence": confidence,
                "label_rationale": rationale,
                "label_attempt": attempt_idx + 1,
            }
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(1 + attempt_idx)
    raise RuntimeError(f"labeling failed after {max_attempts} attempts: {last_error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Khan/CoMTA turn-level pseudo-correctness labels.")
    parser.add_argument("--dataset_path", default=str(ROOT / "CoMTA_dataset.json"))
    parser.add_argument("--output_dir", default=str(ROOT / "outputs" / "pseudo_correctness_qwen_20260522"))
    parser.add_argument("--llm_base_url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--llm_model", default=os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--llm_api_key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--timeout_s", type=float, default=120.0)
    parser.add_argument("--max_tokens", type=int, default=600)
    parser.add_argument("--max_concurrency", type=int, default=8)
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument("--max_attempts", type=int, default=3)
    parser.add_argument("--dry_run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    samples = build_turn_samples(Path(args.dataset_path))
    if args.max_samples is not None:
        samples = samples[: args.max_samples]
    sample_rows = [asdict(sample) for sample in samples]
    write_jsonl(output_dir / "turn_samples.jsonl", sample_rows)
    write_json(
        output_dir / "run_config.json",
        {
            "dataset_path": args.dataset_path,
            "n_samples": len(samples),
            "llm_base_url": args.llm_base_url,
            "llm_model": args.llm_model,
            "max_concurrency": args.max_concurrency,
            "max_samples": args.max_samples,
            "dry_run": args.dry_run,
        },
    )

    if args.dry_run:
        write_json(
            output_dir / "summary.json",
            {"n_samples": len(samples), "dry_run": True},
        )
        print(f"[DryRun] samples={len(samples)} output_dir={output_dir}")
        return

    if not args.llm_base_url or not args.llm_model:
        raise ValueError("--llm_base_url and --llm_model are required unless --dry_run is set")
    if args.max_concurrency <= 0:
        raise ValueError("--max_concurrency must be > 0")

    labels_path = output_dir / "turn_labels.jsonl"
    failure_path = output_dir / "failures.jsonl"
    completed = {str(row["sample_id"]) for row in read_jsonl(labels_path)}
    remaining = [sample for sample in samples if sample.sample_id not in completed]
    if failure_path.exists() and remaining:
        failure_path.unlink()

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
                append_jsonl(labels_path, future.result())
            except Exception as exc:
                append_jsonl(
                    failure_path,
                    {
                        "sample_id": sample.sample_id,
                        "test_id": sample.test_id,
                        "target_turn_idx": sample.target_turn_idx,
                        "error": repr(exc),
                    },
                )
            done += 1
            if done % 20 == 0 or done == len(remaining):
                print(f"[Progress] labeled_this_run={done}/{len(remaining)}")

    label_rows = read_jsonl(labels_path)
    failures = read_jsonl(failure_path)
    counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    level_counts: dict[str, dict[str, int]] = {}
    for row in label_rows:
        label = str(row["pseudo_correctness"])
        confidence = str(row["label_confidence"])
        level = str(row["math_level"])
        counts[label] = counts.get(label, 0) + 1
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
        level_counts.setdefault(level, {})
        level_counts[level][label] = level_counts[level].get(label, 0) + 1
    write_json(
        output_dir / "summary.json",
        {
            "n_samples": len(samples),
            "n_labeled": len(label_rows),
            "n_failures": len(failures),
            "label_counts": counts,
            "confidence_counts": confidence_counts,
            "label_counts_by_math_level": level_counts,
        },
    )
    print(json.dumps(read_jsonl(labels_path)[-1] if label_rows else {}, ensure_ascii=False, indent=2))
    print(f"[Done] output_dir={output_dir}")


if __name__ == "__main__":
    main()
