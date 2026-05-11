from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
XES_ROOT = Path(__file__).resolve().parents[1]
if str(XES_ROOT) not in sys.path:
    sys.path.insert(0, str(XES_ROOT))

from src.evaluation import is_prediction_correct


QUESTION_BANK_PATH = PROJECT_ROOT / "XES3G5M" / "metadata" / "questions.json"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs"


@dataclass(frozen=True)
class ProbeQuestion:
    question_id: str
    canonical_answer: str


PROBE_QUESTIONS = [
    ProbeQuestion(question_id="381", canonical_answer="B"),
    ProbeQuestion(question_id="384", canonical_answer="C"),
    ProbeQuestion(question_id="385", canonical_answer="<,<,>,>,=,>"),
    ProbeQuestion(question_id="386", canonical_answer="0.1,1/100"),
    ProbeQuestion(question_id="397", canonical_answer="18"),
    ProbeQuestion(question_id="1008", canonical_answer="3"),
    ProbeQuestion(question_id="1019", canonical_answer="C"),
    ProbeQuestion(question_id="1023", canonical_answer="A"),
]


def _load_questions() -> dict[str, dict[str, Any]]:
    with QUESTION_BANK_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("questions.json must be dict")
    return payload


def _question_text_block(question: dict[str, Any]) -> str:
    content = str(question.get("content") or "").replace("\n", " ").strip()
    options = question.get("options") or {}
    if not isinstance(options, dict):
        raise ValueError("question options must be dict")
    if not options:
        return content
    option_lines = [f"{key}. {value}" for key, value in options.items()]
    return f"{content}\n选项：{' '.join(option_lines)}"


def _extract_gold_answers(question: dict[str, Any]) -> list[str]:
    answers = question.get("answer")
    if not isinstance(answers, list) or not answers:
        raise ValueError("question answer must be non-empty list")
    return [str(item) for item in answers]


def _build_format_copy_prompt(canonical_answer: str) -> str:
    return (
        "这是格式测试，不需要解题。\n"
        "请只输出下面这行答案本身，不要解释，不要重复题目，不要加任何别的字。\n"
        f"{canonical_answer}"
    )


def _build_gold_render_prompt(question_block: str, canonical_answer: str) -> str:
    return (
        "这道题不用你计算。\n"
        "已知标准答案如下，请你只输出标准答案本身，不要解释，不要重复题目。\n"
        f"题目：{question_block}\n"
        f"标准答案：{canonical_answer}"
    )


def _build_math_solve_prompt(question_block: str) -> str:
    return (
        "请直接做这道中国小学三年级数学题。\n"
        "只输出最终答案，不要解释，不要重复题目。\n"
        "如果是选择题，只输出选项字母。\n"
        "如果是填空题，多个空用英文逗号连接。\n"
        f"题目：{question_block}"
    )


def _strict_match(prediction: str, canonical_answer: str) -> bool:
    return prediction.strip() == canonical_answer.strip()


def _call_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if model.startswith("qwen3-"):
        payload["enable_thinking"] = False

    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=raw,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"malformed response: {body}") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"empty content: {body}")
    return content.strip()


def _load_model_list(config_path: Path) -> tuple[str, str, list[str]]:
    with config_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("config must be object")
    base_url = str(payload.get("base_url") or "").strip()
    api_key_env = str(payload.get("api_key_env") or "").strip()
    model_rows = payload.get("models")
    if not base_url or not api_key_env or not isinstance(model_rows, list) or not model_rows:
        raise ValueError("config must contain base_url, api_key_env, models")
    models = [str(item).strip() for item in model_rows if str(item).strip()]
    if not models:
        raise ValueError("config models is empty")
    return base_url, api_key_env, models


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _write_markdown_summary(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# 小模型探针结果",
        "",
        f"- 运行时间：`{summary['run_timestamp']}`",
        f"- 题目数：`{summary['question_count']}`",
        "",
        "## 结论规则",
        "",
        "- `format_copy_strict_rate` 高：说明模型能照抄并按要求只输出答案",
        "- `gold_render_strict_rate` 高：说明模型在真实题面下也能稳定按格式输出已知标准答案",
        "- `math_solve_correct_rate` 低：说明主要问题是解题能力，而不是输出格式",
        "",
        "## 模型结果",
        "",
    ]
    for row in summary["model_summaries"]:
        lines.extend(
            [
                f"### {row['model']}",
                "",
                f"- `format_copy_strict_rate`: `{row['format_copy_strict_rate']:.3f}`",
                f"- `gold_render_strict_rate`: `{row['gold_render_strict_rate']:.3f}`",
                f"- `math_solve_strict_rate`: `{row['math_solve_strict_rate']:.3f}`",
                f"- `math_solve_correct_rate`: `{row['math_solve_correct_rate']:.3f}`",
                f"- `interpretation`: `{row['interpretation']}`",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe weak-model capability vs instruction-following.")
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path(__file__).resolve().parent / "configs" / "bailian_small_models.json"),
    )
    parser.add_argument("--api_key", type=str, default="")
    parser.add_argument("--output_root", type=str, default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--max_tokens_format", type=int, default=12)
    parser.add_argument("--max_tokens_math", type=int, default=24)
    args = parser.parse_args()

    config_path = Path(args.config)
    base_url, api_key_env, models = _load_model_list(config_path)
    api_key = args.api_key.strip() or os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise ValueError(f"missing api key: --api_key or env {api_key_env}")

    questions = _load_questions()
    output_dir = Path(args.output_root) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=False)

    records: list[dict[str, Any]] = []
    model_summaries: list[dict[str, Any]] = []

    for model in models:
        task_rows: list[dict[str, Any]] = []
        format_ok = 0
        gold_render_ok = 0
        math_strict_ok = 0
        math_correct_ok = 0
        total = 0

        for probe in PROBE_QUESTIONS:
            question = questions.get(probe.question_id)
            if question is None:
                raise ValueError(f"question not found: {probe.question_id}")
            question_block = _question_text_block(question)
            gold_answers = _extract_gold_answers(question)
            has_options = bool(question.get("options"))

            format_prediction = _call_chat_completion(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt=_build_format_copy_prompt(probe.canonical_answer),
                max_tokens=args.max_tokens_format,
            )
            gold_render_prediction = _call_chat_completion(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt=_build_gold_render_prompt(question_block, probe.canonical_answer),
                max_tokens=args.max_tokens_format,
            )
            math_prediction = _call_chat_completion(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt=_build_math_solve_prompt(question_block),
                max_tokens=args.max_tokens_math,
            )

            format_match = _strict_match(format_prediction, probe.canonical_answer)
            gold_render_match = _strict_match(gold_render_prediction, probe.canonical_answer)
            math_strict_match = _strict_match(math_prediction, probe.canonical_answer)
            math_correct = is_prediction_correct(math_prediction, gold_answers, has_options)

            format_ok += int(format_match)
            gold_render_ok += int(gold_render_match)
            math_strict_ok += int(math_strict_match)
            math_correct_ok += int(math_correct)
            total += 1

            task_rows.append(
                {
                    "model": model,
                    "question_id": probe.question_id,
                    "canonical_answer": probe.canonical_answer,
                    "format_copy_prediction": format_prediction,
                    "format_copy_strict_match": format_match,
                    "gold_render_prediction": gold_render_prediction,
                    "gold_render_strict_match": gold_render_match,
                    "math_solve_prediction": math_prediction,
                    "math_solve_strict_match": math_strict_match,
                    "math_solve_correct": math_correct,
                }
            )

        format_rate = format_ok / total
        gold_render_rate = gold_render_ok / total
        math_strict_rate = math_strict_ok / total
        math_correct_rate = math_correct_ok / total

        if format_rate >= 0.75 and gold_render_rate >= 0.75 and math_correct_rate <= 0.5:
            interpretation = "更像能力不足，不是单纯指令跟随差"
        elif format_rate < 0.5 or gold_render_rate < 0.5:
            interpretation = "存在明显指令跟随/格式输出问题"
        else:
            interpretation = "能力不足与指令跟随问题并存，需要继续看"

        model_summaries.append(
            {
                "model": model,
                "question_count": total,
                "format_copy_strict_rate": format_rate,
                "gold_render_strict_rate": gold_render_rate,
                "math_solve_strict_rate": math_strict_rate,
                "math_solve_correct_rate": math_correct_rate,
                "interpretation": interpretation,
            }
        )
        records.extend(task_rows)

    summary = {
        "run_timestamp": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "question_count": len(PROBE_QUESTIONS),
        "models": models,
        "model_summaries": model_summaries,
    }
    _write_json(output_dir / "probe_records.json", records)
    _write_json(output_dir / "probe_summary.json", summary)
    _write_markdown_summary(output_dir / "probe_summary.md", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"output_dir={output_dir}")


if __name__ == "__main__":
    main()
